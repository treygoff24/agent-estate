# baseline

What makes a fresh Linux VPS a safe home for agents: a separate non-sudo login for them, Tailscale, a default-drop firewall that cannot lock you out, unattended security updates, and optional restic backups. On the Mac it only checks what applies.

## Why two halves

The agents' login has no sudo (that is the point of it), so most of this is root setup. The module splits cleanly:

- **`root-setup.sh`** (you run it once, with sudo). `estate install baseline` prints the exact command with your settings filled in. Read it first; `--dry-run` lists every step and changes nothing. It is idempotent: a second run changes nothing.
- **`check`** verifies the result without root. `estate doctor` shows it. It fails until the root half is done, and says which piece is missing.
- **`install`** (as the agents' login) installs the backup timers if you enabled backups, and prints the root command if the root half is not in place.

## What root-setup does

1. **Packages**: nftables, chrony, unattended-upgrades, needrestart, openssh-server, and what the core needs and a minimal image lacks (git, python3, curl, ca-certificates). With `toolchain = true` (default) also build-essential, nodejs and npm, which the optional modules (skills builds Rust, post's hooks run Node) need and the agents' login, having no sudo, cannot install. Plus zram-tools and restic when enabled.
2. **The agents' login** (`agent_user`): created if missing, removed from `sudo`/`wheel`/`admin` if it is in one, systemd **linger** on (so its services survive logout), and **SSH keys only**: `/etc/ssh/sshd_config.d/00-estate.conf` turns passwords off. It copies the public keys of the person running sudo (or `--authorized-keys FILE`) to the login. Passwords are turned off only if a key exists, so the script cannot lock everyone out. The file is named `00-` on purpose: sshd keeps the first value it reads, and cloud images ship a `50-cloud-init.conf` that turns passwords back on.
3. **Tailscale** from the official apt repo. Logging in is yours to do: `sudo tailscale up --ssh`. SSH then works over the tailnet with no public port.
4. **Updates and time**: unattended **security** updates only, never an automatic reboot, needrestart set to report-only (it lists what needs a restart, restarts nothing), chrony for time (if it cannot start, as in a container that may not set the clock, the script warns and continues to the firewall). Optional zram swap.
5. **Firewall** (`firewall.sh`, nftables, own `inet estate` table so other tools' tables are left alone): default-drop ingress; admitted are loopback, established traffic, ICMP, DHCP, Tailscale's direct-path UDP, the Tailscale interface, and public SSH only if `public_ssh = true`.

### The firewall's dead-man revert

A wrong rule on a remote box locks you out. So `apply` loads the ruleset and arms a 90-second systemd timer that deletes it again. Open a **fresh** SSH connection (an existing one survives on conntrack and proves nothing); if it works, run `sudo estate-firewall confirm`, which disarms the timer, saves the ruleset to `/etc/nftables.conf` and enables it at boot. If you do nothing, or cannot connect, the rules vanish by themselves. If the timer cannot be armed, `apply` removes the ruleset again rather than leave you without a safety net.

Order matters on a first run: with public SSH off, a firewall applied before Tailscale is connected would cut you off. So root-setup **skips the firewall** until `tailscale ip -4` works, tells you so, and you run it again after `tailscale up`. Keep your VPS provider's web console handy for the day you misconfigure anyway.

## Backups (optional)

`backups = true` and a `backup_repo`. restic runs as the agents' login from **systemd user timers** (no root needed): a daily backup of `backup_paths` (default the whole home, `~/Code` included) with retention `keep_daily/weekly/monthly`, and a weekly `restic-maintain` that prunes and verifies a random 10% of the data. The first run initialises the repository. The password and repository keys never live in this repo or in the unit files: define `RESTIC_PASSWORD` and the repository's keys (for example `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`) as plain `NAME=value` lines in the key file (`estate config get keys.file`), and the timers load them from there. **Write the repository password down somewhere else too**: without it the backups are unreadable. `check` warns if the last good backup is older than two days. Restore with `restic restore latest --target <dir>` after exporting the same variables.

On the Mac, `backups = true` only checks that Time Machine has a destination; this module installs no backup there.

## Settings (`[modules.baseline]`)

| Key | Default | Meaning |
|---|---|---|
| `agent_user` | `"agent"` | the agents' Linux login |
| `tailscale` | `true` | install Tailscale; admit its interface |
| `public_ssh` | `false` | also accept SSH from the internet |
| `ssh_port` | `22` | port opened when `public_ssh` is true |
| `zram` | `false` | compressed-RAM swap |
| `toolchain` | `true` | root-setup also installs build-essential, nodejs and npm for the optional modules |
| `backups` | `false` | restic backups |
| `backup_repo` | `""` | e.g. `s3:s3.amazonaws.com/bucket`, `b2:bucket:path`, `sftp:user@host:/path` |
| `backup_paths` | `""` | space-separated absolute paths without spaces; empty means the home |
| `backup_time` | `"03:15"` | daily, HH:MM, server time |
| `keep_daily` / `keep_weekly` / `keep_monthly` | 14 / 8 / 12 | retention |

Changing `public_ssh` or `ssh_port` changes the wanted ruleset: `check` fails until the root-setup command (printed by `estate install`) is run again.

## Done when

`estate doctor` shows `baseline` ok on the VPS: the agents' login exists without sudo and with linger, SSH is key-only, Tailscale is connected, the confirmed firewall matches the config, security updates and time sync are on, and (if enabled) backups ran within two days. On the Mac: Tailscale is up.

## Uninstall

`estate uninstall baseline` removes the backup timers only. The root changes stay, because removing a firewall or SSH policy blindly is how people lock themselves out. To drop the firewall by hand: `sudo nft delete table inet estate && sudo rm /etc/nftables.conf`.

## Related guides

- [Many agents compiling](../../guides/many-agents-compiling.md) and [disk hygiene](../../guides/disk-hygiene.md): what fills a VPS and how to keep it healthy.
- [ZFS storage and snapshots](../../guides/zfs-storage-snapshots.md): snapshot-based backups on hardware you own (not part of this module).
- [Egress control](../../guides/egress-control.md): limiting what agents can reach outbound; this module only filters ingress.
- [Physical home server](../../guides/physical-home-server.md): the extra steps for a box on your own network.
