# Clap patterns for excellent Rust agent CLIs

## Default to derive

Use Clap derive as the default API. It keeps argument declarations near their Rust types, makes command structs directly testable, and keeps parsing and reading in sync. Reach for builder APIs when you need runtime-generated command structure, argument occurrence ordering, source metadata, or a shape derive cannot express clearly.

Core imports:

```rust
use clap::{Args, CommandFactory, Parser, Subcommand, ValueEnum};
```

Core derive types:

- `Parser`: top-level CLI struct.
- `Subcommand`: command enum.
- `Args`: reusable groups of flags, usually flattened.
- `ValueEnum`: closed sets of valid values.
- `CommandFactory`: generate a `clap::Command` from derive definitions for help, schemas, completions, or man pages.

## Top-level command

```rust
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
    pub command: Commands,
}
```

Use `arg_required_else_help` and `subcommand_required` for multi-command tools. Agents recover faster from helpful usage errors than from silent no-ops.

## Reusable global flags

```rust
#[derive(Debug, Clone, Args)]
pub struct GlobalArgs {
    #[arg(long, global = true, default_value_t = false)]
    pub pretty: bool,

    #[arg(long, global = true, value_name = "ID")]
    pub correlation_id: Option<String>,

    #[arg(long, global = true, default_value_t = false)]
    pub dry_run: bool,

    #[arg(long, global = true, value_name = "MS", value_parser = clap::value_parser!(u64).range(1..))]
    pub timeout_ms: Option<u64>,
}
```

Make global flags `global = true` only when they truly apply to all subcommands.

## Validation at the parser boundary

Prefer parser-time validation for shape and domain constraints:

```rust
#[derive(Debug, Args)]
pub struct FetchArgs {
    /// Number of records to fetch.
    #[arg(long, default_value_t = 100, value_parser = clap::value_parser!(u16).range(1..=5000))]
    pub limit: u16,

    /// Output format.
    #[arg(long, value_enum, default_value_t = OutputFormat::Json)]
    pub format: OutputFormat,

    /// Path to input file, or '-' for stdin.
    #[arg(value_hint = clap::ValueHint::FilePath)]
    pub input: std::path::PathBuf,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
pub enum OutputFormat {
    Json,
    Jsonl,
}
```

For strings that must not be empty:

```rust
#[arg(long, value_parser = clap::builder::NonEmptyStringValueParser::new())]
pub name: String,
```

For mutually exclusive choices, use groups or conflicts:

```rust
#[derive(Debug, Args)]
#[group(required = true, multiple = false)]
pub struct TargetArgs {
    #[arg(long)]
    pub id: Option<String>,

    #[arg(long)]
    pub file: Option<std::path::PathBuf>,
}
```

Use `requires`, `conflicts_with`, `required_unless_present`, and `required_if_eq` when relationships are simple. If relationships become difficult to describe, redesign the command or use subcommands.

## Handling parse errors as JSON

For agent-only CLIs, use `try_parse()` so parse errors can become structured errors. Preserve help/version behavior.

```rust
use clap::error::ErrorKind;
use clap::Parser;

fn parse_cli() -> Cli {
    match Cli::try_parse() {
        Ok(cli) => cli,
        Err(err) => match err.kind() {
            ErrorKind::DisplayHelp | ErrorKind::DisplayVersion => err.exit(),
            _ => {
                let exit_code = err.exit_code();
                crate::output::write_error_and_exit(
                    exit_code,
                    "invalid_arguments",
                    err.to_string().trim(),
                    false,
                    Some("Run with --help or inspect `tool schema`."),
                );
            }
        },
    }
}
```

`err.exit()` is acceptable for help/version because those are intentionally human-readable. For all other parse errors, emit your error envelope.

## Builder interop

Derive definitions can still produce a mutable `Command`:

```rust
let mut cmd = Cli::command();
```

Use this for:

- Generating shell completions.
- Generating man pages.
- Snapshotting help output in tests.
- Adding runtime-only details when there is no clean derive representation.

## Shell completions

For installable CLIs, add a `completions` subcommand or an xtask that uses `clap_complete`:

```rust
#[derive(Debug, Subcommand)]
pub enum Commands {
    Completions { #[arg(value_enum)] shell: clap_complete::aot::Shell },
}

pub fn print_completions(shell: clap_complete::aot::Shell) {
    let mut cmd = Cli::command();
    let name = cmd.get_name().to_owned();
    clap_complete::aot::generate(shell, &mut cmd, name, &mut std::io::stdout());
}
```

For agent-only tools, completions are less important than schemas but still useful for local operators and debugging.

## Man pages and generated docs

Use `clap_mangen` from an xtask or build script when you ship binaries to humans or system package managers. Do not force every normal build to generate docs if it slows iteration. A simple xtask is often cleaner than `build.rs`.

## Parser tests

Test Clap behavior directly:

```rust
#[test]
fn rejects_zero_limit() {
    let err = Cli::try_parse_from(["tool", "run", "--limit", "0", "input.json"])
        .unwrap_err();
    assert_eq!(err.kind(), clap::error::ErrorKind::ValueValidation);
}

#[test]
fn parses_schema_default() {
    let cli = Cli::try_parse_from(["tool", "schema"]).unwrap();
    assert!(matches!(cli.command, Commands::Schema { .. }));
}
```

Parser tests should cover missing required args, conflicts, aliases, default values, enum values, `-` stdin handling, and any command relationship that an agent might get wrong.
