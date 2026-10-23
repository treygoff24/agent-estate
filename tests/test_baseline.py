"""The baseline module. Nothing here runs as root or touches the real firewall,
systemd or home: system commands are stubs on PATH, and BASELINE_ROOT points
every system path (/etc, /run, /var) at a temp directory."""

import json
import os
import subprocess

from tests.helpers import ROOT, TempHome

MOD = ROOT / "modules" / "baseline"

# Every stub logs its argv to $FAKE_LOG. Some answer from files in $FAKE_STATE.
STUBS = {
    # A stateful nft: the loaded `inet estate` table is the file $FAKE_STATE/loaded.
    "nft": 'echo "nft $*" >> "$FAKE_LOG"\n'
           'L="$FAKE_STATE/loaded"\n'
           'case "$*" in\n'
           '  "-c -f"*) exit 0 ;;\n'
           '  "-f "*) cp "$2" "$L" ;;\n'
           '  "delete table inet estate") [ -z "$FAKE_NFT_SLOW_DELETE" ] || sleep "$FAKE_NFT_SLOW_DELETE"; rm -f "$L" ;;\n'
           '  "list table inet estate") [ -f "$L" ] || exit 1\n'
           '     grep -v "^#" "$L" | grep -v "^$" | grep -v "^delete table" ;;\n'
           'esac\n',
    "systemd-run": 'echo "systemd-run $*" >> "$FAKE_LOG"\n[ ! -f "$FAKE_STATE/no-systemd-run" ]\n',
    "systemctl": 'echo "systemctl $*" >> "$FAKE_LOG"\n'
                 'for w in "$@"; do [ -f "$FAKE_STATE/off-$w" ] && exit 3; done\nexit 0\n',
    "loginctl": 'echo "loginctl $*" >> "$FAKE_LOG"\n'
                'mkdir -p "$BASELINE_ROOT/var/lib/systemd/linger" && touch "$BASELINE_ROOT/var/lib/systemd/linger/$2"\n',
    "tailscale": 'echo "tailscale $*" >> "$FAKE_LOG"\n[ -f "$FAKE_STATE/tailscale-up" ]\n',
    "dpkg": 'exit 0\n',
    "apt-get": 'echo "apt-get $*" >> "$FAKE_LOG"\n',
    "adduser": 'echo "adduser $*" >> "$FAKE_LOG"\n',
    "gpasswd": 'echo "gpasswd $*" >> "$FAKE_LOG"\n',
    "curl": 'echo "curl $*" >> "$FAKE_LOG"\n',
    "getent": 'echo "$2:x:1000:1000::/var/lib/agents/$2:/bin/bash"\n',
    "swapon": 'echo /dev/zram0\n',
    "restic": 'echo "restic $*" >> "$FAKE_LOG"\n',
    "id": 'if [ "$1" = "-u" ]; then echo 1000; elif [ "$1" = "-nG" ]; then echo "${FAKE_GROUPS:-agent}"; else exit 0; fi\n',
}


class BaselineBase(TempHome):
    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "fakebin"
        self.fake.mkdir()
        self.fstate = self.tmp / "fstate"
        self.fstate.mkdir()
        for name, body in STUBS.items():
            p = self.fake / name
            p.write_text("#!/usr/bin/env bash\n" + body)
            p.chmod(0o755)
        self.log = self.tmp / "calls.log"
        self.log.write_text("")
        self.sysroot = self.tmp / "root"
        self.sysroot.mkdir()
        self.env = {"PATH": f"{self.fake}:{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                    "FAKE_STATE": str(self.fstate), "BASELINE_ROOT": str(self.sysroot),
                    "ESTATE_PLATFORM": "linux"}

    def calls(self):
        return self.log.read_text().splitlines()

    def sh(self, args, **kw):
        e = dict(os.environ) | self.env | kw.pop("env", {})
        return subprocess.run([str(a) for a in args], capture_output=True, text=True, env=e,
                              stdin=subprocess.DEVNULL, **kw)

    def tailscale_up(self, up=True):
        f = self.fstate / "tailscale-up"
        f.touch() if up else f.unlink(missing_ok=True)


class Firewall(BaselineBase):
    def render(self, *flags):
        p = self.sh([MOD / "firewall.sh", "render", *flags])
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_render_shape(self):
        r = self.render()
        self.assertIn("policy drop", r)
        for want in ("iif lo accept", "ct state established,related accept", 'iifname "tailscale0" accept',
                     "udp dport 41641 accept"):
            self.assertIn(want, r)
        self.assertNotIn("dport 22", r)  # public SSH is off by default
        self.assertNotIn("incus", r)

    def test_public_ssh_only_when_set(self):
        r = self.render("--public-ssh", "true", "--ssh-port", "2222")
        self.assertIn("tcp dport 2222 accept", r)
        self.assertIn('iifname "tailscale0" accept', r)

    def test_no_tailscale_drops_interface_rule(self):
        self.assertNotIn("tailscale0", self.render("--tailscale-iface", ""))

    def test_bad_flags_refused(self):
        p = self.sh([MOD / "firewall.sh", "render", "--ssh-port", "22; reboot"])
        self.assertNotEqual(p.returncode, 0)

    def apply(self):
        p = self.sh([MOD / "firewall.sh", "apply"])
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def pending(self):
        return (self.sysroot / "run/agent-estate-nft-pending").exists()

    def test_dead_man_unconfirmed_reverts(self):
        p = self.apply()
        self.assertIn("reverts in 90s", p.stdout)
        self.assertTrue(self.pending())
        runs = [c for c in self.calls() if c.startswith("systemd-run")]
        self.assertEqual(len(runs), 1)
        self.assertIn("--on-active=90s", runs[0])
        self.assertTrue(any(c.startswith("nft -f") for c in self.calls()))
        # the timer fires, nobody confirmed: the table is deleted
        revert = self.sysroot / "usr/local/sbin/estate-firewall"
        self.assertTrue(revert.exists())
        p = self.sh([revert, "revert"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("nft delete table inet estate", self.calls())
        self.assertFalse(self.pending())
        self.assertFalse((self.sysroot / "etc/nftables.conf").exists())  # never persisted

    def test_dead_man_confirmed_survives(self):
        self.apply()
        p = self.sh([MOD / "firewall.sh", "confirm"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.pending())
        self.assertIn("systemctl stop estate-nft-revert.timer", self.calls())
        self.assertTrue((self.sysroot / "etc/nftables.conf").read_text().startswith("# agent-estate"))
        # a late timer fire after confirm must not delete the table
        self.sh([self.sysroot / "usr/local/sbin/estate-firewall", "revert"])
        self.assertNotIn("nft delete table inet estate", self.calls())

    # ---- confirm only ever persists a live, unexpired, unchanged pending apply ----

    def fw(self, *args, **kw):
        return self.sh([MOD / "firewall.sh", *args], **kw)

    def loaded(self):
        return (self.fstate / "loaded").exists()

    def persisted(self):
        return (self.sysroot / "etc/nftables.conf").exists()

    def test_confirm_after_the_dead_man_reverted_is_refused_and_persists_nothing(self):
        self.apply()
        revert = self.sysroot / "usr/local/sbin/estate-firewall"
        self.assertEqual(self.sh([revert, "revert"]).returncode, 0)
        self.assertFalse(self.loaded())
        p = self.fw("confirm")
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("apply again", p.stderr)
        self.assertIn("fresh", p.stderr.lower())
        self.assertFalse(self.persisted())
        self.assertFalse(any(c.startswith("systemctl enable nftables") for c in self.calls()))
        self.assertFalse((self.sysroot / "etc/agent-estate/nftables.conf.new").exists())

    def test_confirm_within_the_deadline_persists(self):
        self.apply()
        self.assertTrue((self.sysroot / "etc/agent-estate/nftables.conf.new").exists())
        p = self.fw("confirm")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.persisted())
        self.assertIn("systemctl enable nftables", self.calls())
        self.assertFalse(self.pending())
        self.assertTrue(self.loaded())  # confirming keeps the rules up
        # a second confirm has nothing outstanding
        self.assertNotEqual(self.fw("confirm").returncode, 0)

    def test_confirm_with_no_apply_is_refused(self):
        p = self.fw("confirm")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("apply", p.stderr)
        self.assertFalse(self.persisted())

    def test_confirm_after_the_deadline_is_refused(self):
        p = self.sh([MOD / "firewall.sh", "apply"], env={"BASELINE_NOW": "1000"})
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.fw("confirm", env={"BASELINE_NOW": "1091"})  # one second past the 90 s deadline
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("deadline", p.stderr)
        self.assertFalse(self.persisted())
        p = self.fw("confirm", env={"BASELINE_NOW": "1090"})  # on the deadline: still allowed
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.persisted())

    def test_confirm_when_the_loaded_table_is_not_the_pending_ruleset_is_refused(self):
        self.apply()
        (self.fstate / "loaded").write_text("table inet estate { chain input { policy accept; } }\n")
        p = self.fw("confirm")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("loaded", p.stderr)
        self.assertFalse(self.persisted())
        (self.fstate / "loaded").unlink()  # table gone entirely
        self.assertNotEqual(self.fw("confirm").returncode, 0)
        self.assertFalse(self.persisted())

    def test_a_new_apply_supersedes_the_old_pending_one(self):
        self.apply()
        self.apply()
        p = self.fw("confirm")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.persisted())

    def test_confirm_during_a_running_revert_is_refused(self):
        import subprocess as sp
        import time
        self.apply()
        revert = self.sysroot / "usr/local/sbin/estate-firewall"
        env = dict(os.environ) | self.env | {"FAKE_NFT_SLOW_DELETE": "2"}
        r = sp.Popen([str(revert), "revert"], env=env, stdout=sp.PIPE, stderr=sp.PIPE, text=True,
                     stdin=sp.DEVNULL)
        try:
            for _ in range(100):  # wait until the revert is inside its nft delete
                if "nft delete table inet estate" in self.calls():
                    break
                time.sleep(0.05)
            self.assertIn("nft delete table inet estate", self.calls())
            p = self.fw("confirm")
            self.assertNotEqual(p.returncode, 0, p.stdout)
            self.assertFalse(self.persisted())
        finally:
            r.communicate(timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.loaded())
        self.assertFalse(self.persisted())

    def test_cannot_arm_means_no_ruleset_left(self):
        (self.fstate / "no-systemd-run").touch()
        p = self.sh([MOD / "firewall.sh", "apply"])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("nft delete table inet estate", self.calls())
        self.assertFalse(self.pending())

    def test_syntax_failure_loads_nothing(self):
        (self.fake / "nft").write_text('#!/usr/bin/env bash\necho "nft $*" >> "$FAKE_LOG"\n[ "$1" != -c ]\n')
        p = self.sh([MOD / "firewall.sh", "apply"])
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(any(c.startswith("nft -f") for c in self.calls()))


class RootSetup(BaselineBase):
    def keys(self):
        k = self.tmp / "authorized_keys"
        k.write_text("ssh-ed25519 AAAAFAKE test\n")
        return k

    def setup_args(self, *extra):
        return [MOD / "root-setup.sh", "--agent-user", "agent", "--authorized-keys", self.keys(), *extra]

    def tree(self):
        return sorted(str(p.relative_to(self.sysroot)) for p in self.sysroot.rglob("*"))

    def test_dry_run_lists_steps_and_changes_nothing(self):
        env = {"BASELINE_ROOT": ""}  # real paths, but --dry-run must touch none of them
        p = self.sh(self.setup_args("--dry-run", "--zram", "true", "--backups", "true"), env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for step in ("packages", "agents' login", "Tailscale", "unattended security updates",
                     "zram swap", "firewall"):
            self.assertIn(step, p.stdout)
        self.assertIn("would run: loginctl enable-linger agent", p.stdout)
        self.assertIn("would write: /etc/ssh/sshd_config.d/00-estate.conf", p.stdout)
        self.assertIn("zram-tools", p.stdout)
        self.assertIn("restic", p.stdout)
        # the only commands that may have run are read-only probes
        mutating = [c for c in self.calls() if not c.startswith(("tailscale ip",))]
        self.assertEqual(mutating, [])
        self.assertEqual(self.tree(), [])

    def test_packages_include_core_and_toolchain_and_the_flag_turns_the_toolchain_off(self):
        # the dpkg stub says everything is installed, which lists every wanted package
        on = self.sh(self.setup_args("--dry-run")).stdout
        for pkg in ("git", "python3", "curl", "ca-certificates", "build-essential", "nodejs", "npm"):
            self.assertRegex(on, rf"\b{pkg}\b", pkg)
        off = self.sh(self.setup_args("--dry-run", "--toolchain", "false")).stdout
        for pkg in ("git", "python3", "curl", "ca-certificates"):
            self.assertRegex(off, rf"\b{pkg}\b", pkg)
        for pkg in ("build-essential", "nodejs", "npm"):
            self.assertNotIn(pkg, off)
        self.assertNotEqual(self.sh(self.setup_args("--toolchain", "maybe")).returncode, 0)

    def test_a_time_sync_failure_warns_and_the_firewall_still_loads(self):
        (self.fstate / "off-chrony").touch()
        p = self.sh(self.setup_args("--public-ssh", "true", "--tailscale", "false"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("WARNING: time sync (chrony) could not start", p.stdout)
        self.assertTrue(any(c.startswith("nft -f") for c in self.calls()), self.calls())

    def test_no_tailscale_dry_run_prints_no_empty_interface_flag_and_end_message_says_what_is_next(self):
        p = self.sh(self.setup_args("--dry-run", "--tailscale", "false", "--public-ssh", "true"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would run: firewall.sh apply", p.stdout)
        self.assertNotIn("--tailscale-iface", p.stdout)
        p = self.sh(self.setup_args("--public-ssh", "true", "--tailscale", "false"))
        self.assertIn("INSTALL.md", p.stdout.splitlines()[-1])

    def test_refuses_without_root(self):
        p = self.sh([MOD / "root-setup.sh"], env={"BASELINE_ROOT": ""})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("run as root", p.stderr)

    def test_bad_user_refused(self):
        p = self.sh([MOD / "root-setup.sh", "--agent-user", "x; rm -rf /", "--dry-run"])
        self.assertNotEqual(p.returncode, 0)

    def test_firewall_not_applied_while_tailscale_down(self):
        self.tailscale_up(False)
        p = self.sh(self.setup_args())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("NOT applied", p.stdout)
        self.assertFalse(any(c.startswith("nft") for c in self.calls()))
        self.assertTrue((self.sysroot / "etc/apt/apt.conf.d/52estate-updates").exists())

    def test_public_ssh_applies_without_tailscale(self):
        self.tailscale_up(False)
        p = self.sh(self.setup_args("--public-ssh", "true", "--tailscale", "false"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(any(c.startswith("nft -f") for c in self.calls()))

    def test_second_run_changes_nothing(self):
        self.tailscale_up()
        self.assertEqual(self.sh(self.setup_args()).returncode, 0)
        self.sh([MOD / "firewall.sh", "confirm"])
        before = self.tree()
        p = self.sh(self.setup_args())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.tree(), before)
        self.assertIn("unchanged: ruleset already applied", p.stdout)
        self.assertNotIn("wrote:", p.stdout)
        self.assertEqual(sum(c.startswith("systemd-run") for c in self.calls()), 1)  # no re-arm


class CheckAndInstall(BaselineBase):
    def setUp(self):
        super().setUp()
        self.write_config(["baseline"])

    def row(self):
        p = self.estate("doctor", "--json", env=self.env)
        rows = {r["name"]: r for r in json.loads(p.stdout)["checks"]}
        return rows["baseline"]

    def converge(self):
        keys = self.tmp / "ak"
        keys.write_text("ssh-ed25519 AAAAFAKE test\n")
        self.tailscale_up()
        p = self.sh([MOD / "root-setup.sh", "--agent-user", "agent", "--authorized-keys", keys])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_fails_before_root_setup(self):
        r = self.row()
        self.assertEqual(r["status"], 1, r)
        self.assertIn("SSH is not key-only", r["summary"])

    def test_install_prints_exact_root_command_and_changes_nothing(self):
        p = self.estate("install", "baseline", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"sudo bash {MOD}/root-setup.sh --agent-user agent --tailscale true "
                      "--public-ssh false --ssh-port 22 --zram false --backups false --toolchain true", p.stdout)
        self.assertEqual(list(self.sysroot.rglob("*")), [])
        self.assertFalse((self.home / ".config/systemd").exists())

    def test_unconfirmed_warns_then_confirmed_ok(self):
        self.converge()
        r = self.row()
        self.assertEqual(r["status"], 2, r)
        self.assertIn("not confirmed", r["summary"])
        self.sh([MOD / "firewall.sh", "confirm"])
        r = self.row()
        self.assertEqual(r["status"], 0, r)
        self.assertIn("tailnet only", r["summary"])

    def test_check_detects_sudo_group_and_drift(self):
        self.converge()
        self.sh([MOD / "firewall.sh", "confirm"])
        p = self.estate("doctor", "--json", env=self.env | {"FAKE_GROUPS": "agent sudo"})
        row = {r["name"]: r for r in json.loads(p.stdout)["checks"]}["baseline"]
        self.assertEqual(row["status"], 1)
        self.assertIn("must not have sudo", row["summary"])
        # config now wants public SSH: installed ruleset no longer matches
        self.write_config(["baseline"], "\n[modules.baseline]\npublic_ssh = true\n")
        r = self.row()
        self.assertEqual(r["status"], 1)
        self.assertIn("differs from the config", r["summary"])

    def test_tailscale_down_warns(self):
        self.converge()
        self.sh([MOD / "firewall.sh", "confirm"])
        self.tailscale_up(False)
        r = self.row()
        self.assertEqual(r["status"], 2)
        self.assertIn("not connected", r["summary"])

    def test_mac_checks_only_tailscale(self):
        p = self.estate("doctor", "--json", env=self.env | {"ESTATE_PLATFORM": "mac"})
        r = {x["name"]: x for x in json.loads(p.stdout)["checks"]}["baseline"]
        self.assertEqual(r["status"], 2, r)  # tailscale stub not up
        self.tailscale_up()
        p = self.estate("doctor", "--json", env=self.env | {"ESTATE_PLATFORM": "mac"})
        r = {x["name"]: x for x in json.loads(p.stdout)["checks"]}["baseline"]
        self.assertEqual(r["status"], 0, r)

    def test_mac_without_tailscale_says_it_is_not_required(self):
        self.write_config(["baseline"], "\n[modules.baseline]\ntailscale = false\n")
        p = self.estate("doctor", "--json", env=self.env | {"ESTATE_PLATFORM": "mac"})
        r = {x["name"]: x for x in json.loads(p.stdout)["checks"]}["baseline"]
        self.assertEqual(r["status"], 0, r)
        self.assertIn("not required", r["summary"])
        self.assertNotIn("Tailscale up", r["summary"])

    def test_backups_need_repo(self):
        self.write_config(["baseline"], "\n[modules.baseline]\nbackups = true\n")
        r = self.row()
        self.assertEqual(r["status"], 1)
        self.assertIn("backup_repo is empty", r["summary"])

    def backup_config(self):
        keyfile = self.tmp / "keys.env"
        keyfile.write_text("RESTIC_PASSWORD=not-a-real-secret\n")
        self.write_config(["baseline"], f'''
[keys]
file = "{keyfile}"

[modules.baseline]
backups = true
backup_repo = "sftp:user@example.com:/backups"
backup_time = "02:30"
''')

    def test_backups_install_and_check(self):
        self.backup_config()
        self.converge()
        self.sh([MOD / "firewall.sh", "confirm"])
        p = self.estate("install", "baseline", "--dry-run", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("would write", p.stderr)
        self.assertFalse((self.home / ".config/systemd/user").exists())

        p = self.estate("install", "baseline", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ud = self.home / ".config/systemd/user"
        svc = (ud / "com.example.estate.baseline-restic-backup.service").read_text()
        self.assertIn("Environment=RESTIC_REPOSITORY=sftp:user@example.com:/backups", svc)
        self.assertIn("EnvironmentFile=" + str(self.tmp / "keys.env"), svc)
        self.assertNotIn("not-a-real-secret", svc)  # secrets never land in units
        timer = (ud / "com.example.estate.baseline-restic-backup.timer").read_text()
        self.assertIn("OnCalendar=*-*-* 02:30:00", timer)
        self.assertIn("Sun", (ud / "com.example.estate.baseline-restic-maintain.timer").read_text())
        self.assertEqual(self.estate("install", "baseline", env=self.env).returncode, 0)  # idempotent

        r = self.row()  # everything in place, but no backup has run yet
        self.assertEqual(r["status"], 2, r)
        self.assertIn("no backup has completed", r["summary"])
        (self.state / "baseline").mkdir(parents=True)
        import time
        (self.state / "baseline/last-backup").write_text(str(int(time.time())))
        self.assertEqual(self.row()["status"], 0)
        (self.state / "baseline/last-backup").write_text(str(int(time.time()) - 5 * 86400))
        self.assertEqual(self.row()["status"], 2)

        (self.tmp / "keys.env").write_text("OTHER=1\n")
        r = self.row()
        self.assertEqual(r["status"], 1)
        self.assertIn("RESTIC_PASSWORD is not defined", r["summary"])

    def test_backup_script_runs_restic_with_retention(self):
        env = {"RESTIC_REPOSITORY": "x", "RESTIC_PASSWORD": "y", "ESTATE_STATE": str(self.state),
               "BASELINE_BACKUP_PATHS": "/a /b", "BASELINE_KEEP_DAILY": "3"}
        (self.fake / "restic").write_text(
            '#!/usr/bin/env bash\necho "restic $*" >> "$FAKE_LOG"\n[ "$1" != cat ]\n')
        p = self.sh([MOD / "restic-backup"], env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls()
        self.assertIn("restic init", calls)
        self.assertTrue(any(c.startswith("restic backup") and c.endswith("/a /b") for c in calls))
        self.assertTrue(any("forget" in c and "--keep-daily 3" in c and "--prune" not in c for c in calls))
        self.assertTrue((self.state / "baseline/last-backup").exists())
        self.assertNotIn("y", " ".join(c for c in calls if "PASSWORD" in c))

    def test_uninstall_removes_timers_only(self):
        self.backup_config()
        self.estate("install", "baseline", env=self.env)
        ud = self.home / ".config/systemd/user"
        self.assertTrue(any(ud.glob("*restic*")))
        p = self.estate("uninstall", "baseline", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(any(ud.glob("*restic*")))
