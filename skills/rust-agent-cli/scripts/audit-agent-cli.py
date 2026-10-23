#!/usr/bin/env python3
"""Heuristic audit for Rust CLIs intended for AI agents.

Run from a repository root:
    python path/to/audit-agent-cli.py .

This is intentionally conservative. It flags patterns to inspect; it does not prove correctness.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import dataclass, asdict

@dataclass
class Check:
    id: str
    status: str
    message: str


def read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def any_file_contains(root: pathlib.Path, pattern: str) -> bool:
    rx = re.compile(pattern, re.MULTILINE)
    for path in list(root.glob("src/**/*.rs")) + list(root.glob("tests/**/*.rs")):
        if rx.search(read_text(path)):
            return True
    return False


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cargo = read_text(root / "Cargo.toml")
    src = "\n".join(read_text(p) for p in root.glob("src/**/*.rs"))
    tests = "\n".join(read_text(p) for p in root.glob("tests/**/*.rs"))

    checks: list[Check] = []

    def check(id_: str, ok: bool, message: str) -> None:
        checks.append(Check(id_, "pass" if ok else "review", message))

    check("clap-derive", "clap" in cargo and "derive" in cargo, "Cargo.toml should use clap with the derive feature.")
    check("serde-output", "serde" in cargo and "serde_json" in cargo, "Machine-readable CLIs should use serde + serde_json for output.")
    # Match a trait anywhere inside a derive list, e.g. #[derive(Debug, Parser)].
    def has_derive(trait_: str) -> bool:
        return re.search(rf"derive\([^)]*\b{trait_}\b", src) is not None

    check("typed-errors", "thiserror" in cargo or has_derive("Error"), "Prefer typed public errors with stable error codes.")
    check("parser-derive", has_derive("Parser"), "Use #[derive(Parser)] for the top-level CLI unless builder API is intentionally needed.")
    check("subcommands", has_derive("Subcommand"), "Multi-command tools should model subcommands explicitly.")
    check("value-enum", has_derive("ValueEnum"), "Closed sets should use ValueEnum instead of free-form strings.")
    check("try-parse", "try_parse" in src, "Use try_parse when parse errors need conversion into structured error envelopes.")
    check("no-color-default", "ColorChoice::Never" in src or "color = clap::ColorChoice::Never" in src, "Agent CLIs should disable color by default.")
    check("stdout-json", "serde_json::to_writer" in src or "serde_json::to_string" in src, "Stdout/stderr should be serialized JSON, not hand-built strings.")
    check("stderr-errors", "eprintln!" in src or "stderr" in src, "Diagnostics and errors should not pollute stdout.")
    check("schema-command", re.search(r"Schema|schema", src) is not None, "Consider a schema/contract subcommand for agent self-orientation.")
    check("dry-run", "dry_run" in src or "dry-run" in src, "State-changing tools should expose dry-run or plan/apply semantics.")
    check("parser-tests", "try_parse_from" in tests, "Add parser tests for Clap behavior.")
    check("black-box-tests", "assert_cmd" in cargo and "cargo_bin" in tests, "Add black-box CLI tests that run the binary (assert_cmd::Command::cargo_bin).")
    check("json-tests", "serde_json::from_slice" in tests or "serde_json::from_str" in tests, "Tests should parse stdout/stderr as JSON.")
    check("doctor-command", re.search(r"[Dd]octor", src) is not None, "Tools with dependencies, config, or durable state should expose a doctor command.")

    result = {
        "root": str(root),
        "summary": {
            "pass": sum(1 for c in checks if c.status == "pass"),
            "review": sum(1 for c in checks if c.status == "review"),
        },
        "checks": [asdict(c) for c in checks],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["review"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
