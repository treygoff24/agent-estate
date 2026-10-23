# usage

Every few minutes, reads how much of each subscription's rate-limit windows you have used and writes one JSON snapshot agents and humans can read.

- **Claude**: 5-hour session, weekly, and model-scoped weekly windows (`/api/oauth/usage`).
- **Codex / ChatGPT**: the plan's primary (5h) and secondary (weekly) windows (`/backend-api/wham/usage`).

One account per harness is the default and the tested path. To track more, list accounts in `estate.toml`:

```toml
[harnesses.claude]
accounts = ["default", "spare"]   # "default" = ~/.claude (or $CLAUDE_CONFIG_DIR); "spare" = ~/.claude-spare
```

Codex works the same way (`~/.codex` or `$CODEX_HOME`, then `~/.codex-<name>`). Harnesses other than `claude` and `codex` are ignored.

## Use it

```
estate install usage     # writes the timer (systemd user timer / launchd agent) and polls once
usage-show               # short table; `usage-show --json` for the raw snapshot (adds "stale")
```

The snapshot is `$ESTATE_STATE/usage/snapshot.json` (mode 0600, replaced atomically, so a reader never sees half a file). Each account has `status` (`ok`, `no_login`, `expired`, `http_NNN`, `network_error`, ...) and `limits[]` of `{kind, model, percent, resets_at}` (`kind`: `session`, `weekly_all`, `weekly_scoped`, `window_<N>h`). If a poll fails but an earlier one succeeded, the old numbers are kept with `"stale": true` and `limits_observed_at`. The whole snapshot is stale when older than 3 intervals.

## Settings (`[modules.usage]`)

| Key | Default | Meaning |
|---|---|---|
| `interval_seconds` | `600` | poll period, 60 or more |
| `refresh_login` | `false` | opt in to refreshing an *expired* Claude login; see below |

## Credentials: what is read, what is ever written

- **Claude**: `~/.claude/.credentials.json` (Linux), else on a Mac the login-keychain item `Claude Code-credentials` (read with `security`). Only the access token is sent, and only to the usage endpoint.
- **Codex**: `~/.codex/auth.json`. **Read only.** An expired Codex login is reported as `expired`; run `codex` once and it refreshes itself.
- **Refresh.** A Claude access token lasts hours and Claude Code refreshes it whenever you use it. By default the poller never writes to your login: an expired one is reported `expired` until you next use Claude Code on that machine. On a machine where you rarely run Claude Code (a VPS that mostly runs other agents), set `refresh_login = true` and the poller refreshes an expired login itself. Refresh tokens *rotate*, so the new pair is written back to `.credentials.json` (atomic rename, same mode, other keys kept), after re-reading the file to confirm Claude Code has not refreshed meanwhile (if it has, the poller uses that login and writes nothing). A **keychain login is never written**: it is reported `expired` until Claude Code refreshes it. With the default `refresh_login = false` nothing is ever written. The one risk: a Claude Code process that read the old pair a moment before our write holds a rotated-out refresh token; it recovers by re-reading the file.
- Redirects are refused so a token never follows one to another host.

## Done when

`estate doctor` shows the `usage` row ok: timer loaded, snapshot present and younger than 3 intervals, every account `ok`. It warns on a stale snapshot or any account that errored (for example `no_login` when a configured harness is not signed in on this machine) and fails when the timer is not loaded or no snapshot exists.

## Tests

`tests/test_usage.py` runs against a fake HTTP server and fake credential files in a temporary HOME. Environment hooks for that: `ESTATE_USAGE_CLAUDE_API`, `ESTATE_USAGE_CLAUDE_TOKEN_URL`, `ESTATE_USAGE_CODEX_URL`.

On both platforms the poll wrapper (`$ESTATE_STATE/usage/poll.sh`) execs an absolute Python 3.11+ chosen at install and recorded in `$ESTATE_STATE/usage/python3` (install fails with a clear message if there is none), and the Mac agent sets its own `PATH`: launchd's default `PATH` would run Apple's old Python. `estate doctor` fails if that interpreter goes away.
