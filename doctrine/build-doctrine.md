# Build doctrine

How to run a multi-agent build: one **coordinator** (the session talking to the user) launches
**lanes** (subagents, delegated runs, child sessions), each in its own git worktree on its own
branch. The user's instruction for a specific job overrides anything here.

**Summary.** Give fewer agents richer briefs, grouping related work so each lane learns across
its cluster; run independent clusters in parallel. Prepare vision, acceptance, owned files and
checks before launch. Builders use a capable mid-tier model; researchers the same at high
effort; reviewers come from a different model family than the builder. Review once, send
findings to a fresh fix run on the lane's branch after syncing integration, then verify each
disposition; review again only if the design changed. Land lanes as they pass. Lanes run
targeted tests; the coordinator runs the project gate once on the integrated candidate. Finish
slices through cleanup, performance and product acceptance, compared at the product boundary
with evidence at an exact revision. Put heavy work on a machine with the capacity and respect
its limits. Resume only authorized work; blocked decisions reach their owner. Human gates stay
human.

## Fan-out

Fewer agents with richer briefs beat many agents with thin ones. Group related work into one
lane and one worktree so builds stay warm and what the agent learns carries across the cluster.
Run independent clusters in parallel. Give a shared registry (an index, a manifest, a lockfile)
one owner so lanes do not collide on it. Choose width by the work, not by a target number of
agents, and count what a wider fan-out costs (tokens, rework, integration conflicts) against
what it saves.

## Lane briefs

A lane starts fresh, so its brief is its whole world. Missing briefs are the coordinator's
work. Prepare, before launch:

- **Vision**, once, in the user's words where possible, at the head of every brief. Use these
  six labels: *What we are building*; *Why* (the failure or opportunity it answers); *For
  whom*; *What must be true when it is done*; *What exists that this replaces or extends*;
  *Stack* (and why, if it deviates from the house stack).
- **Acceptance** for the lane (see **Reference and check** below), the **files it owns** (a
  write and serialization declaration, not a dependency edge), the **checks** it runs, and the
  report shape you want back.
- Real data dependencies between lanes, not arbitrary phases. Overlapping writes need
  isolation (separate worktrees) or serialized integration.

Pick the model per role: builders a capable mid-tier model, researchers the same at high
effort, reviewers a different family from the builder. A job-specific instruction replaces
these defaults. Respect confidentiality when choosing where work is routed.

## Review and integration

One cross-family review. Then one fresh fix run on the lane's branch, after merging the
integration branch into it. Then the coordinator checks each disposition against the artifact;
a report alone is not evidence. Review again only when a fix changes the design. Land a passing
lane immediately so later lanes build on it. The coordinator verifies the integrated
candidate itself.

Every acceptance concern needs one of: fix evidence, a waiver from someone authorized to waive
it, or an open blocking item that retains the reviewer's words. A failure that remains needs a
decision, not an unbounded fix loop. High stakes alone do not authorize more review rounds.

## Reference and check

A **reference** is what the deliverable is compared against (the existing implementation, an
approved screen, a specification, a walkthrough, named by path and revision). A **check** does
the comparing. Every acceptance criterion names five things:

| Field | Content |
|---|---|
| Reference | Existing implementation, approved screen, spec or walkthrough, by path and revision |
| Boundary | The running product driven by real inputs; that is where the comparison is made |
| Context | The data, states, sizes and timing that make the comparison meaningful |
| Check | A runnable command, or a named reviewer with a named instrument |
| Evidence | Artifacts to retain at the accepted revision |

An internal module fed pre-shaped fixture data is not the product boundary. Unit checks remain
useful lane diagnostics; they cannot substitute for driving the product. A check that did not
run is unverified. Name who may waive each criterion, and record every waiver with who, why and
the authorization source; count waivers separately from passes.

For a port or redesign, name the layers you compare (data, stills, dynamics) each with its own
reference and check. Build the **state inventory from real use** (real session logs, every
branch of the view code), not from the reference's own fixture list. Review the **instrument
as code**: the acceptance reviewer reads the comparison harness's diff as well as the product's.
Every transform applied to a reference is a named, approved difference, never a silent rewrite
in the harness. A detector must fail on the defect it claims to catch; an empty match set or a
clean exit alone proves nothing.

## Finishing passes

A slice is an independently acceptable outcome: a command, a journey, a screen region. Before
planning or closing one, name its finishing chain: **cleanup** (remove scaffolding, dead
code and stale docs the work created), **performance** (measure the thing that matters; do not
assume), and **product acceptance** (a reviewer other than the builder drives the real product
against the criteria above and cites evidence at the accepted revision). Put the user's own first
look in the *first* slice, not at the end: their words after seeing it, never an agent's pass
substituted for them. Closure cannot outrun that look.

## Capacity and placement

Heavy fan-out (many compiles, large test runs, benchmarks) runs from a coordinator on a machine
with the capacity, typically the Linux box, not the user's interactive laptop. Honor the
machine's compile slots, child-agent cap and any test-load guard. Ready work is not
necessarily eligible work. Drain compiles and pause heavy launches before taking a performance
baseline. Record quota, memory, compile contention and human waits as distinct causes of delay.

## Lane tests

Lanes run named test files for the code they changed and its immediate neighbours, through the
test-load guard (`testrun`) where installed, with worker caps. Never a whole directory or suite.
The coordinator owns the full suite and the project gate, run **once on the integrated
candidate**. Rerun affected checks when an input changes. Expand checks for failures or a
specific unresolved risk, not to accumulate green runs.

**Red-proof each new test:** break the behavior it guards, watch it fail, restore, and show
green. One mutation per new test is the bar. Prose and read-only work get source and artifact
checks, not pretend tests.

## Wakes and recovery

Continue authorized, ready work when capacity and the gate permit. Persist a wake for a
reported rate-limit reset time; invent none. At resume, wake or recovery, reconcile what each
tracker item claims against the children actually running before relaunching anything. Preserve
pauses and stops; restore only the eligible incarnation, under open scope. Record failed
launches. A blocked declaration requires a decision, and a judge cannot overrule it. Three
identical failure signatures or two failed launches also require a decision. Continue
independent authorized work while waiting. Quiet runs and clean exits are not acceptance.

Label every blocked decision `needs-decision`; add `needs-user` when only the user can decide,
so it surfaces on their own list.

## Human gates

Only the user opens a build gate, through their launch instruction. The scope is the plan at a
named revision; implied finishing work and review blockers proceed without re-asking. A new
slice, or a change to a must-be-true outcome, needs the user's decision. Deploys, cutover,
spend, external sends and pushes to public remotes keep their own gates. Authorized lane tokens
are not gated spend: show usage, do not invent caps. Privacy, destructive-action controls and
unrelated work stay outside build authority.
