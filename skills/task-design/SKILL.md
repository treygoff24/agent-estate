---
name: task-design
description: >-
  Use before designing a project's first slice or resolving open choices for a feature, behavior change, architecture choice, or exploratory build. Also use for "how should we build X", "design this", or "let's add Y".
---

# Task design

Design enough to make the requested work clear, then finish in the requested
mode. This method does not expand the authorized scope.

## 0. Collect the project vision once

For a new project epic (a port, product build or redesign), collect this block
from the person who owns the project before designing its first slice. Reuse an
existing approved block; a bug fix or a later feature does not restart the
interview. Prefer their words, read supplied material first, and ask only for
consequential missing answers. Grilling remains a separate tool, not a mandatory
stage.

The block has six fields:

1. **What we are building**, in the owner's words where possible.
2. **Why**: the problem or opportunity behind it.
3. **For whom**: the user, and what they will do with it.
4. **What must be true when it is done**: outcomes that can be checked, not tasks.
5. **What exists that this replaces or extends**: prior systems, data, and constraints.
6. **Stack and boundaries**: the technology already in use, and what is out of scope.

Keep the approved block in the project's plan or README and carry the same text
into every brief you hand to another agent.

**Complete when:** the block answers each field, owner-only decisions are named,
and the plan and prepared briefs carry the same approved vision.

## 1. Establish the boundary

Classify the request as a question, review, brainstorm, plan, or implementation.
Questions, reviews, brainstorms, and plan-only requests end with their requested
answer or artifact. Write a file when the request authorizes that deliverable;
read-only work remains read-only.

For implementation, read the relevant live files and local instructions, inspect
dirty state, and extract the intended behavior, success criteria, supplied brief,
and approved decisions. Approval for unchanged scope satisfies the design gate.
A prior plan supplies context; the current request supplies authority.

**Altitude.** When the request names an artifact (a report, a deck, a fix for
one crash) and that artifact would be discussed in a meeting, name the outcome
it serves and offer the outcome-shaped request beside it: "keep the apps
crash-free" where the request said "fix this crash". The request still sets
the deliverable; the offer is the requester's to take or leave.

**Complete when:** the mode, authorized deliverable, live constraints, success
criteria, settled decisions, and held actions are all explicit.

## 2. Test the design against the real problem

Compare the design's examples with the live data model before choosing its
pattern. When a screen drawn for N fields or steps now serves a seed or catalog
with M far beyond N, report the outgrown design before building. Treat the
pattern as evidence of intent rather than a scale contract.

Build the outcome matrix. For every state a user or record can occupy, including
last, only, empty, and `other`, name the required behavior. Assign a decision
owner wherever the specification is silent. Include validation: enumerate every
formatted field and identify the single source for each rule.

**Depth.** For nontrivial work, answer four questions before settling the
design, and fold in each answer that changes it: what a top professional in
this field would do here that the request does not ask for; the rawest
material they would start from, instead of what has been digested already;
the specific methods and instruments they would use (a database and a
statistical model where a table was offered); and what, other than the model
or the requester, shows the result is right. The last answer becomes the design's
outside check.

**Complete when:** every live field or step maps to a suitable interaction,
every reachable state has an outcome, every format rule has one source,
every unresolved outcome has a named owner, and nontrivial work names its
instrument and its outside check.

## 3. Resolve consequential uncertainty

Proceed directly on a small, clear fix or specified change, stating any material
assumption briefly. For a missing answer that changes behavior, architecture,
cost, privacy, reversibility, or acceptance criteria, inspect available evidence
first. Put the remaining decision to the requester as one concrete question.

For significant unresolved architecture, present a recommended design, the
important alternative, and the tradeoff. Continue independent authorized work
while the unsettled part waits. Prefer reuse and the smallest correct change;
focus review and agent work on the actual crux.

**Complete when:** each consequential choice is settled by evidence, an explicit
ruling, or a named hold, and all work independent of a hold is ready to proceed.

## 4. Finish at the authorized boundary

For plan-only work, deliver a usable plan covering scope, decisions, sequence,
verification, and every material open question. For approved implementation,
execute within those bounds and verify changed behavior with focused checks,
required repository gates, and meaningful tests for nontrivial logic. Stop
extending the design once it supports the authorized task; surface a new
material scope change for decision.

Use an existing project plan or ledger when continuity requires one. Create a
new document when requested or when a real handoff requires it. Ask before any action with a separate authorization boundary (publishing,
spending money, deleting data, messaging other people); the approved design does
not erase those gates.

**Complete when:** the requested artifact or implementation exists, every stated
success criterion has checkable evidence, every required gate has a recorded
result, and every remaining hold names its owner and prerequisite.
