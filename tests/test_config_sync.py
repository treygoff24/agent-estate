"""The config-sync engine (modules/config-sync/estate-config-sync), driven through its
command line against a temporary agent-env repo, HOME and state directory."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from tests.helpers import ROOT, TempHome

MOD = ROOT / "modules" / "config-sync"
TOOL = MOD / "estate-config-sync"
sys.path.insert(0, str(MOD))
import config_merge as M  # noqa: E402

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com"]


def git(repo, *args):
    return subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


class SyncCase(TempHome):
    """A repo with a manifest and files, a home, and a state dir; `sync` runs the tool."""

    platform = "linux"

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "agent-env"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)

    def put(self, rel, text, mode=None):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if mode is not None:
            p.chmod(mode)
        return p

    def manifest(self, *rows):
        lines = ["\t".join(r) if isinstance(r, tuple) else r for r in rows]
        self.put("manifest.tsv", "# test manifest\n" + "\n".join(lines) + "\n")

    def commit(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "x", "--allow-empty")

    def sync(self, *args, platform=None, repo=True):
        cmd = [sys.executable, str(TOOL), args[0], *(["--repo", str(self.repo)] if repo else []),
               "--home", str(self.home), "--state", str(self.state),
               "--platform", platform or self.platform, *args[1:]]
        return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, HOME=str(self.home)))

    def apply(self, *args, **kw):
        return self.sync("apply", *args, **kw)

    def out(self, p):
        return p.stdout + p.stderr

    def h(self, rel):
        return self.home / rel

    def state_json(self):
        return json.loads((self.state / "config-sync" / "state.json").read_text())


class FileRows(SyncCase):
    def test_file_installs_with_mode_and_second_run_is_a_no_op(self):
        self.put("home/a.md", "alpha\n")
        self.put("home/run.sh", "#!/bin/sh\n", 0o755)
        self.manifest(("file", "home/a.md", ".cfg/a.md"), ("file", "home/run.sh", "~/bin/run.sh"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(self.h(".cfg/a.md").read_text(), "alpha\n")
        self.assertEqual(self.h("bin/run.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.h(".cfg/a.md").stat().st_mode & 0o777, 0o644)
        self.assertIn("2 install", p.stdout)
        before = self.h(".cfg/a.md").stat().st_mtime_ns
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertIn("2 unchanged", p.stdout)
        self.assertNotIn("install", p.stdout.replace("config-sync:", ""))
        self.assertEqual(self.h(".cfg/a.md").stat().st_mtime_ns, before)

    def test_repo_change_updates_an_untouched_file(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.put("home/a.md", "v2\n")
        p = self.apply()
        self.assertIn("update      a.md", p.stdout)
        self.assertEqual(self.h("a.md").read_text(), "v2\n")

    def test_dry_run_changes_nothing_and_lists_everything(self):
        self.put("home/a.md", "v1\n")
        self.put("home/t/x", "x\n")
        self.put("home/s.json", '{"k": 1}')
        self.manifest(("file", "home/a.md", "a.md"), ("tree", "home/t", "t"),
                      ("merge-json", "home/s.json", "s.json"))
        p = self.apply("--dry-run")
        self.assertEqual(p.returncode, 0, self.out(p))
        for expect in ("would install a.md", "would install t/x", "would install s.json"):
            self.assertIn(expect, p.stdout)
        self.assertIn("dry run, nothing changed", p.stdout)
        self.assertEqual(os.listdir(self.home), [])
        self.assertFalse(self.state.exists())

    def test_dry_run_reports_update_without_writing(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.put("home/a.md", "v2\n")
        p = self.apply("--dry-run")
        self.assertIn("would update", p.stdout)
        self.assertEqual(self.h("a.md").read_text(), "v1\n")

    def test_platform_filter(self):
        self.put("home/m", "mac\n")
        self.put("home/l", "linux\n")
        self.put("home/b", "both\n")
        self.manifest(("file", "home/m", "m", "mac"), ("file", "home/l", "l", "linux"),
                      ("file", "home/b", "b"), ("file", "home/d", "d", "darwin,linux"))
        self.put("home/d", "d\n")
        self.apply(platform="linux")
        self.assertEqual(sorted(os.listdir(self.home)), ["b", "d", "l"])
        mac_home = self.tmp / "machome"
        mac_home.mkdir()
        p = subprocess.run([sys.executable, str(TOOL), "apply", "--repo", str(self.repo),
                            "--home", str(mac_home), "--state", str(self.tmp / "s2"),
                            "--platform", "mac"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(os.listdir(mac_home)), ["b", "d", "m"])

    def test_same_dest_on_different_platforms_is_allowed_but_overlap_is_not(self):
        self.put("home/m", "mac\n")
        self.put("home/l", "linux\n")
        self.manifest(("file", "home/m", "x", "mac"), ("file", "home/l", "x", "linux"))
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(self.h("x").read_text(), "linux\n")
        self.manifest(("file", "home/m", "x"), ("file", "home/l", "x"))
        p = self.apply()
        self.assertEqual(p.returncode, 1)
        self.assertIn("overlap", self.out(p))

    def test_bad_manifest_installs_nothing(self):
        self.put("home/a", "a\n")
        for row, word in ((("copy", "home/a", "a"), "unknown kind"),
                          (("file", "../x", "a"), "unsafe source"),
                          (("file", "home/a", "/etc/a"), "unsafe dest"),
                          (("file", "home/a", "a", "windows"), "platform"),
                          (("file", "home/a"), "expected")):
            self.manifest(("file", "home/a", "ok"), row)
            p = self.apply()
            self.assertEqual(p.returncode, 1, row)
            self.assertIn(word, self.out(p))
            self.assertFalse(self.h("ok").exists(), row)

    def test_missing_source_is_an_error_and_recorded(self):
        self.manifest(("file", "home/nope", "a"))
        p = self.apply()
        self.assertEqual(p.returncode, 1)
        self.assertIn("error", self.out(p))
        last = self.state_json()["last_apply"]
        self.assertFalse(last["ok"])
        self.assertIn("a:", last["errors"][0])

    def test_missing_checkout_fails_clearly(self):
        p = self.sync("apply", repo=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("no agent-env checkout", p.stderr)


class LocalEdits(SyncCase):
    def test_local_edit_is_never_overwritten(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.h("a.md").write_text("my edit\n")
        self.put("home/a.md", "v2\n")
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(self.h("a.md").read_text(), "my edit\n")
        self.assertIn("local-edit  a.md", p.stderr)
        self.assertIn("--harvest a.md", p.stderr)
        self.assertIn("1 local-edit", p.stdout)
        self.assertEqual(self.apply().returncode, 0)  # stays protected on every later run
        self.assertEqual(self.h("a.md").read_text(), "my edit\n")

    def test_existing_file_config_sync_did_not_write_is_kept(self):
        self.put("home/a.md", "repo\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.h("a.md").write_text("already here\n")
        p = self.apply()
        self.assertEqual(self.h("a.md").read_text(), "already here\n")
        self.assertIn("did not install it", p.stderr)

    def test_deleting_the_local_edit_resumes_updates(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.h("a.md").write_text("mine\n")
        self.put("home/a.md", "v2\n")
        self.apply()
        self.h("a.md").unlink()
        self.apply()
        self.assertEqual(self.h("a.md").read_text(), "v2\n")

    def test_symlink_destination_is_refused(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        (self.tmp / "elsewhere").write_text("keep\n")
        self.h("a.md").symlink_to(self.tmp / "elsewhere")
        p = self.apply()
        self.assertEqual(p.returncode, 1)
        self.assertEqual((self.tmp / "elsewhere").read_text(), "keep\n")


class Harvest(SyncCase):
    def test_harvest_file_copies_local_version_into_repo(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", ".cfg/a.md"))
        self.apply()
        self.h(".cfg/a.md").write_text("my edit\n")
        p = self.sync("harvest", ".cfg/a.md")
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual((self.repo / "home/a.md").read_text(), "my edit\n")
        self.assertIn("git -C", p.stdout)
        p = self.apply()  # now identical: no local-edit, nothing to do
        self.assertNotIn("local-edit", self.out(p))
        self.assertIn("1 unchanged", p.stdout)

    def test_harvest_adopts_a_file_that_existed_before_the_first_apply(self):
        self.put("home/a.md", "repo\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.h("a.md").write_text("pre-existing\n")
        self.assertIn("local-edit", self.apply().stderr)
        self.assertEqual(self.sync("harvest", str(self.h("a.md"))).returncode, 0)  # absolute path
        self.assertEqual((self.repo / "home/a.md").read_text(), "pre-existing\n")
        self.assertNotIn("local-edit", self.out(self.apply()))

    def test_harvest_dry_run_writes_nothing(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.h("a.md").write_text("edit\n")
        p = self.sync("harvest", "a.md", "--dry-run")
        self.assertIn("harvest", p.stdout)
        self.assertEqual((self.repo / "home/a.md").read_text(), "v1\n")

    def test_harvest_tree_file_and_new_file_and_whole_tree(self):
        self.put("home/t/a", "a\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        self.h(".t/a").write_text("a edited\n")
        (self.h(".t") / "new").write_text("brand new\n")
        (self.h(".t") / "sub").mkdir()
        (self.h(".t") / "sub/deep").write_text("deep\n")
        self.assertEqual(self.sync("harvest", ".t/new").returncode, 0)
        self.assertEqual((self.repo / "home/t/new").read_text(), "brand new\n")
        self.assertFalse((self.repo / "home/t/a").read_text() == "a edited\n")
        p = self.sync("harvest", ".t")  # the whole tree row
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual((self.repo / "home/t/a").read_text(), "a edited\n")
        self.assertEqual((self.repo / "home/t/sub/deep").read_text(), "deep\n")

    def test_harvest_refuses_merged_files_links_and_unmanaged_paths(self):
        self.put("home/s.json", '{"a": 1}')
        self.put("home/l", "l\n")
        self.manifest(("merge-json", "home/s.json", "s.json"), ("link", "home/l", "l"))
        self.apply()
        for dest, word in (("s.json", "merged"), ("l", "link"), ("other", "not managed")):
            p = self.sync("harvest", dest)
            self.assertEqual(p.returncode, 1, dest)
            self.assertIn(word, p.stderr)
        self.assertEqual((self.repo / "home/s.json").read_text(), '{"a": 1}')

    def test_harvest_flag_spelling_and_paths_outside_home(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.h("a.md").write_text("edit\n")
        cmd = [sys.executable, str(TOOL), "--harvest", "a.md", "--repo", str(self.repo),
               "--home", str(self.home), "--state", str(self.state), "--platform", "linux"]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual((self.repo / "home/a.md").read_text(), "edit\n")
        p = self.sync("harvest", "/etc/hosts")
        self.assertEqual(p.returncode, 1)


class Trees(SyncCase):
    def test_tree_installs_nested_files(self):
        self.put("home/t/a.md", "a\n")
        self.put("home/t/sub/b.md", "b\n")
        self.put("home/t/.DS_Store", "junk")
        self.manifest(("tree", "home/t", ".t"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(self.h(".t/sub/b.md").read_text(), "b\n")
        self.assertFalse(self.h(".t/.DS_Store").exists())

    def test_file_removed_from_source_is_removed_from_dest_and_empty_dirs_pruned(self):
        self.put("home/t/a.md", "a\n")
        self.put("home/t/sub/b.md", "b\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        (self.repo / "home/t/sub/b.md").unlink()
        (self.repo / "home/t/sub").rmdir()
        p = self.apply()
        self.assertIn("remove      .t/sub/b.md", p.stdout)
        self.assertFalse(self.h(".t/sub").exists())
        self.assertTrue(self.h(".t/a.md").exists())
        self.assertNotIn(".t/sub/b.md", self.state_json()["entries"])

    def test_removal_never_touches_files_config_sync_did_not_install(self):
        self.put("home/t/a.md", "a\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        (self.h(".t") / "mine.md").write_text("user's own\n")
        (self.repo / "home/t/a.md").unlink()
        self.put("home/t/keep", "k\n")
        self.apply()
        self.assertFalse(self.h(".t/a.md").exists())
        self.assertEqual(self.h(".t/mine.md").read_text(), "user's own\n")

    def test_retired_file_with_local_edits_is_kept_and_reported(self):
        self.put("home/t/a.md", "a\n")
        self.put("home/t/b.md", "b\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        self.h(".t/a.md").write_text("edited\n")
        (self.repo / "home/t/a.md").unlink()
        p = self.apply()
        self.assertEqual(self.h(".t/a.md").read_text(), "edited\n")
        self.assertIn("edited locally", p.stderr)

    def test_dropping_a_manifest_row_retires_its_files(self):
        self.put("home/a.md", "a\n")
        self.put("home/t/x", "x\n")
        self.manifest(("file", "home/a.md", "a.md"), ("tree", "home/t", ".t"))
        self.apply()
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        self.assertFalse(self.h(".t/x").exists())
        self.assertTrue(self.h("a.md").exists())

    def test_a_failed_row_blocks_retirement(self):
        self.put("home/t/x", "x\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        self.manifest(("tree", "home/t", ".t"), ("file", "home/missing", "m"))
        (self.repo / "home/t/x").unlink()
        self.put("home/t/y", "y\n")
        self.assertEqual(self.apply().returncode, 1)
        self.assertTrue(self.h(".t/x").exists())  # not retired while the run had errors

    def test_tree_executable_bit_and_symlinks_in_source(self):
        self.put("home/t/run", "#!/bin/sh\n", 0o755)
        (self.repo / "home/t/ln").symlink_to("run")
        self.manifest(("tree", "home/t", ".t"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertTrue(self.h(".t/run").stat().st_mode & stat.S_IXUSR)
        self.assertFalse(self.h(".t/ln").exists())
        self.assertIn("symlink", p.stderr)

    def test_dry_run_reports_removals_without_removing(self):
        self.put("home/t/a", "a\n")
        self.put("home/t/b", "b\n")
        self.manifest(("tree", "home/t", ".t"))
        self.apply()
        (self.repo / "home/t/a").unlink()
        p = self.apply("--dry-run")
        self.assertIn("would remove", p.stdout)
        self.assertTrue(self.h(".t/a").exists())


class Links(SyncCase):
    def test_link_installs_and_is_idempotent_and_retires(self):
        self.put("home/l", "l\n")
        self.manifest(("link", "home/l", ".cfg/l"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertTrue(self.h(".cfg/l").is_symlink())
        self.assertEqual(self.h(".cfg/l").read_text(), "l\n")
        self.assertEqual(os.readlink(self.h(".cfg/l")), str((self.repo / "home/l").resolve()))
        self.assertIn("1 unchanged", self.apply().stdout)
        self.manifest()
        self.apply()
        self.assertFalse(self.h(".cfg/l").exists() or self.h(".cfg/l").is_symlink())

    def test_link_over_a_real_file_or_foreign_link_is_a_local_edit(self):
        self.put("home/l", "l\n")
        self.manifest(("link", "home/l", "l"))
        self.h("l").write_text("mine\n")
        p = self.apply()
        self.assertIn("local-edit", p.stderr)
        self.assertEqual(self.h("l").read_text(), "mine\n")
        self.h("l").unlink()
        self.h("l").symlink_to(self.tmp)
        self.assertIn("local-edit", self.apply().stderr)


class MergeJson(SyncCase):
    def test_unmanaged_keys_survive_and_managed_keys_converge(self):
        self.put("home/s.json", json.dumps({"model": "x", "permissions": {"deny": ["A"]},
                                            "nested": {"k": 2}}))
        self.manifest(("merge-json", "home/s.json", ".claude/settings.json"))
        dest = self.h(".claude/settings.json")
        dest.parent.mkdir(parents=True)
        dest.write_text(json.dumps({"model": "mine", "plugins": {"p": True},
                                    "permissions": {"allow": ["B"], "deny": ["Z"]},
                                    "nested": {"other": 1}}))
        dest.chmod(0o640)
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        got = json.loads(dest.read_text())
        self.assertEqual(got["model"], "x")  # managed scalar converges
        self.assertEqual(got["plugins"], {"p": True})  # unmanaged key survives
        self.assertEqual(got["permissions"], {"allow": ["B"], "deny": ["A"]})
        self.assertEqual(got["nested"], {"other": 1, "k": 2})
        self.assertEqual(dest.stat().st_mode & 0o777, 0o640)
        before = dest.read_bytes()
        mtime = dest.stat().st_mtime_ns
        p = self.apply()
        self.assertIn("1 unchanged", p.stdout)
        self.assertEqual(dest.read_bytes(), before)
        self.assertEqual(dest.stat().st_mtime_ns, mtime)

    def test_absent_target_is_created_private(self):
        self.put("home/s.json", '{"a": 1}')
        self.manifest(("merge-json", "home/s.json", "s.json"))
        self.apply()
        self.assertEqual(json.loads(self.h("s.json").read_text()), {"a": 1})
        self.assertEqual(self.h("s.json").stat().st_mode & 0o777, 0o600)

    def test_a_local_edit_to_a_merged_file_is_not_a_conflict(self):
        self.put("home/s.json", '{"a": 1}')
        self.manifest(("merge-json", "home/s.json", "s.json"))
        self.apply()
        self.h("s.json").write_text('{"a": 1, "mine": true}')
        self.put("home/s.json", '{"a": 2}')
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(json.loads(self.h("s.json").read_text()), {"a": 2, "mine": True})

    def test_unparseable_target_is_refused_untouched(self):
        self.put("home/s.json", '{"a": 1}')
        self.put("home/ok", "ok\n")
        self.manifest(("merge-json", "home/s.json", "s.json"), ("file", "home/ok", "ok"))
        self.h("s.json").write_text("{not json")
        p = self.apply()
        self.assertEqual(p.returncode, 1)
        self.assertIn("not valid JSON", p.stderr)
        self.assertEqual(self.h("s.json").read_text(), "{not json")
        self.assertTrue(self.h("ok").exists())  # other rows still ran

    def test_hooks_merge_per_command(self):
        frag = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "~/a.sh",
                                                       "timeout": 5}]}]}}
        mine = {"hooks": {"SessionStart": [{"matcher": "x", "hooks": [
            {"type": "command", "command": "bash ~/a.sh"},
            {"type": "command", "command": "~/mine.sh"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "~/stop.sh"}]}]}}
        merged = json.loads(M.merge_json(json.dumps(mine), json.dumps(frag)))
        start = merged["hooks"]["SessionStart"]
        self.assertEqual(len(start), 1)  # converged in place, not appended twice
        self.assertEqual(start[0]["hooks"][0]["timeout"], 5)
        self.assertEqual(start[0]["hooks"][1]["command"], "~/mine.sh")
        self.assertEqual(start[0]["matcher"], "x")
        self.assertIn("Stop", merged["hooks"])
        again = M.merge_json(json.dumps(merged), json.dumps(frag))
        self.assertEqual(json.loads(again), merged)

    def test_merge_json_rejects_non_objects(self):
        for target, frag in (("[]", "{}"), ("{}", "[1]"), ("{}", "nope")):
            with self.assertRaises(M.MergeError):
                M.merge_json(target, frag)


class MergeToml(SyncCase):
    FRAG = 'approval_policy = "on-request"\n[features]\nweb = true\n'

    def test_unmanaged_keys_comments_and_tables_survive(self):
        target = ('# my config\nmodel = "m"\napproval_policy = "never"  # old\n\n'
                  '[projects."/some/path"]\ntrust_level = "trusted"\n\n[features]\nother = 1\n')
        out = M.merge_toml(target, self.FRAG)
        self.assertIn('# my config', out)
        self.assertIn('approval_policy = "on-request"', out)
        self.assertNotIn('"never"', out)
        self.assertIn('trust_level = "trusted"', out)
        self.assertIn('other = 1\nweb = true', out)
        import tomllib
        got = tomllib.loads(out)
        self.assertEqual(got["model"], "m")
        self.assertTrue(got["features"]["web"])
        self.assertEqual(M.merge_toml(out, self.FRAG), out)  # idempotent, byte for byte

    def test_absent_table_is_appended_and_absent_file_created(self):
        out = M.merge_toml('model = "m"\n', self.FRAG)
        import tomllib
        self.assertEqual(tomllib.loads(out), {"model": "m", "approval_policy": "on-request",
                                              "features": {"web": True}})
        self.assertEqual(M.merge_toml(out, self.FRAG), out)
        self.assertEqual(M.merge_toml(None, self.FRAG), self.FRAG)

    def test_refusals(self):
        for target, frag, word in (
                ("a = [\n 1,\n 2]\n", "a = [3]\n", "spans several lines"),
                ("x = 1\n", "a.b = 1\n", "single-line"),
                ("x = 1\n", "[[t]]\nk = 1\n", "array tables"),
                ("x = 1\n", "k = [\n1]\n", "one line"),
                ("x = 1\n", "[t]\na = 1\n[t]\nb = 2\n", "TOML"),
                ("broken = \n", "k = 1\n", "target is not valid TOML"),
        ):
            with self.assertRaises(M.MergeError, msg=(target, frag)) as cm:
                M.merge_toml(target, frag)
            self.assertIn(word, str(cm.exception))

    def test_row_end_to_end_with_dry_run(self):
        self.put("home/c.toml", self.FRAG)
        self.manifest(("merge-toml", "home/c.toml", ".codex/config.toml"))
        dest = self.h(".codex/config.toml")
        dest.parent.mkdir()
        dest.write_text('model = "m"\n[projects."/p"]\ntrust_level = "trusted"\n')
        p = self.apply("--dry-run")
        self.assertIn("would merge", p.stdout)
        self.assertNotIn("approval_policy", dest.read_text())
        self.assertEqual(self.apply().returncode, 0)
        text = dest.read_text()
        self.assertIn('trust_level = "trusted"', text)
        self.assertIn('approval_policy = "on-request"', text)
        self.assertIn("1 unchanged", self.apply().stdout)


class Pull(SyncCase):
    def test_apply_pull_fast_forwards_first(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.commit()
        bare = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        git(self.repo, "remote", "add", "origin", str(bare))
        git(self.repo, "push", "-q", "-u", "origin", "main")
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
        (other / "home/a.md").write_text("v2\n")
        git(other, "commit", "-qam", "bump")
        git(other, "push", "-q")
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(self.h("a.md").read_text(), "v1\n")  # no --pull: just what is checked out
        p = self.apply("--pull")
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(self.h("a.md").read_text(), "v2\n")

    def test_failed_pull_warns_and_still_applies(self):
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.commit()
        git(self.repo, "remote", "add", "origin", str(self.tmp / "gone.git"))
        p = self.apply("--pull")
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertIn("pull --ff-only failed", p.stderr)
        self.assertTrue(self.h("a.md").exists())


class Check(SyncCase):
    def chk(self, repo=True):
        return self.sync("check", repo=repo)

    def setUp(self):
        super().setUp()
        self.put("home/a.md", "v1\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.commit()

    def test_missing_checkout_fails(self):
        p = self.sync("check", repo=False)  # falls back to ~/Code/agent-env, which is absent
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stdout.startswith("fail: agent-env checkout missing"))
        self.assertIn("done when:", p.stdout)

    def test_never_applied_fails(self):
        p = self.chk()
        self.assertEqual(p.returncode, 1)
        self.assertIn("never been applied", p.stdout)

    def test_ok_after_apply_and_check_changes_nothing(self):
        self.apply()
        before = (self.state / "config-sync" / "state.json").read_text()
        p = self.chk()
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertTrue(p.stdout.startswith("ok:"), p.stdout)
        self.assertIn("done when:", p.stdout)
        self.assertEqual((self.state / "config-sync" / "state.json").read_text(), before)

    def test_failed_last_apply_fails(self):
        self.manifest(("file", "home/missing", "m"))
        self.apply()
        p = self.chk()
        self.assertEqual(p.returncode, 1)
        self.assertIn("last apply failed", p.stdout)

    def test_pending_change_warns(self):
        self.apply()
        self.put("home/a.md", "v2\n")
        self.commit()
        p = self.chk()
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("1 change(s) waiting to apply", p.stdout)
        self.assertEqual(self.h("a.md").read_text(), "v1\n")  # check never applies

    def test_unharvested_local_edit_warns(self):
        self.apply()
        self.h("a.md").write_text("mine\n")
        self.put("home/a.md", "v2\n")
        self.commit()
        p = self.chk()
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("1 local edit(s) not in the repo (a.md)", p.stdout)
        self.assertIn("--harvest", p.stdout)

    def test_uncommitted_harvest_warns_until_committed(self):
        self.apply()
        self.h("a.md").write_text("mine\n")
        self.sync("harvest", "a.md")
        p = self.chk()
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("uncommitted changes", p.stdout)
        self.commit()
        self.assertEqual(self.chk().returncode, 0)

    def test_invalid_manifest_fails(self):
        self.apply()
        self.put("manifest.tsv", "bogus\tx\ty\n")
        self.commit()
        p = self.chk()
        self.assertEqual(p.returncode, 1)
        self.assertIn("unknown kind", p.stdout)


class Containment(SyncCase):
    """A parent directory under HOME may be a symlink to somewhere else; nothing outside HOME
    may be written, chmodded or deleted through it."""

    def setUp(self):
        super().setUp()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mode) for p in self.outside.rglob("*")
                if p.is_file()}

    def redirect(self, name=".cfg"):
        self.h(name).symlink_to(self.outside)

    def test_file_install_through_a_symlinked_parent_is_refused(self):
        self.put("home/a.md", "alpha\n")
        self.manifest(("file", "home/a.md", ".cfg/a.md"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertIn("outside", p.stderr)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_tree_install_through_a_symlinked_parent_is_refused(self):
        self.put("home/t/a.md", "a\n")
        self.manifest(("tree", "home/t", ".cfg/t"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual(list(self.outside.rglob("*")), [])

    def test_unchanged_file_is_not_chmodded_through_a_symlinked_parent(self):
        self.put("home/run.sh", "#!/bin/sh\n", 0o755)
        (self.outside / "run.sh").write_text("#!/bin/sh\n")
        (self.outside / "run.sh").chmod(0o600)
        self.manifest(("file", "home/run.sh", ".cfg/run.sh"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual((self.outside / "run.sh").stat().st_mode & 0o777, 0o600)

    def test_merge_json_through_a_symlinked_parent_is_refused(self):
        self.put("home/s.json", '{"managed": 1}')
        (self.outside / "settings.json").write_text('{"theirs": true}')
        before = self.snapshot()
        self.manifest(("merge-json", "home/s.json", ".cfg/settings.json"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertIn("outside", p.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_merge_toml_through_a_symlinked_parent_is_refused(self):
        self.put("home/c.toml", 'a = 1\n')
        self.manifest(("merge-toml", "home/c.toml", ".cfg/config.toml"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_merge_whose_leaf_symlink_points_outside_is_refused(self):
        self.put("home/s.json", '{"managed": 1}')
        target = self.outside / "real.json"
        target.write_text('{"theirs": true}')
        self.h("s.json").symlink_to(target)
        self.manifest(("merge-json", "home/s.json", "s.json"))
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual(target.read_text(), '{"theirs": true}')

    def test_merge_through_a_leaf_symlink_that_stays_inside_home_is_followed(self):
        self.put("home/s.json", '{"managed": 1}')
        real = self.h("dotfiles/real.json")
        real.parent.mkdir()
        real.write_text('{"mine": true}')
        self.h("s.json").symlink_to(real)
        self.manifest(("merge-json", "home/s.json", "s.json"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertEqual(json.loads(real.read_text()), {"mine": True, "managed": 1})

    def test_link_through_a_symlinked_parent_is_refused(self):
        self.put("home/a.md", "alpha\n")
        self.manifest(("link", "home/a.md", ".cfg/a.md"))
        self.redirect()
        p = self.apply()
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_retirement_never_deletes_through_a_symlinked_parent(self):
        self.put("home/t/a.md", "a\n")
        self.manifest(("tree", "home/t", ".cfg/t"))
        self.apply()
        victim = self.outside / "t" / "a.md"
        victim.parent.mkdir()
        victim.write_text("a\n")  # same bytes as the engine wrote: a naive retire deletes it
        import shutil
        shutil.rmtree(self.h(".cfg"))
        self.redirect()
        self.manifest(("file", "home/t/a.md", "other.md"))
        p = self.apply()
        self.assertTrue(victim.exists(), self.out(p))
        self.assertIn("outside", p.stderr)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(self.state_json()["last_apply"]["ok"])
        self.assertTrue(self.h("other.md").exists())  # the run went on

    def test_a_stored_path_that_escapes_home_is_never_deleted(self):
        self.put("home/a.md", "a\n")
        self.manifest(("file", "home/a.md", "a.md"))
        self.apply()
        victim = self.outside / "victim"
        victim.write_text("keep me\n")
        state = self.state_json()
        state["entries"]["../outside/victim"] = {"kind": "file", "src": "x",
                                                 "sha256": __import__("hashlib").sha256(b"keep me\n").hexdigest()}
        state["entries"][str(victim)] = dict(state["entries"]["../outside/victim"])
        (self.state / "config-sync" / "state.json").write_text(json.dumps(state))
        p = self.apply()
        self.assertEqual(victim.read_text(), "keep me\n", self.out(p))
        self.assertEqual(p.returncode, 1)

    def test_retiring_through_an_internal_symlinked_parent_does_not_crash_on_prune(self):
        self.put("home/t/a.md", "a\n")
        self.manifest(("tree", "home/t", ".cfg/t"))
        self.apply()
        import shutil
        shutil.move(str(self.h(".cfg")), str(self.h("elsewhere")))
        self.h(".cfg").symlink_to(self.h("elsewhere"))  # inside HOME: may be followed
        self.manifest(("file", "home/t/a.md", "other.md"))
        p = self.apply()
        self.assertEqual(p.returncode, 0, self.out(p))
        self.assertNotIn("Traceback", p.stderr)
        self.assertTrue(self.h(".cfg").is_symlink())  # a link is never pruned as a directory

    def test_empty_redirected_dir_is_not_pruned_or_crashed_on(self):
        self.put("home/a.md", "a\n")
        self.manifest(("file", "home/a.md", ".cfg/sub/a.md"))
        self.apply()
        import shutil
        shutil.rmtree(self.h(".cfg"))
        (self.outside / "sub").mkdir()
        (self.outside / "sub" / "a.md").write_text("a\n")
        self.redirect()
        self.manifest(("file", "home/a.md", "other.md"))
        p = self.apply()
        self.assertNotIn("Traceback", p.stderr)
        self.assertTrue((self.outside / "sub" / "a.md").exists())
        self.assertTrue(self.outside.is_dir())
        self.assertEqual(p.returncode, 1)

    def test_harvest_through_a_symlinked_parent_is_refused(self):
        self.put("home/a.md", "alpha\n")
        self.manifest(("file", "home/a.md", ".cfg/a.md"))
        self.apply()
        import shutil
        shutil.rmtree(self.h(".cfg"))
        (self.outside / "a.md").write_text("secret\n")
        self.redirect()
        p = self.sync("harvest", ".cfg/a.md")
        self.assertEqual(p.returncode, 1, self.out(p))
        self.assertEqual((self.repo / "home/a.md").read_text(), "alpha\n")
