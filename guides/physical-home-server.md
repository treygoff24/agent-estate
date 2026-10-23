# Running the box at home instead of renting a VPS

A rented VPS gives you power, cooling, a UPS and a KVM for free; a Linux box in your house gives
you a machine that does not exist until your home internet, your BIOS and your power supply all
agree, and where a thermal event means the room is hot and the fan is loud. This guide is the
set of host-level choices that make a home box behave like a server: a CPU ceiling and a thermal
watchdog you can actually apply without vendor hacks, a BIOS that comes back after a power cut,
a host baseline whose updates never reboot your agents, a boot sequence that **starts services
and never replays work**, and health checks that answer "is it fine now" and "what changed since
I last looked" separately. It assumes you already have agent-estate's core installed (`INSTALL.md`) and are now
making the physical host trustworthy.

## Do you need this?

**Skip it** if you rent a VPS: the provider owns power, cooling, disk health and console access,
and nothing here applies except the boot sequence and health checks (which the `baseline` and
`health` modules cover).

**Do it** if your agents run on hardware you can touch, especially:

- a mini-PC or tower in a room you also live in (thermal and noise limits are real);
- any box with an encrypted or single-disk root where a power cut means an unattended boot
  either comes back or does not;
- a box that agents reach from outside, so an unattended reboot must not need a human.

**What it costs:** a UPS sized to the box (a 60–120 W mini-PC rides out a short outage on a
small one), a KVM-over-IP or a monitor and keyboard you can plug in twice a year, roughly
30–100 W continuous, and one scheduled hour for the console session (see step 3 — this is the
step people postpone for months; do not).

## Prerequisites

- The `baseline` module's host baseline (time sync, unattended security updates, optional zram
  swap; [modules/baseline/README.md](../modules/baseline/README.md)), plus the `health` collector
  if you want the morning report. Step 4 below converges the same things on hardware you own,
  plus the parts a VPS provider handles for you.
- Physical or KVM access to the machine. Several steps below are BIOS work and cannot be done
  over SSH; a scheduled "console session" with the machine in front of you is a prerequisite,
  not a nice-to-have.
- A UPS with a USB monitoring cable if you want a clean shutdown rather than a hard cut.
- Agent sessions running in containers or as unprivileged users, never as host root: nothing
  here should ever require an agent to hold host sudo.

## Steps

### 1. Put a ceiling on the CPU, using the driver's own controls

Do not write vendor SMU/undervolt registers from userspace: with Secure Boot lockdown active
those writes are refused, and they are the kind of change that survives a reboot in a state you
cannot see. Use the kernel's `cpufreq` interface instead: cap `scaling_max_freq` and set the
energy-performance preference, on every core.

Prerequisites on the host: an AMD CPU on the `amd-pstate-epp` driver (check
`cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver`), and the governor exposing
`energy_performance_available_preferences`.

```sh
# install two scripts and three units yourself (names in "Reference snippets"):
#   estate-power-cap.sh        oneshot at boot: apply the ceiling
#   estate-power-cap-audit     timer: re-apply drift
#   estate-thermal-watch       timer: the watchdog in step 2
sudo systemctl daemon-reload
sudo systemctl enable --now estate-power-cap.service estate-power-cap-audit.timer estate-thermal-watch.timer
sudo /usr/local/sbin/estate-power-cap.sh status
```

Three design choices to copy:

- **Status is readable without root**, and prints the values as facts:
  `cpus=<n> max_freq_khz=<ceiling> epp=balance_performance boost=1 compliant=yes`.
- **An audit timer re-applies drift.** Something (a kernel update, a vendor daemon, a resume
  from suspend) will reset these values; the audit unit restores them and logs a `DRIFT:` line
  instead of silently hoping.
- **The thermal watchdog outranks the ceiling.** While the watchdog has boost disabled, the
  ceiling script must log `DEFER:` and touch nothing. Two guards fighting over the same register
  is how a hot box gets *more* boost.

**Done when:** `estate-power-cap.sh status` prints `compliant=yes`, and
`systemctl is-active estate-power-cap-audit.timer estate-thermal-watch.timer` prints `active`
twice.

### 2. Add a thermal watchdog you can actually act on

On many consumer boards the fan is EC-controlled and there is no OS write path (`pwm1` absent,
or writes ignored). The only lever left is CPU boost: drop it when the package runs hot, restore
it when it cools. That is a coarse control, and it is enough to stop a thermally unstable
machine from wedging under a compile storm.

```sh
# TRIP_MC/CLEAR_MC are millidegrees; sensor is k10temp's Tctl
TRIP_MC=92000 CLEAR_MC=80000 /usr/local/sbin/estate-thermal-watch.sh
logger -t estate-thermal -p user.info "watchdog check"   # or read journalctl -t estate-thermal
```

Behaviours that matter:

- **Trip on three consecutive samples**, not one; a single hot reading during a build is normal.
- **Only restore boost if this script disabled it** (a state file records the trip). Never
  re-enable a boost something else turned off.
- **A missing sensor is not an action**: log "not readable; no action" and exit 0, so an
  unknown sensor never turns into a mystery boost change.

**Done when:** `journalctl -t estate-thermal -n 5` shows either a `TRIP`/`CLEAR` line or a
`no action` line, and `/run/estate-thermal/` exists (the state directory the pair of scripts
share).

### 3. Schedule the console session: BIOS, power, network identity

This is the step that gets deferred. It needs your hands, a monitor or KVM, and about an hour.
Do all of it in one sitting:

1. **BIOS → "Restore on AC Power Loss" = Power On.** Without it, a power cut longer than the UPS
   leaves the box off until someone presses the button. A server that needs a human to press a
   button is not a server.
2. **BIOS/Firmware → disable anything that hides the machine at boot** (boot splash, "wait for
   F1 on error", fast boot that skips POST error reporting). A machine that stops on an unseen
   keypress is down.
3. **Pin the network identity.** A DHCP reservation on the router (by MAC) or a static address,
   so the box's address survives a lease change. Then confirm from the LAN and from outside.
4. **Fan/thermal policy in BIOS**: if the board offers a fixed PWM or a "performance/quiet"
   profile, pick the one that keeps the machine cool under sustained load; you cannot change it
   from the OS later.
5. **Plug the UPS in and prove it**: pull mains power for 60 s with the box idle, watch it stay
   up, plug back in. If you have a monitoring cable, wire a shutdown hook so a long outage ends
   in a clean stop, not a hard cut.
6. Write down what you changed, where, and what the pre-change setting was.

**Done when:** you have pulled mains power for a minute and the box came back by itself — not
"the setting looks right", but an actual power-cut test with the machine returning to service.
Do this test at a moment when nothing important is running.

### 4. Host baseline: updates that never reboot you, swap that is not a disk

The baseline is one idempotent script, run as root, converging rather than installing fresh
each time:

```sh
# write host-baseline.sh from the snippet in "Reference snippets", then:
sudo ./host-baseline.sh     # converges; prints its own verification block
```

What it should do, and why each piece is there:

- **Unattended security updates with `Unattended-Upgrade::Automatic-Reboot "false"`.** Security
  patches install themselves; the reboot is a decision. Include only third-party repos whose
  packages are safe to take unwatched; leave anything that sits under a running agent lane on
  manual.
- **`needrestart` in list-only mode** (`$nrconf{restart} = 'l'`), so the box *reports* services
  that want a restart and never bounces one underneath a session.
- **zram swap first**, disk swap demoted below it (`pri=`) or absent. zram converts swap
  pressure into CPU instead of disk latency, which is what makes a small home box survivable
  during a build storm.
- **A time daemon (chrony) enabled.** Agent work depends on TLS, tokens and logs agreeing on the
  time; an unsynced clock fails in confusing ways.
- **A ZFS ARC cap** if you use ZFS (a modprobe parameter plus the live sysfs write), and a
  ptrace scope of 1 if secrets live in an agent cockpit on the box.
- **Idempotence**: re-running the script must converge, not duplicate. It ends by printing its
  own verification lines so the check is part of the script.

**Done when:** the script's verification block prints `chronyc tracking`, `swapon --show`, the
ARC cap, and `systemctl is-active` for each unit, and a second run changes nothing (diff the
`systemctl show -p ActiveEnterTimestamp` values before and after).

### 5. Boot sequence: start services, never replay work

The rule that keeps a home reboot boring: **a reboot never replays agent work.** After boot, a
one-shot unit may start resident containers, mark anything that was `running` as
`reconcile-required`, append exactly one boot event, and run the reconcile hooks for the network
and service sockets. It must not resume prompts, leases, tasks, shell commands or queued jobs.

```sh
systemctl status estate-reconvene.service --no-pager
journalctl -u estate-reconvene --no-pager -n 40
```

Hook order that works: start cells → reconcile network membership and **confirm** it → repair
service sockets → mark interrupted runs → emit one boot event. Any hook that cannot verify its
result **fails the unit loudly, before runs are marked**, so the next boot's failure is visible
rather than silent. After it finishes, the human or an agent inspects the status and decides what
to restart.

**Done when:** after a reboot, `estate-reconvene.service` is `inactive (dead)` with exit 0, one
boot event exists, and no interrupted task is still marked `running`.

### 6. Ship the kernel log somewhere agents can read it

When the box wedges or a disk drops, the useful evidence is in the kernel log, and the agent
never has host root. Give it a path: mirror kernel messages to a shared file and rotate it.

```
# /etc/logrotate.d/estate-kernel-log
/var/log/estate-cell-share/kernel.log {
    weekly
    rotate 4
    maxsize 50M
    compress
    missingok
    notifempty
    copytruncate
}
```

`copytruncate` matters because the writer (a journal tail, a `dmesg` loop, a serial console
capture) holds the file open; rotating by rename would leave it writing to the unlinked inode.

**Done when:** `logrotate -d /etc/logrotate.d/estate-kernel-log` parses clean, and the shared
path exists and grows after a reboot.

### 7. Health checks that separate "now" from "since you looked"

Two questions, two answers. A single "green/red" dashboard loses the distinction, and the
distinction is what stops the morning triage from re-reading the same alarm every day.

- **`severity`** (ok / warn / crit / unknown) and the process exit code say how the host is
  *right now*. Map exit codes so a script can use them: 0 ok, 1 warn, 2 crit, 3 no report.
- **`attention`** says whether anyone needs to look again. An `ack` records every warn and crit
  in the report it triaged; afterwards a warn is news only when it is *new* (a new check id, a
  new failed unit inside a units check) and a crit always is. A known finding is forgotten once
  that check has read ok for a day, so a relapse later is news again.
- **A missing tool or a failed network call is `unknown`, never `ok`.** An instrument that
  cannot see is not reporting health.
- **Collectors are read-only.** No kill, no delete, no restart, no write outside their own state
  directory; the collector that repairs things is a different program with a different failure
  mode.

**Done when:** `estate-health --json` produces a report with per-check severity, exit codes track the
worst severity, and `estate-health ack` followed by a re-collect shows the previously-known warns as
`ack.known` rather than new attention.

### 8. Measure the home network before you change the router

Only if your agents are on Wi-Fi to this box. Record a baseline from the client, change one
thing, re-run the same test. Two findings, both worth knowing before you buy hardware:

- **Peer-to-peer Wi-Fi features cause latency spikes and packet loss**, not weak coverage. On a
  Mac, AWDL (AirDrop/Continuity) can drop pings on a strong, quiet channel; turning AirDrop off
  is the test.
- **Frequent Wi-Fi scanning causes latency spikes.** A local stats or menu-bar app that asks for
  a live Wi-Fi scan every few seconds produces bursts of multi-second spikes that look like a
  router problem. Turn that module off before changing the router.

The test (from the client, on Wi-Fi, default route on the Wi-Fi interface):

```sh
route get default | grep interface        # must be the Wi-Fi interface
ping -c 300 -i 0.2 <host-address>         # summarize: loss, avg, count over 30 ms, max
```

**Done when:** you have a before/after table with the same command, same duration, same path.

## What bit us (papercuts)

- **After a reboot, a service socket inside the container was dead while its config looked
  perfect.** The proxy device bound the socket into the container's rootfs `/run` *before* the
  tmpfs mounted over it, so the path existed and nothing listened. → The boot reconcile must
  **probe the socket from inside** the cell (`incus exec <cell> -- test -S /run/<service>.sock`),
  bounce only the device when that is the *only* finding, read the config back after the bounce,
  and fail the boot loudly if it is still dead. A device that is present but whose path is dead
  is the real failure shape; a missing device is drift and must not be "repaired" by a bounce.
- **A BIOS setting nobody scheduled stays unset for months.** Restore-on-AC, the DHCP
  reservation and the KVM/UPS purchases sit in a pending list waiting for a console session. → Put the console session on the calendar with a checklist (step 3), and treat the
  power-cut test as the finish line. Anything that needs physical access is a scheduled task,
  not a background intention.
- **The fan could not be controlled from the OS at all.** Fan PWM was EC-locked; the only
  controllable lever was CPU boost. → Say that out loud in your design: if the only lever is
  boost, the watchdog must trip at a temperature that leaves headroom, and it must never fight
  a ceiling script for the same register.
- **A userspace vendor tool wanted to write SMU registers while Secure Boot lockdown was
  active.** Those writes are refused under lockdown. → Use the native `cpufreq` ceiling plus
  EPP, which no lockdown blocks, and keep the third-party frequency tool out of the boot path.
- **A reboot kills more than expected.** Agent sessions and long-lived harness hosts die with
  the box, and some sessions must be relaunched by hand from a saved list. → Keep a
  short file listing the services and sessions you relaunch after a reboot, and drain agents
  before an intentional reboot rather than discovering what was running afterwards.
- **A "quick" reboot became an outage because one hook failed silently.** A boot hook that
  cannot verify its postcondition and exits 0 makes the next boot look fine while the service is
  dead. → Every hook verifies its own result and fails the unit; a partially reconciled boot is
  an alarm, never a quiet success.
- **A deployment step was assumed to be one step and was two.** The installer's own output said
  `provision: ok (not enabled, not started)`, and the service stayed down until someone enabled
  it deliberately. → Read the installer's last line, and make "installed" and "enabled" separate
  visible decisions.
- **Wi-Fi jitter is easily misdiagnosed as a router problem.** Local software causes (AWDL, a
  stats app's periodic scan) can explain all of it. → Baseline, change one variable, measure
  with the same test; and remember that pinging LAN addresses from an agent session on a Mac can
  fail for permission reasons, so ping the tailnet/overlay address that travels the same hop.

## Reference snippets

`host-baseline.sh` — the convergence shape (run as root; idempotent; ends by proving itself):

```bash
#!/bin/bash
set -u; set -o pipefail
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root"
export DEBIAN_FRONTEND=noninteractive

apt-get install -y chrony unattended-upgrades needrestart zram-tools >/dev/null || die "apt install failed"
systemctl enable --now chrony >/dev/null 2>&1

# security updates: install automatically, never reboot
cat > /etc/apt/apt.conf.d/52-unattended <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Origins-Pattern:: "origin=Debian,codename=${distro_codename}-updates,label=Debian";
EOF
[ -d /etc/needrestart/conf.d ] && printf "\$nrconf{restart} = 'l';\n" > /etc/needrestart/conf.d/50-list-only.conf
systemctl enable --now unattended-upgrades >/dev/null 2>&1

# zram swap first
printf 'ALGO=zstd\nSIZE=8192\nPRIORITY=100\n' > /etc/default/zramswap
systemctl enable --now zramswap >/dev/null 2>&1 || systemctl restart zramswap

# ZFS ARC cap: conservative start, tune from pressure
echo "options zfs zfs_arc_max=8589934592" > /etc/modprobe.d/zfs-arc.conf
echo 8589934592 > /sys/module/zfs/parameters/zfs_arc_max 2>/dev/null || true

echo "--- verification ---"
chronyc tracking | head -2
swapon --show
grep -h . /sys/module/zfs/parameters/zfs_arc_max
systemctl is-active chrony unattended-upgrades zramswap
```

The thermal watchdog's core, and the reason it needs a state file:

```bash
# find the CPU package sensor by name, never by hwmon index
tctl=""
for h in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$h/name" 2>/dev/null)" = k10temp ] && tctl=$(cat "$h/temp1_input" 2>/dev/null)
done
[ -n "$tctl" ] || { logger -t estate-thermal "sensor not readable; no action"; exit 0; }
count=$(cat /run/estate-thermal/count 2>/dev/null || echo 0)
if [ "$tctl" -ge "${TRIP_MC:-92000}" ]; then
  count=$((count + 1)); printf '%s\n' "$count" > /run/estate-thermal/count
  if [ "$count" -ge 3 ] && [ "$(cat /sys/devices/system/cpu/cpufreq/boost)" = 1 ]; then
    echo 0 > /sys/devices/system/cpu/cpufreq/boost; touch /run/estate-thermal/tripped
    logger -t estate-thermal "TRIP: ${tctl}mC — boost disabled"
  fi
else
  printf '0\n' > /run/estate-thermal/count
  if [ -e /run/estate-thermal/tripped ] && [ "$tctl" -lt "${CLEAR_MC:-80000}" ]; then
    echo 1 > /sys/devices/system/cpu/cpufreq/boost; rm -f /run/estate-thermal/tripped
    logger -t estate-thermal "CLEAR: ${tctl}mC — boost restored"
  fi
fi
```

## Keeping it healthy

- **Daily:** read the health report; `ack` when triaged so tomorrow's report is about new
  things. Check `systemctl --failed` on the host and inside each container.
- **Weekly:** `zpool status -x` if you use ZFS, `journalctl -p err -b --no-pager` for this boot,
  and the thermal log for a `TRIP` you did not expect.
- **Monthly:** confirm the audit timer is still restoring your CPU ceiling
  (`estate-power-cap.sh status`), look at `last reboot` and `uptime`, and check that the
  unattended-upgrade log has actually been applying security updates.
- **At every kernel/host package update that touches a running unit:** `needrestart` will list
  services wanting a restart; schedule a drain rather than restarting under a live session.
- **Twice a year:** repeat the power-cut test, re-read the BIOS settings you recorded, and check
  the UPS batteries (they are consumables).
- **When the box feels slow or hot:** read the trip log and the CPU ceiling *before* touching the
  fan profile; and run the load that made it hot with `time` on one core first, so you know
  whether the problem is thermal or just the workload.

Last checked: 2026-10, Debian 13 on a small x86 mini-PC.
