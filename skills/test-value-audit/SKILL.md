---
name: test-value-audit
description: >-
  Test value audit: gate a test you are writing or changing; audit a suite for
  low-value, duplicated, or implementation-coupled tests and the test-only
  production seams they keep alive; or prune one subsystem's whole test surface.
---

# Test value audit

Three modes, one **value bar**. The **authoring gate** checks every new or changed test at write time. An **audit** sweeps existing tests for ones that re-assert source, duplicate stronger proof, couple behavior to implementation, or keep test-only production seams alive, and lands them as coherent batches. A **campaign** prunes one subsystem's whole test surface (every test file a plugin or core area owns); before starting one, read [CAMPAIGN.md](CAMPAIGN.md). Optimize for confidence, not deletion count.

## Project facts

Every step below runs on the project's own tooling. Before judging or editing anything, read the root and scoped `AGENTS.md` / `CLAUDE.md` files, then find in CONTRIBUTING, CI config, and the package manifest:

- the test runner and its narrowest invocation (one file, one test, one filter);
- the formatter and linter;
- the full gate the repository requires before merge;
- any areas the project marks fix-only, where tests may be repaired but never deleted.

## Authoring gate

Before adding any test, answer four questions; a missing answer means do not add it yet:

1. What observable behavior, invariant, or independent contract does it protect?
2. What credible regression makes it fail?
3. Why does existing coverage not already catch that failure? Each contract has one primary test owner at the strongest boundary; another layer needs its own distinct risk, such as a transport or lifecycle failure the owner cannot reach. Prefer extending a table-driven case or shared fixture over a near-duplicate test; consolidate duplicated setup in the same change.
4. Does it need a production seam (export, flag, wrapper, injection hook) that no production caller needs? If yes, move the test to the real boundary instead.

Then check the test against every [junk pattern](#junk-patterns); a match fails the gate unless the [retention bar](#retention-bar) names the contract it independently guards. A test that would break under behavior-preserving refactoring is asserting implementation, not behavior; rewrite it at the owning boundary before landing it.

Bug regression tests must go red on the pre-fix code for the intended reason and green after the owner-boundary repair. A regression test that was never seen red proves the mock, not the fix. One regression at the owner boundary covers the bug; do not replay the same scenario at every layer it crosses.

## Junk patterns

The shared checklist for every mode: the authoring gate rejects a new test that matches one, and audits hunt for existing tests that do.

- assertion-free coverage probes;
- self-comparisons and identity copiers;
- copied fixtures, inventories, manifests, or export lists;
- exact source, import, or string greps;
- private predicate or call-shape tests duplicated at real boundaries;
- duplicate invocations of the same contract;
- provider-local replays of shared helpers;
- tests whose only purpose is preserving test-only exports, globals, or wrappers;
- dead production code whose only callers are tests;
- expected values produced by the helper or renderer under test;
- mocks that implement the asserted behavior, or one identical mock standing in for different APIs;
- fixtures that supply the receipt, admission, or callback ordering the owner should produce, or persistence asserted against a store the path never writes;
- capability tests that restate declared flags instead of exercising the delivery or acknowledgement the flag promises;
- negative controls that pass for an unrelated reason, such as a denial from a different guard or a rejection the production path never reaches;
- names or fixtures that promise more than the input exercises, such as a "retires the window" test asserting the window was not cleared.

## Value bar

Tests justify their maintenance cost by protecting behavior, a credible regression, or an independently meaningful contract. In an audit, an existing test that must change for behavior-preserving source reorganization is suspect, not automatically deletable; the authoring gate still rejects new ones.

Before judging a candidate, read the complete test and production owner, its entry point, callers, callees, sibling implementations, overlapping tests, CI routing, and relevant history. When the test claims dependency-backed behavior, inspect the dependency source or types directly.

## Discovery

Keep discovery read-only and report evidence before editing. Who fans out is decided once, at the top: a coordinator with broad scope splits it into parallel read-only discovery lanes by production owner; a lane (a subagent or child agent that was given one owner's files) is the discovery agent itself and reads its files in sequence, launching no helpers (in practice, eight lanes each fanning out hit the machine-wide agent cap within fifteen minutes). Example lanes for a coordinator:

- core library or service modules;
- plugins, extensions, or provider adapters;
- apps, UI, scripts, and tooling;
- one cross-cutting sweep for the junk patterns across all of them.

Outside campaign mode, prefer a few high-confidence candidates over a large speculative inventory.

## Retention bar

Keep a test when it independently enforces a public API, plugin SDK, protocol, config, migration, storage, security, platform, default, prompt-byte, generated cross-language, package, release, or architecture contract. Also keep:

- call ordering when order is observable behavior;
- regressions with a credible failure mode;
- source inspection when it is the cheapest independent guard: it fails when the contract changes (the user-facing key, byte, or path) and survives an identifier-only refactor;
- a retained test that fails on the baseline: treat it as a possible product bug, reproduce it, and repair the owner rather than deleting it.

Static or slow is not a deletion reason. A test that resembles implementation may still be the independent contract; prove otherwise before removing it.

## Candidate evidence

Record every field below before editing. A missing field means the candidate is not ready for deletion:

- exact test name and location;
- what failure it can actually detect;
- non-test callers of the covered production or support seam;
- stronger remaining owner-boundary proof, or why no proof is needed;
- relevant history and the reason the test or seam exists;
- production or test-support deletion unlocked;
- risk and the focused validation command.

## Edit shape

Choose one coherent owner-boundary batch. Delete obsolete test-only exports, globals, wrappers, and dead production paths instead of preserving aliases. Move retained regressions to their canonical owners. Consolidate repeated package or dependency assertions into one generic contract.

Prefer net-negative production LOC. Write no replacement tests that restate the same implementation, and leave uncertain candidates in place rather than converting them to cleanup.

## Validation

Edit only between test runs: a runner in watch mode or mid-run in the same checkout reads half-edited files and reports noise.

1. Run the smallest owner and sibling tests with the runner's narrowest invocation.
2. For removed source greps or plan assertions, run the executable, script, or dry-run that owns the real contract.
3. Run the formatter and linter on changed files, then `git diff --check`.
4. The coordinator runs the full gate the repository requires, once, on the final tree; a lane stops at steps 1 to 3 and reports.
5. Inspect `git diff --numstat`; report production and tooling separately from tests and test support.
6. After the final edits, have a reviewer who did not make them compare the deleted coverage against what remains.

## Landing and continuation

Commit, push, or open a PR only as the repository's rules and the user authorize. Land one coherent batch at a time; after it lands, refresh from the main branch and rerun read-only discovery for the next high-confidence batch.

## Handoff

Report:

- root cause and removed low-value categories;
- production owner simplifications;
- retained false positives and why they remain valuable;
- focused and full proof actually run;
- production versus test LOC;
- commit, PR, and merge state;
- named follow-ups.

<!-- provenance: forked 2026-09-29 from openclaw/openclaw `.agents/skills/test-audit` (revision ef1f568) with the OpenClaw runner, CI, review, and PR tooling replaced by the project's own. The upstream import was removed from the pool the same day. -->
