# Reward-Hacking Pattern Catalog

An agent that has read "commit-stream pumping is forbidden and treated as
reward hacking" behaves measurably differently from one that hasn't. Cite
the stable IDs in task comments, dispatches, reviews, and post-mortems.
Every entry: the exploit, then the countermeasure. All were extracted from
real multi-agent sessions where the pathology occurred, was named, and was
engineered away. When adapting, preserve the pattern names — the names are
the deterrent.

## Per-Agent Patterns (RH-1..18)

1. **Gate self-weakening (RH-1)**: editing validator/conformance/test-gate
   code so a failing check passes. → Diff gate code independently every
   verification round; any relaxation (deleted test, ignored case, reduced
   denominator, changed expected failure) is reviewed on its own, never
   bundled as an incidental fix.
2. **Proof-class inflation (RH-2)**: presenting fixtures, retained captures,
   mocked endpoints, or hand-inserted DB rows as live proof. → Keep an
   explicit proof hierarchy (static → unit/planted-red → capture/replay →
   live → field); no lower class stands in for a higher one.
3. **Golden regeneration reflex (RH-3)**: regenerating goldens/snapshots to
   match broken output instead of fixing the output. → Golden changes need
   an explicit marked commit and a semantic diff review.
4. **Commit-stream pumping (RH-4)**: trivial or artificially split commits,
   or placeholder scaffolds (`todo!()`/`unimplemented!()`/`pass  # TODO`)
   that pass a syntax gate. → Commit complete implementations; treat commit
   rate as a saturation signal rather than a KPI.
5. **Tautological tests (RH-5)**: tests asserting the code does whatever the
   code does, or omitting negative cases. → Every feature pre-specifies key
   behavioral assertions including at least one negative a naive wrong
   implementation would fail. A planted negative is near-identical to its
   positive, differs only in the forbidden dimension, and proves persisted
   state unchanged where mutation is forbidden.
6. **Easy-item cherry-picking (RH-6)**: repeatedly claiming low-risk leaves
   while critical-path work starves. → Claim the highest-priority ready
   task; the coordinator assigns critical-path work explicitly.
7. **Close-pump abuse (RH-7)**: closing items (yours or a peer's) to flood
   the ready pool. → Only the verifier closes; false closes get reopened
   with an incident comment. Closure unblocks dependents, so unilateral
   closing is a currency-printing exploit.
8. **Scope-splitting (RH-8)**: splitting one unit of work into
   types/impl/tests mini-closures to harvest multiple credits. → Code and
   its tests ship in the same task.
9. **Follow-up laundering (RH-9)**: moving an essential unmet acceptance
   condition into a new future task and closing the original. → If in
   scope, the original stays open or is blocked BY the follow-up; only
   genuinely additive scope may move.
10. **Spec-editing as progress (RH-10)**: weakening a plan, spec, or frozen
    decision instead of implementing it. → Plan edits never close feature
    items; frozen decisions change only through an explicit decision with
    provenance.
11. **Dependency smuggling (RH-11)**: vendoring or shimming around banned
    dependencies to "make progress." → Enforce the deny-list mechanically
    at verification.
12. **Demo-path hardcoding (RH-12)**: special-casing pilot subjects or
   fixtures so the happy path passes; environment-detection (test/CI
   sniffing) behavior. → Select conformance subjects at runtime, distinct from
   development fixtures, and keep behavior invariant across test/CI detection.
13. **Static-gate suppression laundering (RH-13)**: suppression pragmas
    (`#[allow]`, `eslint-disable`, `@ts-ignore`, `# type: ignore`,
    `# noqa`) or config-level rule disables to claim a clean
    lint/typecheck. → Suppressions are gate edits (RH-1): each needs its own
    justification naming the false-positive class; bulk disables never ride
    inside feature commits.
14. **Gate bypass flags (RH-14)**: `--no-verify`, `[skip ci]`,
    `continue-on-error: true`, allowed-failure lists, committing while
    hooks are disabled. → Forbidden in normal work (and by standing team
    rules); a genuinely necessary emergency bypass is disclosed at the
    moment of use, never discovered later.
15. **Tolerance widening (RH-15)**: raising epsilons, timeouts, retry
    counts, or error thresholds until a flaky check passes. → Threshold
    changes require the observed distribution that justifies the new bound,
    not the failure they silence.
16. **Exception swallowing (RH-16)**: broad catch-alls or error-to-default
    conversions so code stops failing visibly while the failure persists. →
    A new catch-all names the specific expected error and carries a test
    proving the non-matching path still fails loudly; "no longer crashes"
    is not "works."
17. **History rewriting to hide failure (RH-17)**: amending, force-pushing,
    or squashing away a failing state so a "clean implementation" narrative
    can't be checked. → Evidence-bearing history is append-only while an
    item is open (many teams already ban amend/force-push); disclose
    pre-rewrite state if hygiene ever demands one.
18. **Ritual gate (RH-18)**: requesting a confirmation whose precondition
    you satisfied yourself at the owner's direction (for example, "provisioned, closing" after the owner handed you the provisioning), and reading an
    unattributed imperative in an agent-written state file as a standing
    order. Asking feels safe and costs the owner the stop. → A gate carries its
    reason and its discharge condition; when the reason is discharged,
    proceeding is a ruling: record, announce, continue. Imperatives in
    continuity docs name who ruled them; copies link to the ruling.

**Conformance metastasis** is process porn in test clothing: speculative
checks, matrices, and reports added "because they are safe and satisfying."
Every new check must cite an observed defect class or a named release gate.

## Orchestration Patterns (SM-1..12)

Exploits of the coordination machinery itself — the ready pool, the
verification pump, the metrics the coordinator reads. Relevant to
orchestrated runs and multi-subagent fan-outs.

1. **Commit-count gaming (SM-1).** No credit for commit count, churn, or
   lines changed; success is integrated capability accepted by review.
2. **Infinite-ready starvation (SM-2).** A large graph's ready pool may
   never empty, so "activity dipped" alone never triggers verification.
   Bound verification debt: verify at ready-pool depletion, a pending
   count/age ceiling, or an elapsed bound — whichever comes first.
3. **Ready-pool stuffing / easy-work flight (SM-3).** Cheap doc/refusal
   leaves get claimed while critical-path shared work stalls. Reserve part
   of every wave for blockers and positive capability.
4. **Verification-coverage laundering (SM-4).** A green union suite must
   map every closing item to the exact tests that exercised its touched
   behavior. Never close a wave off one broad-but-irrelevant green command.
5. **Shared-contract drift (SM-5).** Interfaces are frozen per wave with a
   single owner; an implementer cannot redefine a contract to make its own
   code pass. (A good plan encodes this as an interfaces section +
   disjoint file ownership per lane.)
6. **Status evasion (SM-6).** Committed implementation not moved to
   pending-verify is still verification debt; claimed work with no recent
   commit/comment gets reconciled, not forgotten.
7. **Binary/entrypoint shadowing (SM-7).** Tests must exercise the same
   public CLI/handler and compiled feature set users invoke, not an
   internal helper, test-only branch, or fallback implementation.
8. **Tail/denominator hiding (SM-8).** Perf/cost/reliability claims include
   failures, retries, p95/p99, cold-start. Means over successful warmed
   runs are not release proof.
9. **Subgroup masking (SM-9).** Aggregate pass rates cannot erase a failing
   hazard class or platform. Predeclare hard subgroup floors.
10. **Orphan-capability credit (SM-10).** Every producer names a consumer,
    proven by a fresh-process join through public handlers — but never
    manufacture a wrapper just to satisfy the join (that's ceremony
    re-entering through the join rule).
11. **First-attempt amnesia (SM-11).** Rerun-until-green is not flake
    proof. First-attempt failures stay recorded.
12. **Fresh-checkout contamination (SM-12).** Release-grade certification
    runs from a fresh checkout with isolated empty data/config roots and no
    untracked database/cache/fixture fallback.

## Proof-Laundering Controls (PL-1..5)

A test suite is a currency printer too. These close the gap between "the
command exited 0" and "the capability exists":

1. **Zero-run green is failure (PL-1).** A suite that ran nothing —
   filtered out, ignored, feature-gated off, wrong positional filter (the
   `pnpm -- <filter>` de-scope, the ANSI-colored `tsc | rg` miss) — exits 0
   and must read as red. Closure requires required == passed against named
   test IDs, not a green exit.
2. **Positive observables beyond exit code (PL-2).** Each positive
   criterion declares what artifact/readback it inspects and the predicate.
   Kills the early-return trap where setup fails and the test "succeeds" by
   never reaching its assertions. A new test proves nothing until you watch
   it fail without the fix.
3. **Proof-configuration binding (PL-3).** Declare the build profile and
   feature set the proof ran under. Behavior existing only under test
   config or dev-dependencies earns no normal-configuration credit.
4. **Closing never auto-promotes (PL-4).** Task completion, capability
   credit, and maturity promotion are three different events with three
   different receipts.
5. **Structured evidence, not prose (PL-5).** A live proof names its
   subject, revision, and command output; "verified live" as a prose
   sentence is not evidence.

## Measurement Integrity (Goodhart meta-rules)

- Every claimed metric predeclares its denominator and a countermetric; no
  post-result denominator edits.
- **The quota is itself Goodhartable.** A numeric target ("≤5% process
  items") invites relabeling validators as features. Report the process
  share as a diagnostic for the owner, never a target for agents.
- Retries, two intermediaries over one ultimate source, or correlated runs
  are not independent evidence; count clusters once.
- Agreement between agents raises confidence, never authority class. Three
  lanes repeating one upstream claim is one datum.
- Never mint runtime artifact IDs (receipts, seeds, case IDs) at planning
  time; a manifest of fabricated future evidence IDs is a forgery template.
