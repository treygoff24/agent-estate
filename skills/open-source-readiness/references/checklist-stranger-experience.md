# Checklist: the stranger's eye

Review the code and product as someone who is not the maintainer, on a machine that is not the maintainer's, in a language and locale that may not be the maintainer's. A stranger lane typically finds a blocker or two (for example, a default path that silently deleted words in German), several majors, and a long tail. Probe rather than read wherever you can: run the code on foreign input, lower the platform floor and see what breaks.

## Follow the README as written

- Install: the download name in the README matches what the release script produces (`App.dmg` versus `App-<version>.dmg`), and the tag format the update feed assumes (`v<version>` exactly) is stated and checked.
- Build from source on a clean account: toolchain version named exactly (not "a current Xcode"), platform and architecture stated, first build warning-free, tests pass with no maintainer data.
- Every advertised advanced feature can be followed from the README alone. A common miss: a local model advertised with no config block, no model download steps and a hard-coded package-manager path. Either write the full recipe or drop the feature from the first release.
- Quick start and first-run flow: denied permissions are handled at first run and after the user later revokes them; errors say the cause and the fix ("Accessibility is not granted: open Settings > Privacy..."), in plain words, not internal jargon.
- Contributing: how to run tests, which developer flags exist, what a fork must change (update feed URL, update-signing key, bundle id, keychain service) so a fork does not poll your feed or reject its own updates.

## Hidden maintainer assumptions

- Hard-coded paths (`/opt/homebrew/...`, the maintainer's home layout); use a lookup.
- Maintainer's services touched by every user's copy: launch jobs managed at every launch, polling timers re-reading config every second. Gate on the feature being in use; react to changes instead of polling.
- Starter config and comments written to the maintainer's workflow; code whose reasoning is about the maintainer (a migration for installs only they have); comments citing private tests, benchmarks or projects.
- Dead or stale code: tests-only fixtures in production types, comments describing engines you no longer ship.
- Undocumented flags in the release binary (see `checklist-security.md`).

## Non-English and non-default environments

Probe the default path with a foreign locale; the default path is where the stranger lives.
- Text-processing defaults (filler removal, normalization, replacement rules) applied to every language: an English filler-word filter can delete German "um" and hyphenated prefixes in the default mode. Gate language-specific rules on the language, and test with a case that fails without the gate.
- Defaults pinned to English (cloud modes, offline fallback); the fallback built from the wrong component's language; bare language codes mapping to an unexpected regional variant (`en` resolved to South African English). Probe the platform's locale resolution with bare codes and with unsupported ones.
- Unsupported languages silently becoming the default language, which makes the "unsupported" UI state unreachable and its advice wrong. Keep unsupported a visible state.
- Keyboard layouts, right-to-left text, date and number formats, if the project touches them.

## Deployment floor

- Lower the minimum platform version in the manifest and compile: the errors list which APIs truly need the floor. A platform floor often rests on only a couple of API families; gating them with availability checks and fallbacks can open the previous major version. Then decide the floor as a product matter and, if it stays, say why in the README. Untested behavior on the lower version stays in "not verified".
- Architecture (universal or arm64-only) matches the floor; check with `lipo -archs` and the binary's minimum version.
- A CI runner exists for the floor; confirm the label and image before promising CI.

## Tests and CI

- Tests are hermetic: temp directories and named suites only; no real keychain, network, home directory or default user-defaults; they need only tools every machine has. `rg` the tests for `HOME`, `Keychain`, `URLSession`, `.standard`. Tests that need a downloaded model skip with a reason and never count as passed.
- No CI means an outside pull request arrives with no signal. Add a workflow on the project's platform: build, test, no secrets, read-only permissions. Wall-clock assertions (`< 5 s`) can flake on shared runners; list them.
- Release scripts run only on the maintainer's machine, never in CI.

## Release flow a maintainer will hit next

- Version and build number: single source; nothing checks that the build number increased until a check is added (see `checklist-security.md`).
- The update feed is served from latest release assets; a prerelease or draft is never offered. Release notes in the feed.
- Document the release procedure for the next maintainer, including the 0.1.1 sequence.

## Not verifiable by reading

List what you did not launch: behavior with a permission denied after first run, launch-job side effects, keychain prompts after rebuilds, other floor-version failures.
