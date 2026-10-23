---
name: open-source-readiness
description: >-
  Open-source readiness: make a personal project safe and credible to publish (private data, history and identity leaks, license provenance, security for strangers, release-artifact leaks, stranger UX), then publish a fresh export. Use before open-sourcing a personal repo, when auditing a repo or release build for publication, or when asked for a readiness pass. Launch polish (name, sales README, packaging) is oss-launch.
---

# Open-source readiness

A personal project holds things its owner stopped seeing: a work email in history, home paths in the binary, a legal name in a signature, a private project named in a comment, a vocabulary file of real people's names. This skill finds them, fixes them, and publishes a clean **export**. The pattern was developed on a first publish of a desktop app; the export script, release-audit script and plan it used are described in `references/export-and-audit.md` and `references/plan-template.md`, to rebuild for each project.

Launch polish (name check, sales README, cover art, packaging, ship wizard) belongs to `oss-launch`. Run this skill through step 7 first, then use `oss-launch` for polish, with one substitution: its Phase 4 (`gh repo create --source . --push`) publishes your history, so publish the export (step 8) instead.

## Principles

- **Public is permanent.** History, Actions logs, forks, clones and cached views keep everything. Rewriting history leaves copies behind. A fresh repo from an export is the only clean cut, so the private repo never goes public.
- **The artifact is not the source.** A clean tree builds a binary with debug paths, a signature with a legal name, and a bundle with no license notices. Audit what ships.
- **Scanners find credentials, not you.** gitleaks and trufflehog miss names, hostnames, employers, private project names. Build a battery of your own identifiers.
- **Identity decisions are the human's.** Surface them in step 1, with a default and what each blocks.
- **Every lane returns a checklist** of the checks it ran, including those that found nothing. The checklists are what this skill grows from.

## Steps

Each step ends on its completion criterion; do not start the next without it.

1. **Plan.** Write the plan with `references/plan-template.md`: decisions already made, human decisions listed separately (each with a default and the step it blocks), ground rules for every lane, definition of done. The plan names private identifiers, so it stays private and is excluded from the export. Run the name-clash check now (trademark classes 9 and 42, the `.com`, app stores, the GitHub slug), not after the review: a late rename redoes the art, the docs and the gate. Then send the human the open decisions in one message. *Done when* every human decision is either answered or has a stated default and a blocked step.

2. **Build the export and audit tooling** before any review, so every later fix is audited by the same machine. Pattern, pitfalls and a rebuild recipe: `references/export-and-audit.md`. *Done when* the tool runs end to end on the current HEAD, fails on a deliberately planted leak, and passes on the clean tree.

3. **Readiness pass: parallel review lanes** (`references/review-lanes.md` has briefs, model choices and the finding format). Five lanes, one checklist file each:
   - privacy and secrets, including built artifacts: `references/checklist-privacy-secrets.md`
   - security from a stranger-user's threat model: `references/checklist-security.md`
   - licensing and legal: `references/checklist-licensing-legal.md`
   - stranger's-eye code and product: `references/checklist-stranger-experience.md`
   - best-practice research from primary sources: `references/sources.md` lists the starting set
   Lanes review the real export and a real build, not only the working tree. *Done when* every lane has returned a ranked findings list (blocker, major, minor, nit; file:line; fix), the checklist of checks it ran, and a "not verified" list.

4. **Triage and fix.** Merge the lanes' findings: duplicates collapse (two lanes found the private project name, three found the `.gitignore`). Sort into fix-now, human-decision, and consciously-deferred. Cluster fix lanes by file ownership so no two edit the same file; send follow-ups to the same worker rather than starting a new one. Every new test is proved by breaking the guarded code and watching it fail. Merge, then run the full gate once on the integrated candidate. *Done when* every blocker and major is fixed, decided, or deferred with the human's name on the deferral.

5. **Audit the release artifacts.** Build the shipping artifact exactly as release will, then audit the binary, bundle, installer image and update feed: `references/release-artifacts.md`. macOS specifics (strip, codesign identity, notarization, Sparkle): `references/macos-app.md`. Rebuild and re-sign after each fix; any artifact built before the fix is discarded. *Done when* the artifact audit passes on the final installer image and the human has read the identity line the signature discloses.

6. **Final independent gate.** A fresh reviewer, in a fresh context, on a different model from the fix lanes, reviews the exact export that will be published against the plan's definition of done. If any check fails, fix the source and re-export from scratch; a second commit on top would keep the leak in public history. *Done when* the gate reviewer reports no blocker or major on the export commit that will be pushed.

7. **Stranger test.** On an account that has never run the project, install from the public path (not the build machine), follow the README, and complete the first real use. *Done when* the human, or a reviewer who has not seen the code, has done it and what confused them is fixed.

8. **Publish** (`references/publish.md`): new public repo from the export, branch ruleset, vulnerability reporting, secret scanning verified in Settings, release with source line and checksums. Publishing is human-authorized; ask before each push. *Done when* the public clone builds, the public download passes the stranger test, and the Publish lessons section has been filled.

## Human-only decisions (surface in step 1)

Signing identity disclosed by code signing; name clash; bundle id and domain permanence; employer or school IP (work email in history); copyright holder string; GPL `-only` vs `-or-later` (upstream grants can force it); code of conduct and issue templates; platform floor; whether AI-provider terms are acceptable for bring-your-own-key features. Details and defaults: `references/plan-template.md`.

## Gotchas that cost time

- Audit tools skip binary files by default; the first release audit found two blockers the source audit had passed.
- A vocabulary battery that skips ordinary-English terms also skips given names (they are in the dictionary). Check capitalized terms always, and report skipped terms by hashed id.
- A battery tool's own error message can quote the term into the log. Run it bytewise, discard stderr, and fail on a nonzero exit.
- The public repo URL contains your handle and trips the battery in source and in the binary. Carve out that exact URL and nothing broader.
- Public commit dates carry your timezone offset; use UTC. Stage files by name so a Finder `.DS_Store` never rides along.
- The private `.gitignore`, `AGENTS.md`/`CLAUDE.md`, tool state directories and comments describe your workflow. Write a public `.gitignore` in the export and rewrite agent files for strangers.
- Keep the private vocabulary out of reviewers' contexts; they see ids and counts. A reviewer told not to read those files cannot say whether skipped terms match, so provide a report-only pass.
- GitHub's own docs disagree on whether push protection is on for public repos. Look in Settings after publishing.
- A security fix can change behavior users notice (for example, a safety check that holds an action whenever any app has secure input on). List such changes in the release notes.

## Publish lessons

Lessons from a first publish (renamed late) are in `references/publish.md` under "Publish lessons". The two that change the order of work: run the name-clash check in step 1, because a late rename redoes the art, the docs and the gate review; and give any data migration that a rename forces its own review lane.
