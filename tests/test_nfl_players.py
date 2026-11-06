"""F1: football Players page rows (shq/nfl_players.py): owners, rest-of-season and this-week ranks by position, free agent
cut, K/DEF without a ROS number, and the partial flag where other rosters can't be read."""
import unittest

from shq import nfl_players, values


def pl(pid, name, pos, proj, ppg, val=1000, team="DAL", bye=False, status=None):
    return {"id": pid, "key": None, "name": name, "positions": [pos], "team": team, "proj": proj, "_ppg": ppg, "_val": val,
            "bye": bye, "opp": None if bye else "vs NYG", "kickoff": None, "status": status}


class League:
    sport, platform, week = "nfl", "sleeper", 9
    fc_settings = {"dynasty": True}

    def __init__(self, mine, others, fas):
        self.starters, self.bench, self.others, self.free_agents = mine, [], others, fas


def fake_annotate(league):
    for p in values.players_of(league):
        p["ppg"], p["val"], p["wk"] = p["_ppg"], p["_val"], [(9, p["proj"]), (10, None)]
    return True


class FootballPlayers(unittest.TestCase):
    def setUp(self):
        self.saved = values.annotate
        values.annotate = fake_annotate

    def tearDown(self):
        values.annotate = self.saved

    def league(self, others=True):
        mine = [pl("1", "My RB", "RB", 12.0, 14.0), pl("2", "My QB", "QB", 20.0, 18.0), pl("3", "My K", "K", 8.0, 0.0)]
        oth = [{"name": "Rival", "players": [pl("4", "Their RB", "RB", 15.0, 13.0), pl("5", "Their WR", "WR", 9.0, 11.0)]}]
        fas = [pl(str(10 + i), f"FA RB {i}", "RB", 5.0 - i * 0.01, 6.0 - i * 0.01) for i in range(nfl_players.FA_KEEP + 5)]
        fas.append(pl("99", "Nobody", "WR", 0.0, 0.0))
        return League(mine, oth if others else [], fas)

    def test_owners_ranks_and_sources(self):
        b = nfl_players.build(self.league())
        by = {p["name"]: p for p in b["players"]}
        self.assertEqual((by["My RB"]["own"], by["Their RB"]["own"], by["FA RB 0"]["own"]), ("me", "Rival", None))
        self.assertEqual((by["My RB"]["ros_rk"], by["Their RB"]["ros_rk"]), (1, 2))     # 14.0 vs 13.0 per game ROS
        self.assertEqual((by["My RB"]["proj_rk"], by["Their RB"]["proj_rk"]), (2, 1))   # 12.0 vs 15.0 this week
        self.assertEqual(by["My RB"]["next"], [12.0, None])                            # next weeks, None = bye
        self.assertEqual(by["My RB"]["fc"], 1000)
        self.assertIsNone(by["My K"]["ros"])                                           # kickers rank on this week only
        self.assertEqual(by["My K"]["proj_rk"], 1)
        self.assertIn("FantasyCalc dynasty", b["basis"])
        self.assertFalse(b["partial"])

    def test_free_agents_cut_and_zero_projections_dropped(self):
        b = nfl_players.build(self.league())
        fas = [p for p in b["players"] if not p["own"]]
        self.assertEqual(len(fas), nfl_players.FA_KEEP)
        self.assertNotIn("Nobody", [p["name"] for p in fas])
        self.assertNotIn(f"FA RB {nfl_players.FA_KEEP + 4}", [p["name"] for p in fas])   # the weakest are cut

    def test_partial_when_other_rosters_are_unknown(self):
        b = nfl_players.build(self.league(others=False))
        self.assertTrue(b["partial"])
        self.assertIn("Yahoo API pending", b["basis"])

    def test_not_for_basketball(self):
        lg = self.league()
        lg.sport = "nba"
        self.assertIsNone(nfl_players.build(lg))


if __name__ == "__main__":
    unittest.main()
