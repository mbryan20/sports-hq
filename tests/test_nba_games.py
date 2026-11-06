"""NBA games grid and streaming plan (shq/nba_games.py): games per team this week and next, back-to-backs, my games
capped by starting spots, streamers on need-weighted value."""
import unittest

from shq import advice, nba_ages, nba_games, radar
import test_nba_values as base

CATS = {"rows": [{"cat": "PTS", "outlook": "close"}, {"cat": "AST", "outlook": "lose"}, {"cat": "FG%", "outlook": "win"},
                 {"cat": "TO", "outlook": "win"}], "games_left": [5, 3]}


class Games(unittest.TestCase):
    def setUp(self):
        self.saved = radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates
        radar.fetch_pool = lambda *a, **k: base.POOL
        radar.track_ownership = lambda pool, now: {}
        nba_ages.birth_dates = lambda: {}

    def tearDown(self):
        radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates = self.saved

    def test_grid_this_week_and_next_with_back_to_backs(self):
        lg = base.league()
        now, nxt = nba_games.week_days(lg)
        self.assertEqual((now, nxt), ([9, 10, 11, 12, 13], list(range(14, 21))))   # Wed..Sun, then Mon..Sun
        groups, b2b = nba_games.grid(lg, now)
        self.assertEqual(groups, [[4, ["ATL"]], [2, ["BOS"]]])
        self.assertEqual(b2b, ["ATL"])                                             # 11-12-13
        self.assertEqual(nba_games.grid(lg, nxt), ([[2, ["ATL"]], [1, ["BOS"]]], ["ATL"]))

    def test_my_games_count_only_open_starting_spots(self):
        lg = base.league()
        now, nxt = nba_games.week_days(lg)
        roster = [base.rp(2, "A", 1, 0), base.rp(6, "B", 1, 12), base.rp(3, "C", 2, 12)]
        self.assertEqual(nba_games.lineup_games(lg, roster, now, 1), 5)            # 1 spot: 9, 10, 11, 12, 13
        self.assertEqual(nba_games.lineup_games(lg, roster, now, 3), 4 + 4 + 2)
        self.assertEqual(nba_games.lineup_games(lg, roster, nxt, 3), 2 + 2 + 1)

    def test_build_has_both_weeks_mine_and_streamers(self):
        lg = base.league()
        advice.player_values(lg)
        g = nba_games.build(lg, CATS)
        self.assertEqual((g["mine"]["now"], g["mine"]["opp"]), (5, 3))              # from the category table
        self.assertEqual(g["mine"]["next"], 2)                                      # 1 starting spot, ATL plays 15 and 16
        self.assertTrue(g["now"]["span"].startswith("Wed Oct 28"))
        self.assertTrue(g["streamers"])
        self.assertFalse(any(s.startswith(("Volume Shooter", "Star", "Hurt Vet")) for s in g["streamers"]))   # rostered or out
        self.assertRegex(g["streamers"][0], r"\([\w/]+, BOS, \d+% rostered\): 2 games this week \(Th/Sa\)")


if __name__ == "__main__":
    unittest.main()
