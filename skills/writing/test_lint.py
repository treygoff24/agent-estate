#!/usr/bin/env python3
"""Tests for lint.py. Every new rule has a single-defect fixture that fires and
a clean twin that does not; red-proofed against an older scanner (it returned no hit for each defect fixture)."""

import unittest
from pathlib import Path

import lint

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fenced-blocks.md"

CLEAN_BRIDGE = ("Prose bridge paragraph that clears the twenty char bound with ease.\n\n"
                "Second prose paragraph has two sentences. It resets any running count.\n")

STACKED_DOC = """# Stacked

First single sentence paragraph that runs longer than twenty characters.

Second single sentence paragraph that runs longer than twenty characters.

Third single sentence paragraph that runs longer than twenty characters.
"""

TILDE_DOC = """Prose opener with two sentences. Resets the run cleanly.

~~~python
alpha payload sentence long enough to clear twenty chars.

beta payload sentence long enough to clear twenty chars.

gamma payload sentence long enough to clear twenty chars.
~~~
"""

QUAD_BACKTICK_DOC = """Prose opener with two sentences. Resets the run cleanly.

````sh
```
alpha payload sentence long enough to clear twenty chars.

beta payload sentence long enough to clear twenty chars.

gamma payload sentence long enough to clear twenty chars.
````
"""

BLOCK_SCALAR_DOC = """---
name: block-scalar-frontmatter
notes: |
  keep
  ---
  keep
description: a tapestry for the block scalar test
---

Prose bridge paragraph that clears the twenty char bound with ease.

Second prose paragraph has two sentences. It resets any running count.

The flagged line carries an em dash — and must report line fourteen.
"""

TRAILING_SPACE_DOC = (
    "---   \n"
    "name: trailing-space-frontmatter\n"
    "description: a tapestry behind the trailing-space delimiter\n"
    "---    \n"
    "\n"
    "Prose bridge paragraph that clears the twenty char bound with ease.\n"
    "\n"
    "Second prose paragraph has two sentences. It resets any running count.\n"
    "\n"
    "The flagged line carries an em dash — and must report line ten.\n"
)


def rules(text, **kw):
    return [rule for _, rule, _, _ in lint.scan_text(text, **kw)]


def fails(text, **kw):
    return [rule for _, rule, sev, _ in lint.scan_text(text, **kw) if sev == "FAIL"]


class CarriedOverFromScanPy(unittest.TestCase):
    def test_fenced_blocks_are_not_prose(self):
        self.assertEqual(lint.scan_file(FIXTURE), [])

    def test_stacked_one_liners_fire_outside_fences(self):
        self.assertIn("stacked-one-liners", rules(STACKED_DOC))

    def test_tilde_fence_payload_is_not_prose(self):
        self.assertEqual(lint.scan_text(TILDE_DOC), [])

    def test_shorter_backtick_run_does_not_close_longer_fence(self):
        self.assertEqual(lint.scan_text(QUAD_BACKTICK_DOC), [])

    def test_indented_frontmatter_delimiter_is_not_the_closer(self):
        hits = [(n, rule) for n, rule, _, _ in lint.scan_text(BLOCK_SCALAR_DOC)]
        self.assertEqual(hits, [(14, "em-dash")])

    def test_trailing_space_delimiters_bound_frontmatter(self):
        hits = [(n, rule) for n, rule, _, _ in lint.scan_text(TRAILING_SPACE_DOC)]
        self.assertEqual(hits, [(10, "em-dash")])


class Exemptions(unittest.TestCase):
    def test_blockquote_is_someone_elses_words(self):
        self.assertNotIn("em-dash", rules(CLEAN_BRIDGE + "\n> He wrote — and meant it — every word.\n"))
        self.assertIn("em-dash", rules(CLEAN_BRIDGE + "\nHe wrote — and meant it — every word.\n"))

    def test_quoted_span_is_exempt(self):
        self.assertNotIn("testament-to", rules(CLEAN_BRIDGE + '\nShe called it "a testament to grit" and left.\n'))
        self.assertIn("testament-to", rules(CLEAN_BRIDGE + "\nShe called it a testament to grit and left.\n"))

    def test_waiver_marker_skips_the_line(self):
        self.assertNotIn("delve", rules(CLEAN_BRIDGE + "\nWe delve into it here. <!-- lint-ok: quoting the brief -->\n"))
        self.assertNotIn("delve", rules(CLEAN_BRIDGE + "\nWe delve into it here. <!-- riverlint-ok: legacy marker -->\n"))
        self.assertIn("delve", rules(CLEAN_BRIDGE + "\nWe delve into it here.\n"))

    def test_html_comment_block_is_not_prose(self):
        doc = "<!--META\ntitle: We delve into a tapestry\nfooter-tag: x\n-->\n\n" + CLEAN_BRIDGE
        self.assertEqual(lint.scan_text(doc), [])


class NewRules(unittest.TestCase):
    def test_flag_count_assert_or_cut(self):
        four = CLEAN_BRIDGE + "\n".join(f"\nLine {i} [CHECK: check this] holds a fact." for i in range(4)) + "\n"
        three = CLEAN_BRIDGE + "\n".join(f"\nLine {i} [CHECK: check this] holds a fact." for i in range(3)) + "\n"
        self.assertIn("assert-or-cut", fails(four))
        self.assertNotIn("assert-or-cut", rules(three))

    def test_antithesis_density(self):
        one = CLEAN_BRIDGE + "\nIt is not a domestic problem but a foreign-policy one.\n"
        three = one + "\nThe fix is not a statute but a treaty.\n\nThe risk is not the court but the ministry.\n"
        self.assertNotIn("not-x-but-y", rules(one))
        self.assertIn("not-x-but-y", fails(three))

    def test_antithesis_ignores_clause_after_but(self):
        doc = CLEAN_BRIDGE + "\nI am not sure, but we should ask. He is not here, but they know. It was not ready, but I sent it.\n"
        self.assertNotIn("not-x-but-y", rules(doc))

    def test_time_estimate_only_when_addressed_to_owner(self):
        est = CLEAN_BRIDGE + "\nThe rebuild will take about 15 minutes and then I ship.\n"
        self.assertIn("time-estimate", fails(est, to_owner=True))
        self.assertNotIn("time-estimate", rules(est))
        calendar = CLEAN_BRIDGE + "\nWe are hoping to get 30 minutes on Ben's calendar this Tuesday.\n"
        self.assertNotIn("time-estimate", rules(calendar, to_owner=True))

    def test_hedge_stack(self):
        stacked = CLEAN_BRIDGE + "\nThis could perhaps possibly seem likely to work in some cases.\n"
        self.assertIn("hedge-stack", fails(stacked))
        two = CLEAN_BRIDGE + "\nThis could work, and it is likely to hold.\n"
        self.assertNotIn("hedge-stack", rules(two))

    def test_length_budget_reads_the_genre_file(self):
        long_doc = " ".join(["word"] * 120) + ".\n"
        short_doc = " ".join(["word"] * 60) + ".\n"
        self.assertIn("length-budget", fails(long_doc, genre="follow-up-bump"))
        self.assertNotIn("length-budget", rules(short_doc, genre="follow-up-bump"))
        self.assertNotIn("length-budget", rules(long_doc))

    def test_bold_leadins_are_a_genre_setting(self):
        doc = CLEAN_BRIDGE + "\n- **Reader:** one person with one job.\n- **Purpose:** one sentence.\n"
        self.assertIn("bold-leadin", fails(doc, genre="cold-email"))
        self.assertNotIn("bold-leadin", rules(doc, genre="one-pager"))
        self.assertNotIn("bold-leadin", rules(doc))

    def test_bullet_length_is_a_genre_setting(self):
        long_bullet = CLEAN_BRIDGE + "\n- **Regulatory reciprocity.** " + " ".join(["word"] * 50) + ".\n"
        self.assertIn("bullet-as-paragraph", fails(long_bullet))
        self.assertNotIn("bullet-as-paragraph", rules(long_bullet, genre="one-pager"))

    def test_density_scales_with_length(self):
        two = CLEAN_BRIDGE + "\nThe crucial point is crucial to the case.\n"
        self.assertIn("crucial", fails(two))
        one = CLEAN_BRIDGE + "\nThe crucial point is the case.\n"
        self.assertNotIn("crucial", fails(one))
        self.assertIn("crucial", rules(one))

    def test_internal_mode_relaxes_curly_quotes_and_meta(self):
        doc = CLEAN_BRIDGE + "\nHe said “fine” and, as noted above, left.\n"
        self.assertIn("curly-quote", fails(doc))
        self.assertIn("meta-doc-nav", fails(doc))
        self.assertNotIn("curly-quote", fails(doc, internal=True))
        self.assertNotIn("meta-doc-nav", fails(doc, internal=True))
        self.assertIn("curly-quote", rules(doc, internal=True))

    def test_internal_mode_relaxes_candor_density(self):
        doc = CLEAN_BRIDGE + "\nThe honest answer is that the honest number is lower.\n"
        self.assertIn("candor-tic-honest", fails(doc))
        self.assertNotIn("candor-tic-honest", fails(doc, internal=True))
        self.assertIn("candor-tic-honest", rules(doc, internal=True))

    def test_unknown_genre_is_an_error(self):
        with self.assertRaises(SystemExit):
            lint.scan_text(CLEAN_BRIDGE, genre="no-such-genre")


if __name__ == "__main__":
    unittest.main()
