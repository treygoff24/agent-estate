# post

Agent-to-agent mail: agents on any machine, in any harness, send each other direct mail and group-channel messages, and get told when something arrives. The mailbox tool is [post](https://github.com/treygoff24/post), a standalone project that is **not vendored here**. This module installs it, wires its mail hook into each harness you use, and (optionally) its cross-machine bridge, then checks that it works.

## What install does

Use Post 0.11.x for this setup. Earlier public releases lack the Pi hook and
macOS bridge installer. Keep the Post checkout and installed binary on the
same release when upgrading.

1. **Clones** the tool to `<paths.code>/post` (setting `repo_url`, `checkout`). An existing checkout is left alone.
2. **Installs the `post` binary** (setting `install_method`): `auto` downloads the release installer from the repo's releases page (`--no-modify-path`, so your shell profiles are untouched) and, if that fails or the platform has no release, builds from the checkout with `cargo install --locked --path <checkout> --bin post` into the state directory and links it into `paths.bin`. `release` and `source` pick one. Building needs Rust (https://rustup.rs). It is redone only when the checkout's HEAD moves or the binary is gone.
3. **First-run setup:** `post doctor --fix --brief` (creates the mail root `~/.claude-mail/` and empty defaults; safe to repeat).
4. **Hooks** (setting `hooks`, default on) for each harness with a `[harnesses.<name>]` table in `estate.toml`: `claude`, `codex`, `pi`, `cursor`, `grok`. These are post's own installers (`skills/post/hooks/install-*-hooks.mjs`), which need Node.js, merge into the harness config without touching other hooks, and are idempotent. We use them rather than a config-sync fragment because the adapter is copied to a per-harness folder and registered with an absolute path that the installer fills in for the machine. config-sync keeps unrelated hooks when it merges, so the two coexist. Codex asks you to approve the hook once (`/hooks`). Without Node.js the module says so and skips the hooks; mail still works from the command line.
5. **Bridge** (off; see below).
6. **Nightly update:** appends a row to the sync repo table (`modules.sync.repos_file`) unless one named `post` is there:

   ```
   post	<checkout>	<estate>/bin/estate install post
   ```

   The nightly sync fast-forwards the checkout and, when HEAD moved, re-runs this module's install, which rebuilds the binary. Turn off with `register_sync = false`. The sync module must be enabled for the row to do anything.

Run it with `estate install post` (`--dry-run` first if you like). Idempotent.

## Settings (`[modules.post]`)

| Key | Default | Meaning |
|---|---|---|
| `repo_url` | `https://github.com/treygoff24/post` | where the tool is cloned from |
| `checkout` | `""` (`<paths.code>/post`) | the checkout |
| `install_method` | `auto` | `auto`, `release` or `source` |
| `hooks` | `true` | install the mail hook for each harness listed under `[harnesses.*]` |
| `register_sync` | `true` | add the nightly-update row |
| `bridge` | `false` | relay mail between your machines |
| `relay_url` | `""` | the relay repo's git URL (required with `bridge = true`) |
| `ssh_key` | `~/.ssh/post-relay` | this machine's relay key |
| `bridge_interval` | `""` | bridge tick; `""` is the bridge's default (15 s Linux, 60 s Mac) |

## The bridge (optional, off by default)

Local mail needs no server. The bridge carries mail between your machines through **one private git repo** used as a queue, with one branch per machine. Relay operators can read mail, and the git server must stop each machine's key from writing any branch but its own: a private repo alone is not that, so check your host's branch protections (the tool's `bridge/README.md` spells out the requirements; a host without per-branch write controls is not a safe relay). Only enable it if you want agents on the Mac and the VPS to mail each other.

You do the provisioning, once (the module never creates a repo or a key):

1. Create the private relay repo. Create an orphan `registry` branch holding `hosts.json`: `{"v":1,"hosts":["mac","vps"]}` listing **every machine name from `[[machines]]`** (install prints the exact JSON). Machine names must be lowercase letters, digits and dashes, at most 32 characters.
2. Make an SSH key per machine at the `ssh_key` path (mode 0600), register its public half on the relay with write access to that machine's `machines/<name>` branch only, and verify the server's host key through a trusted channel (never disable host-key checking).
3. Set `bridge = true` and `relay_url = "ssh://git@git.example.com/you/post-relay.git"` under `[modules.post]` on every machine and run `estate install post`. The module writes a bridge config (`channels: null`, so channel text stays local) naming this machine (`ESTATE_MACHINE`, else the `[[machines]]` entry that matches the hostname) and runs the tool's `bridge/install.sh`, which installs a systemd **user** timer (Linux) or a launchd agent (Mac); no root.
4. Register differently named workspaces on each machine (`post rooms add builder-mac ...`, `builder-vps`), then follow the two-host smoke test in the tool's `bridge/README.md`.

## Check

`estate doctor` row `post`: **fail** if `post` is not on `PATH`, `post doctor` crashes (exit other than 0 or 1), or, with the bridge on, its timer or agent is not loaded; **warn** if `post doctor` has findings (exit 1) or the mail hook is missing for a listed harness; ok otherwise.

## Done when

`post --version` works, `post doctor` is clean, a new session in each listed harness shows the mail notice when mail is waiting, and (bridge on) `post rooms` lists the other machine's workspaces after both bridges have ticked.
