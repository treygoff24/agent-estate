# Phone access to your agents (Moshi, mosh, herdr)

This guide gives you a phone terminal into the agent workspaces on your Mac and your Linux box. The phone app is Moshi, which speaks mosh (a roaming SSH replacement that survives sleep and network changes). Over the tailnet, the phone connects to a [herdr](https://github.com/herdrdev/herdr) session that is already running on each machine, so your agents keep working when the phone goes away. The guide also fixes the most annoying failure: a phone left attached shrinks every terminal tab on your desk to phone width.

Herdr is a third-party terminal-workspace tool. Moshi is a third-party iOS app (getmoshi.app). This guide only describes how to wire them together.

## Do you need this?

- **Skip it** if you only ever use agents at a desk, or you already reach your box from a laptop and do not care about the phone. Nothing else in agent-estate depends on it.
- **Do it** if you want to check, steer or unblock a running agent from a phone.
- **Cost:** one `mosh-server` process per phone session (small), six UDP ports on the box, one five-minute sweep timer, and one herdr server per machine. Operational weight is moderate, mostly because of the tab-sizing and port-slot problems below.

## Prerequisites

- **Tailscale** (or any private network) on the box, the Mac and the phone, with the phone signed into the same tailnet and its VPN on. Do not use Tailscale SSH (see papercuts).
- **A non-root agent user** on the Linux box that owns the agent sessions, with systemd lingering enabled (`loginctl enable-linger <you>`) so herdr and the sweep timer survive logout.
- **SSH key login** to both machines. Password SSH should be off.
- **Herdr** installed on each machine, per its project README. Do not start it yet.
- **Moshi** on the phone (iOS). Its pairing flow installs the phone's public key on the box.
- Optional, for push notifications from agents: the Moshi hook daemon. See "What bit us".

## Steps

### 1. Install mosh and make it reachable over non-interactive SSH

On the box (Debian or Ubuntu): `sudo apt-get install -y mosh`. On the Mac: `brew install mosh`.

Moshi runs `mosh-server` over a non-interactive SSH command, which does not read your interactive shell rc. On the Mac, Homebrew's `bin` is often missing from that PATH. Put the PATH setup in a file that non-interactive shells read (for zsh, `~/.zshenv`), and append Homebrew rather than prepending it, so system tools keep precedence.

**Done when:** `ssh <you>@<mac-or-vps> 'command -v mosh-server'` prints a path. An empty result means mosh will fail from the phone even though SSH works.

### 2. Open the mosh UDP range on the box

Mosh uses UDP. Pick six ports, for example `60001-60006`, and allow them through the host firewall (and any cloud security group) to the box. If the box is a container, forward those six ports from its host; on a plain VPS, the equivalent is an inbound UDP allow rule for that range. (This step is inferred for a plain VPS; confirm with a live phone connection.)

On the Mac, with the application firewall off, no port range is needed. If your Mac firewall is on, allow `mosh-server`.

**Done when:** from the phone, the Moshi host entry for the box connects with the UDP range set to exactly `60001-60006`.

### 3. Start herdr on each machine

Follow the herdr project README to install it. Then, as the agent user, check that the CLI answers without launching the UI:

```sh
herdr --help
herdr workspace list
```

Do not run bare `herdr` for discovery; it attaches the terminal UI. Run `herdr` only when you want a visible session.

**Done when:** `herdr workspace list` returns JSON on each machine.

### 4. Add the sweep that retires quiet phone transports

Without this, a phone session left attached keeps a small herdr client on the box. See the first papercut for why that matters. The fix has three parts:

1. Export `MOSH_SERVER_SIGNAL_TMOUT=900` from the login environment that Moshi's SSH command inherits (the same file as step 1, for example `~/.zshenv`). With this variable set, `SIGUSR1` makes `mosh-server` exit only when its client has been silent for 900 seconds. Without it, `SIGUSR1` kills the transport outright, so the sweep must skip any process that lacks it.
2. Install the sweep script below as `~/.local/bin/mosh-idle-sweep`, and a systemd user timer that runs it every five minutes.
3. On the Mac, run a launchd agent every 300 seconds (`StartInterval` 300) that runs a macOS variant of the script. The snippet below is Linux-only: it reads `/proc`, which macOS does not have, so on a Mac it would skip every process. The macOS variant reads each process's environment with `ps -E -ww -o command= -p <pid>` and takes the same `MOSH_SERVER_SIGNAL_TMOUT=<positive integer>` token from it. To write it, replace the `/proc` read with that `ps` call and keep the rest. Check that `ps -E` actually shows the variable on a live Moshi transport before you rely on the job.

```sh
#!/bin/sh
# ~/.local/bin/mosh-idle-sweep
# A trimmed version of a longer script. It keeps the Linux branch and drops the
# executable-path check, the macOS branch (which reads the environment with
# `ps -E`), and file logging. Test it on a box before you rely on it.
# Signals one checked PID at a time, only processes of this user that export a
# positive MOSH_SERVER_SIGNAL_TMOUT.
uid=$(id -u)
for pid in $(pgrep -U "$uid" -x mosh-server 2>/dev/null || :); do
  case $pid in ''|*[!0-9]*) continue ;; esac
  tmout=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
    | sed -n 's/^MOSH_SERVER_SIGNAL_TMOUT=\([1-9][0-9]*\)$/\1/p' | head -n 1)
  [ -n "$tmout" ] || continue
  kill -USR1 "$pid" 2>/dev/null || continue
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "kept $pid: client heard from within ${tmout}s"
  else
    echo "retired $pid: client silent for over ${tmout}s"
  fi
done
```

```ini
# ~/.config/systemd/user/mosh-idle-sweep.service
[Unit]
Description=Retire mosh-server transports whose client has been silent past MOSH_SERVER_SIGNAL_TMOUT

[Service]
Type=oneshot
ExecStart=%h/.local/bin/mosh-idle-sweep
Nice=10

# ~/.config/systemd/user/mosh-idle-sweep.timer
[Unit]
Description=Sweep idle mosh-server transports every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
```

Enable it with `systemctl --user daemon-reload && systemctl --user enable --now mosh-idle-sweep.timer`.

**Done when:** `systemctl --user list-timers mosh-idle-sweep.timer` shows the next run, and the sweep's output (run it by hand once) prints nothing or only `kept`/`retired` lines for your own PIDs. Confirm the wiring with a real phone session: the log should show `kept` while the phone is in use, and `retired` only after 15 minutes of silence. A transport started before you exported the variable lacks it and is skipped on purpose; restart it to pick it up.

### 5. Keep the six slots free

Mosh allocates one UDP port per transport, and you have six. A transport can outlive its phone. Six stale `mosh-server` processes fill all six ports, and then new phone connections fail with "can't connect" while SSH still works. The fix is a small launcher. Build it like this if you hit the limit:

1. Save it as `~/.local/bin/mosh-server`, executable, and make sure `~/.local/bin` comes before `/usr/bin` on the PATH of non-interactive SSH commands. Moshi resolves `mosh-server` from that PATH.
2. Take an exclusive lock with `flock` on a file in `$XDG_RUNTIME_DIR` (or `~/.cache`), so two phone connects cannot race.
3. Count this user's processes whose `/proc/<pid>/exe` resolves to the real binary (`/usr/bin/mosh-server`). While the count is six or more, retire the one with the oldest start time (field 22 of `/proc/<pid>/stat`): send `TERM`, wait briefly, then `KILL` only if it still runs.
4. Release the lock only after the real server has chosen its port (close the lock's file descriptor in the child so the daemonized transport does not hold it).
5. `exec` the real server with the original arguments.

Expect about 70 lines of POSIX shell. Test it by opening six real transports and a seventh: the seventh should succeed and the oldest should be gone.

The manual fallback is to stop the specific PIDs you have confirmed are your `mosh-server` processes (`ps -axo pid,lstart,command | grep '[m]osh-server'`, then `kill <pid>` for each). Do not kill by name pattern.

**Done when:** with six transports running, a new phone connection still succeeds.

### 6. Add the box and the Mac to Moshi

In Moshi, add one connection per machine:

- Host: the machine's tailnet name, for example `vps.example.ts.net` or `mac.example.ts.net`.
- Port 22, user `<you>`, the key Moshi generated during pairing.
- Transport: mosh. For the box, set the UDP port range to `60001-60006`.

Use Moshi's pairing (Easy Pair or the host setup command) from a visible terminal. Treat the pairing QR as a temporary access token: anyone who scans it gets SSH access as that user.

Once connected, run `herdr` to attach to the running session. A tab that is the phone's own should be kept separate from the tabs you use at the desk (see the sizing papercut).

**Done when:** the phone shows the same herdr workspaces that `herdr workspace list` shows on the box, and a tab you create from the phone appears in `herdr tab list` on the box.

## What bit us

- **A phone left attached shrinks your desk's tabs.** Herdr gives tab geometry to whichever client is attached. A phone client is 50 columns wide, so when the desk views a tab on another machine, its tabs open phone-sized and then snap back when you return. What happened: this recurs whenever a phone stays attached. Do instead: step 4's sweep, and kill a stale transport by its PID when it happens now.
- **`MOSH_SERVER_NETWORK_TMOUT` does nothing when Moshi launches the server.** Moshi starts `mosh-server` with its own `MOSH_SERVER_NETWORK_TMOUT=86400`, which overrides yours from the environment. What happened: setting it to 3600 changed nothing. Do instead: use `MOSH_SERVER_SIGNAL_TMOUT`, which Moshi does not override, with the sweep.
- **Six stale transports block every new phone connection.** What happened: SSH worked and mosh refused. Do instead: step 5. Do not use `pkill -u <you> mosh-server`; it matches by name and takes every transport, including a live phone session.
- **Never enable Tailscale SSH on the box** (`tailscale set --ssh`). It takes port 22 ahead of `sshd` and breaks the key auth that Moshi and everything else uses.
- **Agent forwarding works only on an SSH connection type,** not mosh or auto. Git from the phone needs its own credentials on the box, or a plain SSH connection.
- **Moshi's hook settings disappear after a settings push.** A sanitized `settings.json` pushed over the agent config replaced the file and dropped the Moshi hook entries, so push notifications went quiet for weeks. Do instead: after any config push, run `moshi-hook status`; if it reports stale, run `moshi-hook install` and restart its user service. Newer config merges keep local hooks, but verify rather than assume.
- **A Mac hook daemon can burn CPU.** In one slowdown investigation it sat at tens of percent CPU in steady state and was uninstalled, though the cause of the spikes stayed unproven. Phone SSH and mosh kept working; push notifications and the Moshi diff viewer did not. If you want push notifications back, measure the daemon's CPU first.
- **Herdr launches an agent by its bare kind if you ask it to.** `herdr agent start --kind claude` runs the bare binary. If your setup needs a launcher (an account launcher or alias), start the agent through that launcher in the pane and then name it. Check with `herdr pane process-info --pane <id>`.
- **The sweep has not been confirmed on a real phone launch.** Check the sweep's log after your first real phone session before you rely on it.

## Reference: what each machine should look like

- `~/.zshenv` (or the file your non-interactive shells read) exports `MOSH_SERVER_SIGNAL_TMOUT=900` and appends Homebrew's `bin` to PATH.
- `~/.local/bin/mosh-idle-sweep` is the script in step 4, and its timer is enabled and active.
- The six UDP ports `60001-60006` reach `mosh-server` on the box.
- `herdr workspace list` works from a plain SSH command, not only from an interactive shell.

## Keeping it healthy

- After each herdr or Moshi upgrade, repeat the phone check in step 6. Herdr changes tab-sizing behaviour between releases.
- Once a week, read the sweep's output: `journalctl --user -u mosh-idle-sweep.service --since "7 days ago"` on the box (the Mac's launchd job logs wherever you pointed it). A sweep that never prints `retired` after a long phone-free day means the variable is missing from the environment Moshi uses.
- After any settings push to the box, check `moshi-hook status` (if you use the hook).
- Keep the `herdr` and `mosh` versions on the box and the Mac close enough that the client and server speak the same protocol.

Last checked: 2026-10, Debian 13 and macOS.
