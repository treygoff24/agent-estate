# Codex Prompt Recipes for GPT-6 (`sol`, `astra`)

Use the smallest recipe that fits. Trim aggressively. Add blocks from `prompt-blocks.md` only when a run shows the behavior they fix.

## Diagnosis

```xml
<task>
Diagnose why the failing test, command, or behavior is breaking in this repository. Identify the most likely root cause from available evidence.
</task>

<compact_output_contract>
Return: root cause, evidence, smallest safe next step, and remaining uncertainty.
</compact_output_contract>

<default_follow_through_policy>
Keep going until you have enough evidence to identify the root cause confidently. Ask only when missing information materially changes correctness.
</default_follow_through_policy>

<verification_loop>
Verify that the proposed root cause matches observed evidence before finalizing.
</verification_loop>

<missing_context_gating>
Do not guess repository facts. Read the required files or state exactly what remains unknown.
</missing_context_gating>
```

## Narrow implementation or fix

```xml
<task>
Implement the smallest safe fix for the stated issue. Preserve behavior outside the failing or requested path.
</task>

<structured_output_contract>
Return:
1. summary of the fix
2. files changed
3. validation performed
4. residual risks or follow-ups
</structured_output_contract>

<completeness_contract>
Resolve the task fully before stopping. Do not stop after identifying the issue without applying the fix.
</completeness_contract>

<verification_loop>
Run the most relevant available validation. If blocked, explain why and name the next best check.
</verification_loop>

<action_safety>
Keep changes tightly scoped. Avoid unrelated cleanup or refactors.
</action_safety>
```

## Long autonomous task (unattended lane)

```text
Goal: [the result, and who or what it is for].
Scope: [owned files; read-only areas].
Done when: [the change works, you have run it, inspected the output, and fixed what failed; plus the named checks].
This work is approved. Do the whole task without stopping for design confirmation. You decide: [choices the lane makes alone, e.g. naming, file layout, test shape]. Stop and ask only for: [the short list that needs the reader, e.g. a dependency change, a destructive command, a scope change].
Report: what changed, what you ran and its result, what remains risky, the next step.
```

Add the autonomy and approval-last blocks if the lane still stops early; add the testing-calibration block if it over-tests.

## Review or adversarial review

```xml
<task>
Review the provided repository changes for material correctness, regression, security, reliability, and maintainability risks.
</task>

<structured_output_contract>
Return findings ordered by severity. For each finding include evidence, likely impact, and concrete recommendation. If there are no material findings, say so directly.
</structured_output_contract>

<grounding_rules>
Ground every finding in repository evidence or tool output. Do not report style nits or speculative concerns without support.
</grounding_rules>

<dig_deeper_nudge>
Check for second-order failures, empty states, retries, stale state, rollback paths, race conditions, and permission boundaries before finalizing.
</dig_deeper_nudge>
```

## Research or recommendation

```xml
<task>
Research the available options and recommend the best path for the user's goal.
</task>

<structured_output_contract>
Return: observed facts, recommendation, tradeoffs, open questions, and sources.
</structured_output_contract>

<retrieval_budget>
Start broad. Retrieve again only when required facts are missing, exhaustive coverage was requested, a specific source must be read, or an important claim would otherwise be unsupported.
</retrieval_budget>

<citation_rules>
Use primary sources where possible. Separate confirmed facts from inference.
</citation_rules>
```

## Prompt patching

```xml
<task>
Diagnose why this existing Codex/GPT-6 prompt is underperforming and propose the smallest high-leverage revision.
</task>

<structured_output_contract>
Return: failure modes, root causes in the current prompt, revised prompt, and why the revision should work better.
</structured_output_contract>

<grounding_rules>
Base the diagnosis on the prompt text and provided failure examples. Do not invent failure modes that are not supported.
</grounding_rules>

<stop_rules>
Prefer removing redundant instructions and clarifying success criteria over adding more process.
</stop_rules>
```
