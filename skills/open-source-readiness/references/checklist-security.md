# Checklist: security from a stranger's threat model

Source: the fixes a security review of a desktop app drove (this list comes from what was found and fixed, so it is a floor, not a review's full coverage) plus CI and supply-chain practice from primary sources. Each fix shipped with a test proved red by mutation; keep that rule.

## Whose threat model

Review as four strangers, because a personal project never had them:
- **The user** who installs your binary and trusts it with their data and their keys.
- **The contributor** whose pull request runs in your CI.
- **The network and the host** that serves your updates and the APIs you call.
- **The fork** that rebuilds your project with different identities.

## Credentials and network

- Key-test and API calls go through an HTTP session that refuses redirects. A key test on the shared session followed 301/302/307/308 to another host and the key went with it. Test with a loopback server that answers each status and redirects to a different host name; the server must never see the key.
- Any URL returned by a remote API (an upload URL, a file URI) is untrusted input. Require https, the expected host, no userinfo, no port except the default, before sending audio or credentials. Validate returned resource names against a strict pattern (a name like `files/../..` turned into a path). Delete or ignore a resource whose URI fails validation.
- Loopback allowlists accept IP literals only (`127.0.0.1`, `::1`), not `localhost`, which resolvers and hosts files can repoint. Update the user-facing error text and the docs together; users with `http://localhost` configs will see an error, so say so in the release notes.
- Secrets in the OS keychain only; never display a saved key; no key as a command-line argument (visible in the process list).

## Local data

- Create user-data directories 0700 and files 0600: databases, their WAL and SHM sidecars (pre-create the main file with the mode so sidecars inherit it), recordings, config. On open, tighten items you own that are group or world accessible. Note the gap for files written by older builds.
- Developer tools that touch the user's data (preview, render and import commands) check before writing: refuse symlinks (dangling or not), hard-linked files, and anything but a plain file or folder, and check every directory in between. State the check-then-write race you did not close.
- Import commands that read another app's data: dry-run opens read-only and never creates files; each input path must resolve, after symlinks, inside the expected folder; reject timestamps and durations outside sane ranges so conversion cannot trap.

## Actions on the user's behalf

- Automation that types or pastes into other apps: hold when the focused element is a secure/password field or the system's secure input is on, and re-check the target (process id, subrole, secure input) immediately before the action to close the time-of-check gap. Fail closed to the clipboard with a visible remark. Unreadable focus alone never holds. Document the cost: a global secure-input setting held every action while on.
- Undocumented command-line flags in the shipped binary (importers, key stores, transcribe helpers) are attack and confusion surface: document them under developer tools or drop them from release builds.
- Launch-time side effects on other components (disabling or booting launch jobs, polling config files every second) are findings in their own right; gate them on the feature being configured.

## Updates and release process

- The updater verifies that an update was signed by your code-signing requirement (exact designated requirement, compiled; a requirement that fails to compile refuses), not only by the update key. Tests: test runner refused, ad-hoc binary refused, platform binary refused.
- The release script verifies the signature of the archive against the public key shipped in the app (not against the private key it is handed), requires the built app's key to equal the plist's, and requires the build number to exceed the highest in the live feed. A 404 on the feed means first release; any other fetch failure stops a real release.
- Signing keys stay off the machine that hosts the downloads. Pass keys by keychain or stdin, never as arguments.
- Keep bundled update frameworks current; they have shipped security fixes.

## Logging

- The public log prints fixed codes (an outcome's log code), never error descriptions or script error text. Detail goes to the private log.
- See `checklist-privacy-secrets.md` for user-derived values.

## CI and supply chain (if a workflow ships)

- Top-level `permissions: contents: read`; widen per job. No secrets in contributor-run workflows.
- No `pull_request_target` or `workflow_run` with untrusted checkout. No untrusted `${{ github.event.* }}` in `run:`.
- Pin third-party actions to a full commit SHA; keep them fresh with Dependabot.
- No self-hosted runners on a public repo.
- Settings: require approval for all external contributors' workflow runs; read-only default token.
- Commit the lockfile (`Package.resolved`, `Cargo.lock`, and so on). Enable Dependabot alerts and updates (alerts are off by default).
- Never run the release script in CI unless the credentials design was reviewed for it.

## Reporting

- `SECURITY.md` with a private channel (GitHub private vulnerability reporting or an email), a response target (OpenSSF: initial response within 14 days), and the supported versions.
