# Per-tool false positives to pre-empt

The findings that will fire on a clean scaffold and are *not* real defects. Disabling these is disposition, not laziness — each fights a framework idiom, not a bug.

## oxlint (Next.js / React App Router)

The aggressive tiers flag valid framework code. Disable these specific rules with the reason:

- `react/react-in-jsx-scope` — off. Modern JSX transform; no `import React` needed.
- `react/jsx-max-depth` — off. Defaults to 2; unusable for real layouts.
- `import/no-named-export` and `import/prefer-default-export` — off. Next route files (`layout.tsx`, `page.tsx`) *require* named exports (`metadata`, `generateStaticParams`).
- `import/no-unassigned-import` — allow `**/*.css` (Next imports global CSS as a side effect).
- `new-cap` — off. Next font loaders (`Geist()`, `Inter()`) are called functions, not constructors.
- `capitalized-comments` — off. Noise.
- `no-magic-numbers`, `id-length`, `max-lines-per-function`, `max-depth`, `no-ternary`, `sort-keys`, `sort-imports`, `func-style`, `unicorn/filename-case` — off. Style opinions that fight normal code without catching defects.

Set `env: { browser: true, node: true }`.

## react-doctor — install is invasive

`react-doctor install` does three things you probably don't want:

1. **Writes a skill dir for ~40 different agent tools** (`.cursor/`, `.windsurf/`, `.roo/`, and so on). Keep only the ones the repo actually uses (e.g. `.claude/`); gitignore or delete the rest.
2. **Adds a GitHub Actions workflow.** Delete it if the repo is local-only / no-GitHub.
3. **Adds a pre-commit hook** — this one you may want; decide deliberately.

Two scan false positives:

- **It flags secret-shaped strings in build-log artifacts** — e.g. a UUID in a gitignored `.agent-runs/*/stdout.log` trips `artifact-secret-leak`. Fix: a `doctor.config.json` with an `ignore` array covering build-log / content / docs dirs. The config *is* honored, but **react-doctor caches** — clear `node_modules/.cache/react-doctor` after editing the config or you'll debug a stale finding.
- **It exits 0 even with findings by default.** Add `--blocking error` so a real finding fails the gate.

## oxfmt / impeccable — scope discipline

Both will happily judge files that aren't source. Point them at `src` only. An oxfmt run over your markdown deliverables reports dozens of "format issues" that are just its opinion of prose — pure noise that erodes trust in the gate.

## The meta-check

After calibration, seed one real defect of each class (a type error, an unused var, a banned font in CSS) and confirm the gate goes red. A gate you never watched fail is a gate you don't know works.
