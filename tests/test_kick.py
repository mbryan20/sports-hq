"""R1 / Q-029: the laptop kick (ops/kick.ps1) writes one log line on every run: started, skipped or FAILED, including
when gh isn't signed in (Nov 5: the scheduled tasks failed silently). Runs the real script with fake gh programs;
Windows only (the CI runner skips it). Never uses Michael's gh login or any token."""
import datetime as dt
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS = shutil.which("powershell")

# fake gh programs as PowerShell scripts (a .cmd would be cut at the "&" in the API URL by cmd.exe)
NOT_SIGNED_IN = '[Console]::Error.WriteLine("To get started with GitHub CLI, please run:  gh auth login"); exit 4\n'


def fake_ok(date):
    return ('switch ($args[0]) { "auth" { exit 0 } "workflow" { exit 0 } "api" { Write-Output "%s"; exit 0 } default { exit 9 } }\n'
            % date)


def utc(**ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


@unittest.skipUnless(os.name == "nt" and PS, "Windows PowerShell only")
class Kick(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "kick.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_kick(self, gh_text, *args, log=None, gh_path=None, path=None, drop=()):
        gh = gh_path or self.tmp / "gh.ps1"
        if gh_text is not None:
            gh.write_text(gh_text, encoding="ascii")
        env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", *drop)}
        env["TEMP"] = env["TMP"] = str(self.tmp)
        if path:
            env["PATH"] = path
        f = log or self.log
        p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "ops" / "kick.ps1"),
                            "-Gh", str(gh), "-Log", str(f), "-TokenFile", str(self.tmp / "no.token"), *args],
                           capture_output=True, text=True, env=env, timeout=60)
        return p.returncode, f.read_text(encoding="utf-8-sig") if f.is_file() else ""

    def test_not_signed_in_is_logged(self):
        code, text = self.run_kick(NOT_SIGNED_IN, "-Workflow", "run.yml", "-FreshMinutes", "20")
        self.assertEqual(code, 2)
        self.assertIn("run.yml: FAILED: gh is not signed in here and no saved token exists; nothing started", text)
        self.assertIn("Sign-in for the scheduled tasks", text)

    def test_started_and_skipped(self):
        code, text = self.run_kick(fake_ok(utc(hours=2)), "-Workflow", "run.yml", "-FreshMinutes", "20")
        self.assertEqual((code, text.strip().split(": ", 1)[1]), (0, "started"))
        code, text = self.run_kick(fake_ok(utc(minutes=3)), "-Workflow", "run.yml", "-FreshMinutes", "20")
        self.assertEqual(code, 0)
        self.assertRegex(text.strip().splitlines()[-1], r"run\.yml: skipped: data committed [2-4] min ago$")
        self.assertEqual(len(text.strip().splitlines()), 2)                    # one line per run

    def test_missing_localappdata_still_logs(self):
        # Nov 5: a scheduled run left no line at all; an empty LOCALAPPDATA killed the old script's parameter defaults
        code, text = self.run_kick(NOT_SIGNED_IN, drop=("LOCALAPPDATA",))
        self.assertEqual(code, 2)
        self.assertIn("FAILED: gh is not signed in", text)

    def test_gh_missing_is_logged(self):
        code, text = self.run_kick(None, gh_path=self.tmp / "nothere.exe", path=str(self.tmp))
        self.assertNotEqual(code, 0)
        self.assertIn("FAILED: gh isn't installed or can't start", text)

    def save_dummy_token(self, text):
        """A DPAPI-encrypted file the way -SaveToken writes it, holding a dummy string (never a real token)."""
        f = self.tmp / "no.token"
        subprocess.run([PS, "-NoProfile", "-Command",
                        f"ConvertTo-SecureString '{text}' -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -Path '{f}' -Encoding ascii"],
                       check=True, capture_output=True, timeout=60)

    def test_saved_token_reaches_gh_only_through_the_environment(self):
        self.save_dummy_token("dummy-not-a-token")
        gh = ('if ($env:GH_TOKEN -ne "dummy-not-a-token") { exit 4 }\n'
              'switch ($args[0]) { "auth" { exit 0 } "workflow" { exit 0 } default { exit 9 } }\n')
        code, text = self.run_kick(gh, "-Workflow", "model-health.yml")
        self.assertEqual((code, text.strip().split(": ", 1)[1]), (0, "started"))
        self.assertNotIn("dummy", text)                                         # never logged

    def test_unreadable_token_file_is_logged(self):
        (self.tmp / "no.token").write_text("garbage", encoding="ascii")
        code, text = self.run_kick(fake_ok(utc(hours=2)))
        self.assertEqual(code, 1)
        self.assertIn("FAILED: the saved token in", text)

    def test_unwritable_log_falls_back_to_temp(self):
        folder = self.tmp / "a-folder"
        folder.mkdir()
        code, _ = self.run_kick(NOT_SIGNED_IN, log=folder)                     # a folder can't be written as a file
        self.assertEqual(code, 2)
        self.assertIn("FAILED: gh is not signed in", (self.tmp / "sports-hq-kick.log").read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
