# Plan template

The plan is the first artifact. It carries every decision up front so lanes execute instead of asking, and it separates what the agents decided from what only the human can. Keep the plan itself out of the export: it names identifiers.

## Sections

1. **Goal and done-means.** One paragraph on who the stranger is and what they can do. Then a numbered list of conditions, each checkable by command or observation. Example: a public repo of one fresh commit with LICENSE, README and NOTICE and nothing private (checked by the audit); a signed, notarized installer attached to a release that updates itself; a never-used account installs it and completes a first use with no key; the maintainer has used it live and signed off.
2. **Decisions already made.** A table: decision, source (who decided, when, which document). Include license, default behavior, platform floor, fresh-export-not-history, signing approach, public commit identity.
3. **Decisions for the human.** Each with a default, the consequence of choosing otherwise, and the step it blocks. Execution proceeds on the default unless the human says otherwise before the blocked step.
4. **Ground rules for every lane.** Copy these into every lane brief:
   - Private data (recordings, transcripts, vocabulary, notes, anything under the private notes folder) never enters commits, tests, logs or reviewer copies. Test data is synthetic.
   - Targeted tests only inside a lane; the coordinator runs the full gate once per integrated candidate.
   - Every new test is proved by a mutation that makes it fail.
   - Remote rules: which pushes are free, which wait for the human each time.
   - Model routing per lane (see `review-lanes.md`).
   - A reinstall or relaunch gate if the maintainer runs the project daily.
5. **Steps.** Each with an outcome sentence, the work, the tests, and the dependency on other steps. Mark which steps run in parallel and which share files (those serialize).
6. **Out of scope.** Name the things you are deliberately not shipping, so lanes do not drift into them.
7. **Risks.** Unknowns a lane might hit, each with the early step that surfaces it.

## Human decisions: the usual list

| Decision | Default | Why it needs the human |
|---|---|---|
| Signing identity | Accept what the individual account discloses, or move to an organization account | An individual Developer ID signature publishes the legal name and Team ID. An organization identity needs a D-U-N-S number. Updates and OS permission grants depend on the identity staying the same, so decide before the first upload. |
| Name clash | Run a clearance search before launch | A clearance search can find a commercial product with the same name on the same platform. Search app stores, package indexes, a trademark database (WIPO Global Brand Database, USPTO, EUIPO) and the web. Only a lawyer clears a mark; add a "not affiliated" line either way. |
| Bundle id, domain, service names | Keep, if intended to be public | Permanent once published. Changing it resets OS permission grants and orphans saved credentials. It also appears as the log subsystem, keychain service and launch-agent labels. |
| Employer or school IP | Check the contract; get written clearance if any doubt | A work email in git history is the tell. The GPL FAQ says the employer or school may claim copyright; the fix is a disclaimer from an authorized officer, which usually is not your manager. |
| Copyright holder string | "<Year> <Name> and the <Project> contributors" | GPL needs a holder. Name the human deliberately. |
| License variant | The strongest the upstream grants allow | Adapted GPL-3.0 code with no "or later" clause forces `GPL-3.0-only` for the combined work. |
| Code of conduct, issue templates, changelog | Add CoC and issue forms (cheap); release notes can replace a changelog | opensource.guide, GitHub's community profile and OpenSSF all ask for them. A plan that says none is often reversed by the research pass. |
| Platform floor | Lowest version the code supports | A platform floor often rests on only a couple of API families; availability gates plus fallbacks can lower it. A product decision with a cost in tests. |
| Old repo | Rename to `<name>-archive`, keep private | Avoids a name clash or redirect surfacing the old repo. |
| Provider terms | Document that the user's own key binds them to the provider's terms | Free tiers of AI APIs may train on content or let humans review it. |
| Account hygiene | GitHub "Keep my email addresses private" and "Block command line pushes that expose my email" | Stops a later stray commit leaking the personal address. |
