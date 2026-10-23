mod cli;
mod error;
mod output;

use clap::Parser;
use cli::{Cli, Commands};
use error::{AppError, AppResult};
use serde_json::json;
use std::path::Path;

fn main() {
    let code = match real_main() {
        Ok(()) => 0,
        Err(err) => output::emit_error(&err),
    };
    std::process::exit(code);
}

fn real_main() -> AppResult<()> {
    let cli = parse_cli_for_agents();
    let meta = output::Meta {
        correlation_id: cli.global.correlation_id.clone(),
        ..Default::default()
    };

    match cli.command {
        Commands::Schema { target } => {
            let data = json!({ "schema_version": "1.0", "target": format!("{target:?}") });
            output::write_success(data, cli.global.pretty, meta).map_err(|e| AppError::Internal {
                message: e.to_string(),
            })
        }
        Commands::Run(args) => {
            // Validate input before any side effect — a missing file is a
            // structured InputNotFound (exit 66), not a panic.
            let contents = read_input(&args.input)?;
            let data = json!({
                "input": args.input,
                "bytes": contents.len(),
                "dry_run": cli.global.dry_run,
            });
            output::write_success(data, cli.global.pretty, meta).map_err(|e| AppError::Internal {
                message: e.to_string(),
            })
        }
    }
}

/// Read a file path, or '-' for piped stdin. Fails before any side effect.
fn read_input(path: &Path) -> AppResult<String> {
    use std::io::{IsTerminal, Read};
    if path == Path::new("-") {
        if std::io::stdin().is_terminal() {
            return Err(AppError::invalid_arguments(
                "input '-' requires piped stdin; stdin is a terminal",
            ));
        }
        let mut buf = String::new();
        std::io::stdin()
            .lock()
            .read_to_string(&mut buf)
            .map_err(|e| AppError::InvalidData {
                message: e.to_string(),
            })?;
        Ok(buf)
    } else {
        std::fs::read_to_string(path).map_err(|_| AppError::InputNotFound {
            path: path.display().to_string(),
        })
    }
}

fn parse_cli_for_agents() -> Cli {
    match Cli::try_parse() {
        Ok(cli) => cli,
        Err(err) => match err.kind() {
            clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion => {
                err.exit()
            }
            _ => {
                let app_err = AppError::invalid_arguments(err.to_string());
                let code = output::emit_error(&app_err);
                std::process::exit(code);
            }
        },
    }
}
