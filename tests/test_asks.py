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


if __name__ == "__main__":
    unittest.main()
