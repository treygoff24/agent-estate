# Storage that survives agents: ZFS datasets, snapshot budgets, and off-box backups

This guide sets up the storage layer under a box that runs coding agents, build caches and
containers: ZFS datasets that separate state worth keeping from churn worth throwing away,
snapshot retention that is bounded by **size** as well as age, quotas that fail in the right
order, disk-backed `/tmp`, and a restic backup that reads a frozen snapshot instead of a live
filesystem. Read it if you have ever had an agent fill a disk, or want one-command rollback of
a wrecked checkout. The hard part is not creating datasets; it is that **deleting a file frees
nothing until the snapshots holding it age out**, and every choice below exists because that
fact took the box down.

## Do you need this?

**Skip it** if: one machine, one agent at a time, a plain ext4/btrfs root, and enough free disk
that a bad day is annoying rather than fatal. A single rented VPS with one developer does not
need any of this. Snapshot budgets and per-dataset quotas are answers to *several agents on
one box*.

**Do it** if two or more of these are true:

- you run containers (Incus, LXD, Docker) or several agent harnesses on one machine;
- your work involves build caches, test databases, or container images that can grow by tens
  of GB in an afternoon;
- you want a rollback point before each agent session, and cheap off-box backups;
- you have already filled a disk once.

**What it costs:** a dedicated disk or pool (ZFS wants real devices, not a loop file), some RAM
for the ARC cache (a cap of 4–16 GiB is fine on a 32 GiB box), and the operational weight of
one more timer plus a monthly look at `zpool status`. sanoid is packaged on Debian/Ubuntu; no
third-party Python is needed.

## Prerequisites

- A recent Debian/Ubuntu host (or any distro with OpenZFS and `sanoid`), root access, and at
  least one spare disk. Mirror the disk if the data matters: one device means one failure from
  losing everything.
- The host baseline from agent-estate's `baseline` module (time sync, unattended security
  updates) applied first, so the box is trustworthy before it holds state.
- A backup target: any S3-compatible bucket (Backblaze B2, Storj, S3, MinIO) and a restic
  password stored somewhere a human can reach when the box is gone. Not on the box.
- Decide your pool name once. This guide uses `tank`; the scripts assume `tank`.

## Steps

### 1. Create the pool

Encrypt it if the box travels or if the disk could leave your hands. Native ZFS encryption
means the key must be available at boot for unattended start, which is a tradeoff: an
unattended-unlock keyfile on the root disk protects against a *removed* disk, not against a
stolen whole machine. Decide deliberately.

```sh
# mirrored, encrypted; you will be prompted for a passphrase
sudo zpool create -o ashift=12 -O compression=lz4 -O atime=off \
  -O encryption=on -O keyformat=passphrase tank mirror /dev/disk/by-id/<disk-a> /dev/disk/by-id/<disk-b>
sudo zfs set mountpoint=/tank tank
```

**Done when:** `zpool status tank` shows the pool ONLINE with no errors, and
`zfs get encryption tank` says `on` (or you have written down why it is off).

### 2. Shape the datasets: keep state and churn apart

The organising rule: **a dataset either holds state you would restore, or it holds something
rebuildable. Never mix the two.** Snapshotted datasets stay small and few; scratch datasets
carry their own quota and take no snapshots.

```sh
sudo ./datasets.sh     # the script in the reference snippets below, run as root
```

That creates, under `tank`:

| Dataset | Why |
| --- | --- |
| `tank/control/*` | git remotes, mail store, service state — snapshotted, never scratch |
| `tank/cells` | handed to Incus as a storage pool source; Incus owns every child |
| `tank/browser/*` | browser profiles: sensitive, `atime=off` |
| `tank/archives/*` | durable archives, separated by project from day one |
| `tank/scratch` | `quota` + `com.sun:auto-snapshot=false` — build caches, container images, worktrees |

**Done when:** `zfs list -r -o name,used,avail,quota,mountpoint tank` shows the tree, and
`zfs get com.sun:auto-snapshot tank/scratch` says `false`.

### 3. Retention with sanoid, per workload

One template per kind of data. The values that worked: control plane frequent (4 per hour,
15-minute period) + 24 hourly + 14 daily + 3 monthly; work data 24/14/3; **container cell
roots 6 hourly + 7 daily + 1 monthly**; delegate worktrees hourly only.

```sh
sudo apt-get install -y sanoid
sudo install -d /etc/sanoid
sudoedit /etc/sanoid/sanoid.conf   # paste the config from "Reference snippets", rename the datasets
sudo systemctl enable --now sanoid.timer
```

Why so few hourlies on cell roots: hourly snapshots of a container root are the default
victim of any churn, and six hours of churn is a disk-full you can still dig out of, while
twenty-four is a day of it.

**Done when:** `systemctl is-active sanoid.timer` says `active` and, after an hour,
`zfs list -t snapshot -o name,creation -d 1 tank/cells/containers/<cell> | head` shows an
`_hourly` snapshot from this hour.

### 4. Add a size budget on top of age pruning

Age pruning alone is not enough: a burst of churn makes every retained hourly fat at once.
This script trims the **oldest `*_hourly`** snapshots of named datasets until
`usedbysnapshots` is under a byte budget, never touches dailies or monthlies, and never
destroys a snapshot named in the keep file.

```sh
# install the pruner script + systemd unit yourself (shape in "Reference snippets"),
# then declare the budget per dataset:
sudo install -d -m 0755 /etc/estate
sudo tee /etc/estate/snapshot-budget.conf >/dev/null <<'EOF'
# <dataset> <snapshot budget GiB>
tank/cells/containers/<cell> 100
EOF
# the keep list is live operator state: create it once, never let an installer overwrite it
sudo test -e /etc/estate/snapshot-keep || printf '# one snapshot name per line; never destroyed\n' | sudo tee /etc/estate/snapshot-keep >/dev/null
sudo systemctl enable --now estate-snapshot-budget.timer
```

Two behaviours worth keeping when you write your own:

- if a dataset is still over budget with no prunable hourly left, **exit 1** so the unit shows
  failed. A silently over-budget dataset is the thing this exists to prevent.
- a safety cap on how many snapshots one run may destroy (`MAX_DESTROY`, default 48) so a
  misconfigured budget cannot eat a week of history in one tick.

`/etc/estate/snapshot-keep` is live operator state: one snapshot name per line, and the pruner
skips those. When you take a snapshot before a risky change, write its name there so no timer
can age it out from under you.

**Done when:** `systemctl start estate-snapshot-budget.service; sleep 2;
systemctl is-failed estate-snapshot-budget.service` reports `inactive` (not failed), and
`journalctl -u estate-snapshot-budget -n 20` shows either a budget-compliant line or a
`destroying` line per dataset.

### 5. Quotas that fail in the right order: `refquota` for live files, `quota` as a backstop

This is the single most important lesson in the guide. With only `quota`, **snapshot growth
counts against the same ceiling as your writes**, so a dataset at 60% with a week of hourlies
can fail an agent's write while `df` says there is plenty of room. Put the real limit on the
live filesystem and leave headroom above it for snapshots:

```sh
sudo zfs set refquota=300G quota=600G tank/cells/containers/<cell>
```

- `refquota` bounds the live filesystem only; writes fail at 300G.
- `quota` bounds live + snapshots; 600G gives snapshot growth its own room and is a backstop
  against a snapshot leak, not a write limit.
- Alert on the **live** number against `refquota`, and on `usedbysnapshots` separately.

**Done when:** `zfs get -o property,value refquota,quota,used,usedsnap tank/cells/containers/<cell>`
shows both limits set, and your health check reports the live percentage against `refquota`.

### 6. Move churn onto unsnapshotted datasets

Everything below belongs on `tank/scratch/*` with a quota, mounted at its normal path, taking
no snapshots: container images and volumes, cargo target dirs, npm/rustup registries, `/var/tmp`,
agent run scratch, delegate worktrees. Do this **before** you cut a cell's snapshot retention
down, or your hourlies are full of compile output.

The safe migration shape, done hot with no restart of the workload:

1. create the dataset with the quota and mountpoint you want;
2. `rsync -aHAX --numeric-ids` the live path into it, then a catch-up pass;
3. attach it (an Incus disk device with `shift=true`, a bind mount, or a config change);
4. compare file counts against the original;
5. delete the shadowed originals **keeping any entry a live process still uses** — you will
   find a handful you cannot remove, and those are correct to leave.

**Done when:** `findmnt -T /tank/scratch/<name>` shows the dataset as `SOURCE` on the mount
holding the path (`findmnt -T <path>` reports the same filesystem), the quota reads what you
set, and the workload still runs (`cargo metadata --offline`
resolves, `docker info` shows the new data root, `npm cache verify` passes).

### 7. Disk-backed `/tmp` (optional, but do it if your builds use `/tmp`)

A tmpfs `/tmp` is RAM: a 20 GB build artefact in `/tmp` on a 32 GiB box is an OOM kill. If
`/tmp` is where compilers, test runners and container clients write, back it with a dataset.
Never replace the live mount under running work: stage the drop-in, then let the next boot
activate it.

```ini
# /etc/systemd/system/tmp.mount.d/50-estate-disk.conf
[Unit]
Requires=zfs-mount.service
After=zfs-mount.service
RequiresMountsFor=/tank/scratch/<host>-tmp
AssertPathIsMountPoint=/tank/scratch/<host>-tmp

[Mount]
What=/tank/scratch/<host>-tmp
Type=none
Options=bind,nosuid,nodev
```

`AssertPathIsMountPoint=` is the line that saves you: without it, if ZFS has not mounted yet,
systemd happily binds an empty directory on the root disk as `/tmp` and nothing tells you.

**Done when:** after a reboot, `findmnt -o SOURCE,FSTYPE,OPTIONS /tmp` shows the dataset as the
source with `nosuid,nodev`. Wait for `systemctl is-active tmp.mount` before starting work — a
container restart command returns before in-container mounts are ready.

### 8. Back up from frozen snapshots, not from a live tree

Backing up a live directory gives you a file that is half-written. Instead: mount each
dataset's newest snapshot read-only, back up the mount, unmount.

```sh
# core of the backup script; see snippets
for ds in $DATASETS; do
  snap=$(zfs list -t snapshot -H -o name -S creation -d 1 "$ds" | head -1)
  mount -t zfs -o ro "$snap" "/run/restic-mounts/$(echo "$ds" | tr '/' '-')"
done
restic backup --retry-lock 20m --tag auto $PATHS /etc /usr/local/sbin
restic forget --retry-lock 20m --tag auto --keep-hourly 24 --keep-daily 14 --keep-weekly 8 --keep-monthly 12
```

Also back up `/usr/local/sbin` and the tooling itself, so a rebuilt box can restore the
scripts that do the restoring. Keep the restic repo password and the bucket key in a password
manager, not on the box.

**Done when:** `restic snapshots --tag auto` lists a snapshot from tonight, and
`restic check --read-data-subset=10%` passes once a week on a timer.

### 9. Make the numbers visible, and alert on the ones that fill

`df /` lies about ZFS: it hides snapshots and it never shows scratch quotas. Collect the real
numbers hourly and alarm at 80% of *any* quota:

```sh
zfs list -H -p -o name,used,quota,usedsnap -r tank/cells/containers tank/cells/scratch \
| awk '$3 > 0 { pct = int($2*100/$3); printf "%s %dG/%dG %d%% (snap %dG)\n", $1, $2/2^30, $3/2^30, pct, $4/2^30;
         if (pct >= 80) printf "ALARM %s at %d%% of quota\n", $1, pct }'
```

**Done when:** the hourly report carries one line per quota'd dataset with its snapshot share,
and an `ALARM` line appears when you deliberately fill a test dataset past 80%.

## What bit us (papercuts)

- **Deleting a file can free nothing for a week.** A container root's `df` showed plenty of
  its quota free after a cleanup, and the box still failed writes: the deletions had landed
  **in snapshots** (USEDSNAP), which `df` does not show. → Before believing a cleanup, read
  `zfs list -o used,refer,usedsnap,quota`; a cleanup only frees space as snapshots age out, or
  when you destroy them deliberately.
- **Agents died on write errors while the pool was healthy.** A cell root sat
  at its ceiling because snapshots and live files shared one quota. → `refquota` for live files,
  `quota` as a higher backstop, fewer hourlies, and a size pruner: after the change, live usage
  sat well under `refquota` with a modest snapshot share.
- **A cloud-sync mount's local cache filled the box.** An `rclone mount` with a large VFS cache
  can write tens of GB in an afternoon, straight into hourly snapshots; a cell hit zero free and its
  agents died. → Point the mount's cache at an unsnapshotted scratch dataset and cap it
  (`--vfs-cache-max-size`), and ask what read that much before re-enabling the mount.
- **Over a thousand leaked test-database volumes churned the snapshotted root.** A test harness created
  anonymous container volumes under names a cleanup adapter did not recognise; they landed on
  the protected root and filled it through hourly snapshots. → Container images, build cache
  and *default* volumes go on unsnapshotted scratch; only volumes worth protecting are
  bind-mounted from the snapshotted dataset, one explicit config line each. A default that is
  rebuildable is a default nobody has to clean up.
- **Scratch quotas were invisible.** The cargo scratch dataset sat near its quota and nothing
  noticed, because `df /` never sees another dataset's quota. → Alarm per quota'd dataset
  (step 9), not on the root filesystem.
- **A `/tmp` mount drop-in can silently bind the root disk.** If the backing dataset is not
  mounted yet, the bind succeeds against an empty directory. → `AssertPathIsMountPoint=` plus
  `Requires=`/`After=` on the ZFS mount units; verify the source with `findmnt` after boot.
- **Hot-migrating a populated path leaves entries behind.** A few `/var/tmp` entries could not
  be deleted after the cutover because live processes held them. → Keep the originals a running
  process still uses, note them, and let them age out with the next restart. Deleting them
  underneath a live process is how you get a mystery failure later.
- **Two backup runs overlapped and one died.** An hourly forget (exclusive lock) waited on the
  nightly job's repo lock, and the run was killed without retries. → `--retry-lock 20m` on every
  restic invocation in every timer, and stagger the schedules.
- **Snapshots are not a cleanup cosmetic.** Do not destroy snapshots to make a space graph look
  better; if a block is still referenced by a snapshot, that snapshot is the reason the data is
  recoverable.
- **The snapshot you need for an incident gets aged out.** That is what the keep list is for:
  write the snapshot name to `/etc/estate/snapshot-keep` when you take the pre-change snapshot,
  and read it back with `zfs list -t snapshot` before you start the risky step.

## Reference snippets

`datasets.sh` — idempotent dataset shape (run as root; converge, never destroy):

```sh
#!/bin/bash
set -u; set -o pipefail
POOL=tank
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
command -v zfs >/dev/null 2>&1 || die "zfs not found"
zpool list "$POOL" >/dev/null 2>&1 || die "pool $POOL not imported"

ensure() {                      # ensure <dataset> [prop=value ...]
  local ds="$1"; shift
  zfs list "$ds" >/dev/null 2>&1 || { zfs create -p "$ds" || die "create failed: $ds"; }
  local kv; for kv in "$@"; do zfs set "$kv" "$ds" || die "set $kv failed on $ds"; done
}

ensure "$POOL/control"
ensure "$POOL/control/git"
ensure "$POOL/control/mail"
ensure "$POOL/cells" canmount=off            # Incus owns all children
ensure "$POOL/browser" atime=off
ensure "$POOL/archives"
ensure "$POOL/scratch" quota=200G atime=off com.sun:auto-snapshot=false
zfs list -r -o name,used,avail,quota,mountpoint "$POOL"
```

`/etc/sanoid/sanoid.conf` — one template per workload:

```ini
[tank/control]
  use_template = control
  recursive = yes
[tank/archives]
  use_template = work
  recursive = yes
[tank/cells/containers]
  use_template = cells
  recursive = yes

[template_control]
  frequently = 4
  frequent_period = 15
  hourly = 24
  daily = 14
  monthly = 3
  autosnap = yes
  autoprune = yes
[template_work]
  hourly = 24
  daily = 14
  monthly = 3
  autosnap = yes
  autoprune = yes
[template_cells]
  hourly = 6
  daily = 7
  monthly = 1
  autosnap = yes
  autoprune = yes
```

The size-pruner's inner loop — the shape is the point, not the exact code:

```sh
while :; do
  snap_b=$(zfs get -Hp -o value usedbysnapshots "$ds")
  [ "$snap_b" -le "$budget" ] && break
  victim=$(zfs list -H -t snapshot -d 1 -o name -s creation "$ds" \
    | grep '_hourly$' | grep -vxF -f <(keep_patterns) | head -n 1 || true)
  if [ -z "$victim" ] || [ "$destroyed" -ge "$MAX_DESTROY" ]; then
    log "WARN $ds: over budget $(gib "$snap_b") with nothing prunable"; rc=1; break
  fi
  zfs destroy "$victim"; destroyed=$((destroyed + 1))
done
```

## Keeping it healthy

- **Weekly:** `zpool status -x`, `zpool list -o name,size,alloc,free,health`, and the health
  check's quota table. Check `systemctl --failed` for a red snapshot-budget unit.
- **Monthly:** `restic check --read-data-subset=10%` (on a timer), `sanoid --monitor-snapshots`
  if you have it wired, and one deliberate restore of a small file from last night's snapshot
  so you know the path works.
- **Quarterly:** look at `usedbysnapshots` per dataset and decide whether the retention numbers
  still match how you work. Fewer hourlies is almost always the right answer.
- **When a disk fills:** read `zfs list -o used,refer,usedsnap` first, then prune by policy
  (budget config), then destroy a specific snapshot you have decided is expendable. Never
  `zfs destroy -r` a dataset to make room unless you have already restored what it held.
- **When you change retention:** change the config, re-run the installer, and read the
  config back from `/etc` rather than trusting the repo copy.

Last checked: 2026-10, Debian 13.
