---
name: visual-qa-harness
description: Render an HTML file or URL with headless Chrome and slice the full-page screenshot into overlapping, legible bands so you (a vision model) can actually read and QA a long scroll page top to bottom. Use after building or editing any self-contained HTML artifact — a visual-explainer, a report, a built deck, a landing page, a dashboard — when you need to SEE whether it rendered correctly: text overlaps, label/curve collisions, broken layout, overflow, orphaned headings, wrong colors, clipped SVG. Bundles a dependency-light script (Chrome/Chromium + Pillow, no Playwright/node). Invoke when the user says "QA this page", "screenshot and check it", "does this render right", or proactively as the verify step after building any self-contained HTML page.
---

# Visual QA harness — render, then read the page in bands

A long HTML page can't be QA'd from the source alone, and it can't be QA'd from one screenshot either. Shrink a 16000px page to fit one image and the text is a blur; capture it at full resolution and it's a single strip you skim instead of read. This skill captures the whole page at 2x, trims the trailing background, and slices it into square-ish overlapping bands. You then **read the bands in order with the Read tool** — each one is a legible screenful, and the overlap means nothing hides in a seam.

This is the verify step for any self-contained HTML page you build. Build the HTML, run the harness, read the bands, fix what you see, re-run. It's the difference between "the markup looks right" and "the page looks right."

## The one command

```bash
python3 ~/.claude/skill-library/visual-qa-harness/scripts/qa_render.py <file-or-url> [--out DIR]
```

Then Read `DIR/band_01.png`, `band_02.png`, … in order. Default `DIR` is `/tmp/qa_render` (band files there are cleared on each run, so each QA pass is clean).

Example:

```bash
python3 ~/.claude/skill-library/visual-qa-harness/scripts/qa_render.py \
  ~/work/ip-tightenings-explainer.html --out /tmp/ipqa
# -> bands: 8  ->  /tmp/ipqa
# then: Read /tmp/ipqa/band_01.png ... band_08.png
```

It prints, for each band, the pixel row range it covers, so you can point a fix at "the collision around row 4300" and re-render just to confirm.

## How it works (so you can reason about failures)

1. Lays the page out in a tall window (`--width` × `--max-height`, default 1200×24000) at `--scale` 2x, and takes one Chrome `--headless=new --screenshot`. The tall window is what forces the full page to render; Chrome's CLI has no true "full-page" flag, so we oversize and trim.
2. **Autocrops** the uniform trailing background with Pillow (`getbbox` against the corner background color), keeping full width. This is why the output ends at the real bottom of the content, not at 24000px of whitespace.
3. **Slices** into bands of `--band` px (default 2400) with `--overlap` px (default 220) shared between neighbors.

If content reaches the bottom of the capture window, it prints a `WARNING` that the page was likely cut off — re-run with a larger `--max-height`.

## Flags worth knowing

- `--width` (default 1200): logical viewport width. Drop to ~390 to QA the mobile layout.
- `--scale` (default 2): device scale. 2 keeps text crisp for reading; 3 for tiny type.
- `--max-height` (default 24000): raise for very long pages (the WARNING tells you when).
- `--band` / `--overlap` (default 2400 / 220): band size and seam overlap, in output px.
- `--settle MS` (e.g. `--settle 1500`): advance virtual time so late web fonts / animation / layout settle before capture. Use it if a band shows fallback fonts or a half-finished transition.
- `--keep-full`: also write `full.png`, the whole stitched page, for a one-glance overview or to attach.
- `--no-autocrop`: keep the padded capture (debugging the autocrop itself).
- `--chrome PATH`: point at a specific Chrome/Chromium binary.

## Caveats

- **Slide decks / `100dvh` pages.** This tool is built for *scroll* pages. A deck whose slides are sized to the viewport will render each slide at the full `--max-height`, which is wrong. For a deck, either capture one slide at a time at a real viewport height (`--max-height 800 --no-autocrop` per slide URL/anchor) or screenshot it through a different path. The dominant use — long editorial explainers and reports — is exactly what the defaults are tuned for.
- **Autocrop assumes a solid page background.** Pages with a full-bleed photo or gradient running to the very bottom won't trim (harmless — you just get some extra background in the last band).
- **Requires Chrome/Chromium and Pillow.** The script finds Chrome in the usual macOS/Linux locations or via `--chrome`.

## Why this exists

The loop (which was first done by hand several times in one session, catching a text/line overlap and a label/curve collision that were invisible in the source) — render full-page at 2x, band-slice, read each band — is the same every time, so it's a script now.
