# Assessment rubric

Use this file after initial repo inspection to classify testing maturity and prioritize work.

## Maturity levels

| Level | Signals | Primary next move |
| --- | --- | --- |
| 0. No meaningful tests | No runner, no test files, or only generated/trivial examples | Establish one reliable local command and add characterization tests around critical behaviors |
| 1. Smoke-only | App boots, component renders, CLI runs, little behavior asserted | Add risk-based boundary tests before more smoke checks |
| 2. Unit-heavy but behavior-poor | Many mocks, high line coverage, weak confidence, private-detail assertions | Replace brittle tests with behavior/component/route/service tests at meaningful seams |
| 3. Good isolated tests, weak seams | Useful pure/component tests but poor auth/API/persistence/E2E coverage | Add boundary integration, contract, and top-journey tests |
| 4. Mature layered suite | Fast local checks, meaningful seam coverage, slim E2E, artifacts, stable CI | Ratchet thresholds, prune low-value tests, improve flake/coverage observability |

## Inventory checklist

If available, start with the bundled read-only helper at `scripts/test_inventory.py` relative to the coverage-architect skill directory. Do not look for this helper under the target repo's own `scripts/` directory unless the repo separately has one.

Inspect:

- Existing runners and configs.
- Current test naming/layout conventions.
- CI commands and artifacts.
- Coverage provider, thresholds, branch coverage support, and stale reports.
- Fixtures/factories/mock servers/testcontainers/test DB strategy.
- Known skipped/quarantined/flaky tests.
- Critical user/API/CLI workflows.
- Risk boundaries: auth, permissions, billing, deletion, persistence, migrations, webhooks, queues, caching, retries, concurrency, external services, file IO, parser/unsafe/adversarial input.

## Gap map fields

For each surface, write:

```md
- Surface:
- Behavior/invariant:
- Risk if broken:
- Current protection:
- Proposed test layer:
- Why this layer:
- Candidate files:
- Verification command:
- Needs domain input: yes/no
```

## Coverage interpretation

Coverage is a map, not a verdict.

Prefer branch coverage over line-only where available. Treat mutation/property/fuzz results as targeted confidence signals for critical pure logic, parsers, serializers, permissions, pricing, retry/backoff, and unsafe/adversarial-input code.

Do not raise thresholds until there is a stable baseline. Prefer ratcheting thresholds after meaningful tests exist.
