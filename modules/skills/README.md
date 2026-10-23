# skills

One pool of agent skills, rendered into every harness. The work is done by [skillherd](https://github.com/treygoff24/skillherd) (command `skillherd`), a standalone project that is **not vendored here**. This module installs it, seeds a pool, renders it into Claude Code and Codex (the tool's default surfaces; it also serves shared Agents, Grok, pi and Cursor folders), and checks it.

skillherd was called skill-cli (command `skill`) before its public release. Re-running `estate install skills` on a machine set up under the old name moves it over: see [Moving from skill-cli](#moving-from-skill-cli).

## What install does

1. **Clones** the tool to `<paths.code>/skillherd` (settings `repo_url`, `checkout`) unless the checkout exists. To use a clone of your own, set `checkout` to it; install then skips the clone.
2. **Installs** it with the tool's own `bash install.sh --prefix <dirname of paths.bin>`, which puts `skillherd` in `paths.bin` (Rust and Cargo are needed; `paths.bin` must end in `/bin`, as the default `~/.local/bin` does). Redone only when the checkout's HEAD moves.
3. **Writes `~/.config/skillherd/config.json`** (`library`, and `remote` if set) once; an existing file is kept. The tool's `SKILLHERD_CONFIG` and `XDG_CONFIG_HOME` are honoured. Claude Code skills go to `~/.claude/skills` unless `CLAUDE_SHARED`, the file's `claude_home` key, or `CLAUDE_CONFIG_DIR` names another root (in that order; see the tool's `docs/reference.md`), so run install from a shell with the same environment as your agents.
4. **The pool.** Its location is the setting `pool`, else `paths.skills`. **One exception:** the tool renders into `~/.agents/skills`, and refuses a library that overlaps its own output, so if the pool is set to that folder the library is `~/.agents/skill-library` instead and install says so.
   - *Plain folder* (default): if the pool holds no skills, it is **seeded by copying** this repo's starter pool `skills/` (34 skills) and the health module's `estate-health` triage skill, then every seeded skill is switched on (`skillherd on`). A pool that already has any skill in it is **never touched**, and install does not seed again. `seed = false` creates an empty pool instead.
   - *Git remote* (`pool_remote = "<url>"`): nothing is seeded; `skillherd sync` clones your skills repo into the pool (and later fast-forwards it, refusing a dirty or diverged one). Put your skills in that repo.
5. **Renders** (`skillherd render`, or `skillherd sync` for a remote pool) into the harnesses. Edit skills in the pool, never in a harness folder; rendered entries are managed symlinks, and the tool leaves foreign entries alone.
6. **Nightly update of the tool:** appends a sync row (`skillherd<TAB><checkout><TAB><estate>/bin/estate install skills`) to the repo table unless one exists (`register_sync = false` skips it).

## Nightly render

Add the tool's sync command to the sync module's hook list in `estate.toml`:

```toml
[modules.sync]
hooks = ["estate-config-sync apply --pull", "skillherd sync"]
```

`skillherd sync` re-renders a plain-folder pool and, for a git pool, fast-forwards it first. The hook runs after the repo table, so the pool is rendered after config changes land.

## Settings (`[modules.skills]`)

| Key | Default | Meaning |
|---|---|---|
| `repo_url` | `https://github.com/treygoff24/skillherd` | where the tool is cloned from |
| `checkout` | `""` (`<paths.code>/skillherd`) | the checkout; point at your own clone to skip the clone step |
| `pool` | `""` (`paths.skills`) | the skill library |
| `pool_remote` | `""` | git URL of a skills repo to use as the pool |
| `seed` | `true` | seed a new, empty pool from the starter skills |
| `register_sync` | `true` | add the nightly-update row |

## Check

`estate doctor` row `skills`: **fail** if `skillherd` is not on `PATH` or the pool folder does not exist; **warn** if `skillherd doctor` exits nonzero (findings), the nightly `skillherd sync` hook is missing from `[modules.sync] hooks`, or the hooks still list the old `skill sync`; ok otherwise.

## Done when

`skillherd list --harness claude` shows the pool's skills, `skillherd doctor` is clean, and a new Claude Code or Codex session lists them.

## Moving from skill-cli

On a machine installed before the rename, `estate install skills`:

- clones skillherd to `<paths.code>/skillherd` and installs it. The installer manages only `skillherd` and its optional `npx` shim; old `skill` and `skill-render` commands are left in place;
- copies `~/.config/skill/config.json` to `~/.config/skillherd/config.json` if the new file does not exist yet (skillherd never reads the old path);
- drops the `skill-cli` row it wrote in the sync repo table and adds a `skillherd` row.

Two steps are yours: in `estate.toml`, replace `"skill sync"` with `"skillherd sync"` in `[modules.sync] hooks` (the `skills` row warns until you do), and remove any `repo_url` or `checkout` under `[modules.skills]` that still names skill-cli. Environment variables were renamed too, with no fallback: `SKILL_*` is now `SKILLHERD_*` (`SKILL_RENDER_PLATFORM` is `SKILLHERD_PLATFORM`). Inspect any old `skill` and `skill-render` commands before retiring them: `skill` may belong to another program. The old checkout `<paths.code>/skill-cli` is no longer used; keep it until you have verified the new install and no command still points into it.
