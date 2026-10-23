# agent-estate

Run coding agents on a Mac and one or more Linux boxes (usually a rented VPS) as one system. Your agents get the same config and tools on every machine, stay inside test-load limits, and tell you when something is wrong.

It is for a developer who already uses a coding agent (Claude Code, Codex, Pi or another harness) and wants several of them working across machines without babysitting each box. You can point your own agent at this repo for a guided setup, or follow [INSTALL.md](INSTALL.md) yourself. Each step ends with a check you can run.

**Status: working, still growing.** The core modules below are built and tested, and `INSTALL.md` takes an agent from a clean Mac and a clean Debian/Ubuntu box to a green `estate doctor`.

## What is in it

Each core module in `modules/` has an install script and a doctor check.

| Module | What it does |
|---|---|
| `baseline` | A VPS made safe for agents: a login with no sudo, Tailscale, a firewall with automatic rollback, security updates, optional restic backups. |
| `sync` | Nightly: pull your repos through git, then run hooks. |
| `config-sync` | Rules, hooks and settings for every harness (Claude Code, Codex, ...) kept in one private git repo and installed on every machine. |
| `keys` | One 0600 key file; keys reach only the tools you name. |
| `usage` | Claude and Codex rate-limit usage in one snapshot. |
| `guardrails` | `testrun` (caps and time limits for heavy commands), optional compile slots, a shell-footgun hook. |
| `health` | Hourly read-only report: disk, memory, failed units, doctor, runaway processes. |
| `cleanup`, `tmp-cleanup` | Age-gated sweeps of old worktrees, build caches, logs and `/tmp` scratch. |
| `show` | Publish a file or dev port as a tailnet-only link with a time limit (Linux). |
| `post` | Agent-to-agent mail between every agent on every machine, with harness hooks and an optional cross-machine bridge. |
| `skills` | One skills pool, seeded with the starter skills, rendered into Claude Code and Codex and synced nightly. |

The [add-on catalog](addons/README.md) links to standalone public tools with
install notes. Field guides in `guides/` cover optional machinery: a self-hosted
Git forge, containers per agent, ZFS snapshots and egress policies. The rules
files in `doctrine/` guide agent behavior; `config-sync` installs them.

## Principles

Config, skills and state move between machines through Git. Agents run as
ordinary users without sudo; the person runs any root commands. Their machine
names, accounts and settings live in `estate.toml`, starting from
`estate.example.toml`. The doctor checks every enabled module and says what
still needs work; setup is complete when every machine is green.

## Quick start

Clone this repository on your Mac as `~/Code/agent-estate`. Keep that checkout in place: installed commands and timers refer to it. Start your coding agent in the checkout and say:

> Read INSTALL.md and set me up.

The agent asks you for the few values `estate.toml` needs and installs the modules you choose. To inspect the kit yourself:

```sh
bin/estate --help
bin/estate list                 # modules and their state
bin/estate config check         # validate ~/.config/agent-estate/estate.toml
bin/estate doctor               # is this machine set up?
```

Needs Python 3.11 or newer (standard library only) and git, on macOS (Apple silicon) or Debian 12+ / Ubuntu 24.04+.

## Troubleshooting and maintenance

Start with `bin/estate doctor`. It checks the modules enabled in your config,
prints what failed, and gives a completion check for each row. Exit 0 means
healthy, 2 means warnings remain, and 1 means a failure. The
[repair table](INSTALL.md#7-verify) covers missing commands, authentication,
permissions, stale installs and stopped timers.

After changing `estate.toml`, run `bin/estate config check`, then
`bin/estate install --dry-run` to preview the changes. Apply them with
`bin/estate install` and run the doctor again. To update the kit, pull the
checkout with `git pull --ff-only`, reinstall, and check each machine.
[Keeping it running](INSTALL.md#9-keeping-it-running) covers adding machines,
config backups and uninstalling modules without losing their data.

## Limits

The supported setup is an Apple silicon Mac and Debian 12+ or Ubuntu 24.04+
with systemd. Windows and other Linux distributions are not verified. The
kit configures existing coding agents; you install and sign in to each
agent separately. Root setup and firewall confirmation require the person
operating the Linux box.

Timers read `~/.config/agent-estate/estate.toml`; keep the config there even
though interactive commands accept `ESTATE_CONFIG`. Optional mail delivery
between machines needs a separate private Git relay; local mail works
without it. Review the cleanup module's dry run before relying on its
scheduled deletions.

## License

MIT. See `LICENSE`.
