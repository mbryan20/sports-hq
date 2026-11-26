"""Opponent research for the pools (pp.opponents): parsing the CFP All Picks dump, rebuilding balances, profiles,
the fair test against the 'favorite + minimum bet' baseline, Yahoo herding, prize-money EV, and that the
committed profile carries no names."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "picks"))

from pp import opponents as O   # noqa: E402

try:
    import numpy  # noqa: F401
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

CFP = """#SOURCE test
#PLAYERS
alice,bob,carol
#GAMES wk;fav;line;dog;covered
2;Big U;-10.5;Small St;F
2;Mid U;-3.5;Low U;D
3;Big U;-20.5;Tiny St;D
3;Mid U;-6.5;Low U;F
#PICKS game,playerIdx+side(F/D)+wager
0,0F5000 1,0F5000 0,1D2500 1,1D2500 0,2F10000
2,0D5000 3,0F5000 2,1F3000 3,2D10000
"""


class CfpParsing(unittest.TestCase):
    def setUp(self):
        self.p = O.parse_cfp(CFP)

    def test_parse(self):
        self.assertEqual(self.p["players"], ["alice", "bob", "carol"])
        self.assertEqual(len(self.p["games"]), 4)
        self.assertEqual(self.p["picks"][0], (0, 0, "F", 5000))
        self.assertEqual(len(self.p["picks"]), 9)

    def test_weekly_net(self):
        w = O.cfp_weekly(self.p)
        self.assertEqual(w["alice"][2], {"n": 2, "wager": 10000, "net": 0, "dog": 0, "big": 5000})   # +5000 -5000
        self.assertEqual(w["bob"][2]["net"], 0)          # dog lost game 0, dog won game 1
        self.assertEqual(w["carol"][2]["net"], 10000)
        self.assertEqual(w["alice"][3]["net"], 10000)    # both covered

    def test_reconstruct_backward_from_leaderboard(self):
        w = O.cfp_weekly(self.p)
        s = O.reconstruct_starts(w, {"alice": 20000, "carol": 0}, 3)
        self.assertEqual(s["alice"], {3: 10000.0, 2: 10000.0})
        # carol: +10000 in week 2, -10000 in week 3, now 0. Week 3 started at 10000; week 2 would start at 0
        # (impossible: a rebuy happened), so it is dropped
        self.assertEqual(s["carol"], {3: 10000.0})

    def test_missed_week_doubles_back(self):
        w = {"x": {2: {"n": 1, "wager": 5000, "net": 5000, "dog": 0, "big": 5000}}}
        s = O.reconstruct_starts(w, {"x": 7500}, 3)         # week 3 missed: lost 50% -> started week 3 at 15000
        self.assertEqual(s["x"], {3: 15000.0, 2: 10000.0})

    def test_rebuy_week_is_dropped(self):
        # A 6,000 balance busts in week 2, rebuys to 10,000, wins 5,000 in week 3 -> 15,000 now. Worked backward,
        # week 2 would start at 16,000 with a 6,000 bet (37%, under the site's 50% floor): that week is dropped.
        w = {"x": {2: {"n": 1, "wager": 6000, "net": -6000, "dog": 0, "big": 6000},
                   3: {"n": 1, "wager": 5000, "net": 5000, "dog": 0, "big": 5000}}}
        s = O.reconstruct_starts(w, {"x": 15000}, 3)
        self.assertEqual(s["x"], {3: 10000.0})

    def test_profiles_and_labels(self):
        prof, weekly, starts = O.cfp_profiles(self.p, {"alice": 20000, "bob": 4500, "carol": 0}, 3)
        self.assertEqual(prof["alice"]["frac_mean"], 1.0)
        self.assertEqual(prof["alice"]["label"], "risky")
        self.assertEqual(O.risk_label(0.55, 0.2), "risk-averse")
        self.assertEqual(O.risk_label(0.7, 0.4), "balanced")

    def test_fair_test_runs_and_reports_baseline(self):
        prof, weekly, starts = O.cfp_profiles(self.p, {"alice": 20000, "bob": 4500, "carol": 0}, 3)
        ft = O.cfp_fair_test(self.p, weekly, starts, min_hist=1)
        self.assertIn("baseline_min", ft["wager_share_mae"])
        self.assertEqual(ft["side_brier"]["n"], 9)
        self.assertLess(ft["side_brier"]["model"], 1.0)


YAHOO = {"1": {"g": "AAA,2.5,BBB;CCC,14.5,DDD", "p": {"m1": "DF", "m2": "DF", "m3": "FF", "HG": "DD"}},
         "2": {"g": "EEE,1.5,FFF;GGG,7.5,HHH", "p": {"m1": "DF", "m2": "FF", "m3": "F-", "HG": "--"}}}


class YahooGroup(unittest.TestCase):
    def test_profiles_skip_inactive(self):
        p = O.yahoo_profiles(YAHOO)
        self.assertNotIn("HG", p)
        self.assertEqual(p["m1"]["dogs"], 2)
        self.assertEqual(p["m3"]["picks"], 3)

    def test_fair_test(self):
        ft = O.yahoo_fair_test(YAHOO)
        self.assertEqual(ft["pick_brier"]["n"], 11)
        self.assertIn("group_dog_count_mae", ft)

    def test_herding_counts(self):
        ctx = {"abbr": {"AAA": "Alpha", "BBB": "Beta", "EEE": "Echo", "FFF": "Fox"},
               "ap": {"1": {"Beta": 10}, "2": {}},
               "games": [{"week": 1, "home": "Alpha", "away": "Beta", "hs": 20, "as": 24, "close": -2.5, "open": 1.0},
                         {"week": 2, "home": "Fox", "away": "Echo", "hs": 10, "as": 14, "close": 1.5, "open": 1.5}]}
        summ, herd = O.herding(YAHOO, ctx, pub={"1": {"Beta": 0.7}})
        self.assertEqual(summ["herd_games"], 1)                  # only week 1 game 1 (2 of 3 active members on the dog)
        w1 = [h for h in herd if h["week"] == 1][0]
        self.assertTrue(w1["dog_ranked_higher"])                 # Beta #10, Alpha unranked
        self.assertTrue(w1["open_fav_was_dog"])                  # opened Beta -1 (home +1), closed Alpha -2.5
        self.assertTrue(w1["dog_won"])
        self.assertEqual(w1["pub_dog"], 0.7)


@unittest.skipUnless(HAVE_NP, "needs numpy")
class PrizeEV(unittest.TestCase):
    def test_payout_ev_ties_split(self):
        import numpy as np
        me = np.array([100.0, 50.0, 80.0])
        opp = np.array([[90.0, 10.0], [90.0, 60.0], [80.0, 10.0]])
        ev, above = O.payout_ev(me, opp, [100, 50, 10])
        # sim 1: 1st (100); sim 2: 3rd (10); sim 3: tie for 1st with one rival -> (100+50)/2
        self.assertAlmostEqual(ev, (100 + 10 + 75) / 3)
        self.assertEqual(list(above), [0, 2, 0])

    def test_bto_payouts_shape(self):
        pay = O.bto_payouts(3675)
        self.assertAlmostEqual(pay["regular"][0], 0.40 * 3600)
        self.assertEqual(pay["regular"][3], 75.0)
        self.assertAlmostEqual(O.bto_playoff_ev(pay, True), 2 * O.bto_playoff_ev(pay, False))

    def test_cfp_season_bets_shift_balance(self):
        import numpy as np
        rng = np.random.default_rng(1)
        me, opp = O.cfp_season(10000, [(5000, 1.0)], 0.5, 1, [9000, 8000], [[0.5], [1.0]], 1, rng, n=500)
        self.assertTrue((me == 15000).all())                     # a sure win this week; no later weeks
        self.assertEqual(opp.shape, (500, 2))
        self.assertTrue((opp >= 0).all())


class CommittedProfileIsAnonymous(unittest.TestCase):
    def test_no_names_in_output(self):
        prof, report = O.build(CFP, {"alice": 20000, "bob": 4500, "carol": 0}, 3, YAHOO)
        text = json.dumps(prof)
        for name in ("alice", "bob", "carol", "m1", "m2", "m3"):
            self.assertNotIn(f'"{name}"', text)
        self.assertIn("alice", report["cfp"])                    # the private report keeps names

    def test_main_writes_private_report_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cfp_allpicks_test.txt").write_text(CFP, encoding="utf-8")
            (Path(d) / "cfp_balances.json").write_text(json.dumps({"last_week": 3, "balances": {"alice": 20000}}), encoding="utf-8")
            old_dir, old_out = O.POOL_OPP_DIR, O.OUT
            try:
                O.POOL_OPP_DIR = Path(d)
                O.OUT = Path(d) / "opponent_profile.json"
                O.main()
            finally:
                O.POOL_OPP_DIR, O.OUT = old_dir, old_out
            self.assertTrue((Path(d) / "opponent_report.json").exists())
            self.assertNotIn("alice", (Path(d) / "opponent_profile.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
