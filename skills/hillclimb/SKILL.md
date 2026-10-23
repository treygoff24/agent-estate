---
name: hillclimb
description: >-
  Hill-climb: improve one measurable number in measured rounds (app, service or
  CLI speed, test-suite or build time, memory, bundle or binary size, throughput,
  cost) by keeping only changes that clear the noise floor while guardrails hold.
  Also resume a climb, or audit a claimed speedup.
---

# Hill-climb

Move one number (the **target**) with a sequence of **rounds**. Each round makes one change and measures it against the last **kept** state. The change stays only when the gain clears the **noise floor** and the **minimum effect**, and every **guardrail** holds. Every round, kept or reverted, goes in the **journal**.

## Other harnesses

Two domains already have better-fitted harnesses. Use them, and apply this skill's integrity rules on top:

- **Website load time, Lighthouse, Core Web Vitals:** a dedicated web-performance skill or Lighthouse itself, with throttled profiles, repeat-visit and scroll byte counts, and exact pixel diffs.
- **Prompts, skills, tool descriptions, model or effort choice, anything graded from model output:** an eval harness: build graded cases and a train/test split first when there is no eval yet, then hillclimb against it.

## Bundle map

Only this file loads with the skill. Read the others when a step sends you there.

| Path | Holds | Read it |
| --- | --- | --- |
| `scripts/hc` | The measuring harness: repeated and interleaved runs, the noise verdict, the harness lock, fingerprints. `hc --help` is its full usage. | Step 2 onward |
| `references/measurement.md` | Noise, reps and their time cost, interleaving, environment control, choosing the metric command | Steps 2–3, and whenever a verdict surprises you |
| `references/integrity.md` | Guardrails, the held-out check, the harness lock, the ways a benchmark gets gamed, what to do when a win looks too good | Step 1, and before keeping any large win |
| `references/domains.md` | Per-domain recipes: metric command, guardrail, held-out check, where the cost hides, first levers | Step 1 |
| `references/stalls.md` | Sorting the remaining cost by cause when rounds stop moving | After two or three rounds inside the noise |

Paths are relative to this skill's folder. Set `HC=<this skill's folder>/scripts/hc` (Python 3, stdlib only).

## Steps

### 1. Frame

Agree on these with the person who asked, proposing a default for each so they can just say yes:

- **Target:** one metric, its direction, and the workload, stated as what a user or operator actually waits for or pays for.
- **Minimum effect:** the smallest gain worth keeping a change for, such as 3%. It filters out real but trivial wins that add complexity.
- **Guardrails:** what must not get worse, each with the check that proves it. Default: the project's full check passes and behavior is unchanged.
- **Held-out check:** a workload you won't tune on, run at the end. For example, tune on the slowest test files and confirm on the full suite. `references/integrity.md` explains why.
- **Scope:** what may change, and what's off-limits.
- **Stopping rule and budget:** a round count, "until three rounds in a row land inside the noise," or a cap on time. Price a round first. It costs about 2 × (reps + warmup) × one workload run, plus a guard run. At 10 reps, a 4-minute suite costs about 90 minutes per round. That's why a slow workload gets a narrower one for the loop (`references/measurement.md`, Reps).

Read `references/domains.md` for the matching recipe. Choosing the loop workload may need a first look at where the cost goes (`pytest --durations=30`, a quick profile). Do that now, because the workload gets locked in Step 2.

Done when every item above is agreed. They go in the journal's Setup section once Step 2 creates it.

### 2. Harness

Write the **metric command**. It runs the workload once and exits non-zero on failure. Its wall time is measured by `hc` (metric `wall_s`), or it prints a JSON object on its last stdout line with the metric in it. Any other numbers in that JSON (a test count, peak memory) are recorded too, and shown beside every comparison. Put it in a script file.

Commit the metric script and every other harness file (fixtures, benchmark config) first. Then create the worktrees, so each one carries the same harness:

- a **candidate** on a new branch: `git worktree add -b hillclimb/<name> <dir>`
- a **kept** worktree at the same commit: `git worktree add --detach <dir> HEAD`

Put both outside anyone else's checkout, and give each its own dependencies: venv, `node_modules`, build output. Check that each one imports code from its own tree, not from the other one. When the workload runs compiled output, build both sides before every A/B, and leave the build out of the timed command unless build time is the target. Write the starting commit in the journal. Step 6 measures against it.

From the candidate worktree's root, initialize and lock:

```bash
$HC init <name> --cmd 'bash bench/run.sh' --metric wall_s --direction lower \
  --min-effect 3% --guard '<guardrail check>' --holdout '<held-out command>' \
  --harness bench/ --reps 10
$HC approve
```

`init` creates `.hillclimb/<name>/` with `state.json` and a `journal.md` skeleton. Measurements go in its `runs/` folder, which is gitignored. Run every later `hc` command from that root, or pass `--flow .hillclimb/<name>`.

`approve` locks the harness: the three commands, every `--harness` path (a directory counts as all the files under it), and `hc` itself. `hc run` and `hc ab` then refuse to measure any directory whose copies differ. You approve once at setup and say so in your reply. After that, only the person who owns the climb re-approves, because numbers from a changed harness can't be compared with earlier ones.

Then prove the metric responds. In the candidate worktree, plant a known cost in the code being measured, never in a harness file. A `sleep` or a doubled loop works. Run `$HC ab plant-k plant-e --a <kept> --b <candidate> --reps 5`, then `$HC compare plant-k plant-e`. It must read WORSE at about the size you planted. Remove the plant afterward.

Done when the journal's Setup section is filled in, the planted regression reads WORSE, and `$HC status` shows the harness locked.

### 3. Baseline and noise floor

Measure the untouched code against itself: `$HC ab base base-r2 --a <kept> --b <kept>`, then `$HC compare base base-r2`. The verdict must be WITHIN NOISE, and its CI half-width is the **noise floor** at this rep count. If the floor is bigger than the minimum effect, no round can prove anything. Fix the measurement first; `references/measurement.md` lists the fixes in order of cost.

Done when the journal records the baseline median and the noise floor, and the floor is below the minimum effect.

### 4. Diagnose

Find where the cost actually goes, with the profiler, trace, or waterfall that fits the domain (`references/domains.md`). Produce a ranked hotspot table from the profiler output (a dedicated profiling skill helps if you have one). Rank candidate changes by expected gain, capped by the share of the target each one attacks, and list them in the journal.

Done when each candidate names the measured cost it attacks, with a number from a profile or trace.

### 5. Rounds

One **hypothesis** per round. A change may touch several files, but only in service of one idea about why the number is what it is.

1. Make the change in the candidate worktree. Label the round `eN-<what>`.
2. Measure it against the kept state in the same session: `$HC ab kept-eN eN-<what> --a <kept> --b <candidate>`, then `$HC compare kept-eN eN-<what>`. Re-measure the kept side every round. Earlier numbers have drifted.
3. **Keep** only on BETTER (exit 0). That means the interval clears zero on the better side, the effect meets the minimum, the candidate's guard passed, and no rep failed. Also read the "also" lines: a change that helps the target can hurt another number, or quietly run fewer tests.
4. If kept: commit the change alone, with the before and after medians and the interval in the message. Then run `git -C <kept> checkout --detach <commit>`.
5. If not kept: `git -C <candidate> checkout -- <the files you changed>`.
6. Either way, write the journal entry: the hypothesis, the change, the numbers, the verdict, and what it taught you.

After two or three rounds in a row inside the noise, stop changing code and read `references/stalls.md`. Before keeping a win much larger than the change should plausibly give, work through `references/integrity.md`, "When a win looks too good".

Done when the stopping rule fires, or every ranked candidate is tried or written under "Considered, not pursued" with its reason.

### 6. Confirm and hand back

- Run the held-out check against the starting commit. Add a worktree there (`git worktree add --detach <dir> <start commit>`), then `$HC ab base-h final-h --holdout --a <that worktree> --b <kept>` and compare. If the gain doesn't carry over, the climb tuned to its benchmark. Report that as the result.
- Run the project's full gate on the final state.
- Fill in the journal's Result section: the target at start and end with the interval, each kept change with its gain, the held-out result, what was dropped and why, and the levers still untried.
- Commit `.hillclimb/<name>/journal.md` and `state.json` on the branch, then remove the worktrees you created.

Done when the held-out result and the full gate are in the journal. The final reply leads with the held-out change and names what wasn't verified.

## Resuming and long runs

A resumed session reads `.hillclimb/<name>/journal.md` and runs `$HC status` before touching anything. Start a measurement that takes minutes as a background job, and give it `--flow` with an absolute path, since a background job runs in the session's working directory. `hc` prints one progress line per rep to stderr (`hc: e3-cache rep 4 exit 0 61.2s`). Check those lines, and the full output in `runs/<label>.log`, before deciding a job is stuck.
