---
name: rust-agent-cli
description: Build, redesign, audit, or refactor Rust command-line tools with Clap for AI-agent-only usage. Use when creating Rust CLIs, Clap parsers, subcommands, machine-readable JSON/JSONL interfaces, deterministic automation tools, agent-facing schemas, structured error/exit-code contracts, doctor/health commands, durable state and idempotency, headless auth, CLI tests, completions, distribution/installers, or release-quality Rust binaries that other agents will drive.
license: MIT
compatibility: Claude Code and Codex CLI Agent Skills; Rust 2021/2024; Clap 4.x derive API.
---

# Rust agent CLI skill

Use this skill when the task involves creating, improving, or reviewing a Rust CLI that will be used by AI agents or other automated systems. Treat the CLI as a protocol surface, not a human UI. Your job is to design a crisp machine contract, implement it with modern Clap patterns, and prove it with tests.

The deep design rationale — why agent CLIs are built the way they are, the error-rewriting craft, the anti-patterns, and the excellence checklist — lives in `references/design-principles.md`. Read it before designing a new surface or reviewing an existing one. The rest of this file is the build procedure.

## Non-negotiable product posture

Agent-only CLIs must be deterministic, non-interactive, structured, easy to inspect, and hard to misuse.

Build every CLI around these defaults:

- No prompts, no menus, no spinners, no hidden TTY dependency. If input is missing, fail with a structured error.
- Stdout is for command results only. Stderr is for diagnostics, logs, and errors.
- Prefer JSON for single-result commands and JSONL for streams or progress events.
- Disable color by default. Let users opt in only when human-facing output is explicitly requested.
- Every successful output shape and error shape should be serializable Rust structs, not hand-built strings.
- Every destructive or state-changing operation must support a dry run or plan mode. Do not make irreversible behavior the path of least resistance.
- Do not infer risky defaults from ambient machine state unless the command also exposes the resolved values in output.
- Include stable exit codes, stable error codes, and stable schemas.
- Keep command names boring, explicit, and kebab-case.

The governing idea (see `references/design-principles.md`): **design every surface so the first command an agent instinctively tries either just works or is redirected with a precise, actionable hint.** The least-surprise-on-failure path matters more than the happy path — failures are where agents lose the most time.

## Workflow

1. **Write the CLI contract first.**

   Before coding, define the commands, flags, inputs, outputs, error codes, exit codes, idempotency behavior, and test cases. For a new CLI, include a `schema` (or `describe`) subcommand and, if it has dependencies/config/state, a `doctor` subcommand — unless the user rejects them. See `references/agent-cli-contract.md` for the contract template.

2. **Use Clap derive by default.**

   Start with `#[derive(Parser)]`, `#[derive(Subcommand)]`, `#[derive(Args)]`, and `#[derive(ValueEnum)]`. Use Clap builder APIs only when derive cannot express the behavior clearly or when runtime-generated command structure is required.

3. **Split parser, execution, output, and errors.**

   Prefer this layout:

   ```text
   src/main.rs       # parse, dispatch, top-level exit handling only
   src/cli.rs        # Clap structs/enums and parser-only validation
   src/commands/     # command implementations
   src/output.rs     # JSON/JSONL writers and envelope types
   src/error.rs      # typed public error contract
   src/lib.rs        # reusable business logic
   tests/cli.rs      # black-box CLI tests
   tests/cmd/        # trycmd/snapshot cases when useful
   ```

4. **Implement parse-boundary validation.**

   Use `ValueEnum`, typed fields, `PathBuf`, `NonEmptyStringValueParser`, `value_parser!(T).range(...)`, `requires`, `conflicts_with`, `ArgGroup`, `default_value_t`, and `value_hint` so invalid invocations fail before business logic runs. Coerce sloppy-but-unambiguous inputs to a canonical form in the `value_parser`; reject genuinely ambiguous input with options rather than guessing.

5. **Emit structured results.**

   Use `serde::Serialize` response structs and `serde_json::to_writer` or `to_writer_pretty`. For long-running work, emit JSONL events to stderr with event `type`, `timestamp`, `correlation_id`, and command-specific data. Keep stdout parseable even when verbose logging is enabled. Bound output by default (`--limit`, `--max-output-bytes`, pagination cursors); spill large payloads to `--output FILE` and return a handle.

6. **Make errors useful to agents.**

   Convert errors to an envelope with:

   ```json
   {
     "ok": false,
     "error": {
       "code": "invalid_argument",
       "message": "short readable message",
       "details": {},
       "retryable": false,
       "suggested_fix": "specific next command or flag"
     }
   }
   ```

   Error messages must name the bad input, why it failed, and how to fix it — ideally the exact command to run instead, with a "did you mean" for typos. Never dump a Rust panic or debug representation as the primary error. The full error-rewriting craft is in `references/design-principles.md`.

7. **Add the agent-orientation surfaces.**

   - `schema` / `describe` so a consuming agent can self-orient without docs.
   - `doctor` (if the tool has dependencies, config, or durable state) to diagnose and optionally `--fix` its own broken state — see `references/doctor-mode.md`.
   - If the tool keeps state across runs, make `apply --idempotency-key` crash-safe — see `references/state-and-persistence.md`.
   - If the tool authenticates to a remote service, do it headlessly and never block on a prompt — see `references/headless-auth.md`.

8. **Test as a command, not only as a library.**

   Add parser unit tests with `Cli::try_parse_from`, integration tests with `assert_cmd`, and schema/JSON parse tests that deserialize every stdout and stderr envelope. For many example invocations, use `trycmd` snapshots. See `references/testing-release.md`.

9. **Run the quality gate.**

   Run or add equivalents of:

   ```bash
   cargo fmt --check
   cargo clippy --all-targets --all-features -- -D warnings
   cargo test --all-features
   cargo build --release
   ```

   When security or distribution matters, also consider `cargo deny`, `cargo audit`, generated completions, generated man pages, and checksums for binaries. For shipping the binary and making agents discover it, see `references/distribution.md`.

## Clap conventions to use

Use this pattern for top-level parsing (the full set of patterns — validation, builder interop, completions, man pages, parser tests — is in `references/clap-patterns.md`):

```rust
use clap::{Args, Parser, Subcommand, ValueEnum};
use std::path::PathBuf;

#[derive(Debug, Parser)]
#[command(
    name = env!("CARGO_PKG_NAME"),
    version,
    about,
    long_about = None,
    arg_required_else_help = true,
    subcommand_required = true,
    color = clap::ColorChoice::Never,
    rename_all = "kebab-case"
)]
pub struct Cli {
    #[command(flatten)]
    pub global: GlobalArgs,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Clone, Args)]
pub struct GlobalArgs {
    /// Emit pretty-printed JSON.
    #[arg(long, global = true, default_value_t = false)]
    pub pretty: bool,

    /// Machine correlation id echoed in structured output and logs.
    #[arg(long, global = true, value_name = "ID")]
    pub correlation_id: Option<String>,

    /// Do not modify state; emit the planned operations.
    #[arg(long, global = true, default_value_t = false)]
    pub dry_run: bool,

    /// Maximum wall-clock time for the command.
    #[arg(long, global = true, value_name = "MS", value_parser = clap::value_parser!(u64).range(1..))]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    /// Print the machine-readable contract for this CLI.
    Schema {
        #[arg(value_enum, default_value_t = SchemaTarget::All)]
        target: SchemaTarget,
    },

    /// Run the primary operation.
    Run(RunArgs),
}
```

Prefer `try_parse()` in `main` so Clap parse errors can be converted into your public error envelope when appropriate. Preserve normal help/version behavior when the user explicitly asks for help or version.

## Output and exit-code policy

Use these defaults unless the repository already has a stronger convention:

| Condition | Exit code | Channel | Shape |
| --- | ---: | --- | --- |
| Success | 0 | stdout | success JSON or JSONL result |
| No matches / valid empty result | 0 | stdout | success JSON with empty list/count |
| Usage or argument error | 2 | stderr | error JSON |
| Validation or bad input data | 65 | stderr | error JSON |
| Missing file or unavailable input | 66 | stderr | error JSON |
| Config problem | 78 | stderr | error JSON |
| Temporary external dependency failure | 75 | stderr | retryable error JSON |
| Permission denied / not authenticated | 77 | stderr | error JSON |
| Internal bug / invariant violation | 70 | stderr | error JSON plus optional debug log |

Never rely on English-only stderr for agent control flow. English can be helpful, but the `code`, `retryable`, and `details` fields are the contract. Auth failures map onto this table (`not_authenticated`/`reauth_required` → 77, rate-limited → 75) and carry the finer distinction in the error `code` field.

One documented exception: a `doctor` command is a diagnostic, so it uses a small linter-style exit dictionary (0 healthy / 1 findings / 2 partial-fix / 3 fix-failed / 4 refused-unsafe) instead of "exit 0 = success." Publish it in `doctor capabilities`. See `references/doctor-mode.md`.

## Agent-facing command design

Use verbs an agent can reason about, grouped by resource noun then verb (`run start`, `run list`, `run logs`):

```text
tool schema [all|input|output|error]   # print the contract for self-orientation
tool doctor [--fix] [--json]           # diagnose / repair the tool's own state
tool inspect <target> --format json    # read state without changing it
tool plan <target> --output plan.json  # compute a proposed mutation, no side effect
tool apply --plan plan.json --idempotency-key <key>   # enact a plan, crash-safe
tool status <operation-id> --format json
```

For a single-purpose tool, a `run` subcommand is fine. For multi-step or destructive workflows, explicit `plan` and `apply` commands beat a pile of flags — the agent gets a dry-run it can inspect before committing blast radius. Avoid ambiguous verbs (`do`, `process`, `manage`, `sync`) unless the domain makes them unambiguous. Keep each subcommand group scannable in one `--help`.

## When to load references

Load only the files you need:

- `references/design-principles.md` — the durable agent-CLI design wisdom: the one rule, the design principles, command granularity, input forgiveness, the error-rewriting craft, anti-patterns, the excellence checklist, verification-first. **Start here when designing or reviewing.**
- `references/agent-cli-contract.md` — output schemas, command contracts, the contract-first spec template, and agent-only UX rules.
- `references/clap-patterns.md` — Clap derive, builder interop, parse-boundary validation, parse-error-to-JSON, completions, man pages, parser tests.
- `references/implementation-patterns.md` — starter Rust modules (main/error/output/stdin), dependency choices, the schema subcommand.
- `references/testing-release.md` — the test pyramid, parser/black-box/trycmd tests, the quality gate, release artifacts.
- `references/doctor-mode.md` — the `doctor`/`health`/`--fix` subcommand: output shape, safety/reversibility rules, exit codes, Rust sketch.
- `references/state-and-persistence.md` — durable state for stateful CLIs: when to use SQLite vs. JSONL vs. nothing, atomic writes, crash-safe idempotency keys, recovery.
- `references/headless-auth.md` — non-interactive auth to remote services: the credential ladder, headless detection, secret handling, the `not_authenticated` error.
- `references/distribution.md` — shipping the binary and agent self-discovery: release artifacts, the curl|bash installer, idempotent agent auto-configuration.
- `references/sources.md` — upstream docs to re-check when making major changes.
- `assets/` — copyable, verified starter templates (`cli.rs`, `main.rs`, `output.rs`, `error.rs`, `tests-cli.rs`, `Cargo.toml.snippet`, `trycmd.toml`). The skeleton compiles and passes `fmt`/`clippy -D warnings`/`test` as-is.
- `scripts/audit-agent-cli.py` — a quick heuristic audit of an existing repository (`python audit-agent-cli.py <repo>`).

## Review checklist

A Rust agent CLI is not done until all of these are true:

- `--help` explains every command and argument with examples or precise value names; a `schema`/`describe` surface returns the full machine contract.
- The default output is parseable by an agent with no flags beyond the command's real inputs; stdout is data only, stderr is diagnostics only.
- Every output type and error type has a Rust struct and a test that deserializes representative output.
- Invalid input fails at the parse boundary, before side effects.
- No command waits for interactive input unless explicitly designed as a REPL; nothing prompts in a non-TTY.
- Destructive operations have `--dry-run`, `plan`/`apply`, or another explicit safety story, and errors name the safe alternative.
- Errors are structured, stable, and actionable — they name the bad input, the reason, and the exact fix (with "did you mean" for typos).
- Output is bounded by default; large payloads spill to `--output FILE`.
- If the tool has dependencies/config/state, it has a `doctor`; if it keeps state, `apply` is crash-safe and idempotent; if it authenticates, it does so headlessly.
- Exit codes and error codes are documented and tested; empty results are exit 0, not exit 1 or empty stdout.
- Parser behavior is tested, including conflicts, required groups, default values, and bad values.
- The project passes fmt, clippy with warnings denied, tests, and a release build.
