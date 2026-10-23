# Many agents compiling on one box

How to keep a box usable when many agents build Rust (and other heavy things) at once: a shared compiler cache, cargo target directories that prune themselves, a FIFO queue for compiles with memory-headroom admission, Docker data on disk that is never snapshotted, garbage collection for test containers, and the Mac rules (nice 19, never background QoS, spawn-storm detection).

## Do you need this?

**Skip it** if any of these is true:

- One person, one or two agents at a time, on a VPS or a Mac. agent-estate's `guardrails` module is enough: `testrun` runs heavy commands niced (Mac) or inside a memory-capped systemd scope (Linux), with a time limit, and refuses a duplicate run. It has no machine-wide job cap.
- Your agents mostly edit and run small test files. Nothing here helps them.
- You have no git worktrees per agent. The pruning in step 2 is keyed on worktrees.

**Do it** if you run roughly four or more agents at once that each build in their own git worktree, and you have seen any of: the disk filling with `target/` directories, the box swapping or being OOM-killed during builds, typing lag on the Mac while agents work, thousands of leftover Docker volumes.

**Cost:** about 1 GiB RAM for the sccache server while it is busy, a cache dataset you size yourself (for example 15 GiB for sccache and a few hundred GiB for targets on a big box), one small systemd timer, and a few Python/bash scripts to maintain. The operational weight is real: the pruner runs to well over a thousand lines because deleting build output safely is hard. Adopt the pieces in order and stop when the pain stops. Steps 1 and 5 are cheap and worth it on any box; steps 2 to 4 are for larger boxes.

## Prerequisites

- agent-estate's `guardrails` module installed (`estate install guardrails`; `testrun` on PATH). Its optional compile slots, `compile_slots = true` under `[modules.guardrails]`, are this guide's steps 1 and 3 in a smaller form; see "What the guardrails module already ships" below.
- Python 3.11+, `sccache` (`cargo install sccache --locked` or your package manager), a Rust toolchain via rustup.
- Linux: systemd user units, and ideally a separate filesystem or directory for scratch (step 2). Mac: Apple silicon, launchd.
- For Docker steps: Docker on the Linux box and root access to install a root-owned helper.

## What the guardrails module already ships

Read this before the steps, so you build only what is missing. See [modules/guardrails/README.md](../modules/guardrails/README.md).

| This guide | In the `guardrails` module |
|---|---|
| Step 1, the compile gate | `rustc-gate` (a `RUSTC_WRAPPER`) when `compile_slots = true`: takes a slot, wraps the compile in `sccache` if it is installed, unsets the three `CARGO_*` target variables before `sccache`, skips `sccache` when `CARGO_INCREMENTAL=1`, runs at nice 19 on a Mac. **Not shipped:** starting one pinned `sccache` server (port 4226) in its own unit, and refusing output paths outside a scratch root. |
| Step 3, the rustc pool | `compile-slot-gate`: `rustc_slots` machine-wide slots (default 12 on Linux, 8 on a Mac, never above the core count), the first `rustc_base` (6) always open, higher ones only with `rustc_headroom_gb` (12) plus 2 GB per higher slot free, one waiter polling and the rest asleep in `flock`, and `state.json` under `~/.local/state/compile-slots/`. **Not shipped:** the cargo reservation pool, strict FIFO tickets, and `measurement-lock`. |
| Step 5, the Mac rules | `testrun` at nice 19 with every core, never `taskpolicy -b`; it waits *before starting* while memory pressure is critical (level 4 on two readings 3 s apart; `--wait-max SECONDS`, default 3600, bounds that wait and exits 75). **Not shipped:** pausing a run that is already going (SIGSTOP/resume), a machine-wide job count, and Spotlight advice. |
| Steps 2, 4, 6 | Nothing: the target-directory pruner, Docker GC and spawn-storm detection are yours to build from this guide. (`cleanup` removes old `target/` directories and worktrees by age; it is not the water-mark pruner.) |

`testrun`'s flags and exit codes, which the rest of this guide assumes: `testrun <repo> <kind> [--max SECONDS] [--wait-max SECONDS] -- <cmd...>`; the run is named `<repo>-<kind>` and a second live run of that name exits 75; `--max` is the execution limit (exit 124; default 600 s, `gate*` kinds 1800, `mut*` 7200, and on a Mac 3600), counted from the start of the command, never from the wait; 64 usage error; 69 no systemd user bus (Linux); 130/143 interrupted. `--list` and `--stop <repo>-<kind>` manage live runs.

## Steps

### 1. Share compiles with sccache behind a compile gate

Every `cargo` run spawns many `rustc` processes. Put one wrapper in front of every compile so there is a box-wide limit, and have it hand the real compile to sccache so fresh worktrees reuse third-party crates.

Set the wrapper in `~/.cargo/config.toml` (preserve other settings):

```toml
[build]
rustc-wrapper = "~/.local/bin/rustc-gate"
```

(Cargo does not expand `~`; write the absolute path of your home in the file.)

The gate (shape; the module's `rustc-gate` is a short bash wrapper plus the `compile-slot-gate` Python helper for the slots, and does items 3 and 4 below; items 1 and 2 are yours to add) does, in order:

1. Refuse compiler output paths outside the scratch area (see step 2), if you adopted that.
2. Make sure one sccache server is running on one port (4226), started *before* a slot is taken.
3. Take one of N slots, hold it for the whole compile, then `exec sccache rustc ...`.
4. Unset `CARGO_TARGET_DIR`, `CARGO_BUILD_TARGET_DIR`, `CARGO_BUILD_BUILD_DIR` just before `exec sccache`. sccache hashes every `CARGO_*` variable into its key; if the target dir is per-worktree, no two worktrees ever share a cache entry (expect zero hits on the second worktree until you do this).

Environment knobs: `RUSTC_GATE_SLOTS` (ceiling; also `rustc_slots` in `estate.toml`; 12 on a big Linux box, 8 on a Mac as a starting point; the other module settings are `rustc_base` and `rustc_headroom_gb`, with `RUSTC_GATE_BASE` and `RUSTC_GATE_HEADROOM_GB` as their environment overrides), `RUSTC_GATE_SCCACHE=0` (skip sccache for one command), `SCCACHE_DIR` (default `~/.cache/sccache`), `SCCACHE_CACHE_SIZE` (`15G` is a reasonable start). `RUSTC_GATE_SLOTS=0` bypasses the slot semaphore entirely; keep it for emergencies and never for scheduled work, because bypassed compiles are invisible to the admission count.

Details that matter:

- Start the sccache server as a transient systemd user unit (`systemd-run --user --unit=sccache-server-4226 -E SCCACHE_START_SERVER=1 -E SCCACHE_NO_DAEMON=1 ... sccache`), so it lives in no job's cgroup. Where there is no systemd (Mac), start it with every inherited file descriptor above 2 closed, e.g. `python3 -c 'import subprocess; subprocess.run(["sccache","--start-server"], close_fds=True)'`. A server that inherits a build's lock descriptors blocks cache cleanup for as long as the server lives.
- sccache refuses every call when `CARGO_INCREMENTAL=1` is set. The gate skips sccache in that case.
- Put the sccache directory on a different filesystem from the cargo targets, and keep it out of the pruner's reach (step 2 deletes any directory it finds under the scratch root that it does not recognise).
- Expect a modest win. A benchmark on a mid-size workspace: about an 80% hit rate on the second and third worktrees, but wall time barely moved (about 6% faster), because crates that include generated code via `OUT_DIR` (serde_core, thiserror, and their dependents) key on a per-worktree path and recompile, and workspace crates are incremental and uncacheable. Workspaces with many third-party crates gain more.

**Done when:** in two fresh worktrees of one project, `sccache --show-stats` shows compile requests served from cache on the second, and `cargo build` still succeeds with `RUSTC_GATE_SCCACHE=0`.

### 2. Route cargo targets to one scratch area and prune it by water marks

Without this, every agent worktree grows its own `target/` (often 5 to 30 GiB), inside the worktree, and the disk fills. In practice, tens of GiB of build output end up inside snapshotted worktrees, and tens more in a shared target directory nobody expires.

Design:

- **One scratch root** on its own filesystem or directory with a quota, **no snapshots** (`~/.cache/cargo-targets/`). Build output is rebuildable; snapshotting it only keeps deleted blocks allocated (see "disk is not reclaimed" in the papercuts).
- **A managed `cargo` entrypoint** earlier in PATH than rustup's. It sets `CARGO_TARGET_DIR=<scratch>/managed-v1/<hash of the canonical worktree root>/` for each build, writes a small marker file recording the workspace path, and refuses explicit targets outside scratch. Keying by worktree (not a pool of shared targets) matters: Cargo's mtime freshness checks mistook artifacts from another checkout for current code when we recycled targets between worktrees.
- **A pruner on a 5-minute timer.** Rules, in order:
  1. A cache whose workspace directory no longer exists is deletable at once, subject to the safety gates below.
  2. A cache unused for 24 hours is deleted whole. Main checkouts (a workspace directly under `~/Code`) are never deleted by age, only under pressure.
  3. **Slimming:** any cache idle over 30 minutes with a free lock loses `debug/incremental` and `release/` (the bulky, cheap-to-regenerate parts); `debug/deps` and `debug/build` stay.
  4. **Water marks** as fractions of the filesystem: above the high mark (70%) clean until below the low mark (50%). Order: one-shot entries (acceptance runs, temp child worktrees, names ending in `-mut`), then lanes, then main checkouts; within a class, longest idle first, then largest. Pass one slims everything; pass two, only if still above low, deletes whole entries. Keep a 10-minute grace window so an agent that just built a binary can still run it.
  5. Throw away wall-clock estimates of what was reclaimed: re-read real filesystem usage after each removal.
- **Safety gates before any deletion** (these exist because each one was a real near-miss or incident):
  - take the cache's exclusive lock (cargo holds a shared one for the whole invocation);
  - a process census: read every process's cwd, exe, open fds, maps, environ and command line, and keep any cache a live process references. Treat a zombie as absent. Fail closed (keep the cache) only for processes you cannot read *and* whose command line names a build tool; unrelated unreadable system processes made every user-run prune stop at "unknown" until we narrowed this.
  - a consumer check: do not delete a target that an installed tool symlinks into.
  - never delete anything outside `managed-v1/<hash>` plus its marker; never follow a symlink out of the target.
- **Deletion is a rename** into `<scratch>/.estate-trash` under the lock, then a drain that stops at a deadline (8 minutes). A pass killed by a timeout otherwise leaves half-deleted trees.
- **Split slow work from the fast timer.** The 5-minute pass only prunes. Docker cleanup and an audit walk for Rust output *outside* scratch (`~/Code`, `~/.cache`, temp dirs) run in a separate hourly unit. When we had both in the 5-minute unit, the audit walk alone took over 12 minutes under disk pressure, every pass hit its timeout, and the pass that never recorded success looped forever.
- **Reclaim inline before refusing.** On each build-writing cargo call, check free space (floor: the larger of 5 GiB and 10% of the filesystem); below it, run one pressure collection first, serialised with a lock so many callers do not all collect at once, and refuse only if still below. Expose `ensure-free` (exit 0, or 2 with a reason) for wrappers.
- **Hold for acceptance scripts.** A script that builds, then later runs the binary, wraps both in `estate-build-cache hold -- <command>`, which keeps a shared lock on the target until the command exits. No lease files, no PIDs to go stale.
- **Report, do not delete, unmanaged caches** found by the audit (targets outside scratch). A human approves removal.

Adopt it incrementally: first just route `CARGO_TARGET_DIR` into a quota'd, unsnapshotted directory and run the pruner with `--dry-run` for a week before enabling deletion. Do not start with the pressure logic.

**Done when:** `cargo build` in a worktree places output under the scratch root (`estate-build-cache path` or your equivalent prints it); deleting a test worktree makes its cache collectible on the next pass; and a deliberately locked cache (a running build) survives a pass with a reason such as `retained: process` in the receipt.

### 3. FIFO compile slots with memory-headroom admission

A semaphore on compiles stops a box melting, but a plain "take whatever fits" semaphore starves big jobs. Two pools, both flock-based (kernel locks release on process exit, so a crash never leaks a slot):

- **Cargo pool (reservations; not in the `guardrails` module):** 8 slots shared by all checkouts. A caller takes N slots for a lane (a gate run takes all 8). Admission is strictly FIFO: each waiter creates a ticket `wait-<time_ns>-<pid>` holding a flock and takes slots only when no *older live* ticket exists. A ticket is live only while its flock is held, so a crashed waiter cannot block the queue. We moved from fit-first to FIFO so a waiter's place is fixed by arrival order; while old fit-first waiters were still running, a head-of-line waiter could still lose slots to them.
- **Rustc pool (compiler processes):** the gate in step 1, which is the `compile-slot-gate` the module ships. The first six slots are always open; each slot beyond them opens only when the cgroup (or machine) has memory headroom: limit minus anonymous and shared memory (file cache is reclaimable) must be at least a configured floor, plus 2 GiB for each higher slot already admitted, because compiles grow after admission. We added this after a whole container was OOM-killed just under its memory limit during parallel builds. The binding limit on a rented VPS is usually RAM, not cores.

Rules that kept this cheap and stable:

- Only the head-of-line waiter polls slots (every 50 ms); everyone else sleeps inside a blocking `flock`. A burst of about a hundred queued compiles, each polling every slot and rewriting a state file ten times a second, can make a laptop unusable.
- Publish one JSON snapshot at `~/.local/state/compile-slots/state.json` (write a temp file in the same directory, then rename; never truncate in place). Fields: `in_use`, `total`, `queue_depth`, per pool. Readers treat a snapshot older than 5 seconds as unknown. Never sum the two pools.
- Never delete lock files while gates run; the kernel lock is tied to the inode.
- `flock` through Python's `fcntl.flock` works on both Linux and macOS and needs no Bash 4 or `flock` binary.
- Set the queue wait separately from the run limit in your wrapper. `testrun` does this for its own pre-start wait: `--wait-max SECONDS` bounds the Mac memory-pressure wait before the command starts (exit 75), and `--max SECONDS` counts from the start of the command (exit 124). It does not queue behind compile slots; if your wrapper waits for a cargo-pool slot, give that wait its own limit too. Do not lengthen the execution limit to cover queue time.
- To benchmark (`measurement-lock` is not in the module; build it from this description), drain compiles first and run `measurement-lock -- <benchmark>`: a nonblocking exclusive lock that makes a second cooperating benchmark exit 75. It excludes other benchmarks, not arbitrary load.

**Done when:** with the slot count temporarily set to 2, launching six compiles shows `queue_depth` of at least 4 in `state.json`, and they complete in arrival order (check ticket timestamps in the logs). With the module's gate, the first half is `for i in 1 2 3 4 5 6; do RUSTC_GATE_SLOTS=2 compile-slot-gate rustc -- sleep 5 & done; sleep 1; RUSTC_GATE_SLOTS=2 compile-slot-gate status` (the snapshot's `rustc.queue_depth`, from a shell where `compile-slot-gate` is on `PATH`); strict arrival order is not something the module promises.

### 4. Docker data on unsnapshotted scratch, and test-container GC

Agents that run database tests in Docker leak. In practice a box can accumulate hundreds of anonymous volumes (tens of GB), later well over a thousand, which fills a snapshotted filesystem through its hourly snapshots.

1. Put Docker's `data-root` (images, layers, build cache, container logs) on the scratch filesystem with a quota and no snapshots: `/etc/docker/daemon.json` → `{"data-root": "/var/lib/<scratch>/engine"}`.
2. Make **new volumes default to scratch**, and bind-mount only the few volumes worth protecting from a snapshotted path, one `/etc/fstab` line each. The inverted default (protect by exception) is what stopped the leak; the earlier approach of recognising test container names missed every new name.
3. Add a Docker systemd drop-in that refuses to start the daemon if any of those mounts is missing, so Docker never silently creates unprotected volume data.
4. For known test harnesses, wrap `docker` so test database containers get a unique scratch data dir, `--rm`, and ownership labels (owner pid, start time, process group, boot id). A wrapper is a helper for cooperative harnesses, not a security boundary.
5. Run a garbage collector hourly as root that removes only: containers carrying your disposable-test label, older than six hours, with only anonymous-volume mounts, whose owner process *and process group* are gone (the group check preserves surviving test children); plus anonymous 64-hex volumes older than six hours that no container references, removed without `-f` so Docker itself refuses anything attached meanwhile. Never touch named volumes, bind mounts or legacy unlabelled containers. Without `--apply` the helper should be read-only. Take a shared lock in the test harness while it runs and `LOCK_EX|LOCK_NB` in the GC, so the GC skips ("busy") rather than racing a live test.
6. In harnesses use immutable container IDs and `docker rm -fv` (the `-v` is needed because Docker 26 leaves bind-backed volumes behind on some automatic-removal paths).

**Done when:** after running your database test twice, `docker volume ls -q | wc -l` returns to its baseline; `docker info -f '{{.DockerRootDir}}'` shows the scratch path.

### 5. The Mac: nice 19, every core, never background QoS

Agents on the Mac you type on must not make typing lag, but must still be able to use every core.

- Run every heavy job at **nice 19**, including compiles started outside `testrun` (the compile gate applies `nice -n 19` on Darwin to the compiler and to a server it starts). Nice 19, not 20: a renderer or Node process that calls `setPriority(PRIORITY_LOW)` (19) from nice 20 is attempting an unprivileged raise and dies with EACCES. A process already at nice 20 cannot lower itself to 19, so restart runs from a normal-priority launcher after changing this.
- **Never use `taskpolicy -b` or `taskpolicy -c utility`.** A measurement of 16 processes doing a fixed amount of work: normal 2.5 s, nice 15/20 2.5-2.7 s, `taskpolicy -t 5 -l 5` 2.5 s, `taskpolicy -c utility` 11.1 s (4.5x slower), `taskpolicy -b` 52.6 s (21x slower; confines work to the efficiency cores).
- Nice is a weak lever on macOS: a 2 ms burst after each wake (like a terminal per keystroke) still saw 9 to 15 ms at the 99th percentile under 64 normal-priority spinners, and 7 to 12 ms with them niced. What actually protects typing is limiting concurrency and avoiding memory pressure, so also:
  - **Pause on critical memory pressure only.** `sysctl -n kern.memorystatus_vm_pressure_level` = 4 on two readings 3 seconds apart: SIGSTOP the job; resume after two non-critical readings. (`testrun` applies only the first half of this: it delays a run's *start* while pressure is critical and never stops one that is running.) CPU load and the "warn" level (2) never pause anything: warn happens routinely during a big build. When several jobs run, never pause the oldest, so the fleet keeps making progress.
  - **Slots per Mac:** `testrun` has no machine-wide job cap, so every `testrun` start runs at once. If your Mac types badly under load, add one in your own wrapper (a count read from a config file, `0` meaning no limit). A reasonable default is one heavy job at a time, with no limit overnight for parallel lanes. Move heavy fan-outs to the Linux box when you can.
  - **Clean up the group:** the supervisor starts the job in its own process group and kills the group when the job ends, times out, or its launcher dies. Record the leader's start time and a random token in the slot record so a reused group id never gets signalled.
  - Time limit on the Mac defaults to one hour (two for mutation runs; `testrun` does exactly this), so a legitimate full suite is not killed at 10 minutes.
- Keep Spotlight out of tool folders: add `~/.cache`, `~/.cargo`, `~/.rustup`, `~/.npm`, your agent config directories and `~/Library/Caches` under System Settings → Spotlight → Search Privacy. An indexer can write gigabytes within minutes of boot while it walks millions of files.

**Done when:** `nice -n 19 sh -c 'ps -o ni= -p $$'` prints 19 inside your job wrapper (`testrun demo unit -- sh -c 'ps -o ni= -p $$'`), and the process tree of a finished job is gone (`pgrep -g <pgid>` empty).

### 6. Mac spawn storms: find the poller, not the compile

A sluggish Mac with mostly idle CPU, a very high load average and a large share of system time is not a compile problem. In one case about 90 new processes per second came from a dozen small pollers (a session forking `perl` seven times a second, a git sweep every 15 seconds, a hook calling `security`, a dashboard starting several CLIs, a `while sleep 1` loop). Every new process, even a prompt's `node --version`, waited to start. `ps` sampling cannot see processes under about 300 ms.

What to build, if you hit this:

- A root LaunchDaemon that runs `/usr/bin/eslogger exec` *directly* (not through `sh -c`; macOS attributes Full Disk Access to the responsible program launchd started, so a shell wrapper is refused even if eslogger is granted) and writes JSON lines to a FIFO in a root-owned directory (the FIFO owned by you, mode 0600).
- A user LaunchAgent that reads the FIFO, counts starts per spawner, and alerts. Name the spawner as the first ancestor older than 3 seconds (younger ones are wrappers like `sh -c`, `env`, `timeout`). Keep only the executable, the first dozen arguments, cwd and pids; never store the process environment, which eslogger includes.
- Alert thresholds that worked: total ≥ 40 starts/s, or one spawner ≥ 5 starts/s, averaged over a minute, for 3 minutes in a row; at most one alert per spawner per 3 hours. Overhead was about 2 to 3% of one core during a storm.
- Grant Full Disk Access to `/usr/bin/eslogger` only; never to `/bin/sh`.

This needs root and carries a privacy cost (eslogger's exec events reach your user account including root's processes' environments), so install it only after you have seen the symptom. Before you build anything, capture first. When the machine lags, run, and save the output to a file *before* quitting apps or rebooting:

```bash
uptime; top -l 2 -s 2 -n 0 | grep -E 'CPU usage|PhysMem|Load' | tail -3
ps -Ao pid,pcpu,pmem,etime,command -r | head -15 | cut -c1-150
memory_pressure | grep 'free percentage'; sysctl -n vm.swapusage
ls -lt /Library/Logs/DiagnosticReports | head -8
```

Load above about 10 with mostly idle CPU means processes waiting on disk or the kernel, not computing. A healthy baseline: load under 5, 70%+ idle, 10 GB+ free memory, no swap. Look at the newest `*.cpu_resource.diag` in DiagnosticReports; a `WindowServer` report names the apps that drove it.

**Done when:** you can say which process starts most often per second (your tool's `top`, or `sudo eslogger exec` for a minute and a count by parent), or you have a saved capture to reason from.

## What bit us (papercuts)

- **Build output inside snapshotted worktrees → tens of GiB gone before anyone noticed.** → Route `CARGO_TARGET_DIR` to an unsnapshotted, quota'd directory from day one.
- **`mise activate` (and similar) re-orders PATH on every prompt, putting `~/.cargo/bin` ahead of your managed `cargo`.** Agents launched from that shell bypassed the wrapper and wrote tens of GiB into the shared root target. → Re-pin your wrapper directory after any PATH-manipulating hook in the shell rc, test it, and give the pruner a backstop that empties bypass output under pressure. Running sessions keep the old PATH until relaunched.
- **A pool of shared targets recycled between worktrees → Cargo thought stale artifacts were fresh.** → One target per worktree identity.
- **sccache saw 0 hits across worktrees.** Cause: `CARGO_TARGET_DIR` hashed into the key. → Unset the three target variables before `exec sccache`.
- **sccache server started inside a job's cgroup → the job waited out the server's 10-minute idle timeout; or server inherited a build's lock fd and blocked cache cleanup.** → Start it as a separate transient unit, or with close-fds.
- **The pruner crashed (exit 2) on a zombie process** whose `/proc/<pid>/fd` is unreadable. → Treat zombies as absent.
- **Six unrelated unreadable system processes made every user prune stop at "process unknown".** → Fail closed only when the unreadable process's command line names a build tool or mentions the scratch root.
- **Fast timer plus slow audit → every pass timed out and looped.** → Bound the fast pass, put slow work in an hourly unit with its own receipt, and make the health check fail if the hourly receipt is stale (over 3 hours).
- **Whole container OOM-killed just under its memory limit.** → Memory-headroom admission for high compile slots; the cap is memory, not cores.
- **Around a hundred queued compilers polling slot files burned the Mac.** → Only the head waiter polls; others sleep in `flock`.
- **A waiting job counted against its execution time limit.** → Separate admission wait (`--wait-max`) from run time (`--max`).
- **Docker test volumes: name-based recognition failed on every new test name (over a thousand volumes).** → Default volumes to unsnapshotted scratch; protect by exception.
- **`docker run --rm` with bind-backed volumes leaves directories behind on Docker 26.** → `rm -fv` with immutable IDs.
- **`taskpolicy -b` for "low priority" made builds 21x slower.** → nice 19 only.
- **nice 20 broke tools that set their own low priority (EACCES).** → nice 19.
- **A Mac with idle CPU and a very high load was blamed on compiles; it was about ninety process starts a second.** → Count process starts before throttling compiles.
- **A background indexer, an app's screen capturing, and a memory tool rewriting a large state file hundreds of times per half-hour each caused "slowdowns".** → Capture the evidence (disk-write rates, DiagnosticReports) before rebooting; per-process write counters are lifetime totals, so diff two snapshots.

## Reference snippets

Environment for a box that has adopted everything:

```bash
# ~/.config/environment.d or shell profile
export RUSTC_GATE_SLOTS=12          # 8 on a Mac
export SCCACHE_CACHE_SIZE=15G
export SCCACHE_DIR="$HOME/.cache/sccache"
# per-command opt-outs: RUSTC_GATE_SCCACHE=0
```

Timer for the pruner (system or user unit; the service is `Type=oneshot` so runs never overlap):

```ini
# estate-build-cache.timer
[Timer]
OnCalendar=*:0/5
RandomizedDelaySec=30
[Install]
WantedBy=timers.target
```

Slot-queue ticket check (the core of FIFO admission): a waiter may take slots only if

```python
older = [t for t in glob("wait-*") if t != mine and key(t) < key(mine) and is_flocked(t)]
if not older: try_take_slots()
```

where `key` is `(time_ns, pid)` parsed from `wait-<time_ns>-<pid>` and `is_flocked` tries a nonblocking flock and treats success as "dead ticket".

## Keeping it healthy

- Watch `state.json` (`queue_depth` sitting above zero for long means too few slots or a stuck holder) and the pruner's `maintenance.json` receipt (usage before and after, `retained` reasons, `deadline_reached`, `hourly_stale`).
- Add health rows: build-cache pruner timer active and last pass under two hours old; no Rust output outside scratch; Docker volume count growth (a jump of 100 or more anonymous 64-hex names over a day is a leak signal, never deletion authority). Treat the first day of growth history as baseline; missing history is unknown, not zero growth.
- Never delete snapshots to make a graph look better; deleted blocks stay allocated until snapshots expire. Keep scratch datasets out of snapshot schedules.
- Never treat `/var/lib/docker/volumes` as a stale Docker root to delete when it holds your protected bind-mounts.
- To reset the compiler cache: `sccache --stop-server && rm -rf ~/.cache/sccache`.
- After a macOS upgrade, re-check Spotlight exclusions and that the nice wrapper still applies.

Last checked: 2026-10, Debian 12/Ubuntu 24.04 and macOS (the Mac compile-slot path is only partly verified natively).
