# Checklist: licensing and legal

From a licensing lane on a GPL-3.0 app with a few files adapted from a GPL-3.0 upstream, and a research lane. The reviewers were not lawyers; items about names and trademarks are risk flags, not clearance. Examples are GPL-specific where the license is; the provenance and notice mechanics apply to any license.

## The license itself

- `LICENSE` at the repo root is the canonical text, unmodified. Diff it against two independent sources (choosealicense's text, the SPDX `GPL-3.0-only` text, a GCC mirror's COPYING3). A hand-copied file often differs by a blank line or `http`/`https` links.
- Choose the variant on purpose: `-only` versus `-or-later`. Adapted code whose upstream grants "version 3" with no later-version clause forces `-only` for the combined work. Say it everywhere it appears (README, NOTICE, About pane, CONTRIBUTING) and add an SPDX header line to each source file (`SPDX-License-Identifier`, `SPDX-FileCopyrightText`). A README statement is legally sufficient per the FSF FAQ, but it separates from the code easily.
- No license means no permission. A public repo without one is not open source.

## Upstream provenance

- List every adapted file, its upstream path and tag, and what you changed. Each adapted file's header names those and carries a modification date (GPL §5(a) needs one; a fresh single-commit repo cannot supply it from history). An unmodified copy needs no change notice.
- Name upstream's copyright holders. If upstream names none, name its principal authors and record where it states its license. An upstream's LICENSE file can be a truncation (GitHub reports NOASSERTION) with the grant resting on its README. Record that in NOTICE.
- Line-level similarity: compare every file against the upstream tree at the cited tag; read the likely paraphrase candidates by hand, since exact-line matching cannot see paraphrase.
- Other copied code: search comments for attributions (Stack Overflow, gists, blogs); inventory fonts, icons, sounds, models, sample data.
- Provenance of media: say in NOTICE where icons, sounds and screenshots came from (synthesized from your own recipes, original work under the repo license). Keep the recipe if it is the preferred form.

## Dependencies and bundled third-party code

- Read each dependency's LICENSE and check compatibility against the license list (Expat/MIT and modified BSD are GPL-compatible; Apache-2.0 is compatible with GPLv3, not GPLv2).
- Copy the dependency's real license text verbatim into a third-party licenses file. A NOTICE that says "MIT" for a dependency whose license names several copyright holders and bundled components under BSD, MIT and zlib-style terms is wrong. Never summarize a license from memory.
- Confirm what the binary links (`otool -L` or the platform equivalent). System libraries are covered by the GPL's System Libraries exception.
- Fonts: the font's license text (OFL) ships beside the font, byte-identical to upstream.

## Notices that ship in the artifact

- The built bundle or package contains LICENSE, NOTICE and the third-party license file; the installer image carries LICENSE and NOTICE at its root; the package metadata has a copyright string. Check by listing the built artifact, not the source. (a first build often has none of these.)
- Appropriate Legal Notices (GPL §5(d)) for an interactive program: the About view shows a copyright line, "no warranty", that you may convey it under the license, and how to view the license text (a link or bundled file).
- Source offer for binaries: each release names the source as the tag `vX.Y.Z` of the public repo, the tag matches the commit the binary was built from, and the source stays up as long as the binary is offered (GPL §6(d)). Put a "Source: tag vX.Y.Z" line in every release's notes.
- Notarization and signing gates against GPL §6 "Installation Information": the reviewer's plain reading found no conflict for a separately downloaded app (the duty is for User Products conveyed with a device, and update gating is excluded). State your own build path for modified versions in the README.

## Names, marks, claims

- Name clash search before launch: app stores, package indexes, domain, the trademark databases (WIPO Global Brand Database, USPTO, EUIPO), the web. A clearance lane can find a commercial product with the same name on the same platform; that is a decision for the human and a lawyer.
- Nominative use of other products' names only; no logos. One line: "not affiliated with or endorsed by <upstream, platform vendor, providers>".
- Reserve the handle and domain.

## Third-party services and platform terms

- README privacy statement reflects each provider's real terms for the bring-your-own-key paths: whether free tiers train on content or allow human review, content licenses taken for voice or text, age requirements, retention options, region differences. Say that the user's own key binds them to the provider's terms, and mention that the update check contacts GitHub.
- Platform SDK terms: if the SDK or OS is pre-release, the vendor's license may forbid screenshots and redistribution of pre-release software. Confirm release status before publishing.
- Model licenses for any model you bundle or tell users to download.

## People and ownership

- Employer or school IP: contract or policy check; the work email in history is the tell.
- Who holds the copyright: the human, personally; confirm. Contributions inbound under the project license by default; add a DCO or CLA only if you plan to relicense.
- AI-assisted code: check commit trailers; the copyright line still names the human.
- Permanent identifiers (bundle id, keychain service, log subsystem) tie the project to a domain or company; confirm that is intended.

## Method limits seen

gnu.org blocked every fetch method; the lane used GitHub mirrors for the license text and web.archive.org copies of the FSF FAQ and license list, and said so. Record fetch limits in "not verified".
