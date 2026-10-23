---
name: review-until-dry
description: Use when the owner explicitly asks for an extended, repeated adversarial review of code or artifacts, looped until independent reviewers find nothing more. Ordinary one-pass review uses code-review instead.
---

# Review until dry

This loop costs real time and tokens, so run it only when the owner has asked for
extended review. Before the first round, record the scope, a round cap and a
stopping criterion; without them, do an ordinary single review pass instead
(`code-review`). The mechanics below apply only inside that authorized regime.

## The core principle: coverage, not redundancy

Two decorrelated reviewers on an identical brief are not a reliability vote:
they see different things. Empirical scorecard from the run that proved this
(a 16-round proving run): twice one reviewer declared dry while the other found the
real residual defect; once each found a SEV-2 the other missed entirely; they
converged on dry only at the true end. **Never AND the verdicts mechanically
and never stop on one reviewer's "dry."** Dry means: both dry, same round, on
briefs covering the full current diff.

## Reviewer roster

Pair two reviewers from *different model families* (for example one Claude and
one Codex/GPT), each at the highest reasoning setting your harness offers. Two
sessions of the same model, or the same model behind two transports, are not
independent opinions. Check your project's confidentiality rules first: if the
code is under privilege, customer-data, or zero-retention terms, exclude any model
you may not send it to. The generic rule is the best available models, filtered
by policy, decorrelated by vendor.

How you launch a reviewer depends on your harness: a Claude Code subagent for the
Claude side, `codex exec` (read-only sandbox) for the Codex side, or any agent
runner you have wired up.

## The loop

### 1. Brief construction

One shared brief per round, given verbatim to both reviewers. It contains:
- exact scope as a commit range (`<base>..HEAD`), never "recent changes"
- the claims under attack (what the fixed code now asserts about itself)
- explicit instruction to try to *refute*, with severity definitions
  (SEV-2 = reachable defect in a delivered artifact or invariant; SEV-3 =
  recorded residual)
- required report format, findings ranked, file:line anchors mandatory
- a matter/scope hygiene scan if the project needs one

Write briefs to files and launch with `--prompt-file`. Archive every brief
alongside its reports. The same-brief pairing is itself a claim someone may
audit later, and the briefs are the evidence.

### 2. Launch

Run the two reviewers in parallel as separate background processes, each with the
brief from a file, each writing its report to its own file. Do not chain a launch
in the foreground behind a wait: killing the watcher kills the reviewer with it.

### 3. Verify before adopt: the non-negotiable step

The coordinator reads the actual code for **every** finding before it becomes
fix work. Frontier reviewers hallucinate: in the proving run one reviewer fabricated
file paths in three separate rounds. A finding is adopted only when the
coordinator has independently confirmed the defect exists at the cited site
and the failure scenario is reachable. Unverifiable finding → recorded as
rejected in the triage doc with the reason, never silently dropped.

When the reviewers split (one dry, one not): adjudicate on the code, not on
track record. In the proving run the minority reviewer was right both times.

### 4. Triage doc

One per round, archived: verdicts, adopted findings with severity, rejected
findings with reasons, coordinator rulings on disputes, and the running
SEV-3 residual list (recorded-not-fixed items stay visible round over round).

### 5. Fix waves

- **Falsifying test first.** Each fix lane writes the test that fails against
  current code before fixing, in the same lane.
- Isolated worktrees per lane (a git worktree each, or your harness's worktree isolation); disjoint file ownership across lanes; entangled
  findings go to ONE lane.
- Brief every lane: never run `git stash`/`checkout --`/`restore` or any
  tree-wide git state command (a shared-tree stash has destroyed sibling
  lanes' work before).
- Run the project's own checks before landing. Inspect trailing call-site updates and polish as well
  as the central fix; the lane's completion report is not proof they landed.

### 6. Re-review

Use the authorized stopping criterion and cap recorded at entry. If another
paired round is authorized, name its new commit range and use the same brief
discipline. An unresolved criterion at the cap goes to the owner for a decision, not another automatic review.

### 7. Close-out

Fresh acceptance/fingerprint run if the project has one; archive the final
triage as the closing summary with the finding trajectory across rounds and
the standing residual list; update the project handoff.

## Cost honesty

The proving run took 16 rounds and 8 fix waves. That is evidence
about that run, not a floor or a standing permission. Report tokens, findings
and rework against accepted outcomes, and distinguish the independent review
from the coordinator's own verification.
