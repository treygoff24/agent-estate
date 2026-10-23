---
name: quality-gate
description: Wire a strict, low-false-positive quality gate into a repo that AI agents write code in, so subagent output self-checks against a mechanical floor instead of a coordinator cleanup pass. Use when setting up linting/formatting/type/design checks for an agent-built repo, hardening a repo before a subagent fan-out, or wiring oxlint / oxfmt / react-doctor / impeccable into one blocking command.
---

# quality-gate

One command, `npm run gate`, that a subagent runs and lands **green** before reporting done. The gate is the mechanism that holds grunt-work code at standard without the coordinator hand-fixing every lane's output.

## The one law

**A gate strict on substance and silent on noise raises the floor. A gate that cries wolf gets bypassed.** The first false positive on a legitimate change teaches every downstream agent to reach for `--no-verify`, and then you have tooling theater instead of a floor. So the work is not installing linters — that part is minutes. The work is *calibrating out the false positives* so the gate only ever fires on a real defect. Budget your time there.

## Setup

1. **Chain the stages into one script.** Add a `gate` npm script that runs, in order and short-circuiting: format-check → lint → typecheck → framework-lint → design-lint → any domain lint. Each stage is also its own script so an agent can run one in isolation. Completion: `npm run gate` exits 0 on a clean tree and non-zero on a seeded defect (test both before trusting it).

2. **Scope each tool to what it should judge.** Formatters and design linters run on source only (`src`), never on prose, docs, generated content, or committed data — a formatter that reformats your markdown deliverables is noise by construction. Set each tool's ignore/scope so it never sees a file it has no business judging.

3. **Calibrate to green on a clean scaffold.** Run the gate on the fresh scaffold and drive it to zero findings by *disposition, not suppression-in-bulk*: for each finding decide real-defect (fix it) or false-positive (turn off that specific rule, with the framework reason). The per-tool false positives worth pre-empting are in `references/tool-gotchas.md` — read it before you start swatting them one by one. Completion: gate is green AND you can name why every disabled rule was a false positive, not just that it was noisy.

4. **Make it blocking, and tell the agents.** Install the gate as a pre-commit hook so a red gate stops the commit (agents must never `--no-verify` past it). Then put one line in every build-lane brief and the repo's `CLAUDE.md`: *run `npm run gate` and land it green before reporting done.* A gate no subagent knows to run is a gate that runs once, at the end, on the coordinator.

## The roster (JS/TS example)

Swap equivalents for other stacks; the law and the four calibration moves (chain, scope, disposition, block) are stack-independent.

- **oxfmt** — format check. Fast. Scope to `src`.
- **oxlint** — the workhorse lint. Turn the aggressive tiers on (`correctness`, `suspicious`, `perf`, `pedantic`, `style`) — then expect to disable a handful of rules that fight your framework's idioms (see gotchas). `--deny-warnings` so warnings fail.
- **tsc --noEmit** — types. `strict` + `noUncheckedIndexedAccess` is the real floor.
- **react-doctor** — framework-level defects (hook misuse, dead code, secret-in-bundle). Install is invasive; see gotchas before wiring.
- **impeccable detect** — design anti-patterns on the built UI; honors a project reject-list (generic-AI fonts, glassmorphism, etc.). Source-scoped.
- **a domain lint** — if the repo has a content/data contract, a small schema linter belongs in the same gate (frontmatter shape, enum validity, cross-file refs). This is usually the highest-signal stage because it is bespoke to your invariants.

Verbatim config that passed a real Next 16 build is in `references/configs.md`. Treat it as a starting point to calibrate from, not gospel.
