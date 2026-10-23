# Maturity report template

Use for substantial assessment or implementation runs.

```md
# Test maturity report

## System summary

- Repo:
- Stack(s):
- Primary runner(s):
- Existing CI/test gates:
- Current maturity level:

## What is already well covered

- ...

## High-risk uncovered or weakly covered areas

| Priority | Surface | Behavior/invariant | Current protection | Recommended layer | Why |
| --- | --- | --- | --- | --- | --- |

## Changes made

| File(s) | Behavior protected | Why this is valuable |
| --- | --- | --- |

## Commands verified

| Gate | Command | Result |
| --- | --- | --- |

## Coverage notes

- Line/branch/context/mutation/property/fuzz availability:
- Baseline or delta:
- Caveats:

## Quality gate notes

- Rejected low-value tests:
- Flake risks fixed or remaining:
- Mocking/seam realism notes:

## Remaining next tests

- [P1] [layer] behavior - why
- [P2] [layer] behavior - why

## Stop conditions / user decisions needed

- ...
```
