# Readers (cold structural reads and reception panels)

One procedure with two modes. **Structural** mode answers "is this sound to a smart stranger?" with one to three personas and a score-and-triage output. **Reception** mode answers "will the specific people whose reaction decides this piece's fate receive it the way I need?" with a small panel of seats chosen by failure mode.

Both modes read cold. Give each reader only its persona block and the file path: no project context, no intent, no rationale for choices in the draft. Every piece of context you leak makes the reader start defending choices it has been told the reason for; the real reader will have none of that.

## The ground-truth exception (record-derived artifacts)

Minimal context governs persona reads. It does not govern a factual-consistency review of an artifact derived from a canonical record (sworn testimony, a filed statute, an executed contract, a published spec, the owner's asserted facts). A cold reviewer without the record flags the artifact's most-vetted language as "unsupported" or "too absolute", and the false positives outnumber the real findings (in practice, most findings from a record-blind review of a quotation-heavy document were verbatim phrases from the filed record; a reviewer given the record as declared ground truth returned fewer findings, all real). So run the two reviews as separate passes with opposite context rules: persona read cold; consistency read with the ground-truth document named and readable and the standard defined as consistency with the record. When triaging any record-blind review, check each flag against the record before acting; expect the strongest language to be the most flagged. Reviewers handed a rule list return rule violations; hand them the brief and the record.

## Structural mode

1. Name the audience the piece is actually trying to reach and pick the most sophisticated likely reader in it, not the friendliest. Write a persona block of four to six sentences: their job, what they already know, what they distrust, what they are reading this for. Starter personas: **the skeptical specialist** (knows the field better than the author, allergic to overclaiming); **the hurried executive** (reads the first paragraph and the last, forwards or doesn't); **the hostile reader** (looking for the line to quote against you); **the smart outsider** (no jargon, no context, good faith).
2. Spawn one fresh subagent per persona in a single message (one-shot general-purpose), with this prompt, substituting only the persona block and the path:

```
You are reading a piece of writing as a specific reader. Persona:

[persona block]

Read the piece at: [absolute path]

Read it once, all the way through, as that reader would. Do not skim. Do not look up unfamiliar terms or names; if the piece does not explain something this reader would not already know, that is a finding.

Return:
1. Score (0-100): the probability you would forward this to a colleague whose time you respect. 50 is "read to the end out of courtesy, would not forward"; 80+ is "would forward with a one-line endorsement"; 90+ is rare.
2. Forward verdict, one sentence: would you forward, to whom.
3. The line that carries the piece, quoted verbatim, or "none" (itself a finding).
4. The tell: the single paragraph or move that most undermines credibility for this reader, quoted, with why.
5. Three to five structural calls: specific and locatable ("the prescriptive section restates the diagnostic section in a different voice"), each with the move that fixes it.
6. Evidence and argument gaps this reader would push on, and what would close each.

Be direct. Do not soften, hedge, or praise to balance critique.
```

3. Slate for a heavy piece: at most three personas that catch different failures. Three generalists waste the pass; readers whose priors conflict outright surface the real tradeoffs.
4. Triage: read everything once before patching. Find the single highest-leverage call (usually the tell), fix it, re-read; other calls often dissolve. Then remaining structural calls in priority order, stopping at nitpicks. Convergent calls across readers come first; a persona-specific call is real for that persona and gets judged against the actual audience.
5. Show the owner: scores and verdicts, the carrying line, the tell verbatim, a three-to-five item fix list, and whether to patch now or restructure first. Never the full transcript.

## Reception mode

Selecting the panel is the skill. Up to four seats, chosen by failure mode:

1. **The primary gate**: the reader whose buy-in the piece most needs, primed defensive. The person whose program it critiques, the ally it cannot afford to alienate. If the reader most inclined to take offense comes away feeling respected, the piece works.
2. **The domain scholar**: allergic to overclaiming and strawmen; catches the rhetorically vivid, analytically false claim and the rebuttal not steelmanned at full strength.
3. **The ally you cannot afford to arm**: nominally on your side, whose enthusiasm could turn a line into ammunition against the goal.
4. **The gatekeeper**: the editor or maintainer at the target venue; tests the open, the length, the glossing, and whether anything reads as a covert advertisement.

Build each seat from a real person's public record when you have one. Swap roles to the piece: a board memo seats the skeptical investor as gate; a coalition letter seats the partner most likely to feel sidelined. The constant: the reader you most need and most risk losing sits as the primary gate, primed defensive.

Spawn all seats in one batch, one-shot agents, draft path only. Each answers in character: gut reaction (attack or ally?); the lines that landed and the lines that stung, quoted; champion or weaponize (forward with endorsement, screenshot as hostile, cite, bury; to whom); the single change that flips you; and, for the gate, whether the posture reads as sincere or as a maneuver.

Synthesize: convergence across two seats is a ship-stopper; the primary gate's flip is near-mandatory; the others are judgment. Then write a clean V2 that references none of the process and reads as a fresh piece by an outside author, run through `voice.md` and lint, with the prior version preserved (copy before overwrite). When stakes justify it, re-run the gate and the scholar on V2.

Scale: a low-stakes piece gets the gate and one failure-mode reader, no re-test; a flagship piece gets all four and a V2 re-run of the gate.
