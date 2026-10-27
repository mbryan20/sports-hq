"""ESPN leagues from a compact snapshot: slot names, games, and an NBA injury swap push."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import notify, run
from shq.leagues import EspnLeague

NOW = dt.datetime(2026, 10, 28, 22, 0, tzinfo=dt.timezone.utc)      # 5pm CT, inside the 2h window
TIP = dt.datetime(2026, 10, 28, 23, 30, tzinfo=dt.timezone.utc)      # 6:30pm CT


class Ctx:
    now, week = NOW, 8
    def pro_schedule(self, sport, season):
        return {1: {"abbrev": "ATL", "games": {9: [(TIP, 2, True)]}},
                2: {"abbrev": "BOS", "games": {9: [(TIP, 1, False)]}},
                3: {"abbrev": "CHI", "games": {}}}
    def injuries(self, sport):
        return {}


def pl(pid, name, team, slot, elig, injury="ACTIVE"):
    return {"id": pid, "name": name, "pro_team": team, "eligible": elig, "pos": 1, "injury": injury,
            "proj": None, "owned": 50.0, "slot": slot}


SNAP = {"captured": "2026-10-28T14:00:00Z", "sport": "nba", "league_id": 1, "season": 2027, "league_name": "Test",
        "scoring_period": 9, "matchup_period": 2, "scoring_type": "H2H_CATEGORY", "team": {"id": 5, "name": "Me"},
        "opponent": "Them", "roster": [
            pl(10, "Out Guard", 1, 0, [0, 5, 11, 12, 13], "OUT"),
            pl(11, "Bench Guard", 2, 12, [0, 5, 11, 12, 13]),
            pl(12, "Idle Guard", 3, 12, [0, 5, 11, 12, 13]),
            pl(13, "Bench Center", 2, 12, [4, 11, 12, 13])],
        "free_agents": []}


class EspnSnapshot(unittest.TestCase):
    def setUp(self):
        import shq.espn_fantasy as ef
        ef.load_snapshot = lambda sport, lid: SNAP
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)

    def test_view_and_swap(self):
        lg = EspnLeague(Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 1, "team_id": 5, "private": True})
        self.assertEqual([p["slot"] for p in lg.starters], ["PG"])
        self.assertEqual(len(lg.bench), 3)
        idle = next(p for p in lg.bench if p["name"] == "Idle Guard")
        self.assertTrue(idle["bye"])                       # no game today
        self.assertEqual(run.injury_watch(lg, NOW), ["suggested Out Guard -> Bench Guard"])
        self.assertIn("start Bench Guard", notify.sent[-1]["message"])


if __name__ == "__main__":
    unittest.main()
