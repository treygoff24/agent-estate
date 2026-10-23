// Black-box CLI tests: run the built binary, parse stdout/stderr as JSON, assert
// on exit code + error code. Self-contained — no on-disk fixtures required.
use assert_cmd::Command;
use assert_fs::prelude::*;
use serde_json::Value;

#[test]
fn run_outputs_json() {
    let file = assert_fs::NamedTempFile::new("input.json").unwrap();
    file.write_str("{}").unwrap();

    let mut cmd = Command::cargo_bin(env!("CARGO_PKG_NAME")).unwrap();
    let output = cmd.arg("run").arg(file.path()).output().unwrap();
    assert!(output.status.success());

    let stdout: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(stdout["ok"], true);
    assert!(stdout.get("data").is_some());
}

#[test]
fn missing_input_is_structured_error() {
    let mut cmd = Command::cargo_bin(env!("CARGO_PKG_NAME")).unwrap();
    let output = cmd
        .args(["run", "definitely-missing.json"])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(66));

    let stderr: Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(stderr["ok"], false);
    assert_eq!(stderr["error"]["code"], "input_not_found");
}
