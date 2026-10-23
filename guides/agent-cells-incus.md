# One Incus container per person ("cells"), with agents that never hold sudo

This guide builds the containment layer that lets one Linux box host several people's
work — you, a collaborator, a partner — without any of them being able to reach the host,
each other, or each other's credentials. The unit is a **cell**: one unprivileged Incus
container per person (or per project) with its own resource caps, its own ingress port,
and two logins inside it: the human, who holds in-cell sudo and nothing on the host, and
the agent, who holds no sudo anywhere. What you get is a box where an agent can be given
almost-root inside its fence without ever being one step from your host, and where
offboarding a person is a sequence of commands instead of a hope.

## Do you need this?

**Skip it** if there is one human on the box, agents run as your own user, and you are
fine with every agent being able to read your whole home directory and your keys. That is
a normal single-user setup; cells buy you a boundary you may not need yet.

**Do it** if any of these are true:

- Another person (a partner, a colleague, a client's employee) will run agents on your box.
- You want each project's agents fenced from the others, so a runaway agent or a poisoned
  dependency cannot touch a different project's work.
- You want a box you can rebuild per project without touching your own environment.
- You want the discipline of "no agent process runs on the host", which is the only shape
  that makes unattended agents defensible.

**What it costs.** Real RAM and CPU per cell. A cell sized at three-quarters of the host's
cores and 8 GiB of memory is comfortable and, on a small VPS, is most of the machine — so
size the host for the number of cells you actually intend to run, or cap cells lower and
expect slower builds. Plus Incus, a ZFS pool (or dir backend), a bridge, and a per-cell
update chore that nothing automates for you. The minimum useful version is **one** cell
for your own agents; it is worth it even at one, because it is the version that gives you
the no-sudo boundary.

## Prerequisites

- A Linux host with a second disk or dataset for cell storage, and Incus installed.
- A tailnet (or another stable path from your laptop to the box) for ingress.
- The **egress guide** done first, or at least understood: cells need to reach the forge
  and a package path to be provisioned, and the host firewall has to let them get an
  address.
- The **self-hosted git guide** if you want cells to clone and push (they should; a cell
  with no git identity cannot do useful work).
- Human actions that no script may perform for you: the tailnet policy edit that scopes a
  partner's identity to one port, and any decision to invite a person at all.

## Steps

### 1. Stand up the Incus runtime, bridge, pool and a locked default profile

Install Incus, put exactly one human in the admin group, and preseed the storage pool,
bridge and default profile in one pass. The default profile is your safety net: every cell
launched without an explicit profile inherits it, so it must be unprivileged, with an
isolated idmap, and with no nesting, no host paths and no host sockets.

```sh
apt-get install -y incus
usermod -aG incus-admin <you>          # the only human here; re-login after this

incus admin init --preseed <<'EOF'
networks:
- name: incusbr0
  type: bridge
  config:
    ipv4.address: auto
    ipv6.address: auto
storage_pools:
- name: cells
  driver: zfs
  config:
    source: <pool>/cells
profiles:
- name: default
  config:
    security.idmap.isolated: "true"
  devices:
    root:
      path: /
      pool: cells
      type: disk
    eth0:
      name: eth0
      network: incusbr0
      type: nic
EOF
```

Re-apply the posture on every run so a drift cannot survive:
`incus profile set default security.idmap.isolated=true`; `incus profile unset default
security.nesting`; `incus profile unset default security.privileged`.

No cell ever sees the Incus socket: agents drive cells through your own tooling on the
host, never by talking to the daemon from inside a cell. If a cell can reach the control
socket, it can escape its fence and every promise below is void.

**Done when** `incus storage list` shows the pool, `incus profile show default` shows
`security.idmap.isolated: "true"` and nothing privileged, and
`incus launch images:debian/13 smoke && incus exec smoke -- id && incus delete smoke -f`
works end to end.

### 2. Build a base image once, and promote it only after a smoke test passes

Do not provision tools into each cell by hand. Build one content-addressed Debian image
with the shared tool layer, then prove it before you give it a stable name: launch a
throwaway container from the new image, run your doctor, run the non-root checks, and only
then point the alias (e.g. `estate-base`) at it. A build that publishes the alias first has
no way to fail safely.

Two properties of the image matter more than its tool list:

- **No credentials, no per-user runtime, no harness sign-in.** Every cell starts logged
  out. The person signs in to their own accounts; a shared image with a baked token is a
  credential leak you cannot audit later.
- **It declares who lives in the cell.** Install a root-owned file listing cell principals,
  one per line (e.g. `/etc/estate/cell-principals`). Anything on the host that must refuse
  to work in a shared cell — a browser on localhost CDP, for instance, which every UID in
  the cell's network namespace can reach — reads that file and refuses when there is more
  than one principal.

**Done when** a fresh container from the alias passes your doctor as the agent user (not
as root), and `incus image info estate-base` resolves.

### 3. Create the cell, then give it caps and a disk quota

```sh
incus launch estate-base <cell>
incus config set <cell> limits.cpu <n>
incus config set <cell> limits.memory 8GiB
incus config set <cell> boot.autostart true
sudo zfs set refquota=<r> quota=<q> <pool>/cells/containers/<cell>
```

Three things to understand, because all three surprise people:

- **A new dataset has no quota at all** and silently shares the pool. `refquota` is the
  real write limit; `quota` is a snapshot backstop above it.
- **Memory applies live. CPU does not.** Incus records the new count but the cell keeps its
  old cpuset until it restarts, so `nproc` inside still shows the old number.
- **Caps live on the instance, not the image.** A rebuilt or recreated cell comes back with
  default caps and no quota, so caps are something you record and re-apply, not something
  the image carries.

**Done when** `incus config get <cell> limits.cpu` and `limits.memory` show your values,
`zfs get refquota,quota` shows the pair, and after the restart in step 8, `nproc` and
`free -g` inside the cell agree.

### 4. Two logins, three rings

Inside each cell there are exactly two accounts:

| Ring | Who | Privilege |
|---|---|---|
| 0 — host | you, the human | the only sudoer on the box; no agent process runs here |
| 1 — cell | `<person>` | in-cell sudo; where their SSH key lands |
| 2 — agent | `<person>-agent` | no sudoers entry anywhere, in any cell, ever |

Create the agent user with no sudoers entry and do not add one later. Root-requiring needs
are met by the human, or baked into the image. This is uniform across everyone, including
you: the rule is worthless if the owner has an exception, because the owner's agents get
the exception by proxy.

Tools go on the agent login (root-owned system packages for build dependencies, per-user
runtimes for the rest); the person reaches them with `sudo -iu <person>-agent`.

**Done when** both of these fail the way they should:

```sh
sudo -l -U <person>-agent          # "not allowed to run sudo"
su - <person>-agent -c 'sudo -n true'; echo $?   # non-zero
```

### 5. Ingress: one host port per cell, and a human-only policy edit

Give each cell its own host port with a proxy device that forwards to the cell's `sshd`:

```sh
incus config device add <cell> ssh-proxy proxy \
  listen=tcp:0.0.0.0:<port> connect=tcp:127.0.0.1:22
incus config device show <cell>
```

Pick a stable port block (e.g. `2201`, `2202`, …) and write the mapping down: the port is
part of the cell's public identity and appears in everyone's `~/.ssh/config`.

Then the part no script may do: **restrict the person's tailnet identity to that one
port.** A device share alone is not a boundary — Tailscale's sharing quarantine protects
the *recipient's* tailnet from your node, not yours from theirs, so your own
deny-by-default policy has to scope the identity to `cell:22` and deny the host and sibling
cells. That is a human action-time edit in the tailnet admin console; file it as something
the human must do and confirm, and don't tell the person their cell is ready until it is
done.

**Done when** `ssh -p <port> <person>@vps.example.ts.net` lands on the cell, and from
inside the cell the host's other ports and every sibling cell are unreachable (test the
negative, not just the positive).

### 6. Put the toolchain on the agent login, not on the system

Per-user runtimes belong to the agent account: Node via `mise`, Rust via `rustup`, `apt`
only for build dependencies. Then fix the three things installers do not:

```sh
# as the agent user
mise use -g node@<version>
# 1. PATH: add the mise shims block to ~/.profile — login shells reset PATH via /etc/profile
# 2. check for a stray empty ~/.bash_profile, which silently skips ~/.profile entirely
# 3. linker: ~/.cargo/config.toml with linker = "clang" and -C link-arg=-fuse-ld=mold
```

And enable lingering so user units survive logout: `loginctl enable-linger <person>-agent`.

**Done when** as the agent user, `node --version`, `rustc --version` and `mold --version`
all print, and Node is at the version your harness needs (an LTS one major behind will
fail to run it).

### 7. Leave every sign-in to the person

The cell ends its setup with Claude/Codex/`gh`/any MCP auth logged out. Signing in is the
person's act, in their cell, with their accounts. If a cell needs a Forgejo identity or a
key, that is a **grant** — it appears in the offboarding sequence, so it is a decision, not
a convenience. Do not copy another user's key to "make cloning work".

**Done when** `git ls-remote <forge-url>` works through the cell's own identity (or the
absence of one is recorded as an open item), and nothing in the cell holds someone else's
credential.

### 8. Restart, then verify — the restart is the network test

```sh
incus restart <cell>
```

This makes the CPU cap real. It is also the moment a cell has to get its IPv4 address
fresh over DHCP, which is exactly the path a host firewall most easily breaks: a
`ct state invalid drop` ahead of the DHCP accept rule means a restarted cell never gets an
address and looks like a broken cell rather than a broken rule.

If there is no IPv4 a minute after the restart, **trace it before editing anything** — a
temporary chain that sets `meta nftrace` on the cell's MAC with `udp dport 67`, `nft
monitor trace` while you run `networkctl renew eth0` inside the cell, then delete the
chain. The trace names the rule that drops it.

**Done when** all of these hold, as the agent user: `nproc` and `free -g` match the caps;
`incus list <cell>` shows an IPv4; `systemctl --user is-active <service>` is `active` for
any user unit you installed; and every tool you expect resolves on PATH.

### 9. Write the cell down before you forget it

One section per cell in a state file the next agent reads: name, caps, disk quota, ingress
port, where tools live, what is signed in, and what updates it (usually: nothing
automatically). Include anything that is a known open item, e.g. "key in
`authorized_keys` that is not the person's — human to keep or remove".

**Done when** the state file has the section and a fresh agent could rebuild the cell from
it.

### 10. Adding the next person

Bringing a second person to **parity** is a different job than making the first cell:
read the existing cell's *live* caps rather than copying numbers out of a document, because
the numbers drift as the machine fills up.

```sh
incus config get <existing-cell> limits.cpu; incus config get <existing-cell> limits.memory
sudo zfs get refquota,quota <pool>/cells/containers/<existing-cell>
```

Then repeat steps 3–9, and note the two orderings that matter: **build first, restart
after** (a restart mid-build loses your warm caches and makes the CPU cap real at the worst
moment), and **ingress policy last, before you announce the cell** — the human's tailnet
edit is the gate, not the container.

**Done when** `incus config get` and `zfs get` show the same values as the cell it is meant
to match, and the state file has both sections.

### 11. Offboarding is an ordered, idempotent sequence

Removing a person is not a real cross-system transaction, so make it one explicit workflow
that fails closed, and re-run it to prove it is idempotent:

1. Disable the principal in your own control plane first.
2. Revoke ingress (unshare the tailnet node or disable the identity) and every lease or
   capability issued to that cell.
3. Remove the person's forge and mail grants.
4. Freeze or quarantine the cell; then preserve or transfer client work per your policy.
5. If they had brokered credentials, revoke those bindings (disable in the broker first,
   remove endpoints second).
6. Their provider and GitHub tokens are revoked **by them** at the provider — you never held
   those credentials, so you record the request and confirm it out of band. Sweep the frozen
   or destroyed cell for residue and report honestly rather than asserting a revocation you
   did not perform.
7. Reconcile and surface any partial failure loudly. **A half-offboarded principal is an
   alarm, never a silent state.**

**Done when** re-running the whole sequence changes nothing and every post-revoke probe
denies — including the ingress port, the forge access, and any leftover device share or
node enrollment.

### 12. Prove the boundary with evidence, not impressions

Write an evidence packet: the claim, the procedure, what you observed, the verdict, and
the environment fingerprint. The matrix that actually tests something:

- **baseline**: SSH from the person's identity lands (and the SSH identity maps to *the
  right principal*, not merely "a TCP connection opened"); the host and sibling cells are
  denied *from* the cell and *to* the cell; no sudo as the agent; the in-cell tailscaled
  state is unreadable by the agent user.
- **post-reboot**: the same matrix after a reboot, including that the port still works. A
  proof with no reboot row proves nothing about the state you live in.
- **post-revoke**: everything denies.

Two rules for the probe adapter: it prints exactly one of `allow`, `deny`, `unknown`; and
`unknown`, an empty line, extra output, a timeout or a non-zero exit is **failed evidence,
never a denial**. Converting an inconclusive probe into a "deny" is how a boundary gets
signed off while it is open.

**Done when** the packet is written, the positive rows carry the principal identity, and
the negative rows are real denials rather than timeouts.

## What bit us

- **The CPU cap was recorded but not applied.** `incus config set` succeeded, the old
  cpuset stayed live, and `nproc` showed the old number until a restart. Set caps, restart,
  then verify — in that order.
- **A new cell's dataset had no quota at all** and shared the pool with everything else.
  Set `refquota` (the write limit) and `quota` (the snapshot backstop) in the same step that
  creates the cell, not later.
- **A restarted cell got no IPv4.** The host firewall dropped its DHCP request (the
  DISCOVER arrives `ct`-invalid once bridge conntrack is loaded), which reads as a broken
  cell. The fix is one accept rule ahead of the invalid drop; the lesson is to *trace* it
  (`nft monitor trace`) instead of guessing at the cell.
- **`incus restart` returns before the cell's mounts are ready.** A post-restart filesystem
  check ran against a not-yet-mounted `/tmp` and looked like data loss. Poll
  `systemctl is-active tmp.mount` before any post-restart proof.
- **An empty `~/.bash_profile` silently skipped `~/.profile`**, so the mise shims never got
  on PATH and `node` "was not installed" as far as every login shell was concerned. Check
  for the stray file first.
- **Every Rust build failed with `rust-lld: error: unknown argument '--thread-count=1'`**
  in a cell that lacked the host's default mold linker config. The repo's flags assume the
  linker; give the agent user its own `~/.cargo/config.toml` with `clang` + mold and leave
  out any host-only paths.
- **A `nohup` daemon installed by a script died with the cell.** Anything that must survive
  a logout or a restart belongs in a user unit; and `systemctl --user` run through `su`
  needs `XDG_RUNTIME_DIR=/run/user/<uid>` or it cannot find the user bus.
- **`incus config show --format=json` did not exist in Incus 6.0** (nor for profile and
  network-acl), so tooling that parsed JSON from those commands failed. Use the REST query
  API at `/1.0/...` for anything machine-readable; `incus list --format=json` is the one
  supported JSON listing.
- **`incus image alias show` was not supported** on the live version, so a preflight
  "does the image exist" check failed before it touched anything. Use `alias list` or the
  query API.
- **The sharing-quarantine direction is easy to get backwards.** Device sharing protects
  the recipient's tailnet from the shared node; nothing about it protects yours. The
  deny-by-default policy is yours to write, and it is a human action.
- **A rebuilt cell came back at default caps.** The image carries the tools; it does not
  carry the instance's limits or quota. Record caps in the state file so "rebuild" does not
  quietly mean "unlimited".

## Reference snippets

The preseed in step 1 is the whole runtime. Two more shapes worth having:

Cell caps and the quota pair, written as one repeatable block (this is what "give it the
same caps as the other cell" means in practice):

```sh
# read from the cell you are matching, never from a document
CPU=$(incus config get <existing-cell> limits.cpu)
MEM=$(incus config get <existing-cell> limits.memory)
REFQ=$(sudo zfs get -H -o value refquota <pool>/cells/containers/<existing-cell>)
QUOT=$(sudo zfs get -H -o value quota    <pool>/cells/containers/<existing-cell>)

incus config set <cell> limits.cpu "$CPU" limits.memory "$MEM" boot.autostart true
sudo zfs set refquota="$REFQ" quota="$QUOT" <pool>/cells/containers/<cell>
incus restart <cell>
incus exec <cell> -- su - <person>-agent -c 'nproc; free -g'
```

The no-sudo invariant, as a check you can run after any change (it should print nothing):

```sh
getent group sudo wheel 2>/dev/null | cut -d: -f4 | tr ',' '\n' | grep -E -- '-agent$'
grep -RhE -- '-agent\b' /etc/sudoers /etc/sudoers.d 2>/dev/null
```

A user unit for a long-lived in-cell daemon (the replacement for a `nohup` process):

```ini
# ~<person>-agent/.config/systemd/user/<service>.service
[Unit]
Description=<service>
After=network-online.target

[Service]
ExecStart=%h/.local/bin/<service> --socket %h/.local/state/<service>.sock
Restart=on-failure

[Install]
WantedBy=default.target
```

```sh
loginctl enable-linger <person>-agent
su - <person>-agent -c 'XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user enable --now <service>'
```

## Keeping it healthy

- **Updates:** security updates via unattended upgrades inside the cell, and never with
  auto-reboot. Harness and CLI updates are per cell and by hand (or one host-side job that
  walks every cell), because they sit under a running agent and can break it mid-task. Say
  in the state file what updates a cell, and assume nothing does.
- **Disk:** watch `refquota` per cell and a snapshot budget per dataset. A cell that fills
  the pool takes down its neighbours.
- **The invariant, re-checked:** after every cell change, run the no-sudo check above and
  read the cell's `authorized_keys` for keys you cannot attribute.
- **Caps after any rebuild:** re-apply and re-record. Compare with the cell you use as the
  reference, not with a stale note.
- **The base image drifts.** Rebuild it on a schedule, and remember existing cells do not
  get it — a rebuild of the image is not an update of the fleet.
- **Offboarding rehearsal:** run the offboarding sequence against a disposable identity
  once, so the first time you run it for real is not the first time.

Last checked: 2026-10, Debian 13 with Incus cells.
