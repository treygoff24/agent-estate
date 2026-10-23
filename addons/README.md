# Add-ons

Optional standalone tools that work well with the agent-estate setup. Each is its own project with its own repository, license and release cycle. None is vendored here: install the ones you want, and skip the rest. The core setup does not depend on any of them.

Where a tool is not public yet, the entry says so.

Keys go in your environment or your secret store, never in a committed file. Each tool's key is listed under its entry.

## Delegate Agent

`delegate` hands one bounded task (a review, an investigation, or a scoped implementation) to another coding-agent runtime such as Claude Code, Codex, Cursor Agent, Factory Droid or Pi, and records the run for later inspection. It does not commit, push, merge or deploy. Use it when you want a second model to review a diff, or to implement a small change while you watch. You need the Python 3.11+ toolchain and the runtime CLIs you plan to call, each already logged in; Delegate holds no key of its own.

- Install: `uv tool install delegate-agent-cli` (the PyPI name differs from the repo; the command is `delegate`).
- Repository: `https://github.com/treygoff24/delegate-agent`

## receipts

`receipts` answers a research question with claims, and every claim comes with a source URL, a quoted passage and a verdict. Anything it cannot verify goes in a separate `uncertainties` field instead of being stated. Use it when you need a cited answer from the open web rather than a fluent guess. It needs two keys.

- Keys: `CEREBRAS_API_KEY` and `EXA_API_KEY`.
- Install: `cargo install receipts`
- Repository: `https://github.com/treygoff24/receipts` (the repository name is `receipts`)

## exa-agent-cli

`exa-agent` is a single Rust binary over Exa's search, page contents, answers, agent runs, monitors and Websets. Every command prints JSON, a mutating command can be previewed with `--dry-run`, and `capabilities search` describes a command offline so an agent does not have to load every schema. It is unofficial and not affiliated with Exa.

- Key: `EXA_API_KEY`.
- Install: `cargo install exa-agent-cli` (the binary is `exa-agent`)
- Repository: `https://github.com/treygoff24/exa-agent-cli`

## elevenlabs-cli (`elv`)

`elv` is an agent-first command-line client for ElevenLabs' published API: speech, transcription, music, sound effects, dubbing, voices, conversations and workspace operations. Each command prints one JSON envelope, and large outputs (audio, transcripts) are written to disk with the path returned in the envelope. Use it when an agent needs to generate or transcribe audio without a bespoke wrapper. It is not affiliated with ElevenLabs.

- Key: `ELEVENLABS_API_KEY`.
- Install: `npm install -g eleven-agent-cli` (the command is `elv`)
- Repository: `https://github.com/treygoff24/elv` (the local folder is `elevenlabs-cli`)

## scout

`scout` orients an agent in an unfamiliar directory. `scout brief` prints a module map, entry points and hot files for a session start; `scout "<query>" <dir>` returns findings whose quoted lines were checked against the source file at the claimed line. Use it when an agent would otherwise spend a large share of its budget just looking around a repository. Indexing calls a model and spends money, and it is resumable.

- Key: `CEREBRAS_API_KEY` (or `SCOUT_API_KEY`).
- Install: `cargo install scout-cli` (the binary is `scout`)
- Repository: `https://github.com/treygoff24/scout`

## agent-hangover (`hangover`)

`hangover` cleans up the machinery that agents leave behind (dead exports, duplicate helpers, one-caller abstractions, tests tied to implementation details) without changing behaviour. Each cleanup has to pass the repository's own gates, a pinned analyzer and a fresh-context reviewer before it closes, and it does not apply fixes on its own: `hangover fix` gives you an evidence packet, and you or an agent make the edit. The backlog lives in the repository's `.hangover/` folder, so a campaign survives from one session to the next. Use it on a TypeScript/JavaScript repository (Rust Cargo workspaces are experimental) that an agent has been writing into for a while. It was called `deslop` before its public release.

- Key: none of its own. The default reviewer is the Codex CLI, installed and signed in; a delegate runner or other command runner can be configured instead.
- Install: `npm install -g --allow-git=root --allow-scripts=@ast-grep/cli git+https://github.com/treygoff24/agent-hangover.git` (not on the npm registry; needs Node 22+ and Python 3.11+), then `hangover doctor`. Its agent skill is `skills/hangover/SKILL.md` in the repository.
- Repository: `https://github.com/treygoff24/agent-hangover`

## porkbun-mcp (`mcp-server-porkbun`)

An MCP server for managing Porkbun domains and DNS through the Porkbun API v3. Risky calls require a dry-run confirmation, and live writes are blocked unless you set `PORKBUN_ENABLE_LIVE_MUTATIONS=true`. Use it when an agent needs to read or change DNS records under your supervision. Keep the live-mutations switch off unless you are asking for a change.

- Keys: `PORKBUN_API_KEY` and `PORKBUN_SECRET_API_KEY`.
- Install: `npm install -g mcp-server-porkbun` (the binary is `porkbun-mcp`), then add it to your MCP client as a stdio server.
- Repository: `https://github.com/treygoff24/porkbun-mcp`

## mcp-image

An MCP server for generating and editing images with Gemini's Nano Banana models, built for Codex and Claude Code. Prompt improvement is kept out of the MCP call, so the server stays small and the image request is what you wrote. It began as a fork of [shinpr/mcp-image](https://github.com/shinpr/mcp-image) and has since been reshaped for local agent workflows.

- Key: `GEMINI_API_KEY`.
- Install: clone the repository, run `npm install` and `npm run build`, then register `dist/index.js` in your harness config (its README has the exact Codex and Claude Code entries).
- Repository: `https://github.com/treygoff24/mcp-image`

## codex-limit-meter

A single Python file that reads the logs Codex keeps on your machine and reports how many dollars of Codex work one percent of your weekly limit buys. It needs no installs, no accounts and no network. Use it to compare plans or to see whether your usage fits the plan you pay for. It reads `~/.codex` (or `$CODEX_HOME`); if some of your logs live elsewhere, it understates your allowance, so check the scan output first.

- Key: none.
- Install: clone the repository and run `python3 codex_limit_meter.py report` (Python 3.10+).
- Repository: `https://github.com/treygoff24/codex-limit-meter`

## papercuts

A complaint box for agents. `papercuts add "<text>"` appends a line to `.papercuts.jsonl` at the repository root, so friction is recorded where it happened and travels with the repository in `git diff`. Use it when agents keep hitting the same dead end and nobody is told. Review the backlog with the tool's own list command (`papercuts --help`).

- Key: none.
- Install: `cargo install papercuts` (needs Rust 1.89 or newer).
- Repository: `https://github.com/treygoff24/papercuts`

## Memorum

One memory shared by every coding agent you use. It keeps the memory as a git repository of Markdown files, served by a local daemon (`memoryd`) and read and written through its CLI, with recall hooks that put relevant memories into each session. It is work in progress, and its own README says not to build on it yet. Setup, the trade-offs and the operating rules are in [guides/shared-memory-memorum.md](../guides/shared-memory-memorum.md).

- Key: see that guide.
- Install: see that guide.
- Repository: not yet published.
