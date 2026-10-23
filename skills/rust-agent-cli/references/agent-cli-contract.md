# Agent-only CLI contract

Design Rust CLIs for agents as small local protocols. The command line is only the transport. The real product is a stable contract made from commands, schemas, exit codes, and side-effect rules.

## Contract-first spec

Before implementation, write a short contract with these fields:

```markdown
# CLI contract

Binary: <name>
Audience: AI agents only
Primary job: <one sentence>

## Commands
- `tool schema [target]`
- `tool doctor`
- `tool plan ...`
- `tool apply ...`

## Global flags
- `--pretty`: pretty JSON
- `--correlation-id <ID>`: echoed in all output
- `--dry-run`: no state changes
- `--timeout-ms <MS>`: command budget

## Output
Success stdout schema: <Rust type / JSON schema>
Error stderr schema: <Rust type / JSON schema>
Progress stderr schema: <Rust type / JSON schema, JSONL when streaming>

## Exit codes
0 success
2 CLI usage error
65 invalid data
66 unavailable input
70 internal software error
75 temporary external failure
77 permission denied
78 config error

## Side effects
What can change? What is idempotent? How can an agent preview, retry, or recover?
```

## Output envelopes

Single-result commands should write exactly one JSON object to stdout on success.

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "schema_version": "1.0",
    "correlation_id": "optional-id",
    "warnings": []
  }
}
```

Streaming commands should write JSONL records, one valid JSON object per line. Use a `type` discriminator so agents can process records incrementally.

```jsonl
{"type":"begin","correlation_id":"abc","command":"run"}
{"type":"item","data":{"path":"src/main.rs"}}
{"type":"summary","data":{"count":1}}
```

Errors should write exactly one JSON object to stderr, even for internal errors. Human text can appear in `message`, but agents should key off `code` and `retryable`.

```json
{
  "ok": false,
  "error": {
    "code": "input_not_found",
    "message": "input file does not exist: missing.json",
    "details": {"path": "missing.json"},
    "retryable": false,
    "suggested_fix": "Pass an existing path or '-' to read stdin."
  },
  "meta": {
    "schema_version": "1.0",
    "correlation_id": "abc"
  }
}
```

## Global flags for agent CLIs

Default global flags worth including unless they conflict with the product:

```text
--pretty                  Pretty-print JSON output.
--correlation-id <ID>     Echoed in output and logs.
--dry-run                 Validate and report intended changes without applying them.
--timeout-ms <MS>         Abort after a bounded wall-clock budget.
--max-output-bytes <N>    Avoid accidentally huge outputs.
--idempotency-key <KEY>   Required or encouraged for external state mutations.
```

Do not add `--interactive` unless the tool truly supports a REPL. Agents need commands that terminate.

## Command taxonomy

Use verbs agents can reason about:

- `schema`: print command/input/output/error schemas.
- `doctor`: validate environment and dependencies.
- `inspect`: read state without changing it.
- `plan`: compute a proposed mutation without applying it.
- `apply`: execute a previously emitted plan.
- `run`: execute a simple primary operation.
- `status`: inspect an operation or job by id.
- `export`: write a durable artifact.

Avoid ambiguous verbs like `do`, `process`, `manage`, or `sync` unless the domain makes them unambiguous.

## Side-effect discipline

State-changing commands must say what they changed. Prefer this success payload:

```json
{
  "ok": true,
  "data": {
    "operation_id": "op_123",
    "changed": true,
    "changes": [
      {"type": "created_file", "path": "out/result.json"}
    ]
  },
  "meta": {"schema_version": "1.0"}
}
```

For destructive actions, require at least one explicit guard such as a plan file, `--yes`, `--force`, `--idempotency-key`, or an exact resource id. Do not make broad mutation possible from a default command with inferred targets.

## Stdin and files

Use `-` to mean stdin only when stdin is not a terminal. If stdin is a terminal, fail with a usage error and a suggested fix. Prefer file inputs for large payloads, because agents can create and inspect files reliably.

For outputs, support both stdout and `--output <FILE>` when outputs may be large. When `--output` is used, stdout should contain metadata pointing to the file, not duplicate huge content.

## Determinism rules

- Sort maps and file lists before output when ordering is not semantically meaningful.
- Include clocks, random ids, and absolute paths only when necessary.
- Provide flags for seed, now, cwd, or config path if behavior depends on them.
- Do not silently read config from surprising locations. If config is auto-discovered, report the resolved path in `meta`.
