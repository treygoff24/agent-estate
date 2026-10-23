# Integrity

A hill-climb optimizes whatever the metric command measures, including its blind spots. Under pressure to move a number, the easiest path is often to change what gets measured instead of what gets done. These guards keep the number honest.

## Guardrails

A guardrail is a condition the climb holds constant while the target moves. Each one needs a check that runs every round, not an intention:

- **Correctness:** the project's tests pass. Use the full gate, not a subset, when the metric is anything other than test time itself.
- **Same behavior:** output unchanged, checked with byte comparison or a hash of the program's output on fixed inputs, screenshots for UI, response bodies for a service.
- **Other resources:** the metrics that must not regress (memory while cutting time, time while cutting memory). Put them in the metric command's JSON so every row carries them, and read them each round.

Pass the check as `--guard`. `hc` runs it once after each label's reps (in `hc ab`, on the candidate side only, unless `--guard-a`), records pass or fail, and a failed candidate guard overrides every other verdict.

## The held-out check

Every round, you read profiles of the benchmark workload and change code to make that workload cheaper. Over many rounds the changes fit that workload specifically, and some won't help anything else. The held-out check is a second workload you never tune on and run only at the end (Step 6):

| Tuned on | Held-out check |
| --- | --- |
| One slow test file | The full suite |
| One input size or dataset | A different size, or a production-shaped sample |
| One page of a site | The other page templates |
| One endpoint under synthetic load | A replay of real traffic |
| Local build | CI or the live deployment |

If the gain doesn't carry over, report that as the result. Don't quote only the tuned number.

## The harness lock

`hc approve` hashes the metric, guard, and held-out commands, the files listed with `--harness`, and `hc` itself, in every directory it measures. A later change to any of them stops measurement. Put on the harness list every file that decides what gets measured: benchmark scripts, fixtures, test configuration, the guard's own files, and CI config when the metric runs there. When the harness genuinely has to change (a bug in it, a better metric), stop, show the owner the diff, and after their OK re-approve and re-measure the kept baseline under the new harness. Numbers from before and after a harness change never share a table.

## Ways a benchmark gets gamed

Each of these makes the number move while the real work stays the same or gets worse. Before keeping a change, confirm it does none of them:

- **Doing less work:** skipping or deselecting tests, lowering the iteration count, truncating the input, catching and swallowing an error so a failing path returns early.
- **Changing the measurement:** editing the benchmark, fixture, timer, or test configuration; moving setup outside the timed region; excluding the slow case from the percentile.
- **Recognizing the benchmark:** special-casing the benchmark's inputs, hard-coding or precomputing its answers, caching across reps so later reps measure a warm result the real workload never sees.
- **Moving cost somewhere unmeasured:** deferring work to after the timer stops, to a background thread the benchmark doesn't wait for, to build time, or to the first real request.
- **Trading away a guardrail the checks miss:** less precision, weaker durability (skipping fsync), dropped validation, lower security settings, lost observability.

Some of these are legitimate when the owner chooses them, such as moving work to build time or turning down a log level. Treat them as proposals: name the trade, and keep the change only after the owner agrees.

## When a win looks too good

A gain far larger than the change could plausibly explain is a measurement bug until shown otherwise. Before keeping it:

1. Explain the mechanism. Point at the profile or trace line that got cheaper and check that its size roughly matches the gain.
2. Check the rows: every rep exit 0, the secondary metrics as expected, the work count unchanged (tests run, requests served, bytes out).
3. Re-run the comparison. A real gain repeats.
4. Run the guard and a slice of the held-out check early.

If you can't point to what got cheaper, don't keep it.
