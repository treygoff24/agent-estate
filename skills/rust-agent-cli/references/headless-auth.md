# Headless auth for an agent CLI

Only relevant when the CLI authenticates to a remote service. The priority order is the inverse of a human CLI: non-interactive credentials are the contract; browser/device-code flows are a fallback or out of scope. The cardinal rule — **an agent CLI must never block on an interactive browser, device prompt, or keyring dialog by default.** If no non-interactive credential is available, fail with a structured error that names exactly which env var / file / command supplies one.

## The auth priority ladder

Resolve credentials in this order, stopping at the first hit. None of these may prompt, block, or open a browser.

```text
1. Explicit flag/arg      --token / --api-key / --auth-file      (per-invocation override)
2. Environment variable   TOOL_TOKEN / TOOL_API_KEY              (the CI/agent default)
3. Credential file        $XDG_CONFIG_HOME/tool/credentials.json (0600)  / OS keyring
4. (fallback ONLY)        device-code / browser-PKCE — gated behind a real TTY AND an
                          explicit opt-in flag; never the default path
```

If 1–3 miss, do not escalate to an interactive flow by default — emit a `not_authenticated` error (below) and exit non-zero. Interactive login is reached only when a TTY is present **and** the caller explicitly asked (`tool login` or `--interactive`).

```rust
fn resolve_token(args: &AuthArgs) -> Result<Secret, AuthError> {
    if let Some(t) = &args.token { return Ok(Secret::new(t.clone())); }        // 1
    if let Ok(t) = std::env::var("TOOL_TOKEN") { return Ok(Secret::new(t)); }  // 2
    if let Some(c) = load_credentials()? { return Ok(c.access_token); }        // 3
    Err(AuthError::NotAuthenticated)                                           // -> structured error
}
```

Prefer flag > env (a caller can override a polluted environment per-call); some tools prefer env > flag for CI. Either is defensible — pick one, document it, keep it stable.

## Headless detection

Default posture is non-interactive. Detect a *real* TTY before considering any interactive flow. Use `std::io::IsTerminal` (Rust ≥ 1.70) — the old `atty` crate is unmaintained.

```rust
use std::io::{IsTerminal, stdin, stdout};

/// True only when a human could actually answer a prompt.
fn is_interactive() -> bool {
    stdin().is_terminal()
        && stdout().is_terminal()
        && std::env::var_os("CI").is_none()
        && std::env::var_os("TOOL_NONINTERACTIVE").is_none()
}
```

Also treat `SSH_CLIENT`/`SSH_TTY`, `CI`, `CONTAINER`, and `/.dockerenv` as headless signals. Gate every interactive flow on `is_interactive()`, and honor an explicit `--no-interactive` as an absolute override even when a TTY exists.

## Credential storage

Try most secure first, degrade silently — never prompt. **Keyring is optional acceleration, the file is the reliable substrate:** on Linux a keyring read can pop a GUI unlock dialog, which hangs a background agent on an invisible modal. A read that would prompt must fail fast, not block.

Enforce perms on every write, not just create:

```rust
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::io::Write;
use std::path::Path;

fn write_credentials(path: &Path, json: &[u8]) -> Result<(), AuthError> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
        std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut f = std::fs::OpenOptions::new()
        .write(true).create(true).truncate(true)
        .mode(0o600)                 // owner rw only, atomically at create
        .open(path)?;
    f.write_all(json)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?; // fix a pre-existing file
    Ok(())
}
```

Paths: `$XDG_CONFIG_HOME/tool/` then `$HOME/.config/tool/`. Keep `config.toml` (non-secret) beside `credentials.json` (secret, 0600). Wrap secrets in a newtype that can't leak to logs or JSON:

```rust
pub struct Secret(String);
impl Secret { pub fn new(s: String) -> Self { Self(s) } pub fn expose(&self) -> &str { &self.0 } }
impl std::fmt::Debug for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { f.write_str("Secret(***)") }
}
// Do NOT derive Serialize. Never place a Secret in a #[derive(Serialize)] envelope field.
```

## Token lifecycle (non-interactive)

Load → check expiry → refresh → persist, all silently.

- API keys / static tokens never expire — nothing to do.
- For expiring tokens, refresh ~30s before expiry. Refresh is transparent (no prompt, no stdout chatter); persist the new token back to the same store at 0600.
- **Refresh failure is terminal for this run.** Do not retry a one-time code or a rejected refresh (the server replay-rejects it). Surface a structured `reauth_required` / `permission_denied` error and exit non-zero so the agent can act.
- **Concurrent processes** sharing a credential file can race a refresh: serialize writes with an advisory file lock around the read-modify-write, and treat a 401 on a just-refreshed token as "another process rotated it" → reload from disk, retry once.

## Structured "not authenticated" error

A typed error mapped into the CLI's JSON envelope with a stable `code`, a masked `message`, and a machine-actionable `suggested_fix` that names the exact env var / file / command. Map the auth failures onto the spine's exit-code table — `not_authenticated`/`reauth_required` → `77` (permission denied), `rate_limited` → `75` (retryable) — and carry the finer distinction in the error `code` field so agents can branch without parsing prose.

```json
{
  "ok": false,
  "error": {
    "code": "not_authenticated",
    "message": "No credentials found. This CLI runs non-interactively and will not open a browser.",
    "details": { "checked": ["--token", "$TOOL_TOKEN", "~/.config/tool/credentials.json"] },
    "retryable": false,
    "suggested_fix": "Set TOOL_TOKEN=<token>, or write ~/.config/tool/credentials.json (chmod 600), or run `tool login` from an interactive terminal."
  },
  "meta": { "schema_version": "1.0" }
}
```

## Security invariants

- **Tokens never in `argv`** — a `--token` value leaks into `ps`, shell history, and the parent agent's transcript. Prefer env/file; if a flag exists, document the leak and support `--token-stdin` / `@file`.
- **Tokens never in stdout JSON** — the envelope is the agent's payload; a token there is exfiltrated downstream. Use the `Secret` newtype; add a test asserting the envelope never contains the token.
- **Secrets never in error `message`/`details`** — structured errors get logged verbatim by callers. Mask values (`tok_ab…f2a1`); `details` carry *names* (env var, path), never values.
- **Secrets never in correlation/trace logs** — redact the `Authorization` header and any token in the log layer.
- **Cred files 0600, dir 0700** — enforced on every write.
- **Logout clears local creds even if the server revoke call fails** — best-effort revoke, then always delete the local store, so a network-flaky agent isn't left "logged in" locally.
- **`User-Agent: tool/<ver> (<os>/<arch>)`** on every request; auth requests get 0 retries.
