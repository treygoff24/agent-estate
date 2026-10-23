# Testing and release quality gate

## Test pyramid for agent CLIs

Use four layers:

1. Parser unit tests with `Cli::try_parse_from`.
2. Business logic unit tests that do not touch Clap or process globals.
3. Black-box CLI tests with `assert_cmd`, `assert_fs`, and JSON deserialization.
4. Snapshot/example tests with `trycmd` when there are many invocations or README examples.

## Parser tests

Cover:

- Empty invocation.
- `--help` and `--version`.
- Every subcommand.
- Required arguments.
- Conflicting arguments and groups.
- Default values.
- ValueEnum accepted and rejected values.
- Range validation.
- `-` stdin conventions.
- Global flags before and after subcommands.

Example:

```rust
#[test]
fn global_flags_work_after_subcommand() {
    let cli = Cli::try_parse_from(["tool", "run", "input.json", "--pretty"]).unwrap();
    assert!(cli.global.pretty);
}
```

## Black-box tests

Every black-box success test should parse stdout as JSON.

```rust
use assert_cmd::cargo::cargo_bin_cmd;
use serde_json::Value;

#[test]
fn run_outputs_json() {
    let mut cmd = cargo_bin_cmd!("tool");
    let output = cmd.args(["run", "tests/fixtures/input.json"]).output().unwrap();
    assert!(output.status.success());

    let stdout: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(stdout["ok"], true);
    assert!(stdout.get("data").is_some());
}
```

Every expected failure should parse stderr as JSON and assert the error code, retryability, and exit status.

```rust
#[test]
fn missing_input_is_structured_error() {
    let mut cmd = cargo_bin_cmd!("tool");
    let output = cmd.args(["run", "missing.json"]).output().unwrap();
    assert_eq!(output.status.code(), Some(66));

    let stderr: serde_json::Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(stderr["ok"], false);
    assert_eq!(stderr["error"]["code"], "input_not_found");
}
```

## trycmd setup

Minimal `tests/cli_tests.rs`:

```rust
#[test]
fn cli_tests() {
    trycmd::TestCases::new()
        .case("tests/cmd/*.toml")
        .case("README.md");
}
```

Use `TRYCMD=dump cargo test --test cli_tests` to generate snapshots, then copy the useful ones into `tests/cmd/`. Use `TRYCMD=overwrite cargo test --test cli_tests` only after deliberately accepting output changes.

Do not over-snapshot Clap help layout. Assert important parts are present instead of depending on every space in generated help text.

## Quality gate

Run this before claiming the CLI is done:

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-features
cargo build --release
```

Recommended additional checks for serious tools:

```bash
cargo deny check
cargo audit
cargo test --no-default-features
cargo doc --no-deps --all-features
```

## Release artifacts

For agent-only CLIs, release quality means automation can install and verify them without improvising:

- Provide binary names and supported target triples.
- Provide SHA256 checksums.
- Emit `tool --version` with crate version, commit hash when available, and build target if useful.
- Include a `doctor` command that checks external dependencies and prints JSON.
- Include a `schema` command so consuming agents can self-orient.
- Keep output schemas backward compatible within a major version.

## Regression guardrails

Add a fixture for every bug found by an agent. Agents will tend to hit similar edges repeatedly: missing paths, invalid JSON, too-large inputs, unknown enum values, duplicate ids, retry after partial failure, and permission problems.

When behavior changes, update the contract first, then implementation, then tests. Never silently change output shape without either preserving compatibility or bumping the schema version.
