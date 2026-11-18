"""Draft-pick mode for Domo Arigato (fantasy-rules.md rule 17, Nov 17): out of the playoff race, the page shows the
pick he holds now (worst record first, fewer points breaks a tie) and drops small start/sit swaps and points-only
pickups, but never tanks (OUT/bye/empty starters are still fixed; a 3+ point gap still shows)."""
import unittest
from pathlib import Path

from shq import draft_race as dr

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {"playoff_teams": 6, "playoff_week_start": 15, "last_scored_leg": 10}


def team(rid, w, l, pts):
    return {"roster_id": rid, "settings": {"wins": w, "losses": l, "fpts": int(pts), "fpts_decimal": round(pts % 1 * 100)}}


# Sunday's Best after week 10 of 2026 (Sleeper, Nov 17)
NOV17 = [team(1, 8, 2, 1532.6), team(2, 8, 2, 1443.4), team(3, 7, 3, 1368.6), team(4, 6, 4, 1399.6),
         team(5, 6, 4, 1361.7), team(6, 6, 4, 1174.7), team(7, 5, 5, 1207.3), team(8, 4, 6, 1221.1),
         team(9, 3, 7, 1368.1), team(10, 3, 7, 1052.4), team(11, 2, 8, 1172.8), team(12, 2, 8, 1136.1)]
NAMES = {10: "mattschadegg", 11: "Domo Arigato", 12: "TheParlay"}


class Race(unittest.TestCase):
    def test_domo_on_nov17_is_out_and_holds_pick_2(self):
        r = dr.build(SETTINGS, NOV17, NAMES, 11)
        self.assertTrue(r["out"])
        self.assertFalse(r["eliminated"])      # not mathematically, but winning out only ties the 6th seed's 6 wins
        self.assertEqual((r["record"], r["games_left"], r["cut_line"], r["pick"]), ("2-8", 4, 6, 2))
        self.assertIn("TheParlay (2-8, 1136.1 pts) holds #1", r["pick_line"])   # same record, fewer points: earlier pick
        self.assertIn("mattschadegg (3-7, 1052.4 pts) is #3", r["pick_line"])
        self.assertIn("rule 17", r["text"])

    def test_a_team_still_in_the_race_is_not_in_draft_mode(self):
        r = dr.build(SETTINGS, NOV17, NAMES, 7)     # 5-5: can reach 9 wins
        self.assertFalse(r["out"])
        self.assertIsNone(r["text"])

    def test_mathematically_eliminated(self):
        r = dr.build({**SETTINGS, "last_scored_leg": 13}, NOV17, NAMES, 11)   # 1 game left: best case 3 wins
        self.assertTrue(r["eliminated"] and r["out"])

    def test_missing_settings_means_no_mode(self):
        self.assertIsNone(dr.build({}, NOV17, NAMES, 11))

    def test_last_years_tie_break(self):
        # 2025: Buttered Toast 6-8 with 1714.4 pts picked 4th, TheParlay 6-8 with 1719.6 pts picked 5th
        ros = [team(1, 6, 8, 1714.4), team(2, 6, 8, 1719.6), team(3, 9, 5, 1800)] + [team(i, 10, 4, 1900) for i in range(4, 10)]
        self.assertLess(dr.build(SETTINGS, ros, {}, 1)["pick"], dr.build(SETTINGS, ros, {}, 2)["pick"])


class Filters(unittest.TestCase):
    def test_small_swaps_go_big_gaps_stay(self):
        self.assertFalse(dr.keep_move(1.2))     # Rodriguez over Kaelon Black, Nov 17
        self.assertTrue(dr.keep_move(3.0))

    def test_pickups_need_long_term_value(self):
        fa = lambda v, pos="RB": {"val": v, "positions": [pos]}
        self.assertFalse(dr.keep_add({"fa": fa(326), "drop": {"val": 254}}))   # Zonovan Knight for Tutu Atwell
        self.assertTrue(dr.keep_add({"fa": fa(650, "WR"), "drop": {"val": 258}}))   # Josh Cameron for Jalen Nailor
        self.assertFalse(dr.keep_add({"fa": fa(0, "DEF"), "drop": {"val": 0}}))     # defense stream
        self.assertTrue(dr.keep_add({"fa": fa(400), "drop": None}))                 # open roster spot

    def test_wired_into_the_site(self):
        self.assertIn('"draft_order"', (ROOT / "shq/config.py").read_text(encoding="utf-8"))
        adv = (ROOT / "shq/advice.py").read_text(encoding="utf-8")
        self.assertIn("draft_race.keep_move(gain)", adv)
        self.assertIn("draft_race.keep_add(a)", adv)
        run = (ROOT / "shq/run.py").read_text(encoding="utf-8")
        self.assertIn("lg.race = draft_race.build(", run)
        self.assertIn("draft_race.keep_move(gain)", run)   # the Weekly tab's start/sit too


if __name__ == "__main__":
    unittest.main()
