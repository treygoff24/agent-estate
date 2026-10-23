---
name: debugging-systematic
description: >-
  Debug a failure, flaky test, regression, race, leak, or unexpected behavior by reproducing and tracing its cause.
context: fork
---

# Systematic Debugging - Root Cause Analysis Framework

## Core Philosophy

**Never guess at fixes.** Always understand the root cause first.

```
Bad: "Let's try adding a timeout here"
Good: "The timeout is occurring because X. Here's proof: [evidence]"
```

## Four-Phase Framework

### Phase 1: Root Cause Investigation
**Goal**: Understand exactly what's happening and why

**Build a feedback loop first; it is most of the work.** Folded in from the retired `diagnosing-bugs` skill (mattpocock/skills, MIT; see LICENSE in this folder). With a tight pass/fail signal that goes red on *this* bug, bisection, hypotheses and instrumentation all just consume it; without one, staring at code will not find the cause. Ways to get one, roughly in order: a failing test at whatever seam reaches the bug; a curl or HTTP script against a running dev server; a CLI run on a fixture input diffed against a known-good snapshot; a headless browser script asserting on DOM, console or network; a captured trace or payload replayed through the code path in isolation; a throwaway harness that runs only the failing path; a property or fuzz loop for "sometimes wrong"; a `git bisect run` harness between two known states; a differential run of old against new; last, a scripted human-in-the-loop step. Then tighten it: faster (skip unrelated setup, narrow scope), sharper (assert the specific symptom, not "didn't crash"), deterministic (pin time, seed randomness, isolate filesystem and network). For a flaky bug the goal is a higher reproduction rate (loop it, parallelise, add stress), not a clean repro. If no loop can be built, stop, say what you tried, and ask for the environment, a captured artifact, or permission to instrument. Phase 1 is done when you can name one command you have already run that goes red on the bug.

**Redact before you show.** Commands, outputs and captured artifacts carry secrets and auth headers: write `<REDACTED>` in their place, keep credentials in the environment rather than in what you show, and quote only the lines that carry the signal.

```
1. Reproduce the issue reliably
   - Minimal reproduction case
   - Consistent reproduction steps
   - Document environment/conditions

2. Gather evidence
   - Error messages (full stack traces)
   - Logs (with timestamps and context)
   - State at failure point
   - Input data that triggers issue

3. Form hypothesis
   - Based on evidence, not guesswork
   - Specific and testable
   - Includes mechanism of failure
```

**Example**:
```
Bug: User authentication fails intermittently

Investigation:
1. Reproduced: Fails every ~10th login attempt
2. Evidence:
   - Error: "Invalid token signature"
   - Logs show token created at 14:32:15, validated at 14:32:17
   - Server logs show time drift between auth & API servers
3. Hypothesis: Clock skew causing token validation failures
   - Auth server: 14:32:15
   - API server: 14:32:10 (5 seconds behind)
   - Token "not yet valid" due to nbf (not before) claim
```

### Phase 2: Pattern Analysis
**Goal**: Understand if this is isolated or systemic

```
1. Check for similar issues
   - Same error in other places?
   - Same pattern in related code?
   - Recurring in error logs?

2. Identify scope
   - One function or entire subsystem?
   - One user or all users?
   - One environment or all?

3. Find common factors
   - Timing (time of day, duration)?
   - Data characteristics?
   - Execution path?
```

### Phase 3: Hypothesis Testing
**Goal**: Prove understanding with experiments

```
1. Design tests that prove/disprove hypothesis
2. Add instrumentation if needed
3. Run experiments systematically
4. Document results
```

**Example Tests**:
```typescript
// Hypothesis: Clock skew causes token failures

// Test 1: Artificially set server clocks in sync
// Result: No failures in 100 attempts

// Test 2: Increase token nbf tolerance to 10 seconds
// Result: No failures in 100 attempts

// Test 3: Log exact time delta when failures occur
// Result: All failures show 4-6 second clock difference

// Conclusion: Hypothesis confirmed
```

### Phase 4: Implementation
**Goal**: Fix root cause, not symptoms

```
1. Address root cause
   - Fix underlying issue
   - Not just surface symptoms

2. Add safeguards
   - Validation
   - Error handling
   - Monitoring

3. Verify fix
   - Reproducer no longer triggers issue
   - Related edge cases handled
   - No new issues introduced

4. Clean up
   - Keep the Phase 1 loop as a regression test where a seam allows
   - Remove temporary instrumentation, debug logging and scratch harnesses
```

## Reference Material

- **Common root causes** (race conditions, shared state, off-by-one, timezones): See [references/common-root-causes.md](references/common-root-causes.md)
- **Advanced techniques** (core dumps, network debugging, profiling): See [references/advanced-techniques.md](references/advanced-techniques.md)

## Debugging Checklist

```
[ ] Can you reproduce the issue reliably?
[ ] Do you have the full error message and stack trace?
[ ] Do you know the exact input that triggers the issue?
[ ] Have you checked recent changes (git log)?
[ ] Have you verified your assumptions with logging?
[ ] Have you isolated the failing component?
[ ] Do you understand WHY it fails (not just WHERE)?
[ ] Have you tested your fix against the reproducer?
[ ] Have you added tests to prevent regression?
[ ] Have you checked for similar issues elsewhere?
```

