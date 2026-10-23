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
    pub command: Commands,
}

#[derive(Debug, Clone, Args)]
pub struct GlobalArgs {
    /// Pretty-print JSON output.
    #[arg(long, global = true, default_value_t = false)]
    pub pretty: bool,

    /// Machine correlation id echoed in structured output and logs.
    #[arg(long, global = true, value_name = "ID")]
    pub correlation_id: Option<String>,

    /// Validate and report intended changes without modifying state.
    #[arg(long, global = true, default_value_t = false)]
    pub dry_run: bool,

    /// Maximum wall-clock time for the command.
    #[arg(long, global = true, value_name = "MS", value_parser = clap::value_parser!(u64).range(1..))]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Subcommand)]
pub enum Commands {
    /// Print the machine-readable contract for this CLI.
    Schema {
        #[arg(value_enum, default_value_t = SchemaTarget::All)]
        target: SchemaTarget,
    },

    /// Run the primary operation.
    Run(RunArgs),
}

#[derive(Debug, Clone, Copy, ValueEnum)]
pub enum SchemaTarget {
    All,
    Input,
    Output,
    Error,
}

#[derive(Debug, Args)]
pub struct RunArgs {
    /// Input file, or '-' for stdin.
    #[arg(value_name = "INPUT", value_hint = clap::ValueHint::FilePath)]
    pub input: PathBuf,
}
