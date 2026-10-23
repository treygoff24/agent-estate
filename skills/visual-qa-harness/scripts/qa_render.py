#!/usr/bin/env python3
"""Render an HTML file or URL headless and slice the full-page screenshot into
overlapping bands a vision model can actually read.

A long scroll page (an editorial explainer, a report, a dashboard) does not fit
in one legible screenshot: shrink it to fit and the text is unreadable; capture
it at full resolution and it is one 8000px-tall strip the model skims. This tool
captures the whole page at 2x, trims the trailing background, and slices the
result into square-ish bands with a small overlap so nothing is lost at a seam.
Read the bands in order to review the page top to bottom.

Default path is dependency-light: Chrome/Chromium headless + Pillow. No
Playwright, no node. Measures nothing via CDP; instead it lays the page out in a
very tall window and autocrops the uniform trailing margin, which is robust for
ordinary scroll pages. See --help and the SKILL.md for the slide-deck caveat.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops

# Full-page captures of long pages are legitimately huge (a 24000px window at 2x
# is ~115M px). Disable Pillow's decompression-bomb guard; the input is our own
# screenshot, not untrusted data.
Image.MAX_IMAGE_PIXELS = None


def find_chrome(explicit: str | None) -> str:
    if explicit:
        if Path(explicit).exists():
            return explicit
        sys.exit(f"error: --chrome path does not exist: {explicit}")
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    sys.exit("error: no Chrome/Chromium found. Install Chrome or pass --chrome <path>.")


def to_url(target: str) -> str:
    if target.startswith(("http://", "https://", "file://")):
        return target
    p = Path(target).expanduser().resolve()
    if not p.exists():
        sys.exit(f"error: file not found: {p}")
    return p.as_uri()


def capture(chrome, url, width, max_height, scale, settle_ms, out_png, timeout) -> None:
    out = Path(out_png)
    if out.exists():
        out.unlink()  # never slice a stale screenshot if this run's Chrome fails
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--force-device-scale-factor={scale}",
        f"--window-size={width},{max_height}",
        f"--screenshot={out_png}",
    ]
    if settle_ms:
        # Advance virtual time so late fonts/layout/animation settle before capture.
        cmd.append(f"--virtual-time-budget={settle_ms}")
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        sys.exit(f"error: chrome timed out after {timeout}s rendering {url}")
    if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        tail = (r.stderr or "")[-1500:]
        sys.exit(f"error: chrome produced no usable screenshot (exit {r.returncode}).\n{tail}")


def autocrop_bottom(img: Image.Image, margin: int):
    """Crop the uniform trailing background, keeping full width and the top.

    Returns (cropped_image, truncated, content_found). `truncated` is True when
    content reaches the bottom of the actual capture — a sign the real page is
    taller than --max-height and was cut off. `content_found` is False when the
    whole capture is one flat color (blank/failed render).

    The background is sampled from the bottom edge, not the top corner, so a page
    with a colored header but plain body still trims correctly.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    bg = rgb.getpixel((1, h - 2))  # trailing background lives at the bottom
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg))
    bbox = diff.getbbox()  # (left, upper, right, lower) of non-background content
    if not bbox:
        return img.crop((0, 0, w, min(h, 1400))), False, False
    lower = bbox[3]
    truncated = lower >= h - 2
    lower = min(h, lower + margin)
    return img.crop((0, 0, w, lower)), truncated, True


def slice_bands(img, band_h, overlap, out_dir: Path, prefix: str):
    w, h = img.size
    if band_h <= overlap:
        sys.exit("error: --band must be greater than --overlap")
    step = band_h - overlap
    bands, y, i = [], 0, 1
    while y < h:
        y2 = min(y + band_h, h)
        path = out_dir / f"{prefix}_{i:02d}.png"
        img.crop((0, y, w, y2)).save(path)
        bands.append((path, y, y2))
        if y2 >= h:
            break
        y += step
        i += 1
    return bands


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render an HTML file/URL and slice the full-page screenshot into readable bands.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("target", help="HTML file path or http(s)/file URL")
    ap.add_argument("--out", default="/tmp/qa_render", help="output directory (cleared of band_*.png first)")
    ap.add_argument("--width", type=int, default=1200, help="logical viewport width in px")
    ap.add_argument("--scale", type=float, default=2.0, help="device scale factor (2 = crisp text)")
    ap.add_argument("--max-height", type=int, default=24000, help="capture-window height; raise for very long pages")
    ap.add_argument("--band", type=int, default=2400, help="band height in output px (after scaling)")
    ap.add_argument("--overlap", type=int, default=220, help="vertical overlap between bands in output px")
    ap.add_argument("--margin", type=int, default=40, help="px of background kept below content after autocrop")
    ap.add_argument("--settle", type=int, default=0, metavar="MS", help="virtual-time budget to let fonts/anim settle (e.g. 1500)")
    ap.add_argument("--timeout", type=int, default=60, help="chrome process timeout in seconds")
    ap.add_argument("--no-autocrop", action="store_true", help="keep the full padded capture; do not trim trailing background")
    ap.add_argument("--keep-full", action="store_true", help="also keep full.png (the stitched full-page image)")
    ap.add_argument("--prefix", default="band", help="band filename prefix")
    ap.add_argument("--chrome", help="explicit path to a Chrome/Chromium binary")
    args = ap.parse_args()

    if args.band <= 0:
        sys.exit("error: --band must be positive")
    if not (0 <= args.overlap < args.band):
        sys.exit("error: --overlap must be >= 0 and < --band")
    if args.width <= 0 or args.max_height <= 0 or args.scale <= 0:
        sys.exit("error: --width, --max-height, and --scale must be positive")
    if args.margin < 0 or args.settle < 0:
        sys.exit("error: --margin and --settle must be >= 0")
    if args.prefix != Path(args.prefix).name or any(c in args.prefix for c in "*?[]"):
        sys.exit("error: --prefix must be a plain filename fragment (no path separators or glob chars)")

    chrome = find_chrome(args.chrome)
    url = to_url(args.target)
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{args.prefix}_*.png"):
        stale.unlink()

    full_png = out_dir / "full.png"
    capture(chrome, url, args.width, args.max_height, args.scale, args.settle, str(full_png), args.timeout)

    try:
        img = Image.open(full_png)
        img.load()
    except Exception as e:
        sys.exit(f"error: could not read screenshot {full_png}: {e}")
    truncated = False
    content_found = True
    if not args.no_autocrop:
        img, truncated, content_found = autocrop_bottom(img, args.margin)

    bands = slice_bands(img, args.band, args.overlap, out_dir, args.prefix)

    if args.keep_full:
        img.save(full_png)
    elif full_png.exists():
        full_png.unlink()

    w, h = img.size
    print(f"rendered: {url}")
    print(f"page:     {w}x{h}px  (width {args.width} @ {args.scale}x)")
    print(f"bands:    {len(bands)}  ->  {out_dir}")
    for path, y, y2 in bands:
        print(f"  {path.name}  rows {y}-{y2}")
    if not content_found:
        print(
            "\nNOTE: no non-background content detected — the page may be blank or "
            "failed to render. Check the URL/path and try --settle 1500.",
            file=sys.stderr,
        )
    if truncated:
        print(
            f"\nWARNING: content reached the bottom of the {args.max_height}px window — "
            f"the page is likely taller and was cut off. Re-run with a larger --max-height.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
