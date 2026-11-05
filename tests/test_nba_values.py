"""NBA category values (shq/nba_values.py): source per player, z-scores in the league's own categories (ratio cats
weighted by attempts, reversed cats negative), rank, this-week value, owners, and the players.json writer."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import advice, nba_values, radar
from shq.leagues import EspnLeague

NOW = dt.datetime(2026, 10, 28, 15, 0, tzinfo=dt.timezone.utc)      # Wed 10am CT, scoring period 9
TIP = lambda day: NOW + dt.timedelta(days=day - 9, hours=8)


def pl(name, team, season, gp=8, proj=None, injury="ACTIVE", owned=10.0, eligible=(0, 1, 5, 11, 12)):
    return {"name": name, "team": team, "pos": 1, "eligible": list(eligible), "injury": injury, "owned": owned, "change": 0,
            "season": season, "gp": gp, "proj": proj or {}, "games": []}


def line(pts, ast, fgm, fga, to=2, mins=30):
    return {"0": pts, "3": ast, "13": fgm, "14": fga, "11": to, "40": mins}


POOL = {
    "1": pl("Star", 1, line(30, 8, 11, 20)),
    "2": pl("Volume Shooter", 1, line(20, 3, 10, 16)),           # 62.5% on 16 attempts
    "3": pl("Low Volume", 2, line(8, 2, 5, 8)),                  # 62.5% on 8 attempts
    "4": pl("Rookie", 2, line(4, 1, 1, 5), gp=3, proj=line(16, 5, 6, 13)),   # 3 games: ESPN projection
    "5": pl("Hurt Vet", 2, line(18, 4, 7, 15), injury="OUT"),
    "6": pl("Bench Guy", 1, line(6, 1, 2, 6)),
    "7": pl("Turnover Machine", 2, line(20, 3, 8, 17, to=6)),
}
REPORT = {"5": {"status": "Out", "name": "Hurt Vet", "team": "BOS", "date": NOW, "note": "Vet (knee) is out.",
                "url": "https://www.espn.com/nba/player/_/id/5"}}


class Ctx:
    now, week, week_start = NOW, 8, None
    def pro_schedule(self, sport, season):
        return {1: {"abbrev": "ATL", "games": {d: [(TIP(d), 2, True)] for d in (9, 11, 12, 13, 15, 16)}},
                2: {"abbrev": "BOS", "games": {d: [(TIP(d), 1, False)] for d in (10, 12, 17)}}}
    def injury_report(self, sport):
        return REPORT


def rp(pid, name, team, slot):
    return {"id": pid, "name": name, "pro_team": team, "eligible": [0, 12], "pos": 1, "injury": "ACTIVE", "proj": None,
            "owned": 1.0, "slot": slot}


CATS = [[0, False], [3, False], [19, False], [11, True]]   # PTS, AST, FG%, TO (reversed)
SNAP = {"captured": "2026-10-28T14:00:00Z", "sport": "nba", "league_id": 190278, "season": 2027, "league_name": "Test",
        "scoring_period": 9, "matchup_period": 2, "scoring_type": "H2H_CATEGORY", "team": {"id": 5, "name": "Me"},
        "opponent": "Them", "slot_counts": {"0": 1, "12": 1, "13": 1}, "size": 2,
        "roster": [rp(2, "Volume Shooter", 1, 0), rp(6, "Bench Guy", 1, 12)],
        "teams": [{"id": 9, "name": "Them", "roster": [rp(1, "Star", 1, 0), rp(5, "Hurt Vet", 2, 12)]}],
        "free_agents": [], "matchup": {"cats": CATS, "mine": {}, "opp": {}, "opp_id": 9, "avg": {}, "fa_more": []}}


def league():
    import shq.espn_fantasy as ef
    ef.load_snapshot = lambda sport, lid: SNAP
    return EspnLeague(Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 190278, "team_id": 5, "private": True})


class Values(unittest.TestCase):
    def setUp(self):
        self.saved = radar.fetch_pool, radar.track_ownership
        radar.fetch_pool = lambda *a, **k: POOL
        radar.track_ownership = lambda pool, now: {}

    def tearDown(self):
        radar.fetch_pool, radar.track_ownership = self.saved

    def test_source_is_season_from_five_games_else_espn_projection(self):
        self.assertEqual(nba_values.per_game(POOL["1"])[1:], ("season", 8))
        st, src, gp = nba_values.per_game(POOL["4"])
        self.assertEqual((src, gp, st["0"]), ("proj", 3, 16))
        self.assertEqual(nba_values.per_game({**POOL["4"], "proj": {}})[1], "season")   # no projection: what he has

    def test_ratio_cats_count_volume_and_reversed_cats_count_negative(self):
        cats = [(19, False), (11, True)]
        lines = {k: nba_values.per_game(p)[0] for k, p in POOL.items()}
        vals, sc = nba_values.value_pool(lines, cats, 4)
        fg = lambda k: vals[k][1][0]
        self.assertGreater(fg("2"), fg("3"))            # same 62.5%, twice the attempts
        self.assertGreater(fg("3"), 0)
        self.assertLess(vals["7"][1][1], vals["1"][1][1])   # 6 turnovers a game is worse than 2

    def test_build_ranks_owners_sources_and_this_week(self):
        lg = league()
        b = nba_values.build(lg)
        self.assertEqual(b["cats"], ["PTS", "AST", "FG%", "TO"])
        self.assertEqual(b["n"], 4)                                  # 2 teams x 2 roster spots (IR doesn't count)
        by = nba_values.by_id(b)
        self.assertEqual(b["players"][0]["name"], "Star")
        self.assertEqual([p["rk"] for p in b["players"]], list(range(1, len(POOL) + 1)))
        self.assertEqual((by["2"]["own"], by["1"]["own"], by["3"]["own"]), ("me", "Them", None))
        self.assertEqual(by["4"]["src"], "proj")
        self.assertEqual(by["1"]["g"], [4, 2])                       # ATL: 9, 11, 12, 13 this week; 15, 16 next
        self.assertEqual(by["1"]["b2b"], 3)                          # 11-12, 12-13, 15-16
        self.assertAlmostEqual(by["1"]["wk"], round((by["1"]["v"] - b["repl"]) * 4, 1), places=1)
        self.assertEqual((by["5"]["wk"], by["5"]["out"], by["5"]["inj"]), (0.0, True, "Out"))
        self.assertEqual(by["2"]["st"][:2], [20, 3])
        self.assertEqual(by["2"]["st"][2], 0.625)
        # what the Players page (docs/players/index.html) reads
        self.assertTrue({"id", "name", "team", "pos", "own", "src", "gp", "min", "v", "rk", "wk", "g", "b2b", "z", "st", "inj",
                         "out", "dmin", "pct"} <= set(by["1"]))
        self.assertEqual(len(by["1"]["z"]), len(b["cats"]))
        self.assertEqual(by["1"]["pos"], "PG/SG")

    def test_roster_rows_get_value_labels(self):
        lg = league()
        advice.player_values(lg)
        vs = next(p for p in lg.starters if p["name"] == "Volume Shooter")
        self.assertEqual(set(vs["val"]), {"v", "rk", "wk", "src"})
        self.assertEqual(vs["val"]["src"], "8 g")
        from shq.leagues import view
        row = next(r for r in view(lg)["starters"] if r["name"] == "Volume Shooter")
        self.assertEqual(row["val"]["rk"], vs["val"]["rk"])

    def test_save_keeps_a_missing_league_and_writes_a_player_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "players.json"
            nba_values.save(path, {"A": {"cats": ["PTS"], "players": [{"id": "1"}, {"id": "2"}]}}, "t1")
            nba_values.save(path, {"A": None, "B": {"cats": ["AST"], "players": [{"id": "3"}]}}, "t2")
            d = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(d["updated"], "t2")
            self.assertEqual([p["id"] for p in d["leagues"]["A"]["players"]], ["1", "2"])
            self.assertEqual(d["leagues"]["B"]["cats"], ["AST"])
            self.assertIn('\n{"id":"2"}\n', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
