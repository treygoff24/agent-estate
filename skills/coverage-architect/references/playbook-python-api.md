# Python, APIs, and backend playbook

## Defaults

- Prefer pytest when the repo has no established alternative.
- Use coverage.py for coverage; prefer branch coverage when available.
- Preserve existing tox/nox/pytest-asyncio/framework settings.
- Use framework test clients before raw sockets when they prove the seam.
- Use dependency override mechanisms before monkeypatching internals.
- Use Testcontainers or real test databases when datastore/protocol semantics matter.

## Python scripts and CLIs

High-value tests cover:

- CLI args, env vars, config file precedence, and defaults.
- Human-readable errors and exit codes.
- Tempdir/file IO behavior.
- Idempotency and dry-run behavior.
- Time-dependent behavior with frozen/controlled time.

Use temp dirs, monkeypatch/env fixtures, subprocess or framework CLI runners, and controlled clocks.

## FastAPI / Flask / Django

- FastAPI: use `TestClient` for sync-style app tests; use async client/ASGI transport when the test itself awaits async behavior; prefer `app.dependency_overrides` for seams.
- Flask: use app/client/CLI fixtures from `conftest.py` patterns.
- Django: use `TestCase`/transaction-backed isolation, client for request behavior, RequestFactory for direct view tests, and browser tools for JS/rendered UX.

## API/backend priorities

Test high-risk boundaries before easy CRUD:

- Auth/authz matrices and permission escalation failures.
- Validation and error shapes.
- Idempotency and duplicate deliveries.
- Pagination, sorting, filtering consistency.
- Webhook signatures and replay protection.
- Background job reentrancy and queue side effects.
- Migration/backfill correctness.
- Cache invalidation and stale reads.
- Retry/partial failure behavior.
- Observability/audit events when part of the contract.

## Contract and schema testing

- Use explicit handler/client tests for core semantics.
- Use OpenAPI/schema-driven tests such as Schemathesis when schemas exist and input edge cases matter.
- Use consumer-driven contracts such as Pact when provider/consumer compatibility is the risk.
- Do not replace focused auth/persistence/idempotency tests with broad schema fuzzing alone.

## HTTP mocking choices

- HTTPX clients: consider RESPX when already present or appropriate.
- Recorded external APIs: VCR.py can help when cassettes are reviewable and sanitized.
- Real dependencies: prefer Testcontainers for Postgres/Redis/etc. when mocks would lie.

## Good scenarios

- Duplicate idempotency key returns original result without duplicate side effect.
- Invalid webhook signature is rejected; duplicate event is ignored; valid event enqueues once.
- Auth-required endpoint denies anonymous and insufficient-role users, permits authorized user.
- CLI config precedence is arg > env > config > default, with useful error messages.
- Migration preserves invariant on representative legacy rows.
