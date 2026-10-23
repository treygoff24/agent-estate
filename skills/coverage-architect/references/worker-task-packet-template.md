# Worker task packet template

Use this template for delegated implementation lanes.

```yaml
task_id: short-kebab-id
objective: >
  Add or improve tests proving one specific behavior/invariant.
repo_context:
  stack:
  current_test_runner:
  relevant_conventions:
files_in_scope:
  - path/or/glob
behavior_under_test:
  - observable behavior 1
  - observable behavior 2
risk_being_reduced: >
  Why this behavior matters to users, API consumers, operators, or data integrity.
commands_to_discover_first:
  - package.json scripts / Makefile / pyproject / Cargo / CI commands
likely_verification_commands:
  - command if already known from repo discovery
constraints:
  - preserve existing tooling unless impossible
  - use behavior/contract/invariant assertions
  - keep fixtures deterministic and isolated
forbidden_shortcuts:
  - no broad sleeps
  - no snapshot-only tests
  - no implementation-detail assertions when observable outcomes exist
  - no mocking away the target seam
expected_evidence:
  - files changed
  - command output summary
  - explanation of why the test is worth keeping
  - failure artifact paths if any
done_when:
  - targeted test passes or failure is diagnosed with evidence
  - test would fail on the intended regression
  - primary reviewer can inspect a small, coherent diff
```

## Report format for workers

```md
## Summary

## Files changed

## Behavior protected

## Commands run

## Evidence / artifacts

## Risks or follow-up
```
