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


if __name__ == "__main__":
    unittest.main()


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
        kept, picks = self.run_keep(0.17)
        self.assertFalse(picks[0])
        self.assertEqual(kept, {0: "Your pick kept: Kansas wins 49%, season chance 0.8%→1.0%"})

    def test_switch_stands_when_season_value_negative(self):
        kept, picks = self.run_keep(-0.05)
        self.assertTrue(picks[0])
        self.assertEqual(kept, {})
