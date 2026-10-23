# Recommended upstream skills (not included)

These are useful skills we deliberately did not copy into this pool, either because
their license is restrictive or not clearly stated, or because they teach one vendor's
product, or because they depend on a tool you install separately. Get them from the
source below, check the license yourself, and install with `skillherd install <owner/repo>`
(which records the upstream so `skillherd update` can refresh it) or by copying the folder
into your pool and naming it in `.globals/house`.

## Document skills (restrictive license: do not redistribute)

| Skill | Get it from | Note |
| --- | --- | --- |
| `docx`, `pdf`, `xlsx`, `pptx` | https://github.com/anthropics/skills | Published under a source-available license that restricts redistribution. Install from the source rather than vendoring. |

## Skills with an unclear license

| Skill | Get it from | Note |
| --- | --- | --- |
| `thermo-nuclear-code-quality-review` | https://github.com/cursor/plugins (`thermos/skills/thermo-nuclear-code-quality-review`) | No license file published at time of writing. A strict structural code review. |
| `agent-ergonomics-and-intuitiveness-maximization-for-cli-tools`, `documentation-website-for-software-project`, `security-audit-for-saas`, `codebase-audit`, `mock-code-finder`, `idea-wizard`, `gh-cli`, `e2e-testing-for-webapps` | https://jeffreys-skills.md | Distributed through a skills marketplace whose redistribution terms are not stated in the skill folders. |
| `profiling-software-performance`, `library-updater`, `reality-check-for-project` | https://github.com/oysteinkrog/dotfiles (`.claude/skills/`) | No license file at time of writing. |

## Vendor and product how-to packs

Generic in shape, but each teaches one product. Install the ones that match your stack.

| Skill | Get it from |
| --- | --- |
| `vercel-react-best-practices`, `web-design-guidelines` | https://github.com/vercel-labs/agent-skills |
| `shadcn` | https://github.com/shadcn/ui |
| `resend`, `email-best-practices` | https://github.com/resend/resend-skills, https://github.com/resend/email-best-practices |
| `better-auth-best-practices` | https://github.com/better-auth/skills |
| `userinterface-wiki` | https://github.com/raphaelsalaja/userinterface-wiki |
| `impeccable` (frontend design critique and polish, with companion subagents) | https://github.com/pbakaus/impeccable |
| `break`, `explain-interface` (UI debugging helpers) | https://github.com/jakubkrehel/skills |
| `agent-browser` (browser automation CLI skill) | https://github.com/vercel-labs/agent-browser |
| `seo-audit`, `copywriting`, `ad-creative` and other marketing skills | https://github.com/coreyhaines31/marketingskills |
| `supabase`, `supabase-edge-functions` | https://github.com/supabase/agent-skills |

## Add-ons that ship their own skill

A few standalone tools come with a skill that teaches an agent to run them. Install the
tool and its skill together from the tool's repo; they are listed in the add-ons section of
the main documentation rather than here. One example is `agent-hangover` (command `hangover`), a
code-cleanup pass that needs its own CLI.
