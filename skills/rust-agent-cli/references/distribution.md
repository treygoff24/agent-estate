# Distribution and agent self-discovery

Release quality for an agent CLI means automation can install it, verify it, and discover how to call it without a human improvising. Two jobs: ship a verifiable binary, and make freshly-installed binaries announce themselves to the agents that will drive them.

## Release-artifact contract

Build all four targets; static-link Linux with `musl` (portable, no glibc-version roulette — `gnu` is an anti-pattern):

| Platform | Triple |
| --- | --- |
| Linux x86_64 | `x86_64-unknown-linux-musl` |
| Linux arm64 | `aarch64-unknown-linux-musl` |
| macOS x86_64 | `x86_64-apple-darwin` |
| macOS arm64 | `aarch64-apple-darwin` |

- **Naming.** Pick one canonical scheme and publish a simple alias so an installer's fallback chain finds it: versioned `{repo}-v{VERSION}-{TARGET}.tar.gz`, latest alias under `/releases/latest/download/`, simple alias `{repo}-{OS}-{ARCH}.tar.gz`.
- **Checksums.** Publish `SHA256SUMS` alongside every tarball. Installer verifies before install (`sha256sum` on Linux, `shasum -a 256` on macOS): tool missing → warn + skip; mismatch → hard fail.
- **Signing (optional, asymmetric verify).** Sigstore/cosign keyless, signed by the release workflow's OIDC identity. cosign absent → soft-skip; cosign present + bad signature → hard fail.
- **`--version` carries provenance.** Bake commit + build date at compile time (a `build.rs` emitting `GIT_SHA`/`BUILD_DATE`, or `vergen`) and expose a machine-readable form: `tool --json version` → `{"version","commit","date","target"}`. Agents (and `doctor`) diff this, not the human string.

## curl|bash installer non-negotiables

The whole script must run with zero prompts so an agent can pipe it.

- **Hardening.** `set -euo pipefail`, `umask 022`, `trap cleanup EXIT` (never leak temp dirs).
- **Platform detect → triple**, with a `cargo build --release` source fallback for unknown platforms.
- **Verify before install.** Download to temp, checksum-verify, then `install -m 0755` (atomic copy+chmod). Never install an unverified blob.
- **Drive everything by flag *or* env var** so there is no interactive path: `--yes`/`FORCE=1`, `--dest`/`DEST=`, `--version`/`VERSION=`, `--no-verify` (escape hatch), `--no-configure` (skip agent registration), `--offline TARBALL`, `--quiet`. A non-TTY stdin must proceed with defaults, never block on `read`.
- **Idempotent re-run.** Version-already-installed short-circuits the download but still runs agent configuration (which is itself idempotent), then `exit 0`.
- **Machine-readable final status** — a last line an agent can grep, even under `--quiet`:

```text
INSTALL_OK bin=$HOME/.local/bin/tool version=1.4.0 agents=claude:merged,codex:skill path_updated=1
```

- **No sudo by default.** Install to `~/.local/bin` (user-writable); `--system` is opt-in. Detect whether the dest is on `PATH` and, if not, print the exact `export` line.

## Agent auto-configuration (the load-bearing part)

A freshly installed binary should make agents aware it exists, what it does, and how to introspect it — without the agent having read your README. For a *callable* agent CLI this is the default mode (a guard/interceptor CLI that must hook agent shell calls is a different, narrower job — register a `PreToolUse`/`beforeShellExecution` hook per agent and skip the rest of this section).

**1. Drop a thin skill / instructions file** into each detected agent's skills dir, idempotently — tarball-primary with an inline-heredoc fallback so it works offline:

```bash
for dest in "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.agents/skills"; do
  [ -d "$(dirname "$dest")" ] || continue
  mkdir -p "$dest/$REPO"
  if curl -fsSL "$SKILL_URL" -o "$TMP/skill.tgz" 2>/dev/null; then
    tar -xzf "$TMP/skill.tgz" -C "$dest"
  else
    cat > "$dest/$REPO/SKILL.md" <<'EOF'
... name + one-line description + "run `tool --json describe` to self-orient" ...
EOF
  fi
done
```

Keep the skill body thin: name, one-line description, and a pointer to the binary's own introspection surface — not a copy of help that will drift.

**2. Merge a project-level `AGENTS.md` / `.cursor/rules` entry, never clobber.** Use a fenced marker block so re-runs replace only your section:

```bash
MARK_BEGIN="<!-- tool:begin -->"; MARK_END="<!-- tool:end -->"
# if markers exist, replace between them (python3, not sed — sed mangles multiline);
# else append the block. Back up first; merge preserves sibling content.
```

**3. Expose an introspection surface the agent can call** — this is what makes the CLI self-orienting and is the single most important deliverable of the whole install:

- `tool --json describe` → full command catalog (every subcommand, flag, type) as JSON. The single source agents read instead of scraping `--help`.
- `tool --json <cmd> --help` → structured per-command spec.
- `tool doctor [--json]` → post-install diagnostics (version, config found, auth/keys present, PATH ok), non-zero on any failure. The installer's own `--verify` calls this to confirm the tool is live.
- Optionally `tool schema` → JSON Schema of structured inputs/outputs.

Generate `describe` / per-command help from one registry so the three surfaces can't drift.

### Idempotent JSON merge (when touching any `settings.json`)

Non-negotiable: timestamped backup before write, dedup by binary name, tolerant load (corrupt/empty → `{}`), rollback on failure, never clobber sibling keys. Try `jq` deep-merge, fall back to embedded `python3` (always present; `sed`/`awk`/hand-written JSON in bash are anti-patterns):

```bash
echo "$existing" | jq ". * $NEW_JSON" > "$settings"   # "*" deep-merges objects, keeping existing keys
```

Report a per-agent status from a stable vocabulary in the final summary: `created | merged | already | failed | skipped | unsupported | conflict | no_repo`. If an existing config lacks your marker, report `conflict` and do not overwrite.

## Rust release tooling

Use **cargo-dist** to generate the release matrix (the four triples), `SHA256SUMS`, the GitHub Release upload, and a baseline `install.sh` with platform-detect + checksum-verify already wired — then layer the agent-config steps on top. Keep the crate **cargo-binstall-compatible** (predictable naming + a `[package.metadata.binstall]` block) so `cargo binstall tool` works for Rust users, and ensure plain `cargo install tool` still builds from source as the universal fallback. Net: three acquisition paths — curl|bash (agents/CI), `cargo binstall` (fast, no compile), `cargo install` (source) — all landing the same `--version`-stamped binary.

## Publishing to crates.io

Two gotchas that bite at ship time (both hit on a first launch):

- **Check the crate name before you commit to it.** crates.io names get squatted — generic words especially (a 0.0.1 placeholder claimed `recon` a week before launch). Check early with `curl -s -A "name-check (<your email>)" https://crates.io/api/v1/crates/<name>` (404 = free; a plain curl with no user-agent gets policy-blocked). If the name is taken, decide rename vs `<name>-cli` crate with a `<name>` binary before writing any docs or URLs.
- **Whitelist crate contents.** Without `include` in `Cargo.toml`, `cargo publish` packages everything not gitignored — README banner images, docs/, tests/, CI config — and any *untracked* file aborts the publish as a "dirty tree." Set `include = ["src/**", "Cargo.toml", "README.md", "LICENSE", "CHANGELOG.md"]` and verify with `cargo package --list` + `cargo publish --dry-run` before tagging.

## Anti-patterns

- No checksum / no signature — supply-chain hole; verify SHA256 always, cosign when present.
- Clobbering agent config — overwriting `settings.json`/`AGENTS.md` instead of backup-then-merge; `sed`/hand-written JSON that corrupts on special chars.
- Requiring interaction — any prompt, a TTY check that blocks, or a missing `--yes`/env mode; an agent can't answer a `read`.
- sudo-by-default — default to `~/.local/bin`; `--system` opt-in only.
- No idempotency — re-run errors out or double-appends hooks/PATH lines instead of detecting "already configured."
- `gnu` Linux target — non-portable; use `musl`.
- Hard-fail on optional steps — a missing agent, no cosign, a failed skill-drop should warn + continue, not abort.
- Drift-prone help — hand-maintained `describe`/help text that diverges from the real flags; generate both from one registry.
