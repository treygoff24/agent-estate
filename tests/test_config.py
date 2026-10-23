import os
import socket
import tomllib
from unittest import mock

from tests.helpers import ROOT, TempHome, write_module

from estate import config as C
from estate import modules as M


class ConfigLoad(TempHome):
    def test_example_config_is_valid_and_fills_defaults(self):
        known = M.discover()
        cfg = C.load(ROOT / "estate.example.toml", known)
        self.assertEqual(cfg["label_prefix"], "com.example.estate")
        self.assertEqual(cfg["paths"]["code"], str(self.home / "Code"))
        self.assertEqual(cfg["paths"]["bin"], str(self.home / ".local/bin"))
        self.assertEqual(cfg["keys"]["file"], str(self.home / ".config/agent-estate/keys.env"))
        self.assertEqual(cfg["harnesses"]["claude"], {"accounts": ["default"]})
        self.assertEqual(cfg["modules"]["tmp-cleanup"], {"path": "/tmp", "age": "1d"})
        self.assertEqual(cfg["machines"][0]["ssh"], "mac")

    def test_missing_file_says_what_to_do(self):
        with self.assertRaises(C.ConfigError) as e:
            C.load(self.tmp / "nope.toml")
        self.assertIn("estate.example.toml", str(e.exception))
        self.assertIn("ESTATE_CONFIG", str(e.exception))

    def test_bad_toml(self):
        self.cfg_path.write_text("label_prefix = \n")
        with self.assertRaises(C.ConfigError) as e:
            C.load()
        self.assertIn("not valid TOML", str(e.exception))

    def test_every_problem_is_reported_at_once(self):
        raw = tomllib.loads(self.write_config().read_text())
        raw["user"]["email"] = "not-an-email"
        raw["user"]["nmae"] = "typo"
        raw["machines"][0]["os"] = "ubuntu"
        raw["machines"][1]["role"] = "boss"
        raw["machines"][1]["name"] = "mac"
        raw["label_prefix"] = "estate"
        raw["colour"] = "blue"
        raw["keys"] = {"names": ["exa_key"]}
        with self.assertRaises(C.ConfigError) as e:
            C.validate(raw, path="x.toml")
        msg = str(e.exception)
        for needle in ("user.email", "user.nmae: unknown key", "machines[0].os",
                       "machines[1].role", "'mac' is used twice", "label_prefix",
                       "colour: unknown top-level key", "keys.names[0]"):
            self.assertIn(needle, msg)
        self.assertTrue(all(line.startswith("x.toml: ") for line in msg.splitlines()))

    def test_required_sections(self):
        with self.assertRaises(C.ConfigError) as e:
            C.validate({})
        msg = str(e.exception)
        for needle in ("user: missing", "label_prefix: missing", "git: missing",
                       "machines: missing", "harnesses: missing"):
            self.assertIn(needle, msg)

    def test_accounts_list_and_empty_list(self):
        raw = tomllib.loads(self.write_config().read_text())
        raw["harnesses"]["codex"] = {"accounts": ["main", "spare"]}
        self.assertEqual(C.validate(raw)["harnesses"]["codex"]["accounts"], ["main", "spare"])
        raw["harnesses"]["codex"] = {"accounts": []}
        with self.assertRaises(C.ConfigError):
            C.validate(raw)


class ModuleSettings(TempHome):
    def setUp(self):
        super().setUp()
        mdir = self.tmp / "modules"
        write_module(mdir, "base", meta='[defaults]\nage = "1d"\npath = "/tmp"\n')
        write_module(mdir, "top", requires='["base"]')
        self.known = M.discover(mdir)

    def test_defaults_merge_with_overrides(self):
        self.write_config(["base"], '\n[modules.base]\nage = "2d"\n')
        cfg = C.load(None, self.known)
        self.assertEqual(cfg["modules"]["base"], {"age": "2d", "path": "/tmp"})
        self.assertEqual(C.get(cfg, "modules.base.age"), "2d")

    def test_unknown_setting_unknown_module_and_missing_requirement(self):
        self.write_config(["top", "ghost"],
                          '\n[modules.base]\nagee = "2d"\n[modules.nobody]\nx = 1\n')
        with self.assertRaises(C.ConfigError) as e:
            C.load(None, self.known)
        msg = str(e.exception)
        self.assertIn("modules.base.agee: unknown setting", msg)
        self.assertIn("modules.nobody: no module named", msg)
        self.assertIn("no module named 'ghost'", msg)
        self.assertIn("'top' requires 'base'; enable it too", msg)


class Lookup(TempHome):
    def setUp(self):
        super().setUp()
        self.write_config()
        self.cfg = C.load()

    def test_get_dotted_and_machine_by_name(self):
        self.assertEqual(C.get(self.cfg, "user.email"), "test@example.com")
        self.assertEqual(C.get(self.cfg, "machines.vps.ssh"), "vps-alias")
        self.assertEqual(C.get(self.cfg, "machines.mac.ssh"), "mac")
        for bad in ("user.phone", "machines.nas.ssh", "_path", "paths.code.x"):
            with self.assertRaises(KeyError):
                C.get(self.cfg, bad)

    def test_this_machine(self):
        with mock.patch.object(socket, "gethostname", return_value="somewhere.local"):
            self.assertEqual(C.this_machine(self.cfg, "linux")["name"], "vps")
            self.assertEqual(C.this_machine(self.cfg, "mac")["name"], "mac")
            os.environ["ESTATE_MACHINE"] = "vps"
            self.assertEqual(C.this_machine(self.cfg, "mac")["name"], "vps")
            os.environ["ESTATE_MACHINE"] = "nas"
            self.assertIsNone(C.this_machine(self.cfg, "mac"))
        del os.environ["ESTATE_MACHINE"]
        with mock.patch.object(socket, "gethostname", return_value="VPS.example.ts.net"):
            self.assertEqual(C.this_machine(self.cfg, "mac")["name"], "vps")

    def test_two_linux_boxes_need_a_hostname(self):
        self.cfg["machines"].append({"name": "box2", "ssh": "box2", "role": "agents",
                                     "os": "linux", "hostname": "b2"})
        with mock.patch.object(socket, "gethostname", return_value="elsewhere"):
            self.assertIsNone(C.this_machine(self.cfg, "linux"))
        with mock.patch.object(socket, "gethostname", return_value="b2"):
            self.assertEqual(C.this_machine(self.cfg, "linux")["name"], "box2")

    def test_platform_override(self):
        os.environ["ESTATE_PLATFORM"] = "linux"
        self.assertEqual(C.current_platform(), "linux")
        os.environ["ESTATE_PLATFORM"] = "windows"
        with self.assertRaises(ValueError):
            C.current_platform()


class ConfigCli(TempHome):
    def test_check_and_get(self):
        self.write_config(["tmp-cleanup"])
        p = self.estate("config", "check")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("ok: "))
        self.assertEqual(self.estate("config", "get", "machines.vps.ssh").stdout, "vps-alias\n")
        self.assertEqual(self.estate("config", "get", "modules.enabled").stdout, "tmp-cleanup\n")
        self.assertEqual(self.estate("config", "get", "harnesses", "--json").stdout.strip(),
                         '{"claude": {"accounts": ["default"]}}')
        p = self.estate("config", "get", "user.phone")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no such config key: user.phone", p.stderr)

    def test_check_fails_with_every_problem(self):
        self.write_config(["no-such-module"])
        text = self.cfg_path.read_text().replace('os = "mac"', 'os = "beos"')
        self.cfg_path.write_text(text)
        p = self.estate("config", "check")
        self.assertEqual(p.returncode, 1)
        self.assertIn("machines[0].os", p.stderr)
        self.assertIn("no module named 'no-such-module'", p.stderr)
