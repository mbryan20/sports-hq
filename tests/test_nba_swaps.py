"""NBA pickups as swaps (shq/nba_swaps.py): dead roster spots first, need-weighted this-week gain, the season-value
guard, IR slots, and dynasty protection (ownership and age)."""
import unittest

from shq import advice, nba_ages, nba_swaps, nba_values, radar
import test_nba_values as base

POOL = {
    **base.POOL,
    "8": base.pl("No Team Guy", 0, base.line(12, 3, 4, 10), gp=0, proj=base.line(12, 3, 4, 10)),       # pro team 0: dead
    "9": base.pl("Free Streamer", 1, base.line(14, 6, 6, 12)),          # ATL: 4 games this week
    "10": base.pl("Free Dud", 2, base.line(3, 0, 1, 5)),
    "11": base.pl("Free Out", 1, base.line(25, 7, 9, 17), injury="OUT"),
    "12": base.pl("Young Bench", 2, base.line(4, 1, 2, 6)),
}
ROSTER = [base.rp(2, "Volume Shooter", 1, 0), base.rp(6, "Bench Guy", 1, 12), base.rp(8, "No Team Guy", 0, 12),
          base.rp(12, "Young Bench", 2, 12), {**base.rp(3, "Low Volume", 2, 13), "injury": "OUT"}]
CATS = {"rows": [{"cat": "PTS", "outlook": "close"}, {"cat": "AST", "outlook": "lose"}, {"cat": "FG%", "outlook": "win"},
                 {"cat": "TO", "outlook": "win"}], "games_left": [5, 4]}


class Swaps(unittest.TestCase):
    def setUp(self):
        self.saved = radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates, dict(base.SNAP)
        radar.fetch_pool = lambda *a, **k: POOL
        radar.track_ownership = lambda pool, now: {}
        nba_ages.birth_dates = lambda: {"12": "2005-01-01", "6": "1995-01-01"}
        base.SNAP.update(roster=ROSTER, slot_counts={"0": 1, "12": 3, "13": 1})

    def tearDown(self):
        radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates, snap = self.saved
        base.SNAP.clear()
        base.SNAP.update(snap)

    def league(self, dynasty=False):
        lg = base.league()
        lg.dynasty = dynasty
        advice.player_values(lg)
        return lg

    def test_weights_favor_close_categories_and_average_one(self):
        w = nba_swaps.weights({"cats": ["PTS", "AST", "FG%", "TO"]}, CATS)
        self.assertAlmostEqual(sum(w.values()) / 4, 1)
        self.assertEqual(w["PTS"], 3 * w["AST"])
        self.assertEqual(set(nba_swaps.weights({"cats": ["PTS", "AST"]}, {**CATS, "games_left": [0, 0]}).values()), {1.0})

    def test_dead_spot_first_then_best_gain(self):
        lg = self.league()
        s = nba_swaps.build(lg, CATS)
        first = s["swaps"][0]
        self.assertEqual((first["drop"]["name"], first["dead"]), ("No Team Guy", True))
        self.assertEqual(first["add"]["name"], "Free Streamer")                 # the best healthy free agent
        self.assertIn("Drop No Team Guy (no NBA team, a dead roster spot), add Free Streamer (PG/SG, ATL, 4 games this week",
                      s["lines"][0])
        names = {(x["drop"]["name"], x["add"]["name"]) for x in s["swaps"]}
        self.assertFalse(any(a == "Free Out" for _, a in names))                 # out: never an add
        self.assertFalse(any(d == "Low Volume" for d, _ in names))               # IR slot: frees nothing
        self.assertEqual([p["name"] for p in s["dead"]], ["No Team Guy"])

    def test_gain_is_need_weighted_worth_difference(self):
        lg = self.league()
        s = nba_swaps.build(lg, CATS)
        w = nba_swaps.weights(lg.values, CATS)
        for x in s["swaps"][1:]:
            exp = nba_swaps.worth(x["add"], lg.values, w, 0) - nba_swaps.worth(x["drop"], lg.values, w, 0)
            self.assertAlmostEqual(x["gain"], round(exp, 1))
            self.assertGreaterEqual(x["gain"], nba_swaps.MIN_GAIN)
            self.assertGreaterEqual(x["add"]["v"], x["drop"]["v"] - nba_swaps.SEASON_SLACK)

    def test_never_trades_season_value_for_one_week(self):
        lg = self.league()
        s = nba_swaps.build(lg, CATS)
        self.assertNotIn("Volume Shooter", [x["drop"]["name"] for x in s["swaps"]])   # far better for the season

    def test_dynasty_keeps_young_players(self):
        drops = lambda dyn: [x["drop"]["name"] for x in nba_swaps.build(self.league(dyn), CATS)["swaps"]]
        self.assertIn("Young Bench", drops(False))
        self.assertNotIn("Young Bench", drops(True))                              # 21 years old
        self.assertIn("No Team Guy", drops(True))                                 # a dead spot goes either way

    def test_league_adds_are_swaps(self):
        lg = self.league()
        lg.cats = CATS
        lines = advice.adds(lg)
        self.assertTrue(lines[0].startswith("Drop No Team Guy"))


if __name__ == "__main__":
    unittest.main()
