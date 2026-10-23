# config-sync

Keeps your agent configuration (rules files such as `CLAUDE.md` and `AGENTS.md`, harness settings, hooks, the doctrine pack) in **one git repository you own**, and installs it into the right places in `$HOME` on every machine. Every harness on every machine then sees the same configuration. Machines change configuration only by committing to that repo.

The repo is called agent-env here. It holds a `manifest.tsv` and a `home/` tree. `estate install config-sync` creates it from a starter if you do not have one, and installs the `estate-config-sync` command.

## Set up

```sh
bin/estate install config-sync --dry-run   # what it would create and install
bin/estate install config-sync             # create the checkout, install the command, apply
bin/estate doctor                          # the config-sync row should be ok
```

The first install creates the checkout at `<paths.code>/agent-env` from `starter/` (its `payload/` directory becomes the repo's `home/`), copies the doctrine pack (`doctrine/` in this repo) into its `home/doctrine/`, and makes one commit. Then **you** publish it:

```sh
git -C ~/Code/agent-env remote add origin git@github.com:<you>/agent-env.git   # a private repo
git -C ~/Code/agent-env push -u origin HEAD:main
```

The new repo also carries the guardrails module's shell-footgun hook, so every harness refuses machine-checkable shell mistakes: at creation, `init` merges `modules/guardrails/settings/claude.json` into `home/.claude/settings.json` and copies `codex-hooks.json` to `home/.codex/hooks.json` (the manifest has a `merge-json` row for each). The fragments are read from agent-estate, so they are not stored twice here, and hooks merge per command, so hooks you already have are kept. The command points at `<paths.bin>/footgun-hook` (written in `~` form). The hook only does anything once `estate install guardrails` has put `footgun-hook` there. Codex ignores an unreviewed hook: start Codex, open `/hooks` and trust it. A checkout you cloned from an existing remote is not touched; add the two rows by hand if its manifest lacks them.

Fill in `home/doctrine/house-register.md` (the "About me" blanks) and read `home/.codex/config.base.toml`: it sets Codex's `approval_policy` and `sandbox_mode`; change them to the posture you want before relying on them.

### A second machine

Put `remote = "git@github.com:<you>/agent-env.git"` under `[modules.config-sync]` in `estate.toml` (the same file on every machine) and run `estate install config-sync` there: the checkout is cloned instead of created. If the remote exists but is empty, the starter is committed into the clone for you to push. If it cannot be cloned, install fails and creates nothing; create the empty private repo first.

## Settings

Under `[modules.config-sync]` in `estate.toml`:

| Key | Default | Meaning |
|---|---|---|
| `repo` | `""` | the agent-env checkout; empty means `<paths.code>/agent-env` |
| `remote` | `""` | git URL of your agent-env repo; used only when the checkout does not exist yet |

## The manifest

`manifest.tsv`: one row per line, fields separated by a **tab**: `kind  source  dest  [platform]`. `#` starts a comment. `source` is relative to the repo root, `dest` is relative to `$HOME` (a leading `~/` is fine), `platform` is `mac`, `linux` or `all` (the default) or a comma list.

| Kind | What it does |
|---|---|
| `file` | Copies one file. The executable bit follows the source. |
| `tree` | Copies a directory. A file later removed from the source is removed from `dest` **if config-sync installed it and nobody edited it**; files it did not install are never touched. Emptied directories are pruned. |
| `merge-json` | Merges the source's keys into a JSON file the harness also writes, such as `~/.claude/settings.json`. Objects merge key by key; under `hooks`, hooks merge per command; any other list or scalar takes the source's value (so put every item you want in a list in the fragment). Keys the source does not mention stay. A missing file is created with mode 0600; one that does not parse is refused untouched. |
| `merge-toml` | The same for a simple TOML file, such as `~/.codex/config.toml`. Limit: the fragment may hold only single-line `key = value` pairs at the root or under `[table]` headers (no dotted keys, `[[array tables]]` or multi-line values). A key found in the target is replaced on its line (comments stay), a missing key is appended to its table, a missing table is appended to the file. A target value that spans several lines cannot be replaced and is refused. The merged result is parsed and checked before anything is written. |
| `link` | `dest` becomes a symlink to the source inside the checkout, for files you want live-edited in the repo. |

Two rows may not claim overlapping destinations on the same platform. Both merge kinds are additive: **neither can delete a key**, so a key removed from a fragment stays on each machine until you remove it by hand. Use `~` in settings rather than absolute paths, so one file is right on every machine.

## Nothing outside your home is touched

Before every write, chmod, delete or empty-directory prune, config-sync resolves the destination (every parent directory, so symlinks are followed) and requires the result to stay inside `$HOME`. A destination whose path runs through a symlink that points outside your home is refused with a per-row `error` (`resolves to ..., outside ...`), the other rows still run, and the apply exits nonzero. A symlink that resolves to somewhere still inside your home (for example `~/.config` kept in a dotfiles directory) may be followed. A `merge-*` row may also end at a symlink to the real file the harness owns, again only when that file is inside your home. The paths remembered in the state file for retiring files get the same check, and a link is never pruned as an empty directory.

## Local edits are never overwritten

For each file it installs, config-sync remembers the hash of what it wrote (state: `$ESTATE_STATE/config-sync/state.json`). It replaces a file only while the file still has those bytes. If the file differs, or already existed and config-sync never wrote it, that is a **local edit**: the file is kept, `apply` prints

```
local-edit  .claude/CLAUDE.md  changed since config-sync installed it; kept
    keep yours in the repo: estate-config-sync --harvest .claude/CLAUDE.md   (or delete it to take the repo's)
```

and `estate doctor` warns until it is resolved. To keep the local version, **harvest** it, then commit and push:

```sh
estate-config-sync --harvest ~/.claude/CLAUDE.md     # copies it into the agent-env checkout
git -C ~/Code/agent-env add -A && git -C ~/Code/agent-env commit -m "adopt local CLAUDE.md" && git -C ~/Code/agent-env push
```

`--harvest` takes a file, or a tree row's directory (every file under it, including new ones). It refuses merged files (edit the fragment in the repo instead) and links (edits already land in the repo). Deleting the local file instead takes the repo's version on the next apply.

Merged files are not protected this way: they are *meant* to differ from the fragment, because the harness writes its own keys into them.

## Commands

```
estate-config-sync apply [--pull] [--dry-run] [-v]    install the manifest
estate-config-sync --harvest <dest> [--dry-run]       copy a local edit back into the checkout
estate-config-sync check                              the doctor check (ok / warn / fail)
estate-config-sync init                               create or clone the checkout (install runs it)
```

`apply --dry-run` lists every change (`would install`, `would update`, `would merge`, `would remove`) and changes nothing. A second `apply` changes nothing. `--pull` runs `git pull --ff-only` in the checkout first; a failed pull warns and applies what is checked out. Global options: `--repo`, `--home`, `--state`, `--platform`; the repo location is remembered from install.

## The nightly sync

The sync module pulls your repos each night. To have it apply this config afterwards, add the command to the sync module's `hooks` list in `estate.toml`:

```toml
[modules.sync]
hooks = ["estate-config-sync apply --pull"]
```

The installed link is `<paths.bin>/estate-config-sync`; use the full path if that directory is not on the nightly job's `PATH`. `install` is idempotent whether or not you add the line: without it, run `estate-config-sync apply --pull` by hand, or `estate install config-sync`, after pulling changes.

## Check

`estate doctor` runs `check`:

- **fail** when the checkout is missing or has no valid `manifest.tsv`, config was never applied on this machine, the last apply failed, or a dry-run apply would hit an error;
- **warn** when a local edit is waiting to be harvested, changes from the repo are waiting to be applied (drift), or the checkout has uncommitted changes (a harvest not yet committed);
- **ok** otherwise.

done when: every file in the agent-env manifest is installed under your home, nothing local is waiting to be harvested, and the last apply succeeded.

## Uninstall

`estate uninstall config-sync` removes the `estate-config-sync` link only. The checkout, the installed files and the state stay; deleting those would delete your configuration.

## Notes

- Python 3.11+ standard library only. State, the lock and the remembered repo path live under `$ESTATE_STATE/config-sync/`.
- A symlinked tree-source entry is skipped with a warning. Settings values such as absolute home paths cannot be templated; use `~`.
