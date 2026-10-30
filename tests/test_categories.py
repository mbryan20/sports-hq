"""NBA category matchup: projection with a daily lineup cap, close categories, what to chase, FA ideas."""
import copy
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import categories, save_espn
from shq.leagues import EspnLeague

NOW = dt.datetime(2026, 10, 28, 22, 0, tzinfo=dt.timezone.utc)      # Wed 5pm CT, scoring period 9
TIP = lambda day: NOW + dt.timedelta(days=day - 9, hours=1, minutes=30)


class Ctx:
    now, week = NOW, 8
    def pro_schedule(self, sport, season):
        return {1: {"abbrev": "ATL", "games": {d: [(TIP(d), 2, True)] for d in (9, 11, 13)}},
                2: {"abbrev": "BOS", "games": {d: [(TIP(d), 1, False)] for d in (10, 12)}},
                3: {"abbrev": "CHI", "games": {}}}
    week_start = None
    def injuries(self, sport):
        return {}
    def injury_report(self, sport):
        return {}


def rp(pid, name, team, slot, avg, injury="ACTIVE", **extra):
    return {"id": pid, "name": name, "pro_team": team, "slot": slot, "injury": injury, "avg": avg, **extra}


def roster_entry(pid, slot):
    return {"id": pid, "name": f"P{pid}", "pro_team": 3, "eligible": [0, 12], "pos": 1, "injury": "ACTIVE",
            "proj": None, "owned": 1.0, "slot": slot}


SNAP = {"captured": "2026-10-28T14:00:00Z", "sport": "nba", "league_id": 190278, "season": 2027, "league_name": "Test",
        "scoring_period": 9, "matchup_period": 2, "scoring_type": "H2H_CATEGORY", "team": {"id": 5, "name": "Me"},
        "opponent": "Them", "slot_counts": {"0": 1, "12": 3, "13": 1},
        "roster": [roster_entry(i, 0 if i == 1 else 12) for i in range(1, 9)], "free_agents": [],
        "matchup": {
            "cats": [[0, False], [17, False], [19, False], [11, True]],
            "mine": {"0": 50, "17": 10, "19": 0.5, "13": 20, "14": 40, "11": 10},
            "opp": {"0": 100, "17": 10, "19": 0.45, "13": 18, "14": 40, "11": 9},
            "my_roster": [
                rp(1, "Atlanta Star", 1, 0, {"0": 20, "17": 3, "13": 8, "14": 16, "11": 2}),
                rp(2, "Boston Wing", 2, 12, {"0": 10, "17": 1, "11": 1}),
                rp(3, "Atlanta Backup", 1, 12, {"0": 5, "17": 4}),          # loses the one slot on ATL days
                rp(4, "Hurt Guy", 2, 13, {"0": 40, "17": 9})],              # IR: never counts
            "opp_roster": [rp(9, "Boston Big", 2, 0, {"0": 30, "17": 5, "13": 10, "14": 20, "11": 3})],
            "fa": [rp(20, "Atlanta Shooter", 1, None, {"17": 2.5}, eligible=[0, 5]),
                   rp(21, "Boston Shooter", 2, None, {"17": 3}, eligible=[1]),
                   rp(22, "Injured Shooter", 1, None, {"17": 9}, injury="OUT", eligible=[1])]}}


def league(snap=SNAP):
    import shq.espn_fantasy as ef
    ef.load_snapshot = lambda sport, lid: snap
    return EspnLeague(Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 190278, "team_id": 5, "private": True})


class Categories(unittest.TestCase):
    def test_projection_and_advice(self):
        c = categories.build(league())
        rows = {r["cat"]: r for r in c["rows"]}
        # one starting slot: ATL days go to the Star (3 games), BOS days to the Wing (2); the opponent's Big plays 2
        self.assertEqual(c["games_left"], [5, 2])
        self.assertEqual(rows["PTS"], {"cat": "PTS", "me": "50", "opp": "100", "now": "L", "outlook": "lose"})  # 130 vs 160
        self.assertEqual(rows["3PM"]["outlook"], "close")                                                      # 21 vs 20
        self.assertEqual((rows["FG%"]["me"], rows["FG%"]["outlook"]), (".500", "win"))                         # .500 vs .475
        self.assertEqual((rows["TO"]["now"], rows["TO"]["outlook"]), ("L", "lose"))                            # fewer wins
        self.assertEqual((c["now"], c["proj"], c["close"]), ("1-2-1", "1-2", 1))
        self.assertEqual(c["chase"], ["3PM is close. Keep in the lineup: Atlanta Star (3 games, 3.0/g) and Boston Wing (2 games, 1.0/g)."])
        self.assertEqual(c["adds"], ["For 3PM: Atlanta Shooter (PG, ATL), 3 games left, 2.5/g"])

    def test_last_weeks_snapshot_is_ignored(self):
        old = copy.deepcopy(SNAP)
        old["captured"] = "2026-10-26T01:00:00Z"                     # Sunday night CT: last week's totals
        self.assertIsNone(categories.build(league(old)))

    def test_no_matchup_block(self):
        snap = {k: v for k, v in SNAP.items() if k != "matchup"}
        self.assertIsNone(categories.build(league(snap)))

    def test_snapshot_validation(self):
        self.assertEqual(save_espn.validate(SNAP)["name"], "Ball is Life")
        bad = copy.deepcopy(SNAP)
        bad["matchup"]["opp_roster"] = []
        with self.assertRaises(ValueError):
            save_espn.validate(bad)


if __name__ == "__main__":
    unittest.main()
