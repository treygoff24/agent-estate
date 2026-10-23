# Doctor / health / fix subcommand

Agent CLIs run with no human nearby. A `doctor` command is a contract with a future caller — usually an agent, one shot to make the tool work again — that diagnoses the tool's own broken state and, optionally, repairs it. Add one to any CLI that has installable dependencies, on-disk config, or durable state.

## One rule

**Detect, then fix — never fix, then detect.** Detectors are pure: read-only, return a finding, never write. Fixers run only when `--fix` is passed, and every mutation goes through one chokepoint that backs up first. If `doctor --fix` and `doctor undo <run-id>` are not a true inverse pair, the doctor is broken regardless of what else it does.

Check-vs-fix separation is structural, not cosmetic. A read-only `doctor` is always safe to run blind, the agent can parse findings and decide whether to authorize repair, and repair is reversible so the agent can roll back its own bad call.

## Command surface

```text
tool doctor                  # read-only diagnose
tool doctor --fix            # repair, with backups
tool doctor --fix --dry-run  # print the plan, mutate nothing
tool doctor undo <run-id>    # restore a prior --fix run, byte-for-byte
tool doctor capabilities     # version, contract, detector+fixer list, exit codes, writable paths
```

Invariants: bare `doctor` never mutates; no flag silently implies `--fix`; no flag turns off backups; `--dry-run` is only meaningful with `--fix`. Like the rest of the CLI, default output is JSON on stdout; progress/color go to stderr and auto-disable on non-TTY.

## Output shape

Top-level `status` is `healthy | degraded | broken`. Each check names its own fix — citing `file:line` / `key=…` / row — and states whether a fixer exists.

```json
{
  "schema_version": "1.0",
  "status": "degraded",
  "summary": { "total": 4, "ok": 2, "warn": 1, "error": 1, "fixable": 1 },
  "checks": [
    {
      "id": "config.schema_version",
      "category": "config",
      "severity": "error",
      "ok": false,
      "detail": "config at ~/.tool/config.toml is schema v1; tool expects v3",
      "location": "~/.tool/config.toml",
      "fix_available": true,
      "remediation": { "summary": "migrate config v1 -> v3", "command": "tool doctor --fix", "reversible": true }
    },
    {
      "id": "deps.ripgrep",
      "category": "deps",
      "severity": "warn",
      "ok": false,
      "detail": "ripgrep not found on PATH; falls back to slow grep",
      "location": null,
      "fix_available": false,
      "remediation": { "summary": "install ripgrep", "command": "brew install ripgrep", "reversible": false }
    }
  ],
  "run_id": null
}
```

Per-check contract: `id` (stable, dotted, machine-keyable), `category`, `severity` (`info|warn|error`), `ok`, `detail` (specific — names the offending thing, never generic prose), `location` (nullable), `fix_available`, `remediation` (nullable: `summary`, a `command` the agent can run verbatim, `reversible`). On a `--fix` run, populate top-level `run_id` and add an `actions[]` block (`path`, `op`, `before_hash`, `after_hash`) so the agent can later call `doctor undo <run-id>`.

## Check categories

Inventory real failure modes (`git log --grep='fix\|panic\|corrupt\|race'`, the issue tracker, any "how to unstick X" playbook). Each becomes a `(detector, fixer, fixture)` triple.

- **env** — required tooling on PATH, env vars set, runtime/toolchain version present.
- **deps** — external binaries the tool shells out to (recommended-but-optional → `warn`, not `error`).
- **config** — file exists, parses, required keys present, values in range.
- **permissions** — files/dirs readable/writable, not world-writable, lockfile ownership.
- **state integrity** — caches/indexes/DBs not corrupt, hashes match, no orphan `.tmp` or stale lock.
- **version skew** — config `schema_version` vs. tool expectation, on-disk state format vs. binary.

## Safety rules for `--fix`

Every fixer mutation must satisfy all of these — any miss is a rework target, not "ship and watch":

- **Single mutation chokepoint.** Every write goes through one `mutate(run, path, op)` that backs up, records before/after hashes, and appends to `actions.jsonl`. Add a test that fails if any other code path writes under `--fix`.
- **Backup before every mutation,** byte-identical, perms + mtime preserved.
- **Reversible.** `undo <run-id>` replays `actions.jsonl` in reverse, restores from backups, verifies the restored hash matches the recorded `before_hash`, fails closed if a backup is missing.
- **Idempotent.** `--fix` twice → second run reports "no actions taken," exit 0.
- **Atomic + crash-safe.** Write-tmp → fsync → rename, always. Killed mid-fix → next run completes or aborts cleanly; no torn writes, no orphan `.tmp`.
- **Offline by default.** Network probes are opt-in behind `--online`.
- **Scoped writes.** Only write inside paths declared in `doctor capabilities`; anything outside refuses (exit 4).
- **Never destructive-by-default.** No `rm -rf`, `git reset --hard`, `DROP TABLE`. To "remove" a file, move it to quarantine via a recorded rename; real deletion is a separate, explicitly-gated `gc` command.

Run artifacts live under a gitignored `<repo>/.doctor/runs/<iso8601>__<short-id>/` (`report.json`, `actions.jsonl`, `backups/`). Derive the run-id (`sha256(state + iso-seconds)[..6]`) rather than randomizing, so runs are reproducible.

## Exit codes (doctor-local, documented exception)

`doctor` is a diagnostic command, so it uses a small linter-style dictionary instead of the general exit-code table in `references/agent-cli-contract.md`. This is the one intentional exception to "exit 0 = success"; publish it in `doctor capabilities` so agents can branch on it.

| Code | Meaning |
| ---: | --- |
| 0 | healthy (or `--fix` fully succeeded / nothing to do) |
| 1 | findings present (read-only diagnose found problems) |
| 2 | `--fix` partial — some fixers succeeded, some failed |
| 3 | `--fix` failed and rolled back |
| 4 | refused-unsafe (out-of-scope write, ambiguous state) |
| 5 | lock held |
| 64 | usage error |

Status mapping: `0 → healthy`; `1 → degraded` (warns only) or `broken` (any `error` severity); `2/3/4/5 → broken`. A `panic`/`unwrap` on a user path is a bug — convert it to a refused-unsafe finding (exit 4) with a precise reason.

## Rust sketch

```rust
use serde::Serialize;
use std::path::Path;

#[derive(clap::Args, Debug)]
pub struct DoctorArgs {
    /// Apply fixes (backed up + reversible). Omit for read-only diagnose.
    #[arg(long)]
    pub fix: bool,
    /// With --fix: print the plan, mutate nothing.
    #[arg(long, requires = "fix")]
    pub dry_run: bool,
    /// Allow network probes (off by default).
    #[arg(long)]
    pub online: bool,
    #[command(subcommand)]
    pub action: Option<DoctorAction>,
}

#[derive(clap::Subcommand, Debug)]
pub enum DoctorAction {
    /// Restore a prior --fix run byte-for-byte.
    Undo { run_id: String },
    /// Emit version, contract, detectors/fixers, exit codes, writable paths.
    Capabilities,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status { Healthy, Degraded, Broken }

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity { Info, Warn, Error }

#[derive(Serialize)]
pub struct Remediation { pub summary: String, pub command: String, pub reversible: bool }

#[derive(Serialize)]
pub struct Check {
    pub id: &'static str,
    pub category: &'static str,
    pub severity: Severity,
    pub ok: bool,
    pub detail: String,
    pub location: Option<String>,
    pub fix_available: bool,
    pub remediation: Option<Remediation>,
}

#[derive(Serialize)]
pub struct DoctorReport {
    pub schema_version: &'static str,
    pub status: Status,
    pub checks: Vec<Check>,
    pub run_id: Option<String>,
}

/// Pure detector: reads only, returns a finding, NEVER writes.
type Detector = fn(&Ctx) -> Check;

/// THE chokepoint. Every destructive op funnels here. Nothing else writes.
fn mutate(run: &Run, path: &Path, op: Op) -> Result<(), DoctorError> {
    run.assert_in_scope(path)?;        // else refused -> exit 4
    copy_verbatim(path, &run.backup_path(path))?;  // perms + mtime preserved
    let before = sha256(path)?;
    apply_atomic(path, &op)?;          // write .tmp, fsync, rename
    let after = sha256(path)?;
    run.append_action(Action { path: path.into(), op, before, after, ts: now() })?;
    Ok(())
}
```

Wiring: run all detectors → build `checks` → derive `Status` and exit code → serialize `DoctorReport` to stdout. If `--fix` and not `--dry-run`, route each fixable finding through `mutate`. See `references/state-and-persistence.md` for the atomic-write and crash-recovery primitives a stateful doctor reuses.

## Anti-patterns

- A fixer that bypasses `mutate()` "for speed" — breaks backups/undo. Everything routes through the chokepoint.
- Printing "fixed" without appending to `actions.jsonl` — undo can't find the action. If `mutate` didn't run, the fix didn't happen.
- `panic`/`unwrap` on a user path — convert to a refused-unsafe finding (exit 4) with a precise reason.
- Color or progress on stdout — breaks `| jq`. Diagnostics go to stderr.
- Deleting a file in `--fix` "to clean up" — quarantine via recorded rename; real deletion is the separate gated `gc`.
- Generic findings ("config looks wrong") — each must cite `file:line`/`key=`/row and name the exact flag or command that resolves it.
- A detector that writes (creates a missing dir "while it's here") — detectors are pure; the runtime owns the `--fix` decision.
