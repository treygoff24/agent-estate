# Global Codex instructions

Keep this machine-wide layer small; durable project guidance belongs in each repository's own
`AGENTS.md`. The current human request sets the task.

This file is installed on every machine by config-sync from the person's agent-env repo. Edit it
in that repo (`home/.codex/AGENTS.md`), commit and push; edits made only in `~/.codex/` never
reach the other machines.

Codex has no rules directory that loads by itself, so at session start read these, from
`~/.config/agent-estate/doctrine/`:

- `house-register.md`: how to talk to the person. It applies to every reply.
- `agent-operating-contract.md`: task and authority, verification, communication, continuity.
- `shell-footguns.md`: shell, git, process and test rules, each with its reason.
- `no-ceremony.md`.

`shell-footguns-catalog.md`, `shell-footguns-lore.md` and `build-doctrine.md` in the same
directory are read on demand.

## Git

- Commits and pushes to the person's own private `origin` are fine at coherent checkpoints.
  Pushes to public remotes, PRs, tags, releases and deploys need fresh authorization.
- Never amend, force-push, or bypass hooks. Stage files by name.
