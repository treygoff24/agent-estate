# Egress control: deciding what your agents can reach on the network

Agents run unattended, follow links, install dependencies and occasionally invent a URL.
This guide puts a boundary around what they can reach: a host firewall that admits only
known paths, a small set of named **egress tiers** (sealed, build, research, open, site)
attached per cell, a package proxy with an allowlist for build work, and an apply procedure
that reverts itself in ninety seconds if you lock yourself out of the box. The point is not
surveillance; it is that a cell doing billing work cannot reach your LAN, another person's
cell, or a metadata endpoint, and that you can prove both the allow and the deny.

## Do you need this?

**Skip it** if your agents run on your laptop or a single box where "can reach the LAN" is
normal, and you have no cells and no partners. Nothing else in agent-estate depends on it.

**Do it** if any of these are true:

- Agents run unattended on a box that also holds work you would not hand them.
- More than one person or project shares the box (cells make the need concrete: every cell
  should be denied east-west by default).
- You want builds to fetch only packages, not arbitrary URLs, so a compromised dependency
  or a prompt-injected agent cannot exfiltrate.
- You want a written, reviewable statement of what each class of work is allowed to reach.

**What it costs.** This is the heaviest module in the kit. Plan an afternoon for the host
policy and the tiers, and treat the build proxy as a separate project: it needs a pinned
Squid, its own CA, and a boot-ordering fix that you install by hand. The minimum viable
version is much cheaper and still worth doing: **the host firewall from step 1**, which
alone turns "any cell can reach my LAN" into "no cell can". Add tiers when you have a
second class of work that should behave differently.

## Prerequisites

- A Linux host with nftables, and cells on an Incus bridge (see the cells guide). The host
  policy below is written for that layout; the tier machine assumes Incus.
- Root on the host, and a *fresh second* way in (a console or a physical keyboard).
  The dead-man revert in step 2 is your safety net; a second path in is the belt to that
  net.
- A pinned Forgejo or equivalent local git remote if a tier may reach one (the build and
  open tiers name its two ports explicitly).
- Python 3.11+ on the host if you adopt the renderer/controller shape; the policies below
  are JSON so any renderer works.

## Steps

### 1. Write the host ingress policy in its own table

**If you installed agent-estate's `baseline` module, read this first.** Its firewall already owns the table name `inet estate`, the file `/etc/nftables.conf`, the revert unit `estate-nft-revert` and the command `estate-firewall` (a default-drop ingress that admits loopback, Tailscale and optionally SSH; see [modules/baseline/README.md](../modules/baseline/README.md)). The policy in this guide is a larger version of the same thing (it adds the cell bridge, DHCP from the bridge and one LAN recovery path), so adopting it **replaces** the module's ruleset on that host. Do not run both: the second load deletes the first table, and `estate doctor`'s `baseline` row fails with "firewall ruleset differs from the config" because the module compares `/etc/nftables.conf` with the ruleset it renders. Either keep the module's firewall and skip this guide's step 1 and 2, or take this guide's policy and accept that red row (a future `baseline` setting to hand the firewall over is not built; until then, leave that row failing on purpose and write the reason next to your policy file). Rename your table (`inet estate_cells`) if you want both to exist while you migrate, and remember two default-drop input chains at the same hook must each accept a packet for it to pass.

The host policy is small and its job is narrow: default-drop on physical interfaces,
admit the tailnet, admit the cell bridge, admit one deliberately chosen narrow local path,
and keep ICMP for diagnosability.

Two rules here are load-bearing and both were learned the hard way:

- **Scope the rules to your own table and never `flush ruleset`.** Incus owns its own
  NAT/forward tables; flushing the ruleset takes the cells' networking down with it.
- **Accept DHCP from the bridge before the conntrack invalid drop.** A restarted cell's
  DISCOVER (0.0.0.0 → broadcast) arrives `ct state invalid` once bridge conntrack is
  loaded; without an explicit accept ahead of the invalid drop, a restarted cell never gets
  an IPv4 address and every other diagnosis you make is wrong.

The file is in [Reference snippets](#reference-snippets). Adapt the physical interface
names (`enp3s0`, …) to your box, and the one LAN recovery CIDR to your own.

**Done when** `nft -c -f nftables.conf` prints nothing and `nft list table inet estate`
shows your chains — but do not load it with `nft -f` by hand; that is what step 2 is for.

### 2. Apply it with a dead-man revert

The first rule you get wrong can cut your own SSH session. So a load is always paired with
an automatic revert, and confirmation is a separate, deliberate act:

```sh
# loads the policy and arms a 90-second revert
20-network/apply.sh

# prove a FRESH ssh connection works (a new connection, not the one you are holding)
ssh -p <port> <you>@vps.example.ts.net true && echo fresh-ok

# then, and only then, make it persistent
20-network/apply.sh confirm
```

`apply.sh` syntax-checks first (`nft -c -f`), loads, touches a pending marker, and arms
`systemd-run --on-active=90s --unit=estate-nft-revert` to delete the table unless you
confirm. `confirm` disarms the timer, removes the marker, copies the file to
`/etc/nftables.conf` and enables `nftables` at boot.

**Done when** a *new* SSH connection works, `apply.sh confirm` prints the persisted path,
and `systemctl is-enabled nftables` says `enabled`.

### 3. Decide the tiers you actually need, and write them as data

A tier is a reviewable JSON file, not a paragraph in a document: one file per tier, each
listing its required inputs, what it allows, what it denies, and the fact that a missing
input means *reject*, not "open". Two fields do most of the work:

- `"agent_may_change": false` — an agent inside the cell cannot widen its own tier.
- `"selection": "trusted-controller-only"` — only the host-side controller attaches a
  tier; a cell cannot ask for one.

The five that proved useful, by kind of work:

| Tier | For | Reaches | Denies |
|---|---|---|---|
| `sealed` | anything whose inputs are already in the cell | broker and estate service paths only | public, LAN, tailnet, host, east-west |
| `build` | compiling and testing | a TLS policy proxy for package/source reads, plus a broker-mediated forge | direct DNS, direct public, LAN, tailnet, host except the proxy, east-west, proxy-unapproved hosts, plain HTTP, uploads, git receive-pack |
| `research` | reading the web | public web, broker/estate reporting | host, tailnet, RFC1918, link-local, metadata, east-west, internal resolver and DNS rebinding |
| `open` | resident personal cells (not an agent-worker default) | direct public 22/80/443 and UDP 443, hosted dev database ports, WebRTC/STUN, controller-derived DNS, the named local forge | host, sibling cells, tailnet-internal, RFC1918, link-local, metadata, other east-west |
| `site` | a production service instance | public 80/443 and UDP 443, QUIC, NTP, the tunnel edge; inbound SSH from one deploy source cell | everything else, including public SSH and dev database ports |

Also write down which tiers may be **narrowed** into which — sealed from any of build,
research, open, site; research from open — with a reason per pair. Then make anything
unknown or *widening* a hard error. A narrowing table is what lets a controller move a
cell down without a human re-reading policy; it is also what stops a typo from granting
more.

`open` deserves one honest note. Its database port list is hygiene, not a security
boundary: nftables cannot scope by hostname, and 443-anywhere already exists, so anyone
who can reach the internet at all can reach a database on 443. Write that in the file so
nobody later mistakes the list for a guarantee.

**Done when** each tier is a file, `reject` is the stated behaviour for missing inputs, and
your narrowing table validates (unknown or widening pairs error out).

### 4. Render and validate before you apply anything

Keep three artefacts separate: the policy contract (the tier files), the renderer that
turns contracts plus discovered host state into concrete nftables members and Incus
ACLs/profiles, and the controller that applies them. The renderer must be runnable offline
and its output diffable; the controller must refuse to bootstrap its own prerequisites.

Before applying, the controller should: render, validate, enumerate the cells it will
touch, **snapshot every piece of state it is about to change**, and only then install
Incus ACLs/profiles, nftables members, any generated proxy config, and units. Arm the same
kind of 90-second snapshot-backed rollback as step 2 and require an explicit `confirm`
after a human reads the diff. A rollback must restore all of it: the Incus objects, the
nftables table, the generated files, the proxy unit's enabled/disabled/masked and
active/inactive state, and the distribution package's mask state.

**Done when** `validate` (or `doctor`) reports the definition hash current, no drift, and
no pending transaction — on a machine where you have changed nothing since the last apply.

### 5. Build work through a proxy with an allowlist

The build tier's idea: give the cell **no** direct public route and **no** direct DNS, and
let one dedicated proxy resolve and fetch what builds actually need.

The allowlist is a short, boring file — package registries, language toolchains, one or two
source hosts — plus a `git_read_post` entry that admits `git-upload-pack` on a
`/<owner>/<repo>(.git)?` path and therefore denies `git-receive-pack`. Uploads, plain HTTP
and unlisted hosts are all refusals, by design.

The proxy has two contracts, and mixing them is the source of the worst incidents here:

- **`prepare-proxy` is an explicit, reviewed, non-transactional host operation.** It masks
  and stops the distribution `squid.service` *before* installing the pinned
  `squid-openssl` package, re-checks masked-and-inactive after install, creates the
  build-only CA and the Squid SSL database, and refuses to run on paths that are symlinks.
  The ordering exists because installing the package auto-starts a default listener that
  would happily serve traffic with none of your policy.
- **`apply` refuses to bootstrap any of that.** If the CA, the SSL database or the service
  mask is missing, `apply` errors; it does not quietly create them. Its rollback restores
  the mask state, because "the proxy was masked before" is part of the state you changed.

**Done when**, from inside a build-tier cell: a package install through the proxy succeeds,
`curl` to an unlisted host is refused, `git clone` from the allowlisted forge reads and a
`git push` is refused, and there is no direct DNS lookup (`dig` fails).

### 6. Attach a tier to a cell — and handle the half-attached state

Attaching writes tier keys and ACLs, so it can be interrupted. Treat a *pending* transaction
as the truth-teller: tier keys already written are **not** proof of a confirmed attach. The
only skip condition is a green scoped `doctor` (tier keys valid, definition hash current,
no drift) **with no pending transaction outstanding** — and the pending marker must be
re-checked *after* the doctor probe, because a concurrent attach can create one and reach a
green doctor between your check and your probe. When in doubt: confirm or roll back, then
attach.

**Done when** `doctor --cell <cell>` is green for that cell and `pending` does not exist.

### 7. Prove the denies, not just the allows

A tier is only real if you have tested from inside the cell, as the agent user:

- the host, on any port you did not name;
- a sibling cell, both directions;
- RFC1918, link-local, and the metadata endpoint;
- tailnet-internal addresses;
- for build: direct DNS, an unlisted host, an upload, a git push.

And a rule about evidence, because it is the easiest thing to fudge: a probe that cannot
distinguish "denied" from "unreachable" is not evidence. Have the probe print exactly one
of `allow`, `deny`, `unknown`; treat `unknown`, emptiness, extra output, a timeout or a
non-zero exit as **failed evidence, never a denial**.

**Done when** every negative row above is a real denial with a recorded output, and every
positive row is reachable through the path you intended.

### 8. Survive a reboot, and re-render when the host changes

Two facts make reboots the place this breaks:

- **Services that bind bridge addresses start before the bridge exists.** A proxy that
  binds the bridge comes up, fails a few times in a second, hits systemd's start limit and
  stays dead; the bridge appears a fraction of a second later. Fix it with a drop-in, not a
  sleep: `After=incus.service`, `StartLimitIntervalSec=0`, `RestartSec=2s`. Install it by
  hand on a rebuilt host — a controller that compares only the main unit file will not see
  the drop-in as drift, so nothing will reinstall it for you.
- **The policy pins discovered host addresses.** A cell or bridge created *after* the last
  render is not in the manifest. After a reboot that brings it up, the reconcile step fails
  on host-address drift — which is correct, fail-closed behaviour, but it reads like a broken
  boot. Re-render and apply (inputs unchanged, only the addresses differ), confirm, and
  re-run the reconcile.

**Done when** after a real reboot the proxy is active without manual intervention, the
reconcile step reports clean, and `doctor` is green for every cell.

## What bit us

- **The build proxy crash-looped at boot.** It started before `incusd` created the bridge,
  failed several times within a second or two, hit the start limit, and stayed dead while the
  bridge came up a fraction of a second later. The reconcile step then failed on "build proxy is not
  active" and armed an egress rollback. Fix: the `After=incus.service` /
  `StartLimitIntervalSec=0` / `RestartSec=2s` drop-in above, installed by hand, because the
  controller deliberately does not manage it.
- **A new bridge was not in the manifest.** A cell created after the policy was rendered
  produced an address the manifest had never seen; the first boot afterwards failed the
  reconcile step on host-address drift. Fix: `apply` + `doctor` + `confirm` (only the
  discovered addresses changed), then reconcile. Lesson: **re-render after adding a cell or
  bridge**, before the next reboot surprises you.
- **A restarted cell lost its IPv4.** The host policy dropped the DHCP DISCOVER because it
  arrived `ct state invalid` after bridge conntrack loaded. Fix: an explicit
  `iifname "<bridge>" udp sport 68 udp dport 67 accept` ahead of `ct state invalid drop`.
- **Installing the proxy package opened a default listener.** `squid-openssl` auto-starts
  the distribution service on install, and disposable policy probes silently hit that
  default listener instead of the test config. Fix: mask and stop the distribution service
  *before* installing, and re-check masked-and-inactive after.
- **Squid initialized its cache but not its TLS certificate state.** `squid -z` creates
  cache directories and leaves `sslcrtd` uninitialized, so the proxy briefly listens and
  then dies. Fix: run `security_file_certgen -c` and `chown` the SSL database before
  starting, or keep a proxy that does not bump TLS.
- **A hermetic self-test passed on the wrong operating system.** The controller's self-test
  passed on macOS and failed on Debian, because generated `/bin/sh` mocks used bash syntax
  and the fixture depended on real install ownership. Fix: run fixtures on the target OS
  before any live apply; an offline test that never ran on the real platform is a hypothesis.
- **`incus config show --format=json` did not exist (Incus 6.0).** The controller's
  machine-readable reads failed for profile, config and network-acl objects. Fix: query the
  REST API at `/1.0/...`; `incus list --format=json` is the only supported JSON listing.
- **Half-attached cells looked attached.** An interrupted attach leaves tier keys written
  but unconfirmed; treating the keys as proof skipped the confirm the transaction still owed.
  Fix: pending marker + green scoped doctor, re-checked after the probe.
- **The database-port list looked like a boundary and was not.** nftables cannot scope by
  hostname, and 443-anywhere exists anyway, so allowing 5432/6379/3306 is hygiene. Write
  that down in the tier file so a later reader does not defend it as a guarantee.

## Reference snippets

Host policy — `/etc/nftables.conf`, the shape that works (adapt interfaces and the single
LAN CIDR):

```sh
#!/usr/sbin/nft -f
# Host ingress policy. Default-drop on physical interfaces; admitted paths are the
# tailnet, the cell bridge, one narrow LAN recovery path, and ICMP.
# Scoped to its own table so Incus's managed NAT/forward tables are untouched.
table inet estate
delete table inet estate

table inet estate {
  chain input {
    type filter hook input priority 0; policy drop;

    iif lo accept
    ct state established,related accept
    # Cell DHCP DISCOVER (0.0.0.0 -> broadcast) arrives ct-invalid once bridge
    # conntrack is loaded; without this a restarted cell never gets IPv4.
    iifname "incusbr0" udp sport 68 udp dport 67 accept
    ct state invalid drop

    iifname "tailscale0" accept
    iifname "incusbr0" accept

    # the one explicit LAN recovery path (example interfaces and range: use your own)
    iifname { "enp3s0", "enp4s0" } ip saddr 192.168.0.0/24 tcp dport 22 accept

    # diagnosability
    icmp type echo-request accept
    icmpv6 type { echo-request, nd-neighbor-solicit, nd-neighbor-advert,
                  nd-router-advert, mld-listener-query } accept

    # tailscale direct-path UDP (avoids DERP-only relaying)
    udp dport 41641 accept
    # DHCP client (box is DHCP on the LAN; broadcast re-bind isn't conntracked)
    udp dport 68 accept
  }
}
```

The dead-man revert, as one block from `apply.sh`:

```sh
nft -c -f "$HERE/nftables.conf" || die "syntax check failed"
nft -f "$HERE/nftables.conf" || die "load failed"
touch /run/estate-nft-pending
systemd-run --on-active=90s --unit=estate-nft-revert \
  sh -c '[ -f /run/estate-nft-pending ] && nft delete table inet estate && echo reverted'
echo "policy LOADED, revert armed for 90s — prove a FRESH ssh connection now, then confirm"
```

A minimal tier file (`sealed.json`, the one that reaches nothing public):

```json
{
  "schema_version": 1,
  "profile": "sealed",
  "selection": "trusted-controller-only",
  "agent_may_change": false,
  "missing_input_behavior": "reject",
  "required_inputs": ["broker_unix_socket", "estate_unix_socket"],
  "nftables": {
    "default_policy": "drop",
    "allow": { "network": [] },
    "deny": ["public", "lan", "tailnet", "host", "east_west"]
  },
  "incus_acl": { "default_egress": "reject", "allow": [] }
}
```

The narrowing table, which is what makes tiers safe to compose:

```json
{
  "schema_version": 1,
  "relation": "allowed-egress-subsets",
  "allowed_narrowing": [
    { "broader": "build",    "narrower": "sealed", "reason": "removes every build network input" },
    { "broader": "research", "narrower": "sealed", "reason": "removes public web egress" },
    { "broader": "open",     "narrower": "sealed", "reason": "removes public web egress" },
    { "broader": "open",     "narrower": "research", "reason": "research keeps web, adds research controls" },
    { "broader": "site",     "narrower": "sealed", "reason": "removes web and the tunnel edge" }
  ],
  "unknown_or_widening_behavior": "reject"
}
```

## Keeping it healthy

- **After every boot:** proxy active without help, reconcile clean, `doctor` green for
  every cell. Automate the check; the failures above are silent ones.
- **After every new cell or bridge:** re-render before the next reboot, or the reconcile
  step will fail closed on addresses it has never seen.
- **After every host rebuild:** reinstall the boot-ordering drop-in by hand. The controller
  compares only the main unit, so drift detection will not remind you.
- **Review the allowlist** like code: it is the list of everything a compromised build can
  talk to. Keep it short, and keep `git-upload-pack` the only git verb on it.
- **Keep the rollback honest:** snapshots of Incus objects, nftables, generated files and
  service mask state, and one rehearsal where you roll back on purpose.
- **Rotate the build CA** on a schedule and after any suspected cell compromise; a
  build-tier CA that has been inside a compromised cell is not a boundary any more.
- **Watch for drift in the tier files themselves.** `agent_may_change: false` protects the
  cell; nothing protects the repository, so version and review it like the firewall it is.

Last checked: 2026-10, Debian 13 with Incus cells.
