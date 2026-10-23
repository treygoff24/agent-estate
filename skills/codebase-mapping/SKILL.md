---
name: codebase-mapping
description: >-
  Systematically explore an unfamiliar codebase to build a working mental model,
  and optionally persist it as a durable architecture document. Use when
  onboarding to a new project, "what does this do", understanding legacy code,
  "write up the architecture", or producing a handoff doc. A working model for yourself;
  an audit's findings are codebase-audit, a client-facing cold read is build-audit.
---

# Codebase Mapping

> **Core: documentation first, then follow data flow from the entry points outward.** Random file reading wastes context and builds a fuzzy map. Trace the real flow and you get a model you can act on.

Two outputs, same exploration. Stop at the mental model when you just need to work in the code; produce the written report when the understanding has to survive context compaction or hand off to someone else. Understanding is ephemeral; a doc isn't.

## Explore (build the model)

1. **Docs first.** Read `AGENTS.md`/`CLAUDE.md` and `README.md` completely before any code — they carry architecture notes, decisions, and gotchas you'd otherwise rediscover the slow way. Read the manifest (`Cargo.toml`/`package.json`/`pyproject.toml`/`go.mod`) for dependencies and entry points.

2. **Entry points.** Find where execution starts and fan out from there:
   ```bash
   rg "fn main|func main|def main|if __name__|export default" 
   rg "clap|cobra|argparse|click|typer|commander|yargs"   # CLI dispatch
   rg "Router|routes|app\.(get|post)|@app\.|FastAPI|axum|fastify"  # HTTP
   ```

3. **The 3–5 key types** everything revolves around — the domain objects the rest of the code orbits:
   ```bash
   rg "^(pub )?(struct|class|interface|type|enum) \w+"
   ```

4. **Trace one path end to end:** entry → handler/dispatch → core domain logic → storage/integration. Read the key functions along that path; skim the rest. The layers are almost always entry points → handlers → core domain → storage/external integration.

5. **The edges:** config (env vars, config files, CLI flags, and their precedence), external integrations (HTTP clients, DB queries, file I/O), and what the tests reveal about intended behavior.

For a large codebase (>10K LOC), spawn an `Explore` subagent to read broadly and return a synthesized map instead of filling your context with raw files. Give it the same five targets above.

## Report (persist the doc)

When the model needs to outlive the session, write it as markdown with `file:line` references so a reader (human or agent) can jump straight to evidence. Match depth to purpose — a quick orientation is ~150 lines; a full onboarding doc fills every section; an audit-grade doc adds diagrams and traces every path.

```markdown
# <Project> — Architecture

## Summary
<what it is + key stats: ~LOC, language, the handful of load-bearing deps> 

## Entry points
| Entry | Location | Purpose |

## Key types
| Type | Location | Purpose |

## Data flow
<ascii diagram + 2 sentences: entry → processing → storage>

## External dependencies
| Dependency | Purpose | Critical? |

## Configuration
| Source | Precedence | Example |

## Test infrastructure
| Type | Location | What it covers |
```

## Anti-patterns

- Skipping `AGENTS.md`/`README` — you re-derive documented knowledge the hard way.
- Reading files at random instead of following entry → data flow.
- Reading whole files when you need the structure plus the few key functions.
- Stopping at understanding when the work will outlast your context — write the doc.
- Vague prose instead of `file:line` references — the doc has to point at evidence to be useful.

## When to use what

Brand-new repo → full explore. Adding a feature → trace the nearest existing analogue. Fixing a bug → trace from symptom to root. One module → start at its public API. Anything that hands off or that you'll revisit after a compaction → produce the report.
