"""R1 / Q-029: the laptop kick (ops/kick.ps1) writes one log line on every run: started, skipped or FAILED, including
when gh isn't signed in (Nov 5: the scheduled tasks failed silently). Runs the real script with fake gh programs;
Windows only (the CI runner skips it). Never uses Michael's gh login or any token.
Q-037: a failed kick pushes once per outage. The pushes go to a local stand-in for ntfy, never the real topic."""
import datetime as dt
import http.server
import os
import threading
import shutil
import subprocess
import tempfile
import pathlib
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


class FakeNtfy(http.server.BaseHTTPRequestHandler):
    """Records each POST: (path, Title header, body)."""
    got = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        FakeNtfy.got.append((self.path, self.headers.get("Title"), body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@unittest.skipUnless(os.name == "nt" and PS, "Windows PowerShell only")
class Kick(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "kick.log"
        self.topic = self.tmp / "topic"          # absent unless a test writes it: no push at all
        FakeNtfy.got = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeNtfy)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.ntfy = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_kick(self, gh_text, *args, log=None, gh_path=None, path=None, drop=(), ntfy=None):
        gh = gh_path or self.tmp / "gh.ps1"
        if gh_text is not None:
            gh.write_text(gh_text, encoding="ascii")
        env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN", *drop)}
        env["TEMP"] = env["TMP"] = str(self.tmp)
        if path:
            env["PATH"] = path
        f = log or self.log
        p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "ops" / "kick.ps1"),
                            "-Gh", str(gh), "-Log", str(f), "-TokenFile", str(self.tmp / "no.token"),
                            "-AlertFile", str(self.tmp / "kick.alerted"), "-TopicFile", str(self.topic),
                            "-NtfyBase", ntfy or self.ntfy, *args],
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
        # defensive: with LOCALAPPDATA empty the first version's parameter defaults failed before anything was logged
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

    def test_no_topic_file_no_push(self):
        code, text = self.run_kick(NOT_SIGNED_IN)
        self.assertEqual(code, 2)
        self.assertIn("no phone alert (no ntfy topic file)", text)
        self.assertEqual(FakeNtfy.got, [])

    def test_failure_pushes_once_per_outage(self):
        self.topic.write_text("fake-topic-q037\n", encoding="ascii")
        self.run_kick(NOT_SIGNED_IN, "-Workflow", "run.yml")
        self.run_kick(NOT_SIGNED_IN, "-Workflow", "model-health.yml")          # same outage, other workflow
        self.assertEqual(len(FakeNtfy.got), 1)
        path, title, body = FakeNtfy.got[0]
        self.assertEqual(path, "/fake-topic-q037")
        self.assertEqual(title, "Sports HQ: laptop can't start GitHub jobs")
        self.assertIn("gh is not signed in here and no saved token exists. Jobs run late on GitHub's own schedule", body)
        self.assertIn("Fix: ops/designs/Q-014.md", body)
        lines = self.log.read_text(encoding="utf-8-sig").strip().splitlines()
        self.assertEqual(len(lines), 2)                                         # still one line per run
        self.assertTrue(lines[0].endswith("; phone alert sent"))
        self.assertTrue(lines[1].endswith("; phone alert already sent for this outage"))
        self.assertNotIn("fake-topic-q037", self.log.read_text(encoding="utf-8-sig"))
        # a working kick ends the outage; the next failure pushes again
        code, _ = self.run_kick(fake_ok(utc(hours=2)), "-Workflow", "run.yml", "-FreshMinutes", "20")
        self.assertEqual(code, 0)
        self.assertFalse((self.tmp / "kick.alerted").exists())
        self.run_kick(NOT_SIGNED_IN)
        self.assertEqual(len(FakeNtfy.got), 2)

    def test_dispatch_failure_pushes_per_workflow(self):
        self.topic.write_text("fake-topic-q037", encoding="ascii")
        gh = ('switch ($args[0]) { "auth" { exit 0 } "workflow" { Write-Output "HTTP 404: workflow not found"; exit 1 } '
              'default { exit 9 } }\n')
        code, text = self.run_kick(gh, "-Workflow", "no-such.yml")
        self.assertEqual(code, 1)
        self.assertIn("FAILED: gh couldn't start no-such.yml (HTTP 404: workflow not found); phone alert sent", text)
        self.run_kick(gh, "-Workflow", "no-such.yml")
        self.assertEqual(len(FakeNtfy.got), 1)
        self.assertEqual((self.tmp / "kick.alerted").read_text(encoding="ascii").split(), ["dispatch:no-such.yml"])

    def test_push_failure_is_logged_and_retried(self):
        self.topic.write_text("fake-topic-q037", encoding="ascii")
        dead = "http://127.0.0.1:9"                                             # nothing listens there
        code, text = self.run_kick(NOT_SIGNED_IN, ntfy=dead)
        self.assertEqual(code, 2)
        self.assertIn("; phone alert failed: ", text)
        self.assertNotIn("fake-topic-q037", text)
        self.assertFalse((self.tmp / "kick.alerted").exists())                  # not remembered: the next run tries again
        self.run_kick(NOT_SIGNED_IN)
        self.assertEqual(len(FakeNtfy.got), 1)


class TaskSettingsDoc(unittest.TestCase):
    """The registration block in ops/designs/Q-014.md must keep the kick tasks at normal priority (Nov 10: at the default
    priority 7 PowerShell starved for memory and never ran kick.ps1 before the time limit)."""

    def test_registration_uses_normal_priority_and_room_to_start(self):
        doc = (pathlib.Path(__file__).resolve().parent.parent / "ops" / "designs" / "Q-014.md").read_text(encoding="utf-8")
        line = next(ln for ln in doc.splitlines() if ln.startswith("$set = New-ScheduledTaskSettingsSet"))
        self.assertIn("-Priority 4", line)
        self.assertIn("New-TimeSpan -Minutes 15", line)


if __name__ == "__main__":
    unittest.main()
