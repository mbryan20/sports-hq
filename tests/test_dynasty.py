"""3-Ball dynasty assets from the league sheet copy, and ESPN's IR-slot rule."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import digest, dynasty

UTC = dt.timezone.utc
OCT = dt.datetime(2026, 10, 30, 20, 0, tzinfo=UTC)


# made-up league: the real sheet copy is laptop-only (the repo is public)
R = ["1st Rd", "2nd Rd", "3rd Rd", "4th Rd"]
SHEET = {
    "me": "ME", "url": "https://example.com/sheet", "read": "2026-10-30", "picks_updated": "3/1/26",
    "minors_updated": "8/1/26",
    "picks": [["", "26 NFL", "27 NFL", "27 MLB", "28 NBA"],
              ["ME", "Ann", "Ann", R[0], R[0]], ["", R[1], R[1], "Ann", R[1]], ["", R[2], R[2], R[2], R[2]],
              ["", R[3], R[3], R[3], R[3]],
              ["Ann", "ME", "Bob", R[0], R[0]], ["", R[1], R[1], "ME", R[1]], ["", R[2], R[2], R[2], R[2]],
              ["", R[3], R[3], R[3], R[3]]],
    "minors": [["Ann", "ME"], [], ["Prospect A", "Prospect B"], ["Prospect C", ""], ["", "Prospect D"]],
}


class Assets(unittest.TestCase):
    def test_my_picks(self):
        h = dynasty.holdings(SHEET, OCT)
        self.assertNotIn((2026, "NFL"), h)                      # 2026 drafts are done
        # my 2027 1st went to Ann, and Ann's went to Bob, not to me
        self.assertEqual(h[(2027, "NFL")], {"mine": [(2, None), (3, None), (4, None)], "lost": [(1, "Ann")]})
        self.assertEqual(sorted(h[(2027, "MLB")]["mine"]), [(1, None), (2, "Ann"), (3, None), (4, None)])

    def test_block(self):
        b = dynasty.block("mlb", OCT, SHEET)
        self.assertEqual(b["lines"][0], "2027 MLB: 1st, 2nd (via Ann), 3rd, 4th (your 2nd went to Ann)")
        self.assertIn("2027 NFL: 2nd, 3rd, 4th (your 1st went to Ann)", b["lines"])
        self.assertEqual(b["lines"][-1], "Minor leaguers: Prospect B, Prospect D")
        self.assertTrue(dynasty.block("nba", OCT, SHEET)["lines"][0].startswith("2028 NBA"))

    def test_spring_still_shows_this_years_drafts(self):
        march = dt.datetime(2027, 3, 1, tzinfo=UTC)
        self.assertIn((2027, "MLB"), dynasty.holdings(SHEET, march))


class IrSlot(unittest.TestCase):
    def test_questionable_player_in_ir_blocks_moves(self):
        mont = {"id": "1", "name": "David Montgomery", "slot": "IR", "positions": ["RB"], "status": "Q",
                "why": "ESPN: QUESTIONABLE", "news": None, "kickoff": None, "started": False, "bye": False, "proj": 12.0}

        class League:
            name, sport, starters, bench, free_agents, ir_blocked = "Stempak", "nfl", [], [], [], [mont]
        item = digest.league_items(League, OCT)[0]
        self.assertTrue(item["urgent"])
        self.assertIn("Move David Montgomery out of IR: ESPN lists him Questionable", item["text"])


if __name__ == "__main__":
    unittest.main()
