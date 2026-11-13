"""Clear a Fix now line (Nov 12, Michael: "Need the ability to clear items like this on fix now")."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shq import cleared

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)
LINE = ("David Montgomery (RB) is Out → start Jordan Mason (10.7 proj)"
        " [ESPN, Nov 9 4:10p: Montgomery (groin) is likely to miss Sunday's game.]")


class Key(unittest.TestCase):
    def test_problem_part_only(self):
        self.assertEqual(cleared.key(LINE), "david montgomery rb is out")

    def test_new_projection_or_note_keeps_it_cleared_but_a_new_status_does_not(self):
        same = "David Montgomery (RB) is Out → start Woody Marks (9.1 proj) [ESPN, Nov 12 9:00a: limited practice]"
        self.assertEqual(cleared.key(same), cleared.key(LINE))
        self.assertNotEqual(cleared.key("David Montgomery (RB) is Doubtful → start Jordan Mason"), cleared.key(LINE))

    def test_same_rule_as_the_site(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            raise unittest.SkipTest("node not installed")
        src = (ROOT / "docs" / "lib" / "core.js").read_text(encoding="utf-8")
        fn = re.search(r"S\.clearKey = (t => .+?);\n", src).group(1)
        lines = [LINE, "Move Ajay Mitchell out of IR: ESPN lists him as active, so ESPN blocks adds",
                 "FLEX (FLEX) is empty → add Jaylen Waddle", "Luka Dončić (PG) is Out → start X"]
        got = json.loads(subprocess.run([node, "-e", f"const f = {fn}; console.log(JSON.stringify({json.dumps(lines)}.map(f)))"],
                                        check=True, capture_output=True, text=True, encoding="utf-8").stdout)
        self.assertEqual(got, [cleared.key(x) for x in lines])


class Record(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "cleared.json"

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_cleared_line_drops_from_the_digest_items_until_it_expires(self):
        item = cleared.parse(f"Clear: Stempak: {LINE[:60]}", f"{LINE}\n\n---\nLeague: Stempak\nPage: x\n", 9, "t")
        self.assertEqual((item["league"], item["issue"]), ("Stempak", 9))
        cleared.record(item, NOW, self.path)
        items = [{"league": "Stempak", "text": LINE, "urgent": True}, {"league": "Stempak", "text": "2 starters play today", "urgent": False}]
        self.assertEqual([i["text"] for i in cleared.drop("Stempak", items, NOW, self.path)], ["2 starters play today"])
        self.assertEqual(len(cleared.drop("Ball is Life", items, NOW, self.path)), 2)          # other leagues untouched
        later = NOW + timedelta(days=cleared.DAYS, minutes=1)
        self.assertEqual(len(cleared.drop("Stempak", items, later, self.path)), 2)              # back after a week

    def test_clearing_again_replaces_and_expired_rows_are_pruned(self):
        item = cleared.parse("Clear: Stempak: x", f"{LINE}\n\n---\nLeague: Stempak\n")
        cleared.record(item, NOW - timedelta(days=30), self.path)
        cleared.record(dict(item, issue=2), NOW, self.path)
        rows = json.loads(self.path.read_text(encoding="utf-8"))["items"]
        self.assertEqual([r["issue"] for r in rows], [2])

    def test_not_a_clear_issue(self):
        self.assertIsNone(cleared.parse("Feedback: hi", "no league here"))


class Workflow(unittest.TestCase):
    def test_guards(self):
        y = (ROOT / ".github" / "workflows" / "clear.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.issue.user.login == 'mbryan20' && github.event.issue.author_association == 'OWNER'", y)
        self.assertIn("contains(github.event.issue.labels.*.name, 'clear')", y)
        for line in y.splitlines():
            if "github.event.issue.body" in line or "github.event.issue.title }}" in line:
                self.assertRegex(line.strip(), r"^ISSUE_(BODY|TITLE): ")
        self.assertNotIn("--rebase", y)
        self.assertNotIn("${{ secrets", y)
        self.assertEqual(json.loads((ROOT / "docs" / "data" / "cleared.json").read_text(encoding="utf-8"))["items"], [])


if __name__ == "__main__":
    unittest.main()
