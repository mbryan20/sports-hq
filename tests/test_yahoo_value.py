"""Yahoo group value: the season sim behind 'value of taking the other side', and the anonymous pool profile."""
import os
import sys
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "picks"))

try:
    import numpy  # noqa: F401
    HAVE_NP = True
except ImportError:  # test.yml installs numpy; requirements.txt (the 10-minute run) does not. Both modules need it (pool_profile via cards)
    HAVE_NP = False
if HAVE_NP:
    from pp import pool_profile, yahoo_value as V   # noqa: E402

PROFILE = {"weeks": [1, 2], "dog_rate_by_spread": [[0, 3, 0.4], [3, 7, 0.2], [7, 14, 0.05], [14, 99, 0.005]],
           "spreads": [1.5, 3.5, 6.5, 10.5, 17.5, 24.5], "me": {"points": 120, "lean": 0.8},
           "others": [{"points": 126, "lean": 0.6}, {"points": 124, "lean": 0.9}, {"points": 110, "lean": 1.5}]}


@unittest.skipUnless(HAVE_NP, "needs numpy")
class GroupValue(unittest.TestCase):
    def test_close_game_everyone_else_on_the_favorite_is_worth_flipping(self):
        games = [{"p_fav": 0.53, "spread": 1.5, "pub_dog": 0.05, "my_dog": False},
                 {"p_fav": 0.92, "spread": 21.5, "pub_dog": 0.02, "my_dog": False}]
        base, vals, combo = V.season_values(games, PROFILE, n=20000)
        self.assertGreater(vals[0], 0)          # near coin flip, chalky leaders: the dog gains ground
        self.assertLess(vals[1], 0)             # fading a 92% favorite only costs
        self.assertGreater(combo, 0)
        self.assertTrue(0 < base < 1)

    def test_profile_is_anonymous(self):
        picks = {"1": {"g": "AAA,1.5,BBB;CCC,10.5,DDD", "p": {"Me": "FF", "Leader": "FF", "Gambler": "DD", "HG": "--"}}}
        prof = pool_profile.build(picks, {"me": "Me", "points": {"Me": 10, "Leader": 12, "Gambler": 8}})
        self.assertEqual([o["points"] for o in prof["others"]], [12, 8])
        self.assertNotIn("Leader", str(prof))
        self.assertNotIn("Gambler", str(prof))



class KeepSavedPick(unittest.TestCase):
    """Nov 12: the card said 'switch Kansas to West Virginia' while its own season sim said Kansas raised Michael's
    chance to win the group (0.8% -> 1.0%). A saved pick the season sim favors is kept, with no CHANGE line."""
    def run_keep(self, val):
        import numpy as np
        from pp import cards as C
        rows = [{"sg": {"away": "Kansas", "home": "West Virginia"}}]
        picks = np.array([True])
        orig = C.season_flips
        C.season_flips = lambda *a: (0.008, [val], val, [{"p_fav": 0.51, "my_dog": False}], [], [0], {})
        try:
            kept = C.keep_saved_picks(rows, picks, [], [True], [0.51], [0.96],
                                      {"saved": {"picks": {"Kansas@West Virginia": "Kansas"}}})
        finally:
            C.season_flips = orig
        return kept, picks

    def test_kept_when_season_value_positive(self):
        kept, picks = self.run_keep(1.7)
        self.assertFalse(picks[0])
        self.assertEqual(kept, {0: "Your pick kept: Kansas wins 49%, helps your finish"})

    def test_switch_stands_when_season_value_negative(self):
        kept, picks = self.run_keep(-0.5)
        self.assertTrue(picks[0])
        self.assertEqual(kept, {})

    def test_switch_stands_when_gain_is_inside_sim_noise(self):
        kept, picks = self.run_keep(0.3)
        self.assertTrue(picks[0])
        self.assertEqual(kept, {})


PLACE = {"weeks": [1, 2], "dog_rate_by_spread": [[0, 3, 0.4], [3, 7, 0.2], [7, 14, 0.05], [14, 99, 0.005]],
         "spreads": [1.5, 3.5, 6.5, 10.5, 17.5, 24.5], "me": {"points": 184, "lean": 0.9, "dropped": 12},
         "others": [{"points": 193, "lean": 0.8, "dropped": 12}, {"points": 184, "lean": 1.0, "dropped": 11},
                    {"points": 183, "lean": 1.0, "dropped": 11}, {"points": 181, "lean": 1.2, "dropped": 12}]}


@unittest.skipUnless(HAVE_NP, "needs numpy")
class FinishingPlace(unittest.TestCase):
    """Nov 27: Yahoo's pick % is all Yahoo players, the group has no prize, and Yahoo drops each member's worst week."""
    def test_member_lean_shifts_the_yahoo_share(self):
        q = V.member_dog_probs([0.74, 0.08], [0.5, 1.0, 2.0])
        self.assertAlmostEqual(float(q[0, 1]), 0.74, places=3)        # lean 1 = the Yahoo-wide share itself
        self.assertLess(q[0, 0], q[0, 1])
        self.assertGreater(q[1, 2], q[1, 1])

    def test_drop_rule_adds_back_the_old_worst_week_when_a_new_week_is_worse(self):
        prof = {**PLACE, "me": {"points": 100, "lean": 1.0, "dropped": 12},
                "others": [{"points": 101, "lean": 1.0, "dropped": 5}]}
        # no games this week; one future week of 1 game: both score 0 or 1, so both drop the new week
        r = V.season_place([], prof, weeks_left=1, future_games=1, n=4000)
        # me: 100 + 12 + w - min(12, w) = 112 (w <= 1); other: 101 + 5 + w - min(5, w) = 106 -> I finish 1st
        self.assertEqual(r["rank"], 2)
        self.assertAlmostEqual(r["place"], 1.0)
        self.assertTrue(r["drop_rule"])

    def test_without_dropped_the_old_totals_are_used(self):
        prof = {**PLACE, "me": {"points": 100, "lean": 1.0}, "others": [{"points": 101, "lean": 1.0, "dropped": 5}]}
        r = V.season_place([], prof, weeks_left=0, n=1000)
        self.assertFalse(r["drop_rule"])
        self.assertAlmostEqual(r["place"], 2.0)

    def test_protecting_a_place_goes_with_the_herd_on_a_coin_flip(self):
        # coin flip where the group herds on the Yahoo underdog (74%); Michael tied for 4th with rivals right behind
        # (plus 20 near-locks so this week scores above everyone's dropped week and counts)
        games = [{"p_fav": 0.53, "spread": 2.5, "pub_dog": 0.74, "my_dog": False},
                 {"p_fav": 0.85, "spread": 14.0, "pub_dog": 0.02, "my_dog": False}] +                 [{"p_fav": 0.97, "spread": 24.5, "pub_dog": 0.01, "my_dog": False}] * 20
        r = V.season_place(games, PLACE, n=20000)
        self.assertGreater(r["flips"][0]["hold"], r["hold"])       # take the herd's side
        self.assertLess(r["flips"][1]["hold"], r["hold"])          # never fade an 85% favorite

    def test_profile_carries_dropped_without_names(self):
        picks = {"1": {"g": "AAA,1.5,BBB", "p": {"Me": "F", "Rival": "D"}}}
        prof = pool_profile.build(picks, {"me": "Me", "points": {"Me": 10, "Rival": 12}, "dropped": {"Me": 3, "Rival": 4}})
        self.assertEqual(prof["me"]["dropped"], 3)
        self.assertEqual(prof["others"][0]["dropped"], 4)
        self.assertNotIn("Rival", str(prof))


if __name__ == "__main__":
    unittest.main()
