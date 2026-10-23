# Running a personal assistant gateway (OpenClaw) on the box

OpenClaw is a third-party, open-source gateway that runs one or more personal agents as a long-lived service. It connects them to chat channels (Discord, Telegram and similar), runs scheduled automations, and answers direct agent turns from a CLI. Upstream is [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw), with docs at docs.openclaw.ai. This guide covers running it as a systemd user service on the Linux box, updating it safely, and the failure modes a working setup hits.

Everything below is a lesson from running it, not a recommendation to run it. Upstream moves fast, and the mistakes that cost the most were updates, not configuration.

## Do you need this?

- **Skip it** unless you want an agent that is always on, answers in a chat app, and runs jobs on a schedule while you are away. If you only run agents in a terminal you start yourself, skip it.
- **Do it** if you accept an always-on service with its own secrets, its own state database, and channel accounts that act on your behalf.
- **Cost:** expect the gateway process to hold a couple of GiB of resident memory, and somewhat more for the whole service once its child processes are counted. Each Codex app-server child adds a few hundred MiB if you use Codex as a backend. An update takes the gateway down for tens of minutes. Its state database migrates forward during an update, which is why rollback needs a cold copy (step 6).

## Prerequisites

- The base box setup, which is agent-estate's `baseline` module ([modules/baseline/README.md](../modules/baseline/README.md)): a non-root agent user, SSH key login, systemd user services, and lingering enabled (its root script does this; by hand, `sudo loginctl enable-linger <agent-login>`). Without lingering the gateway stops when you log out.
- Node and pnpm for the build, installed through your version manager.
- **Decided, in writing:** which chat channels the gateway may use, which model logins each agent may use, and whether any voice channel exists and who may speak in it. These are policy decisions. Write them down before you connect anything (see step 7).
- Accounts you control for every channel and model login. Do not hand the gateway a shared or someone else's account.

## Steps

### 1. Build from upstream main, in a checkout you can reset

Clone upstream, check out `main`, and build. Keep your own patches, if you have any, on a separate branch on top of upstream main. Do not run from a release tag (see papercuts).

```sh
git clone https://github.com/openclaw/openclaw.git <home>/src/openclaw
cd <home>/src/openclaw
git checkout main
pnpm install --frozen-lockfile
pnpm build
```

Link the CLI into a directory on the agent user's PATH with the npm global prefix. Put that directory on the PATH of the unit (step 3), because a non-interactive SSH or systemd environment does not get your interactive PATH.

**Done when:** `openclaw --version` prints the version and the upstream commit you built from.

### 2. Keep the secrets in an env file, not the config

Put every token in one file that only the agent user can read:

```sh
install -m 0600 /dev/null <home>/.openclaw/secrets/gateway.env
```

Write the variable names the config refers to (for example the gateway token and each channel's bot token) into that file. The OpenClaw config should refer to these by name, not contain the values.

Because of this, the bare CLI cannot read the token from the config. It fails with `gateway.auth.token is configured as a secret reference but is unavailable`. Run every CLI command that needs the token through a unit that loads the env file (step 4 and the reference snippet).

**Done when:** `openclaw health` returns healthy when run with the env file loaded, and fails with the secret-reference error when run bare. Both results are expected.

### 3. Run the gateway as a systemd user service

Create `openclaw-gateway.service` under `~/.config/systemd/user/` with an `EnvironmentFile=` pointing at the env file, a `WorkingDirectory=` for the agent user's home, and a PATH that includes the node shims and the npm global bin. Set a restart policy. Enable and start it:

```sh
systemctl --user daemon-reload
systemctl --user enable --now openclaw-gateway.service
```

Add a health watchdog: a timer that runs the health check and restarts the service if it fails. A gateway can be killed by a system-wide out-of-memory event during a heavy build, and the watchdog's restart is what brings it back.

**Done when:** `systemctl --user is-active openclaw-gateway.service` prints `active`, `systemctl --user show openclaw-gateway.service -p NRestarts` prints `NRestarts=0` after ten minutes, and the gateway's channels report connected in its log.

### 4. Run each agent turn in its own transient unit

Scripted agent turns should start as transient units that load the same env file, not as bare CLI calls:

```sh
systemd-run --user --unit=oc-job-<name> --collect \
  -p EnvironmentFile=<home>/.openclaw/secrets/gateway.env \
  -p WorkingDirectory=<home> \
  --setenv=PATH="<home>/.local/share/mise/shims:<home>/.npm-global/bin:$PATH" \
  -- <home>/.npm-global/bin/openclaw agent --agent <agent-id> \
     --session-key agent:<agent-id>:<name>-<date> \
     --message-file <brief.md> --timeout 1500
```

Give each job a fresh `--session-key` so it gets its own transcript. Leave delivery to chat channels off unless you have decided that this agent may send messages there. Wait on the unit with `systemctl --user is-active oc-job-<name>` and read its output with `journalctl --user -u oc-job-<name> -o cat`.

Treat the agent's report as a claim. Check the end state on disk before you relay it.

**Done when:** the unit exits and its final report matches the state you check on disk (for example, `git status` in the checkout the agent worked in).

### 5. Check the automations and channels

Read-only commands use the same env-file unit (add `--wait --pipe` in place of `--unit`):

- `openclaw cron list` shows every scheduled automation with its last status (`ok`, `skipped`, `error`, or `idle`). Use `openclaw cron runs <id>` for history.
- `openclaw logs --follow` tails the gateway's file log over RPC. The user journal is mostly chat-poll diagnostics; scheduled firings are not in it.
- `openclaw sessions list --agent <agent-id>` reads the local session store and needs no token.

Two ways to reach an agent, which behave differently:

- A **message** is a note the agent can read later. If the agent's main session is busy, an automation that offers it a message can skip the offer and record the run as `skipped`, with nothing else happening.
- A **turn** (`openclaw agent`) starts a session and waits for the reply. Use it when the job must happen now.

**Done when:** every scheduled job's last status is `ok` or `idle`, and you have checked each automation against the decisions you wrote down in Prerequisites.

### 6. Take a cold backup of code and state together, before every update

The state database migrates forward during an update, and a newer schema can refuse to open with an older build. So the only safe rollback is the code and the state, taken together, from the same moment.

With the gateway stopped:

```sh
STAMP=$(date +%Y%m%d)
COLD=<home>/.cache/oc-update-$STAMP/openclaw-cold
mkdir -p "$COLD/state"
chmod 0700 "$(dirname "$COLD")" "$COLD"
cp -a <home>/.openclaw/. "$COLD/state/"          # includes secrets: keep the mode
git -C <home>/src/openclaw rev-parse HEAD > "$(dirname "$COLD")/code-head.txt"
git -C <home>/src/openclaw branch --show-current >> "$(dirname "$COLD")/code-head.txt"
```

The copy includes the secrets file, so keep its directory at mode 0700. Compare the copy against the original with checksums (`find <home>/.openclaw -name '*.sqlite' -exec sha256sum {} +` in both places). Also keep a branch that points at the current commit (for example `patches-pre-<stamp>`), so the code can be restored by name.

**Done when:** the checksums match for every database file, and the code commit is recorded in `code-head.txt` and on a branch.

Keep this pair until the next update has succeeded and you have checked the gateway afterwards. Do not prune it in a disk cleanup. A disk cleanup that deletes every rollback copy leaves no way back for the next update.

### 7. Update to upstream main, never to a release tag

Target the upstream `main` commit you want, and check that your current build is an ancestor of it first:

```sh
git -C <home>/src/openclaw fetch origin
git -C <home>/src/openclaw merge-base --is-ancestor <current-commit> origin/main \
  && echo "ancestor: ok" || echo "NOT an ancestor: stop"
```

If the check fails, stop. Do not go on.

Then stop the gateway, take the cold backup (step 6), check out the target commit, rebuild (step 1), start the service, and run the update's repair step with `--no-restart` and then the CLI's doctor check. Run `openclaw --help` and each subcommand's `--help` for the exact names in your version. Expect the gateway to be down for the whole rebuild and repair, typically tens of minutes.

**Done when:** the service is active with `NRestarts=0`, the channels reconnect, a fresh agent turn (step 4) completes using the model and login you expect, and the scheduled jobs are back (step 5).

### 8. Keep a local patch only while upstream lacks the fix

For each local patch, run its own test against plain upstream first:

- If the test passes on plain upstream, upstream has the fix. Drop the patch.
- If the test fails on plain upstream, the bug is still there. Keep the patch and record the reason.
- If the test cannot even load on plain upstream, check first whether upstream removed the feature. Only drop the patch once you have confirmed that. A test that cannot load is not a pass.

**Done when:** each kept patch is recorded with the upstream commit where it was last checked and the test that proves it still applies.

## What bit us

- **A release tag was a downgrade.** An update to a release tag was attempted and rolled back. The tag sat on an older branch, well over a thousand commits behind the build the gateway was running. The state database's schema check refused the older build, and the cold copy restored the previous build with zero checksum differences. What to do instead: target upstream `main` and check the ancestor first (step 7).
- **Patches outlived their reason.** A spoken-confirmation patch stayed in the build until upstream removed the feature; its test then could not load on plain upstream, and it was dropped once that was confirmed. A nested-subagent patch was still needed because upstream's test for that case stayed red. What to do instead: run each patch's test against plain upstream on every update (step 8).
- **Upstream changed voice behaviour, not just the bug.** Upstream removed spoken confirmation and moved authenticated voice requests onto ordinary text permissions. Check voice behaviour after every update, not just that the service started.
- **The bare CLI fails on the token.** `gateway.auth.token is configured as a secret reference but is unavailable`. What to do instead: run every token-needing command through the env file (step 2 and 4).
- **Transient units lose the PATH.** A unit started over SSH inherits a PATH without the version-manager shims, and then fails with `env: 'node': No such file or directory`. What to do instead: name the shims and the npm global bin in the unit's `--setenv=PATH`.
- **The user journal does not show automation firings.** It is mostly chat-poll diagnostics. What to do instead: read `openclaw cron list` and `openclaw logs --follow`.
- **A busy session skipped automation offers.** A scheduled offer to a busy session is recorded as `skipped` and nothing happens. What to do instead: check `cron list` after you change any automation, and use a turn for work that must happen now.
- **A heavy build caused an out-of-memory kill of the gateway.** The kernel killed the gateway during a heavy build, and the watchdog restarted it. A memory cap on builds (their own scope with a limit) is a suggestion that has not been tested here.
- **Resident memory grew over a day on one build.** The gateway's RSS climbed by several GiB over about a day, mostly outside the JavaScript heap, while the main heap stayed flat. The next build stayed flat for a few hours, which is encouraging but did not prove the growth was fixed. What to do instead: track RSS over days (step below).
- **The memory warning is a tripwire, not a limit.** The gateway logs "memory pressure" at a level derived from the Node heap limit (a couple of GiB). It does not restart anything. Do not read it as a capacity problem by itself.
- **`openclaw memory forget` refuses while the gateway runs.** It needs exclusive offline state. Stop the service first, or leave the entry in place.
- **Cold backups get deleted in a cleanup.** A disk cleanup removed every rollback copy, and the next update had nothing to roll back to. What to do instead: keep the current pair until the next update is checked (step 6).
- **Which login an agent uses is a decision.** An agent's model login can move between accounts over time, and the choice is per agent, not for the whole gateway. Decide the account per agent and write it down.
- **Voice is a policy decision.** Limit voice to the people who have agreed to it, and check the terms of any organisation whose data the voice channel carries.

## Reference: a health check through the env file

```sh
systemd-run --user --pipe --wait --collect \
  -p EnvironmentFile=<home>/.openclaw/secrets/gateway.env \
  --setenv=PATH="<home>/.local/share/mise/shims:<home>/.npm-global/bin:$PATH" \
  -- <home>/.npm-global/bin/openclaw health
```

Use the same unit pattern for `openclaw cron list`, and drop `--pipe --wait` for a job that should run in the background.

## Keeping it healthy

- **Track RSS over days.** `systemctl --user show openclaw-gateway.service -p MemoryCurrent` once a day, logged somewhere. Compare the week before and after each update. A steady climb is worth reporting upstream with the numbers.
- **Read the changelog before each update**, and note which of your local patches it touches.
- **Re-check patches after each update** (step 8). Drop the ones upstream now covers.
- **Keep the cold pair until the next update is verified.** Then delete the older one.
- **Recheck the decisions you wrote in Prerequisites** after each update, because upstream changes defaults. Skill proposals and voice behaviour both changed between releases.

Last checked: 2026-10, Debian 13.
