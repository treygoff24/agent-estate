# Durable state for a stateful agent CLI

Most agent CLIs need no local state — read inputs, do work, emit one envelope, exit. Reach for this only when the CLI must *remember across invocations*: a crash-safe `apply --idempotency-key`, a `status` command that reads back recent operations, or an audit log. It supplies the durability layer that the spine's plan/apply + idempotency contract depends on.

## When to reach for state (default: none)

A CLI that is a pure function of its argv + stdin + the world it mutates needs no store.

| Need | Use |
| --- | --- |
| Pure transform; idempotency comes from the remote target itself (PUT-like) | **Nothing.** Re-running is safe; don't invent a store. |
| Append-only operation/audit log; `status` reads recent ops; git-diffable | **Flat JSONL** (one op per line, atomic rotate). |
| `apply --idempotency-key` must dedupe across crashes; concurrent invocations; queryable history | **SQLite** (ACID `INSERT OR IGNORE` + transactions are the point). |
| Both: SQLite authoritative, JSONL the inspection mirror | **SQLite source of truth + JSONL export.** |

Rule of thumb: if you reach for `flock` + manual JSON read-modify-write to get atomic dedupe, you've reinvented SQLite badly — switch. If you only ever append and never need a transactional check-then-act, SQLite is overkill — use JSONL.

## Source of truth + JSONL sync

Pick **one** authoritative store; every sync is one-way, lock-serialized, atomic. The natural choice for an agent CLI is **SQLite-first**: writes commit to SQLite under WAL with ACID guarantees, and a JSONL export is produced on a quiet-period / on-exit cadence for git history and human review. `status` reads straight from SQLite. Each store carries a version marker (monotonic counter in the DB, header record or sidecar `.meta.json` in JSONL); on startup compare them — DB newer → re-export; JSONL newer (hand-edited or git-restored) → rebuild the DB. Brief divergence is expected; fast eventual consistency is the contract, not realtime mirroring.

## Atomic JSONL write (temp + fsync + rename)

Never leave a partial/truncated file. Temp in the *same dir* (rename is only atomic within one filesystem) → flush → fsync file → rename → fsync dir on Unix.

```rust
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;

pub fn write_jsonl_atomic(path: &Path, records: &[impl serde::Serialize]) -> Result<(), StateError> {
    let dir = path.parent().ok_or(StateError::BadPath)?;
    let tmp = tempfile::NamedTempFile::new_in(dir)?; // same-dir temp keeps the rename on one fs
    {
        let mut w = BufWriter::new(tmp.as_file());
        for r in records {
            serde_json::to_writer(&mut w, r)?;
            w.write_all(b"\n")?;
        }
        w.flush()?;
        tmp.as_file().sync_all()?; // durable bytes before the rename
    }
    tmp.persist(path)?;            // atomic replace
    #[cfg(unix)]
    File::open(dir)?.sync_all()?;  // durably record the rename itself
    Ok(())
}
```

Keep the old file on any failure — never partial-write in place. Append-only logs can `lock + append + flush`; full exports use temp+rename. (`tempfile` is a justified non-stdlib dependency for a stateful CLI; a stateless one stays stdlib-only.)

## Minimal-correct SQLite (rusqlite)

The smallest set that is actually crash-safe for a single-binary CLI, set on every connection open:

```rust
use rusqlite::Connection;
use std::time::Duration;

pub fn open_db(path: &std::path::Path) -> Result<Connection, StateError> {
    let conn = Connection::open(path)?;
    conn.pragma_update(None, "journal_mode", "WAL")?;      // concurrent reads during writes
    conn.pragma_update(None, "synchronous", "NORMAL")?;    // FULL for max durability (see below)
    conn.pragma_update(None, "foreign_keys", "ON")?;       // OFF by default in SQLite!
    conn.pragma_update(None, "wal_autocheckpoint", 1000)?; // bound WAL growth
    conn.busy_timeout(Duration::from_secs(5))?;            // wait out a concurrent writer
    Ok(conn)
}
```

- `WAL` + `synchronous=NORMAL` is the right default: durable across app crashes, a tiny last-txn window on OS/power loss. Use `synchronous=FULL` (plus `PRAGMA fullfsync=ON` on macOS) when a single lost operation is unacceptable.
- Checkpoint the WAL at exit or after N txns so the `-wal` file doesn't grow unbounded.
- Batch multi-row writes in one transaction; never commit per row.

## Crash-safe idempotency keys

The core of `apply --idempotency-key`. Store every operation's intent *and* outcome so a re-run with the same key returns the cached result instead of re-doing the side effect. Two-phase: record `pending` intent **and commit it** before the side effect, then flip to `committed` with the cached envelope after.

```sql
CREATE TABLE IF NOT EXISTS operations (
    idempotency_key TEXT PRIMARY KEY,
    request_hash    TEXT NOT NULL,   -- sha256 of canonical request; detects key reuse with a different payload
    status          TEXT NOT NULL,   -- 'pending' | 'committed' | 'failed'
    result_json     TEXT,            -- cached parent-facing envelope, set on commit
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

```rust
pub enum Idem { Cached(String), Proceed, Recover, Conflict }

/// BEGIN IMMEDIATE takes the write lock up front so check-then-act is atomic
/// against a concurrent invocation racing on the same key.
pub fn claim(conn: &Connection, key: &str, req_hash: &str) -> Result<Idem, StateError> {
    let tx = conn.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
    let existing: Option<(String, String, Option<String>)> = tx
        .query_row(
            "SELECT status, request_hash, result_json FROM operations WHERE idempotency_key=?1",
            [key],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .optional()?;

    let decision = match existing {
        Some((_, h, _)) if h != req_hash             => Idem::Conflict,       // same key, different body → reject
        Some((s, _, Some(out))) if s == "committed"  => Idem::Cached(out),    // replay the stored envelope
        Some((s, _, _)) if s == "pending"            => Idem::Recover,        // prior run crashed mid-flight
        Some(_)                                      => Idem::Proceed,        // 'failed' → retry
        None => {
            tx.execute(
                "INSERT INTO operations(idempotency_key,request_hash,status,created_at,updated_at)
                 VALUES (?1,?2,'pending',?3,?3)",
                rusqlite::params![key, req_hash, now_iso()],
            )?;
            Idem::Proceed
        }
    };
    tx.commit()?; // pending intent is durable BEFORE the side effect runs
    Ok(decision)
}
```

Flow: `claim` → on `Proceed` do the side effect → `finish(key, envelope)` sets `status='committed'` with the cached envelope. On `Cached` skip the side effect and emit the stored envelope verbatim (same exit code). On `Conflict` fail with a typed error. On `Recover` reconcile (below). Reject empty/non-unique keys at the contract boundary. Cache the *result*, not just a "done" flag — replays must reproduce the exact envelope and exit code.

## Crash recovery

A `pending` row at startup means a prior process died *between* recording intent and committing the result — the side effect may or may not have landed. The store alone can't know; reconcile against the real target.

```text
for each operations row WHERE status='pending':
    observed = probe_target_state(op)        # ask the world what actually happened
    if observed == applied:  finish(key, reconstruct_envelope(observed))   # -> committed
    elif observed == absent: mark_failed(key)  # or re-run if the side effect is idempotent
    else:                    report unresolved; require operator input (exit non-zero)
```

`doctor` should: acquire the lock, `PRAGMA integrity_check`, sweep `pending` ops and reconcile each, compare DB↔JSONL version markers and re-export/rebuild whichever is stale, then confirm convergence (record counts, or a canonical-JSON SHA-256). Design the side effect to be naturally re-runnable (write a target-side marker you can probe), or a crashed `pending` op is unrecoverable without a human.

## Gotchas (one-liners)

- `foreign_keys` is **OFF** by default per-connection — set it every open or cascades silently no-op.
- Rename is only atomic within one filesystem — keep the temp file in the target's own directory.
- `sync_all()` on the file isn't enough — fsync the *directory* (Unix) or the rename can be lost on power cut.
- Use `BEGIN IMMEDIATE` for check-then-act; a deferred txn that upgrades to a write can deadlock two writers into `SQLITE_BUSY`.
- One `rusqlite::Connection` per thread; open fresh in workers, never share.
- Set `busy_timeout`; without it a concurrent writer fails you instantly with `SQLITE_BUSY`.
- Never put the SQLite file on a network filesystem; its locking is unreliable there.

## Anti-patterns

- Non-atomic writes — `write!` straight into the live state file (truncates on crash).
- SQLite for trivial state — a single counter or last-run timestamp belongs in one atomic-written JSON file.
- Unbounded logs — append-only JSONL/`operations` that never rotates or checkpoints.
- Two-way sync in one command — mirror one direction only; bidirectional needs cycle detection you won't get right.
- Idempotency by "have I seen this key?" with no `request_hash` — silently returns the wrong cached result on key reuse.
- Recording `committed` *before* the side effect, or doing the side effect before persisting `pending` intent — both break crash recovery.
- Per-record git commits / per-row transactions — commit storms; batch on a quiet-period cadence.
