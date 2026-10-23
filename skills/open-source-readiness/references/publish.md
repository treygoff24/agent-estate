# Publish

Publishing is human-authorized: ask before the push, before the release, and before each settings change that is not reversible. One authorization is one action. Start only when the final gate review has passed on the exact export commit (steps 1-7 of `SKILL.md`).

## Before the push

- The export commit is the one the gate reviewed: confirm the hash. One commit, ID-form no-reply author, UTC dates.
- `git for-each-ref` on the export repo shows only `main`; `git tag -l` is empty. Tag the first release on the public repo; do not import private tags.
- Rename the old private repo to `<name>-archive` (stay private) so the name and redirects are free for the new one.
- Community files are in the export: README, LICENSE, NOTICE, CONTRIBUTING, SECURITY, code of conduct, issue forms with `blank_issues_enabled: false` and contact links (warn "do not paste private text or audio"), PR template.
- Account hygiene confirmed: email privacy and block-pushes-that-expose-email are on.

## Create the repo and set it up

1. Create the new public repo from the export directory and push `main`.
2. **Ruleset on the default branch** blocking force-push and deletion. A solo maintainer takes this tier only: no required approvals (that would block self-merge), and no required checks until CI is green on main. Bypass lists exist for rulesets; branch protection bypass exists only on organization repos.
3. **Private vulnerability reporting** on (Settings > Advanced Security); point SECURITY.md at it.
4. **Secret scanning and push protection**: open Settings and verify both are on. GitHub's docs disagree about push protection's default on public repos; do not assume.
5. **Dependabot alerts and security updates** on (alerts are off by default); `dependabot.yml` for actions and the language ecosystem.
6. **Actions**: read-only default token; "Require approval for all external contributors"; optionally require actions pinned to full SHAs. Watch the first CI run to green.
7. **Immutable releases**: enable before the first release (it applies to future releases only). Then create releases as drafts, attach every asset, then publish.
8. Description, website, topics (lowercase, digits, hyphens, at most 50 characters each, at most 20), social preview image (PNG/JPG/GIF under 1 MB, 1280x640 best; upload is a settings-UI action; strip its metadata first). Turn off wiki, projects and pages if unused.

## The release

- Tag `vX.Y.Z` exactly as the update feed and release script assume; the tag points at the commit the binary was built from.
- Human-written release notes (not raw `git log`), with the line `Source: tag vX.Y.Z of this repository` (GPL source offer) and any user-visible behavior changes from security fixes.
- Assets: the installer, `SHA256SUMS` made from the final installer (`shasum -a 256`), the update feed (appcast) built for the final installer. With immutable releases on, the feed is attached to the draft before publishing; it cannot be replaced afterwards.
- Mark prereleases as prereleases so `latest` does not move.
- Publish the draft last.

## Verify as a stranger

- Fresh clone of the public repo on a clean account: follow the README, build, run the tests.
- Download the installer from the public URL in a browser (quarantined), pass Gatekeeper-equivalent checks, install, complete the first use.
- Update from an old build through the public feed.
- The repo's `/community` page is green for the files you chose; the Security tab shows the policy and the report button.
- Announce last, after the install and update tests pass, with one home URL.

## After

Archive a short handoff for the next maintainer: release procedure, where keys live, the triage target written in CONTRIBUTING (OpenSSF: acknowledge most bug reports; respond to vulnerability reports within 14 days).

## Publish lessons

From a first public release of a macOS app, in the order they cost time:

1. **Check the name for clashes in step 1, not at the end.** A live product with the same name and a `.com` can turn up after the readiness pass and force a late rename. That means redoing the icon, banner, screenshots and docs, a module rename across the codebase, and a fresh gate review. Run a trademark search (USPTO, the software classes 9 and 42), the `.com` and app-name search, and a check that `github.com/<you>/<name>` is free before step 2. Only collision-checked candidates go to the human.
2. **A rename adds a data-migration surface, and that surface needs its own review.** Moving the owner's existing data folders and config to the new names was the riskiest code in the release. The first review of it found a blocker (a second running copy of the old build could have its folders moved under it) and two majors (a failed migration left the app running on empty data; login-item re-registration lost its intent on failure). Give migration code a dedicated reviewer, keep the bundle id if you can (it keeps the Keychain, preferences and log subsystem untouched), and stop the launch on any migration conflict rather than carrying on.
3. **Build the release artifact from the export checkout, not the private one,** so the public tag is the exact source of the shipped binary. Release scripts that call private audit tools skip them in the export; run the private artifact audit on the result afterwards.
4. **The vocabulary battery matches substrings inside identifiers.** `launchd` inside `LaunchDelegate`-style names tripped it. Allowlist public identifiers by hashed id instead of loosening the matcher.
5. **Some agent sandboxes cannot take a `/tmp` working directory** unless the session itself runs under `/tmp`. Give them absolute paths to the export instead.
6. **Enable immutable releases before creating the first draft.** Turning it on after publishing leaves the first release mutable. Immutability then binds the next release: attach the appcast to the draft, because it cannot be replaced after publishing.
7. **Everything except the social preview is scriptable.** `gh repo create --source <export> --remote github --push`, `PUT private-vulnerability-reporting`, `vulnerability-alerts`, `automated-security-fixes`, `immutable-releases`, `actions/permissions/workflow` (`default_workflow_permissions=read`), `actions/permissions/fork-pr-contributor-approval` (`all_external_contributors`), `POST rulesets` (`deletion` + `non_fast_forward` on `~DEFAULT_BRANCH`), `gh repo edit --enable-discussions --enable-wiki=false --enable-projects=false --add-topic …`. `GET repos/<r>` → `security_and_analysis` showed secret scanning and push protection already on for a new public repo. The social preview image is a Settings-UI upload only, so leave it to the human.
8. **The community profile reports `issue_template: false` for YAML issue forms**, even while it scores the repo 100%. That is a detection quirk, not a missing file.
9. **Verify the public download by hash, not by status code.** `curl -sL …/releases/latest/download/appcast.xml | shasum -a 256` and the same for the installer both matched the local build. The draft's asset `digest` fields from `gh release view --json assets` are a cheaper first check.
10. **Labels before the first issue.** Issue forms silently drop `labels:` that don't exist on the repo, so run the label sync right after the push. A sync script that defaults to "the checkout's repo" fails in a clone whose only remote isn't GitHub; pass `-R`.
