# Delegation workflow

Use this when coverage work is large enough to split into independent lanes.

## Primary agent responsibilities

The primary agent owns:

- Repo assessment and gap map.
- Test strategy and layer selection.
- Worker task boundaries.
- Review of every diff.
- Verification command selection.
- Final maturity/coverage report.

Do not delegate the architectural judgment that determines what is worth testing.

## Worker lane rules

A worker task must be bounded by behavior and files, not by vague coverage goals.

Good objective:

> Add tests proving invalid webhook signatures are rejected, duplicate event IDs are idempotent, and valid events enqueue exactly once.

Bad objective:

> Improve webhook test coverage.

Workers must return evidence:

- Files changed.
- Why the test is valuable.
- Commands run and output summary.
- Any artifacts/logs/traces for failures.
- Known limitations.

## Launching workers

Use whatever your harness gives you for bounded workers (Claude Code subagents, `codex exec`, or another agent runner). Typical routing:

- A write-enabled worker in its own git worktree for bounded implementation.
- A read-only worker (read-only sandbox or a reviewer subagent) for audits and reviews.

Keep prompts bounded: task, scope, verification, constraints, and report format. Prefer prompt files for long packets. Always review work-mode diffs before accepting.

## Lane splitting patterns

Split by independent behavior surface:

- React forms vs API route handlers vs auth E2E.
- Python CLI config precedence vs FastAPI auth endpoint vs webhook idempotency.
- Rust parser property tests vs CLI tempdir tests vs snapshot cleanup.

Avoid splitting lanes that will touch the same setup file or test harness unless one worker is explicitly responsible for harness setup and others wait.

## After worker completion

1. Inspect diff.
2. Apply quality-gate rubric.
3. Run targeted command.
4. If green and valuable, run narrow gate.
5. Reject or patch weak tests even if they pass.
6. Update final gap map with what changed and what remains.
