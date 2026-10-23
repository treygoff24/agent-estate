# Stalls

The round loop assumes the next change will make the target cheaper. Once the obvious costs are gone, that stops being true. What's left is spread across many small costs, sits in the harness rather than the code, or is below what the measurement can resolve. The sign is two or three rounds in a row landing WITHIN NOISE, or BETTER, BELOW MIN EFFECT, despite changes that should have helped. Stop making changes and spend one round sorting instead.

## Sort what's left

Profile the current kept state again from scratch; the profile from Step 4 is stale. Put the remaining cost into buckets:

| Bucket | How it shows | What to do instead of another code round |
| --- | --- | --- |
| **One big cost left** | One path still dominates the profile | Not a stall. Attack it, possibly with a larger structural change than earlier rounds tried. |
| **Long tail** | Dozens of small costs, none above the minimum effect | Stop here, or do one broad round: several independent small fixes applied together, kept or reverted as a group. This deliberately breaks one-hypothesis-per-round, because no single fix can be measured alone. |
| **Fixed floor** | Time spent in things outside scope: process startup, the network, a dependency, the runtime, the hardware | Report the floor with its number. Offer to widen scope if the owner wants to go further. |
| **Measurement** | Changes that should matter don't register; reps are bimodal; the unchanged-vs-unchanged comparison has drifted | Fix the harness per `measurement.md`, re-approve with the owner, and re-baseline. |
| **Wrong target** | The number moves but the thing people complain about doesn't | Go back to the owner with the evidence and propose a different target. |

Write the bucket counts and their costs in the journal as that round's entry.

## Change the target or stop

When the target has plateaued, check the guardrail metrics for one with room to improve (memory after time, or p99 after the median). Propose switching to it, holding what's already won, but ask first: the owner set the goal and may consider it done. Otherwise report the best so far and stop. Saying "this is where it ends, and here's why" with numbers is a finished climb.
