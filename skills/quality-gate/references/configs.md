# Verbatim configs — Next 16 / TS / Tailwind v4

Passed a real agent-built repo end-to-end. Starting point; calibrate from it.

## package.json scripts

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "format": "oxfmt src",
    "format:check": "oxfmt --check src",
    "lint": "oxlint --deny-warnings",
    "typecheck": "tsc --noEmit",
    "react:doctor": "react-doctor . --yes --lint --blocking error",
    "design:detect": "impeccable detect src",
    "content:lint": "python3 scripts/lint-content.py",
    "gate": "npm run format:check && npm run lint && npm run typecheck && npm run react:doctor && npm run design:detect && npm run content:lint"
  }
}
```

Drop `content:lint` if there's no content/data contract. Order matters: cheapest and most-likely-to-fail stages first (format, lint, types) so a broken tree fails in seconds, not after the slow design scan.

## .oxlintrc.json

```json
{
  "categories": {
    "correctness": "error", "suspicious": "error", "perf": "error",
    "pedantic": "error", "style": "error"
  },
  "plugins": ["react", "typescript", "unicorn", "oxc", "import", "jsx-a11y", "nextjs", "promise"],
  "env": { "browser": true, "node": true },
  "rules": {
    "sort-keys": "off", "sort-imports": "off", "no-magic-numbers": "off",
    "max-lines-per-function": "off", "id-length": "off", "func-style": "off",
    "no-ternary": "off", "max-depth": "off", "unicorn/filename-case": "off",
    "react/react-in-jsx-scope": "off", "react/jsx-max-depth": "off",
    "import/no-named-export": "off", "import/prefer-default-export": "off",
    "import/no-unassigned-import": ["error", { "allow": ["**/*.css"] }],
    "new-cap": "off", "capitalized-comments": "off"
  },
  "ignorePatterns": ["node_modules", ".next", "out", "content", "docs", "public-assets"]
}
```

## doctor.config.json

```json
{
  "ignore": ["content/**", "docs/**", "public-assets/**", "scripts/**", ".next/**", "node_modules/**"]
}
```

Clear `node_modules/.cache/react-doctor` after any edit to this file.

## pre-commit hook (.git/hooks/pre-commit)

```sh
#!/bin/sh
npm run gate || { echo "gate failed — fix before commit (never --no-verify)"; exit 1; }
```

`chmod +x` it. Runs in ~2-3s on a small repo.
