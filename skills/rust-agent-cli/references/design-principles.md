# Agent-first CLI design principles

The design-wisdom layer behind the Rust mechanics. An agent CLI and an MCP server are the same thing in different clothes: a tool surface an LLM drives blind, with no human in the loop. Everything here follows from that.

## The one rule

**Design every surface so the first command an agent instinctively tries either just works or is redirected with a precise, actionable hint.** Or, from the MCP side of the house: **make the wrong thing impossible and the right thing obvious.** Agents misuse tools in *predictable* ways — design for the predictable mistake, then educate toward success instead of just rejecting.

An agent's failure model differs from a human's. Humans iterate visually and tolerate ambiguity; agents iterate on parsed signals and exit codes and need explicit branches. So **the least-surprise-on-failure path matters more than the least-surprise happy path** — failures are where agents lose the most time. And an agent's working memory is bounded, every call costs tokens and round-trips, outputs eat context, and it forgets your conventions between sessions. So the tool must **teach itself on every invocation** and **return less, more structured**.

## Principles

**1. Discoverability via help + a machine contract.** Ship `--help` an agent reads top-down (first lines matter most), plus a `describe`/`capabilities --json` surface returning the full contract: version, every verb/flag/exit-code/env-var, limits, schemas. Without an introspectable contract the agent must remember conventions out-of-band; with it, it reads the contract straight from the tool. Table stakes, not a nice-to-have.

**2. Predictable I/O contracts.** Stdout is data only; stderr is diagnostics only. A `--json`/structured mode emits *only* valid machine output on stdout — no banners, no progress, no prose. `tool x --json | parser` must work without filtering log lines. Mixing the two streams is the single biggest cause of agent fragility.

**3. Structured, machine-readable errors.** Every error names (a) what failed, (b) where (`file:line` if applicable), (c) the exact command the agent should have run instead — plus an exit-code category and, for typos, a "did you mean." "See --help" teaches nothing; a surgical correction teaches the right form forever. See the error-rewriting craft below.

**4. Determinism by default.** Same input → same output bytes. Stable ordering (sorted or documented). No wall-clock timestamps in free-text output — timestamps live in JSON fields. Honor a reproducible-clock override; seed any RNG; content-address IDs where possible. Agents build downstream logic on outputs and trust them to be reproducible; hashmap-iteration order, locale formatting, and random IDs silently break that trust.

**5. Idempotency / safe retries.** Repeat invocation is safe; mutations are gated and re-runnable without compounding damage. Prefer advisory reservations/leases with TTLs over hard locks — a failed lock deadlocks, a lease recovers. Transient failures return a retry-safe exit code with a "wait N and retry" action. Agents pause, resume hours later, and run concurrently with other agents.

**6. Non-interactivity.** Never prompt in a non-TTY. Destructive ops require an explicit `--yes`/`--confirm` flag, not an interactive y/n. Bare invocation must never launch a TUI — it prints useful help/summary and exits, or an explicit `tool tui` opens the interface, never both. Any blocking prompt hangs an agent that didn't expect it and burns its whole turn.

**7. Least-surprise, inevitable defaults.** Verb and flag names match the agent's prior expectation: POSIX (`--help`, `--version`, `--quiet`), modern (`--json`, `--no-color`, `--dry-run`, `--yes`), tool-family conventions, dictionary expectations (`list` not `enumerate`; `delete` not `purge`; symmetric `add`/`remove`). Pick the name the agent would guess first as canonical; alias the rest. Every divergence from expectation is a failed first try.

**8. Self-documentation, no telepathy required.** Every flag, exit code, and behavior is documented in the contract; every undocumented behavior is a defect. The canonical task requires zero prior knowledge. Advanced features are optional-but-rewarded, never required to use the tool correctly.

**9. Token-efficient, bounded output.** Return IDs + the 2–3 fields the agent actually needs, not the full payload. Support sparse field selection, `--limit`, pagination cursors (`count`, `total`, `next_cursor`/`has_more`), and `--max-output-bytes` with a sane default so one accidental `list` can't blow the agent's context. Spill big output to disk and return a handle (`--output FILE` → path + summary on stdout). Two altitudes: a terse default and a `--json`/`--full` firehose by opt-in. Outputs consume working memory; round-trips cost tokens.

**10. Explicit over implicit.** Where humans tolerate ambiguity, give agents explicit signals: `--color=auto|never|always`, `--pager=never`, a documented default target, honored env conventions (`NO_COLOR`, `CI`, `TERM=dumb`). Keep human-friendly implicit defaults, but always expose and document the explicit override.

**11. Stable contracts + versioning.** Pin the output schema and exit-code dictionary; carry a contract/api version. Changes go through deprecation: keep the old flag, warn naming the new one, ship the new flag, provide a migration recipe — never silently drop or repurpose. Agents (and the scripts they write) branch on your contract; a silent breaking change is a future production bug in every consumer.

**12. Graceful degradation with provenance.** When a capability tier is unavailable (index down, network offline), emit best-effort output that says which mode actually ran and what would unlock the better tier — rather than failing entirely or pretending nothing changed. Agents may build downstream logic on the result; they need to see the degradation and the remedy.

**13. Minimum viable surface, machine-first.** Expose the smallest surface covering the canonical tasks; one canonical form per operation, alias the rest. Design the machine surface first (contract schema → per-verb schemas → error taxonomy → implement → render JSON to human text), not human-first-retrofitted — retrofits always leave parity gaps.

**14. Composability + a sub-second hot path.** Support stdin pipelines (`--from-stdin` / `-`) so bulk work is one call, not a shell loop of N. Keep the most common invocation fast (~1s warm); defer expensive analysis to an explicit `--full`/`--deep` slow path. Accept the same shapes you emit — if `list` prints IDs, another command accepts those exact IDs; if `plan` emits a JSON change-set, `apply` consumes it. Round-trippable I/O lets agents pipe your output back into you.

## Command surface and granularity

- **Group by resource noun, then verb** (`run start`, `run list`, `run logs`) — the CLI analog of MCP's `service_action_resource` prefix. Namespacing makes a command guessable from the task description and prevents collisions.
- **Keep each subcommand group scannable in one `--help`** (MCP's ≤7-tools heuristic). If a group's help scrolls, split into nested subgroups — don't pile on flags.
- **Don't over-atomize** into dozens of tiny subcommands (the agent pays a discovery/selection tax per command), and don't collapse into one mega-command with a `--mode` flag that secretly swaps the whole contract (that just hides the menu where it's undiscoverable).
- **Split when** two operations have disjoint required args, different read/write blast radius, or different output shapes. **Combine when** callers almost always invoke them in sequence, or the only difference is a filter.
- **Annotate blast radius.** Expose a machine-readable `readOnly`/`destructive`/`idempotent` property per command in `describe`, so an agent can reason about a command before calling it. A hint, not the safety mechanism.

## Input forgiveness (forgive, but stay deterministic)

- **Coerce at the edges, validate at the parse boundary.** Accept reasonable variations — case-insensitive enums, `true/1/yes`, IDs with or without a known prefix, trailing slashes, `key=val` and `key:val` — and normalize to one canonical internal form. In Rust this lives in a Clap `value_parser` / custom `FromStr`, so the rest of the program sees only validated, canonical values.
- **Forgiveness must be deterministic and total**, never heuristic guessing that can flip between runs. Coerce only where the mapping is unambiguous (one input → exactly one meaning). The moment two plausible meanings exist, **reject with options** rather than picking one — agents replay commands, so a silent wrong guess is worse than a clean error.
- **Detect predictable confusion and name it.** When a positional looks like it belongs to a different flag, or is a placeholder (`YOUR_PROJECT`, `$VAR`, `<id>`, `...`), fail with a message that says which flag or discovery step it belongs to — don't pass the literal through.
- **Reject broadcast scope.** A destructive command refuses "operate on everything" unless an explicit `--all` opt-in is present, so an under-specified call fails loud instead of nuking the tree.

## Composite operations and the plan/apply analogy

- **Ship a composite subcommand** for any sequence agents reliably perform together (`init` = create + configure + verify) — fewer round-trips, fewer places to drop the thread, atomic success/failure. This is MCP's "macro tool." **Keep the primitives too**; macros are additive convenience, not a replacement.
- **plan / apply is the safe macro shape for mutation.** `plan` computes and prints the full intended change-set (read-only, deterministic); `apply` enacts it, ideally consuming `plan`'s own output. The agent gets a dry-run it can inspect before committing blast radius.
- **Return next-step hints.** On success, name the obvious follow-up (`"run \`tool run logs <id>\` to follow"`). MCP's `next_actions` turns one call into a self-documenting workflow.
- **Make composites idempotent** — re-running converges, doesn't duplicate.

## The error-rewriting craft

A bad error is a dead end; a good error is a teaching moment. Climb this ladder: **silent_fail** (worst — exit 0, nothing said) → **useless_error** (fired, no path forward) → **useful_hint** (names the exact flag/command/env-var to use) → **inferred_and_acted** (infers intent and proceeds with a warning — use sparingly: only typo-distance 1, non-destructive, stable canonical form; never auto-correct a destructive op).

Every useful_hint-class error follows one anatomy, 5–10 lines, no stack traces (unless `--debug`), no framework jargon ("clap parse error" means nothing to the agent), never on stdout:

```text
error: <what failed> [at <where: file:line>]
  <one-line WHY>
  <one or more named REMEDIATIONS, each a paste-ready command or path>
  see: <pointer to describe / robot-docs / project docs>

exit <N> (<exit_code_kind>)
```

**Unknown flag** — fuzzy-match and suggest (the highest-leverage import from MCP: on any unknown subcommand, enum value, or ID, print the nearest valid candidate):

```text
# before:  error: unrecognized arguments: --jsno        (exit 2)
# after:
error: unknown flag '--jsno'
  did you mean '--json'?
  see: tool list --help                                  (exit 2)
```

**Missing required argument** — name how to *find* the value:

```text
error: 'delete' requires <ITEM_ID>
  syntax:        tool delete <ITEM_ID>
  example:       tool delete X-001 --dry-run
  to find an ID: tool list --json | jq '.items[].id'
  see: tool delete --help
```

**Destructive op without confirmation** — name the go-ahead, the safe alternative, and the preview:

```text
error: 'delete' is destructive; refusing without confirmation
  preview the change:  tool delete X-001 --dry-run
  perform the change:  tool delete X-001 --yes
  safer alternative:   tool archive X-001  (reversible; later 'tool restore X-001')
```

**Transient failure** — communicate the exit-code category as data so retry logic can branch:

```text
error: failed to connect to api.example.com:443: connection refused (after 2 retries)
  is the service up?         tool doctor
  retry with longer timeout: tool sync --timeout-ms 60000
  use cached data:           tool sync --offline
exit 75 (temporary-failure; retry safe)
```

**Empty result** — make "ran, found nothing" distinct from "didn't run": exit 0 with an empty array and a hint, never exit 1 and never empty stdout.

```json
{"ok":true,"data":{"items":[],"total":0},"meta":{"warnings":["no matches; try a broader query or --recent"]}}
```

Pin every rewritten error with a regression test asserting the hint survives future refactors.

## Anti-patterns that specifically hurt agents

- Interactive prompts in a non-TTY — hangs the agent; require `--yes` and error-with-instructions.
- TUI on bare invocation — blocks any agent that didn't expect it.
- Color/ANSI/emoji leaking into pipes — corrupts downstream parsers; honor `NO_COLOR`, `CI`, `TERM=dumb`, non-TTY.
- Logs/progress/banners on stdout, or mixing JSON and free text on stdout — `--json` must be valid JSON and nothing else.
- Silent-fail (exit 0 on failure) — the agent can't even detect failure to retry.
- Exit 1 for "ran fine, no results" — empty result is exit 0 with an empty array.
- Ad-hoc / undocumented exit codes — codes must be a published dictionary an agent can `case $?` on.
- Unstable or English-prose-only errors — keep them structured, categorized, stable enough to match on.
- Silently dropping a deprecated/typo'd flag — proceed-with-warning or error-with-migration-recipe; never ignore.
- Hidden state / undocumented behavior — every relied-on behavior must be in the contract.
- Non-deterministic output — hashmap order, wall-clock in prose, unseeded IDs, locale formatting.
- Silent truncation — surface the limit and the paths forward (raise limit / paginate / filter / count-only).
- Ambiguous or family-confused verbs — a verb that means something different here than in a sibling tool.
- Huge unbounded output, or returning data without the next move (recommendations without paste-ready commands; output without a `data_hash` for drift detection).
- Multiple ways to do one thing — one canonical form, aliases for the rest.

## "Is my agent CLI excellent?" build checklist

1. **Agent intuitiveness** — the first command an agent guesses succeeds, or is redirected with a hint that names the exact correction.
2. **Agent ergonomics** — the canonical task takes minimal round-trips; a composite bundles the multi-call workflow into one call with paste-ready follow-ups.
3. **Ease of use** — fully discoverable without external docs: `--help`, `describe`, self-describing output, in-tool agent handbook.
4. **Output parseability** — stable documented schema; structured mode on every read verb; stdout=data / stderr=diagnostics; published exit-code contract.
5. **Error pedagogy** — errors teach: name the exact flag/command, cite `file:line`, suggest the safe alternative, offer "did you mean."
6. **Intent inference** — legible-but-wrong invocations (typos, deprecated spellings) recover gracefully or hint surgically.
7. **Safety with recovery** — irreversible ops gated behind explicit confirmation, with `--dry-run`/`plan`, named rollback, lease-based concurrency (read-only verbs are inherently safe).
8. **Determinism & reproducibility** — same input → same bytes; no wall-clock in prose; content-addressed IDs; a `data_hash` for drift detection.
9. **Self-documentation** — `describe --json` returns the contract; per-verb schema export exists; verbs cross-reference related verbs.
10. **Composability** — clean in pipelines; no surprise prompts; honors `NO_COLOR`/`CI`/`TERM`; stdin-driven bulk path.
11. **Regression resistance** — golden/snapshot tests pin help text, output schemas, exit codes, and error hints so ergonomics can't silently drift.

## Verification-first

Don't claim the tool has a property without verifying it against the actual binary. The methodology is evergreen; live behavior is volatile — a flag, default, or schema can change every release. Before you say "done":

- **Invoke, don't assume.** "Has flag `--x`" → run `--help | grep` *and* check source. "Exits N on condition C" → trigger C, check `$?`. "Output schema is {…}" → run it, inspect the keys.
- **Dry-run the dangerous paths.** Exercise every gated mutation through its `--dry-run`/`plan` and its refusal path, so you've seen the gate hold.
- **Pin what you proved.** Each contract property an agent depends on — schema shape, exit-code meaning, error hint, deterministic bytes — gets a regression test. Two consecutive structured invocations should be byte-identical (modulo documented volatile fields).

A property isn't real until the binary demonstrates it and a test pins it. Tests and dry-runs are how you prove the contract, not vibes.
