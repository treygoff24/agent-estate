---
name: fenced-blocks
description: Fenced shell and JSON blocks must never read as stacked prose.
---

# Fenced blocks fixture

This fixture proves the document passes skip fenced code. The shell and JSON blocks below carry blank-line-separated segments that the old paragraph pass counted as stacked prose, and a regression scan must stay clean on all of them.

```sh
set -eu
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates

curl -fsSL https://example.invalid/install.sh -o /tmp/install.sh
sh /tmp/install.sh
```

A prose bridge between the fences keeps the document mixed, the way a real plan interleaves commands with rationale for each rollout step. It also resets any paragraph run the scanner might be tracking.

```json
{
  "name": "sample-project",
  "version": "1.0.0",
  "private": true
}

{
  "scripts": {
    "build": "tsc -b",
    "test": "node --test"
  },
  "engines": {
    "node": ">=20"
  }
}
```

Final prose paragraph: one clean sentence, safe on its own.
