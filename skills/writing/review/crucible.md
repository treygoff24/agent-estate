# Crucible (decorrelated review loop for a bet-the-outcome artifact)

You wrote or hold a high-stakes written artifact: a position paper, a design-rationale memorandum, a contract, a plan someone will bet real work on. Crucible subjects it to independent adversarial reviews from different model families, converges the findings, and patches with your judgment, looping until a round yields only nits. The gain is decorrelated error: a Codex lane, a native Claude lane, and a third family each catch holes the others miss. You are author and integrator: reviewers advise, you decide.

Size it to the stakes: a modest artifact gets two lanes (native plus Codex), one pass; a bet-the-outcome artifact gets three lanes with a third family and loops until clean. A throwaway note or a one-paragraph reply never runs here. For a plan stress-tested by live Q&A with the owner, use `grilling`.

## The loop

1. **Frame.** Pin the artifact path, the companion documents it must stay consistent with, the locked decisions, and the one highest-value check (usually "the artifact cites real sources; read each and flag every citation that is wrong or stale").
2. **Fan out blind and parallel.** Every lane gets the same baseline brief and its own primary lens; no lane sees another's findings. Launch all lanes from one message. Use the best reasoning setting each family offers: for example a Claude subagent, a Codex read-only session (`codex exec`), and a third family if you have one as the decorrelated seat.
3. **Converge.** Ground-truth every finding against the cited source before acting; reviewers cite stale lines and sometimes invent a problem. Two independent lanes flagging the same thing is high confidence: fix it. A lone flag is adjudicated on the merits and, if rejected, gets one line saying why.
4. **Patch** with `revision.md` (patch before rewrite; reframe before cut). Re-verify the highest-stakes fixes with a second engine when they touch load-bearing claims.
5. **Loop or ship.** A round with no blockers and no risks, only nits, is converged. On a later round tell the lanes what was already reviewed and patched and point them at what the prior round missed and whether the patches introduced new problems.

## Briefing a lane

```
READ-ONLY review. The author wants the holes found; be adversarial and specific.

ARTIFACT: <path>. Consistency targets: <companion paths>.
BRIEF: <the step-1 brief: reader, purpose, genre, spine, hard constraints>.
GROUND TRUTH: <the record the piece rests on; facts the owner asserted listed here are settled>.

CONTEXT (do not relitigate, do not flag as wrong): locked decisions <…>; intentional idioms <…>; scope boundary <in / out>.

HIGHEST-VALUE CHECK: <the one thing>.
YOUR PRIMARY LENS (weight this; still cover the rest): <lens>.
[LATER ROUNDS] Already reviewed and patched: <summary>. Focus on what that missed and whether the patches introduced new problems.

OUTPUT: BLOCKERS / RISKS / NITS, each with a file:line or § anchor and a concrete fix. Do not inflate severity; do not pad with praise. Cite the source for any "this is wrong" claim.
```

Give the lane the brief and the record, and withhold your defense of the design; arguing for it anchors the reviewer toward agreeing. A read-only reviewer sees a copy with no gitignored files: materialize any diff or context doc as an untracked, non-ignored file inside the tree and read it back before launch.

## Where it goes wrong

Three reviewers from one family (redundancy, not coverage). Showing one lane another's findings. Applying a finding without ground-truthing it. Letting a lane's "looks good" stand in for your judgment. Reviewing past nits-only.
