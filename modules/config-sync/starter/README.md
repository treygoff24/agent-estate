# agent-env

Your agent configuration, in one git repo. `config-sync` (from agent-estate) installs it into
`$HOME` on every machine, so every harness on every machine sees the same rules and settings.
Machines change configuration only by committing here.

```
manifest.tsv     what goes where
home/            the files the manifest points at
home/doctrine/   the doctrine pack (copied from agent-estate when this repo was created); yours now
```

## manifest.tsv

One row per line, fields separated by a TAB: `kind  source  dest  [platform]`. `source` is a path
in this repo, `dest` a path under `$HOME`, `platform` is `mac`, `linux` or `all` (the default).

| kind | does |
|---|---|
| `file` | copies one file |
| `tree` | copies a directory; a file you later delete here is deleted from `dest` too, but only if config-sync installed it and nobody edited it |
| `merge-json` | merges the keys in the source into a JSON file the harness also writes (`~/.claude/settings.json`); other keys stay |
| `merge-toml` | the same for a simple TOML file (`~/.codex/config.toml`); other keys stay |
| `link` | makes `dest` a symlink to the source inside this checkout |

Merges own the keys they name and never remove a key: delete a key from the fragment and each
machine keeps its last copy until you remove it by hand. A list inside a fragment replaces the
machine's list, so put every item you want in it.

## Working with it

- Change configuration **here**: edit, commit, push. The nightly sync pulls and applies it; to
  apply right now run `estate-config-sync apply --pull`.
- `estate-config-sync apply --dry-run` lists every change without making any.
- config-sync never overwrites a file that differs from what it last installed. If you edited
  `~/.claude/CLAUDE.md` in place, it reports `local-edit`; keep your version with
  `estate-config-sync --harvest ~/.claude/CLAUDE.md`, then commit and push. The same applies to a
  file that already existed on a machine before the first apply.
- `home/doctrine/house-register.md` has blanks under "About me": fill them in. It changes every
  reply you get.
- The footgun hook from agent-estate's guardrails module is already wired in: it sits in
  `home/.claude/settings.json` and `home/.codex/hooks.json`. Codex needs you to trust it once
  (`/hooks` inside Codex).
- The Codex fragment sets `approval_policy` and `sandbox_mode`. Change them in
  `home/.codex/config.base.toml` if you want a different posture.
