# Disk hygiene when agents work all day

How to keep disks from filling when agents create git worktrees, build caches and scratch directories all day: a read-only worktree census, a salvage step before any deletion, a janitor that deletes only age-gated junk and only *reports* runaway processes, and the rule that a deletion is not a reclaim while snapshots still hold the data.

## Do you need this?

**Skip it** if you run one or two agents at a time on one machine with plenty of disk (say, you have never seen over 60% used) and you remove your own worktrees. `git worktree list` and `du -sh ~/Code/*` once a month is enough.

**Do it** if agents (or agent orchestrators) create worktrees on their own, you run more than a few at once, you build Rust/Node projects, or any disk or dataset has a quota or snapshots. In practice a day of parallel agent work adds tens of GB of worktrees and build output, and a single overnight run can leave tens of GB of dead worktrees.

**Cost:** two small scripts (census, janitor) and one timer. Everything is read-only or age-gated until you arm it. The risk is not the scripts' weight but a wrong deletion, which is why the rules below are strict.

## Prerequisites

- agent-estate's `health` and `sync` modules for health checks and the nightly sync (the janitor's report feeds the health check; the janitor itself is standalone). The `cleanup` module is a trimmed version of this guide's janitor and census (age-gated worktrees, `target/` and `node_modules/`, logs, an orphan report that never kills, and no salvage step), and `tmp-cleanup` ages out `/tmp`. Install them first if you only need that; read on for the salvage step, the deletion rules and the snapshot caveats they do not cover.
- `git`, POSIX `sh`/`bash`, `find`, `du`, `stat`. Linux for `/proc` checks; on the Mac use `/usr/sbin/lsof`.
- If you use many Rust builds, read `guides/many-agents-compiling.md` first: it owns the build caches. This guide must never delete those (see step 4).
- Decide who may approve deletions beyond the rules here. A workable rule: the agent may delete only what the gates in this guide allow; anything else is the human's call.

## Steps

### 1. Adopt the deletion rules before writing any script

These are the rules every cleanup in this guide follows. They came from real incidents (see "What bit us").

1. **Only delete leftovers created before today, with no process inside.** Do not try to work out which trees an in-flight build still needs. A directory from an earlier day with no process whose cwd is in it is safe by definition; today's directories are not touched. (This replaces hours of per-tree analysis.)
2. **Save uncommitted work first.** Before removing any worktree with changes, write its diff, its untracked files and a note about its HEAD somewhere durable. Branches stay; only the working directory goes.
3. **An unreadable answer is "keep".** A failed `git status`, a failed `find`, an empty process list, a missing tool on PATH: each must read as "keep", never as "clean" or "nothing found".
4. **Janitors delete only junk that is old by a mtime gate.** They never decide a process is dead; they *report* runaway or orphan processes and a human (or an armed, narrowly gated reaper) acts.
5. **A deletion is not a reclaim.** If snapshots hold the blocks, free space does not move until the snapshots expire (step 6).
6. **Dry-run first.** Every deleting script takes a dry-run switch and runs in dry-run for at least a week before it is allowed to delete.

**Done when:** these six rules are in your agent instructions or runbook, in the same words, so any agent that cleans a disk reads them.

### 2. Find stale worktrees with a read-only census

The census prints one TSV line per linked worktree: `REMOVE` or `KEEP`, the reason, path, branch, repo. It never removes anything. `REMOVE` requires all of: untouched for 24 hours, clean (including untracked files), HEAD already in the remote's default branch or on some remote branch, and no process with its cwd inside.

Save as `~/.local/bin/worktree-census`:

```bash
#!/usr/bin/env bash
# worktree-census: read-only. Usage: worktree-census <code-root> <cwds-file>
# <cwds-file>: working directory of every live process, one per line.
#   Mac:   /usr/sbin/lsof -a -d cwd -Fn | sed -n 's/^n//p' > cwds.txt
#   Linux: readlink /proc/*/cwd 2>/dev/null > cwds.txt   (as root to see all users)
# An empty list is refused: it would read every worktree as unoccupied.
# Run as the owner of the repos: root's git refuses other owners' repos, and a
# failed `git status` is reported, never read as clean.
set -uo pipefail
ROOT="${1:?usage: worktree-census <code-root> <cwds-file>}"
CWDS="${2:?usage: worktree-census <code-root> <cwds-file>}"
[ -s "$CWDS" ] || { echo "worktree-census: cwd list $CWDS is empty or missing; refusing" >&2; exit 2; }
NOW=$(date +%s)
if [ "$(uname)" = Darwin ]; then mt(){ stat -f %m "$1" 2>/dev/null || echo 0; }
else mt(){ stat -c %Y "$1" 2>/dev/null || echo 0; }; fi

while IFS= read -r gitdir; do
  repo=$(dirname "$gitdir")
  git -C "$repo" worktree list --porcelain 2>/dev/null |
    awk 'BEGIN{RS="";FS="\n"} NR>1 {wt="";br="(detached)"
      for(i=1;i<=NF;i++){ if($i~/^worktree /)wt=substr($i,10); if($i~/^branch /)br=substr($i,19) }
      print wt"\t"br}' |
  while IFS=$'\t' read -r wt br; do
    emit(){ printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$wt" "$br" "$repo"; }
    [ -d "$wt" ] || { emit KEEP "folder gone (git worktree prune clears the record)"; continue; }
    reasons=()
    gd=$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null)
    newest=0
    for f in "$gd/HEAD" "$gd/index" "$gd/logs/HEAD" "$wt"; do
      m=$(mt "$f"); [ "$m" -gt "$newest" ] && newest=$m
    done
    age_h=$(( (NOW - newest) / 3600 ))
    [ "$age_h" -lt 24 ] && reasons+=("active <24h (${age_h}h)")
    if st=$(git -C "$wt" status --porcelain --untracked-files=all 2>&1); then
      n=$(printf '%s' "$st" | grep -c .)
      [ "$n" -ne 0 ] && reasons+=("$n uncommitted/untracked")
    else reasons+=("git status failed"); fi
    head=$(git -C "$wt" rev-parse HEAD 2>/dev/null)
    def=$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
    if [ -n "$head" ] && git -C "$repo" merge-base --is-ancestor "$head" "$def" 2>/dev/null; then :
    elif [ -n "$head" ] && git -C "$repo" branch -r --contains "$head" 2>/dev/null | grep -q '^ *origin/'; then :
    else reasons+=("commits not on origin"); fi
    grep -qF -- "$wt" "$CWDS" && reasons+=("occupied by a process")
    if [ ${#reasons[@]} -eq 0 ]; then emit REMOVE "idle ${age_h}h, clean, on origin, unoccupied"
    else emit KEEP "$(IFS=';'; echo "${reasons[*]}")"; fi
  done
done < <(find "$ROOT" -mindepth 2 -maxdepth 3 -name .git -type d 2>/dev/null)
```

(The loop skips a repo's main checkout via `NR>1`, because the first porcelain record is the main worktree. Add a `case` that prints `KEEP` for any path you never want touched, such as a directory someone else owns.)

Run it, read the `REMOVE` rows by eye the first few times, and remove with plain `git worktree remove <path>` (no `--force`).

**Done when:** `worktree-census ~/Code cwds.txt` prints a line per linked worktree, a worktree you have open in a terminal is `KEEP ... occupied by a process`, and an empty `cwds.txt` makes it exit 2.

### 3. Salvage before deleting dirty or unpushed worktrees

For the days when you clear everything regardless of the census, do this per worktree *before* removal:

```bash
salvage() {  # salvage <worktree-path> <dest-dir>
  wt=$1; dest=$2/$(basename "$wt")-$(date +%s); mkdir -p "$dest" || return 1
  git -C "$wt" status --porcelain=v1 --untracked-files=all >"$dest/status.txt" || return 1
  git -C "$wt" diff HEAD >"$dest/tracked.diff" || return 1
  git -C "$wt" ls-files --others --exclude-standard -z |
    tar -C "$wt" --null -T - -czf "$dest/untracked.tgz" || return 1
  { echo "path=$wt"; echo "head=$(git -C "$wt" rev-parse HEAD)"; echo "branch=$(git -C "$wt" branch --show-current)"; } >"$dest/info.txt"
  # a detached HEAD that is not on a remote branch is kept as a branch
  if [ -z "$(git -C "$wt" branch --show-current)" ] && [ -z "$(git -C "$wt" branch -r --contains HEAD)" ]; then
    git -C "$wt" branch "salvage/$(date +%Y%m%d)/$(basename "$wt")" HEAD
  fi
}
# Remove only if salvage succeeded: salvage "$wt" "$HOME/salvage" && git worktree remove --force "$wt"
```

Use `&&`, never `;`, between salvage and removal. Branches stay; only the working directory and its untracked files are removed. In a cleanup of dozens of worktrees, a large share were dirty and a handful had detached HEADs not on any remote; all were salvaged this way and nothing was ever asked for afterwards.

Ledgers and lane residue (an issue tracker's `.beads/` export, `.papercuts.jsonl`, scaffolding directories, `*.log`) rewrite themselves constantly. Exclude them from the "is this dirty?" test or every worktree will look dirty forever. Triaging dozens of stranded worktrees turns up only a few worth keeping; adopt the rule that a lane's work ends committed on its branch or it is junk.

**Done when:** a test worktree with one modified, one untracked and one committed-only file gets a salvage directory containing all three, and the worktree is removable afterwards.

### 4. Install a janitor that deletes only age-gated junk

One POSIX `sh` script on a timer (every 6 hours as root on a shared host, with `Nice=10` and `IOSchedulingClass=idle`; on a single VPS run it as your user). It does four things and nothing else.

1. **Temp sweep.** A top-level `/tmp/*` entry is deleted only when *nothing inside it* is newer than 3 days (recursive `find -newermt "3 days ago" -print -quit`, so a long-lived but active tree survives). Entries whose newest file is 2 to 3 days old are announced as "deletes-tomorrow" so owners get one report cycle to claim them. Exclude live-infrastructure names (`systemd-private-*`, `tmux-*`, your agent tools' own sockets, `ssh-*`, dotfiles). Throwaway agent-copy directories age out at 1 day.
2. **Dead worktree directories** (only if your orchestrator creates them in a known place). Delete when the newest file is over 12 hours old, no live process has its cwd inside, and there are no uncommitted changes (ledger/residue excluded). Dirty and under 24 hours old: retain and report. Dirty and over 24 hours old: delete anyway (rule: committed or junk), after salvage if you can. Prune the `.git` directory out of both freshness probes: running `git status` rewrites `.git/index`, which can make every dirty worktree look "24 hours fresh" forever. A worktree with processes still inside but nothing newer than 12 hours is *kept* and the pinning pids are named in the report (a leaked dev server or browser from a finished lane).
3. **Build trees.** A `target/` or `*target*` cache directory is deleted only if its newest file is over 12 hours old *and* no cargo, rustc or linker process is running anywhere on the machine (a cwd/fd snapshot races an active build; a target deleted mid-link by hand breaks the build). Skip any mount point, and skip directories owned by a dedicated pruner. If you adopted `guides/many-agents-compiling.md`, add its scratch roots to the exclusion list: a broad glob can match a managed cache directory, delete its contents every idle pass, then fail on the mount point.
4. **Small hygiene and a census.** `git worktree prune` (admin records only; count by comparing record counts before and after, not by parsing the verbose output, which prints before it acts), `docker image prune -f` (images only, never volumes), `journalctl --vacuum-size=500M`, deleting your own reports older than 30 days, then a census appended to a trend file: date, memory used and available, swap, root disk percent.

Rules inside the script:

- `find` errors read as *keep*: `newest=$(find ... -print -quit); [ $? -ne 0 ] && keep`. An unreadable tree is never "nothing newer, delete".
- Delete with `rm -rf "$e" && [ ! -e "$e" ]`, and print `DELETED` or `delete-failed` accordingly. Never print `DELETED` for something still there.
- Parse `du -sh` figures properly (no suffix means bytes), and compute bytes for the report from `du -sk`.
- One line per action to a log (`DELETED`, `would-delete`, `deletes-tomorrow`, `retained-dirty`, `find-error(kept)`, `orphan-pinned(kept)`), plus an events feed if you have one. `JANITOR_DRY_RUN=1` prints `would-delete` instead.
- **Report processes; do not kill them here.** Kill candidates are processes over 500 MiB resident, under 5% lifetime CPU, older than 6 hours, whose cwd is under no live terminal pane or agent session. The janitor lists them (`KILL-CANDIDATE pid=... rss=... age=... cwd=... cmd=...` with the command line truncated and non-printables stripped) and a human or a separate reaper decides. Without a reliable "who owns this process" oracle (for example the terminal multiplexer's list of live panes), do not even report: everything would be a candidate forever.
- Alarm lines: any quota'd dataset at 80% or more of its quota, and any root filesystem over 80%. `df /` hides snapshot usage and separate scratch datasets with their own quotas; check the dataset view too (step 6).

A narrowly gated reaper is optional, and it should run **dry-run until armed by a file** (`touch /etc/<you>/reaper.armed`; `rm` to disarm; an environment variable forces dry-run) after a clean week of observation. If you build one, a kill requires *all* of: not a system service (no `.service` in the cgroup), not owned by a live agent session, human shell or restart-capable supervisor (walk the parent chain; any walk error is "unknown", which never kills), and a detector: cwd inside throwaway scratch for over 6 hours (24 hours for `/tmp`), cwd already deleted (re-confirmed just before the kill), or sustaining about one full core across a live 10-second delta sample (lifetime average never decides). Identify the process by `(uid, start time)` and re-verify before TERM, before KILL and for the verdict, so pid reuse cannot redirect a signal.

**Done when:** a dry run (`JANITOR_DRY_RUN=1`) over a test directory with one 5-day-old tree, one 2.5-day-old tree and one fresh tree prints `would-delete`, `deletes-tomorrow` and nothing for the fresh one; with the dry-run flag off, only the first is removed; and a tree containing a file you touch a minute ago survives however old its other files are.

### 5. Run the big clean-up days by the same rules

When disk is near full and a human says "clean everything" (this happens more than once a month on a busy box), do it in this order and keep the receipts:

1. Check what is live first: running services, containers, anything a person is attached to.
2. Worktrees: census, then salvage, then remove the ones created before today with no process inside. Count what you skipped (today's, busy) in the summary.
3. Git-ignored build output in those repos (`node_modules`, `.next`, `target`, `dist`), except in repos a live service runs from.
4. Caches (`pnpm store prune`, npm, pip, old browser builds: keep the newest of each), and old probe or scratch directories.
5. Snapshots (step 6), last, because only now are the largest blocks unreferenced.
6. Re-check services (no failed user units), then say in the summary: what was removed, what was archived and where, what was kept and why, and the before/after numbers for both live and snapshot usage.

Expect the first builds afterwards to recompile and reinstall dependencies; say so.

**Done when:** the summary lists before/after for live and snapshot usage separately, and a service check shows nothing newly failed.

### 6. A deletion is not a reclaim: snapshots

If the filesystem or host takes snapshots (ZFS/sanoid, Btrfs, LVM, Time Machine local snapshots on the Mac, your VPS provider's image snapshots), data you delete stays allocated until every snapshot holding it expires. In practice root usage can fall by tens of GB while snapshot usage *rises* by a similar amount as the deletions age into the snapshots; a Mac can gain hundreds of GB free only after clearing Time Machine local snapshots *after* deleting the build output; and `df /` can hide a hundred GB or more of snapshot usage on a quota'd dataset.

- See it: ZFS: `zfs list -o name,used,usedbysnapshots,quota -r <pool>/<datasets>`; Mac: `tmutil listlocalsnapshots /`, `df -h /`; compare "used" with "used by snapshots".
- Keep a retention policy; do not delete snapshots to make a graph look better on an ordinary day. When the human has asked for a hard clean-up, remove snapshots older than 24 hours but keep the freshest one or two, after checking for holds, keeps or clones (`zfs holds`, `zfs get clones`). Mac: `tmutil deletelocalsnapshots <date>` per snapshot.
- Prefer **not snapshotting** the churn. Put worktrees' build output, Docker data and caches on an unsnapshotted dataset or directory with a quota (see `guides/many-agents-compiling.md`), so cleanup never has to fight snapshots.
- Before destroying a snapshot, consider what only the snapshot holds: uncommitted files of deleted worktrees can survive only in the previous days' snapshots, which is exactly why step 3 (salvage) comes before step 6.

**Done when:** you can state, for each filesystem, the live size, the snapshot size and the policy, and a cleanup receipt shows both numbers moving.

## What bit us (papercuts)

- **Dead worktrees pile up faster than a 3-day gate fires.** One overnight run can leave tens of GB. → 12-hour gate for worktrees whose lane ended; 24 hours for the census.
- **A worktree was removed while its agent was still running.** The agent's shell reported "working directory was deleted" mid-command, and all its in-progress work would have been lost. → Removal requires "no process with cwd inside" and, if you can ask, "no live run owns it" (owner process and its process group), checked again immediately before deleting.
- **`lsof` was not on the PATH of a restricted job**, so the cwd list came back empty and two worktrees in use were marked removable. → Refuse an empty list; use `/usr/sbin/lsof` by absolute path.
- **Root's git refuses repos owned by other users ("dubious ownership")**; a failed `git status` was nearly read as clean. → Run the census as the repo owner and treat a failed status as "keep".
- **`git status` rewrote `.git/index` and made dirty worktrees look permanently fresh**, so the gate never fired. → Exclude `.git` from freshness probes.
- **Ledger and log files made every worktree "dirty".** Every retained-dirty worktree held only tracker exports and logs. → Exclude residue patterns from the dirty test.
- **A cache cleanup glob matched a managed mount point**, deleted its contents every idle pass, then errored. → Skip mount points and directories owned by another pruner.
- **A target directory was deleted mid-link by hand**, because a cwd/fd snapshot races an active build. → Skip build-tree deletion whenever any compiler or linker is running.
- **Orphaned dev servers and browsers held gigabytes** after their lanes finished. → Report "orphan-pinned" with pids; let a human or an armed reaper act.
- **A multi-GB orphaned server was found only because ownership was judged by the terminal multiplexer's live pane list.** A resident-size threshold alone flags every long-lived tool. → Use an ownership oracle; without one, don't flag.
- **A handful of leaked supervisor processes spun several cores for half a day** under a 24-hour age gate. → Sustained CPU across a live delta sample, over 30 minutes old, not lifetime average.
- **Deleting a lot did not free space**: see step 6.
- **"Delete everything" lost uncommitted work in principle.** The only copy of some changes was in a worktree about to go. → Salvage first; keep branches.
- **A deleting script that printed `DELETED` for something still present** hid a permissions failure. → Verify with `[ ! -e "$path" ]` before claiming.
- **Chaining cleanup with `;`** (`cmd --body-file "$f"; rm -f "$f"`) deletes the input when `cmd` fails. → `&&`, or check the result in a separate call. Never pass a possibly-empty variable to `rm`; guard `[ -n "$p" ]` first.

## Reference snippets

Janitor unit and timer (systemd; for a user-level install drop `IOSchedulingClass` as needed and use `systemctl --user`):

```ini
# janitor.service
[Service]
Type=oneshot
ExecStart=/usr/local/lib/<you>/janitor.sh
Nice=10
IOSchedulingClass=idle
# janitor.timer
[Timer]
OnCalendar=*-*-* 04,10,16,22:00
Persistent=true
RandomizedDelaySec=300
[Install]
WantedBy=timers.target
```

The temp-sweep core (the shape; keep the dry-run switch, the exclusions and the find-error rule):

```sh
for e in /tmp/*; do
  [ -e "$e" ] || continue
  case "${e##*/}" in systemd-private-*|tmux-*|ssh-*|.*) continue ;; esac
  newest=$(find "$e" -newermt "3 days ago" -print -quit 2>/dev/null) || { echo "find-error(kept) $e"; continue; }
  if [ -z "$newest" ]; then
    if [ "${DRY:-0}" = 1 ]; then echo "would-delete $e"
    elif rm -rf "$e" 2>/dev/null && [ ! -e "$e" ]; then echo "DELETED $e"
    else echo "delete-failed $e"; fi
  elif [ -z "$(find "$e" -newermt "2 days ago" -print -quit 2>/dev/null)" ]; then
    echo "deletes-tomorrow $e"
  fi
done
```

## Keeping it healthy

- Read the janitor's report and trend file weekly; add a health row that fails when the last janitor run is over 12 hours old, or when any dataset is at 80% or more.
- Review the `retained-dirty`, `orphan-pinned` and `KILL-CANDIDATE` lines; recurring entries mean a workflow is leaking (a lane that never commits, a server nobody stops). Fix the source, not the janitor.
- Keep exclusions in one place; every new managed cache directory must be added to the janitor's skip list the day it is created.
- If you ever arm a reaper, re-run it dry for a week after every change to its rules.
- After any hard clean-up, check snapshot retention is back to its normal policy and that a service check is green.

Last checked: 2026-10, Debian 12 and macOS (the census script is exercised; the portable salvage function and the single-VPS janitor variant are generalizations and should be dry-run before use).
