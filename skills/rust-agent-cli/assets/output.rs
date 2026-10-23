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

#[derive(Debug, Serialize)]
pub struct Meta {
    pub schema_version: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
}

impl Default for Meta {
    fn default() -> Self {
        Self {
            schema_version: "1.0",
            correlation_id: None,
            warnings: vec![],
        }
    }
}

pub fn write_success<T: Serialize>(data: T, pretty: bool, meta: Meta) -> io::Result<()> {
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    let envelope = SuccessEnvelope {
        ok: true,
        data,
        meta,
    };
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
        meta: Meta::default(),
    };

    let stderr = io::stderr();
    let mut out = io::BufWriter::new(stderr.lock());
    let _ = serde_json::to_writer(&mut out, &envelope);
    let _ = writeln!(out);
    err.exit_code()
}
