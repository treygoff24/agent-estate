# Implementation patterns

## Recommended dependencies

Start minimal. Add only what the contract needs.

```toml
[dependencies]
clap = { version = "4", features = ["derive", "env", "wrap_help"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
thiserror = "2"
anyhow = "1"

[dev-dependencies]
assert_cmd = "2"
assert_fs = "1"
predicates = "3"
trycmd = "1"
```

Useful optional dependencies:

```toml
# JSON Schema for `schema` subcommands
schemars = { version = "1", features = ["derive"] }

# Better signal handling or cancellation when needed
ctrlc = "3"

# Runtime completions
clap_complete = "4"

# Man page generation, usually in xtask or build-dependencies
clap_mangen = "0.3"
```

For public libraries, prefer `thiserror` for typed errors. For binaries, `anyhow::Context` is fine internally, but convert to public error codes before emitting.

## main.rs shape

```rust
mod cli;
mod error;
mod output;
mod commands;

use clap::Parser;
use cli::{Cli, Commands};
use error::{AppError, AppResult};

fn main() {
    let code = match real_main() {
        Ok(()) => exitcode::OK,
        Err(err) => output::emit_error(&err),
    };
    std::process::exit(code);
}

fn real_main() -> AppResult<()> {
    let cli = parse_cli_for_agents();

    match cli.command {
        Commands::Schema { target } => commands::schema::run(&cli.global, target),
        Commands::Run(args) => commands::run::run(&cli.global, args),
    }
}

fn parse_cli_for_agents() -> Cli {
    match Cli::try_parse() {
        Ok(cli) => cli,
        Err(err) => match err.kind() {
            clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion => err.exit(),
            _ => {
                let app_err = AppError::invalid_arguments(err.to_string());
                let code = output::emit_error(&app_err);
                std::process::exit(code);
            }
        },
    }
}
```

If you do not want an extra `exitcode` dependency, define constants yourself.

## Error type

```rust
use serde::Serialize;
use thiserror::Error;

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("invalid arguments: {message}")]
    InvalidArguments { message: String },

    #[error("input not found: {path}")]
    InputNotFound { path: String },

    #[error("invalid input data: {message}")]
    InvalidData { message: String },

    #[error("temporary external failure: {message}")]
    Temporary { message: String },

    #[error("internal error: {message}")]
    Internal { message: String },
}

impl AppError {
    pub fn invalid_arguments(message: impl Into<String>) -> Self {
        Self::InvalidArguments { message: message.into() }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::InvalidArguments { .. } => "invalid_arguments",
            Self::InputNotFound { .. } => "input_not_found",
            Self::InvalidData { .. } => "invalid_data",
            Self::Temporary { .. } => "temporary_failure",
            Self::Internal { .. } => "internal_error",
        }
    }

    pub fn exit_code(&self) -> i32 {
        match self {
            Self::InvalidArguments { .. } => 2,
            Self::InvalidData { .. } => 65,
            Self::InputNotFound { .. } => 66,
            Self::Temporary { .. } => 75,
            Self::Internal { .. } => 70,
        }
    }

    pub fn retryable(&self) -> bool {
        matches!(self, Self::Temporary { .. })
    }

    pub fn suggested_fix(&self) -> Option<&'static str> {
        match self {
            Self::InvalidArguments { .. } => Some("Run with --help or inspect `schema`."),
            Self::InputNotFound { .. } => Some("Pass an existing file path or '-' for stdin."),
            Self::InvalidData { .. } => Some("Validate the input against `schema input`."),
            Self::Temporary { .. } => Some("Retry with the same idempotency key after the dependency recovers."),
            Self::Internal { .. } => Some("Rerun with verbose logs and report the command, input, and version."),
        }
    }
}
```

## Output module

```rust
use crate::error::AppError;
use serde::Serialize;
use std::io::{self, Write};

#[derive(Debug, Serialize)]
pub struct SuccessEnvelope<T: Serialize> {
    pub ok: bool,
    pub data: T,
    pub meta: Meta,
}

#[derive(Debug, Serialize)]
pub struct ErrorEnvelope<'a> {
    pub ok: bool,
    pub error: ErrorBody<'a>,
    pub meta: Meta,
}

#[derive(Debug, Serialize)]
pub struct ErrorBody<'a> {
    pub code: &'a str,
    pub message: String,
    pub details: serde_json::Value,
    pub retryable: bool,
    pub suggested_fix: Option<&'a str>,
}

#[derive(Debug, Default, Serialize)]
pub struct Meta {
    pub schema_version: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
}

pub fn write_success<T: Serialize>(data: T, pretty: bool, meta: Meta) -> io::Result<()> {
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    let envelope = SuccessEnvelope { ok: true, data, meta };
    if pretty {
        serde_json::to_writer_pretty(&mut out, &envelope)?;
    } else {
        serde_json::to_writer(&mut out, &envelope)?;
    }
    writeln!(out)?;
    Ok(())
}

pub fn emit_error(err: &AppError) -> i32 {
    let envelope = ErrorEnvelope {
        ok: false,
        error: ErrorBody {
            code: err.code(),
            message: err.to_string(),
            details: serde_json::json!({}),
            retryable: err.retryable(),
            suggested_fix: err.suggested_fix(),
        },
        meta: Meta { schema_version: "1.0", ..Default::default() },
    };

    let stderr = io::stderr();
    let mut out = io::BufWriter::new(stderr.lock());
    let _ = serde_json::to_writer(&mut out, &envelope);
    let _ = writeln!(out);
    err.exit_code()
}
```

## Reading stdin safely

```rust
use std::io::{self, IsTerminal, Read};
use std::path::Path;

pub fn read_input(path: &Path) -> crate::error::AppResult<String> {
    if path == Path::new("-") {
        if io::stdin().is_terminal() {
            return Err(crate::error::AppError::invalid_arguments(
                "input '-' requires piped stdin; stdin is a terminal",
            ));
        }
        let mut buf = String::new();
        io::stdin().lock().read_to_string(&mut buf)
            .map_err(|e| crate::error::AppError::InvalidData { message: e.to_string() })?;
        Ok(buf)
    } else {
        std::fs::read_to_string(path).map_err(|_| crate::error::AppError::InputNotFound {
            path: path.display().to_string(),
        })
    }
}
```

## Schema subcommand

If using `schemars`, derive `JsonSchema` on public request/response/error structs and print schemas from a `schema` subcommand.

```rust
#[cfg(feature = "schema")]
pub fn print_schema<T: schemars::JsonSchema + ?Sized>() -> serde_json::Value {
    serde_json::to_value(schemars::schema_for!(T)).expect("schema serializes")
}
```

Agents love schemas. They reduce bad calls, simplify repairs, and let one CLI teach another agent how to use it.
