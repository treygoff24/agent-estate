# Shared agent memory with Memorum

Memorum (`memoryd`) is one memory shared by every coding agent and machine you use: decisions, fixes that worked, where things live, what failed last time. Claude Code and Codex each keep private notes, so a session in another tool or on another machine starts cold; Memorum holds that memory in one git repository of Markdown files, served by a local daemon that agents read and write through a CLI. It is optional. The rest of agent-estate works without it.

## Do you need this?

**Skip it** if you work in one tool on one machine, or if `CLAUDE.md` / `AGENTS.md` files and each tool's own memory already carry what you need. Also skip it if you cannot accept running an early-stage tool.

**Do it** if you move between Claude Code, Codex and other harnesses, or between a Mac and a VPS, and keep re-explaining the same decisions. The feature agents use most is the end-of-session "focus" handoff: what the last session was doing on this project and branch.

**Be honest about the state of the project.** Memorum is a work in progress. It is in daily use by its author, has no releases, its CLI and file formats still change without notice, and its repository is not yet public: check the project page for availability. Until then this guide tells you what it does and how agents use it, not a download line. Install steps below apply once you have the source.

**Cost:** one small daemon per machine (Rust), a git repo of Markdown (default `~/memorum`), a SQLite index rebuildable from it. Optional keys: a Gemini API key for embeddings (vector search) and an OpenRouter key for the per-message recall judge. Without them it runs on keyword search alone.

## Prerequisites

- A recent stable Rust toolchain to build it, on each machine.
- Git, and for two or more machines a shared remote you control (a private repo on any host works; `INSTALL.md` section 3 shows the GitHub setup).
- Claude Code and/or Codex installed. Memorum can import what they already saved.
- The project source, obtained from its project page once available.

## What it gives you

- **Governed writes.** A write is checked for duplicates, contradictions with existing memories and missing sources. A newer memory supersedes an older one instead of overwriting it, so history stays.
- **Typed memory.** Each memory has a kind: `preference`, `procedure`, `lesson`, `fact`, or `status` (time-bounded; expires from recall at `valid_to`). It also has a namespace: `me` (the user's identity and preferences), `project` (this repository), `agent` (lessons that hold across projects).
- **Recall without asking.** At session start a hook injects a short block about the current project (the focus note first), and on each message a judge model rates search hits against the live conversation and injects only the helpful ones. The hook fails open: a timeout or missing key injects nothing.
- **Standing rulings.** A memory written with `standing: true` is a ruling: a durable instruction the user gave, kept ahead of ordinary memories. Write it only when the user explicitly asks for it.
- **Two machines, one memory.** Each machine runs its own daemon on its own clone; clones sync through a shared git remote with a merge driver that merges memory files by field, not by line.
- **Nightly dreaming** (optional): a model reads recent memory, merges redundant entries and writes reflections. Today it consolidates little and a redesign is planned; do not count on it.
- **Import.** `memoryd import` brings in what Claude Code and Codex already saved, without duplicating on re-runs.

## Steps

### 1. Build and install

From the Memorum source checkout:

```bash
export MEMORUM_REPO="$HOME/memorum"
export MEMORUM_RUNTIME="$MEMORUM_REPO/.memoryd"
bash scripts/install-memorum.sh --repo "$MEMORUM_REPO" --runtime "$MEMORUM_RUNTIME"
```

The installer builds `memoryd` and `memory-merge-driver` and prints lifecycle commands with an absolute socket path.

**Done when:** `memoryd --help` prints and `command -v memory-merge-driver` finds the merge driver.

### 2. Initialize, import and wire hooks

```bash
memoryd init                       # interactive: imports Claude Code/Codex memory, starts the daemon, wires hooks
# scripted/CI (stdin not a terminal): memoryd init --non-interactive --daemon systemd --repo "$MEMORUM_REPO" --runtime "$MEMORUM_RUNTIME"
```

`memoryd init` is interactive and declining every prompt changes nothing. When stdin is not a terminal, a bare `init` refuses on purpose; scripts must pass `--non-interactive`. On Linux, `--daemon systemd` installs the daemon and the daily dream timer as systemd user units. `init` creates `~/.config/memorum/env` (mode 0600) with a commented `MEMORUM_GEMINI_API_KEY=` line and never writes a key value; the human adds the key if wanted.

Use `memoryd init --detect-only` to see what exists without changing anything, and `memoryd import --dry-run` to preview an import.

**Done when:** `memoryd status` exits 0 and `memoryd doctor --repo "$MEMORUM_REPO" --runtime "$MEMORUM_RUNTIME"` reports healthy.

### 3. Optional: turn on embeddings

```bash
memoryd config embedding-lane --lane gemini-api    # needs MEMORUM_GEMINI_API_KEY in ~/.config/memorum/env; restart the daemon after
```

`doctor` reports API problems as `embedding_api_*` findings. Without the key, search falls back to keywords.

**Done when:** `memoryd doctor` shows no `embedding_api_*` finding.

### 4. First round trip

```bash
memoryd write-note "memorum smoke test note"
memoryd search "smoke test note"
```

**Done when:** the search hit list contains the new memory's id (`data.hits` in the JSON on stdout).

### 5. Add a second machine

There is no pairing command: device pairing is unsupported alpha scope, so this step is manual. The mechanism is plain git: each machine's memory repo has the same private remote as `origin`.

```bash
git -C "$MEMORUM_REPO" remote add origin <your-private-remote>   # first machine; push once
# second machine: clone the same remote to the same path, then run: memoryd init
memoryd sync now          # one cycle; waits up to 60 s
```

Sync is silently disabled (local commits only) when the repo has no `origin`, or when the merge driver cannot be resolved; `memoryd sync now` exits 65 with no `origin` and 75 on a fetch, merge or push failure. The daemon otherwise fetches on startup and every 5 minutes and pushes within seconds of a commit. A merge quarantine (`memoryd quarantine list`) is a human checkpoint: edit the memory file until no conflict markers remain, then `memoryd quarantine resolve --edited <id>`; the daemon never picks a side. Only one device should run the nightly dreaming pass (the always-on VPS is the natural choice); leave `dream now`, `dream scheduled` and `dream enable` to that schedule.

**Done when:** `memoryd sync now` reports `data.outcome` of `nothing_to_do`, `fast_forwarded` or `pushed` on both machines, and a note written on one is returned by `memoryd search` on the other within a few minutes.

### 6. Teach your agents the loop

Put this in the user-level instructions your agents load (`CLAUDE.md`, `AGENTS.md`), and install the `using-memorum` skill from the Memorum source for the full command reference:

1. **Orient.** At session start read the injected `<focus>` first. If it says `stale`, orient from git and rewrite it at closeout. If no block arrived in an interactive session, run `memoryd status`; exit 75 means the daemon is down, then run `memoryd doctor`.
2. **Recall before search.** Check the injected recall blocks first. If something is missing: `memoryd search "<terms>"` (scoped to you, this project and the agent namespace), `--all-namespaces` for another project, then `memoryd get <id>` for the full body (capped at 4 KiB).
3. **Write.** Search first. A quick note is `memoryd write-note "<text>"` (immediate, ungoverned). A real memory is governed:

```bash
memoryd write "The staging deploy needs the cache flag; without it the build serves stale assets." \
  --title "Staging deploy needs cache flag" --tag deploy \
  --meta '{"namespace":"project","type":"claim","kind":"lesson","source_kind":"agent_primary","source_ref":"file:/abs/path/to/notes.md"}'
```

   Cite what you found yourself with `source_kind` and `source_ref`. A write with no source is recorded as user-stated, so reserve that for what the user told you. A `status` memory needs `valid_to`. `data.status` must be `promoted` to be live; `candidate` or `quarantined` waits in `memoryd review queue`.
4. **Correct.** `memoryd supersede <old-id> "<corrected text>" --reason "<why>" --meta '{"source_kind":"...","source_ref":"..."}'` keeps the chain. `memoryd forget <id> --reason "<why>"` tombstones (text stays on disk). For a leaked secret add `--purge`, and tell the user git history still holds the original.
5. **Close out.** Write the handoff, under 400 words, first line a one-sentence summary of at most 280 characters, from inside the git checkout:

```bash
memoryd focus write --body-file /abs/path/focus.md
```

**Done when:** an agent in a fresh session on the same project and branch quotes the previous session's goal and next step from the injected focus.

### 7. Read the contract, not this guide

Commands print one JSON envelope: success on stdout with exit 0, failure on stderr with a nonzero exit (65 invalid input or governance refusal, read `error.suggested_fix`; 66 no such memory; 75 daemon unreachable, retry once then `doctor`). `memoryd schema --json` prints the whole contract. Since the CLI still changes, trust `memoryd schema` and `memoryd --help` over any copy of the commands here.

## What bit us (papercuts)

1. **Recall noise.** In a long session a good share of the injected memories can be noise. → Read `score`, `updated` and `source` before relying on a recalled memory, and `memoryd get` the body before acting on a summary.
2. **Vector search mostly fell back to keywords** in early use. → Treat semantic search as an extra, and write memories with specific `cues` and `abstraction` so keyword hits land.
3. **Subagents and headless runs get no startup block.** Per-message recall reaches interactive sessions only. → Tell delegated agents to run `memoryd search` themselves.
4. **Over-built first version.** A privacy layer, an MCP server, a web dashboard and cross-session coordination were cut to shrink the system to what gets used. → Start with notes, search, focus and sync; add the rest only when you feel the need.
5. **Sync can stall for days without a visible error.** A misconfigured merge driver or a dirty lease file blocks merges cycle after cycle. → Check `memoryd status` and `memoryd doctor` on a schedule (below) rather than assuming sync works.
6. **Setup can assume the author's launch scripts**, which turn recall on for interactive sessions only. → Confirm the hooks are wired in each harness with a deliberate test: ask a fresh session what the focus said.
7. **Dreaming consolidates little today** (no feed of raw session events, no contradiction checking). → Do not rely on it to tidy memory; supersede stale entries yourself.

## Keeping it healthy

- Run `memoryd doctor` from the same timer or morning routine that runs your other health checks; `events_log_mirror_lag` is advisory, `memoryd doctor --reindex` rebuilds it.
- Run `memoryd sync now` before leaving a machine you will not use for a while.
- Expire `status` memories by giving them `valid_to`; daily cleanup archives them. Facts are never auto-archived, so supersede stale ones.
- Back up the memory repo like any other git repo (its remote is the backup).
- To remove it: `memoryd uninstall --print-only` previews; plain `memoryd uninstall` keeps your data and `--purge` deletes it.
- Re-check this guide against `memoryd schema` after each update.

Last checked: 2026-10, Debian 13 and macOS (Memorum built from source; no tagged release).
