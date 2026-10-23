#!/usr/bin/env python3
"""Fail if any file in the repo matches a private marker.

The markers are regexes, one per line (blank lines and # comments skipped),
matched case-insensitively. A line "allow: <regex>" is an allowance instead:
text it matches is blanked out of each line before the markers run, so a
public link such as https://github.com/<you>/<tool> can stay while every
other use of the same name is still caught. They are read from, in order:
  $ESTATE_PRIVATE_MARKERS, <repo>/.private-markers (git-ignored),
  ~/.config/agent-estate/private-markers.
The marker file itself never belongs in the repo. With no marker file the
scan is skipped with a loud warning (exit 0), so a fresh clone still gates.

Built-in markers (always on): absolute paths into a named home directory
under /Users or /home, except for the placeholder names you, <you>,
example and user. Write ~/ instead.

Scanned: every tracked file plus untracked files that are not git-ignored,
so a new file is caught before it is added; file paths are scanned too.
Allowed: the copyright line of LICENSE (it names the author on purpose).
Output: path:line:pattern for each hit, never the matching text.
Exit: 0 clean (or skipped), 1 hits, 2 bad marker file.

Usage: scan-private.py [repo-dir]   (default: the repo holding this script)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MARKERS = "~/.config/agent-estate/private-markers"
PLACEHOLDER_NAMES = r"(?!(?:you|<you>|example|user)/)"
BUILTIN = [
    # Case-sensitive: a capitalised home path is private, /users/${id}/ is an API route.
    r"(?-i:/Users/)" + PLACEHOLDER_NAMES + r"[^/\s'\"`]+/",
    r"/home/" + PLACEHOLDER_NAMES + r"[^/\s'\"`]+/",
]
LICENSE_ALLOW = re.compile(r"^\s*Copyright\s+(\(c\)|©)\s+\d{4}")


def marker_file(repo: Path) -> Path | None:
    env = os.environ.get("ESTATE_PRIVATE_MARKERS")
    if env:
        return Path(os.path.expanduser(env))
    for p in (repo / ".private-markers", Path(os.path.expanduser(DEFAULT_MARKERS))):
        if p.is_file():
            return p
    return None


def load_markers(path: Path) -> tuple[list[str], list[str]]:
    """Return (markers, allowances) from a marker file."""
    out, allow = [], []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        dest = out
        if s.startswith("allow:"):
            s, dest = s[len("allow:"):].strip(), allow
        try:
            re.compile(s)
        except re.error as e:
            raise ValueError(f"{path}:{n}: bad regex: {e}") from None
        dest.append(s)
    return out, allow


def repo_files(repo: Path) -> list[str]:
    p = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others",
                        "--exclude-standard"], capture_output=True, check=True)
    return sorted({f for f in p.stdout.decode().split("\0") if f})


def scan(repo: Path, patterns: list[str], files: list[str],
         allow: list[str] = ()) -> list[tuple[str, int, str]]:
    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in patterns]
    allowed = [re.compile(a, re.IGNORECASE) for a in allow]
    hits = []
    for rel in files:
        for pat, rx in compiled:
            if rx.search(rel):
                hits.append((rel, 0, pat))
        f = repo / rel
        if not f.is_file():
            continue  # deleted in the work tree, or a submodule
        text = f.read_bytes().decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            if rel == "LICENSE" and LICENSE_ALLOW.match(line):
                continue
            for ax in allowed:
                line = ax.sub(" ", line)
            for pat, rx in compiled:
                if rx.search(line):
                    hits.append((rel, n, pat))
    return hits


def main(argv) -> int:
    repo = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    mf = marker_file(repo)
    patterns = list(BUILTIN)
    allow: list[str] = []
    note = "builtin only"
    if mf is None or not mf.is_file():
        bar = "!" * 72
        print(f"{bar}\nscan-private: WARNING: no private-marker file "
              f"({mf or 'set ESTATE_PRIVATE_MARKERS or create ' + DEFAULT_MARKERS}).\n"
              f"Only the built-in home-path markers ran; personal names, hosts and "
              f"emails were NOT checked.\n{bar}", file=sys.stderr)
    else:
        try:
            extra, allow = load_markers(mf)
        except ValueError as e:
            print(f"scan-private: {e}", file=sys.stderr)
            return 2
        patterns += extra
        note = f"{len(extra)} markers" + (f", {len(allow)} allowances" if allow else "")
    files = repo_files(repo)
    hits = scan(repo, patterns, files, allow)
    for rel, n, pat in hits:
        print(f"{rel}:{n}:{pat}")
    verdict = "FAIL" if hits else "clean"
    print(f"scan-private: {verdict}: {len(hits)} hits in {len(files)} files ({note})",
          file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
