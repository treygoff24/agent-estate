---
genre: readme
words: 2500
bold_leads: off
bullet_words: 40
review: cold-read
---

# README for a software project (CLI, library, tool)

This file governs structure; voice and the check step stay with the rest of this skill.

**Reader.** A scanner deciding in under a minute whether this solves their problem, then a user coming back for one command. Lead with value, prove it with examples, document with precision. Most READMEs fail by burying the value under installation, explaining what the tool *is* instead of what problem it *solves*, or making claims with no example.

**Spine.** Explainer, in this order:

```
1. HERO (above the fold)
   logo/illustration · badges (CI, license, version) · one-line description · quick install
2. TL;DR (sell the value)
   The Problem (the pain) · The Solution (what this does) · Why use it (feature table)
3. QUICK EXAMPLE (prove it works)
   5–10 commands showing the core workflow in action
4. REFERENCE
   design philosophy · comparison vs alternatives · installation (multiple paths) ·
   quick start · command reference · configuration · architecture
5. SUPPORT
   troubleshooting · limitations · FAQ · license
```

**Rules.**

| Rule | Why |
|------|-----|
| Lead with value, not installation | TL;DR before Quick Start; installation buries the pitch |
| An escape-hatch install above the fold | impatient readers want one line to try it |
| Every feature claim has an example | abstract claims do not sell |
| Comparison tables over prose | scannable beats readable for "vs alternatives" |
| A limitations section | builds trust, saves support time |
| Multiple install paths | one-liner, package manager, from source |
| Architecture diagram for complex tools | ASCII survives copy-paste |
| Troubleshooting is mandatory | the top five errors with fixes deflect support load |

**Contributions.** If the project takes outside contributions, link a `CONTRIBUTING.md`. If it does not, a short note in the project's own voice is fine; never paste a boilerplate policy.

**Pre-publish checklist.** Hero with one-line description and quick install; TL;DR with Problem/Solution/feature table; quick example (5–10 commands); at least three install methods; every command has a usage example; comparison against at least two alternatives; architecture diagram for complex tools; troubleshooting; limitations; FAQ; license; every code block copy-paste ready; no broken links or badges; consistent terminology.

**Cut.** Installation-first openings; "This is a tool that…" (say "Solves X by doing Y"); screenshot-heavy sections (they break and do not copy-paste; use ASCII and code blocks); hidden limitations; a single install method; outdated badges that make the project look abandoned. **Neighbours:** A full open-source launch (name check, cover art, AGENTS.md contract, release pipeline) is `oss-launch`; a docs site is a separate project.
