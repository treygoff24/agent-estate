use thiserror::Error;

pub type AppResult<T> = Result<T, AppError>;

// Starter taxonomy: the full set of public error kinds with their stable codes
// and exit codes. The minimal skeleton only constructs some of them — keep the
// rest as you add commands that need them. `allow(dead_code)` is here only so the
// scaffold passes `clippy -D warnings`; drop it once every variant is in use.
#[allow(dead_code)]
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
        Self::InvalidArguments {
            message: message.into(),
        }
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
            Self::Temporary { .. } => {
                Some("Retry with the same idempotency key after the dependency recovers.")
            }
            Self::Internal { .. } => {
                Some("Rerun with verbose logs and report the command, input, and version.")
            }
        }
    }
}
