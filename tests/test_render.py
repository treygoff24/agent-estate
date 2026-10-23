from tests.helpers import ROOT, TempHome

from estate import config as C
from estate import render as R


class Render(TempHome):
    def setUp(self):
        super().setUp()
        self.write_config()
        self.cfg = C.load()
        self.ctx = R.context(self.cfg, "demo", "linux")

    def test_values_label_and_paths(self):
        out = R.render_text("Label=${label}\nUser=${user.name}\nState=${paths.state}\n"
                            "Ssh=${machines.vps.ssh}\nHome=${home}\nM=${module}\n", self.ctx)
        self.assertEqual(out, f"Label=com.example.estate.demo\nUser=Test User\n"
                              f"State={self.state}\nSsh=vps-alias\nHome={self.home}\nM=demo\n")

    def test_escape_leaves_literal_placeholder(self):
        out = R.render_text("ExecStart=/bin/sh -c 'echo $${HOME} $$ $HOME'", self.ctx)
        self.assertEqual(out, "ExecStart=/bin/sh -c 'echo ${HOME} $$ $HOME'")

    def test_unknown_key_fails_and_names_every_one(self):
        with self.assertRaises(R.RenderError) as e:
            R.render_text("a=${user.name} b=${user.phone} c=${nope}", self.ctx, "t.service")
        msg = str(e.exception)
        self.assertTrue(msg.startswith("t.service: "))
        self.assertIn("${user.phone}: no such key", msg)
        self.assertIn("${nope}: no such key", msg)

    def test_non_scalar_and_malformed_fail(self):
        for text, needle in (("${machines}", "not a single value"),
                             ("${harnesses.claude.accounts}", "not a single value"),
                             ("x ${user.name", "unclosed or malformed"),
                             ("${bad key}", "not a valid key")):
            with self.assertRaises(R.RenderError, msg=text) as e:
                R.render_text(text, self.ctx)
            self.assertIn(needle, str(e.exception))

    def test_label_needs_a_module(self):
        with self.assertRaises(R.RenderError) as e:
            R.render_text("${label}", R.context(self.cfg, None, "linux"))
        self.assertIn("needs a module", str(e.exception))

    def test_module_from_template_path(self):
        tpl = ROOT / "modules" / "tmp-cleanup" / "templates" / "tmpfiles.conf"
        self.assertEqual(R.module_of(tpl), "tmp-cleanup")
        self.assertIsNone(R.module_of(self.tmp / "x.service"))


class RenderCli(TempHome):
    def test_out_written_only_when_every_placeholder_renders(self):
        self.write_config()
        good = self.tmp / "good.plist"
        good.write_text("<string>${label}</string> ${paths.bin}\n")
        dest = self.tmp / "out" / "unit.plist"
        p = self.estate("render", str(good), "--module", "sync", "--out", str(dest))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(dest.read_text(),
                         f"<string>com.example.estate.sync</string> {self.home}/.local/bin\n")

        bad = self.tmp / "bad.service"
        bad.write_text("Description=${label}\nUser=${user.nickname}\n")
        dest2 = self.tmp / "out" / "bad.service"
        p = self.estate("render", str(bad), "--module", "sync", "--out", str(dest2))
        self.assertEqual(p.returncode, 1)
        self.assertIn("${user.nickname}: no such key", p.stderr)
        self.assertFalse(dest2.exists())
        self.assertEqual(sorted(x.name for x in dest.parent.iterdir()), ["unit.plist"])
