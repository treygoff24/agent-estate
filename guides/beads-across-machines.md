# Beads across machines

How to use the `bd` (beads) task ledger from agents on more than one machine, by carrying its state through the git remote you already have instead of bd's own remote sync; how to stop bd's export file from leaving checkouts dirty so the nightly sync can pull them; and how to give agents a short session briefing instead of bd's stock one.

## Do you need this?

**Skip it** if you do not use `bd`, if all your agents work on one machine, or if a plain `TODO.md` or issue tracker is enough. Nothing else in agent-estate depends on beads.

**Skip the transport part** (steps 2 to 4) if one machine owns each repository's ledger and the others never write to it.

**Do it** if the same repositories are worked on from a Mac and a Linux box, agents on both create and close beads, and you want one ledger per repository that both see within a day. **Cost:** one small script run by the nightly sync, one committed file per repository (`.beads/issues.jsonl`), a `chore(beads): export from <host>` commit in each repository's history, and one rule for people: ledger changes arrive on the sync schedule, not instantly.

## Prerequisites

- `bd` installed on each machine, **the same version everywhere** (1.3.x with its embedded Dolt database at the time of writing; move machines together, because version skew is a live risk).
- Each repository has a git remote you may push to from every machine and an upstream branch set (`git push -u`).
- agent-estate's `sync` module ([modules/sync/README.md](../modules/sync/README.md)): it runs `beads-sync` as an entry in its `hooks` list and refuses to pull dirty checkouts, which is the problem step 3 solves.
- Human: decide which remotes the script may push to (step 3). A private Git host or private GitHub repository is fine; an open-source repository's history is public, so check what your ledger exports before you push it (`bd export` excludes `bd remember` memories by default; keep it that way).

## Steps

### 1. Initialise bd per machine, without bd touching your instruction files or git hooks

`bd init` is a per-machine, per-checkout act. A bare `bd init` rewrites `AGENTS.md`/`CLAUDE.md`, installs git hooks and makes its own commit. Use:

```bash
cd ~/Code/<repo>
bd init --skip-agents --skip-hooks --prefix <short-prefix>   # same prefix on every machine
bd export -o .beads/issues.jsonl
git add .beads/issues.jsonl .beads/.gitignore .beads/config.yaml .beads/metadata.json   # check `git status` for what else bd wants tracked
git commit -m "chore(beads): track export" && git push
```

On the second machine, clone, then run the same `bd init --skip-agents --skip-hooks --prefix <same>`; the first `beads-sync` run fills its database from the committed export. If a database was never initialised on a machine, the sync warns and leaves that checkout alone.

**Done when:** `bd list` works in the checkout on both machines and `git status` is clean apart from the files named in step 3.

### 2. Why not bd's own remote sync

Bd's own Dolt remote sync (a Dolt remote carried inside the git repository) works in a controlled two-client test, but in daily use `bd sync` can halt on both machines with `local changes would be stomped by merge: events`, no checkout has bd's git hooks installed, and nothing carries a bead from one machine to the other: one machine's databases become stale forks (many issues missing) and its closes never reach the other. What *does* travel reliably is the JSONL export bd rewrites on every write (`.beads/issues.jsonl`), as long as somebody commits it, which nobody does on a headless machine. So: commit the export, and import the other side's export. Do not use `bd dolt push/pull` for this.

Rules of this design:

- The committed export is the transport. The local Dolt database is per machine and per checkout.
- `bd import` is an upsert: a row lands only if its `updated_at` is newer, so importing an older export never regresses a bead.
- Conflict rule: per bead, the row with the newer `updated_at` wins whole. Two machines editing the *same* bead between syncs lose the older edit. That is acceptable for a task ledger (agents mostly touch different beads); it is not a database you merge by hand.
- Ledger changes arrive on the sync schedule. A bead written on the other machine a moment ago may not be here yet: look there, or wait for the next sync, before recreating it.

**Done when:** you can state in one sentence which file carries beads between machines (`.beads/issues.jsonl`, via git) and what runs the carrying (`beads-sync`).

### 3. Install `beads-sync` and un-dirty checkouts

bd rewrites `.beads/issues.jsonl` (and, in older versions, `.beads/interactions.jsonl`) on every write. On a machine where agents write beads but nobody commits, every checkout is permanently dirty, and a sync that refuses to pull dirty trees stops pulling anything. On a headless machine most checkouts end up stuck that way. The export is derived from the database, so it is always safe to throw away the local modification of it and regenerate it.

`beads-sync` does, for every git checkout directly under the roots (default `~/Code`) whose `.beads/issues.jsonl` is tracked:

1. Fetch; import the upstream's export into the local database.
2. If the working tree is clean except for bd's own export files: drop those derived modifications, drop any earlier unpushed `chore(beads): export from <host>` commit, fast-forward to the upstream, re-export, and if the export differs from HEAD commit it as `chore(beads): export from <host>` and push. The other machine imports it on its next run.
3. If the tree has other tracked changes (a working checkout with a session in it): import only. Never pull, commit or push there; the session owns the export and commits it with its work.
4. A checkout with local commits that are not beads-sync's own is imported into but never pulled, committed to or pushed: warn and leave it.

The subject is conventional-commit shaped because some repositories enforce `type(scope): summary` in a commit-msg hook (such a hook rejects a prefix like `beads-sync: export`).

Save as `~/.local/bin/beads-sync` and make it executable. This compact version was run against two local clones sharing a bare remote with bd 1.3.1 (bead created on each side, both appeared on both after two runs; a checkout with uncommitted work was imported into and left alone; run under macOS's stock bash 3.2):

```bash
#!/usr/bin/env bash
# beads-sync (compact): carry bd state between machines through git.
# For each git checkout directly under $BEADS_SYNC_ROOTS (default ~/Code) that
# tracks .beads/issues.jsonl:
#   1. fetch; import the upstream's export into the local bd database;
#   2. if the tree is clean apart from bd's export files: drop that derived dirt,
#      fast-forward, re-export, commit "chore(beads): export from <host>", push;
#   3. otherwise (real work in progress): import only; never pull or commit.
set -euo pipefail
ROOTS="${BEADS_SYNC_ROOTS:-$HOME/Code}"
HOST="$(hostname -s)"
EXPORT=.beads/issues.jsonl
AUDIT=.beads/interactions.jsonl
PUSH_RE="${BEADS_SYNC_PUSH_URL_RE:-.}"   # tighten: an ERE a remote URL must match to be pushed
command -v bd >/dev/null || { echo "beads-sync: no bd here; nothing to do"; exit 0; }
rc=0
BOUND=(); command -v timeout >/dev/null && BOUND=(timeout 300)   # stock macOS has no timeout
for dir in "$ROOTS"/*/; do
  dir="${dir%/}"; name=$(basename "$dir")
  [ -d "$dir/.beads" ] || continue
  git -C "$dir" ls-files --error-unmatch "$EXPORT" >/dev/null 2>&1 || { echo "skip $name (export not tracked)"; continue; }
  up=$(git -C "$dir" rev-parse --abbrev-ref '@{u}' 2>/dev/null) || { echo "WARN $name: no upstream"; continue; }
  remote=${up%%/*}; branch=${up#*/}
  ${BOUND[@]+"${BOUND[@]}"} git -C "$dir" fetch -q "$remote" || { echo "WARN $name: fetch failed"; continue; }
  # 1. import (upsert: a row lands only if its updated_at is newer)
  if ! git -C "$dir" show "$up:$EXPORT" 2>/dev/null | (cd "$dir" && bd import - --json >/dev/null); then
    echo "WARN $name: import failed (bd init --skip-agents --skip-hooks needed here?)"; rc=1; continue
  fi
  other=$(git -C "$dir" status --porcelain --untracked-files=no -- . ":(exclude)$EXPORT" ":(exclude)$AUDIT")
  if [ -n "$other" ]; then   # 3. real work in progress: leave it to the session
    echo "$name: imported; $(printf '%s\n' "$other" | wc -l | tr -d ' ') other change(s), left alone"; continue
  fi
  # 2. clean but for bd's own files
  git -C "$dir" checkout -q -- "$EXPORT" "$AUDIT" 2>/dev/null || true
  ahead=$(git -C "$dir" rev-list --count "$up..HEAD")
  if [ "$ahead" -gt 0 ]; then
    if git -C "$dir" log --format=%s "$up..HEAD" | grep -Eqv '^chore\(beads\): export from '; then
      echo "WARN $name: local commits that are not ours; left alone"; continue
    fi
    git -C "$dir" reset -q --keep "$up"   # drop our own unpushed export commit; re-export below
  fi
  git -C "$dir" merge -q --ff-only "$up" || { echo "WARN $name: cannot fast-forward"; continue; }
  (cd "$dir" && bd export -o "$EXPORT")
  git -C "$dir" diff --quiet -- "$EXPORT" && { echo "$name: in sync"; continue; }
  git -C "$dir" commit -q -m "chore(beads): export from $HOST" -- "$EXPORT"
  if git -C "$dir" remote get-url --push "$remote" | grep -Eq "$PUSH_RE"; then
    git -C "$dir" push -q "$remote" "HEAD:refs/heads/$branch" && echo "$name: published" || echo "WARN $name: push rejected; next run retries"
  else
    echo "WARN $name: committed, not pushed ($remote not allowed)"
  fi
done
exit $rc
```

Tighten `BEADS_SYNC_PUSH_URL_RE` in the sync's environment to an extended regex that your approved remotes match (for example, automation pushes only to a private or self-hosted Git server, and pushes to a public host stay a human act). On any other remote the script commits the export and leaves the push to a person, and the next run keeps that one commit current instead of stacking more.

Wire it into the `sync` module as an entry in `[modules.sync] hooks` (for example `hooks = ["estate-config-sync apply --pull", "beads-sync"]`). The module pulls its repo table first and runs the hooks after, so a checkout that bd left dirty and that is also in the repo table shows up as *skipped* in that night's pull (and `estate doctor` warns) even though `beads-sync` then fixes it. Keep repositories that use beads out of the repo table and let `beads-sync` pull them; it handles every checkout under its roots. Run it by hand (`beads-sync`, or one repository at a time by setting `BEADS_SYNC_ROOTS`) after you create a lot of beads. Add `.beads/.auto-import-issues.jsonl` to `.gitignore` if it shows up untracked.

**Done when:** on two machines, a bead created and closed on the Mac appears closed on the Linux box after both have run `beads-sync` twice, `git status` in a clean checkout is empty afterwards, and a checkout with an uncommitted source change still has that change after the run.

### 4. Handle bd's schema gate and recovery

- **Schema gate.** After a bd upgrade a repository may print `refusing to auto-apply N pending schema migrations to a remote-backed database`. Back up `.beads` first (`cp -a .beads ~/.cache/bd-migrate-$(date +%Y%m%d)/`), then run `bd migrate --force` on each machine. Expect to apply it to every database on every machine, and again after the next bd upgrade. It makes the Dolt histories unmergeable across machines; the export-and-import transport does not care.
- **A missing database silently becomes an empty one.** On a checkout whose database is gone, any bd command creates an empty database and reports `No issues found`, which looks legitimate, and then blocks a restore with `database already exists`. If `bd ready` shows an empty ledger where it should not: stop, do not run more bd commands, check `.beads/embeddeddolt`, and restore (from a `bd backup`/Dolt backup, or by `bd init --skip-agents --skip-hooks` followed by one `beads-sync` run, which re-imports everything from the committed export). Restoring a Dolt backup does not restore remote configuration.
- **Fetch before bootstrap.** `bd bootstrap` on a stale clone builds a database from stale metadata. Run `git fetch` first.
- `bd doctor` is unavailable in embedded mode; build health checks from `bd list` and `bd stats`.
- `bd export` is not a full backup (no history or non-issue tables). Use `bd backup init`/`bd backup sync` if you want point-in-time backups, and keep them off the git remote.

**Done when:** you have run `bd migrate --force` (with a backup) on a throwaway copy once, so the first real gate is not a surprise.

### 5. A lean session briefing instead of bd's stock one

`bd prime` is what bd's hooks inject at session start. It is a generic command cheatsheet (a few KB) plus a "session close protocol" that tells agents to commit and push, which conflicts with a house git policy, plus every `bd remember` memory in full (which can grow to tens of KB, mostly memories that duplicate your memory layer). Those tokens cost on every session and every compaction.

Replace it with a five-line reminder that points at `bd prime` for the full reference on demand. Save as `~/.claude/hooks/bd-prime-lean.sh` (any path you keep your hooks in):

```sh
#!/bin/sh
# Lean replacement for `bd prime --hook-json` in SessionStart hooks.
set -eu
python3 - <<'PY'
import json
house = (
    "Beads is this repo's work ledger. Workflow: `bd ready` on arrival; "
    "create the bead before substantial work; `bd close <id> --reason=...` when done; "
    "`bd prime` for the full command reference on demand. Beads is the work graph only: "
    "journals and state files stay the narrative layer. Git policy comes from CLAUDE.md "
    "(or AGENTS.md), not from bd."
)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": house}}))
PY
```

Wire it for Claude Code in `.claude/settings.json` (project) or `~/.claude/settings.json` (user), falling back to bd's own output if the script is missing:

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "", "hooks": [
        { "type": "command",
          "command": "sh -c 'if [ -x \"$HOME/.claude/hooks/bd-prime-lean.sh\" ]; then exec \"$HOME/.claude/hooks/bd-prime-lean.sh\"; else exec bd prime --hook-json; fi'" }
      ] }
    ]
  }
}
```

(Replace `$HOME` handling if your harness does not run hooks through `sh`.) Codex and other harnesses: if your version supports session-start hooks, point it at the same script's text; otherwise put the same five lines in `AGENTS.md`. Because `bd init --skip-agents --skip-hooks` stopped bd from writing its own block into your instruction files, nothing else injects the stock briefing. If a repository already has a bd-written block in `CLAUDE.md` or `AGENTS.md`, delete it by hand and say in your house rules that house rules win over any bd-injected block (it may tell agents to push or to avoid memory files).

**Done when:** a new session in a beads repository shows the five-line reminder and not the cheatsheet, and `bd prime` still prints the full reference when run by hand.

### 6. Working conventions that make the ledger useful across machines

Conventions that work well (leave out any that depend on a particular dashboard):

- **Actor identity.** Set `BEADS_ACTOR` per session (`<harness>:<machine>:<pane-or-session-id>`, e.g. `claude-code:mac:1`) so claims and comments say which session and machine did them. If it is empty, bd records the git user name and you cannot tell sessions apart.
- **A project is an epic; its steps are child beads.** Several steps, spans sessions, or a person wants to follow it: one epic (`bd create "<title>" -t epic -l project --silent -d "Goal: ... Done when: ..."`) and children (`--parent <epic> --no-inherit-labels` so the `project` label is not copied onto every step; `bd dep add <later> <earlier>` for order). One-shot tasks need a single bead or none. Work a project in one repository's ledger only; never split it across two.
- **Claim before work, one at a time.** `bd ready` lists unblocked steps; `bd update <id> --claim`. "Already claimed by <actor>" means another session holds it: pick another or ask, never force. Release with `bd unclaim <id>` plus a comment if you stop.
- **Close with evidence.** `bd close <id> --reason "<commit, test result with counts, file or URL>"`. "Done" is not evidence. Reopen a step whose evidence turned out wrong instead of adding a fix step that hides it.
- **Narrative in the epic's comments**, each starting `finding:`, `decision:` or `need:` (lowercase, colon). Skip routine progress; closed steps already say it.
- **Keep the plan honest.** No retitling, reordering or deleting steps to flatter the count. Add work with a dated reason; retire with `bd supersede <old> --with <new>` or a `dropped:` close reason.
- **Worktrees share the main checkout's ledger**; run bd from inside the repository you mean.
- **Never `bd edit`** (it opens an editor and blocks the agent).

**Done when:** the conventions are in your agent instructions, and a session started on either machine can say which bead it holds.

## What bit us (papercuts)

- **bd's Dolt remote sync halted on both machines** (`local changes would be stomped by merge: events`), so nothing travelled and the second machine's databases were stale forks (many issues missing). → Carry the committed export instead (steps 2 and 3).
- **Most headless checkouts end up dirty with bd export changes**, so the nightly sync refused to pull them. → The export is derived: drop it, fast-forward, re-export. Never hand-fix export dirt.
- **A stray `interactions.jsonl` audit sidecar** kept appearing as dirt after bd turned it off in 1.3.0. → Treat it like the export when un-dirtying.
- **A commit-msg hook rejected the first export commit subject.** → Conventional-commit subject: `chore(beads): export from <host>`.
- **Some checkouts never have bd initialised on the second machine.** → The sync warns and leaves them; initialise with `--skip-agents --skip-hooks`. A bare `bd init` rewrote `AGENTS.md`/`CLAUDE.md` and committed on its own.
- **Schema gate recurred after each bd upgrade** (many databases at once). → Pin and move bd versions together; back up `.beads`, `bd migrate --force`.
- **`bd` on a broken workspace shows an empty ledger as if it were healthy**, and then blocks restore. → Stop on `No issues found` where issues should exist (step 4).
- **A pending-push race.** If two machines push exports at once, one push is rejected. → Warn, keep the local commit, and let the next run drop it and re-export; do not force-push.
- **bd's stock briefing conflicted with house git rules** (it told agents to push and to write bd memories). → Lean hook and a written rule that house rules win.
- **Seeing a bead later than expected is normal.** Agents recreated beads that existed on the other machine. → Say in the instructions: check the other machine or wait for the sync before recreating.

## Reference snippets

Environment knobs for the sync (all optional): `BEADS_SYNC_ROOTS` (colon-separated roots, default `~/Code`), `BEADS_SYNC_PUSH_URL_RE` (extended regex of remote URLs the script may push to; default in the compact version above allows any, which you should tighten).

Hand-run checks:

```bash
BEADS_SYNC_ROOTS=~/Code beads-sync          # all checkouts
BEADS_SYNC_ROOTS=/path/to/one-root beads-sync   # one root
git -C ~/Code/<repo> log --oneline -3       # expect "chore(beads): export from <host>"
bd list --status=open | head                # same beads on both machines after two runs
```

## Keeping it healthy

- After each bd upgrade, on every machine: upgrade together, back up `.beads`, expect the schema gate, run `beads-sync` twice and compare `bd list | wc -l` across machines.
- Watch the sync output for `WARN ... local commits that are not ours` (someone committed in a ledger checkout without pushing), `WARN ... not fast-forwardable` (a diverged branch), and checkouts that stay in "other tracked changes, left alone" for days (a stalled session that never committed its export).
- Do not let the export commits become noise: they are one small commit per change burst per repository; if that bothers you, run the sync less often rather than squashing history.
- If you stop using beads in a repository, delete `.beads` and the tracked export in one commit; the sync skips repositories whose export is not tracked.

Last checked: 2026-10, macOS and Linux (the compact sync script above was exercised on two local clones under macOS bash 3.2 and was not run on Linux or against a hosted remote).
