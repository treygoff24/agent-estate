# The module contract

A module is one directory, `modules/<name>/`, that installs one piece of the estate and can say whether that piece is working. `estate` finds every directory here that holds a `module.toml`. `modules/tmp-cleanup/` is the reference: copy its shape.

## Files

| File | Required | What it is |
|---|---|---|
| `README.md` | yes | What the module does, its settings, and when it counts as done. Written for the person and their agent. |
| `module.toml` | yes | Metadata, below. |
| `install` | to be built | Executable. Installs or updates the module. Idempotent. `--dry-run` says what would change and changes nothing. |
| `check` | to be built | Executable. The doctor check, below. Changes nothing. |
| `uninstall` | no | Executable. Removes what `install` put in place. `--dry-run` as for `install`. |
| `templates/` | no | Files rendered with `estate render`: systemd user units, launchd plists, config fragments. |

A module with neither `install` nor `check` is a **stub**: `estate list` shows it as `stub`, `estate install` refuses it, and `estate doctor` reports it as a warning ("not built yet") when it is enabled. A built module has both. Scripts are any executable (bash is usual); helpers they share can sit beside them (tmp-cleanup has `common.sh`).

## module.toml

```toml
name = "tmp-cleanup"                 # must equal the directory name: lowercase, digits, dashes
description = "One line for `estate list`"
platforms = ["mac", "linux"]         # where it runs; elsewhere install skips it and doctor says ok
requires = []                        # other modules installed first, and enabled with it

[prerequisites]                      # commands that must be on PATH; doctor and install check them
all = ["git"]
linux = ["systemctl"]
mac = []

[defaults]                           # every setting the module reads, with its default
age = "1d"
```

Unknown keys are an error. `requires` must name modules that exist; a cycle is an error.

**Settings.** A user overrides a setting in `estate.toml` under `[modules.<name>]`. A key there that is not in `[defaults]` is a config error, so typos surface in `estate config check`. Scripts read the merged value with `estate config get modules.<name>.<key>`; templates use `${modules.<name>.<key>}`.

`ESTATE_MODULES_DIR`, if set, replaces `modules/` as the place `estate` looks for modules (the tests use it to drive the CLI with fixture modules).

## The environment scripts get

`estate` runs every script with the module directory as its working directory, stdin closed, and these set:

| Variable | Value |
|---|---|
| `ESTATE_CONFIG` | absolute path of the `estate.toml` in use |
| `ESTATE_ROOT` | the repo checkout (`$ESTATE_ROOT/bin/estate` is the CLI) |
| `ESTATE_STATE` | the state directory (`paths.state`, default `~/.local/state/agent-estate`); it exists |
| `ESTATE_PLATFORM` | `mac` or `linux` |
| `ESTATE_MACHINE` | this machine's `[[machines]]` name, or empty if it cannot tell |
| `ESTATE_MODULE` | the module's name |
| `ESTATE_MODULE_DIR` | the module's directory |

`lib/estate.sh` is the shell helper. Source it first: `. "$ESTATE_ROOT/lib/estate.sh"`. It sets `set -euo pipefail`, reads `--dry-run` into `ESTATE_DRY_RUN=1`, and defines `cfg KEY`, `label`, `render TEMPLATE DEST` (honours dry run), `run CMD...` (prints instead of running under dry run), `say MSG`, and `ok`/`warn`/`fail MSG [DONE_WHEN]` for checks.

**Mac jobs must pin Python.** launchd starts jobs with a minimal `PATH`, where `python3` is Apple's 3.9 or missing. A module whose Mac job runs Python calls `pin_python` in `install` (finds Python 3.11+, records it in `$ESTATE_STATE/<module>/python3`, sets `PY`; fails with a clear message if there is none), writes `@PYTHON@` in its plist template where the interpreter goes, and installs it with `render_pinned TEMPLATE DEST`. Its `check` calls `pinned_python` and compares against `rendered_pinned TEMPLATE`. Every plist also sets an explicit `EnvironmentVariables` `PATH` (`paths.bin`, `/opt/homebrew/bin`, `/usr/local/bin`, system dirs); Linux units set `Environment=PATH=` with `paths.bin` first.

## The check

`check` answers one question: is this module doing its job on this machine right now?

- **Exit code:** `0` ok, `1` fail, `2` warning. Any other exit, or running past 60 seconds, counts as a fail.
- **Output:** the first line is the status, e.g. `ok: /tmp ages out after 1d (hourly sweep)` (a leading `ok:`/`warn:`/`fail:` is dropped in the table, since the status column says it). Somewhere after it, one line `done when: <what green means>`, in words a newcomer can act on. Doctor shows that line under any row that is not ok.
- Check what is true now (the file matches what the config renders to, the timer is active), not that install once ran. Change nothing.

`estate doctor` runs core checks (Python 3.11+, git; on Linux the systemd user manager and linger), validates the config, then runs the check of every enabled module in `requires` order, prints a table and exits with the worst status: `1` if anything failed, else `2` if anything warned, else `0`. `--json` prints the same rows as JSON.

## Install

`estate install [module...]` (no names: every enabled module) installs the named modules and everything they require, dependencies first, each once. It skips modules not used on this platform, refuses stubs and missing prerequisites, and stops at the first failure. `--dry-run` is passed through to every script. `estate uninstall <module...>` runs `uninstall` for the named modules only, dependents first.

An install must be idempotent: run twice, the second run changes nothing and succeeds. It runs as the agents' login, which has no sudo. If something truly needs root, the install prints the exact command for the person to run and the check fails until it is done.

## Templates and labels

`estate render <template> [--out PATH] [--module NAME]` fills `${dotted.key}` from the config: anything `estate config get` can read (`${paths.state}`, `${machines.vps.ssh}`, `${modules.tmp-cleanup.age}`), plus:

| Placeholder | Value |
|---|---|
| `${label}` | `label_prefix` + `.` + module name, e.g. `com.example.estate.tmp-cleanup`: use it for every launchd label and systemd unit name |
| `${module}` | module name |
| `${home}` | the user's home directory |
| `${machine}` | this machine's name, or empty |
| `${estate.root}` | the repo checkout |
| `$${X}` | a literal `${X}`, for systemd's own variable expansion |

Paths come out absolute (launchd does not expand `~`). An unknown key, a list or table value, or a malformed `${` is an error, and `--out` writes nothing unless every placeholder rendered; with `--out` the write is atomic. A template under `modules/<name>/templates/` gets its module from its path; elsewhere pass `--module`. `estate label <module>` prints the label for scripts.

## Adding a module

1. `mkdir modules/<name>` with `README.md` and `module.toml`.
2. Write `install` and `check` (and `uninstall` if it leaves anything behind); `chmod +x` them. Start from `modules/tmp-cleanup/`.
3. Add any setting to `[defaults]`, any unit file to `templates/`.
4. Add tests under `tests/` that drive it through `bin/estate` with a temporary HOME and config (see `tests/test_tmp_cleanup.py`; fake system commands on PATH where the real ones would change the machine).
5. Run `scripts/gate.sh`.
