# Running several Claude and Codex subscriptions

This guide sets up more than one Claude (and optionally Codex) subscription across your machines, so heavy agent use does not stall on one account's limit. You get one native config directory per account, a usage poller that reads every account's 5-hour and weekly windows, a launcher that picks the account with the most room, automatic cooldowns when an account hits 100%, and a snapshot exchange between hosts that never moves a login.

## Do you need this?

**Skip it** if you have one subscription, or two and you are happy to switch by hand. One account needs only the usage poller (steps 1, 4 and 5), which is worth having alone: it shows how close you are to a limit before you hit it.

**Do it** if you hit limits regularly, run agent fleets overnight, or keep three or more accounts. Account ranking starts paying off at about three.

**Cost:** no new services. A poller run every 10 minutes per host (a few HTTPS calls per account), a JSON snapshot and an append-only history file (tens of MB per month with session detail), and one launcher function. The operational weight is credentials: each account needs two (a login and a setup token) and you must keep them straight.

## Prerequisites

- agent-estate's `usage` module ([modules/usage/README.md](../modules/usage/README.md)), or its equivalent: a script on a 10-minute timer (systemd user timer on Linux, launchd on the Mac). The module covers step 5's polling for the accounts listed under `[harnesses.*] accounts` and writes `$ESTATE_STATE/usage/snapshot.json` (`usage-show` prints it). It does not yet do the history file, identity check, cooldowns, peer exchange or launcher in steps 5 to 9; this guide gives the facts and policy those must follow.
- A Claude Code and/or Codex CLI on each host, and a human at a real terminal with a browser for each login. Logins cannot be completed headlessly, and authorization codes must not be pasted into a detached terminal.
- For the cross-host steps: SSH from each host to the other (aliases `mac` and `vps` below).

## Steps

### 1. Lay out one native config directory per account

Each account gets its own directory, owned by the vendor CLI, so the vendor refreshes its own tokens. Pick a root and a stable label per account (labels are used everywhere; do not rename them later).

```bash
mkdir -p ~/.claude-accounts/{a,b,c} ~/.codex-accounts/{a,b}   # your labels
chmod 700 ~/.claude-accounts ~/.codex-accounts
```

Claude Code reads its config directory from `CLAUDE_CONFIG_DIR`; Codex reads `CODEX_HOME`. Never share one directory between two accounts.

**Done when:** every directory exists, is mode 700 at the root, and no label appears twice.

### 2. Log in once per account (the "full login")

Run these with the human at the terminal, one account at a time. Before each, make sure the browser is signed in to the account you intend (see "What bit us", item 5).

```bash
CLAUDE_CONFIG_DIR=~/.claude-accounts/a claude          # then /login, complete the browser flow
CODEX_HOME=~/.codex-accounts/a codex login
```

Where the login lands: on Linux, `<config dir>/.credentials.json` (mode 0600). On macOS, Claude Code keeps it in the login Keychain in an item named `Claude Code-credentials-<suffix>`, where the suffix is the first 8 hex characters of the SHA-256 of the config directory path. Read these stores only through the poller; never print or copy them.

**Done when:** `CLAUDE_CONFIG_DIR=<dir> claude` starts without asking to log in, for every account, and (Linux) the credentials file exists with mode 0600 (`stat -c %a <dir>/.credentials.json`).

### 3. Mint a one-year setup token per Claude account

A setup token is a long-lived credential for running sessions. Launching sessions on it keeps the full login untouched, which is what lets the poller refresh that login safely (step 4). It cannot read usage: the usage endpoint requires the `user:profile` scope and a setup token lacks it. So every account needs both the login from step 2 and a token from this step.

```bash
CLAUDE_CONFIG_DIR=~/.claude-accounts/a claude setup-token
```

Rules, each of which costs time when missed:

1. Run it in the human's own interactive terminal and let them complete the browser authorization themselves. The CLI draws a TUI; do not relay authorization codes into a background PTY.
2. The printed token wraps across lines in a narrow terminal. Capture it privately; never paste raw output into a transcript, and do not assume it is a single line.
3. Before trusting a token, make one minimal inference request with it and compare the `anthropic-organization-id` response header with the organization you expect for that account. A token minted in the wrong browser session silently belongs to the wrong account.
4. Store it in `<config dir>/.setup-token.json`, mode 0600, with fields `token`, `email`, `org_id`, `expires_at` (Unix seconds, set conservatively from the issue time). Never commit, print or sync this file.

**Done when:** each account's token file exists at mode 0600, its organization check passed, and `expires_at` is in the future (put a reminder 30 days before the earliest one).

### 4. Launch sessions through one launcher

Every interactive or headless session goes through a launcher that selects an account, sets exactly that account's variables, and removes any inherited credential first. A bare `claude` bypasses the whole system and collides with whichever session holds the live refresh token.

```bash
# ~/.local/bin/claude-as <label> [claude args...]
set -euo pipefail
label=$1; shift
dir="$HOME/.claude-accounts/$label"
rec="$dir/.setup-token.json"
[ -d "$dir" ] || { echo "claude-as: no account $label" >&2; exit 2; }
unset CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
export CLAUDE_CONFIG_DIR="$dir"
if [ -f "$rec" ]; then
  [ "$(stat -c %a "$rec" 2>/dev/null || stat -f %Lp "$rec")" = 600 ] || { echo "claude-as: $rec must be mode 600" >&2; exit 2; }
  CLAUDE_CODE_OAUTH_TOKEN=$(python3 -c 'import json,sys,time
r=json.load(open(sys.argv[1]))
assert r["expires_at"] > time.time(), "setup token expired"
print(r["token"])' "$rec") || exit 2
  export CLAUDE_CODE_OAUTH_TOKEN
fi
exec claude "$@"
```

Fail closed: a malformed, expired or unsafe token record stops the launch; only a missing record falls back to the native login. Do not set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`: from Claude Code 2.1.266 it forces the permission mode to `default`, which silently disables a bypass-permissions launch.

For Codex, the equivalent is `CODEX_HOME=<dir> exec codex "$@"`. In this guide Codex sessions run on the Codex login itself.

**Done when:** `claude-as a -p "say ok"` answers, and `env -i HOME=$HOME PATH=$PATH CLAUDE_CODE_OAUTH_TOKEN=wrong claude-as a -p "say ok"` still answers (the inherited token was removed).

### 5. Run the usage poller on each host

The poller reads each account's windows and writes a snapshot. Facts it must follow:

- Claude: `GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer <login access token>` and header `anthropic-beta: oauth-2026-04-20`. The response lists limits: `session` (the 5-hour window), `weekly_all` (the 7-day window) and `weekly_scoped` (a per-model weekly, for example the most expensive model), each with a `percent` and a `resets_at`. Older responses carry only `five_hour` and `seven_day`; accept both. These endpoints are undocumented and can change: parse tolerantly and treat an unexpected shape as `unavailable`, never as zero.
- Codex: `GET https://chatgpt.com/backend-api/wham/usage` with the login's access token as Bearer and its account id in a `ChatGPT-Account-Id` header. Observe only. A Codex refresh token rotates and Codex itself is its only consumer, so the poller never refreshes it. An expired Codex token reads as `expired` until Codex next runs.
- Credentials: reading usage touches no credential. The only write is refreshing an expired (or within-an-hour-of-expiry) Claude access token, and only when no live session could be holding that login (see item 2 of "What bit us"). The refresh is an OAuth `refresh_token` grant at `https://platform.claude.com/v1/oauth/token`; use the client id Claude Code itself ships.
- Status per account, exactly one of: `ok`, `no_login`, `expired`, `stale_login` (expired, live session on it, no network call made), `no_scope` (403), `wrong_account` (step 7), `http_<code>`.
- Per snapshot row keep: label, status, limits, live session count, and `observed_at`. Add `is_current` and the broker/cooldown state if you have one.
- Append every poll to a history file (`claude-usage-history.jsonl`, one row per poll, all accounts). Append only; prune rows older than 90 days at most once a day. Rewriting the file every poll moves tens of MB every ten minutes once rows carry session detail.
- Keep each history line independently parseable so one truncated line never discards the rest.

Schedule it every 10 minutes (`usage-poll.timer` as a systemd user unit on Linux; a launchd agent with `StartInterval` 600 on the Mac).

**Done when:** `usage-show` (or reading the snapshot JSON) lists every account with `status: ok` and sane percentages, and the history file grows by one row per poll.

### 6. Exchange snapshots between hosts, never logins

Each host polls its own logins and writes its own snapshot. To give the other host a view of yours, stream the snapshot over SSH to a fixed receiving verb:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 vps 'usage-poll receive-peer' < ~/.local/state/agent-estate/usage/snapshot.json
```

The `receive-peer` verb is not part of the `usage` module's `usage-poll`; it is a few lines you add to your own poller or wrapper. The receiver stores it as `usage.peer.json`, rejects anything over a size cap (512 KiB covers dozens of sessions), and treats a snapshot older than 30 minutes as absent. A failed push is reported, never fatal; the peer is often off. If you gate SSH keys by command, allow exactly this one command and nothing else from the poller.

Why not copy logins: a refresh rotates the refresh token, so two hosts holding copies of one login log each other out. Each login has exactly one consumer. Install a login on a second host by logging in there (step 2), not by copying a file.

**Done when:** each host's `usage-show` (or your own poller's show command) lists the peer's session counts, and a login file exists on each host only because someone logged in on it.

### 7. Verify whose login it is

Before trusting a reading, confirm the login belongs to the account you filed it under. Call `GET https://api.anthropic.com/api/oauth/profile` (same headers) and compare `account.email` with the email recorded in that account's setup-token file. Run it at most hourly and after every refresh. On mismatch set status `wrong_account`, publish no numbers, and set no cooldown. Also read `organization.rate_limit_tier` from the same response about daily: the login stores the plan it was issued under, and upgrades never reach it.

**Done when:** every account reports `identity: ok`; a deliberately swapped test (copy of the email edited in a scratch record) reports `wrong_account` and no limits.

### 8. Rank accounts by expected load against headroom

When the launcher is run without a label, it picks the best account with this policy. All inputs come from the snapshot and the history file. The reference implementation is below; the numbers were calibrated on a couple of weeks of history, so keep them as defaults and recalibrate on your own data.

How the pieces work:

- **Headroom** is `100 - pct_7d`. **Hours to reset** is time to the weekly `resets_at`, floored at 0.25 h.
- **Sessions** on an account are local live sessions, plus fresh peer sessions (peer snapshot under 15 minutes old), plus launches in the last 90 seconds (so two launches in a row do not pick the same account).
- **Measured burn** is the account's %/h over the last hour from history: the newest row within 30 minutes of now, against the row 45 to 90 minutes earlier with the same weekly `resets_at`; cap it at 20 %/h; `None` when unavailable. Session counts alone miss subagents (they share the parent's pid) and headless runs that never register a session; measured burn catches them.
- **Expected load** (%/h of weekly) for the account after this launch: `0.31 * sessions + 0.42 * measured + prior` when burn is known, else `0.55 * sessions + prior`. The `prior` is the new session's own expected burn: 0.6 for a normal model, 1.0 for the most expensive model (about double per output token).
- **Survival:** forecast the weekly percent at reset as `pct + load * min(h, 6) + trailing_24h_avg_burn * max(h - 6, 0)` (the average excludes intervals when the account was capped; use `load` when there are under 6 hours of history). The account survives when the forecast is at most `100 - 5 * min(1, h/24)`.
- **Order, best first:** (1) accounts that survive, by spare rate descending, where spare is `headroom / hours_to_reset - load`, the %/h that would otherwise go unused at reset (use it or lose it); (2) accounts that would stall, by hours-to-cap descending, where hours-to-cap is `headroom / load`; (3) ties keep the current account, then label order. No switching margin: an exact tie stays put.
- **5-hour guard, ahead of everything:** an account at 85% or more of its 5-hour window ranks last unless that window resets within 20 minutes. If every account is hot, the one whose 5-hour window resets soonest wins. For the expensive model, use the higher of its weekly and the all-models weekly as the percent.

```python
def rank(accts, now, current, sessions, burn, prior=0.6):
    """accts: [{label, pct_5h, reset_5h, pct_7d, reset_7d, avg24}]; epoch seconds."""
    out = []
    for a in accts:
        head = max(0.0, 100 - a["pct_7d"])
        h = max(0.25, (a["reset_7d"] - now) / 3600)
        n, m = sessions.get(a["label"], 0), burn.get(a["label"])
        load = (0.31 * n + 0.42 * m + prior) if m is not None else (0.55 * n + prior)
        avg = a.get("avg24") if a.get("avg24") is not None else load
        forecast = a["pct_7d"] + load * min(h, 6) + avg * max(h - 6, 0)
        survives = forecast <= 100 - 5 * min(1, h / 24)
        hot = a["pct_5h"] >= 85 and a["reset_5h"] - now > 20 * 60
        spare, to_cap = head / h - load, head / load
        out.append((
            1 if hot else 0, a["reset_5h"] if hot else 0,
            0 if survives else 1, -spare if survives else -to_cap,
            0 if a["label"] == current else 1, a["label"],
        ))
    return [t[-1] for t in sorted(out)]
```

Print one plain line on every launch, stay or switch, so the choice is auditable: which account, its percent used, sessions, measured and expected burn, hours to cap, hours to reset, and why the runner-up lost. When usage data is missing or stale, say so and stay on the current account rather than guessing.

**Sticky picks.** When the human switches by hand (a `next` or `use` command in your launcher), honor that pick: skip ranking for that launch, and keep the pick for 15 minutes for every launch while the current-account pointer still names it. Otherwise autoselect overrides the human's choice one launch later. A launch that resumes a named session must stay on the account whose config directory holds that session (Claude finds a session only under the launching account's directory). A session id that no account holds keeps normal ranking, and the launcher says so. Provide an opt-out variable (for example `USAGE_AUTOSELECT=0`) that stays on the current account and still prints the line.

**Done when:** with a fixture of three accounts (one at 97% of 5h, one with a weekly reset in 2 days at 40%, one with a reset in 6 days at 10%), the function ranks the 97% account last, and a launch right after a manual `use` keeps that pick.

### 9. Set cooldowns from real limits

- The poller sets a cooldown only from a limit reading 100% or more, ending at that limit's own `resets_at` (the latest, if several are at 100%). The launcher's ranking must skip an account in cooldown.
- A cooldown on an account that now reads under 100% on every limit is stale, whether the poller or a human set it: clear it. Real data outranks a guessed deadline.
- Each host sets cooldowns only in its own launcher state; the peer applies its own on its next poll.
- Decide who may mark an account "limited" by hand. Reserve that for the human; agents never do.

**Done when:** a test snapshot with one account at 100% on its weekly produces a cooldown ending at that reset, and the next snapshot with the same account at 40% clears it.

## What bit us (papercuts)

1. **A setup token cannot read usage → give every account both credentials.** The usage endpoint needs `user:profile`, which setup tokens lack (403). Mint the token for sessions and keep the full login for the poller.
2. **Refreshing a login rotates its refresh token → only refresh when no live session holds that login.** A session holding the old token is logged out. With a live session on an account without a setup token and an expired login, report `stale_login` and make no network call; the usage endpoint answers an expired token with a misleading 429.
3. **An account with a session open all day kept an expired login for days (usage endpoint 429s) → launch on setup tokens.** Sessions on a setup token never hold the login, so the poller may refresh it even with sessions live. Only sessions on a token with a valid record qualify; check that the record is valid before relying on this.
4. **Never copy logins between hosts → push snapshots.** Copies fight over the rotating refresh token. Re-login on the second host instead. The same goes for Codex.
5. **A login filed under the wrong account.** If the browser is still signed in to a different account when you log in, the login authenticates as that other account. Sessions are fine (they run on setup tokens) but the poller publishes the other account's numbers under the wrong label, ranks launches on them, and can put the wrong account in a false 7-day cooldown. → Check the profile email against the enrolled email (step 7), and sign out of the browser or use a fresh profile before each login.
6. **Launches landed on an account at 97% of its 5-hour window.** The ranking looked only at weekly numbers. → The 5-hour guard.
7. **A first-draft ranking rule repeatedly predicted a cap within 6 hours and was wrong every time.** It assumed 1.0 %/h per session; measured, one session burns 0.5 to 0.6 %/h, and it ignored subagents and headless runs. → Measured burn plus session count (step 8).
8. **A first-draft survival check flagged most account-hours as "will stall" while only a small share of flags were followed by a real cap.** Projecting the one-hour load across days is wrong. → Current load for 6 hours, then the trailing 24-hour average (far fewer flags, and a higher share followed by a cap). Backtest any ranking change against your own history before shipping it; keep the history for that reason.
9. **The usage endpoint jitters `resets_at` by a second.** That split one cycle into two and made burn "unavailable". → Treat weekly resets within an hour of each other as the same cycle.
10. **Setting `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` silently disabled bypass-permissions launches** on Claude Code 2.1.266 and later. Leave it unset.
11. **A bare `claude` or `codex` collides with a live OAuth refresh.** Keep the launcher the only way sessions start, in panes, scripts and cron alike.
12. **A Codex login can go stale after an org change** and Codex logged "workspace routing discovery unauthorized (401)". → Log in again into the directory your launcher uses (`CODEX_HOME=<dir> codex login`) and also run plain `codex login`; one of the two was the stale one.
13. **A history file rewritten on every poll** moves on the order of 100 MB every ten minutes once rows carry session detail. → Append only; prune once a day.

## Reference snippets

Snapshot row (one account), the shape every consumer needs:

```json
{"label": "a", "status": "ok", "live_sessions": 2,
 "limits": [{"kind": "session", "percent": 31.0, "resets_at": 1790000000},
            {"kind": "weekly_all", "percent": 58.0, "resets_at": 1790400000}],
 "identity": "ok", "broker_state": "available", "is_current": false}
```

History row: `{"observed_at": <epoch>, "host": "vps", "accounts": {"a": {"pct_7d": 58.0, "pct_5h": 31.0, "resets_at": <epoch>, "live_sessions": 2}}}`.

Poller loop shape: read old snapshot; for each account: read login, refresh only if allowed, fetch usage, verify identity, parse limits; then apply cooldowns, write the snapshot atomically (temp file plus rename), append history, push to the peer.

## If you have two orgs (work and personal)

Skip this unless a work org and a personal org must never share credentials, tools or billing. The shape is two profiles, selected explicitly:

- Separate account directories per profile (`~/.claude-accounts/org-a-*`, `~/.claude-accounts/org-b-*`) and one key file per profile (`~/.config/profiles/org-a/keys.sh`, `.../org-b/keys.sh`, mode 0600) holding that profile's provider API keys.
- One contract file listing every managed key *name* (never values). This list is the safety property: the launcher scrubs every listed name from the inherited environment before anything else runs.
- A launcher takes the profile as its first decision. It clears inherited credentials (the managed names plus `CLAUDE_CODE_OAUTH_TOKEN`), sources exactly one profile's key file, and only then lets autoselect rank accounts within that profile. Ranking never crosses profiles.
- Fail closed: a command that needs `EXA_API_KEY` in the `org-b` profile, where the key is absent, refuses with a message naming the profile and the missing key. It never falls back to the other profile's key. Fixing it means adding the name to the contract and the key to that profile's file, by the human.
- Interactive shells hold no provider keys. Key-backed tools run through a wrapper (`with-profile org-a <cmd>`) that does the scrub-source-exec sequence.

```bash
# with-profile <profile> <cmd...>
p=$1; shift
for n in $(cat ~/.config/profiles/managed-names); do unset "$n"; done
set -a; . ~/.config/profiles/"$p"/keys.sh; set +a
exec "$@"
```

Check: `with-profile org-b env | grep -c ORG_A_ONLY_KEY` prints 0.

## Keeping it healthy

- Poller freshness: alert if the snapshot is older than 30 minutes or an account stays `stale_login`, `expired`, `no_scope` or `wrong_account` for more than a day.
- Setup tokens expire after a year; re-mint the oldest 30 days ahead, verifying the organization header each time.
- Re-run the backtest every few weeks against your history file; adjust the load coefficients if your usage pattern differs (evenings and fan-outs are typically the heaviest).
- Prune the history file to 90 days, once a day.
- After a home directory restore, treat every login as suspect: redo them one at a time and confirm `identity: ok`.

Last checked: 2026-10, Debian 12 and macOS.
