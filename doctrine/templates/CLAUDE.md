<!--
Template for ~/.claude/CLAUDE.md (your global Claude Code instructions).
Fill every <angle-bracket> slot, delete the comments and any section you do not want, and keep
the result short: every line here is loaded on every turn. Per-project CLAUDE.md files override
these globals. See doctrine/README.md for where the referenced files get installed.
-->
# Global Claude instructions

The current human request sets the task. Per-project `CLAUDE.md` overrides these globals within
the instruction hierarchy; loaded rules files govern their topics. `~/.claude/rules/` holds the
operating contract and the shell rules (loaded automatically; read them if your harness did not
load them). Longer references and incident stories live in `<doctrine-dir>` and are read on
demand; a bare filename in those rules (`build-doctrine.md`, `shell-footguns-catalog.md`) means
the file of that name there.

`<your-name>` reads agent output all day. Follow `<doctrine-dir>/house-register.md` for every
reply and deliverable addressed to them. Read `<doctrine-dir>/no-ceremony.md` too; both bind
every session.

<!-- Optional: dictation. Delete if you type. -->
`<your-name>` dictates: resolve obvious speech-to-text homophones by intent, without nitpicking.

<!-- Optional: how you want things handed to you. -->
For anything `<your-name>` will copy into another app, put a plainly named file in the relevant
project tree and open it. Show the content in chat when review is the point.

## Machines

<!-- One line per machine so agents know where heavy work belongs. -->
- `mac`: <interactive laptop; light work, review, browser>
- `vps`: <Linux box; builds, test runs, long jobs, anything unattended>

## Git remotes and pushes

<!-- Replace with your own rule. This default matches the operating contract. -->
- `origin` is `<your private git host>`. Commits and pushes to `origin` are ungated at coherent
  checkpoints.
- Pushes to any public remote, PRs, tags, releases and deploys need fresh explicit authorization,
  every time.
- Never amend, force-push, or bypass hooks (`--no-verify`). Stage files by name.

## Escalation

<!-- Only if you want to be pinged. Delete otherwise. -->
When a blocking, time-sensitive decision only `<your-name>` can make comes up, ask through
`<your channel, e.g. a push-notification CLI>`: one question, options inline, no secrets. Never
for progress updates.

## Disclosed branches

Read the file before doing the thing in the left column.

| Before | Read or apply |
| --- | --- |
| Delegating work or running a multi-agent build | `<doctrine-dir>/build-doctrine.md` |
| Shell-heavy work, rg/sed/perl/Python/zsh, test runners, systemd/launchctl, Docker, keychains | `<doctrine-dir>/shell-footguns-catalog.md` (and `shell-footguns-lore.md` before weakening a rule) |
| Creating a checklist, tracker, report or check nobody asked for | `<doctrine-dir>/no-ceremony.md` |
| <your topic, e.g. browser automation> | <path or skill> |

## Commit messages

Subject at most 72 characters, a blank line, then whole sentences, soft-wrapped (never
hard-wrapped; UIs reflow). About 15 to 20 lines at most; review context belongs in the PR
description, and bullets only for genuine lists. A code commit's body states the verification that
ran and its count ("unit and integration suites 72/72, typecheck clean"; "red-proofed against the old
component"), so a reviewer can trust the commit without re-running it.

## Work ledger

<!-- Optional. Delete if you do not use a tracker. Beads (`bd`) is one option. -->
In a repo with `.beads/`, run `bd ready` on arrival and `bd prime` for commands. Create a bead
before substantial project work; claim it (`bd update <id> --claim`) before working it, one claim
at a time per session, and close it with a reason that states the evidence. The tracker is the
work graph; journals, state files and memory remain narrative context.
