"""Moves skipped on HQ's fantasy cards (docs/data/decisions.json): matching rule, expiry, and that a skipped move leaves
the lists and is listed under "You skipped" (shq/decisions.py, docs/lib/skips.js; HQ fantasy live sync, Nov 14)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from shq import advice, decisions

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 14, 18, tzinfo=timezone.utc)

CASES = [
    ("start Devaughn Vele over Kaelon Black at SUPER_FLEX", "start|devaughnvele|kaelonblack"),
    ("Start Devaughn Vele (9.1) over Kaelon Black (6.0) at SUPER_FLEX, +3.1", "start|devaughnvele|kaelonblack"),
    ("Start Day'Ron Sharpe (BKN @ NYK, 6:30 PM) over Donte DiVincenzo at F: more minutes", "start|dayronsharpe|dontedivincenzo"),
    ("Add Geno Smith (QB, NYJ, 20.4/gm, value 159) for David Montgomery (RB, your RB3, 9.2/gm): starts at QB over Matthew Stafford",
     "add|genosmith|davidmontgomery"),
    ("add Geno Smith, drop David Montgomery before 10:00 PM", "add|genosmith|davidmontgomery"),
    ("Drop David Montgomery and add Geno Smith", "add|genosmith|davidmontgomery"),
    ("First move Ajay Mitchell out of IR (back Friday); then drop Saddiq Bey (1.2/g), add Paul Reed (3.1/g)", "add|paulreed|saddiqbey"),
    ("Kaelon Black (RB) is Out → start Devaughn Vele (9.1) [ESPN Nov 14]", "start|devaughnvele|kaelonblack"),
    ("add KC Concepcion Jr., drop Tre Tucker", "add|kcconcepcion|tretucker"),
    ("Bench Josh Allen", "bench josh allen"),
    ("drop Tre Tucker, add Ladd McConkey, start him at FLEX", "add|laddmcconkey|tretucker"),
    ("add Ladd McConkey, drop Tre Tucker, then start him", "add|laddmcconkey|tretucker"),
    ("move Ajay Mitchell from IR, dropping Saddiq Bey", "ir|ajaymitchell"),
    ("Move Ajay Mitchell out of IR: ESPN lists him as active, so ESPN blocks adds and drops", "ir|ajaymitchell"),
    ("start Josh Allen over Bo Nix, then bench Nix", "start|joshallen|bonix"),
    # the fantasy guards' real HQ step lines (HQ app, Nov 14)
    ("add Tyler Allgeier, drop Dameon Pierce", "add|tylerallgeier|dameonpierce"),
    ("drop Obi Toppin, add Jordan Goodwin (PHX), start him at UTIL over Dyson Daniels (no game)", "add|jordangoodwin|obitoppin"),
    ("drop Saddiq Bey (27, no game today), add Paul Reed (DET), start him at F over Matisse Thybulle (no game)", "add|paulreed|saddiqbey"),
    ("move Jarrett Allen (Day-to-day) from IR to bench, dropping Kevin Porter Jr. (unsigned)", "ir|jarrettallen"),
    ("drop Kevin Porter Jr., move Brandin Podziemski from IR to bench", "ir|brandinpodziemski"),
    ("optional: add Jerami Grant, start him at F over Franz Wagner (no ORL game)", "add jerami grant start him at f over franz wagner"),
    ("move Travis Etienne Jr. to IR if a slot is open", "toir|travisetienne"),
    ("Before 7:00 PM: add Tyler Allgeier, drop Dameon Pierce", "add|tylerallgeier|dameonpierce"),
]


def write(entries):
    d = tempfile.mkdtemp()
    p = Path(d) / "decisions.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    decisions._cache.clear()
    return p


class MatchingRule(unittest.TestCase):
    def test_keys(self):
        for text, want in CASES:
            self.assertEqual(decisions.move_key(text), want, text)

    def test_browser_copy_gives_the_same_keys(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        js = (ROOT / "docs/lib/skips.js").read_text(encoding="utf-8")
        prog = "global.window={};" + js + ";console.log(JSON.stringify(" + json.dumps([c[0] for c in CASES]) + ".map(window.SHQSKIP.key)))"
        out = subprocess.run([node, "-e", prog], check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(out.stdout), [c[1] for c in CASES])
        prog = "global.window={};" + js + ";console.log(JSON.stringify(" + json.dumps([c[0] for c in CASES]) + ".map(window.SHQSKIP.names)))"
        out = subprocess.run([node, "-e", prog], check=True, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(out.stdout), [decisions.names(c[0]) for c in CASES])


class Skips(unittest.TestCase):
    def test_missing_or_empty_file_means_no_skips(self):
        self.assertEqual(decisions.load(Path(tempfile.mkdtemp()) / "none.json"), [])
        p = write([])
        self.assertEqual(decisions.split("Kosmonauts", ["Start A (1) over B (2) at QB"], NOW, path=p)[1], [])

    def test_skip_leaves_the_list_with_a_tag_until_it_expires(self):
        p = write([{"id": "x1", "sport": "football", "app": "Sleeper", "league": "Sunday's Best",
                    "move": "start Devaughn Vele over Kaelon Black at SUPER_FLEX", "reason": "notworth", "at": "2026-11-14T15:00:00Z"},
                   {"id": "x2", "sport": "football", "league": "Sunday's Best", "move": "add Geno Smith, drop Tre Tucker",
                    "reason": "notnow", "until": "2026-11-14T12:00:00Z", "at": "2026-11-13T15:00:00Z"}])
        lines = ["Start Devaughn Vele (9.1) over Kaelon Black (6.0) at SUPER_FLEX, +3.1", "Add Geno Smith (QB) for Tre Tucker (WR)"]
        keep, gone = decisions.split("sunday's best", lines, NOW, path=p)
        self.assertEqual(keep, lines[1:])                        # x2's until passed: suggested again
        self.assertEqual(gone[0]["tag"], "You skipped this (Not worth it, Nov 14)")
        self.assertEqual(decisions.split("Kosmonauts", lines, NOW, path=p)[1], [])   # other leagues untouched
        self.assertEqual(len(decisions.split("Domo Arigato", lines, NOW, path=p)[1]), 1)   # Sleeper's name for it

    def test_app_league_names(self):
        p = write([{"league": "3-Ball Dynasty League", "sport": "basketball", "move": "add A, drop B", "at": "2026-11-14T15:00:00Z"},
                   {"league": "Damon’s Guilltoine League 2026", "sport": "football", "move": "add C, drop D", "at": "2026-11-14T15:00:00Z"},
                   {"league": "We playin basketball", "sport": "basketball", "move": "add E, drop F", "at": "2026-11-14T15:00:00Z"}])
        self.assertTrue(decisions.skipped("3-Ball BB", "Add A (x) for B (y)", NOW, path=p))
        self.assertFalse(decisions.skipped("3-Ball FB", "Add A (x) for B (y)", NOW, path=p))
        self.assertTrue(decisions.skipped("Guillotine", "add C, drop D", NOW, path=p))
        self.assertTrue(decisions.skipped("Ball is Life", "add E, drop F", NOW, path=p))

    def test_advice_lists_skip_and_record(self):
        p = write([{"league": "Guillotine", "move": "add Geno Smith, drop Woody Marks", "reason": "bad", "at": "2026-11-14T15:00:00Z"}])
        old = decisions.DECISIONS
        try:
            decisions.DECISIONS = p
            decisions._cache.clear()
            lg = SimpleNamespace(name="Guillotine", skipped=[])
            out = advice._unskipped(lg, ["Add Geno Smith (QB) for Woody Marks (RB)", "Add Ladd McConkey (WR) for Tre Tucker (WR)"], NOW)
        finally:
            decisions.DECISIONS = old
        self.assertEqual(out, ["Add Ladd McConkey (WR) for Tre Tucker (WR)"])
        self.assertEqual(lg.skipped[0]["tag"], "You skipped this (Bad advice, Nov 14)")


class Fallback(unittest.TestCase):
    def test_same_players_match_when_no_pattern_fits(self):
        p = write([{"league": "Ragonk Force", "sport": "basketball", "app": "ESPN",
                    "move": "optional: add Jerami Grant, start him at F over Franz Wagner (no ORL game)", "reason": "notworth",
                    "at": "2026-11-14T15:00:00Z"},
                   {"league": "We playin basketball", "move": "move Jarrett Allen from IR to bench, dropping Kevin Porter Jr.",
                    "at": "2026-11-14T15:00:00Z"}])
        self.assertEqual(decisions.names("optional: add Jerami Grant, start him at F over Franz Wagner (no ORL game)"),
                         ["jeramigrant", "franzwagner"])
        self.assertTrue(decisions.skipped("3-Ball BB", "For BLK: Jerami Grant (ORL, 1.4 blk) over Franz Wagner", NOW, path=p))
        self.assertFalse(decisions.skipped("3-Ball BB", "For BLK: Jerami Grant (ORL, 1.4 blk)", NOW, path=p))      # both names needed
        self.assertFalse(decisions.skipped("3-Ball FB", "Jerami Grant over Franz Wagner", NOW, path=p))           # other sport
        self.assertTrue(decisions.skipped("Ball is Life", "Move Jarrett Allen out of IR: ESPN lists him as active, so ...", NOW, path=p))
        self.assertFalse(decisions.skipped("Ball is Life", "Start Jarrett Allen (CLE) over X at C", NOW, path=p))   # one name: no fallback


class Wiring(unittest.TestCase):
    def test_file_trigger_and_pages(self):
        self.assertEqual(json.loads((ROOT / "docs/data/decisions.json").read_text(encoding="utf-8")), [])
        wf = (ROOT / ".github/workflows/run.yml").read_text(encoding="utf-8")
        self.assertIn("paths: [docs/data/decisions.json]", wf)
        self.assertIn("github.event_name != 'schedule'", wf)
        self.assertIn('sec("You skipped"', (ROOT / "docs/lib/core.js").read_text(encoding="utf-8"))
        wr = (ROOT / "docs/war-room-v2/index.html").read_text(encoding="utf-8")
        self.assertIn("../lib/skips.js", wr)
        self.assertIn("rowSkip(r)", wr)
        commit = (ROOT / ".github/commit_data.sh").read_text(encoding="utf-8")
        self.assertIn("git pull -q --rebase", commit)          # a skip pushed mid-run is pulled in, never overwritten


if __name__ == "__main__":
    unittest.main()
