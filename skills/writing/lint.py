#!/usr/bin/env python3
"""Deterministic prose lint for the writing skill.

Run AFTER drafting:  python3 lint.py [--genre NAME] [--to-owner] [--internal] [--json] FILE...
Exit 0 = no hard findings (warnings allowed), 1 = hard findings, 2 = usage error.

A drafting context never reads this file. It holds the machine-checkable
pattern tables so the drafting path can describe the target voice without
naming what it wants absent. Judgment-tier patterns live in
review/cold-audit.md, loaded by auditors only.

Exempt from phrase and density checks: YAML frontmatter, fenced code, HTML
comment blocks, blockquote lines (someone else's words), double-quoted spans
inside a line, and any line carrying the waiver marker `lint-ok` (put it in
an HTML comment: <!-- lint-ok: reason -->; `riverlint-ok` still works).

Genre settings come from genres/<name>.md frontmatter next to this file:
`words:` is the length budget, `bold_leads: off` flags bold-lead-in bullets, and
`bullet_words:` (default 30) is the longest bullet the genre carries.
"""

import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- character-level rules (hard) --------------------------------------------

CHAR_RULES = [
    (re.compile(r"—"), "em-dash", "em dash; restructure with comma/colon/period"),
    (re.compile(r"\s–\s"), "en-dash-punct", "spaced en dash used as punctuation"),
    (re.compile(r"\w\s+-\s+\w"), "hyphen-punct", "spaced hyphen used as dash punctuation"),
]
CURLY_RE = re.compile(r"[“”‘’]")

BULLET_RE = re.compile(r"^\s*[-*•]\s+\S")
BOLD_LEADIN_RE = re.compile(r"^\s*[-*•]\s+\*\*[^*]+?\*\*")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
FLAG_RE = re.compile(r"\[CHECK:")

MINOR_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "is",
               "of", "on", "or", "the", "to", "vs", "via", "with"}


def is_title_case(text):
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", text) if len(w) > 1]
    if len(words) < 3:
        return False
    caps = [w for w in words if w[0].isupper()]
    minor_caps = [w for w in words[1:] if w.lower() in MINOR_WORDS and w[0].islower()]
    return len(caps) >= max(3, int(0.8 * len(words))) and (len(minor_caps) > 0 or len(caps) == len(words))


def has_emoji(line):
    for ch in line:
        if ord(ch) >= 0x1F000 or (0x2600 <= ord(ch) <= 0x27BF):
            if unicodedata.category(ch) in ("So", "Sk"):
                return True
    return False


# --- lexicon rules (hard; word-boundary, case-insensitive) --------------------

def rx(p):
    return re.compile(r"\b" + p + r"\b", re.IGNORECASE)

HARD = [
    (rx(r"delv(e|es|ed|ing)"), "delve"),
    (rx(r"a testament to|testament to (the|its|their|his|her)"), "testament-to"),
    (rx(r"foster(s|ed|ing)? a sense of"), "fostering-a-sense"),
    (rx(r"boast(s|ed|ing)? (a|an|the|over|more)"), "boasts"),
    (rx(r"nestled"), "nestled"),
    (rx(r"renowned"), "renowned"),
    (rx(r"breathtaking"), "breathtaking"),
    (rx(r"groundbreaking"), "groundbreaking"),
    (rx(r"stunning"), "stunning"),
    (rx(r"in the heart of"), "heart-of"),
    (rx(r"evolving landscape"), "landscape-abstract"),
    (rx(r"serves? as (a|an|the)"), "serves-as"),
    (rx(r"stands? as (a|an|the)"), "stands-as"),
    (rx(r"stands? out as"), "stands-out-as"),
    (rx(r"plays? a (vital|crucial|key|pivotal|critical) role"), "vital-role"),
    (rx(r"highlight(s|ed|ing)? the (importance|need|significance)"), "highlighting-importance"),
    (rx(r"emphasiz(es|ed|ing) the (importance|need)"), "emphasizing-need"),
    (rx(r"setting the stage for"), "setting-the-stage"),
    (rx(r"paves? the way"), "paves-the-way"),
    (rx(r"in today's"), "in-todays"),
    (rx(r"in an era of"), "era-of"),
    (rx(r"it'?s not (just|only|merely) about"), "not-just-about"),
    (rx(r"it is (important|worth) (to note|noting)"), "important-to-note"),
    (rx(r"it'?s worth noting"), "worth-noting"),
    (rx(r"in order to"), "in-order-to"),
    (rx(r"due to the fact that"), "due-to-the-fact"),
    (rx(r"at this point in time"), "at-this-point"),
    (rx(r"has the ability to"), "has-ability-to"),
    (rx(r"I hope this helps"), "chatbot-residue"),
    (rx(r"great question"), "sycophancy"),
    (rx(r"you'?re absolutely right"), "sycophancy"),
    (rx(r"as of my last (update|training)"), "cutoff-disclaimer"),
    (rx(r"would you like me to"), "chatbot-residue"),
    (rx(r"experts (say|agree|note|believe)"), "vague-attribution"),
    (rx(r"industry observers"), "vague-attribution"),
    (rx(r"some critics (argue|say|contend)"), "vague-attribution"),
    (rx(r"the future (looks|is) bright"), "generic-conclusion"),
    (rx(r"exciting times (lie )?ahead"), "generic-conclusion"),
    (rx(r"to be (perfectly |brutally )?honest|candidly|let me be (frank|clear|honest|blunt)"), "performed-candor"),
    (rx(r"I (will|won'?t) (not )?(pretend|sugarcoat|bury the lede)"), "performed-candor"),
    (rx(r"(that|this) (context )?matters,? because"), "self-narration"),
    (rx(r"I want to be (precise|clear|honest) about"), "self-narration"),
    (rx(r"what this means is"), "self-narration"),
    (rx(r"to put (this|that) in perspective"), "self-narration"),
    (rx(r"moreover"), "moreover"),
    (rx(r"furthermore"), "furthermore"),
    (rx(r"additionally"), "additionally"),
]

# Document self-reference. Hard in external docs,
# a warning under --internal, where a working doc may point at its own parts.
META = [
    (rx(r"this (memo|document|brief|section|paper|note|update|explainer) (has|covers|lays out|walks|contains|is organized|presents|explains)"), "meta-doc-self-ref"),
    (rx(r"(one|a) (structural|quick|brief|final) note before"), "meta-windup"),
    (rx(r"here'?s the (part|thing|piece) that matters"), "meta-windup"),
    (rx(r"(the|a) (list|table|section|discussion) (below|above|that follows)"), "meta-doc-nav"),
    (rx(r"as (noted|mentioned|discussed) (above|earlier|below)"), "meta-doc-nav"),
    (rx(r"(carry|carries|carrying) the rest of the"), "meta-choreography"),
    (rx(r"(more|further) on (this|that) (below|later)"), "meta-doc-nav"),
    (rx(r"(the next|this) section (turns to|takes up|addresses)"), "meta-choreography"),
    (rx(r"before (we|I) (get|turn|move) to"), "meta-choreography"),
    (rx(r"(worth|bears) (noting|mentioning|saying) (that|plainly|up front)"), "meta-windup"),
]

# Density-gated: (regex, rule, warn_at, fail_at) per ~1,000 words. Human prose
# uses these sparingly; machine prose uses them at density.
DENSITY = [
    (rx(r"honest(ly)?"), "candor-tic-honest", 1, 2),
    (rx(r"genuine(ly)?"), "intensifier-genuine", 1, 2),
    (rx(r"crucial(ly)?"), "crucial", 1, 2),
    (rx(r"pivotal"), "pivotal", 1, 2),
    (rx(r"foster(s|ing|ed)?"), "foster", 1, 2),
    (rx(r"showcas(e|es|ing|ed)"), "showcase", 1, 2),
    (rx(r"underscor(es|ed|ing)"), "underscore-verb", 1, 2),
    (rx(r"highlight(s|ing|ed)"), "highlight-verb", 2, 3),
    (rx(r"the \w+ landscape|landscape"), "landscape-abstract", 1, 2),
    (rx(r"tapestry"), "tapestry", 1, 1),
    (rx(r"intricate|intricacies"), "intricate", 1, 2),
    (rx(r"garner(s|ed|ing)?"), "garner", 1, 2),
    (rx(r"interplay"), "interplay", 1, 2),
    (rx(r"vibrant"), "vibrant", 1, 2),
    (rx(r"robust"), "robust", 2, 3),
    (rx(r"seamless(ly)?"), "seamless", 1, 2),
    (rx(r"leverag(e|es|ing|ed)"), "leverage-verb", 2, 3),
    # negative parallelisms: contrast is a spice; a piece that earns two keeps two
    (rx(r"not (just|only|merely) [^.;:\n]{2,60}?,? but( also)?"), "not-just-but", 2, 3),
    (re.compile(r"\bnot (?:a |an |the |to |about |for )?[^.;:,\n]{1,40}?,? but (?:rather |instead |simply |a |an |the |to )?(?!(?:I|we|he|she|they|it|you|that|this)\b)\w", re.IGNORECASE), "not-x-but-y", 2, 3),
]
INTERNAL_RELAXED = {"candor-tic-honest", "intensifier-genuine"}

# Time-estimate phrases in anything addressed to the owner.
TIME_ESTIMATE = [
    rx(r"(will|should|would|could|might|going to|gonna) (take|be done|be ready|be finished|finish|land|wrap( up)?)[^.;]{0,30}?\d+\s?(min|mins|minutes?|hours?|hrs?|days?|weeks?)"),
    rx(r"(takes?|taking|took) (about|around|roughly|approximately|~)?\s?\d+\s?(min|mins|minutes?|hours?|hrs?|days?|weeks?)"),
    rx(r"in (about|around|roughly|approximately|~)?\s?\d+\s?(min|mins|minutes?|hours?|hrs?|days?)(?! (on|of|from|before|after|since|per))"),
    rx(r"\d+[- ](minute|hour|day|week) (job|task|fix|build|run|effort|change)"),
    rx(r"(should|will|would) (be )?(done|ready|finished|complete) (by|in|within) (the )?(end of|about|\d+|an hour|a day|tonight|today|tomorrow|this)"),
    rx(r"back (to you )?in \d+\s?(min|mins|minutes?|hours?)"),
    rx(r"ETA"),
]

HEDGE_RE = rx(r"may|might|could|perhaps|possibly|arguably|likely|probably|seems?|appears?|somewhat|to some extent|potentially|tends? to|in some cases|it is possible")
SENT_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"')\]]))\s+(?=[A-Z\"'(])")


# --- document masking ---------------------------------------------------------

FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})")
FRONTMATTER_DELIM_RE = re.compile(r"^---[ \t]*$")
QUOTED_SPAN = re.compile(r'"[^"\n]*"|“[^”\n]*”')
WAIVERS = ("lint-ok", "riverlint-ok")


def fence_states(lines, start=0):
    """Per-line in-fence mask. An opener records its delimiter character and
    run length; only a run of the same character at least that long, followed
    by whitespace, closes it. Opener and closer lines both count as fenced."""
    states = [False] * len(lines)
    open_char, open_len = None, 0
    for i in range(start, len(lines)):
        if open_char is None:
            m = FENCE_OPEN_RE.match(lines[i])
            if m:
                open_char, open_len = m.group(1)[0], len(m.group(1))
                states[i] = True
            continue
        states[i] = True
        stripped = lines[i].lstrip()
        run = 0
        while run < len(stripped) and stripped[run] == open_char:
            run += 1
        if run >= open_len and not stripped[run:].strip():
            open_char, open_len = None, 0
    return states


def comment_states(lines, start=0):
    """Per-line mask for HTML comment blocks (<!-- ... -->), multi-line or
    single-line. A line that opens and closes a comment is masked whole only
    when the comment is the entire line."""
    states = [False] * len(lines)
    inside = False
    for i in range(start, len(lines)):
        line = lines[i]
        if inside:
            states[i] = True
            if "-->" in line:
                inside = False
            continue
        s = line.strip()
        if s.startswith("<!--"):
            states[i] = True
            if "-->" not in s:
                inside = True
    return states


def body_start_of(lines):
    if lines and FRONTMATTER_DELIM_RE.match(lines[0]):
        for j in range(1, len(lines)):
            if FRONTMATTER_DELIM_RE.match(lines[j]):
                return j + 1
    return 0


def split_paragraphs(lines):
    buf, start = [], None
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if start is None:
                start = i
            buf.append(stripped)
        else:
            if buf:
                yield start, " ".join(buf)
            buf, start = [], None
    if buf:
        yield start, " ".join(buf)


SENT_END_RE = re.compile(r"[.!?][\"')\]]*\s")


def count_sentences(text):
    return len(SENT_END_RE.findall(text + " "))


# --- genre settings -----------------------------------------------------------

def genre_settings(name):
    """Read words: and bold_leads: from genres/<name>.md frontmatter."""
    if not name:
        return {}
    p = HERE / "genres" / f"{name}.md"
    if not p.is_file():
        raise SystemExit(f"lint.py: no genre file {p}")
    lines = p.read_text(encoding="utf-8").splitlines()
    end = body_start_of(lines)
    out = {}
    for line in lines[1:max(end - 1, 1)]:
        m = re.match(r"^(\w+):\s*(.+?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


# --- the scan -----------------------------------------------------------------

def scan_text(text, path="<text>", genre=None, to_owner=False, internal=False):
    hits = []  # (line, rule, severity, msg)

    def add(n, rule, sev, msg):
        hits.append((n, rule, sev, msg))

    settings = genre_settings(genre)
    bullet_words = int(settings.get("bullet_words", 30))
    lines = text.splitlines()
    body_start = body_start_of(lines)
    fence = fence_states(lines, body_start)
    comment = comment_states(lines, body_start)
    masked = [n <= body_start or fence[n - 1] or comment[n - 1] for n in range(1, len(lines) + 1)]
    prose_lines = ["" if masked[n - 1] else line for n, line in enumerate(lines, 1)]

    # scannable: prose lines minus blockquotes, waivers, and quoted spans
    scannable = {}
    for n, line in enumerate(lines, 1):
        if masked[n - 1] or line.lstrip().startswith(">") or any(w in line for w in WAIVERS):
            continue
        scannable[n] = QUOTED_SPAN.sub("", line)

    words = max(sum(len(re.findall(r"\b\w+\b", l)) for l in scannable.values()), 1)
    scale = max(1.0, words / 1000.0)

    # per-line hard rules
    for n, line in enumerate(lines, 1):
        if masked[n - 1]:
            continue
        stripped = line.strip()
        if not internal and CURLY_RE.search(line):
            add(n, "curly-quote", "FAIL", f"curly quote; use straight quotes :: {stripped[:80]}")
        elif internal and CURLY_RE.search(line):
            add(n, "curly-quote", "WARN", f"curly quote; house style is straight :: {stripped[:80]}")
        if BULLET_RE.match(line):
            item = re.sub(r"^\s*[-*•]\s+", "", line)
            if len(item.split()) > bullet_words:
                add(n, "bullet-as-paragraph", "FAIL",
                    f"bullet carrying {len(item.split())} words; reasoning belongs in prose :: {item[:70]}")
        if settings.get("bold_leads") == "off" and BOLD_LEADIN_RE.match(line):
            add(n, "bold-leadin", "FAIL",
                f"inline-header list; this genre carries its points in prose :: {stripped[:70]}")
        m = HEADING_RE.match(line)
        if m and is_title_case(m.group(1)):
            add(n, "title-case-heading", "FAIL", f"heading in Title Case :: {m.group(1)[:60]}")
        if has_emoji(line):
            add(n, "emoji", "FAIL", f"decorative emoji :: {stripped[:60]}")
        if n not in scannable:
            continue
        text_n = scannable[n]
        for pat, rule, msg in CHAR_RULES:
            if pat.search(text_n):
                add(n, rule, "FAIL", msg + f" :: {stripped[:80]}")
        for pat, rule in HARD:
            m = pat.search(text_n)
            if m:
                add(n, rule, "FAIL", f"'{m.group(0)}' :: {stripped[:80]}")
        for pat, rule in META:
            m = pat.search(text_n)
            if m:
                add(n, rule, "WARN" if internal else "FAIL", f"'{m.group(0)}' :: {stripped[:80]}")
        if to_owner:
            for pat in TIME_ESTIMATE:
                m = pat.search(text_n)
                if m:
                    add(n, "time-estimate", "FAIL",
                        f"time estimate to the owner; give order and dependencies :: '{m.group(0)}'")
                    break

    # density-gated rules
    for pat, rule, warn_at, fail_at in DENSITY:
        found = [(n, m.group(0)) for n, l in scannable.items() for m in pat.finditer(l)]
        if not found:
            continue
        k = len(found)
        eff_warn = max(warn_at, math.ceil(warn_at * scale))
        eff_fail = max(fail_at, math.ceil(fail_at * scale))
        sev = "FAIL" if k >= eff_fail else ("WARN" if k >= eff_warn else None)
        if sev == "FAIL" and internal and rule in INTERNAL_RELAXED:
            sev = "WARN"
        if sev:
            for n, frag in found:
                add(n, rule, sev, f"'{frag}' ({k}x in {words} words)")

    # hedge stacking, per sentence
    for start, para in split_paragraphs([scannable.get(n, "") for n in range(1, len(lines) + 1)]):
        for sent in SENT_SPLIT_RE.split(para):
            k = len(HEDGE_RE.findall(sent))
            if k >= 3:
                add(start, "hedge-stack", "FAIL" if k >= 4 else "WARN",
                    f"{k} hedges in one sentence; keep one :: {sent.strip()[:80]}")

    # flag count
    flags = sum(len(FLAG_RE.findall(l)) for n, l in enumerate(prose_lines, 1))
    if flags > 3:
        add("-", "assert-or-cut", "FAIL",
            f"{flags} [CHECK:] flags; a flag is for a contradiction with the public record or a legal line, so assert the rest or cut them")

    # bullet-heavy document
    content = [l for l in prose_lines[body_start:] if l.strip()]
    bullets = [l for l in content if BULLET_RE.match(l)]
    if len(content) >= 12 and len(bullets) / len(content) > 0.4 and settings.get("bold_leads") != "on":
        add("-", "bullet-heavy", "FAIL",
            f"{len(bullets)}/{len(content)} content lines are bullets; convert reasoning to prose")

    # stacked single-sentence paragraphs
    run, run_start = 0, None
    for start, para in split_paragraphs(prose_lines):
        if para.lstrip().startswith((">", "- ", "* ", "|")):
            run, run_start = 0, None
            continue
        if count_sentences(para) <= 1 and len(para) > 20:
            run += 1
            if run_start is None:
                run_start = start
            if run == 3:
                add(run_start, "stacked-one-liners", "FAIL", "3+ consecutive single-sentence paragraphs")
        else:
            run, run_start = 0, None

    # length budget from the genre file
    budget = settings.get("words")
    if budget and budget.isdigit():
        budget = int(budget)
        if words > budget * 1.25:
            add("-", "length-budget", "FAIL", f"{words} words against a {budget}-word {genre} budget; cut")
        elif words > budget:
            add("-", "length-budget", "WARN", f"{words} words against a {budget}-word {genre} budget")

    return hits


def scan_file(path, **kw):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"lint.py: cannot read {path}: {e}", file=sys.stderr)
        return [("-", "error", "FAIL", str(e))]
    return scan_text(text, path=str(path), **kw)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic prose lint (writing skill)")
    ap.add_argument("files", nargs="+", help="markdown or text files")
    ap.add_argument("--genre", help="genre name; reads genres/<name>.md for budget and bullet settings")
    ap.add_argument("--to-owner", action="store_true", help="the text is addressed to the owner: flag time estimates")
    ap.add_argument("--internal", action="store_true", help="internal document: relax curly quotes, candor tics, and self-reference to warnings")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    all_hits = []
    for f in args.files:
        if not Path(f).is_file():
            print(f"lint.py: no such file: {f}", file=sys.stderr)
            return 2
        for n, rule, sev, msg in scan_file(f, genre=args.genre, to_owner=args.to_owner, internal=args.internal):
            all_hits.append({"file": f, "line": n, "rule": rule, "severity": sev, "msg": msg})

    fails = [h for h in all_hits if h["severity"] == "FAIL"]
    if args.json:
        print(json.dumps({"ok": not fails, "findings": all_hits}, indent=1))
    else:
        for h in sorted(all_hits, key=lambda h: (h["file"], 0 if h["line"] == "-" else h["line"])):
            print(f"{h['file']}:{h['line']}: {h['severity']} [{h['rule']}] {h['msg']}")
        print(f"\n{len(fails)} hard finding(s), {len(all_hits) - len(fails)} warning(s)." if all_hits else "clean.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
