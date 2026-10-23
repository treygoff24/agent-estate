# Checklist: privacy and secrets

Run against the export directory and a built artifact. Where an item caught something on a past project, it says what. Items that found nothing stay in the list: they are cheap and the next project may not be clean.

## History and identity

- `git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`: any personal or employer address means a fresh export, not a scrub. (Typical: employer-domain emails in history.)
- Public commit: ID-form no-reply author, UTC dates, one commit, no private tags or refs (`git for-each-ref` on the new repo shows only intended refs).
- GitHub account settings: email privacy on, and block pushes that expose the email.
- Commit hygiene in the export tool: files added by name; no `.DS_Store`.
- Rotate any secret that ever sat in committed history; do not rely on removal.

## Secrets

- gitleaks on the export directory (with archive and decode depth) and on the new repo; a verifying scanner as a second layer.
- List archives, installers, keys and certificates in the tree (`*.zip *.dmg *.xcarchive *.tar* *.p12 *.p8 *.cer *.mobileprovision *.pem`) and justify each.
- Metadata and config: lockfiles or submodules pointing at private URLs; plists, entitlements and project files with team ids and bundle ids on a personal domain (a team id is public in every signature, so treat it as identifying, not secret); scripts naming hostnames, tailnets, home directories; CI files; agent state directories and transcripts.
- Scripts that source credentials from a personal path. (For example, an install script that sourced a keys file from the maintainer's profile; it should read only documented environment variables.)

## Personal content in the tree

- Grep battery over text, plist and JSON for names, handles, employers, domains, home paths. Review comments for rulings, incidents, "as in <private project>", test counts from private benchmarks.
- Private project names (for example, files that name another private project; independent lanes tend to find the same ones).
- Personal habits written as design premises (a design doc said "most often <my terminal> in full screen"). Make them generic.
- Vocabulary and replacement files, configs, examples: diff the examples against the real files.
- Test fixtures: real audio, transcripts, screenshots, recordings. Voice is biometric. Use synthetic data (`say` plus `afconvert`) and name test people with obviously fake names; check them against the vocabulary battery.
- Screenshots at 100%: window titles, menu bar, Dock, notifications, wallpaper, usernames, paths. Use a clean demo account.
- Image, audio and icon metadata: PNG chunks, EXIF/XMP, WAV `LIST`, ICNS info, extended attributes (`xattr -l`). `exiftool -all=` or re-export to strip. They are often clean (screenshot software tags only); verify, do not assume.
- Starter configs and defaults written into every user's home: wording addressed to the maintainer's workflow ("agents edit this file"), maintainer-specific paths, model ids.
- Links in README and docs: every one resolves to an included file; nothing in the export names an excluded file.

## Tool and workflow leakage

- The private `.gitignore` reveals issue trackers, agent tools, a private notes folder with an explanatory comment. Ship a generated minimal `.gitignore`; move personal lines to `.git/info/exclude` in the private repo.
- `AGENTS.md`, `CLAUDE.md`, contributor docs: no private paths, hostnames, internal tools, task-tracker conventions, credential locations. Keep per-tool state directories excluded.
- Scripts in the export should not need private tools (`testrun`, the issue tracker, the audit tooling).

## Runtime logging

- Log statements with public privacy markers: any user content, device name, path, bundle id of the app the user was working in, or user-chosen config string at `.public` becomes an activity trail readable by any admin and in system diagnostics. (For example, the bundle id of the app the user pasted into, logged public on every action.) Make user-derived values private, log fixed codes, and keep error text private.
- Provider error bodies and transcripts never go to public logs.

## Built artifact

Do these on the real build; `release-artifacts.md` has the detail.
- Debug-map paths and `/Users/<you>` in the binary.
- Signing identity (legal name, team id) in the signature.
- Home paths and names in bundled resources, plists, appcast.
- The public repo URL tripping the battery in the binary: carve out the exact URL.

## Decisions to surface

Signing identity; bundle id and domain; whether the Developer team name is acceptable to publish; employer clearance.
