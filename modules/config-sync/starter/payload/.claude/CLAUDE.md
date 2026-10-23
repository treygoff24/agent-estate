# Global Claude instructions

The current human request sets the task. A project's own `CLAUDE.md` overrides this file within
the instruction hierarchy.

This file is installed on every machine by config-sync from the person's agent-env repo. Edit it
in that repo (`home/.claude/CLAUDE.md`), commit and push; edits made only in `~/.claude/` are kept
locally but never reach the other machines, and config-sync reports them until they are harvested.

## Shared rules

- `~/.claude/rules/` holds the operating contract and the shell rules; Claude Code loads them on
  its own. Read them if your session did not.
- Longer references live in `~/.config/agent-estate/doctrine/` and are read on demand:
  `shell-footguns-catalog.md` (tool-specific rules), `shell-footguns-lore.md` (the incident behind
  each rule), `build-doctrine.md` (multi-agent builds), `no-ceremony.md`. Read `no-ceremony.md`
  and `house-register.md` there at the start of a session; both bind every reply.

## Machines

<!-- One line per machine so agents know where heavy work belongs. Delete this comment. -->
- `mac`: the interactive laptop; light work, review, browser.
- `vps`: the Linux box; builds, test runs, long jobs, anything unattended.

## Git

- Commits and pushes to the person's own private `origin` are fine at coherent checkpoints.
  Pushes to public remotes, PRs, tags, releases and deploys need fresh authorization.
- Never amend, force-push, or bypass hooks. Stage files by name.
