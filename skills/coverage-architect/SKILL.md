---
name: coverage-architect
description: Assess and improve software test coverage with a behavior-first, senior-QA workflow. Use when asked to add tests, improve coverage, establish testing from scratch, audit test maturity, harden CI test gates, write behavior-driven tests, test React/Next.js/TypeScript/JavaScript/Python/API/Rust code, or coordinate delegated worker agents for test implementation while the primary agent reviews quality.
---

# Coverage Architect

Improve confidence, not vanity coverage. Use this skill to assess a repo's current testing maturity, identify the highest-value unprotected behaviors, delegate bounded test implementation work when useful, and reject low-signal tests even when they pass.

## Operating stance

- Keep the primary agent in **architect/reviewer/quality-gate** mode for substantial work.
- Prefer behavior, contract, invariant, and user-journey tests over implementation-detail tests.
- Choose the cheapest test layer that actually proves the behavior.
- Preserve existing test tooling unless it is absent, broken, or clearly mismatched.
- Discover repo-native commands before inventing runner commands.
- Treat flaky tests as failed test-system design, not acceptable near-passes.
- Do not chase coverage percentage before establishing meaningful baseline tests.

## Fast path

1. Inspect repo instructions, dirty state, manifests, test configs, CI, and existing tests.
2. Run the bundled inventory script when a read-only inventory helps. It lives inside this skill, not the target repo. Run `python3 <skill-folder>/scripts/test_inventory.py <repo-root>`, where `<skill-folder>` is this skill's installed directory.
3. Classify maturity with `references/assessment-rubric.md`.
4. Build a gap map of high-risk unprotected behaviors.
5. Load only the relevant stack playbook(s):
   - JS/TS/React/Next: `references/playbook-js-ts-react-next.md`
   - Python/API/backend: `references/playbook-python-api.md`
   - Rust/CLI: `references/playbook-rust.md`
6. If implementation is more than a small local patch, use `references/delegation-workflow.md` and `references/worker-task-packet-template.md` to delegate bounded lanes.
7. Review every added/changed test with `references/quality-gate-rubric.md`.
8. Report results using `references/maturity-report-template.md`.

## Assessment workflow

### 1. Read before running

Before assuming the inventory helper is absent, locate this skill's own directory. The helper is bundled at `scripts/test_inventory.py` relative to `SKILL.md`; it is not expected to exist as `<repo>/scripts/test_inventory.py`.

Inspect, in order:

- Local agent instructions: `AGENTS.md`, `CLAUDE.md`, `.codex/`, `.agents/` when present.
- Git state: changed, untracked, ignored test artifacts.
- Manifests and config:
  - JS/TS: `package.json`, lockfiles, `tsconfig*`, `vite.config*`, `vitest.config*`, `jest.config*`, `playwright.config*`, `cypress.config*`, `next.config*`.
  - Python: `pyproject.toml`, `pytest.ini`, `tox.ini`, `noxfile.py`, `requirements*.txt`, framework app files.
  - Rust: `Cargo.toml`, workspace members, `nextest.toml`, `.cargo/config*`.
  - General: `Makefile`, `justfile`, `Taskfile*`, `.github/workflows/*`, CI config.
- Existing tests, fixtures, mocks, factories, test setup, and coverage reports.
- High-risk surfaces: auth, permissions, billing, data deletion, persistence, migrations, webhooks, background jobs, caches, middleware/proxy, file IO, external integrations, CLI entrypoints, parsers, unsafe Rust, public SDK/API contracts.

### 2. Discover commands before inventing them

Prefer commands in this order:

1. Project docs and agent instructions.
2. Package/task scripts: `package.json`, Make/Just/Task, pyproject tools, tox/nox, Cargo aliases.
3. CI workflow commands.
4. Existing runner config.
5. Framework-native fallback commands only after discovery fails.

Use four gate levels:

| Gate | Purpose | Examples |
| --- | --- | --- |
| Targeted | Worker iteration | one test file, one package, one changed behavior |
| Narrow | Prove touched behavior | related suite/package/service |
| Full local | Catch cross-cutting regressions | unit + integration stack |
| Release-confidence | Top runtime flows/artifacts | E2E, coverage, browser traces, packaged CLI |

Run the smallest gate that can falsify the claim, then escalate only when warranted.

### 3. Create the gap map

For each important surface, record:

- Behavior or invariant at risk.
- Current protection: none, smoke-only, over-mocked, meaningful unit, meaningful boundary/integration, meaningful E2E, contract/property/fuzz coverage.
- Recommended layer and why it is the cheapest layer that proves the behavior.
- Verification command.
- Whether domain confirmation is needed.

## Implementation policy

### Proceed autonomously when

- The repo has standard test conventions and safe local commands.
- The desired behavior is derivable from code, docs, routes, tests, issues, or explicit user request.
- Missing coverage is clearly at a high-risk seam.
- Work can be bounded to small file sets and verified locally.

### Stop and ask when

- Multiple plausible strategies would materially change project architecture.
- Auth, billing, data deletion, regulated workflows, or production-like fixtures require domain truth not present in the repo.
- Tests require secrets, paid services, destructive remote state, or unavailable infrastructure.
- Existing failures look like environment/tooling breakage rather than the touched behavior.
- A custom internal harness cannot be safely understood from local files.

### What to reject

Reject or rewrite tests that:

- Only assert render/existence without meaningful behavior.
- Assert private implementation details, hook calls, or arbitrary mock calls.
- Mock away the auth/router/database/runtime seam that is the actual risk.
- Use broad sleeps instead of condition-based waits.
- Add giant or unreadable snapshots.
- Depend on live networks for unit tests.
- Share mutable fixtures or depend on execution order.
- Inflate line coverage without improving confidence.

## Delegation policy

For substantial coverage work, delegate implementation lanes and keep the primary lane responsible for architecture and review.

- If your harness can launch bounded workers (subagents, `codex exec`, another runner), use them for bounded worker tasks.
- Use work mode for scoped implementation. Use safe/read-only mode for audits or independent review.
- Give workers narrow packets: objective, files in scope, behavior under test, risk, commands, constraints, forbidden shortcuts, and expected evidence.
- Do not accept a worker result until you inspect the diff and run/confirm relevant verification.
- Mix worker models only when multiple independent lanes exist; do not delegate urgent blocking analysis if the primary lane needs it immediately.

Read `references/delegation-workflow.md` before fanning out work.

## Final report requirements

End substantial runs with:

- Current test maturity level.
- What changed and why the tests are worth keeping.
- Commands run and exact pass/fail status.
- Coverage/tooling notes, including any unreliable or missing coverage signal.
- Remaining high-risk gaps.
- Rejected low-value test ideas or worker outputs, if any.

Use `references/maturity-report-template.md` for longer handoffs.
