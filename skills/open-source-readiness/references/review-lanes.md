# Review lanes

Five parallel reviewers, each with one scope, one checklist file, and one output format. Run them after the export tooling exists (step 2) so each can run the export and a real build itself.

## Lanes

| Lane | Scope | Model | Checklist |
|---|---|---|---|
| Privacy and secrets | The export, the built artifact, logs the app writes at runtime, images and other binaries | Strongest available | `checklist-privacy-secrets.md` |
| Security | The code and release process from a stranger-user's threat model | A different model family from the one that wrote the code | `checklist-security.md` |
| Licensing and legal | License text, upstream provenance, bundled notices, in-app legal notices, name and trademark, third-party terms | Strong, with web access | `checklist-licensing-legal.md` |
| Stranger's eye | Code and product as someone who is not the maintainer meets them | Strongest available | `checklist-stranger-experience.md` |
| Best-practice research | Primary sources on what a small solo-maintained project should ship | Strong, with web access | `sources.md` |

Why these models: privacy and stranger review need the judgment to notice what does not belong or confuses a newcomer, which is where weaker reviewers pass. Security gets a different family because the author's blind spots correlate with the author's model. For example, use a Codex lane for security and fix what it finds with Claude workers.

## Brief for every lane

Give each lane, in this order:

1. The goal in one sentence and the stranger it protects.
2. What to run: the export command and a real build of the artifact, with output paths.
3. Its checklist file to start from, and permission to go beyond it.
4. What is off limits (private vocabulary files, the maintainer's real data) and what it gets instead (ids, counts).
5. The output format (below).
6. A reminder that "I checked X and found nothing" is a result, and that claims about what it did not run are required.

## Output format

- **Summary:** what ran, with counts (files exported, tests passed, terms loaded); what was clean.
- **Findings, ranked:** blocker, major, minor, nit. Each: file and line, what is wrong with evidence (the command and its output), why a stranger cares, and the fix. A blocker blocks any upload; a major blocks the first release.
- **Checklist:** every check run, numbered, including those that found nothing. Future passes start here.
- **Not verified:** what it did not launch, did not read, could not fetch (gnu.org returned 403 to every fetch; the lane used archive copies and said so).
- **Decisions for the human**, separated from code findings.

The research lane returns the same shape with tiers (E essential, R recommended, O optional), a source key per row, and *(inference)* marked on anything that is the lane's judgment rather than a source's claim. It should also push back on the plan where sources disagree with it. A research lane can reverse a plan's "no code of conduct or templates" decision and catch GitHub's docs contradicting each other on push protection.

## Triage

- Merge all lists into one ranked list. Deduplicate across lanes and keep the strongest evidence.
- Sort each item: fix now, human decision, deferred (with the human's name on it).
- Cluster the fixes into lanes by file ownership. Example clusters: engine and app-shell code and tests; scripts, CI and export tooling; notices, About pane and README. Two lanes never edit one file.
- Send follow-ups to the worker that owns the cluster instead of launching a new one; it already holds the files.
- Each fix needs a test proved red by mutation, or an honest "not unit-testable" with what was checked by hand.
- Merge by hand, then run the full gate once on the integrated candidate. Re-run the export audit on the merged HEAD.
- A fix changes what the audit should look for: add the term or check that would have caught it.

## Final gate lane

Run after the fixes and the artifact audit, on a model different from the fix lanes, in a fresh context. Brief it with the plan's definition of done and the exact export commit. It reviews the export directory that will be pushed, not the working tree. Majors get fixed and the export is rebuilt from scratch.
