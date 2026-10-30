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
    def injuries(self, sport):
        return {}


def rp(pid, name, team, slot, injury="ACTIVE", eligible=(0, 12)):
    return {"id": pid, "name": name, "pro_team": team, "eligible": list(eligible), "pos": 1, "injury": injury,
            "proj": None, "owned": 1.0, "slot": slot}


AVG = {"1": {"0": 20, "17": 3, "13": 8, "14": 16, "11": 2}, "2": {"0": 10, "17": 1, "11": 1}, "3": {"0": 5, "17": 4},
       "4": {"0": 40, "17": 9}, "9": {"0": 30, "17": 5, "13": 10, "14": 20, "11": 3},
       "20": {"17": 2.5}, "21": {"17": 3}, "22": {"17": 9}}
SNAP = {"captured": "2026-10-28T14:00:00Z", "sport": "nba", "league_id": 190278, "season": 2027, "league_name": "Test",
        "scoring_period": 9, "matchup_period": 2, "scoring_type": "H2H_CATEGORY", "team": {"id": 5, "name": "Me"},
        "opponent": "Them", "slot_counts": {"0": 1, "12": 3, "13": 1},
        "roster": [rp(1, "Atlanta Star", 1, 0),
                   rp(2, "Boston Wing", 2, 12),
                   rp(3, "Atlanta Backup", 1, 12),          # loses the one slot on ATL days
                   rp(4, "Hurt Guy", 2, 13)]                 # IR: never counts
                  + [rp(i, f"P{i}", 3, 12) for i in range(5, 9)],
        "teams": [{"id": 9, "name": "Them", "roster": [rp(9, "Boston Big", 2, 0)]},
                  {"id": 8, "name": "Other", "roster": [rp(30, "Elsewhere", 1, 0)]}],
        "free_agents": [rp(20, "Atlanta Shooter", 1, None, eligible=[0, 5]), rp(21, "Boston Shooter", 2, None, eligible=[1])],
        "matchup": {
            "cats": [[0, False], [17, False], [19, False], [11, True]],
            "mine": {"0": 50, "17": 10, "19": 0.5, "13": 20, "14": 40, "11": 10},
            "opp": {"0": 100, "17": 10, "19": 0.45, "13": 18, "14": 40, "11": 9},
            "opp_id": 9, "avg": AVG,
            "fa_more": [{"id": 22, "name": "Injured Shooter", "pro_team": 1, "injury": "OUT", "eligible": [1]}]}}


def legacy(snap):
    """The block as saved before 2026-10-30: full player lists, each with its averages."""
    old = copy.deepcopy(snap)
    m, with_avg = old["matchup"], lambda ps: [{**p, "avg": AVG[str(p["id"])]} for p in ps]
    m["my_roster"], m["opp_roster"] = with_avg(old["roster"][:4]), with_avg(old["teams"][0]["roster"])
    m["fa"] = with_avg(old["free_agents"] + m.pop("fa_more"))
    del m["avg"], m["opp_id"]
    return old


def league(snap=SNAP):
    import shq.espn_fantasy as ef
    ef.load_snapshot = lambda sport, lid: snap
    return EspnLeague(Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 190278, "team_id": 5, "private": True})


class Categories(unittest.TestCase):
    def test_projection_and_advice(self, snap=SNAP):
        c = categories.build(league(snap))
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

    def test_snapshot_saved_before_the_trim(self):
        self.test_projection_and_advice(legacy(SNAP))

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
        bad["matchup"]["opp_id"] = 7                                 # opponent's roster missing from "teams"
        with self.assertRaises(ValueError):
            save_espn.validate(bad)


if __name__ == "__main__":
    unittest.main()
