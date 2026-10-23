# sync

Once a night on every machine, brings your repos current through git, then runs any hooks other modules register. This is how "nothing crosses machines except through git" holds: each machine pulls what the others pushed.

## What it does

1. **Repo table.** For each repo listed in the table: clone it if missing, otherwise `git fetch` and `git pull --no-rebase --ff-only`. It never resets, stashes or discards anything. A checkout with uncommitted changes to tracked files, a detached HEAD, no upstream, or a history that diverged from upstream is **skipped and reported**, not fixed.
2. **Install command.** A row may carry a command (`bash -c`, run in the repo). It runs only when the pull moved HEAD or the repo was just cloned, with `ESTATE_SYNC_NAME`, `ESTATE_SYNC_REPO`, `ESTATE_SYNC_BEFORE`, `ESTATE_SYNC_AFTER` set. Exit 75 means "not now": the repo shows as skipped and the command is retried next run even if nothing new arrived. Any other nonzero exit is a failure, also retried.
3. **Hooks.** The `hooks` setting is an ordered list of shell commands run after the repo table (config sync, skill sync and so on plug in here without editing this module). A failing hook does not stop later ones; it makes the run fail.
4. **Status and log.** `$ESTATE_STATE/sync/status.json` (per repo and per hook: `ok`/`skipped`/`failed`, reason, timestamps, and an overall `ok`) and `$ESTATE_STATE/sync/sync.log`. `estate-sync` exits nonzero if anything failed; skipped repos are not failures.
5. **Timer.** A systemd user timer and service (Linux) or a launchd agent (Mac), rendered from `templates/`, daily at 04:00 local by default. On a Mac asleep at that time, launchd runs it on wake.

## The repo table

A tab-separated file, by default `~/.config/agent-estate/sync-repos.tsv` (`install` writes a commented starter). One repo per line, `#` for comments:

```
name <TAB> path <TAB> install command
```

- `name`: the repo; its remote is `<git.remote_base>/<name>.git`.
- `path`: the checkout; empty or `-` means `<paths.code>/<name>`. `~` is allowed.
- `install command`: optional.

Example (the second column is `-` for the default path):

```
dotfiles
my-tool	-	cargo install --path . --root ~/.local
```

## Settings (`[modules.sync]` in estate.toml)

| Key | Default | Meaning |
|---|---|---|
| `repos_file` | `~/.config/agent-estate/sync-repos.tsv` | the repo table |
| `hooks` | `[]` | commands run in order after the repo table |
| `hour`, `minute` | `4`, `0` | local time the timer fires |

## Install, run, check

- `estate install sync` links `estate-sync` into `paths.bin`, writes the starter table if there is none, and loads the timer or agent. It is idempotent; `--dry-run` changes nothing. The link points into this checkout, so the script updates when the checkout does.
- Run it by hand any time: `estate-sync`.
- `estate uninstall sync` removes the timer or agent and the link; the repo table, checkouts and state stay.
- The timer reads the config at its default location (`~/.config/agent-estate/estate.toml`). If you keep it elsewhere, put the repo table, hooks and times where the default config can see them, or run `estate-sync` from your own scheduler with `ESTATE_CONFIG` set.

## Done when

`estate doctor` shows `sync` ok: the timer or agent is loaded and matches `estate.toml`, and the last run finished OK within 36 hours. It **fails** if the timer is not loaded, or the last run is missing, failed or older than 36 hours; it **warns** while any repo is skipped (commit, push or merge that checkout by hand).
