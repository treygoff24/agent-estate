---
name: receiving-code-review
description: >-
  Act on review feedback that has arrived on your work: a reviewer's or teammate's report, PR comments, a subagent's review findings, "fix these review items". Verify each finding against the code, then accept, push back, or implement it one at a time. Not for doing a review of a diff yourself (code-review).
---

# Receiving Code Review

Code review is a technical evaluation, not a social performance. Verify before implementing. Ask before assuming. Technical correctness over comfort.

## The response pattern

When feedback arrives:

1. **Read** the whole thing before reacting.
2. **Understand** — restate each requirement in your own words, or ask.
3. **Verify** — check it against what the codebase actually does.
4. **Evaluate** — is it sound for *this* codebase, on this stack, for these constraints?
5. **Respond** — technical acknowledgment or reasoned pushback.
6. **Implement** — one item at a time, testing each.

## Don't perform agreement

Skip "You're absolutely right," "Great point," "Excellent feedback," and any reflexive thanks. They add nothing and they often precede implementing something you haven't verified. Instead: restate the requirement, ask a clarifying question, push back with reasoning, or just do the work and let the diff speak.

When the feedback is correct, the acknowledgment is the fix itself:

- "Fixed — [what changed]."
- "Good catch on [specific issue]. Fixed in [location]."

Not: "Thanks for catching that!" / "You're right!" The code shows you heard it.

## Unclear feedback: don't guess

If an item is unclear, ask about it; do not invent a reading. Items are often related, so first check whether the unclear one changes how you would implement the clear ones. If it does, ask before implementing the related items. If the clear items are independent of it, do them now and ask about the rest in the same message (the operating contract: finish independent authorized work first, ask only when the answers change the work).

```
Feedback: "Fix items 1-6"
You understand 1,2,3,6 but not 4,5.

Items 4,5 touch the same module as 2: ask about 4,5 first, then do 1-6 together.
Items 4,5 are independent of the rest: do 1,2,3,6, and in the reply say "Need clarification on 4 and 5."
Never: implement 4 and 5 on a guess.
```

## Source matters

**From the project owner or your collaborator** — trusted. Implement after you understand it. Still ask if scope is unclear. Skip the performative agreement; go straight to action or a one-line technical acknowledgment.

**From external reviewers** — suggestions to evaluate, not orders to follow. Before implementing, check:

1. Is this correct for *this* codebase?
2. Does it break existing functionality?
3. Is there a reason the current implementation is the way it is?
4. Does it hold across all platforms/versions you target?
5. Does the reviewer have full context?

If it seems wrong, push back with technical reasoning. If you can't verify it, say so: "I can't verify this without [X]. Should I investigate, ask, or proceed?" If it conflicts with a prior decision by the project owner, stop and surface that conflict before acting.

## YAGNI check on "do it properly" feedback

When a reviewer asks you to "implement this properly" (full metrics, date filters, CSV export, etc.), grep for actual usage first.

- Unused: "Nothing calls this endpoint. Remove it (YAGNI), or is there usage I'm missing?"
- Used: then implement it properly.

You and the reviewer both serve the same goal. If the feature isn't needed, the right move is to cut it, not to gold-plate it.

## Implementation order

For multi-item feedback:

1. Clarify anything unclear first.
2. Blocking issues (breaks, security).
3. Simple fixes (typos, imports).
4. Complex fixes (refactors, logic).
5. Test each fix individually; verify no regressions.

## When to push back

Push back when the suggestion breaks existing functionality, the reviewer lacks context, it violates YAGNI, it's wrong for this stack, legacy/compatibility reasons exist, or it conflicts with an established architectural decision.

How: technical reasoning, not defensiveness. Ask specific questions. Point to the working tests or code. Escalate to the project owner if the disagreement is architectural.

## If your pushback was wrong

State the correction and move on. No long apology, no defending why you pushed back.

- "You were right — I checked [X] and it does [Y]. Implementing now."
- "Verified, you're correct. My initial read was wrong because [reason]. Fixing."

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State the requirement or just act |
| Blind implementation | Verify against the codebase first |
| Batch without testing | One at a time, test each |
| Assuming the reviewer is right | Check whether it breaks things |
| Avoiding pushback | Technical correctness over comfort |
| Partial implementation | Clarify all items first |
| Can't verify, proceed anyway | State the limitation, ask for direction |

## Examples

**Performative (bad):**
```
Reviewer: "Remove legacy code"
"You're absolutely right! Let me remove that..."
```

**Verified (good):**
```
Reviewer: "Remove legacy code"
"Checking — build target is 10.15+, this API needs 13+. Legacy path is required for
backward compat. The current impl does have the wrong bundle ID though; fix that, or
drop pre-13 support?"
```

**YAGNI (good):**
```
Reviewer: "Add proper metrics tracking with database, date filters, CSV export"
"Grepped the codebase — nothing calls this endpoint. Remove it (YAGNI)? Or is there
usage I'm missing?"
```

## Bottom line

External feedback is suggestions to evaluate, not orders to follow. Verify. Question. Then implement. No performative agreement, technical rigor always.

## Output

When you finish triaging, report:

- Clarifications needed
- Items accepted, with the verification note for each
- Items rejected, with the reasoning
- Implementation order and test plan
