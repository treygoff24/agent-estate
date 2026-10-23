---
name: oss-launch
description: Take a working local tool to a fully shipped open-source launch — name check, sales-forward README with cover art, AGENTS.md machine contract, packaging/CI/release pipeline, public repo, and a ship-wizard for the human-only steps. Use when the user says "ship this as open source", "make this a real OSS tool", "launch package", or a project needs the full modern agent-friendly release treatment.
---

# OSS Launch

Turn a working local tool into a shipped, installable, discoverable open-source project in one session. The phases are dependency-ordered; run them as one pass. Everything the agent can do, the agent does; everything only the human can do goes into a generated ship-wizard at the end.

Launching a *personal* project with private history, personal data, or a signed release? Run `open-source-readiness` first. Its fresh-export publish replaces Phase 4's `gh repo create --source . --push`, which would put your whole history public.

## Phase 0 — Name check (before anything else)

The name is load-bearing for every later artifact (URLs, badges, install commands, env vars), so settle it first.

1. Check the package registry: `curl -s -A "name-check (<email>)" https://crates.io/api/v1/crates/<name>` (404 = free) — or the npm/PyPI equivalent. Registries get squatted; generic words especially.
2. Check the GitHub repo slug is free.
3. If taken, present options via AskUserQuestion: rename (check a shortlist of candidates against the registry first, present only confirmed-free ones), `<name>-cli` crate with original binary name, or dispute the squat (slow — don't block launch on it).
4. If renaming: sed across tracked source only (`git ls-files`), including case variants and env-var prefixes and schema/identifier strings. Leave dated design docs in `docs/plans/` as history. Gate immediately after.

Also confirm early: which GitHub account/org (check `gh api user -q .login` — don't guess the username, it burns URLs baked into README/Cargo metadata), public-now vs polish-private-first.

## Phase 1 — Launch docs

**README = half sales, half reference**, two audiences explicitly:

- Cover banner at top (Phase 2), centered title + one-line pitch, badges (registry version, CI, license).
- An "🤖 Are you an agent? → AGENTS.md" callout near the top.
- The hook: one paragraph naming the problem, then a real invocation + real output block a reader can evaluate in 10 seconds.
- Install section with every path (brew, curl installer, cargo/npm/pip), then usage, then the reference material (env vars, exit codes, contracts) as the back half.
- Load `writing` before drafting the sales prose.

**AGENTS.md = the machine contract**, not a README copy: install one-liner, secrets the agent must request from its human (with URLs to get them), self-verification command (`doctor`-style if the tool has one), canonical invocations with cost/latency expectations, output-parsing rules ("trust rule": which fields are citable/actionable), exit-code table with "your move" column, and a pointer to machine self-description commands as the source of truth.

Plus: CONTRIBUTING.md (short: the gate command + invariants), CHANGELOG.md, package metadata (description/license/repository/homepage/keywords), and the publish **include-whitelist** (see rust-agent-cli `references/distribution.md` — without it you ship banners and CI config inside the package, and untracked files abort publish).

## Phase 2 — Cover art

1280x640 (GitHub social-preview size — also ideal README banner). Use whatever image-generation tool you have — ask for 3 candidates with meaningfully different compositions, exact-spelling requirement on the wordmark/tagline, "no glowing robots/AI brains" guard, and have it resize to exactly 1280x640. Review candidates yourself; keep one file (`assets/cover.png`), delete rejects. For text-heavy wordmark banners, hand-built SVG rasterized at 2x renders sharper than diffusion and costs $0 — a legitimate fallback, not a compromise.

## Phase 3 — Packaging + CI

For Rust: `dist init` (cargo-dist) with shell + homebrew installers, tap = `<user>/homebrew-tap` (create the tap repo if missing), `publish-jobs = ["homebrew"]`. Add a plain CI workflow (fmt/clippy/test on push + PR). Validate with `dist plan`. Other ecosystems: goreleaser (Go), semantic-release/np (npm) — same shape: tag → binaries → installers → formula.

Verify publish packaging before tagging: `cargo package --list` shows only source + metadata; `cargo publish --dry-run` passes.

## Phase 4 — Repo

`gh repo create <user>/<name> --public --source . --push` with a real description; add topics; social preview is a settings-UI upload only the human can do (goes in the wizard). Watch the first CI run to green before proceeding.

## Phase 5 — Ship wizard

Generate a throwaway interactive checklist script covering ONLY the human-gated steps, then let the wizard itself automate the rest so finishing the wizard = shipped:

- Tokens the human must create in a browser (registry token → `cargo login`; fine-grained PAT for the tap → `gh secret set HOMEBREW_TAP_TOKEN` — run from repo root so gh targets the right repo).
- Social preview upload (open the settings URL + reveal the banner file in your file manager).
- Then the wizard runs publish (dry-run first, confirm gate — registry publishes are permanent), tags vX.Y.Z, pushes the tag, and opens the Actions page.

Wizard is session-ephemeral: gitignore it, delete after the run.

## Phase 6 — Verify as a real user

Not done until installed from the public path: `brew install <user>/tap/<name>` (or equivalent), `--version`, one real invocation, plus registry page live and installer URL returning 200. Fix-forward anything found, get an independent review (a second agent from another model family) on any post-launch patch, ship it as a point release through the same tag pipeline.

## Session-proven gotchas

- GitHub username ≠ assumed: verify with `gh api user -q .login` before baking URLs anywhere.
- crates.io API blocks default curl user-agents — always send `-A "purpose (email)"`.
- Homebrew formula publish to a separate tap repo needs its own PAT secret (`HOMEBREW_TAP_TOKEN`); the workflow's `GITHUB_TOKEN` can't write to other repos.
- If a dry-run/estimate output exists, make sure its headline number is the *expected* case, not worst case — agents budget off it.
