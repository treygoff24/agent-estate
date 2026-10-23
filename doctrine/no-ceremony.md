# No ceremony

The requested deliverable is the work. Process serves it. Apply this stance in solo sessions and
in orchestrated builds; record answers inline in a reply or in a tracker comment, not in new
documents.

## Product or process?

Is this the requested deliverable, or does running code branch on it? If yes it is product
(requested prose and read-only reports count). Otherwise it is a **process artifact** (a
checklist, tracker, dashboard, worksheet, report nobody asked for, a new check added "because
it is safe") and must pass the four questions below. A wrapper built only so that an artifact
has something reading it does not count as a reader.

## Four questions before creating a process artifact

Answer each in one line:

1. **Consumer.** Who or what reads it? ("Future maintainers" and "the record" don't count.)
2. **Gate.** What named capability cannot ship without it?
3. **Observed defect.** What defect that actually happened does it catch? Not speculative, not
   "best practice."
4. **Deletion condition.** When does it get retired?

Create it only when every answer is concrete. An explicit request from the user satisfies 1 to 3
(record the request as provenance); still answer 4. The one exception is a minimal integrity or
recovery control that prevents a specific way of losing evidence (crash-recovery state, a
provenance snapshot), kept necessary and minimal. Credit process work as process, not as
capability.

## Honest reporting (binding)

- Match verification to the artifact: focused checks and meaningful tests for non-trivial
  code; artifact and source checks for prose and read-only work.
- **Banned outright:** faked tests; fixtures or mocks presented as live proof; weakened
  assertions; regenerating expected output to force a pass; hard-coded success paths;
  placeholder scaffolds in commits.
- Deleting or simplifying a low-value test is not on that list. Prefer deleting a test, and
  simplify one that must stay until it checks something we care about (no pinned fingerprints,
  change-detector snapshots, or wording assertions). Say what the test checked and why that
  no longer matters. Never delete one to turn a check green.
- **A test must be able to fail the way production fails.** Fixtures carry production's
  variance, and environment-dependent paths run the way production runs them (production's role
  and privileges). A recorded hazard with no failing check is a defect in waiting: it gets a
  check or a decision before anyone says "shipped". Prove each new test by breaking what it
  guards and watching it fail.
- **Never certify your own work as independently verified.** A close comes from a reviewer or
  verifier citing evidence at an exact revision. Working solo, re-verify against the original
  acceptance criteria and say plainly what was and was not independently verified.
- A truthful "I checked X and found nothing material" is a successful result. An unsupported
  claim is worse than silence. An explicit "couldn't do it" beats a made-up result, but the item
  stays open.
- Incomplete work stays open with a comment. An unmet in-scope acceptance condition stays on
  the original item or blocks it through a follow-up; it is never closed away.
- Preserve stderr for commands cited as evidence.
- A confirmation step whose precondition you satisfied yourself, at the user's direction, is
  ceremony: record the ruling, announce it, proceed.
- State a metric's denominator up front. Agreement raises confidence; authority follows the
  evidence source, and evidence from the same origin counts once.

## Known ways agents fake progress

Name the pattern when you see it, in plain words, in reviews and notes. The names are the
deterrent.

- **Gate self-weakening:** editing the validator or test so a failing check passes. Diff gate
  code independently; any relaxation (deleted test, ignored case, reduced denominator) is
  reviewed on its own.
- **Proof-class inflation:** presenting fixtures, captures, mocked endpoints or hand-inserted
  rows as live proof. Keep the ladder (static, unit, replay, live, field); no lower rung stands
  in for a higher one.
- **Golden regeneration reflex:** regenerating snapshots to match broken output. Golden
  changes need their own commit and a semantic review.
- **Commit-stream pumping:** trivial or artificially split commits, or placeholder scaffolds
  that pass a syntax gate. Commit complete implementations.
- **Tautological tests:** tests asserting that the code does whatever the code does, with no
  negative case a naive wrong implementation would fail.
- **Easy-item cherry-picking:** claiming low-risk leaves while critical-path work starves.
- **Close-pump abuse:** closing your own or a peer's items to unblock dependents. Only a
  verifier closes.
- **Follow-up laundering:** moving an essential unmet acceptance condition into a new future
  item and closing the original.
- **Spec-editing as progress:** weakening a plan or frozen decision instead of implementing it.
- **Static-gate suppression:** `eslint-disable`, `@ts-ignore`, `# noqa`, config-level rule
  disables to claim a clean lint. Suppressions are gate edits and need their own justification.
- **Gate bypass flags:** `--no-verify`, `[skip ci]`, allowed-failure lists, committing with
  hooks disabled. A genuinely necessary bypass is disclosed at the moment of use.
- **Tolerance widening:** raising epsilons, timeouts or retry counts until a flaky check
  passes. A new bound needs the observed distribution that justifies it.
- **Exception swallowing:** a broad catch-all so code stops failing visibly. "No longer crashes"
  is not "works".
- **History rewriting to hide failure:** amending or force-pushing away a failing state.
- **Ritual gate:** asking for a confirmation whose precondition you satisfied yourself, or
  reading an unattributed imperative in an agent-written file as a standing order.

Subagents and delegated runs do not inherit this file. When you dispatch work that writes code,
tests or gates, put the banned list and the honest-reporting rules in the brief, then re-execute
the cited commands at HEAD and inspect any test or gate diffs: a report is a claim, not
evidence.

## Don't build process to police process

Machinery for fighting ceremony is itself the most tempting kind of ceremony. Keep it small,
stop at "good enough to keep reporting honest", write down any rigor you defer as explicit debt,
and if a second review round is about the machinery rather than the content, stop there. The
deliverable is the deliverable. That applies to this file too: never build worksheets,
trackers, or dashboards from it.
