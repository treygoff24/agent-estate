# Doctrine pack

Instruction files and rules that make coding agents behave well on this setup. You copy them
into your harness's instruction layer; a later agent-estate module will install them for you.
They were extracted from a working multi-machine setup and de-personalized: every rule keeps its
reason, and the incident stories behind the rules are kept with names and hosts removed.

## What is here

| File | What it is | Where it goes |
| --- | --- | --- |
| `agent-operating-contract.md` | Task and authority, verification, communication, continuity, action boundaries. The one document every harness points at. | Claude Code: `~/.claude/rules/`. Codex: read from `<doctrine-dir>` (the AGENTS.md template says so). |
| `shell-footguns.md` | Core shell, git, process and test rules, each with its reason. macOS and Linux. | Claude Code: `~/.claude/rules/`. Codex: read from `<doctrine-dir>`. |
| `shell-footguns-catalog.md` | The long tail of tool-specific rules (rg, sed, perl, zsh, pnpm, launchctl, Docker, ...). | `<doctrine-dir>`, read on demand. |
| `shell-footguns-lore.md` | The incident behind each rule. Read before weakening one; append new stories. | `<doctrine-dir>`, read on demand. |
| `build-doctrine.md` | How to run multi-agent builds: coordinator and lanes, briefs, review, tests, gates. | `<doctrine-dir>`, read before delegating. |
| `no-ceremony.md` | Stance against process for its own sake, plus the honest-reporting rules. | `<doctrine-dir>`; the templates tell every session to read it. |
| `templates/CLAUDE.md` | Fill-in global instructions. | `~/.claude/CLAUDE.md` |
| `templates/AGENTS.md` | Fill-in global instructions for Codex. | `~/.codex/AGENTS.md` |
| `templates/house-register.md` | Fill-in "how to talk to me". | `<doctrine-dir>/house-register.md` |

`<doctrine-dir>` is where the longer reference files live. The default is
`~/.config/agent-estate/doctrine`. Templates and rules refer to it by that placeholder or by bare
filename, so pick one place on each machine and use it consistently.

The shell rules were merged from a Mac set and a Linux set, so one copy serves both. Rules that
only made sense inside private tooling (a shell-guard hook, launchers, internal orchestration
CLIs) were dropped; `shell-footguns.md` says so at the top. The build doctrine
omits dated rulings, experiment arms and internal references. If your harness installs a
pre-tool hook that denies machine-checkable shell mistakes, it enforces roughly the first half
of the shell rules at call time.

## Install by hand

Run on each machine (Mac and every Linux box) from the repo root. Re-running refreshes the
reference files; the three templates are never overwritten if they already exist.

```bash
DOC="$HOME/.config/agent-estate/doctrine"
mkdir -p "$DOC" "$HOME/.claude/rules" "$HOME/.codex"

# 1. Reference files, read on demand
cp doctrine/agent-operating-contract.md doctrine/shell-footguns.md \
   doctrine/shell-footguns-catalog.md doctrine/shell-footguns-lore.md \
   doctrine/build-doctrine.md doctrine/no-ceremony.md "$DOC/"

# 2. Claude Code loads ~/.claude/rules/*.md on its own
cp doctrine/agent-operating-contract.md doctrine/shell-footguns.md "$HOME/.claude/rules/"

# 3. Templates: substitute the doctrine path; fill the remaining slots by hand (see below)
test -e "$HOME/.claude/CLAUDE.md" && echo "CLAUDE.md exists: merge by hand" \
  || sed "s|<doctrine-dir>|$DOC|g" doctrine/templates/CLAUDE.md > "$HOME/.claude/CLAUDE.md"
test -e "$HOME/.codex/AGENTS.md" && echo "AGENTS.md exists: merge by hand" \
  || sed "s|<doctrine-dir>|$DOC|g" doctrine/templates/AGENTS.md > "$HOME/.codex/AGENTS.md"
test -e "$DOC/house-register.md" && echo "register exists" \
  || sed "s|<doctrine-dir>|$DOC|g" doctrine/templates/house-register.md > "$DOC/house-register.md"
```

Check the result: `test -f "$DOC/build-doctrine.md"`, and open `~/.claude/CLAUDE.md` to confirm
no `<doctrine-dir>` is left. If you already have a global `CLAUDE.md` or `AGENTS.md`, merge the
sections you want instead of replacing it.

To keep machines in step, put the repo's `doctrine/` through the same git-based sync as the rest
of your config, and re-run the copies after you change it. Copies installed elsewhere are not
updated for you.

## Customize first

1. **`house-register.md`.** Fill the "About me" blanks. This changes every reply you get.
2. **`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`.** Replace each `<angle-bracket>` slot: your
   name, your machines, your git-remotes rule, your escalation channel. Delete the optional
   blocks (dictation, tracker, escalation) you do not want. Keep these files short; they load on
   every turn.
3. **Git-remotes rule.** The default is: local commits and pushes to your own private origin are
   ungated; public remotes, PRs, tags, releases and deploys need fresh authorization; never
   amend, force-push, or bypass hooks. Change it if your policy differs. The operating contract
   points at it.
4. **Work tracker.** The templates mention `bd` (beads). If you use something else, replace the
   section; if nothing, delete it.
5. **Add your own rakes.** When an agent hits a new footgun, add the story to
   `shell-footguns-lore.md` and the rule to `shell-footguns.md` (or the catalog if it is
   tool-specific).

## Notes

- Instruction files are context, not enforced config. Settings and hooks enforce; these files
  guide. Claude Code concatenates every `CLAUDE.md` it discovers (project files win on
  conflict), and loads `~/.claude/rules/*.md` before project rules.
- Nothing here names a person, host or account. If you fork and add any, keep them out of any
  copy you publish.
