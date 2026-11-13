"""Ask Claude (Q-054): the issue the league page's box opens -> question; answers kept per league in asks.json."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from shq import asks

BODY = ("Should I put in a claim for KC Concepcion and drop Tre Tucker?\n\n---\nLeague: Guillotine\n"
        "Move on screen: add KC Concepcion, drop Tre Tucker → Not worth it (−0.2 points of win odds)\nPage: https://x/\n")


class Parse(unittest.TestCase):
    def test_question_league_and_move(self):
        q = asks.parse("Ask: Guillotine: Should I put in a claim", BODY, "12", "2026-11-11T15:00:00Z", names=["Guillotine", "Stempak"])
        self.assertEqual(q["league"], "Guillotine")
        self.assertEqual(q["issue"], 12)
        self.assertEqual(q["question"], "Should I put in a claim for KC Concepcion and drop Tre Tucker?")
        self.assertTrue(q["move"].startswith("add KC Concepcion, drop Tre Tucker"))

    def test_unknown_league_is_general_and_title_is_a_fallback(self):
        q = asks.parse("Ask: Nowhere: who wins?", "who wins?\n\n---\nLeague: Nowhere\n", 3, None, names=["Guillotine"])
        self.assertEqual(q["league"], "General")
        q = asks.parse("Ask: Stempak: start Herbert?", "", 4, None, names=["Stempak"])
        self.assertEqual((q["league"], q["question"]), ("Stempak", "start Herbert?"))

    def test_windows_line_endings(self):
        q = asks.parse("Ask: Stempak: x", BODY.replace("\n", "\r\n").replace("Guillotine", "Stempak"), 5, None, names=["Stempak"])
        self.assertEqual(q["league"], "Stempak")


SHOT = "https://github.com/user-attachments/assets/0f1e2d3c-aaaa-bbbb-cccc-123456789abc"


class Screenshots(unittest.TestCase):
    """Nov 12: screenshots pasted into the GitHub issue reach Claude; only GitHub's image hosts are fetched."""
    def test_found_and_taken_out_of_the_question(self):
        body = (f"Montgomery still shows out?\n\n![Screenshot 2026-11-12]({SHOT})\n<img width=\"400\" alt=\"x\" src=\"{SHOT}2\" />\n"
                "![evil](https://evil.example/a.png)\n\n---\nLeague: Stempak\n")
        q = asks.parse("Ask: Stempak: Montgomery", body, 7, None, names=["Stempak"])
        self.assertEqual(q["images"], [SHOT, SHOT + "2"])
        self.assertEqual(q["question"], "Montgomery still shows out?")

    def test_screenshot_only_question(self):
        q = asks.parse("Ask: Stempak: ", f"![s]({SHOT})\n\n---\nLeague: Stempak\n", 8, None, names=["Stempak"])
        self.assertEqual(q["question"], "(see the screenshot)")

    def test_at_most_four(self):
        self.assertEqual(len(asks.images("".join(f"![a]({SHOT}{i})" for i in range(9)))), asks.MAX_IMAGES)

    def test_download_keeps_images_only(self):
        class R:
            def __init__(self, kind, data): self.headers, self.data = {"Content-Type": kind}, data
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return self.data[:n]
        answers = {SHOT: R("image/png", b"\x89PNG..."), SHOT + "2": R("text/html", b"<html>")}
        with tempfile.TemporaryDirectory() as d:
            q = asks.fetch_images({"images": [SHOT, SHOT + "2"]}, d, opener=lambda req, timeout: answers[req.full_url])
            self.assertEqual([Path(f).name for f in q["image_files"]], ["1.png"])
            self.assertEqual(q["images_failed"], 1)

    def test_record_counts_them(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            row = asks.record({"issue": 1, "league": "Stempak", "question": "Q", "images": [SHOT]}, "A", p)["leagues"]["Stempak"][0]
            self.assertEqual(row["shots"], 1)


class Record(unittest.TestCase):
    def setUp(self):
        fd, name = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.path = Path(name)
        self.path.write_text('{"updated": null, "leagues": {}}', encoding="utf-8")

    def tearDown(self):
        self.path.unlink()

    def test_newest_first_and_a_rerun_replaces(self):
        q = {"issue": 1, "league": "Guillotine", "question": "Q1", "asked": "t0"}
        asks.record(q, "A1", self.path, now="2026-11-11T15:01:00Z")
        asks.record(dict(q, issue=2, question="Q2"), "A2", self.path, now="2026-11-11T15:05:00Z")
        d = asks.record(dict(q, question="Q1"), "A1 again", self.path, now="2026-11-11T15:09:00Z")
        rows = d["leagues"]["Guillotine"]
        self.assertEqual([(r["issue"], r["a"]) for r in rows], [(1, "A1 again"), (2, "A2")])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["updated"], "2026-11-11T15:09:00Z")

    def test_keeps_twenty_and_trims_long_answers(self):
        for i in range(25):
            d = asks.record({"issue": i, "league": "Stempak", "question": f"Q{i}"}, "line\n" * 2000, self.path)
        rows = d["leagues"]["Stempak"]
        self.assertEqual(len(rows), asks.KEEP)
        self.assertEqual(rows[0]["issue"], 24)
        self.assertLessEqual(len(rows[0]["a"]), asks.MAX_ANSWER + 60)
        self.assertIn("GitHub thread", rows[0]["a"])

    def test_cli_empty_answer_says_so(self):
        qf = self.path.with_suffix(".q.json")
        qf.write_text(json.dumps({"issue": 9, "league": "Guillotine", "question": "Q"}), encoding="utf-8")
        old = asks.ASKS
        asks.ASKS = self.path
        try:
            self.assertEqual(asks.main(["record", str(qf), str(self.path.with_suffix(".missing"))]), 0)
        finally:
            asks.ASKS = old
            qf.unlink()
        row = json.loads(self.path.read_text(encoding="utf-8"))["leagues"]["Guillotine"][0]
        self.assertIn("didn't finish", row["a"])


class Workflow(unittest.TestCase):
    """The answerer only runs for the owner's own issues, and issue text never reaches the shell."""
    def test_guards(self):
        y = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ask.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.issue.user.login == 'mbryan20' && github.event.issue.author_association == 'OWNER'", y)
        self.assertIn("contains(github.event.issue.labels.*.name, 'ask')", y)
        self.assertNotIn("issue_comment", y)
        self.assertNotIn("id-token", y)
        self.assertNotIn("run: echo \"${{ github.event.issue", y)
        for line in y.splitlines():
            if "github.event.issue.body" in line or "github.event.issue.title }}" in line:
                self.assertRegex(line.strip(), r"^ISSUE_(BODY|TITLE): ")
        self.assertIn("git add docs/data/asks.json", y)
        self.assertNotIn("--rebase", y.replace("--no-rebase", ""))
        # re-ask (workflow_dispatch): only Michael can start it, and only for his own "ask" issue
        self.assertIn("github.event_name == 'workflow_dispatch' && github.actor == 'mbryan20'", y)
        self.assertIn('assert i["author"]["login"] == "mbryan20"', y)
        self.assertIn('assert any(l["name"] == "ask" for l in i["labels"])', y)
        # the answer is recorded onto the newest asks.json each try, so a re-run never hits a merge conflict
        self.assertIn("git checkout -q -f -B ask-answer origin/main", y)


if __name__ == "__main__":
    unittest.main()
