---
name: codex-prompting
description: >-
  Prompting for Codex or OpenAI models (sol, astra, luna): draft or revise the task prompt sent to GPT or Codex for delegation, implementation, diagnosis, review, research, or an API call. Not for writing skills, AGENTS.md or reference docs for agents in general: writing-for-agents.
---

# Codex Prompting

Prompt `sol` (GPT-6.1) and `astra` (GPT-6) like a senior colleague: the outcome, constraints, evidence, and what done includes. OpenAI's own guidance is that detailed itineraries now hurt where they once helped, so give steps only where the order is itself the requirement. Provenance of every claim below: [`references/openai-sources.md`](references/openai-sources.md).

## Minimum contract

```text
Goal: the user-visible result.
Context: only the files/facts needed.
Constraints: scope (what may be read or changed), standards, explicit non-goals.
Done when: what must be true before the final answer, including running the result, inspecting it, and fixing what fails.
Validation: the named commands, sources, screenshots, or checks.
Output: format and brevity.
Stop rules: when to ask, search, retry, escalate, or stop.
```

## What changed with GPT-6

- **Done includes the run.** `astra` stops sooner than earlier models and returns for review with work left. State the full done state, and name the decisions that need the reader's review; a "stop for review after the first implementation" line pulls it to stop there.
- **Authorize the work.** `astra` asks when intent is unclear. For an unattended lane say the work is approved, and say that approval comes last: finish the authorized work, then ask over a concrete, reviewable result. Blocks in `prompt-blocks.md`.
- **Boundaries as lists.** Name what may proceed alone and what needs approval. A blanket "always ask first" or "never without permission" is taken at full strength and stalls the run.
- **One authority order.** The prompt outranks skills and `AGENTS.md`. `astra` follows repo instructions closely, so read the target repo's `AGENTS.md` and skills for rules that contradict the brief or demand extra testing and docs-reading, and resolve the conflict in the prompt.
- **Size verification.** `astra` tests thoroughly unprompted, so "run tests" lines now over-test. Name the checks the change needs and say to stop there for small reversible changes; "run all tests" and "read every doc first" burn time.
- **Say how to write the answer.** The default is long, formatted, with recurring phrases. Give the output shape and register.
- **Say when to use subagents.** `astra` delegates less than a workflow often wants; give the condition and the limit.
- **`sol` is unproven on the `astra` fixes.** OpenAI derived the behavior guidance from `astra` and says to evaluate it on your model; `sol` follows user intent and restrictions better than GPT-6 Sol did. Add the blocks when a `sol` run shows the behavior, not by default. A brief for an unattended lane gets the authorization and done lines either way.

## Reasoning effort

- `low`: routine, well-scoped work (extraction, small edits). `sol` and `astra` have no `none` or `minimal`, so `low` is the floor.
- `medium`: planning, comparing options, work needing judgment. The `sol` default; start there.
- `high`: difficult debugging, deeper analysis, careful review.
- `xhigh` / `max`: when `high` falls short and the gain justifies the time and cost. Never as a patch for an unclear prompt: clarify the contract first.

This skill owns only how the prompt is written; which model to pick for which job is your own routing.

## Delegation prompts

For subagents or delegated workers, include:

- exact owned files or read-only scope,
- what the lane decides alone and what it must stop for,
- model/reasoning lane,
- expected artifact path or report shape,
- validation/review requirements,
- whether the worker may edit or only draft.

## Evidence

Use current sources for unstable facts, laws, APIs, SDKs, prices, schedules, and named people/company roles; inspect live files for code. Say what is confirmed and what is inferred. For plans, map requirements to files/systems, risks, validation, rollback, and open questions.

## Final answer standard

Return what changed/found, what was verified, what remains risky or blocked, and the next best step. Keep it as short as the task allows.

## Reference files

- [`references/prompt-blocks.md`](references/prompt-blocks.md): paste-in blocks, OpenAI's GPT-6 prompts first, house blocks after. Open it when a prompt needs a section spelled out.
- [`references/codex-prompt-recipes.md`](references/codex-prompt-recipes.md): whole prompts for diagnosis, a narrow fix, a long autonomous task, review, research, and patching an existing prompt. Open it when the task is one of those.
- [`references/codex-prompt-antipatterns.md`](references/codex-prompt-antipatterns.md): bad-versus-better pairs, with a legacy-prompt audit. Open it when revising a prompt that underperformed or carries over from GPT-5.x.
- [`references/openai-sources.md`](references/openai-sources.md): what OpenAI says versus house practice, what was not adopted, what is unconfirmed, and the dated sources. Open it before changing a model claim.
