# Auditing release artifacts

A source export can pass every check while the notarized installer still leaks the maintainer's legal name and home directory. The release script builds from the private checkout, and both source batteries skip binary files. The artifact audit exists to close that gap. Worked example: `<project>/scripts/release-audit.sh`.

## The rule

Audit the file a stranger downloads, mounted or unpacked exactly as they get it, with the same battery as the source. Audit the app after the build and again on the final installer and update feed, since packaging adds files. Rebuild after every fix; an artifact built before a fix is discarded and never uploaded.

Build the release from the export checkout, or prove the trees equal (`git diff --stat` between the private commit and the export on included paths), so the public source tag corresponds to the binary. This is a recommendation; many first release scripts build from the private checkout.

## What to scan

- Every file in the bundle or image: bytes, case-insensitive fixed strings from the battery (`grep -a -F -f`), binaries included. Splitting a binary at its code-signature blob lets you judge a hit in the signature separately from a hit in code.
- Compiler debug maps and embedded paths. A `strings`-style search misses the linker's debug map; use the platform's symbol dumper (`nm -ap` on Mach-O, then look for object and source entries) and `grep -a '/Users/'` or your home prefix. A release binary can carry dozens of object-file and source-directory entries naming the maintainer's home and project layout. Other ecosystems have the same class: Go `-trimpath`, Rust `--remap-path-prefix`, panic and assertion strings with source paths, `#filePath`-style literals, sourcemaps, bundled `.dSYM` or `.pdb` files.
- Identity in the signature or metadata (code-signing authority, team id, package author fields, PE/Mach-O version info). It cannot be scripted away; print it for a human to read and accept as INFO, keeping the same term anywhere else in the artifact a failure.
- Resources, plists and manifests: names, hostnames, paths. Convert binary plists to XML before searching.
- The update feed or manifest: URLs must point at the public repo, not the archive.
- Image, audio and icon metadata in the bundle.
- The public repo URL contains your handle: carve out that exact URL (bounded so a similarly named archive repo still matches) in source and binary scans.
- Short battery terms (under 4 characters) match as whole words, or they hit ordinary words in bundled third-party localizations.

## What to confirm is present

- LICENSE, NOTICE and the third-party license files inside the bundle; LICENSE and NOTICE at the installer root; the copyright string in package metadata.
- A human-readable About/legal view in the app (licensing checklist).
- Architecture and minimum OS version of every executable (`lipo -archs`, build version load command).
- The checksum file generated from the final installer bytes.

## Fixing leaks

- Strip debug info from the shipped executable after copying it into the bundle and before signing (`strip -S` on macOS; run `dsymutil` first if you want a private symbol file). Global symbols stay for crash reports. In practice: many `/Users/` entries before, none after, and a smaller binary.
- Keep language-level fixes where they exist: Swift 6 language mode makes `#file` concise (`Module/File.swift`); `#filePath` always embeds the absolute path; `-file-prefix-map` did not rewrite those literals in a probe.
- Wire the audit into the release script after the build and on the final installer, and make it skip cleanly when the audit script is absent, as in the public export.

## Prove the audit

Test it on known-bad input: an unstripped binary must fail; a resource file containing a battery term must fail; a feed pointing at the archive repo must fail; the good artifact must pass; the identity exemption must be INFO only in the signature. Run it once on a third-party signed app to see it detect real leaks. State the audit's limits (compressed or UTF-16 strings are not searched).

## Per-platform specifics

macOS: `macos-app.md`. For another platform, carry over the shape: build as release does, scan every file and the debug map, read the identity line, confirm notices, rebuild after fixes.
