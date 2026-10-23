# health

A read-only collector that answers "what is the state of this box now, and what happened since I last looked?". It runs hourly, writes a cache, and exits with the worst severity so a script or an agent can act on the number alone.

## What it checks

| Check | Means |
|---|---|
| `disk` | percent of the home volume in use |
| `memory` | percent of memory in use, not counting reclaimable cache |
| `units` | failed systemd user units (Linux) or launchd agents with a non-zero exit (Mac) whose name starts with this estate's `label_prefix` |
| `doctor` | the result of `estate doctor` (a failing row is `crit`, a warning is `warn`) |
| `sync` | last nightly sync, read from `$ESTATE_STATE/sync/` when it exists (absent is `unknown`, not a failure) |
| `runaway_processes` | processes averaging high CPU for a long time |
| `stale_worktrees` | git worktrees of repos under `paths.code` untouched for a while, or whose directory is gone |

Severity is `ok`, `unknown`, `warn` or `crit`. `unknown` means the check could not run and never raises the exit code.

## Use

```sh
estate-health             # collect now, print text; exit 0 ok, 1 warn, 2 crit
estate-health --json      # the same report as JSON
estate-health show        # the cached report, no collection (exit 3 if none)
estate-health ack --by me # mark this report as triaged
```

`ack` records every warn/crit finding in the cached report as known. The next report's "since last ack" section lists only new findings, resolved ones, and a count of what `estate-cleanup` did in between. `attention` in the JSON is true for something new or any `crit`.

State is in `$ESTATE_STATE/health/` (`latest.json`, `ack.json`). The collector writes nothing else and changes nothing on the machine.

An agent should read `skill/estate-health/SKILL.md` (install it with the skills module, or copy it to your harness's skills directory): it says how to read the report each morning, what is safe to fix, and what to bring to the person.

## Settings

In `estate.toml` (defaults shown):

```toml
[modules.health]
disk_warn = 85          # percent of the home volume used
disk_crit = 95
mem_warn = 85
mem_crit = 95
runaway_cpu = 80        # average % of one core ...
runaway_minutes = 30    # ... sustained at least this long
worktree_days = 14
```

## Install and done when

`estate install health` links `estate-health` into `paths.bin`, installs the hourly job (a systemd user timer on Linux at minute 7, a launchd agent on the Mac) and takes the first report. On the Mac the job names an absolute Python 3.11+ chosen at install (recorded in `$ESTATE_STATE/health/python3`; install fails with a clear message if there is none) and sets its own `PATH`, because launchd's default `PATH` would run Apple's old Python. On both platforms the job's `PATH` starts with the keys module's `shim_dir`, then `paths.bin`, so the doctor run inside the report sees the key shims first and its `keys` row does not warn; `estate doctor` fails if that interpreter goes away.

Done when `estate doctor` shows `health ok`: the job is installed and enabled, and `latest.json` is under 150 minutes old (the hourly interval plus slack). A job that stopped running fails the check; one that has not run yet warns.

`estate uninstall health` removes the job and the link and keeps the reports.
