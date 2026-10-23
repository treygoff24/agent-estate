"""The shell-footgun hook: a table with, per rule, commands it must refuse and
near-misses it must allow, plus the envelope, bypass and skip behaviour."""

import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, TempHome

HOOK = ROOT / "modules" / "guardrails" / "bin" / "footgun-hook"

# rule id -> (commands refused, near-miss commands allowed)
BATTERY = {
    "kill-by-pattern": (
        ["pkill -f 'my server'", "killall node", "sudo pkill python", "kill -9 -1", "kill -1",
         "bash -c 'pkill -f foo'", "echo $(pkill x)"],
        ["kill -TERM 1234", "kill -1 1234", "kill -- -1234", "pgrep -f foo", "pkill -P 4321",
         "echo pkill is banned", "git commit -m \"pkill -f x\""]),
    "rm-deadly-path": (
        ["rm -rf .", "rm -rf \"\"", "rm -rf /", "rm -rf ~", "rm -rf $HOME", "rm -rf *", "rm -rf ~/*",
         "trash ."],
        ["rm -rf ./build", "rm -rf node_modules", "rm file.txt", "rm .", "rm -rf '.cache-x'",
         "echo rm -rf ."]),
    "rm-unguarded-variable": (
        ["rm -rf \"$BUILD\"", "rm -rf \"$UNSET/subdir\"", "rm -rf ${DIR}/out", "cd x && rm -rf \"$P\"",
         "trash \"$P\""],
        ["rm -rf \"${BUILD:?}\"", "rm -rf \"${DIR:?}/out\"", "[ -n \"$P\" ] && rm -rf \"$P\"",
         "P=/tmp/x; rm -rf \"$P\"", "set -u; rm -rf \"$P\"", "for d in a b; do rm -rf \"$d\"; done",
         "rm -rf \"$HOME/.cache/x\"", "rm -rf '$BUILD'", "rm -rf build/$V", "rm \"$FILE\"",
         "rm -rf \"${DIR:-/tmp/fallback}\""]),
    "heredoc-unquoted-dollar": (
        ["cat <<EOF\nkey=${API_KEY}\nEOF", "ssh host 'python3 -' <<PY\nprint('$HOME')\nPY",
         "cat > f <<EOF\nvalue $(date)\nEOF", "tee f <<-EOF\n\t`id`\n\tEOF"],
        ["cat <<'EOF'\nkey=${API_KEY}\nEOF", "cat <<\"EOF\"\n$HOME\nEOF", "cat <<EOF\nno variables here\nEOF",
         "cat <<EOF\ncost is \\$5\nEOF", "echo $HOME", "cat <<-'EOF'\n\t$X\n\tEOF"]),
    "find-delete": (
        ["find . -name '*.log' -delete", "find ~/Code -type d -empty -delete"],
        ["find /tmp/scratch -name '*.o' -delete", "find . -name '*.log' -print", "find . -type f"]),
    "pipeline-exit-code": (
        ["make build | tail -5; echo \"exit=$?\"", "./run.sh 2>&1 | tail -20\necho $?",
         "run-checks | tail -3 && git commit -m x"],
        ["set -o pipefail; make build | tail -5; echo \"exit=$?\"", "make build | tail -5",
         "make build; echo $?", "run-checks > log.txt && git commit -m x",
         "make build | tail -5 && echo done"]),
    "heavy-test-unwrapped": (
        ["pytest -q", "python3 -m pytest tests/", "python -m unittest discover", "cargo test --workspace",
         "pnpm test", "npm run test", "make test", "go test ./...", "bash scripts/gate.sh", "./gate.sh",
         "vitest run", "cd app && pytest"],
        ["testrun app unit -- pytest -q", "testrun app gate -- bash scripts/gate.sh", "pytest --help",
         "cargo build", "pnpm install", "npm run lint", "echo pytest", "git log --oneline",
         "cat tests/test_gate.py"]),
    "rg-replace-flag": (["rg -rn foo src", "rg -ri pattern ."], ["rg -n foo src", "rg --replace x foo", "rg -r x foo"]),
    "rg-help-flag": (["rg -hn foo src", "rg -h foo"], ["rg -I foo src", "rg --help", "rg -n foo"]),
    "sed-bare-range": (["sed -n '10,20' file"], ["sed -n '10,20p' file", "sed 's/a/b/' file"]),
    "pnpm-double-dash": (["pnpm test -- src/a.test.ts", "pnpm run lint -- foo", "pnpm lint -- src/a.ts"],
                         ["pnpm lint src/a.ts", "pnpm exec vitest -- foo", "pnpm lint", "pnpm add -D -- foo"]),
    "perl-i-truncate": (["perl -i -e 'my $c = <>; print $c' f", "perl -i -e '$_ = <>; print' f"],
                        ["perl -pi -e 's/a/b/' f", "perl -ne 'print' f"]),
}


def run_hook(command, env=None, tool="Bash", cwd="/work/my-app", raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd})
    e = dict(os.environ) | (env or {})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=e)


def verdict(p):
    """The rule id that fired, or None for an allow."""
    if not p.stdout.strip():
        return None
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and out["hookEventName"] == "PreToolUse"
    import re
    return re.match(r"\[footgun:([a-z-]+)\]", out["permissionDecisionReason"]).group(1)


class Hook(TempHome):
    def setUp(self):
        super().setUp()
        self.env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.tmp / "xdg"),
                    "ESTATE_FOOTGUN_SKIP": ""}

    def test_battery_every_rule_refuses_its_bad_commands_and_allows_its_near_misses(self):
        self.assertGreaterEqual(len(BATTERY), 10)
        for rule, (bad, ok) in BATTERY.items():
            self.assertTrue(bad and ok, f"{rule}: empty battery proves nothing")
            for cmd in bad:
                with self.subTest(rule=rule, refused=cmd):
                    self.assertEqual(verdict(run_hook(cmd, self.env)), rule)
            for cmd in ok:
                with self.subTest(rule=rule, allowed=cmd):
                    self.assertIsNone(verdict(run_hook(cmd, self.env)))

    def test_every_rule_in_the_table_is_in_the_battery(self):
        out = subprocess.run([sys.executable, "-c",
                              "import importlib.machinery as m, importlib.util as u;"
                              f"l=m.SourceFileLoader('h','{HOOK}');s=u.spec_from_loader('h',l);"
                              "h=u.module_from_spec(s);l.exec_module(h);print(*[r for r,_ in h.RULES])"],
                             capture_output=True, text=True).stdout.split()
        self.assertGreaterEqual(len(out), 10)
        self.assertEqual(sorted(out), sorted(BATTERY))

    def test_denial_names_the_rule_and_the_fix(self):
        p = run_hook("pkill -f foo", self.env)
        reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertTrue(reason.startswith("[footgun:kill-by-pattern] "))
        self.assertIn("FOOTGUN-OK", reason)
        self.assertEqual(p.returncode, 0)

    def test_heavy_denial_names_the_testrun_line_for_this_repo(self):
        reason = json.loads(run_hook("pytest -q", self.env, cwd="/work/My_App").stdout
                            )["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("testrun my-app <kind> -- pytest -q", reason)
        self.assertNotIn("FOOTGUN-OK", reason)  # advertising the bypass invites skipping testrun

    def test_bypass_token_allows(self):
        self.assertIsNone(verdict(run_hook("pkill -f foo  # FOOTGUN-OK", self.env)))

    def test_only_bash_is_judged_and_junk_input_never_blocks(self):
        self.assertIsNone(verdict(run_hook("pkill -f foo", self.env, tool="Edit")))
        for raw in ("", "not json", "[]", json.dumps({"tool_name": "Bash"}),
                    json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}})):
            p = run_hook("", self.env, raw=raw)
            self.assertEqual((p.returncode, p.stdout), (0, ""), raw)

    def test_codex_argv_form_is_read(self):
        raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": ["bash", "-lc", "pkill -f foo"]}})
        self.assertEqual(verdict(run_hook("", self.env, raw=raw)), "kill-by-pattern")

    def test_shell_wrapper_scripts_and_substitutions_are_judged(self):
        self.assertEqual(verdict(run_hook("sh -c 'rm -rf .'", self.env)), "rm-deadly-path")
        self.assertEqual(verdict(run_hook("x=$(killall foo)", self.env)), "kill-by-pattern")

    def test_skip_file_and_env_switch_a_rule_off(self):
        self.assertEqual(verdict(run_hook("pytest -q", self.env)), "heavy-test-unwrapped")
        skipdir = self.tmp / "xdg" / "agent-estate"
        skipdir.mkdir(parents=True)
        (skipdir / "footgun-skip-guardrails").write_text("# comment\nheavy-test-unwrapped\n")
        self.assertIsNone(verdict(run_hook("pytest -q", self.env)))
        self.assertEqual(verdict(run_hook("pkill foo", self.env)), "kill-by-pattern")  # others stay on
        self.assertIsNone(verdict(run_hook("pkill foo", self.env | {"ESTATE_FOOTGUN_SKIP": "kill-by-pattern"})))


if __name__ == "__main__":
    unittest.main()
