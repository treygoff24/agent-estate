# guardrails

Keeps many agents on one box from melting it or shooting themselves in the foot. Three pieces, installed into `paths.bin` (default `~/.local/bin`):

| Command | What it is |
|---|---|
| `testrun <repo> <kind> -- <cmd...>` | The one way agents run tests, gates, builds and sweeps. Caps CPU and memory, refuses a duplicate run, kills the whole tree at a time limit. |
| `compile-slot-gate`, `rustc-gate` | Optional, for Rust users: N machine-wide compile slots with a memory-headroom gate; `rustc-gate` is a `RUSTC_WRAPPER` that takes a slot. |
| `footgun-hook` | A PreToolUse hook for Claude Code and Codex that refuses machine-checkable shell mistakes before they run. |

Written for the agent that installs it: install, merge the hook fragment, run `estate doctor`.

## Install

```bash
estate install guardrails        # --dry-run first if you like
```

Then wire the hook into each harness you use (below). Without that step everything but the footgun refusals works, and `estate doctor` warns.

## testrun

```bash
testrun myrepo unit -- pytest -q                     # kind "unit": 10 min default limit
testrun myrepo gate -- bash scripts/gate.sh          # kinds starting "gate": 30 min
testrun myrepo mut-sweep --max 5400 -- make mutants  # kinds starting "mut": 2 h
testrun --list                                       # live runs
testrun --stop myrepo-unit
```

`<repo>` and `<kind>` are lowercase letters, digits and dashes; a run is named `<repo>-<kind>`. Two runs of the same name never overlap: the second exits 75 at once (a different kind in the same repo is fine). Options go before `--`: `--max SECONDS` is the execution limit (exit 124), `--wait-max SECONDS` bounds the Mac memory-pressure wait before the run starts (exit 75). The command's own exit code comes back otherwise; 64 is a usage error.

- **Linux.** The command runs in a transient systemd user scope (`systemd-run --user --scope --unit=<repo>-<kind>`) inside one shared slice that caps memory (`memory_high`, `memory_max`) and shares CPU by weight (`cpu_weight`), with no CPU quota, so a lone run may use every core. A scope inherits environment, cwd, stdin and stdout, so nothing is written to a unit file (a transient service would copy the environment, API keys included, into a readable file). Everything the run started dies with the unit. With no systemd user bus, `testrun` exits 69 and never runs the command unwrapped (check `loginctl enable-linger $USER`). The run's processes get `oom_score_adj` 1000, so the kernel kills a test run before anything else.
- **macOS.** No systemd. The command runs at **nice 19** with every core available (never `taskpolicy -b`: it confines work to the efficiency cores and measured 21x slower; and never nice 20, which breaks tools that set their own low priority). Before starting, `testrun` waits while `kern.memorystatus_vm_pressure_level` is critical (4) on two readings 3 seconds apart; the "warn" level never blocks. The command runs in its own process group, and the whole group is killed when the run ends, times out or is interrupted. There is deliberately no machine-wide job cap here; add one if your Mac types badly under load, and see the field guide `guides/many-agents-compiling.md` for the pause-under-pressure refinement.

Heavy runs with lots of test containers, Docker volumes or Rust target directories need more than this: see `guides/many-agents-compiling.md`.

## Compile slots (optional)

Off by default. Set `compile_slots = true` under `[modules.guardrails]` and re-run `estate install guardrails`, then in `~/.cargo/config.toml` (Cargo does not expand `~`, write your home path):

```toml
[build]
rustc-wrapper = "/home/<you>/.local/bin/rustc-gate"
```

At most `rustc_slots` compiles run at once across every session and worktree (default 12 on Linux, 8 on a Mac, never above the core count). The first `rustc_base` slots are always open; each slot past them opens only while the machine has `rustc_headroom_gb` free memory plus 2 GB per high slot below it, because the limit on a big box is memory, not cores. Waiting costs almost nothing: one waiter probes the slots, the rest sleep in `flock`. `rustc-gate` also runs the compiler through `sccache` when it is installed (`RUSTC_GATE_SCCACHE=0` turns that off, `RUSTC_GATE_SLOTS=0` bypasses the slots) and at nice 19 on a Mac. `compile-slot-gate status` prints the snapshot also published to `~/.local/state/compile-slots/state.json` (`in_use`, `total`, `queue_depth`; older than 5 seconds means unknown).

## The footgun hook

`footgun-hook` reads the PreToolUse JSON on stdin and acts only on the Bash tool. It refuses with a one-line reason naming the rule and the fix (`[footgun:<id>] ...`), and prints nothing when the command is fine. A bug inside it allows the call: a guard that cannot read a command must not block work.

| Rule id | Refuses |
|---|---|
| `kill-by-pattern` | `pkill`, `killall`, `kill -1` (not `pkill -P <pid>` or `kill <pid>`) |
| `rm-deadly-path` | recursive `rm`/`trash` of `""`, `.`, `/`, `~`, `$HOME`, `*` |
| `rm-unguarded-variable` | recursive `rm`/`trash` of `"$VAR"` or `"$VAR/..."` with no `${VAR:?}`, `[ -n "$VAR" ]`, assignment or `set -u` before it |
| `heredoc-unquoted-dollar` | `<<EOF` with an unquoted delimiter whose body holds `$` or backticks |
| `find-delete` | `find ... -delete` outside `/tmp`-style scratch |
| `pipeline-exit-code` | a `head`/`tail` pipeline whose masked exit is read through `$?` or gates `git commit/push` |
| `heavy-test-unwrapped` | `pytest`, `python -m unittest`, `cargo test`, `pnpm test`, `make test`, `go test`, `scripts/gate.sh` ... not run through `testrun` |
| `rg-replace-flag`, `rg-help-flag`, `sed-bare-range`, `pnpm-double-dash`, `perl-i-truncate` | single-tool traps from `doctrine/shell-footguns.md` |

It is not a shell parser: it reads quotes, heredocs, `$(...)`, `bash -c '...'` and common wrappers (`sudo`, `env`, `nice`, `timeout`), and it is deliberately conservative. The reasons behind each rule are in `doctrine/shell-footguns.md`. It enforces no git policy (that is yours to write).

- **Bypass one command:** put `# FOOTGUN-OK` in it.
- **Switch a rule off on this machine:** list its id, one per line, in any `~/.config/agent-estate/footgun-skip*` file, or in the comma-separated `ESTATE_FOOTGUN_SKIP`. `refuse_unwrapped_tests = false` in `estate.toml` does this for `heavy-test-unwrapped`.

### Wiring the hook into a harness

The fragments are in this module: `settings/claude.json` and `settings/codex-hooks.json`. They run `~/.local/bin/footgun-hook`; if you changed `paths.bin`, edit the path in the copy you merge.

- **Claude Code:** merge `settings/claude.json` into `~/.claude/settings.json` (or the account's `$CLAUDE_CONFIG_DIR/settings.json`). The config-sync module does this with a `merge-json` row; point that row at `modules/guardrails/settings/claude.json`. By hand: add the `hooks.PreToolUse` entry without removing your other hooks.
- **Codex:** Codex supports the same PreToolUse hook (`~/.codex/hooks.json`, matcher `^Bash$`, same deny envelope). Merge `settings/codex-hooks.json` into it, start Codex, open `/hooks` and **trust** the new hook: Codex skips an unreviewed hook silently apart from a startup warning. Codex's own docs call tool hooks a guardrail, not a complete enforcement boundary.

## Settings

Override under `[modules.guardrails]` in `estate.toml`:

| Key | Default | Meaning |
|---|---|---|
| `compile_slots` | `false` | also install `compile-slot-gate` and `rustc-gate` |
| `rustc_slots` | `0` | concurrent compiles; 0 means 12 on Linux, 8 on a Mac (never above the core count) |
| `rustc_base` | `6` | slots that are always open |
| `rustc_headroom_gb` | `12` | free memory to open the first slot above the base (+2 GB per slot after) |
| `memory_high` | `"80%"` | Linux: soft memory limit for all test runs together (bytes with K/M/G/T, or a percent of RAM) |
| `memory_max` | `"90%"` | Linux: hard ceiling; past it the kernel kills inside the test slice only |
| `cpu_weight` | `100` | Linux: the test slice's CPU share against sibling slices (no quota) |
| `refuse_unwrapped_tests` | `true` | hook refuses test and gate commands that skip `testrun` |

Install also writes `~/.config/agent-estate/guardrails.json` (the slice name and the compile-slot settings, read by the tools at run time) and the slice unit `~/.config/systemd/user/<label with dashes as underscores>.slice` on Linux.

## Papercuts behind these defaults

- CPU quotas on a slice froze every task in it for the rest of each period and timed out timing-sensitive tests; weight-only sharing did not. Memory gets a hard ceiling, CPU does not.
- A global out-of-memory kill landed on a service instead of the test build until test runs were made the preferred victim.
- The agent harness starts children with SIGINT and SIGQUIT ignored, and the ignore survives `exec`; `testrun` resets both so interrupted Python test runs stop.
- `nice -n 19` is relative: from an already-niced parent it lands on 20. `rustc-gate` raises to exactly 19.
- 100 queued compilers each probing every slot burned a Mac; only the head waiter polls.

## Done when

`estate doctor` shows `guardrails` ok: the commands are in `paths.bin` and match this repo, the slice and config are installed (Linux), and the hook is in each configured harness's settings. A hands-on check: `testrun demo unit -- sh -c 'ps -o ni= -p $$'` prints 19 on a Mac and runs inside a scope on Linux, and `echo '{"tool_name":"Bash","tool_input":{"command":"pkill -f x"}}' | footgun-hook` prints a deny.
