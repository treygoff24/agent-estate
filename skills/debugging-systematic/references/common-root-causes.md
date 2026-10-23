# Common Root Causes

## 1. Race Conditions
```typescript
// Symptom: Intermittent failures, works in debugger
// Root cause: Async operations completing in wrong order

// Bad
let userData = null;
fetchUser().then(data => userData = data); // Async
sendEmail(userData.email); // Runs before fetch completes!

// Fixed
const userData = await fetchUser();
sendEmail(userData.email);
```

## 2. Shared Mutable State
```typescript
// Symptom: Tests pass individually, fail together
// Root cause: Tests sharing state

// Bad - shared state
const cache = {}; // Global
test('test1', () => { cache.foo = 'bar'; });
test('test2', () => { expect(cache.foo).toBeUndefined(); }); // Fails!

// Fixed - isolated state
test('test1', () => {
  const cache = {};
  cache.foo = 'bar';
});
test('test2', () => {
  const cache = {};
  expect(cache.foo).toBeUndefined();
});
```

## 3. Incorrect Assumptions
```typescript
// Symptom: Crashes with certain inputs
// Root cause: Assumed data always present

// Bad - assumes email exists
function sendWelcome(user) {
  sendEmail(user.email); // Crashes if email is null
}

// Fixed - validate assumptions
function sendWelcome(user) {
  if (!user?.email) {
    logger.warn('Cannot send welcome email', { userId: user.id });
    return;
  }
  sendEmail(user.email);
}
```

## 4. Off-by-One Errors
```typescript
// Symptom: Array index errors, missing last item
// Root cause: Loop boundary wrong

// Bad
for (let i = 0; i < array.length - 1; i++) { // Misses last element
  process(array[i]);
}

// Fixed
for (let i = 0; i < array.length; i++) {
  process(array[i]);
}
// Or better: array.forEach(process);
```

## 5. Timezone Issues
```typescript
// Symptom: Date calculations wrong for some users
// Root cause: Not handling timezones

// Bad
const deadline = new Date('2024-01-01'); // Midnight in what timezone?

// Fixed
const deadline = new Date('2024-01-01T00:00:00Z'); // Explicit UTC
// Or use library: dayjs.utc('2024-01-01')
```
