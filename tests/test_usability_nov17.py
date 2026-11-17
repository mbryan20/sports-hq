"""Sports HQ usability fixes P1-P3 (HQ usability check Nov 16, findings-sports.md; Claude Ops, Nov 17):
P1 the home counts, the Today tile and the Pool Picks tile come from one list (SHQ.feed), and that list includes the
picks page's red CHANGE lines (docs/picks/alerts.json) until the card's week is over; P2 a "Do this now" strip first on
the home page, and What's new / War Room / picks open as one-line rows on a phone; P3 links to his HQ on every page,
the "Guilltoine" typo fixed, and the War Room's missing icon (its one 404)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "picks"))


class PickAlerts(unittest.TestCase):
    def test_picks_build_writes_the_change_lines_with_the_weeks_end(self):
        from pp import cards
        d = Path(tempfile.mkdtemp())
        with mock.patch.object(cards, "DOCS", d):
            cards.write_alerts({"generated_iso": "2026-11-12T03:00:00+00:00", "alerts": ["CHANGE: Yahoo: yours A → card B (why)"]})
        got = json.loads((d / "alerts.json").read_text(encoding="utf-8"))
        self.assertEqual(got["alerts"], ["CHANGE: Yahoo: yours A → card B (why)"])
        self.assertTrue(got["over"].startswith("2026-11-17T00:00:00"))      # the Tuesday after the card was built

    def test_home_reads_them_into_the_same_list_as_the_counts(self):
        core = (DOCS / "lib/core.js").read_text(encoding="utf-8")
        self.assertIn("picks/alerts.json", core)
        self.assertIn('S.pickAlerts(d).forEach(t => items.push({ kind: "pick"', core)
        home = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn('kpi(picks.length, "Picks to change"', home)
        self.assertIn("picks.slice(0, 3)", home)                              # the Pool Picks tile lists the same items
        self.assertNotIn("No stale-line edges open right now", home)


class DoNowAndPages(unittest.TestCase):
    def test_do_this_now_strip_comes_first(self):
        home = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn('innerHTML = SHQ.doNowHTML(d) + kpis', home)
        core = (DOCS / "lib/core.js").read_text(encoding="utf-8")
        self.assertIn('["fix", "risk", "move", "pick"].includes(i.kind)', core)

    def test_long_pages_open_as_one_line_rows(self):
        self.assertIn('<details class="it"', (DOCS / "whats-new/index.html").read_text(encoding="utf-8"))
        wr = (DOCS / "war-room-v2/index.html").read_text(encoding="utf-8")
        self.assertIn('<details class="card"><summary>', wr)
        self.assertIn('id="railfold"', wr)
        self.assertIn("flex-wrap:nowrap;overflow-x:auto", wr)
        picks = (ROOT / "picks/pp/cards.py").read_text(encoding="utf-8")
        self.assertIn("<details class='pool'", picks)
        self.assertIn("<summary>Ask Claude about these picks</summary>", picks)


class LinksTypoIcon(unittest.TestCase):
    def test_hq_links_on_every_page(self):
        core = (DOCS / "lib/core.js").read_text(encoding="utf-8")
        self.assertIn("https://claude.ai/artifact/RMES5QXJbfnJuqouufBUSq", core)
        self.assertIn("${S.hqLinks()}", core)                                 # the shared footer
        self.assertIn("RMES5QXJbfnJuqouufBUSq", (DOCS / "index.html").read_text(encoding="utf-8"))

    def test_guillotine_spelled_right(self):
        from shq.leagues import fix_name
        self.assertEqual(fix_name("Damon’s Guilltoine League 2026"), "Damon’s Guillotine League 2026")
        self.assertIsNone(fix_name(None))
        self.assertIn('.replace("Guilltoine", "Guillotine")', (ROOT / "warroom/model.py").read_text(encoding="utf-8"))

    def test_war_room_pages_have_an_icon(self):
        for f in ("war-room-v2/index.html", "war-room-v2/compare.html"):
            self.assertIn('rel="icon" href="../icons/icon-192.png"', (DOCS / f).read_text(encoding="utf-8"), f)
        self.assertTrue((DOCS / "icons/icon-192.png").exists())


if __name__ == "__main__":
    unittest.main()
