"""The skills module: tool install, pool seeding (never over an existing pool), activation,
rendering, the sync row and check statuses. git, cargo and skillherd are stubs on PATH that record
their argv; the tool's install.sh is a stub in a fake checkout. The real HOME is untouched."""

import json
import shutil

from tests.helpers import ROOT
from tests.test_post import GIT, LOG_STUB, PostBase, stub

SKILLHERD = """#!/usr/bin/env bash
echo "skillherd $*" >> "$FAKE_LOG"
[ -z "$FAKE_NOISE" ] || echo '{"noisy":"report"}'
case "$*" in *render*) exit "${FAKE_RENDER_RC:-0}" ;; esac
case "$*" in *doctor*) exit "${FAKE_DOCTOR_RC:-0}" ;; esac
exit 0
"""
# the tool's installer: puts the stub skillherd in <prefix>/bin and records its arguments
INSTALL_SH = """#!/usr/bin/env bash
echo "install.sh $*" >> "$FAKE_LOG"
[ "$1" = --prefix ] || exit 2
mkdir -p "$2/bin"; cp "$FAKE_SKILLHERD" "$2/bin/skillherd"
"""
STARTER = sorted(d.name for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").is_file())


class SkillsBase(PostBase):
    def setUp(self):
        super().setUp()
        stub(self.fake / "skillherd-stub", SKILLHERD)
        stub(self.fake / "cargo", LOG_STUB.format(name="cargo"))
        stub(self.template / "install.sh", INSTALL_SH)
        self.env["FAKE_SKILLHERD"] = str(self.fake / "skillherd-stub")
        # the tool's own overrides, so a developer's shell cannot steer the install
        self.env |= {"SKILLHERD_CONFIG": "", "SKILLHERD_AGENTS_DIR": ""}
        self.checkout = self.home / "Code" / "skillherd"
        self.pool = self.home / ".agents" / "skill-library"
        self.repos = self.home / ".config/agent-estate/sync-repos.tsv"
        self.hook = '\n[modules.sync]\nhooks = ["skillherd sync"]\n'

    def config(self, extra="", hook=True):
        self.write_config(enabled=["skills"], extra=(self.hook if hook else "") + extra)

    def install(self, *args, **env):
        return self.estate("install", "skills", *args, env=self.env | env)

    def row(self, **env):
        rows = json.loads(self.check(**env).stdout)
        rows = rows["checks"] if isinstance(rows, dict) else rows
        return next(r for r in rows if r["name"] == "skills")


class Install(SkillsBase):
    def test_install_runs_the_tools_installer_then_seeds_activates_and_renders(self):
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        order = [self.index("git clone https://github.com/treygoff24/skillherd"),
                 self.index(f"install.sh --prefix {self.home}/.local"),
                 self.index(f"skillherd --pool {self.pool} on"),
                 self.index(f"skillherd --pool {self.pool} render")]
        self.assertEqual(order, sorted(order), self.calls())
        self.assertTrue((self.home / ".local/bin/skillherd").is_file())
        on = self.calls()[self.index(f"skillherd --pool {self.pool} on")].split()
        for name in STARTER + ["estate-health"]:
            self.assertIn(name, on)
            self.assertTrue((self.pool / name / "SKILL.md").is_file(), name)
        self.assertEqual(len(STARTER), 34)
        # copied, not linked, and only skill folders (not the starter's README/PROVENANCE)
        self.assertFalse((self.pool / "estate-health").is_symlink())
        self.assertFalse((self.pool / "README.md").exists())
        cfg = json.loads((self.home / ".config/skillherd/config.json").read_text())
        self.assertEqual(cfg, {"library": str(self.pool)})

    def test_every_seeded_skill_is_declared_house_so_doctor_has_no_unknown_provenance(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        house = self.pool / ".globals" / "house"
        names = {ln.split()[0] for ln in house.read_text().splitlines()
                 if ln.split("#")[0].strip()}
        self.assertEqual(names, set(STARTER) | {"estate-health"})

    def test_an_existing_house_file_is_extended_never_overwritten(self):
        house = self.pool / ".globals" / "house"
        house.parent.mkdir(parents=True)
        house.write_text("# mine\nmy-skill  # keep\ntdd\n")
        self.config()
        self.assertEqual(self.install().returncode, 0)
        text = house.read_text()
        self.assertTrue(text.startswith("# mine\nmy-skill  # keep\ntdd\n"), text)
        self.assertEqual(text.count("tdd"), 1, text)
        self.assertIn("estate-health", text)

    def test_a_pool_that_already_has_skills_gets_no_house_file(self):
        mine = self.pool / "mine"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("mine\n")
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse((self.pool / ".globals").exists())

    def test_the_tools_reports_are_not_echoed_and_the_hint_is_conditional(self):
        self.config()
        p = self.install(FAKE_NOISE="1")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("noisy", p.stdout + p.stderr)
        self.assertNotIn('Add "skillherd sync"', p.stderr)
        self.config(hook=False)
        p = self.install(FAKE_NOISE="1")
        self.assertIn('Add "skillherd sync"', p.stderr)

    def test_a_failing_render_shows_the_tools_output(self):
        self.config()
        p = self.install(FAKE_NOISE="1", FAKE_RENDER_RC="3")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("exit 3", p.stdout + p.stderr)
        self.assertIn("noisy", p.stdout + p.stderr)

    def test_missing_cargo_says_rust_and_the_linker(self):
        (self.fake / "cargo").unlink()
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 1)
        for word in ("Rust", "rustup", "xcode-select --install", "build-essential"):
            self.assertIn(word, p.stderr)

    def test_paths_skills_is_used_when_it_is_not_the_rendered_agents_folder(self):
        pool = self.home / "my-skills"
        self.config(f'\n[modules.skills]\npool = "{pool}"\n')
        self.assertEqual(self.install().returncode, 0)
        self.assertTrue((pool / "tdd" / "SKILL.md").is_file())
        self.assertFalse(self.pool.exists())

    def test_an_existing_pool_is_never_overwritten(self):
        mine = self.pool / "mine"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("mine\n")
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([d.name for d in self.pool.iterdir()], ["mine"])
        self.assertEqual((mine / "SKILL.md").read_text(), "mine\n")
        self.assertFalse([c for c in self.calls() if " on " in c])
        self.assertTrue([c for c in self.calls() if c.endswith("render")])

    def test_a_seeded_pool_that_was_edited_survives_reinstall_and_nothing_reruns(self):
        self.config()
        self.assertEqual(self.install().returncode, 0)
        (self.pool / "tdd" / "SKILL.md").write_text("edited\n")
        (self.pool / "brainstorming" / "SKILL.md").unlink()
        self.log.write_text("")
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.pool / "tdd" / "SKILL.md").read_text(), "edited\n")
        self.assertFalse((self.pool / "brainstorming" / "SKILL.md").exists())
        for gone in ("git clone", "install.sh", "skillherd --pool " + str(self.pool) + " on"):
            self.assertFalse([c for c in self.calls() if c.startswith(gone)], (gone, self.calls()))
        rows = [ln for ln in self.repos.read_text().splitlines() if ln.startswith("skillherd\t")]
        self.assertEqual(len(rows), 1, rows)

    def test_a_pool_remote_is_synced_not_seeded(self):
        self.config('\n[modules.skills]\npool_remote = "git@github.com:you/skills.git"\n')
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse(self.pool.exists())
        self.assertIn("skillherd sync", self.calls())
        cfg = json.loads((self.home / ".config/skillherd/config.json").read_text())
        self.assertEqual(cfg["remote"], "git@github.com:you/skills.git")

    def test_an_existing_tool_config_is_kept(self):
        conf = self.home / ".config/skillherd/config.json"
        conf.parent.mkdir(parents=True)
        conf.write_text('{"library": "~/elsewhere"}')
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(conf.read_text(), '{"library": "~/elsewhere"}')

    def test_a_skill_cli_config_is_carried_over_and_left_in_place(self):
        old = self.home / ".config/skill/config.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"library": "~/elsewhere", "claude_home": "~/.claude-x"}')
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        new = self.home / ".config/skillherd/config.json"
        self.assertEqual(new.read_text(), '{"library": "~/elsewhere", "claude_home": "~/.claude-x"}')
        self.assertEqual(old.read_text(), '{"library": "~/elsewhere", "claude_home": "~/.claude-x"}')

    def test_the_skill_cli_sync_row_this_module_wrote_is_replaced(self):
        self.repos.parent.mkdir(parents=True)
        mine = "skill-cli\t-\tmake install\n"     # not this module's command: left alone
        self.repos.write_text("dotfiles\n" + mine
                              + f"skill-cli\t{self.home}/Code/skill-cli\t/old/estate/bin/estate install skills\n")
        # a checkout already there, so the dry run gets as far as the repo table
        shutil.copytree(self.template, self.checkout)
        (self.checkout / ".git").mkdir()
        self.config()
        p = self.install("--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would drop the old skill-cli row", p.stderr)
        self.assertIn("/old/estate/bin/estate install skills", self.repos.read_text())
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        lines = self.repos.read_text().splitlines(keepends=True)
        self.assertEqual(lines[:2], ["dotfiles\n", mine], lines)
        self.assertEqual([ln.split("\t")[0] for ln in lines[2:]], ["skillherd"], lines)
        self.assertIn("dropped the old skill-cli row", p.stderr)

    def test_an_old_skill_sync_hook_is_named_for_replacement(self):
        self.config(hook=False, extra='\n[modules.sync]\nhooks = ["skill sync"]\n')
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn('replace "skill sync" with "skillherd sync"', p.stderr)

    def test_a_failed_clone_says_so_and_names_the_checkout_setting(self):
        stub(self.fake / "git", GIT.replace('clone) dest', 'clone) exit 128 ;;\n  X) dest'))
        self.config()
        p = self.install()
        self.assertEqual(p.returncode, 1)
        self.assertIn("cannot clone https://github.com/treygoff24/skillherd", p.stderr)
        self.assertIn("modules.skills.checkout", p.stderr)

    def test_a_local_clone_is_used_without_cloning(self):
        shutil.copytree(self.template, self.checkout)
        (self.checkout / ".git").mkdir()
        self.config()
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse([c for c in self.calls() if c.startswith("git clone")])
        self.assertTrue([c for c in self.calls() if c.startswith("install.sh")])

    def test_dry_run_changes_nothing(self):
        self.config()
        p = self.install("--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.checkout.exists())
        self.assertFalse(self.pool.exists())
        self.assertFalse(self.repos.exists())

    def test_paths_skills_inside_the_rendered_agents_folder_is_moved_aside(self):
        self.config('\n[modules.skills]\npool = "~/.agents/skills"\n')
        p = self.install()
        self.assertIn("shared Agents output folder", p.stderr)
        self.assertFalse((self.home / ".agents/skills").exists())


class Check(SkillsBase):
    def installed(self, **kw):
        self.config(**kw)
        self.assertEqual(self.install().returncode, 0)

    def test_ok(self):
        self.installed()
        r = self.row()
        self.assertEqual(r["status"], 0, r)

    def test_missing_skillherd_or_pool_fails(self):
        self.installed()
        shutil.rmtree(self.pool)
        self.assertEqual(self.row()["status"], 1)
        self.installed()
        (self.home / ".local/bin/skillherd").unlink()
        self.assertEqual(self.row()["status"], 1)

    def test_doctor_findings_warn(self):
        self.installed()
        self.assertEqual(self.row(FAKE_DOCTOR_RC="1")["status"], 2)

    def test_missing_nightly_hook_warns(self):
        self.installed(hook=False)
        r = self.row()
        self.assertEqual(r["status"], 2, r)
        self.assertIn("skillherd sync", r["summary"])

    def test_an_old_skill_sync_hook_warns_even_beside_the_new_one(self):
        self.installed(hook=False, extra='\n[modules.sync]\nhooks = ["skill sync", "skillherd sync"]\n')
        r = self.row()
        self.assertEqual(r["status"], 2, r)
        self.assertIn("still runs", r["summary"])
