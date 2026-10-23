# OpenAI sources and provenance (read 2026-10-13)

Open this before changing a model claim in the skill. Each line says whether OpenAI said it or the author decided it.

## Models served (as of 2026-10-13; check your Codex CLI's model list)

`sol` = `gpt-6.1-sol`, `astra` = `gpt-6-astra`, `luna` = `gpt-6-luna` (all served through Codex). OpenAI's pages list `low, medium, high, xhigh, max` for `sol` and `astra`, `medium` as the `sol` default, and no `none` or `minimal` for either. `ultra` is not an effort value in any OpenAI page read; "Ultrafast" is a speed mode. Whether `ultra` is a Codex-side effort is unconfirmed.

## What OpenAI says (the skill adopts it)

| Claim in the skill | Source |
| --- | --- |
| Clear assignment = result, audience, context, constraints, what counts as done; Codex four-part prompt (goal, context, constraints, done when) | S2, S6 |
| Overly specific guidance and elaborate recipes now hinder; models handle nuance and ambiguity | S2, S4 |
| `astra` asks more and stops earlier; autonomy, requests-imply-action and approval-last prompts | S1, S4 |
| Define done to include implementing, running, inspecting, fixing failures; a required review stop pulls toward stopping early; name decisions needing review | S2, S4 |
| Replace blanket "always ask" rules with explicit boundaries; strong boundary language can make `astra` stop where work could continue | S2, S4 |
| `astra` is more sensitive to skills and `AGENTS.md`; audit them for conflicts; user instructions outrank skills (prompt block) | S1 |
| `astra` tests thoroughly unprompted; old "run tests" lines cause unnecessary testing; testing-calibration prompt; permit safe local test runs | S1, S4 |
| Default style is detailed and formatted with recurring phrases; style prompts | S1 |
| `astra` delegates less than desired; subagent prompt | S1 |
| Effort bands: low routine, medium judgment, high difficult debugging or careful review, xhigh/max only when high falls short and the gain pays; in Codex start at the default; effort is a tuning knob, not the way to recover quality | S2, S7 |
| `none`/`minimal` unsupported on `sol` and `astra`; low is the floor | S1, S8 |
| Final handoff = what changed, what was checked, what still needs attention | S2 |
| Do not require reading a doc stack before every edit; point to docs by case | S4 |
| `AGENTS.md`: layered, nearer file wins, 32 KiB combined default cap (`project_doc_max_bytes`) | S5 |
| `sol` shows better respect for user intent and restrictions than GPT-6 Sol | S3 |

## House practice (OpenAI's docs are silent)

- The minimum-contract field names beyond the four OpenAI names (Output, Stop rules, Validation), the delegation-prompt checklist, and the final-answer wording beyond S2's three items.
- Every XML block under "House blocks" in `prompt-blocks.md`, and the XML tag form itself. OpenAI's prompt-engineering page (S9) allows Markdown and XML delimiters but publishes its GPT-6 prompts as plain text.
- Putting the authorization and done lines in every unattended-lane brief for `sol` too. OpenAI's behavior guidance was observed on `astra`; the pages never state that `sol` shows the same stopping behavior.
- Adding the `astra` fixes to a `sol` prompt only after a run shows the behavior. OpenAI says only to evaluate the prompts on your model.
- Pairing the scope line in `action_safety` with the list of actions allowed without asking.

## Read and not adopted

- The agentic-task sample in S9 ("plan extensively ... reflect extensively", "keep going until the query is completely resolved") is the GPT-5-era text in a page that now names `gpt-6-astra`. It conflicts with S2 and S4 (no itineraries; define done), so the skill uses the S1 autonomy prompts instead.
- S9's "GPT models are like a junior coworker needing precise step-by-step instructions" contradicts S2, S4 for GPT-6; not adopted.
- The reasoning-effort table in S7 and the `phase` section name `gpt-5.5`/`gpt-5.4`; the effort bands are corroborated by S2 and used, `phase` is kept only as "unconfirmed" in `prompt-blocks.md`.
- S10 (Codex models page) still lists `gpt-5.5`/`gpt-5.4` models; nothing taken from it.
- S11 (reasoning best practices) covers o-series versus GPT models; not applicable.
- API-only features in S1 (async tool calling, mid-turn steering, `configuration_update`, Fast/Ultrafast, cache TTL, removing `temperature`/`top_p` at non-`none` effort): they change an API call, not how a task prompt is written. One API fact worth knowing: tool calling needs the Responses API. Nothing in the skill carries them.
- The slop-word block is adopted verbatim for use on request, though it is a list of prohibitions; `writing-for-agents` prefers positive targets. The style block above it is the positive form.
- Third-party guides (promptessor, usepromptup, codexhow and others) surfaced in search; none are OpenAI primary sources and none were used.

## Could not confirm

- Any prompt-level difference between GPT-6 Sol and GPT-6.1 Sol: OpenAI's migration section (S1) covers API parameters only; S3 reports benchmarks and alignment evaluations, not prompt guidance.
- Per-model prompt guidance specific to `sol` or `luna`: S1 states the prompts "address behavior observed with GPT-6 Astra".
- Whether the Codex CLI serves `sol` and `astra` the base instructions in S12 (the file read is on `main`); it is cited only for "the CLI already asks for short pre-tool updates and persistence".
- OpenAI's default effort for `astra` (the model page lists supported values but no default).
- A GPT-6-specific verbosity control, a "tool preamble" switch, or a "GPT-6 migration from 5.x" section on prompts: none found in the pages below.

## Sources

| # | URL | Read |
| --- | --- | --- |
| S1 | https://developers.openai.com/api/docs/guides/latest-model ("Using GPT-6": prompting best practices, migration quickstart) | 2026-10-13 |
| S2 | https://openai.com/index/practical-guide-building-gpt-6/ ("A model guide for the GPT-6 family", dated 2026-10-02) | 2026-10-13 |
| S3 | https://openai.com/index/introducing-gpt-6-1-sol/ ("Introducing GPT-6.1 Sol") | 2026-10-13 |
| S4 | https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra ("Rethinking skills and prompts for GPT-6 Astra") | 2026-10-13 |
| S5 | https://developers.openai.com/codex/guides/agents-md | 2026-10-13 |
| S6 | https://developers.openai.com/codex/learn/best-practices | 2026-10-13 |
| S7 | https://developers.openai.com/api/docs/guides/reasoning | 2026-10-13 |
| S8 | https://developers.openai.com/api/docs/models/gpt-6.1-sol and https://developers.openai.com/api/docs/models/gpt-6-astra | 2026-10-13 |
| S9 | https://developers.openai.com/api/docs/guides/prompt-engineering | 2026-10-13 |
| S10 | https://developers.openai.com/codex/models | 2026-10-13 |
| S11 | https://developers.openai.com/api/docs/guides/reasoning-best-practices | 2026-10-13 |
| S12 | https://github.com/openai/codex/blob/main/codex-rs/protocol/src/prompts/base_instructions/default.md | 2026-10-13 |
| S13 | https://developers.openai.com/codex/prompting and https://developers.openai.com/codex/concepts/customization (skimmed; nothing adopted beyond S6) | 2026-10-13 |
