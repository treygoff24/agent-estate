# Source notes

This skill was drafted from the following source families. Re-check these when making major changes.

- Clap crate docs: https://docs.rs/clap/latest/clap/
- Clap derive tutorial and reference: https://docs.rs/clap/latest/clap/_derive/_tutorial/index.html and https://docs.rs/clap/latest/clap/_derive/index.html
- Clap FAQ on derive vs builder APIs: https://docs.rs/clap/latest/clap/_faq/index.html
- Clap feature flags: https://docs.rs/clap/latest/clap/_features/index.html
- Clap ValueParser docs: https://docs.rs/clap/latest/clap/builder/struct.ValueParser.html
- Clap cookbook: https://docs.rs/clap/latest/clap/_derive/_cookbook/index.html
- clap_complete: https://docs.rs/clap_complete/latest/clap_complete/
- clap_mangen: https://docs.rs/clap_mangen/latest/clap_mangen/
- trycmd: https://docs.rs/trycmd/latest/trycmd/
- Command Line Applications in Rust book: https://rust-cli.github.io/book/
- Agent Skills specification: https://agentskills.io/specification
- Claude Code skills docs: https://code.claude.com/docs/en/skills
- Claude skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Codex Agent Skills docs: https://learn.chatgpt.com/docs/build-skills
- Codex AGENTS.md docs: https://learn.chatgpt.com/docs/agent-configuration/agents-md

## For the synthesized reference set

This skill consolidates several earlier skills into one canonical agent-CLI builder. The added references draw on:

- Design principles & error-rewriting (`references/design-principles.md`): general agent-ergonomics and MCP-server-design skills (see `RECOMMENDED-UPSTREAM.md`).
- Doctor/health/fix command (`references/doctor-mode.md`): the `cli-doctor-mode` skill.
- Durable state & idempotency (`references/state-and-persistence.md`): the `rust-cli-with-sqlite` skill; rusqlite docs https://docs.rs/rusqlite/ ; SQLite WAL/PRAGMA docs https://www.sqlite.org/wal.html and https://www.sqlite.org/pragma.html
- Headless auth (`references/headless-auth.md`): the `saas-cli-auth-flow` skill; `std::io::IsTerminal` https://doc.rust-lang.org/std/io/trait.IsTerminal.html
- Distribution & agent auto-config (`references/distribution.md`): the `installer-workmanship` skill; cargo-dist https://opensource.axo.dev/cargo-dist/ ; cargo-binstall https://github.com/cargo-bins/cargo-binstall
- assert_cmd / assert_fs (black-box tests): https://docs.rs/assert_cmd/ and https://docs.rs/assert_fs/
