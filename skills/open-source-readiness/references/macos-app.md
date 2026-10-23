# macOS app specifics

Read when the project ships a macOS app: signing, notarization, Sparkle updates, and the places a Mac build leaks. Sources are Apple and Sparkle documentation (see `sources.md`); items marked *(inference)* are judgment, *(probe)* was checked on a recent Mac toolchain.

## Code-signing identity discloses you

- A Developer ID Application signature for an individual account embeds the legal name and Team ID, readable by anyone from the DMG (`codesign -dvv` shows `Authority=` and `TeamIdentifier=`). No script removes them. A battery that lists both strings as private will flag every signed release.
- Options: accept and say so in the plan (take the strings out of the battery's failing set, keep them visible as INFO in the artifact audit), or enroll as an organization (needs a D-U-N-S number) and sign under its name. Decide before the first upload: Sparkle updates and OS permission grants depend on the identity staying the same.
- Only the Account Holder can create a Developer ID certificate; it is valid five years. The private key lives in the Mac's keychain: back it up as an encrypted `.p12` outside the repo and outside cloud sync *(inference)*. Apple cannot revoke from the portal; revocation goes by email to `product-security@apple.com` and blocks installs of everything signed with it.

## Strip before signing

Release binaries built with SwiftPM keep the linker's debug map: `nm -ap <AppBinary> | grep -E ' (OSO|SO) /'` showed object and source paths under the maintainer's home. Run `strip -S` on the executable after copying it into the bundle and before any `codesign` (global symbols stay for crash reports); `dsymutil` first if you want a private dSYM. `-debug-prefix-map` alone does not rewrite the object paths; `-Xlinker -oso_prefix` would too (untested). *(probe)*

`#file` in Swift 6 language mode (tools-version 6.x packages) is concise; in Swift 5 mode and for every `#filePath` the binary embeds the absolute path. `-file-prefix-map` did not remap those literals in a probe. Check with `strings -a App.app/Contents/MacOS/* | rg -i '/Users/|<username>'` and over every Mach-O in `Contents/Frameworks`, and use `nm -ap` for the debug map, which `strings` misses.

## Sign, notarize, staple

- Two signing modes in one build script: Developer ID with hardened runtime and secure timestamp for releases (selected by an environment variable naming the identity), ad hoc without hardened runtime for contributors. Hardened runtime library validation refuses an ad-hoc-signed embedded framework, so contributor builds must omit it. Document both in the README.
- Sign inside-out: embedded helpers and XPC services, then the framework (copy with `ditto` so symlinks survive), then the app, then the DMG.
- `xcrun notarytool submit X.dmg --keychain-profile <name> --wait`; require `Accepted`; read `notarytool log <id>` even on success. `altool` is no longer accepted. Limit 75 submissions a day.
- `xcrun notarytool store-credentials` keeps an app-specific password or App Store Connect API key in the keychain; the repo and scripts hold only the profile name. Credentials never pass through an agent or a log.
- Notarization prerequisites: Developer ID cert (not ad hoc), hardened runtime, secure timestamp, no `get-task-allow` entitlement, XML entitlements. Checks: `codesign -vvv --deep --strict`, `codesign -dvv` (timestamp), `codesign -d --entitlements :-`.
- Staple and validate: `xcrun stapler staple X.dmg && xcrun stapler validate X.dmg`.
- Gatekeeper on a clean machine: test a quarantined download from the public URL in a fresh user account or VM; the build Mac has local trust and no quarantine.
- Pre-release Apple SDK or Xcode: the Xcode license forbids posting screenshots of pre-release Apple software; confirm macOS and Xcode are released before publishing.

## Bundle id permanence

The bundle id is also the log subsystem, the keychain service and the prefix of launch-agent labels in a typical app. Changing it after release resets users' Microphone and Accessibility grants and orphans saved credentials. Decide it before 0.1.0, as a public identifier tied to your domain.

Rebuilding an ad-hoc copy changes its signature, so TCC grants (microphone, accessibility) reset and keychain prompts may return. Tell contributors in the README. Never run a second copy of the app under the maintainer's account while testing: it shares keychain items, launch agents, history database and hotkey. Use a throwaway macOS user account for every full-app run.

## Notices and legal in the bundle

Copy LICENSE, NOTICE and each embedded framework's LICENSE into `Contents/Resources`; put LICENSE and NOTICE at the DMG root; set `NSHumanReadableCopyright` in Info.plist; show the legal notice in the About window. Detail: `checklist-licensing-legal.md`.

## Sparkle updates

- `generate_keys` stores the EdDSA private key in the login keychain and prints `SUPublicEDKey` for Info.plist. Export it (`-x`) to an encrypted backup outside the repo and the web host; keys vanish if the keychain or system is erased. If the key is lost and the app is Developer ID signed, you can still rotate: change either the certificate or the EdDSA key in one update, not both.
- `SUFeedURL` points at an HTTPS feed. On GitHub: `https://github.com/<owner>/<repo>/releases/latest/download/appcast.xml`. Two traps: with immutable releases the appcast cannot be replaced after publish, so attach the final appcast to the draft first; and `latest` excludes prereleases and drafts, so a beta never moves the feed. The release tag must equal what the appcast's download URL assumes (`v<version>`).
- Build number (`CFBundleVersion`) is what Sparkle compares and must increase each release; check it against the live feed in the release script.
- Sign archives with the keychain or `--ed-key-file -` (stdin); `-s` as an argument is deprecated as insecure. Optionally `SURequireSignedFeed` and `SUVerifyUpdateBeforeExtraction`. Keep Sparkle current.
- Verify in the release script that the archive's signature checks against `SUPublicEDKey` from the built app's Info.plist (`sign_update --verify` checks the private key you give it, so it cannot do this).
- Test the update end to end twice: against a local appcast, then once against the public feed from an old build.
- Forks: `SUFeedURL`, `SUPublicEDKey`, bundle id and keychain service must change; say so in CONTRIBUTING.
- Sparkle's LICENSE (multi-license, named holders) ships with the app.

## Other Mac leaks

- Unified logging: values interpolated with `privacy: .public` land in `log show` and sysdiagnose; make user-derived values `.private`.
- Launch agents or launchctl calls made on behalf of the maintainer's helpers at every user's launch.
- Entitlements and usage strings honest about audio leaving the machine in cloud modes.
- CI: a hosted macOS runner image must exist for the deployment floor (a hosted image for a brand-new SDK may be a preview or missing; confirm the label before promising CI). Build, test, ad-hoc app build; never the release script.
