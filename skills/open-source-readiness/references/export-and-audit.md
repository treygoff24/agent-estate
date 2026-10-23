# Export and audit tooling

The pattern: publish a fresh repo from an **export** of a chosen commit, after an audit that a human or script can rerun. Rebuild it for each project; the layout below is a worked example.

Worked example, all under `<project>/scripts/`:
- `export.sh`: archive, exclude, audit, optional tests, optional commit.
- `export-exclude.txt`: paths left out of the export.
- `audit-battery.txt`: private identifiers, one per line, shared by both audits.
- `release-audit.sh`: audits a built `.app` or `.dmg` and its update feed.

## Why not flip or scrub

Flipping the private repo public publishes Actions logs, all history, and resets stars. Rewriting history (`git-filter-repo --sensitive-data-removal`, then force-push) leaves commits reachable in forks, clones, cached SHA views and PR refs until GitHub Support purges them. A fresh export drops commit messages, branch and tag names, and author metadata too. The cost is losing blame and bisect; the private repo keeps them. A secret that ever reached a public repo is burned: rotate it, do not scrub it.

## Export steps

1. Refuse a destination that exists and is non-empty.
2. `git archive <commit> | tar -x -C <dest>`. Never `.git`, `--mirror` or `--all`. The commit is an explicit argument so the export is reproducible.
3. Delete every path in the exclude list, read from the same commit. Entries are repo-relative; a trailing slash means a directory. Abort on entries that are absolute, empty, or contain `..`. The exclude list, the export script, the audit scripts, the battery and the plan are all in the list.
4. Write a generated public `.gitignore` (build outputs and OS litter only) over the private one, which names private tooling.
5. Print the sorted file list. A human reads it against the expected tree before anything is published.
6. Run the audit (below). Every check runs; the script prints a summary and exits nonzero if any failed.
7. `--commit`: only after a passing audit, `git init -b main` in the destination and make one commit.
   - Identity per command (`git -c user.name=... -c user.email=...`), never `git config`. Use the ID-form no-reply address `<id>+<user>@users.noreply.github.com`.
   - Author and committer dates in UTC (`+0000`) so the commit does not reveal your timezone.
   - Add files by name (`find -print0 | xargs -0 git add --`), excluding `.DS_Store`.

## Audit checks

- **gitleaks** on the export directory, and on the new repo's history once committed. Archives are only traversed if told: `--max-archive-depth 3 --max-decode-depth 3`. A second scanner that verifies liveness (trufflehog; AGPL, so run it, do not vendor it) is worthwhile. Treat both as one layer.
- **Grep battery.** Case-insensitive fixed strings over every text file; print `file:line:term` (the terms are not secret). Contents: legal name, username, personal and work emails and email domains, employer and former-employer names, hostnames, tailnet or internal domains, home-directory path, internal tool and agent names, private project names, private repo names. Add terms as reviews find new ones (for example a private project name that two lanes found independently). Carve out the exact public repo URL, stripped before matching, bounded so `repo-archive` still matches.
- **Vocabulary battery** for the maintainer's personal vocabulary (names of people, clients, places that live in a custom dictionary or replacement files). Design points, each learned from a failure:
  - Terms live only in temp files removed on exit and are never printed. Report a hashed id (first 10 hex of sha256 of the lowercased term), match count and `file:line`.
  - The noise filter skips ordinary English (every word in `/usr/share/dict/words`) and terms under 4 characters, except that capitalized terms are always checked, because given names are in that dictionary. Terms under 4 characters match as whole words.
  - List skipped terms by id and count so the skipping is visible; add a report-only pass over them.
  - Allowlist hashed ids in a file outside the repo (comments allowed). Allowlisted ids are counted, not failed; print their file:line too so a reviewer can see where they match.
  - Strict inside source, tests, README and docs: a non-allowed id matching there fails. Elsewhere, report only.
  - Run the filter under `LC_ALL=C` with stderr discarded and fail the audit if it exits nonzero: an awk error on an odd byte sequence once quoted a term into the log.
  - Expect new strictness to match public words (a product name that is also a vocabulary term). The human reviews the ids and allowlists them; the agent does not edit the allowlist.
- **Clean build.** Copy the export to a temp directory, `git init`, commit, and build (and optionally run the full tests there). This catches files that only existed untracked or ignored in the private tree.
- **Metadata of non-text files.** Image chunks (PNG tEXt/iTXt/eXIf), audio chunks, icon info, extended attributes. A first-draft script may not cover these: have the privacy lane parse them by hand, or add them to the script or the checklist.

## Audit the audit

An audit that has never failed proves nothing. Before trusting a tool, give it known-bad input and watch it fail: mutation-prove a release audit against an unstripped binary, a resource file containing names, an appcast pointing at the archive repo, and a DMG built from the good app (which must pass). Also state what each check does not see: compressed or UTF-16 strings, scanners that stop at archive depth 0, text the battery cannot name.

## Rebuilding for another project

1. Write the exclude list: private plan and notes, agent state directories, tracked-if-present tool files, internal research, the tooling itself.
2. Write the battery from `git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`, `rg` for your usernames and hostnames, and the private project list. Keep it outside the export; keep it out of reviewers' contexts unless they need it.
3. Decide what counts as the maintainer's personal vocabulary for this project and wire the vocabulary battery, or state that there is none.
4. Add build and test commands in a clean copy.
5. Write the artifact audit (`release-artifacts.md`) and call it from the release script after the build and again on the final installer.
6. Mutation-prove both audits.
