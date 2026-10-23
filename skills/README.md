# Starter skill pool

Thirty-four skills that agents load on demand: software craft and process (design,
test-driven development, debugging, review, test auditing, architecture), writing,
and a few broadly useful technical references. A skill is a folder with a
`SKILL.md` (frontmatter `name` and `description`, then instructions) and optional
reference files the skill names. A harness shows the agent only the name and
description until the task calls for the skill, so a large pool costs little
while it stays dormant.

Every skill here is either written for this repo or copied from an upstream project
under a license that allows redistribution (MIT, with the upstream `LICENSE` kept in
the skill's folder). `PROVENANCE.md` has one row per skill. Skills we did not copy,
because their license is unclear or restrictive, are listed with where to get them
in `RECOMMENDED-UPSTREAM.md`.

## What is in the pool

| Group | Skills |
| --- | --- |
| Design and planning | `task-design`, `brainstorming`, `grilling`, `premortem`, `wayfinder`, `domain-modeling`, `codebase-design`, `improve-codebase-architecture`, `codebase-mapping` |
| Build and test | `tdd`, `debugging-systematic`, `test-value-audit`, `coverage-architect`, `quality-gate`, `hillclimb` |
| Review and honesty | `code-review`, `receiving-code-review`, `review-until-dry`, `no-ceremony`, `triage`, `triage-issue` |
| Writing and prompts | `writing`, `writing-for-agents`, `codex-prompting`, `operationalizing-expertise`, `teach` |
| Shipping | `open-source-readiness`, `oss-launch`, `rust-agent-cli` |
| Visual QA | `visual-qa-harness`, `vqa-fresh-eyes` |
| Technical references | `rust-engineer`, `supabase-postgres-best-practices`, `interaction-design` |

## Rendering it with `skillherd`

The [`skillherd`](https://github.com/treygoff24/skillherd) CLI renders a pool into every harness's
skill directory from one policy file, and only ever removes entries it created. The
policy is in `.globals/`:

- `harnesses`: which harnesses to serve. Claude Code and Codex by default.
- `sets`: the always-on skills. Five, on purpose. Every always-on skill puts its
  description in every session's context, and long always-on lists are a known failure
  mode.
- `presets/`: named bundles for per-project activation (`dev`, `design-and-docs`, `ship`).
- `house`: skills that live in this pool rather than being tracked from an upstream.

Point the CLI at this directory and render:

```bash
export SKILLHERD_LIBRARY=~/Code/agent-estate/skills   # the pool (this directory)
export CLAUDE_SHARED=~/.claude                        # Claude Code reads ~/.claude/skills
skillherd doctor            # pool and surfaces: should report nothing but "surface_drift" before the first render
skillherd render            # links the always-on set into ~/.claude/skills and ~/.codex/skills
skillherd list --harness claude
```

Then activate more where you need them:

```bash
skillherd search review                  # find a skill by name or description
cd ~/Code/my-project && skillherd add @dev     # a preset, for this project only
skillherd add writing                    # or single skills
skillherd on code-review                 # always-on, everywhere (use sparingly)
```

Try it first in a scratch home (`HOME=$(mktemp -d) skillherd render`) if you want to see
what it would write. `skillherd render --dry-run` prints the plan without changing anything.

Without the CLI, any harness can use a skill by copying or symlinking its folder into
`~/.claude/skills/` (Claude Code) or `~/.codex/skills/` (Codex), or into a project's
`.claude/skills/` or `.agents/skills/`.

Some skills carry helper scripts (`hillclimb/scripts/hc`, `writing/lint.py`,
`coverage-architect/scripts/test_inventory.py`, `visual-qa-harness/scripts/`). They use
only the Python 3 standard library, except `visual-qa-harness`, which needs
Chrome/Chromium and Pillow. Paths in a skill are relative to its own folder.

## Adding your own skills

1. Make a folder `skills/<name>/` with a `SKILL.md` that starts with frontmatter:

   ```markdown
   ---
   name: <name>          # must match the folder name
   description: When to use this skill, in one or two sentences an agent can match against a task.
   ---
   ```

   The description is the only part an agent sees before loading the skill, so write
   it as a trigger ("Use when ..."), not a summary. Keep `SKILL.md` lean and put
   long material in reference files the skill names; a file nothing points at never
   gets read. `writing-for-agents` is the guide to writing these well.
2. List the name in `.globals/house` (so `skillherd doctor` knows it is yours).
3. Optionally add it to a preset in `.globals/presets/`. Put it in `.globals/sets`
   only if you want it in every session.
4. `skillherd render`, then `skillherd doctor` to confirm.

To bring in someone else's skill, use `skillherd install <owner/repo>`, which records its
upstream so `skillherd update` can refresh it. Check the license first, and keep its
`LICENSE` file with it if you redistribute the pool.

Machine-specific text: if the same pool serves a Mac and a Linux box, fence the lines
that exist on only one with `<!-- mac-only -->` / `<!-- linux-only -->` markers; the
renderer serves each side only its own lines.
