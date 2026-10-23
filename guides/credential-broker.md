# The credential broker: keys that never enter an agent's container

When one box serves several people and several provider accounts, the tempting design is to
put keys in the agent's environment and hope the agent behaves. This guide describes the other
design, the one that survived contact with real use: a small host daemon (`brokerd`) that owns
credential custody, hands out **leases** against account pools, injects third-party credentials
**host-side** so the secret never crosses into the container, and authenticates every request
by **kernel-derived peer identity** rather than by anything the caller claims. There is a lot of
machinery here, and that is the point of the gate below: **most people should not build this.**
Read section 1, decide honestly, and if the answer is "no", the simplest version in step 2 is
the whole answer.

## Do you need this?

**Skip it — and this is the common case — unless all of these are true:**

- **three or more accounts** of the same provider (several subscription accounts, or several
  organisations you keep separate), where the point is rotation, cooldowns and quota;
- **several agents and at least one other person** sharing one physical box, so "who asked" has
  to be answerable at a kernel boundary, not by a log line;
- **a real containment requirement**: one principal's agent must not be able to spend another
  principal's credentials even if it is root inside its own container;
- you are willing to own a daemon, a registry, a UID allocator, an ordered revocation path and
  a boot-time reconcile.

**A single developer with one or two accounts on one box should not run this.** The honest
minimal version (step 2) is three pieces: one key file per realm with a **name contract**, an
exec wrapper that loads exactly one realm and refuses rather than falling back, and a usage
poller that writes numbers. That covers the daily 90%. What the broker adds is account rotation,
cooldowns, peer-authenticated leases and third-party credential injection — every one of those
is a solution to "many accounts, many agents, one box".

**What it costs:** a systemd-managed daemon, a SQLite registry, a reserved UID range, an Incus
proxy device per binding, an append-only audit log, and the discipline to reconcile after every
reboot. Plan on more operational attention than the rest of the core modules combined.

## Prerequisites

- The single-account version working: keys stored per realm with a name contract, an exec
  wrapper, and a usage poller. agent-estate's `keys` module is that version for one realm (one
  key file, a managed-name list, scrub-and-inject shims) and its `usage` module is the poller;
  several realms are what this guide adds. Do not start the broker before this is boring.
- Containers (Incus or equivalent) with isolated idmaps, because the whole identity story rests
  on "the container boundary is the principal boundary".
- systemd socket activation, so the daemon's listeners are passed as inherited descriptors and
  the daemon can refuse anything unexpected.
- A place for human recovery material: a password manager, a sealed note, a safe. **No code in
  this design reads your vault**, so the human recovery path is a step you own explicitly.

## Steps

### 1. Write the decision down

State, in one paragraph in your repo, which of these you have: the account count, the number of
principals sharing the box, and the containment requirement. If any is absent, stop here and run
step 2 only. A broker built for one account is a daemon you maintain for nothing.

**Done when:** the decision paragraph exists and names either "single-account version only" or
the specific multi-account/multi-principal property that justifies the rest.

### 2. Build the single-account version first (this is the useful part)

Three pieces, no daemon:

1. **One key file per realm**, `0600`, plus a second file listing the *names* of every variable
   your setup manages. The name contract is the safety property: nothing loads a variable that is
   not on the list, and a key present in one realm but absent in another **refuses** rather than
   falling back to a neighbour's value.
2. **An exec wrapper plus per-tool shims** in front of `PATH`. Interactive shells hold nothing;
   each shim runs the real binary through the wrapper, which scrubs every managed name out of
   the inherited environment, sources exactly one realm's file, and execs. The realm comes from
   an explicit variable, defaulting to one documented value.
3. **A usage poller** on a timer: read each account's usage endpoint, write a local snapshot,
   refresh a login only when it is *expired and has no live session* (see papercuts), and set a
   cooldown flag at 100% that clears when every limit reads under 100%.

To get keys onto the host, stream them over SSH **on stdin** into an installer that validates
against the name contract, rejects unknown/shadowed/empty values and symlinks, and atomically
replaces the file (temp file, `os.replace`, `fsync`, `umask 077`). Nothing is written to a
command line, an argument list or a log.

```sh
# the secret travels on stdin only; the destination path is the only argument
ssh <vps> 'umask 077 && cat > ~/.config/agent-env/keys.tmp' < ./keys.local
ssh <vps> 'mv ~/.config/agent-env/keys.tmp ~/.config/agent-env/keys'   # or use the validating installer
```

**Done when:** a shimmed tool works in a fresh shell with no keys exported in the environment,
the key file is `-rw-------` owned by the agent user, and asking for a variable that belongs to
the other realm fails with a clear refusal instead of an empty value.

### 3. Reserve the identity space (start of the broker proper)

The broker's core idea: **every binding between a container and a principal gets its own host
UID, and that UID *is* the identity.** Reserve a range that nothing else on the host uses
(for example `3000–3999`), one fixed group shared by every binding account, and a registry
table whose rows are the only source of truth mapping UID → (container, principal, state).

Allocation rules worth copying verbatim:

- A UID is eligible only when its row is `reusable` **and** no passwd entry exists **and** no
  process runs as it **and** no proxy device references it.
- Exhaustion of the range is a **loud, fail-closed refusal** — never allocate outside the range.
- The row is mutable state with exactly one status; history goes in a separate append-only audit
  log (every assign, revoke, teardown event), never rewritten.

Lifecycle, one canonical sequence:

| State | Meaning |
| --- | --- |
| `free` | never used, or verified clean |
| `active` | allocated, account created, device attached, serving |
| `revoked` | requests refused immediately, leases terminated, teardown not done |
| `tombstoned` | device removed, no process runs as the UID, account and group membership removed |
| `reusable` | the allocator has *verified* teardown; residue (device, process, account) is gone |

**Done when:** you can create a synthetic binding, revoke it, tear it down, and watch the row
walk `active → revoked → tombstoned → reusable` with the audit log recording each step, and a
second allocation attempt on the same UID before `reusable` is refused.

### 4. Wire the transport so the identity is real

The container cannot open a host socket and prove who it is; a plain Unix socket gives you
`uid=0` for everything. The trick that works: one **proxy device per binding**, with the device
configured to present a specific UID to the host socket, plus a socket the daemon reads with
`SO_PEERCRED`.

```
# per binding: an Incus proxy device, not a bind mount of the socket
incus config device add <cell> estate-broker proxy \
  listen=unix:/run/estate-broker.sock   \
  connect=unix:/run/estate/broker.sock  \
  bind=instance \
  security.uid=<binding-uid> security.gid=<binding-group-gid>
```

Then the permissions, which are where this design is usually broken:

| Object | Owner:group | Mode | Why |
| --- | --- | --- | --- |
| host socket | `root:<binding-group>` | `0660` | every binding account is in the group; any other host user is refused at the socket, not just by policy |
| its parent directory | `root:<binding-group>` | `0711` (group-traverse) | the proxy connects *as the binding UID* and must reach the socket by path; `0700` blocks it silently |
| in-container socket | `<agent user>:<in-container group>` | `0660` | the container's `estate` group holds exactly the accounts that may use it; every other in-container UID is denied |
| revoke/control socket | `root:root` | `0600` | separate path, never exposed through a device; only the root controller can revoke |

The daemon then: reads `SO_PEERCRED` on the accepted socket, refuses `uid 0`, refuses a UID
outside the reserved range, refuses a UID with no registry row, refuses a caller-supplied
principal (identity is derived, never asserted), refuses a revoked or tombstoned binding, and
refuses a container that is not **single-principal**. Each refusal is logged loudly with the UID
and the reason.

**Done when:** from inside the container, a request as the agent account succeeds and a request
as any other account fails; from the host, a request as a normal user fails; and the daemon's log
shows the refused `uid` it saw for each attempt.

### 5. Leases, cooldowns, and revocation that is ordered rather than atomic

Revocation touches the store, live requests, the device, the process and the account. It cannot
be atomic across those, so make it **ordered and fail-closed**:

1. **Mark revoked in the store first.** From that instant every request on the binding is
   refused, whatever else fails. Terminate its leases. Kill only live requests pinned to that
   binding, and return only after an authoritative readback shows zero live, plus shutdown of
   every accepted socket.
2. **Tear down**: remove the proxy device, verify no process runs as the binding UID, remove the
   account and its group membership, then set `tombstoned`.
3. **Verify, then `reusable`.** Only the allocator may promote a row, and only after confirming
   no residue; the non-active row keeps acting as a refusal barrier for a full handler timeout.

Leases are where quotas live: an account is leased per request, a 100% usage reading sets a
cooldown the lease manager refuses through, and the pool exposes a **human-controlled pointer**
to the preferred account rather than an automatic winner. Account state holds only non-secret
metadata plus opaque identity fingerprints — never the OAuth token itself, which stays in the
harness's own config directory so the vendor can refresh it.

**Done when:** killing the process between step 1 and step 2 reconverges on the next reconcile
run without handing the UID out again; a revoked binding's request is refused within the same
second; and the audit log has one revoke event and one teardown event.

### 6. Inject third-party credentials host-side

For MCP relays and other HTTP services that need a token, the token should never enter the
container. Run a small host-side proxy: the container talks to a local relay, the proxy attaches
the credential and forwards. Describe each provider as **declarative data**, not code:

- scheme, host, port, auth kind (bearer, OAuth-bearer with a token endpoint and refresh window);
- allowed operations: method, a path pattern, and a maximum request and response size;
- the exact request headers allowed through, and which response headers to strip;
- an explicit policy for cross-host redirects (the safe answer is "follow credential-less").

Per-provider custody: the secret is imported once, on stdin, straight into custody; the proxy
reads it from custody at request time; the container never sees it, in any form, at any point.

**Done when:** the relay works from inside the container with no credential in the container's
environment or filesystem, and a request outside the allowed path pattern is refused by the
proxy (prove both: the allow and the refuse).

### 7. Doctor checks and the orphan sweep

The daemon needs a health verb an agent can run and read:

- every registered binding has a live proxy process owned by its binding UID and an `active`
  row;
- **orphan sweep**: any process running as a UID in the reserved range with no active row, any
  passwd entry matching the binding-account pattern with no row, and any row with no
  user or device — each reported loudly;
- the socket paths, owners and modes match the table above.

**Done when:** `brokerd doctor` (or your equivalent) reports `ok` on a healthy box and, when you
create one deliberately, names the orphan you planted.

### 8. Reconcile after every boot

After a reboot the proxy device can bind the socket into the container's root filesystem
`/run` *before* the tmpfs is mounted over it: the path exists, nothing listens, and the daemon
looks healthy. Handle it in the boot sequence: probe the socket **from inside** each bound
container, bounce only the device (remove + re-add, readback-verified) when that is the *only*
finding, and fail the boot loudly if a socket is still dead. See the home-server guide's boot
steps for the rest of that sequence.

**Done when:** after a reboot, the boot unit's log shows one verified probe per bound container
and the unit exits 0; a deliberately dead socket fails the unit instead.

## What bit us (papercuts)

- **In-container root walked straight through a `0600` socket.** Root bypasses filesystem modes,
  so per-socket permissions cannot separate *principals* that share a container. → The container
  boundary is the principal boundary: attach a binding only to a container registered as
  single-principal, and re-check that flag on **every** request so a container later converted to
  multi-principal is refused mid-lease. Fail closed and loudly.
- **Without a dedicated UID per binding, every container presented as root** and the daemon could
  not tell them apart. → A binding without its own UID is invalid; refuse `uid 0` and any UID
  outside the reserved range before doing identity or control work.
- **A `0700` socket directory silently blocked the proxy.** The secured proxy connects *as the
  binding UID*, so it could not traverse into the socket's directory; the failure looked like the
  daemon ignoring requests. → Parent directory `0711` (or group-traverse for the binding group),
  socket itself `0660`, and prove traversal as a binding account during setup.
- **An owner-only in-container socket locked out the human account.** The container had two
  identities of the *same* principal (human and agent); `0600` denied one of them. → Group-scope
  the socket to an in-container group that contains exactly those accounts and nothing else. That
  is still one principal; the rule about single-principal containers does not change.
- **`SO_PEERCRED` carries no generation number.** Reusing a UID while an old proxy process could
  still present it would let a dead binding act. → Never reallocate a UID before teardown is
  verified (`reusable`), and keep the non-active row as a refusal barrier for a full handler
  timeout.
- **The usage poller logged a live session out.** Refreshing a login rotates the refresh token,
  which invalidates the token the running session holds. → Refresh only when the login is expired
  **and** the account has no live session; and use a setup token for launched sessions so a live
  session does not pin a keychain login at all.
- **The simplest harness launch pinned the interactive login.** A session started from the stored
  login held the keychain open and blocked rotation. → Launch with a minted setup token, and keep
  the vendor's own config directory for the OAuth the vendor refreshes.
- **A realm shim fell back instead of refusing**, so a command in one realm quietly used the other
  realm's key. → Fail closed per realm: a managed name absent from the requested realm is a
  refusal, not a fallback. Same for the name contract: unknown or shadowed names are rejected at
  import time.
- **A scripted `incus exec` ate the rest of the script.** `incus exec` consumes the caller's
  stdin, so the next lines of the loop became the container's input. → Every scripted exec gets
  `</dev/null`, without exception.
- **A partial revocation looked like a success.** Steps of a multi-system teardown fail
  independently, and a stuck UID reused too early is a real safety hole. → Ordered, fail-closed,
  idempotent steps, an authoritative readback after each, a loud alarm plus a reconciler on
  partial failure, and a UID that is never reallocated while stuck.
- **A secret appeared on a command line once, and that was enough.** Arguments are visible in
  process listings and shell history. → Import secrets on stdin; the destination path is the only
  argument; nothing is logged but the resulting generation number.
- **No vault was in the loop, and the design assumed one.** Nothing in the code read a password
  manager, so human recovery material had no defined home. → Decide the human recovery path
  explicitly at setup (a password manager item with the repo password and keys, refreshed at each
  rotation); the broker is custody for services, not a recovery plan for humans.

## Reference snippets

A provider definition as data (this is the whole shape; keep the sizes small on purpose):

```json
{
  "name": "<vendor>",
  "scheme": "https",
  "host": "mcp.<vendor>.com",
  "port": 443,
  "auth_kind": "bearer",
  "provider_class": "public",
  "realm_scoped": true,
  "operations": [
    {
      "name": "mcp",
      "methods": ["POST", "DELETE"],
      "path_pattern": "/mcp\\?project_ref=[A-Za-z0-9_-]{1,64}(?:&read_only=true)?",
      "max_request_bytes": 8388608,
      "max_response_bytes": 8388608
    }
  ],
  "allowed_request_headers": ["Accept", "Content-Type", "MCP-Protocol-Version", "Mcp-Session-Id"],
  "strip_response_headers": [],
  "follow_cross_host_redirect_credential_less": false
}
```

The identity/permission matrix, as a checklist you can test:

```
binding UID range            3000-3999, allocator-owned, refuse outside and refuse uid 0
binding account              brk-b<uid>, primary group <binding-group> (fixed alphabet, no cell/principal strings)
host socket                  root:<binding-group> 0660
host socket parent dir       root:<binding-group> 0711   <- 0700 breaks the proxy silently
control/revoke socket        root:root 0600, separate path, never proxied
in-container socket          <agent user>:<in-container group> 0660
                             <- group contains exactly the principal's accounts
brokerd refusals             uid unmapped | uid 0 | uid out of range | caller-supplied principal
                             | binding revoked/tombstoned | container not single-principal
```

Import a secret without ever putting it on a command line:

```sh
# read it from the one place it already lives, pipe it into custody, print only the generation
incus exec <cell> -- sudo -u <agent> sed -n 's/^export <NAME>=//p' ~/.config/agent-env/keys \
  | sudo -u brokerd python3 /usr/local/lib/estate/import_secret.py <provider>-<realm>
# expect: {"generation": 1, "provider": "<provider>-<realm>"}
```

## Keeping it healthy

- **Every boot:** the socket probe per bound container (step 8), then the doctor verb.
- **Daily:** the usage poller's snapshot per account; a cooldown that is stuck on with every
  limit under 100% is a bug, not a quota. Check the audit log for revoke/teardown events you did
  not expect.
- **Weekly:** the orphan sweep — processes in the reserved UID range with no row are the residue
  of a failed teardown; fix the row, do not kill the process and move on.
- **On every account change:** import on stdin, record the new generation, and rotate the human
  recovery copy in the same sitting. A rotation that exists only on the box is a rotation you
  cannot restore.
- **When something looks wrong, read the refusals first.** Every refusal names a UID and a
  reason; the daemon's log is the fastest map of what the topology actually is.
- **Before you scale it up:** add one principal, one container, one binding — prove the negative
  tests (refused principal, cross-container access, host user refused, revocation ordering) —
  and only then add the next.

Last checked: 2026-10, Debian 13 with Incus cells.
