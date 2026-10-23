# Quality gate rubric

Use this rubric for every worker result and every local test patch. Passing tests are not enough.

## Required questions

- What behavior, contract, or invariant does this protect?
- Would the test fail if that behavior regressed?
- Is this the cheapest layer that can prove the behavior?
- Did the test preserve the real seam that carries the risk?
- Are mocks limited to true external boundaries?
- Are waits condition-based and deterministic?
- Are fixtures isolated and readable?
- Is the failure message useful?
- Is runtime acceptable for the confidence gained?
- Would this test still be worth keeping in six months?

## Strong vs weak

| Dimension | Strong | Weak |
| --- | --- | --- |
| Behavior focus | User-visible, contract-visible, or invariant-visible outcome | Private internals, hook calls, DOM trivia, mock-call-only assertions |
| Layer choice | Cheapest layer that proves behavior | Unit when runtime semantics matter, E2E for trivial pure logic |
| Boundary realism | Real framework/runtime/auth/db/http seam where it matters | Mocks away the seam being tested |
| Flake resistance | Controlled time/data, condition waits, isolated state | Sleeps, live networks, shared state, order dependence |
| Reviewability | Clear setup, narrow assertions, useful names | Opaque fixtures, huge snapshots, unclear intent |
| Ongoing value | Protects top flow, bug, invariant, or public contract | Adds noise to satisfy coverage percentage |

## Automatic rejection list

Reject tests that:

- Only prove a component renders.
- Snapshot broad DOM trees or API blobs without narrow reviewable purpose.
- Spy on implementation calls when an observable result exists.
- Mock router/auth/db/http so thoroughly that the target risk is absent.
- Use `sleep`, `wait(1000)`, or arbitrary timers where a condition exists.
- Depend on test order or mutable global fixtures.
- Hit live third-party networks in unit/component tests.
- Test third-party library behavior instead of the project's use of it.

## Repair moves

- Replace render/existence checks with user action + visible/resulting state.
- Replace internals assertions with output, status, persistence, event, or navigation assertions.
- Move up a layer when mocking is excessive.
- Move down a layer when E2E is only proving pure logic.
- Introduce factories/builders to keep setup readable.
- Control time/randomness/filesystem/network deterministically.
