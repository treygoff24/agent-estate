# cleanup

A deterministic cleanup and census, run every six hours. It deletes only agent scratch that it can prove is regenerable junk *and* old, reports orphaned processes without touching them, and writes one JSON line per action so you can see exactly what happened.

It does not touch `/tmp`: the `tmp-cleanup` module owns that. This one handles the other places scratch piles up.

## What it deletes (all age-gated)

| What | Proof it is junk | Age setting |
|---|---|---|
| Git worktrees in scratch locations: `<paths.code>/*-worktrees/*` and `<repo>/.worktrees/*` | clean (no uncommitted or untracked files), not locked, nothing inside modified for the age; removed with plain `git worktree remove` (never `--force`), and the branch is kept | `worktree_age` (7d) |
| `target/` beside a `Cargo.toml`, `node_modules/` beside a `package.json`, under `paths.code` | regenerable by a build; nothing inside modified for the age | `cache_age` (30d) |
| `*.log`, `*.log.N`, `*.log.gz` under the state directory and any `log_dirs` | older than the age | `log_age` (30d) |
| This module's own event files | older than the age | `events_age` (90d) |

Anything dirty, locked, symlinked, unreadable or too young is kept, and a kept worktree is logged with its reason. Records of worktrees whose directory is gone are pruned (`git worktree prune`).

## What it only reports

A process whose parent is init, running at least `orphan_hours`, and either in a deleted or scratch working directory (Linux) or averaging `orphan_cpu` percent of a core, is logged as an `orphan` event. **Nothing here signals a process**: killing is a decision for the person, who can see the report in `estate-health` or the event file. (A leaked dev server holding a deleted worktree open is the classic case.)

A `census` event closes every run: home-volume use, linked worktrees seen, build caches kept, orphans found.

## Events

`$ESTATE_STATE/cleanup/events-YYYYMMDD.jsonl`, one object per line: `ts`, `epoch`, `source`, `kind` (`deleted`, `would-delete`, `pruned`, `kept`, `failed`, `orphan`, `census`, `info`), `summary`, `dry_run`, plus fields such as `path` and `bytes`. `last-run.json` in the same directory records the last finished run, which is what `estate doctor` checks.

## Use

```sh
estate-cleanup run --dry-run   # preview: logs would-delete events, deletes nothing
estate-cleanup run             # what the timer runs
estate-cleanup last            # when the last run finished
```

## Settings

```toml
[modules.cleanup]
worktree_age = "7d"
cache_age = "30d"
log_age = "30d"
events_age = "90d"
log_dirs = []           # extra directories whose *.log files age out
orphan_hours = 6
orphan_cpu = 80
```

## Install and done when

`estate install cleanup` links `estate-cleanup` into `paths.bin`, installs the six-hourly job (a systemd user timer at 00, 06, 12 and 18 :17 on Linux; a launchd agent on the Mac) and does a first run. On the Mac the job names an absolute Python 3.11+ chosen at install (recorded in `$ESTATE_STATE/cleanup/python3`; install fails with a clear message if there is none) and sets its own `PATH`, because launchd's default `PATH` would run Apple's old Python; `estate doctor` fails if that interpreter goes away.

Done when `estate doctor` shows `cleanup ok`: the job is installed and enabled, and `last-run.json` is under 14 hours old. A job that stopped running fails the check; one that has not run yet warns. `estate uninstall cleanup` removes the job and the link and keeps the events.
