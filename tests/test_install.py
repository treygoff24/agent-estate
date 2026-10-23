import shutil
from tests.helpers import ROOT, TempHome, write_module

from estate import modules as M


def meta(requires=()):
    return {"requires": list(requires)}


class Order(TempHome):
    def test_dependencies_first_each_once_stable(self):
        known = {"a": meta(), "b": meta(["a"]), "c": meta(["a", "b"]), "d": meta(),
                 "e": meta(["d", "b"])}
        self.assertEqual(M.install_order(["c"], known), ["a", "b", "c"])
        self.assertEqual(M.install_order(["e", "c"], known), ["d", "a", "b", "e", "c"])
        self.assertEqual(M.install_order(["d", "a"], known), ["d", "a"])
        self.assertEqual(M.install_order(["b", "a", "b"], known), ["a", "b"])

    def test_cycle_and_unknown(self):
        known = {"a": meta(["b"]), "b": meta(["c"]), "c": meta(["a"])}
        with self.assertRaises(M.ModuleError) as e:
            M.install_order(["a"], known)
        self.assertIn("a -> b -> c -> a", str(e.exception))
        with self.assertRaises(M.ModuleError) as e:
            M.install_order(["zz"], {"a": meta()})
        self.assertIn("no module named 'zz'", str(e.exception))


class Discover(TempHome):
    def test_module_toml_is_validated(self):
        mdir = self.tmp / "modules"
        write_module(mdir, "ok")
        self.assertFalse(M.discover(mdir)["ok"]["has_check"])
        self.assertTrue(M.discover(mdir)["ok"]["stub"])
        write_module(mdir, "bad", platforms='["windows"]', meta='colour = "red"\n')
        with self.assertRaises(M.ModuleError) as e:
            M.discover(mdir)
        self.assertIn("bad/module.toml", str(e.exception))
        self.assertIn("platforms", str(e.exception))
        self.assertIn("unknown key 'colour'", str(e.exception))

    def test_requires_must_exist(self):
        mdir = self.tmp / "modules"
        write_module(mdir, "x", requires='["ghost"]')
        with self.assertRaises(M.ModuleError) as e:
            M.discover(mdir)
        self.assertIn("requires unknown module 'ghost'", str(e.exception))

    def test_repo_modules_are_valid(self):
        known = M.discover()
        self.assertIn("tmp-cleanup", known)
        self.assertFalse(known["tmp-cleanup"]["stub"])
        for name, m in known.items():
            readme = (M.repo_root() / "modules" / name / "README.md")
            self.assertTrue(readme.is_file(), f"{name} has no README.md")
            if not m["stub"]:
                self.assertTrue(m["has_install"] and m["has_check"],
                                f"{name}: a built module needs both install and check")


class InstallCli(TempHome):
    def test_install_runs_in_requires_order_and_stops_on_failure(self):
        # Drive cmd_install through the real CLI with fixture modules (the real
        # tmp-cleanup, a stub, and a Linux-only module), so the test does not
        # depend on which repo modules are still stubs.
        mdir = self.tmp / "modules"
        shutil.copytree(ROOT / "modules" / "tmp-cleanup", mdir / "tmp-cleanup")
        write_module(mdir, "stubby")
        write_module(mdir, "linuxonly", platforms='["linux"]', check="exit 0", install="exit 0")
        env = {"ESTATE_PLATFORM": "mac", "ESTATE_MODULES_DIR": str(mdir)}
        self.write_config(["tmp-cleanup"])
        p = self.estate("install", "--dry-run", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("== tmp-cleanup: install --dry-run", p.stdout)
        p = self.estate("install", "stubby", "tmp-cleanup", env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn("== stubby: not built yet", p.stdout)
        self.assertNotIn("== tmp-cleanup", p.stdout)
        p = self.estate("install", "linuxonly", env=env)
        self.assertIn("== linuxonly: skipped (not used on mac)", p.stdout)
        self.assertEqual(p.returncode, 0)
