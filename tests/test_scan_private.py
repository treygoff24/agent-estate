import os
import subprocess
import sys

from tests.helpers import ROOT, TempHome

SCAN = ROOT / "scripts" / "scan-private.py"
# Built by concatenation so this file does not trip the scanner itself.
HOME_PATH = "/Us" + "ers/zed/Code/thing"


class ScanPrivate(TempHome):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.markers = self.tmp / "markers"
        self.markers.write_text("# a comment\n\nacme[- ]?corp\nzed@example\\.org\n")
        os.environ["ESTATE_PRIVATE_MARKERS"] = str(self.markers)

    def put(self, rel, text, add=True):
        f = self.repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        if add:
            subprocess.run(["git", "-C", str(self.repo), "add", rel], check=True)

    def scan(self):
        return subprocess.run([sys.executable, str(SCAN), str(self.repo)],
                              capture_output=True, text=True)

    def test_clean_repo_passes(self):
        self.put("README.md", "nothing to see; paths like ~/Code and /home/<you>/x are fine\n")
        p = self.scan()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("clean: 0 hits", p.stderr)
        self.assertIn("(2 markers)", p.stderr)

    def test_hits_report_path_line_pattern_never_the_text(self):
        self.put("README.md", "line one\nWorks at ACME Corp, secretword\n")
        self.put("docs/a.md", f"see {HOME_PATH}\n")
        self.put("notes.txt", "mail Zed@Example.org\n", add=False)   # untracked, not ignored
        self.put(".gitignore", "ignored.txt\n")
        self.put("ignored.txt", "acmecorp\n", add=False)               # git-ignored: skipped
        self.put("acme-corp.md", "fine\n")                              # the path itself
        p = self.scan()
        self.assertEqual(p.returncode, 1)
        lines = set(p.stdout.splitlines())
        self.assertIn("README.md:2:acme[- ]?corp", lines)
        self.assertIn("notes.txt:1:zed@example\\.org", lines)
        self.assertIn("acme-corp.md:0:acme[- ]?corp", lines)
        self.assertTrue(any(ln.startswith("docs/a.md:1:") and "/Users/" in ln for ln in lines), lines)
        self.assertNotIn("ignored.txt", p.stdout)
        self.assertNotIn("secretword", p.stdout + p.stderr)
        self.assertEqual(len(lines), 4, lines)

    def test_license_copyright_line_is_the_only_allowance(self):
        self.put("LICENSE", "MIT License\n\nCopyright (c) 2026 Acme Corp\n\nacme corp may...\n")
        self.put("NOTICE", "Copyright (c) 2026 Acme Corp\n")
        p = self.scan()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(sorted(p.stdout.splitlines()),
                         ["LICENSE:5:acme[- ]?corp", "NOTICE:1:acme[- ]?corp"])

    def test_missing_marker_file_warns_loudly_and_passes(self):
        os.environ["ESTATE_PRIVATE_MARKERS"] = str(self.tmp / "absent")
        self.put("README.md", "acme corp\n")
        p = self.scan()
        self.assertEqual(p.returncode, 0)
        self.assertIn("WARNING: no private-marker file", p.stderr)
        self.assertIn("builtin only", p.stderr)
        # the built-in home-path marker still runs
        self.put("x.md", HOME_PATH + "\n")
        self.assertEqual(self.scan().returncode, 1)

    def test_bad_regex_is_an_error(self):
        self.markers.write_text("ok\n(unclosed\n")
        p = self.scan()
        self.assertEqual(p.returncode, 2)
        self.assertIn(":2: bad regex", p.stderr)

    def test_allow_line_blanks_only_what_it_matches(self):
        self.markers.write_text("acme[- ]?corp\nallow: https://github\\.com/acmecorp/[a-z0-9-]+\n")
        self.put("README.md", "see https://github.com/acmecorp/tool for it\n")
        self.put("other.md", "acmecorp wrote https://github.com/acmecorp/tool\n")
        p = self.scan()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(p.stdout.splitlines(), ["other.md:1:acme[- ]?corp"])
        self.assertIn("(1 markers, 1 allowances)", p.stderr)

    def test_home_path_marker_is_case_sensitive(self):
        self.put("api.md", "fetch(`/users/${id}/orders`)\n")
        self.assertEqual(self.scan().returncode, 0)
        self.put("home.md", "see " + HOME_PATH + "\n")
        self.assertEqual(self.scan().returncode, 1)
