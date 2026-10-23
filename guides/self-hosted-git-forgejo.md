# Self-hosting a git forge: Forgejo as the hub every machine and agent pushes to

This guide stands up [Forgejo](https://forgejo.org) on your Linux box as the git remote
that your Mac and every agent cell push to, with GitHub kept as a separate, deliberate
mirror for publication. You get a push target that never rate-limits you or asks which
token scope it is allowed, one account per person, and a place where agents can create
branches and repositories without holding a credential that can also publish your public
code. It also carries the two patterns that are easy to get wrong and expensive to
discover late: minting credentials agents can use without the token ever landing in a
transcript, and moving every existing clone onto the new remote without losing the GitHub
URL it already had.

## Do you need this?

**Skip it** if you have one machine and no cells, if your agents only ever push to
branches you review by hand, or if private GitHub repos with scoped tokens are already
comfortable. Nothing else in agent-estate requires a self-hosted forge: the default git
remote is whatever you already use.

**Do it** if any of these are true:

- Agents push many times an hour and you are tired of per-push token scopes, rate limits
  or "which account is this clone using".
- You want a hub that keeps working when an external forge is down or throttling you.
- You want some repos to never leave your box, while a handful still publish publicly.
- You want per-person identities so that a partner's push is attributable to them.

**What it costs.** Forgejo is one static binary plus SQLite: a few hundred MB of RAM and
a few GB of disk for repos and LFS, one systemd unit, one `app.ini`. The operational
weight is low but real: it is a service you must back up, update and monitor, and while
the box is down your `origin` is down. That last point is a design decision, not an
accident — the pattern below keeps you committing locally instead of silently
re-pointing at GitHub.

## Prerequisites

- agent-estate core set up (`INSTALL.md`, `estate doctor` green), and at least one agent cell or Mac clone that can reach the
  box (the egress guide matters here: a cell in a restricted tier can only reach the
  forge listeners you explicitly allow, ports 2222 and 3000 below).
- A stable name for the box that resolves from every client. A tailnet FQDN is the easy
  choice; a hostname alias in `~/.ssh/config` is not, for reasons in step 5.
- Debian 12+/Ubuntu 24.04+ or equivalent on the box, with root.
- Optional: a GitHub repo you want to mirror. Not needed until step 8.
- Human decisions: who gets an account, and who is admin. Accounts are per person from
  day one — one shared account destroys attribution, and attribution is most of the value.

## Steps

### 1. Install the binary, verified

Download the release for your architecture, check its published checksum, and install it
outside the package manager so you control the version:

```sh
cd /tmp
V=16.0.2
curl -fsSLO "https://codeberg.org/forgejo/forgejo/releases/download/v$V/forgejo-$V-linux-amd64"
curl -fsSLO "https://codeberg.org/forgejo/forgejo/releases/download/v$V/forgejo-$V-linux-amd64.sha256"
sha256sum -c "forgejo-$V-linux-amd64.sha256"
install -m 0755 "forgejo-$V-linux-amd64" /usr/local/bin/forgejo
rm -f "forgejo-$V-linux-amd64" "forgejo-$V-linux-amd64.sha256"
```

Create a service account with no shell, and a state tree it owns:

```sh
useradd --system --home-dir /srv/forgejo --shell /usr/sbin/nologin forgejo
install -d -o forgejo -g forgejo -m 0750 \
  /srv/forgejo /srv/forgejo/data /srv/forgejo/repos /srv/forgejo/log /srv/forgejo/custom/conf
```

Install a systemd unit that runs `forgejo web` as that user with `WorkingDirectory` and
`Environment=USER=forgejo HOME=/srv/forgejo`, then `systemctl daemon-reload &&
systemctl enable --now forgejo`.

**Done when** `forgejo --version` prints your pinned version and `systemctl is-active
forgejo` says `active`.

### 2. Write `app.ini`

Copy the configuration in [Reference snippets](#reference-snippets) to
`/srv/forgejo/custom/conf/app.ini` (mode 0640, owned by the service account) and restart
the unit. Three settings there are load-bearing and each has its reason in the comments:
the built-in SSH server on its own port, `BUILTIN_SSH_SERVER_USER = git`, and
push-to-create in a user's own namespace with organisation creation left off.

**Done when** `curl -fsS http://127.0.0.1:3000/api/v1/version` returns JSON, and
`ss -tlnp | grep -E ':(3000|2222) '` shows both listeners on the box loopback/all
addresses.

### 3. Make `git@` the login

Forgejo's built-in SSH server answers only to `RUN_USER` unless you name a user, so
without `BUILTIN_SSH_SERVER_USER = git` every clone URL on every machine reads
`forgejo@box`, which nobody wants to type or paste into a script. The key is in the
`app.ini` above; after a restart:

```sh
ssh -p 2222 -T git@vps.example.ts.net     # expect Forgejo's greeting, not a shell
```

**Done when** that greeting appears and this prints a hash:

```sh
git ls-remote ssh://git@vps.example.ts.net:2222/<you>/<repo>.git
```

### 4. Create one account per person, with one-time passwords

Never seed accounts with passwords in a shell history. Generate them, force a change on
first login, and write them to a root-only file the human collects once:

```sh
CREDS=/root/forgejo-bootstrap-creds.txt
as_forgejo() { sudo -u forgejo /usr/local/bin/forgejo \
  --config /srv/forgejo/custom/conf/app.ini "$@"; }

pw=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 20)
as_forgejo admin user create --username <you> --email you@example.com \
  --password "$pw" --must-change-password --admin
printf '%s: %s\n' <you> "$pw" >> "$CREDS"
chmod 0600 "$CREDS"
```

Register each person's SSH public key on their own account (web UI or
`admin user` + the API). Registration is disabled in `app.ini`, so no account appears that
you did not create.

**Done when** `as_forgejo admin user list` shows exactly the principals you intended, and
each one has at least one working key.

### 5. Use the FQDN in remote URLs, not an SSH alias

A remote URL gets baked into every clone on every machine and survives for years. Write
the full form so it keeps working across IP changes, new clients, and an edited
`~/.ssh/config`:

```
ssh://git@vps.example.ts.net:2222/<owner>/<repo>.git
```

An alias like `forge:owner/repo.git` works only where that alias is defined and correct;
a machine whose `forge` alias points somewhere else makes the shorthand
fail with a confusing "does not appear to be a git repository".

**Done when** `git ls-remote` on the full URL prints a hash from the Mac *and* from inside
at least one cell.

### 6. Create repositories: push-to-create for people, API for the curated org

`ENABLE_PUSH_CREATE_USER = true` means any account can make a repo by pushing to its own
namespace — agents get this for free, with no token that can create anything in an
organisation:

```sh
git init -q mytool && cd mytool && git commit --allow-empty -m init
git remote add origin ssh://git@vps.example.ts.net:2222/<you>/mytool.git
git push -u origin main
```

Organisation repos stay curated: leave `ENABLE_PUSH_CREATE_ORG` unset and create them
deliberately through the API (see step 7), so nothing can spray repos into a shared
namespace.

**Done when** a push with no pre-created repo succeeds, `git ls-remote` shows the branch
from another machine, and a clone of it succeeds in a cell.

### 7. Give agents a token that never enters a transcript

Two patterns, both of which keep the secret out of `argv`, the environment, and the
agent's conversation:

**Box-side proxy for admin calls.** Put the admin token in a root-only file
(`/root/.forgejo-api-token`, mode 0600) and install a tiny wrapper that runs as root,
reads the token, passes it to `curl` through a file descriptor, and unsets the variable
before exec. Agents call `sudo fj-api GET /repos/...` and never see the secret. The
wrapper is in [Reference snippets](#reference-snippets).

**Per-cell token for agents.** Mint one token per cell with every write scope *except*
`admin` and `user` — repo, org, issue, package, misc, notification — so a compromised cell
can push code but cannot create identities:

```sh
SCOPES=write:repository,write:organization,write:issue,write:package,write:misc,write:notification
sudo -u forgejo forgejo admin user generate-access-token -c /srv/forgejo/custom/conf/app.ini \
  --username <service-user> --token-name "cell-<cell>" --scopes "$SCOPES" --raw
```

Deliver it into the cell as `root:<agent-group>` mode 0640 at a fixed path, and install a
client that reads the file into FD 3, unsets the variable, then curls
`http://<bridge-gateway>:3000/api/v1...`. Re-running the mint step revokes the old token
and issues a new one, so rotation is one command.

**Done when** `sudo fj-api GET /orgs/<org>/repos` returns JSON from the box, and inside a
cell `fj GET /orgs/<org>/repos` returns the same, with no token visible in `ps`, `env`, or
a transcript.

### 8. Dual-home: Forgejo is `origin`, GitHub is a gated mirror

The contract, applied to every repo on every machine:

| Remote | Points at | Push policy |
|---|---|---|
| `origin` | Forgejo | Ungated. Push at every coherent checkpoint. |
| `github` | GitHub, on repos that publish | Gated. One explicit human authorisation per push, mirror included. |

Moving an existing clone without losing history or the GitHub URL, per repo:

1. Ensure the Forgejo repo exists (API `POST /orgs/<org>/repos`, private by default).
2. **Deepen shallow clones first.** Forgejo refuses `shallow update not allowed`, and one
   shallow clone will abort a whole batch. `git fetch --unshallow origin` from the clone's
   *current* remote — a fetch, never a push.
3. Push refs with `git push <url> --all` and `git push <url> --tags`. Never `--mirror`: it
   deletes forge-side refs and republishes remote-tracking refs.
4. Point the default branch at the clone's HEAD branch.
5. Add `github` with the pre-cutover URL *verbatim*, then repoint `origin` at Forgejo.
6. Verify with a checklist, not a vibe (see snippets): `origin` URL is Forgejo, `github`
   URL is byte-identical to what it was, and no local branch or tag is missing from the
   forge.

For repos you also want mirrored *from* GitHub, create a second repo as a pull mirror in
its own namespace (`mirrors/<name>`, `POST /repos/migrate` with `"mirror": true` and an
interval). A pull mirror is read-only and cannot be a push target — see the papercuts.

**Done when** for every repo `git remote get-url origin` is the Forgejo URL, the GitHub
URL is unchanged, and the missing-refs check prints zero.

### 9. Prove a round trip

One commit each way, with the SHA checked at every hop: commit on the Mac and push; clone
from Forgejo inside a cell, read the file, commit and push; pull on the Mac and confirm
the cell's SHA is now `HEAD`. If you use a temporary credential for this, tear it down
after and record where.

**Done when** the Mac's `HEAD` equals the SHA the cell reported pushing, and the cell read
the file the Mac wrote.

## What bit us

- **`git@` was refused; only the service user answered.** `forgejo@box:2222`
  authenticated and `git@box:2222` did not. Fix: set
  `BUILTIN_SSH_SERVER_USER = git`, back up the live `app.ini` before editing, restart, and
  put the same line in the tracked source so a redeploy cannot silently revert it.
- **A pull mirror cannot also be a push target.** Setting `mirror_interval` on an ordinary
  repo returns HTTP 200 and leaves `mirror=false`; pushing to a real mirror is refused with
  `Mirror Repository ... is read-only`. Fix: two repos per mirrored project — one pushable,
  one a one-way mirror.
- **A single shallow clone aborted the whole cutover.** Forgejo's `shallow update not
  allowed` killed the batch partway through. Fix at the root: deepen any shallow clone
  from its current remote before pushing, and make a per-repo failure skip that repo
  instead of aborting the run.
- **A stand-in upstream could not be imported.** Forgejo refuses local-path imports
  (`You are not allowed to import local repositories`) unless you loosen `IMPORT_LOCAL_PATHS`.
  Stage the mirror gap from the mirror side instead — rewind the mirror's branch and
  delete a tag, then let one sync close it — which exercises the same fetch-and-advance path.
- **`--mirror` is the wrong push flag here.** It would delete refs that exist only on the
  forge and republish remote-tracking refs as branches. `--all` plus `--tags` is what you
  want.
- **Remote shorthand hid a broken alias.** `forge:owner/repo.git` failed on a machine whose
  `forge` alias pointed elsewhere. Always publish the explicit `ssh://` URL.
- **A stale remote-tracking ref made a deploy checkout look clean.** `main...origin/main`
  read as level while `origin/main` was days old. Compare against `git ls-remote` before
  claiming the box and the forge agree.
- **`git pull --ff-only` still refused on unrelated local changes** because a global
  `pull.rebase = true` made git evaluate the rebase precondition first (exit 128). For
  deploy checkouts use `git fetch` then `git merge --ff-only`.
- **A token minted for an account with a forced password change was unusable.** Mint
  service tokens only for an account that is already usable, and keep one-time passwords in
  the 0600 root file until the human has collected them.
- **A helper that lies about its exit status.** The in-cell `fj` client documented "4xx
  exits non-zero", but `fj GET /repos/<org>/<missing> && echo EXISTS` printed `EXISTS` on a
  404. Check the JSON body (or the HTTP code) rather than trusting a friendly wrapper's
  help text.
- **The forge moved while a lane was working.** `main` advanced under an agent that had
  not fetched, and its unrelated dirty work tree made a merge the wrong move. Fix: fetch
  before the final push, and publish the isolated checkpoint branch instead of dragging
  unrelated state through `main`.
- **Order the shared checkout last.** The repo that every other lane pushes from should be
  the last one re-pointed, and the other lanes should be told the moment `origin` moves.

## Reference snippets

`/srv/forgejo/custom/conf/app.ini` — the shape that works, with the reasons inline:

```ini
APP_NAME = estate forge
RUN_USER = forgejo
WORK_PATH = /srv/forgejo

[server]
PROTOCOL = http
HTTP_ADDR = 0.0.0.0
HTTP_PORT = 3000
DOMAIN = vps.example.ts.net
ROOT_URL = http://vps.example.ts.net:3000/
; Built-in SSH server on its own port: git SSH never touches host sshd, and a
; task credential can never become a host login.
START_SSH_SERVER = true
SSH_PORT = 2222
SSH_LISTEN_PORT = 2222
; Without this the built-in server answers only to RUN_USER, so every clone URL
; would read forgejo@host.
BUILTIN_SSH_SERVER_USER = git
LFS_START_SERVER = true

[database]
DB_TYPE = sqlite3
PATH = /srv/forgejo/data/forgejo.db

[repository]
ROOT = /srv/forgejo/repos
DEFAULT_PRIVATE = private
; Agents create repos in their OWN user namespace by plain git push.
; ENABLE_PUSH_CREATE_ORG stays absent: the shared org remains curated.
ENABLE_PUSH_CREATE_USER = true

[service]
DISABLE_REGISTRATION = true
REQUIRE_SIGNIN_VIEW = true

[security]
INSTALL_LOCK = true

[log]
MODE = file
ROOT_PATH = /srv/forgejo/log
LEVEL = Info

[actions]
; No CI runners in v1; keep them off until you actually want them.
ENABLED = false
```

`/usr/local/sbin/fj-api` — box-side API proxy, token never in `argv` (run as root via
`sudo`):

```sh
#!/bin/sh
# usage: fj-api <METHOD> <API_PATH> [body]   JSON body, when declared, on stdin
set -eu
m=$1; p=$2; want_body=${3:-nobody}
T=$(cat /root/.forgejo-api-token)
exec 3<<EOF
Authorization: token $T
EOF
unset T
if [ "$want_body" = body ]; then
  exec curl -sS -X "$m" -H @/dev/fd/3 \
    -H "Content-Type: application/json" --data-binary @- \
    "http://localhost:3000/api/v1$p"
fi
exec curl -sS -X "$m" -H @/dev/fd/3 "http://localhost:3000/api/v1$p"
```

The dual-home checklist, as a comparison rather than a hope:

```sh
# every local branch and tag must exist on the forge
missing=$(comm -23 \
  <(git -C "$repo" for-each-ref --format='%(refname) %(objectname)' refs/heads refs/tags | sort) \
  <(git -C "$repo" ls-remote origin | awk '{print $2" "$1}' | sort) | wc -l | tr -d ' ')
[ "$missing" = 0 ] || echo "FAIL: $missing refs missing from origin"
```

Rollback is possible because you snapshot `.git/config` per repo before touching remotes:
restore every `remote.*` key byte-for-byte from the snapshot, drop remotes the snapshot did
not have, then `git fetch --prune` to clear tracking refs that still describe forge state.

## Keeping it healthy

- **Back up the state tree, not just the repos.** `/srv/forgejo/repos` (including LFS) and
  the SQLite database. Stop the unit for a consistent copy, or use `VACUUM INTO`. The
  instance's `SECRET_KEY` lives on the box and is not in `app.ini`: a restore without it
  invalidates sessions and mints new token secrets.
- **Update deliberately.** Pin a version and its checksum; upgrade by replacing the binary;
  read the release notes first, and restart the unit after.
- **Watch disk.** Mirrors are full copies, LFS is invisible in `du` of working trees, and
  repos only grow. Alert on the dataset, not on a weekly look.
- **Monitor the three things that fail.** Unit active, `:3000` answering, `:2222` greeting.
  Add "last successful push age" if you want to catch a client-side break before you need
  the forge.
- **Rotate cell tokens** on any cell rebuild or offboarding, and re-mint rather than editing
  scopes in place.
- **Test one restore** into a scratch directory. A backup you have never restored is a
  hypothesis.

Last checked: 2026-10, Debian 13 host and macOS clients.
