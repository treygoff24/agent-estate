---
name: operationalizing-expertise
description: >-
  Turn a tacit method — an expert's approach, a paper's technique, or your own
  repeated practice — into reusable, auditable, executable artifacts (a skill, a
  rule set, a checklist). Use when distilling a methodology, "make this a skill",
  "operationalize how I do X", or mining your own history into rules.
---

# Operationalizing Expertise

Goal: convert tacit method into something a future agent (or you) can execute without rediscovering it. The output is usually a skill, but the shape is general — corpus → distilled kernel → operator rules → validators.

> **Evidence-first, or it's fiction.** Every rule traces to a specific source: a quote, a worked example, a real session where it paid off. A rule with no provenance is a guess dressed as knowledge. If you can't cite why a rule exists and what failure it prevents, cut it.

## Three tracks — pick by where the method lives

**Track A — distill from sources** (a paper, a transcript, an expert's writing). Gather the primary material, pull the load-bearing quotes with stable anchors, extract the kernel of axioms they all agree on, then write operator rules.

**Track B — distill from your own practice.** Mine your history for the thing you keep doing. `atuin`/shell history and prior session transcripts show the repeated prompts and command sequences. For each recurring move, name the trigger, the action, and the failure it avoids.

**Track C — synthesize across models** (when the method is contested or you want range). Ask several models (different families, in separate sessions) for independent distillations, then keep only the consensus in the kernel and route disagreements to a "disputed" section rather than averaging them away.

## The pipeline

1. **Corpus.** Collect the actual source material — transcripts, the paper, your session logs. Keep it; rules cite it.
2. **Evidence extraction.** Pull the specific quotes / examples / command sequences that carry the method. Give each a stable id so rules can reference it.
3. **Kernel.** Distill the small set of axioms — the default truths the method rests on. These are stress-tested defaults, not scripts: an axiom you can't justify under an edge case isn't an axiom. Triangulate if you used several sources; consensus goes in the kernel, disagreements stay flagged.
4. **Operator rules.** Turn the kernel into "when X, do Y, because Z." Each rule names its trigger, its action, the failure it prevents, and an evidence anchor. This is the executable layer.
5. **Validators.** Define how you'd check the artifact is sound — counter-examples it must handle, a self-test of trigger phrases, the gate that says "this is ready." Failing a validator blocks shipping it.

## Writing it as a skill (the usual output)

A good skill is a lean `SKILL.md`: a one-line "core" framing, the rules in priority order, a short anti-patterns table, and a "pairs with" pointer. Front-load the load-bearing rules. Cut everything that restates the obvious or that a competent reader would infer. The frontmatter `description` is the activation trigger — make it match how you'd actually ask for the thing, with concrete trigger phrases. Bias hard toward short: a skill that's read in full beats a comprehensive one that's skimmed.

## Invariants

- Every rule cites evidence; no orphan rules.
- The kernel holds consensus only; disagreements are visible, not blended.
- Operator rules carry trigger + action + failure-prevented, not just an action.
- A validation gate exists and is required before the artifact ships.
- The artifact stays lean — distillation removes, it doesn't accumulate.

## Anti-patterns

- Comprehensive over usable — a 900-line "skill" nobody reads is worse than a 90-line one they do. (The skills this very pipeline produced for Jeff Emanuel are the cautionary tale: great kernels buried under scaffolding.)
- Rules with no provenance — speculation laundered as method.
- Averaging contested claims into mush instead of keeping the sharpest version and flagging the dispute.
- Distilling a method pitched at someone else's workflow without re-grounding it in yours.
