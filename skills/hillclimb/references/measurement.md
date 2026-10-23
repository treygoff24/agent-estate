# Measurement

How to get numbers the verdict can trust. Read it while building the harness, and again whenever a verdict surprises you.

## What `hc compare` computes

- **Paired mode** (labels measured together by `hc ab`) compares each A rep with the B rep that ran beside it. `hc ab` alternates order A B, B A, A B, and so on, which cancels drift that builds up over a run (thermal throttling, a growing cache, a neighbour's job). The per-pair change is the log ratio `ln(B/A)` when every value is positive, otherwise the plain difference `B − A`. The median of those, bootstrapped 10,000 times with a fixed seed, gives the change and a 95% interval.
- **Unpaired mode** (labels from separate `hc run` calls) compares the two medians and bootstraps each side independently. It can't tell your change from drift between the two sessions, so it warns when the runs are more than an hour apart or on different hosts. Use it for quick looks, and use `hc ab` for any keep decision.
- **Verdict:** BETTER when the interval lies wholly on the better side and the effect meets the minimum effect. BETTER, BELOW MIN EFFECT when it's real but too small. WORSE when the interval lies wholly on the worse side. WITHIN NOISE otherwise. GUARD FAILED (the candidate's guard) or FAILED REPS (the candidate's) override all of these; failed reps on the kept side show as a note. `hc compare` exits 0 on BETTER and 1 on every other verdict. `hc run` and `hc ab` exit 3 when the harness lock is missing or changed.
- **Noise floor:** the CI half-width of an unchanged-vs-unchanged comparison (`base` vs `base-r2`). It shrinks roughly with the square root of the rep count: four times the reps, half the floor.

## Reps

- Start at 10 reps for timings under a minute, 5 for longer ones, and 20 or more when the floor is close to the minimum effect.
- **Price it.** One `hc ab` round runs the workload 2 × (reps + warmup) times, plus the guard once. At 5 reps, a 4-minute suite costs about 50 minutes per round. For a slow workload, loop on a narrower one (the slowest files, one representative job) that takes seconds, and keep the full workload for the held-out check. That usually improves the noise too.
- Add reps to a label with `hc run <label> --append` or `hc ab ... --append`. Both sides need the same treatment, so append to A and B together through `hc ab`.
- Below 5 reps a side, the bootstrap interval is too optimistic; `hc` notes it.
- A warmup rep runs first and is discarded (`--warmup`, default 1). Raise it when the first several runs are slow: JIT compilation, disk cache, lazy compilation, connection pools.

## Quieting the machine

Noise you remove is cheaper than noise you average away.

- **Other load.** `hc` warns when the load average exceeds half the CPU count. On a shared box, other agents' builds and tests share the CPUs, so check `uptime` before a keep decision, and re-run when it's busy.
- **Laptop.** Low Power Mode and thermal throttling slow later reps. Interleaving cancels that drift but still widens the noise.
- **Caches between reps** (`__pycache__`, `.pytest_cache`, build and bundler caches, OS file cache): decide whether the metric is cold or warm, and make every rep the same.
- **Cold or warm, decide which.** A cold-start metric has to clear the relevant cache every rep (restart the service, `purge` on macOS, a fresh temp dir). A warm metric needs warmups. Mixing the two produces bimodal data: a few reps far from the rest. Look at the min and max `hc run` prints.
- **Pin what you can.** Fixed seeds, fixed input files, fixed thread or worker counts. Offline where possible: network variance swamps most code changes.
- **Shared resources.** Both worktrees must not share a database, port, or temp directory that one side's run leaves in a different state for the other. Give each its own, or reset it in the metric command.
- **Flaky workloads.** A flaky test fails a rep, and failed reps block a keep. Fix or quarantine the flake with the owner's agreement before the baseline, and record which tests were quarantined.
- **Measure the narrowest thing that still means something.** A single slow test file beats the whole suite for the fast inner loop. Confirm on the full suite at the end.

## Choosing the metric command

- It runs the workload **once** and exits 0 on success. `hc` does the repetition, timing, and statistics.
- For a metric other than wall time, print a JSON object on the last stdout line: `{"p95_ms": 41.2, "rss_mb": 312}`. `hc` records every numeric key, and the one named by `--metric` drives the verdict. The rest show up in the rows for checking side effects.
- Prefer a metric the workload reports itself (a benchmark's own ns/op, a server's latency histogram) over wall time around a process that also pays startup cost, unless startup is part of what users wait for.
- Deterministic counts beat timings when they measure the same thing. Bytes shipped, allocations, queries per request, and instructions retired (`perf stat -e instructions` on Linux) have almost no noise, so one rep suffices. Confirm with a timing at the end, because a count is a proxy.
- Percentiles need enough samples inside each rep. A p99 from 200 requests is dominated by one or two of them.

## When a verdict surprises you

- **Bimodal reps** (look at min vs max): something alternates between two states, like cache hit vs miss or a GC firing or not. Find it and pin it before continuing.
- **The interval won't shrink with more reps:** drift within a session that interleaving doesn't cancel, or a metric that changes over time (a database that grows each run). Reset state inside the metric command.
- **The unchanged-vs-unchanged comparison doesn't read WITHIN NOISE:** order effects (the first directory measured is always slower), or the two directories aren't actually identical. Check `hc status` fingerprints: git head and dirty diff.
- **Other numbers moved.** `hc compare` prints an "also" line for every other number the metric command reported. `runs/<label>.jsonl` has every rep.
