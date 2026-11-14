"""Nov 14 improvements: What's new page data, Ask at home/work, the Pool Picks key and Ask box, ROS ranks file."""
import json
import re
import unittest
from pathlib import Path

from shq import asks

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class WhatsNew(unittest.TestCase):
    def test_every_item_says_what_why_notice_and_undo(self):
        d = json.loads((DOCS / "data/whatsnew.json").read_text(encoding="utf-8"))
        ns = [x["n"] for x in d["items"]]
        self.assertEqual(sorted(ns), list(range(1, len(ns) + 1)))
        self.assertEqual(ns, sorted(ns, reverse=True))          # newest first
        for x in d["items"]:
            for k in ("title", "changed", "why", "notice", "undo", "area", "date"):
                self.assertTrue(x.get(k), (x["n"], k))

    def test_page_and_home_tile(self):
        page = (DOCS / "whats-new/index.html").read_text(encoding="utf-8")
        self.assertIn("data/whatsnew.json", page)
        self.assertIn("SHQASK.mount", page)
        self.assertIn('data-go="whats-new/"', (DOCS / "index.html").read_text(encoding="utf-8"))


class AskTwoWays(unittest.TestCase):
    def test_ask_js_has_work_and_private_home_paths(self):
        js = (DOCS / "lib/ask.js").read_text(encoding="utf-8")
        self.assertIn("https://claude.ai/new?", js)
        self.assertIn("issues/new?", js)
        self.assertIn("anyone can read GitHub questions", js)
        self.assertNotIn("secrets", js)

    def test_move_box_has_both_buttons(self):
        js = (DOCS / "lib/move.js").read_text(encoding="utf-8")
        self.assertIn("data-askhome", js)
        self.assertIn("Ask at work (GitHub, public)", js)

    def test_page_topics_file_under_their_page(self):
        body = "Why the switch?\n\n---\nLeague: Pool Picks\nPage: x\n"
        q = asks.parse("Ask: Pool Picks: Why the switch?", body, 9, "2026-11-14T16:00:00Z", names=asks.leagues() or asks.TOPICS)
        self.assertEqual(q["league"], "Pool Picks")


class PoolPicksKey(unittest.TestCase):
    def test_builder_and_page_have_the_key_and_ask_box(self):
        src = (ROOT / "picks/pp/cards.py").read_text(encoding="utf-8")
        self.assertIn("READ_HTML", src)
        self.assertIn("{READ_HTML}", src)
        page = (DOCS / "picks/index.html").read_text(encoding="utf-8")
        for s in ("How to read the CHANGE lines", 'id="askpicks"', "../lib/ask.js"):
            self.assertIn(s, page)


class RosRanks(unittest.TestCase):
    def test_keys_match_the_pages(self):
        d = json.loads((DOCS / "data/ros.json").read_text(encoding="utf-8"))
        self.assertTrue(d["sources"])
        for k, p in d["players"].items():
            name, pos = k.split("|")
            self.assertRegex(name, r"^[a-z]+$")
            self.assertEqual(pos, p["pos"])
            self.assertIn(p["basis"], ("source", "Claude's judgment"))
            self.assertTrue(p["why"])
        self.assertIn("braelonallen|RB", d["players"])


if __name__ == "__main__":
    unittest.main()
