---
name: estate-health
description: >-
  Read the estate health report and triage it: "what happened on the box overnight",
  "morning report", "is something eating CPU or disk", "is the estate healthy", or
  acknowledging a triaged report. Use at the start of a working day, after any alert,
  and before reporting that a machine is fine.
---

# estate-health: the morning read

`estate-health` is a read-only collector installed by the `health` module. It runs
hourly, grades each check `ok`, `unknown`, `warn` or `crit`, and remembers what you
last acknowledged. You are the judgment it deliberately lacks: it never kills,
deletes, restarts or upgrades anything.

## Steps

1. **Run it.** `estate-health` (text; exit 0 ok, 1 warn, 2 crit). Use `--json` when you
   need a field, `estate-health show` for the cached hourly report without collecting.
   On a remote box: `ssh <machine> estate-health`.
2. **Check the collector first.** If `estate doctor` shows `health` failing, or the report
   is more than about two hours old, that is the first finding: a dead collector looks
   like a healthy machine. Fix with `estate install health`.
3. **Read "since last ack".** It lists findings that are new since the last ack, ones
   that resolved, and what the nightly cleanup deleted. Start from what is new.
4. **Triage each non-ok line** with the table below: fix it, propose it, or just note it.
   `?` (unknown) lines are gaps (a tool missing, no sync state yet), not health. Name
   them; do not chase them unless asked.
5. **Brief the person**: severity and the headline first; then the overnight events in two
   or three lines; then proposed actions as a short list, one question at a time where
   their decision is needed. Wait for answers before anything under "bring to the human".
6. **Verify each fix** by re-running `estate-health` (it is read-only and cheap).
7. **Ack when you have read it all**: `estate-health ack --by <your name>`. Every finding
   you triaged becomes "known" and stops counting as new; a crit always stays in
   attention. Ack only what you actually looked at.

## Playbook

| Check | Safe for you to do | Bring to the human |
|---|---|---|
| `disk` | Run `estate-cleanup run --dry-run`, then `estate-cleanup run` (age-gated scratch only). Report sizes of the largest regenerable caches (`target/`, `node_modules`, package caches). | Deleting anything that cleanup does not own: other people's data, databases, backups, snapshots, anything you did not create. |
| `memory` | Read-only: find the biggest consumers (`ps -axo pid,rss,etime,comm`). | Killing or restarting anything. |
| `units` | `systemctl --user status <unit>` / `journalctl --user -u <unit> -n 30` (Linux), the agent's log (Mac). Fix an obvious cause (stale path, missing env) then `systemctl --user reset-failed <unit>`. | A unit that fails again after a fix, or whose purpose you do not know. |
| `doctor` | Follow each failing row's `done when:` line. `estate install <module>` re-applies a module and is idempotent. | Rows that need root (the login has no sudo): show the exact command and wait. |
| `sync` | Read the sync log; re-run the sync once if the cause was transient. | A conflict, a diverged branch, or a second failure. Never force anything. |
| `runaway_processes` | Name the process, owner, age, and what started it. A build or a live agent session is fine. | Any kill. Propose it with the pid and owner line; the person decides. |
| `stale_worktrees` | `git worktree prune` for ones whose directory is gone; `estate-cleanup` removes clean ones past its age. | A dirty worktree: check `git -C <path> status` and whether the work was committed or pushed; ask before removing it. |

Anything not in a "safe" cell is the person's call: deleting what you did not create,
killing a process, upgrading packages, restarting a service, rebooting. If disk, memory
or a failed unit is critical and you are unsure, stop and tell the person before
acting: a well-meant restart during a memory or I/O problem can make it worse.

## What the severities mean

- `crit` (exit 2): something is broken now, or the disk or memory is nearly gone. Say so first.
- `warn` (exit 1): needs a look today. Not new after an ack unless a new thing appears.
- `unknown`: the check could not run. Never read it as ok.
- `attention: true` in the JSON: something new warned since the last ack, or any crit.
