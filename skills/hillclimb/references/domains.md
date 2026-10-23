# Domains

Starting recipes. Each gives a metric command shape, the guardrail, a held-out check, where to look for the cost, and the first levers. Adapt freely. The method in `SKILL.md` stays the same.

## Test-suite time

- **Metric:** `wall_s` around the suite command (`pnpm test`, `pytest -q`, `go test ./...`, `cargo test`). A failing test fails the rep, so the suite is its own correctness check.
- **Guardrail:** the same tests run and pass. Save the collected test list once (`pytest --collect-only -q | grep '::' > bench/tests.txt`, which drops the summary line and its timing; or the runner's own list mode) and make `--guard` diff a fresh collection against it; put `bench/` on the harness list. Also print the passed-test count as JSON on the metric command's last line, so a drop shows in every comparison.
- **Held-out:** tune on the slowest files, confirm on the whole suite. Confirm in CI too, where parallelism and caches differ.
- **Per-worktree setup:** each worktree gets its own virtualenv or `node_modules`. An editable install (`pip install -e`) must point at its own tree. Pin the worker count (`-n` for pytest-xdist) so both sides run the same parallelism.
- **Where the time goes:** per-test durations (`pytest --durations=30`, `go test -json` elapsed fields, the JSON reporters of vitest and jest), plus setup and teardown, collection or import time (`python -X importtime`), and per-worker imbalance: one worker finishing last sets the wall time.
- **Levers:** shared fixtures instead of per-test setup; in-memory or transaction-rollback databases; removing real sleeps and timeouts (fake timers); worker count and sharding balance; lazy imports; dropping duplicated coverage only with the owner's agreement, since that is removing tests.

## Build and typecheck time

- **Metric:** `wall_s` of a clean build and, separately, an incremental build after touching one representative file. They respond to different levers; climb the one people actually wait on.
- **Guardrail:** output unchanged. Hash the build directory, or diff the emitted files after normalizing timestamps.
- **Per-worktree setup:** each worktree gets its own virtualenv or `node_modules`. An editable install (`pip install -e`) must point at its own tree. Pin the worker count (`-n` for pytest-xdist) so both sides run the same parallelism.
- **Where the time goes:** `cargo build --timings`, `tsc --extendedDiagnostics` or `--generateTrace`, bundler profiles (`vite build --profile`, webpack's `--profile --json`), `go build -x`.
- **Levers:** cache configuration and hit rate, project references or workspace splitting, excluding generated or vendored code from typechecking, faster transpilers for dev builds, dependency trimming, parallelism.

## CLI, library, or batch-job runtime

- **Metric:** a fixed-input invocation, wall time or the program's own timing. Use a deterministic count (instructions, allocations) for the inner loop when noise is high.
- **Guardrail:** byte-identical output on a set of fixed inputs, hashed in `--guard`.
- **Held-out:** a different input size or shape: the 10× file, the pathological case, a real production sample.
- **Per-worktree setup:** each worktree gets its own virtualenv or `node_modules`. An editable install (`pip install -e`) must point at its own tree. Pin the worker count (`-n` for pytest-xdist) so both sides run the same parallelism.
- **Where the time goes:** a sampling profiler. `py-spy record`, `samply record`, `perf record` (Linux), Instruments (macOS), `go tool pprof`, `node --cpu-prof`. Then rank what it finds in a hotspot table.
- **Levers:** algorithmic first (the quadratic loop, repeated work, needless I/O), then allocation and copying, then I/O batching and buffering, then parallelism, and micro-optimizations last.

## Service latency and throughput

- **Metric:** a load generator at a fixed request rate (for latency) or fixed concurrency (for throughput), printing percentiles as JSON. Hold the load constant across rounds. Latency measured at saturation is mostly queueing.
- **Guardrail:** response bodies and status codes unchanged on a fixed request set; error rate zero.
- **Held-out:** replay of real traffic, or a different mix of endpoints.
- **Per-worktree setup:** each worktree gets its own virtualenv or `node_modules`. An editable install (`pip install -e`) must point at its own tree. Pin the worker count (`-n` for pytest-xdist) so both sides run the same parallelism.
- **Where the time goes:** request traces and spans, slow-query logs, profiler under load, connection pool wait times.
- **Levers:** query count per request (N+1), indexes, caching with an explicit invalidation story, payload size, connection reuse, moving work off the request path (a trade the owner signs off on; see `integrity.md`).

## Memory

- **Metric:** peak RSS from the metric command's own report, or from `/usr/bin/time -l` (macOS, bytes) or `/usr/bin/time -v` (Linux, KB), converted in the JSON to one unit. Or heap-in-use from the runtime's own stats.
- **Guardrail:** wall time must not regress past its noise. Memory wins often cost speed; put wall time in the JSON.
- **Where it goes:** heap profilers (`memray`, `heaptrack`, pprof heap, Chrome heap snapshots, Instruments Allocations).

## Size: bundle, binary, image

- **Metric:** bytes, compressed as served (brotli or gzip for web assets). Deterministic: one rep is enough and the noise floor is zero, so the minimum effect does all the filtering.
- **Guardrail:** behavior unchanged (the test suite, plus screenshots for UI).
- **Where it goes:** `source-map-explorer` or a bundle visualizer, `cargo bloat`, `go tool nm -size`, `docker history` or `dive` for images.
- **Levers:** dead dependencies, duplicate versions of one package, per-route code splitting, stripping symbols, smaller base images, multi-stage builds.

## Website load time

Use a dedicated web-performance harness (throttled Lighthouse runs). It handles throttling profiles, repeat visits, full-scroll bytes, and exact screenshot diffs, which this runner doesn't.

## Prompts, skills, model and effort choice

Build an eval first. Model output needs graded cases, a train and test split of those cases, and transcript reading. The integrity rules here still apply.

## Cost

Cost is usually a derived metric: requests × tokens × price, or instance-hours × rate. Measure the countable parts deterministically (tokens per task, queries per request, CPU-seconds per job), and hold quality or latency as the guardrail.
