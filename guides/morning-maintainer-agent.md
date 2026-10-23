# Morning maintainer agent

A scheduled agent that wakes before you do, checks that your machines are healthy, repairs the nightly syncs, updates your agent CLIs and tools (with a backup, a smoke check and a rollback each), removes stale worktrees, and leaves you one short summary. It runs on a timer, starts a headless session of whatever harness you use with a runbook as its brief, and has a real off switch.

## Do you need this?

**Skip it** if you have one machine, you update tools by hand now and then, and nothing has ever rotted while you were away. A weekly manual `doctor` run and a calendar reminder cost less.

**Do it** if you have a Mac plus a Linux box (or several), update more than a handful of agent tools, and have noticed any of: tools drifting out of version between machines, a failed nightly sync that nobody saw for days, stale worktrees and backup folders piling up, or "I forgot to update that and it broke on the other machine".

**Cost:** one scheduled headless agent session per day (a few tens of minutes of one subscription window or some API spend, more on the day many updates land), a runbook you maintain, and trust: the agent will upgrade software and delete old worktrees unattended. That trust is bounded by the authority list in step 3. If you are not ready to grant it, run the same runbook by hand each morning for two weeks first.

## Prerequisites

- agent-estate's `sync` (nightly), `health` and `cleanup` modules, `estate doctor`, and the worktree census (the `cleanup` module's report, or `guides/disk-hygiene.md`'s census script).
- A scheduler: launchd on the Mac, a systemd **user** timer on Linux (`loginctl enable-linger <you>` so user timers run when you are logged out).
- A headless way to start your harness with a prompt: Claude Code (`claude -p "<prompt>"`), Codex (`codex exec "<prompt>"`), or any other that takes a prompt non-interactively. Check `<harness> --help` for the permission flag your unattended mode needs. The agent must be allowed to run shell commands without prompting; scope that by running it as your normal user, not root.
- Somewhere to post the summary: a file always; optionally a chat channel, mail, or a webhook.
- Human: sign the harness in on each machine, and decide the authority list (step 3).

## Steps

### 1. Write the charter as outcomes, not a checklist

Give the agent a short standing charter of outcomes it keeps true. A checklist invites the agent to tick boxes; outcomes make it notice and handle what the list missed. A checklist version keeps missing things (for example, a whole class of self-updating CLIs on the Mac that no step named can sit minor versions behind the Linux box until someone notices). The runbook stays as *its* checklist, and the agent adds a runbook step when an outcome needs one.

Put this in the agent's standing instructions (the file your harness reads at start: `CLAUDE.md`, `AGENTS.md`, or the brief itself), adapted:

```markdown
You keep my machines healthy, their tooling current and working, and my agent
spend legible. At each morning run, check these outcomes before reading any
task; at any other wake, read your last summary instead of rechecking.

1. Every machine is healthy: every health line is ok, fixed (said in the
   summary), expected and explained, or on my list (the issues labelled
   needs-me).
2. Every machine runs current, working tooling: skills and config synced, the
   agent CLIs and the tools the setup's scripts call, and the nightly syncs ran
   clean. "Current" means current, or held with the reason in the summary (a
   login, a release that breaks). An upgrade that breaks is rolled back and
   reported, never left half-applied.
3. Spend is legible: every usage source has an observation from the last day,
   or the reason it does not is recorded. Logins are mine, never fixed here.
4. Nothing accumulates: stale worktrees, old backups, failed units, orphan temp
   files. Containers and daemons are reported with their age; stopping them is
   mine unless the runbook names it yours.
5. (Mondays only) The setup knows what it is missing: read the release notes of
   the installed agent CLIs and anything the week's runs tripped on; each thing
   worth my time becomes one ticket. "None" is a fine answer.

The runbook is your checklist, not your charter. Each run ends with one
summary that opens with which outcomes held.
```

**Done when:** the charter is in the agent's standing instructions and every outcome can be answered yes/no by a command or file the agent can read.

### 2. Write the runbook (the brief the timer hands over)

Save `~/.config/agent-estate/morning-runbook.md` (or in the repo under `docs/`). Keep it a short ordered list; each item names its command and what "ok" looks like. Order that worked:

1. **Prune old backups** under `~/.local/state/morning-run/backups/` older than one day (otherwise they stack up nightly), plus `brew cleanup --prune=1` on the Mac. Delete only inside that folder.
2. **Health:** run `doctor` (and your box health command over ssh for each Linux machine); read every non-ok line against its playbook.
3. **Syncs:** read last night's nightly sync on each machine (`estate-sync --status` prints the verdict; the log is `~/.local/state/agent-estate/sync/sync.log`, and on Linux `journalctl --user -u <sync-unit> -n 100`). Fix failed hooks, stale paths and failed units (`systemctl --user reset-failed` after the fix). A repair to a tracked file goes on a branch and is named in the summary, never pushed to main.
4. **Updates**, Mac side first, then each Linux machine, each with the backup/check/rollback rule below. Order within a machine: package-manager formulae, then command-line casks one at a time, then global npm/uv/cargo/bun tools, then each agent CLI by its own update command (call them by absolute path, since shims may wrap them).
5. **Stale worktrees** (`guides/disk-hygiene.md`, steps 1 to 3: use its census script, its salvage step and the same removal gates).
6. **Spend:** summarise usage; compare with yesterday's summary file for jumps; a login that expired is reported, not fixed.
7. **Ack the health report** only after reading every line.
8. **Write the summary** and post it, then stop.

**Done when:** a dry read of the runbook by a fresh session produces a plan with no step that asks "which command?".

### 3. Decide the authority list, and write it into the runbook

Split into *standing* (do without asking) and *the human's* (report, do not act):

- **Standing:** updates and their rollbacks; repairs to syncs and scripts; `reset-failed` and restarting a failed service after fixing its cause; killing a process the health playbook calls an orphan (record pid and owner in the summary); removing a worktree that is **all** of: older than one day, `git status` clean including untracked files, its branch merged or pushed to a remote, and with no process whose cwd is inside it. Anything failing a test is listed, never removed.
- **The human's:** rebooting a host; OS-level package upgrades that need a reboot; closing terminal panes or stopping services someone may be using; anything that needs a login or approval (a macOS Gatekeeper approval, a re-auth); pushes to remotes; deleting anything not named above; updating the harness the maintainer itself runs inside (it reports that an update exists).

**Done when:** the runbook has both lists, and your first dry run did nothing outside the first list.

### 4. Backup, smoke-check, roll back (the update rule)

Before changing a tool, record how to put it back, under `~/.local/state/morning-run/backups/<YYYY-MM-DD>/` on the machine where it lives: version manifests (`brew list --versions`, `npm ls -g --depth=0`, `uv tool list`, each CLI's `--version`), a copy of any config file the update may rewrite, and git HEADs for anything installed from git. Run Homebrew with `HOMEBREW_NO_INSTALL_CLEANUP=1` so the old keg stays for rollback.

After each update, run a smoke check that proves the tool *works*, not just that it installed: `--version` plus one real no-cost command (for example `<agent-cli> --version` and one read-only subcommand). If it fails, roll back to the recorded version, run the check again, and report. Never leave a tool broken to report that it is broken.

Rules from the incidents below, to put in the runbook:

- Upgrade casks one at a time, under a time limit, with stdin from `/dev/null`, then run the new binary the same way (`<bin> --version </dev/null`, killed after 10 seconds).
- Upgrade only command-line casks. App casks that update themselves are left alone; swapping an app someone is using is not a morning fix.
- `npm install -g` is all-or-nothing; if one package fails to build the batch rolls back. Drop that package and re-run. Skip `npm` itself when Homebrew node owns it, and skip any global that `npm ls -g` shows as a link to a local checkout.
- Judge a health command by its meaningful checks when it exits non-zero for a known benign notice; filter those out (with `jq`) instead of rolling back on every exit code.
- Before updating anything that tracks a branch rather than tagged releases, check the target is *newer* than what runs (`git merge-base --is-ancestor <running base> <target>`). A stable tag can sit on a release branch cut days before the running build.

**Done when:** you can break a test tool on purpose (make its smoke check fail), run the update path, and see the rollback restore it and the summary say so.

### 5. Write the driver: timer → headless session

The driver must not depend on one harness. It is a small script that (a) checks the off switch, (b) starts a headless session with the runbook as the brief, (c) logs.

`~/.local/bin/morning-run` (shape; adapt the `HARNESS_CMD` line):

```bash
#!/usr/bin/env bash
set -euo pipefail
STATE="$HOME/.local/state/morning-run"; mkdir -p "$STATE/logs"
LOG="$STATE/logs/$(date +%F).log"
# Real off switch: any of these stops the run before a session starts.
[ -e "$STATE/OFF" ] && { echo "$(date '+%F %T') off switch present; skipping" >>"$LOG"; exit 0; }
RUNBOOK="$HOME/.config/agent-estate/morning-runbook.md"
# One harness per machine. Examples (check your harness's current flags):
#   claude -p "$PROMPT" --permission-mode <mode-that-allows-your-runbook>
#   codex exec "$PROMPT"
HARNESS_CMD=${MORNING_HARNESS_CMD:?set MORNING_HARNESS_CMD, e.g. claude -p}
PROMPT="Morning run for $(date +%F). Follow $RUNBOOK from the top; keep the charter's outcomes true; finish with the summary."
echo "$(date '+%F %T') run start" >>"$LOG"
# Hard wall-clock cap so a wedged session cannot run all day.
timeout 3h $HARNESS_CMD "$PROMPT" </dev/null >>"$LOG" 2>&1 || echo "rc=$?" >>"$LOG"
echo "$(date '+%F %T') run end" >>"$LOG"
```

Subcommands worth adding: `off` (`touch "$STATE/OFF"`), `on` (remove it), `status` (is the timer loaded, tail of the last log), `run` (run now). Keep `on/off/status/run` as the only interface, so travelling means one command.

**macOS (launchd)**, `~/Library/LaunchAgents/<you>.morning-run.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string><you>.morning-run</string>
  <key>ProgramArguments</key><array><string><ABSOLUTE-HOME>/.local/bin/morning-run</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:<ABSOLUTE-HOME>/.local/bin</string>
    <key>HOME</key><string><ABSOLUTE-HOME></string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>5</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><false/>
</dict></plist>
```

(Replace `<ABSOLUTE-HOME>` with your real absolute home directory; launchd does not expand `~` or `$HOME`.) Load it with `launchctl bootstrap gui/$(id -u) <plist>`. Hard off: `launchctl bootout gui/$(id -u)/<you>.morning-run && launchctl disable gui/$(id -u)/<you>.morning-run`; back on: `launchctl enable ...` then `bootstrap` again.

**Linux (systemd user timer):**

```ini
# ~/.config/systemd/user/morning-run.service
[Service]
Type=oneshot
ExecStart=%h/.local/bin/morning-run
# ~/.config/systemd/user/morning-run.timer
[Timer]
OnCalendar=*-*-* 05:00:00
Persistent=false
[Install]
WantedBy=timers.target
```

`systemctl --user enable --now morning-run.timer`. Off: `systemctl --user disable --now morning-run.timer`.

Run one machine as the lead (the Mac, if you have one): it starts the session and the session reaches the Linux machines over ssh. Don't give every machine its own agent running the same runbook; two agents repairing the same sync at once is worse than one agent doing it over ssh.

**Done when:** `morning-run status` reports the timer loaded; `morning-run run` produces a log with a summary; `touch ~/.local/state/morning-run/OFF` makes the next scheduled run skip, with a log line saying why.

### 6. The summary

Always write `~/.local/state/morning-run/summaries/<YYYY-MM-DD>.md`, and post the same text where you will see it (chat channel, email or notification). First line is the verdict: "all clean", or the one thing that needs you. Then one line each: what was fixed, updated (old → new), rolled back and why, worktrees removed, worktrees kept (with the reason), and anything waiting on you. No internal ticket numbers or jargon. Open with which of the five outcomes held.

**Done when:** the summary file exists after every run, including runs where nothing changed.

## What bit us (papercuts)

- **A checklist agent missed whole classes of tools.** The Mac's own agent-CLI updaters (bun globals and self-updating CLIs in `~/.local/bin`) were absent from the list, and one tool sat several minor versions behind the Linux box for days. → Charter as outcomes, and (a suggestion, untested here) an occasional "list every installed CLI and say how it updates" sweep.
- **The scheduled wake raced the session start.** The timer started the session and sent its message a fraction of a second later; the message was lost and the agent idled out. → After starting, wait about 30 seconds before sending anything, or better, pass the brief on the command line so there is nothing to race.
- **A sleeping agent that any channel post re-wakes can loop.** If you pause the maintainer by putting it to sleep, the next post to a team channel can wake it and it re-sends the same ask to the human. Sleeping is not an off switch. → Turn it off at the source: disable the timer, remove or flag the agent so no wake path works (for example a `retired: true` field the wake path refuses), and make an agent that is woken unexpectedly check the OFF file first and exit. Drain any pending posts to that channel when you switch it off.
- **Gatekeeper hang on a freshly downloaded command-line cask.** macOS refused new binaries (quarantine flag `0181` vs `01c1` on approved ones); both the binary and Homebrew's own completion step hung. → Time-limit every cask upgrade, run `<bin> --version </dev/null` afterwards, roll back by hand if it hangs (rename `Caskroom/<cask>/<old>.upgrading` and its `.metadata` back to `<old>`, repoint the `bin` symlink, move the new folders into the backup dir). Never strip the quarantine flag: approving a binary is the human's call.
- **`brew upgrade --cask` on an app that updates itself installed an older build over a newer one**, and the older build could not read the newer's state database; its worker crash-looped. → For apps with their own updater, read the real version from `Info.plist` (`defaults read /Applications/<App>.app/Contents/Info.plist CFBundleShortVersionString`), and never `brew upgrade` them.
- **"Newer" by tag is not newer.** A stable release tag was cut days before the running (branch-tracking) build and lacked more than a thousand of its commits; the update would have run a schema "migration" backwards and had to be rolled back from a cold copy. → `merge-base --is-ancestor` check before updating anything that tracks main.
- **A health command's exit code rolled back good updates.** It exited 1 for harmless legacy notices. → Judge by named checks, not exit status.
- **Backups stacked nightly.** → Delete backup folders older than one day at the *start* of each run.
- **Mac `lsof` is not on a restricted job's PATH**, so the worktree census saw no occupied directories. → Call `/usr/sbin/lsof` by absolute path; on Linux read `readlink /proc/*/cwd` as root.
- **Root's git refuses other users' repositories** ("dubious ownership"), so the census failed on shared boxes. → Run the census as the owning user (`su - <user> -c ...`).

## Reference snippets

Gate a removal on all four conditions (shape of the census check; use the real script from `guides/disk-hygiene.md`):

```bash
# worktree path $w, remote branch check, no cwd inside, older than a day
[ -z "$(git -C "$w" status --porcelain --untracked-files=all)" ] \
 && git -C "$w" branch -r --contains HEAD | grep -q . \
 && ! grep -qx "$w.*" "$CWDS_FILE" \
 && [ -n "$(find "$w" -maxdepth 0 -mtime +0)" ] \
 && git worktree remove "$w"
```

Mac list of cwds for the census: `/usr/sbin/lsof -a -d cwd -Fn | sed -n 's/^n//p' > "$CWDS_FILE"`.

## Keeping it healthy

- Read the summaries weekly; if three in a row say "all clean" and you stopped reading them, shorten the runbook, not the schedule.
- If a step fails the same way twice, fix the cause or move it to the human's list; do not let the agent retry it every morning.
- Keep a "held" list (tools intentionally not updated, with the reason) in the runbook, so "current or held with reason" is checkable.
- When you travel: `morning-run off`. When you return: `morning-run on`, then run once by hand to see the backlog.
- Re-check the harness's headless flags after each major harness update; permission-mode names change.

Last checked: 2026-10, macOS and Debian 12 (the harness-agnostic driver script and systemd timer in this guide are a generalization and were not run as written; test them with `morning-run run` before relying on them, and check the headless flags against your harness version).
