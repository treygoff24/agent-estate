# Rust and Rust CLI playbook

## Defaults

- Start with `cargo test` and existing workspace conventions.
- Use `cargo nextest` when present or when suite runtime/isolation warrants adoption.
- Use `cargo llvm-cov` when coverage is requested and the repo supports it.
- Use specialized tools only where they match the risk: property tests, Miri, fuzzing, snapshots.

## Rust CLI tests

Prefer process-level CLI tests for command behavior:

- `assert_cmd` for binaries, exit codes, stdout/stderr.
- `trycmd` for many CLI cases and reviewed golden outputs.
- `tempfile` for config/filesystem isolation.
- `predicates` where already used for expressive assertions.

High-value CLI scenarios:

- Exit code and stderr on invalid input.
- Config precedence: CLI arg > env > config > default.
- Filesystem side effects in temp dirs.
- Golden output for help text or stable user-facing output, if snapshots stay readable.
- Idempotent reruns and dry-run behavior.

## Library/system tests

- Use unit tests for pure deterministic logic.
- Use integration tests for public crate behavior and feature combinations.
- Use doc tests for public API examples that should compile and remain true.
- Use `rstest` for table/fixture-heavy cases when it improves failure clarity.
- Use `mockall` sparingly at trait seams for external collaborators.

## Robustness tools

- Use `proptest` or `quickcheck` for parsers, serializers, normalization, and invariants.
- Use Miri for unsafe code and undefined-behavior risk.
- Use `cargo-fuzz` for parsers, decoders, file formats, network input, and adversarial user input.
- Do not add fuzz/Miri gates casually to every project; justify them by risk and runtime.

## Snapshot policy

Use `insta` or `trycmd` snapshots only for intentionally stable, reviewable artifacts: CLI help, formatted diagnostics, serialized output, pretty-printers. Reject giant snapshots nobody will review.
