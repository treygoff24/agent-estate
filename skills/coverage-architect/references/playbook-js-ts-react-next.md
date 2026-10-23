# JS, TS, React, and Next.js playbook

## Defaults

- Preserve existing Jest/Vitest/Node runner choice unless it is absent or broken.
- Prefer Vitest for modern Vite/TS-first projects.
- Prefer existing Jest in established Jest or `next/jest` projects.
- Consider `node:test` for minimal Node libraries/CLIs without browser needs.
- Use Testing Library semantics for React: role/name/label/text before test IDs.
- Use `user-event` for user interactions.
- Use MSW for HTTP seams in unit/component/integration tests.
- Use Playwright for critical browser journeys unless the repo is Cypress-centered.

## High-value React tests

Prioritize:

- User can complete task.
- Validation prevents incorrect action and explains why.
- Async states show pending/success/empty/error behavior.
- Keyboard and accessible roles/names work.
- Optimistic UI reconciles or rolls back.
- Error boundaries show useful fallback when that is product behavior.

Reject shallow/implementation tests that only assert hook calls, child props, class names, or render existence.

## Next.js App Router guidance

- Test Client Components and synchronous render logic with Jest/Vitest when cheap.
- For async Server Components, server rendering, cookies, redirects, caching, and runtime semantics, prefer E2E or request-level seam tests.
- Route Handlers are HTTP contracts: test status, body/schema, headers, auth, validation, caching/idempotency/webhook signatures where relevant.
- Server Actions: cover validation, authz/authn, redirect semantics, cookie mutation, and origin/CSRF-sensitive behavior where applicable.
- Middleware/Proxy: detect both `middleware.*` and `proxy.*`; extract pure decision logic when useful, but verify end behavior at request/browser boundary.
- Do not fix router-context problems by mocking everything. Use the proper provider/context or move up to navigation-level tests.

## TypeScript-specific coverage

For libraries and SDKs, include type-level tests when public types are part of the contract:

- Vitest `*.test-d.ts`, `expectTypeOf`, or `assertType`.
- `tsd` if the repo already uses it or public `.d.ts` compatibility is central.

## Good scenarios

- Protected route redirects anonymous user and allows authenticated user.
- Form rejects invalid input, announces error, enables submit after correction.
- API route rejects invalid payload and returns documented status/body.
- Client retries or error state renders after MSW-controlled failure.
- Locale/i18n route preserves behavior across supported languages.
- Server Action persists state and redirects with correct user-visible result.
