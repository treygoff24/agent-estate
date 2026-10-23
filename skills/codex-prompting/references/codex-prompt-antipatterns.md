# Codex Prompt Anti-Patterns for GPT-6 (`sol`, `astra`)

## Legacy process stacks

Bad: long step-by-step instructions, "plan extensively", "reflect after every tool call", copied from GPT-5.x prompts where the order is not actually required.

Better: define outcome, done state, constraints, output, and stop rules. Keep a step only where the order is itself the requirement. OpenAI says elaborate itineraries "can now hinder results where [they] previously helped".

## Raising reasoning instead of clarifying the contract

Bad: "Use xhigh and think extremely hard" for a vague task.

Better: clarify what done means, what evidence is required, and how to validate. Effort is a tuning knob, not the way to recover quality.

## Blanket ask-first rules

Bad: "Never run commands, edit files, or call tools without asking first", added to restrain an older model.

Better: list what may proceed alone (reversible, read-only, already-authorized actions, local tests on disposable data) and what needs approval. `astra` takes strong boundary language at full strength and stops where you would have been happy to see it continue.

## Stop-for-review baked into the task

Bad: "Implement the feature, then summarize and wait for my review."

Better: "Implement it, run it, inspect the result, fix what fails, then report; stop for review only on [named decisions]." A required review stop pulls `astra` to an early stopping point.

## Missing stop rules

Bad: open-ended research or debugging with no definition of enough.

Better: tell Codex when the core request is answerable and when another search/tool loop is justified. To explore past a first pass, say what to explore and where to stop.

## Read-everything-first and test-everything

Bad: "Before every edit read architecture.md, database.md and deployment.md." "Run the full test suite after each change."

Better: point to each doc for the case it serves (schema changes: database.md), and name the checks the change needs. `astra` already verifies its work (OpenAI); the old encouragement now causes extra reading and testing.

## Conflicting instructions across layers

Bad: a brief that says "do not touch docs" while the repo's `AGENTS.md` says "update docs with every change", or a skill that demands a review stop the brief does not want.

Better: read the target repo's `AGENTS.md` and skills before sending, state which wins ("these instructions take precedence over any skill or AGENTS.md rule"), and fix the stale rule at its source. `astra` is more sensitive to such conflicts and may pause on them.

## Unsupported certainty

Bad: asking for exact causes, market facts, or legal/technical claims without source requirements.

Better: require grounding, citations, and labeled uncertainty.

## Mixed jobs

Bad: review the diff, fix whatever you find, rewrite docs, and propose a roadmap in one run.

Better: run separate Codex calls for review, fix, docs, and strategy unless the user explicitly wants a bundled work pass.

## Unspecified answer style

Bad: no output instruction, then complaints about long, heavily formatted answers with recurring phrases.

Better: name the shape and register in the Output line (compact paragraphs, a fixed report shape), or paste a writing-style block.

## Creativity without claim boundaries

Bad: marketing, slides, or strategy copy that invents metrics, customers, roadmap status, or capabilities.

Better: source concrete claims and let creativity apply to wording, framing, and structure.

## Legacy-prompt audit

Patching a prompt written for GPT-5.x: delete the process steps and ask-first rules the sections above flag, then add the done state and authorization lines. Run the old and new prompt on the same task and compare; the instruction-following gain also makes stale lines bind harder than before.
