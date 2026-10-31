"""nflverse NFL efficiency: play-by-play summary (filters, team codes, neutral-state early-down pass rate),
schedule lines (sign convention), opponent-adjusted ratings and the per-game stats dict, and the NFL
cutoffs for rule-4 traits on the breakdown panels."""
import csv
import gzip
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import nflverse as N  # noqa: E402
from pp import explain as E  # noqa: E402

try:
    import numpy  # noqa: F401
    HAVE_NP = True
except ImportError:  # CI installs no numpy
    HAVE_NP = False

PBP_COLS = ["game_id", "season_type", "week", "home_team", "away_team", "posteam", "defteam", "epa", "success",
            "pass", "rush", "wp", "half_seconds_remaining", "down", "cpoe", "pass_oe", "play_type", "yards_gained",
            "interception", "fumble_lost", "sack", "location", "desc"]


def play(**kw):
    base = {"game_id": "2026_01_SF_LA", "season_type": "REG", "week": "1", "home_team": "LA", "away_team": "SF",
            "posteam": "SF", "defteam": "LA", "epa": "0.5", "success": "1", "pass": "1", "rush": "0", "wp": "0.5",
            "half_seconds_remaining": "900", "down": "1", "cpoe": "", "pass_oe": "", "play_type": "pass",
            "yards_gained": "5", "interception": "0", "fumble_lost": "0", "sack": "0", "location": "Home", "desc": ""}
    base.update(kw)
    return [base[c] for c in PBP_COLS]


def write_gz(path, header, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


class Summary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = pathlib.Path(self.tmp.name) / "pbp.csv.gz"

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_and_filters(self):
        write_gz(self.p, PBP_COLS, [
            play(epa="0.5", success="1", yards_gained="25", cpoe="10", pass_oe="20"),        # explosive pass
            play(**{"pass": "0"}, rush="1", play_type="run", epa="-0.3", success="0", down="2", yards_gained="12"),
            play(epa="1.0", wp="0.97"),                                                      # not neutral
            play(epa="0.2", down="3"),                                                       # neutral, not early down
            play(play_type="qb_kneel", **{"pass": "0"}, rush="1", epa="-0.1"),                      # kneel: dropped
            play(epa=""),                                                                    # no EPA: dropped
            play(season_type="POST", epa="2.0"),                                             # playoffs: dropped
            play(posteam="LA", defteam="SF", epa="-0.2", success="0", interception="1"),
        ])
        rows = {r["team"]: r for r in N._summarize(self.p)}
        sf, la = rows["SF"], rows["LAR"]                     # nflverse LA -> ESPN LAR
        self.assertEqual(sf["opp"], "LAR")
        self.assertEqual((sf["n"], sf["p_n"], sf["r_n"]), (4, 3, 1))
        self.assertAlmostEqual(sf["epa"], 1.4)
        self.assertEqual(sf["sr"], 3)
        self.assertEqual(sf["expl"], 2)                      # 25-yd pass and 12-yd run
        self.assertEqual(sf["nn"], 3)                        # wp 0.97 play excluded
        self.assertEqual((sf["ed_n"], sf["ed_pass"]), (2, 1))
        self.assertEqual((sf["cp_n"], sf["cpoe"]), (1, 10.0))
        self.assertEqual(sf["loc"], -1)
        self.assertEqual(la["loc"], 1)
        self.assertEqual(la["to"], 1)


class Schedule(unittest.TestCase):
    def test_spread_sign_and_codes(self):
        cols = ["game_id", "season", "game_type", "week", "home_team", "away_team", "home_score", "away_score",
                "spread_line", "total_line", "roof", "location", "espn"]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "games.csv.gz"
            write_gz(p, cols, [["2026_01_NE_SEA", "2026", "REG", "1", "SEA", "NE", "13", "10", "3", "44.5", "outdoors", "Home", "1"],
                               ["2026_02_WAS_LA", "2026", "REG", "2", "LA", "WAS", "", "", "-2.5", "47", "dome", "Neutral", "2"],
                               ["2026_22_X_Y", "2026", "SB", "22", "KC", "PHI", "", "", "1", "50", "dome", "Neutral", "3"]])
            N.schedule.cache_clear()
            with mock.patch.object(N, "_fetch", return_value=p):
                S = N.schedule()
            N.schedule.cache_clear()
        self.assertEqual(len(S), 2)                          # playoff game skipped
        g = S["2026_01_NE_SEA"]
        self.assertEqual(g["home_spread"], -3.0)             # SEA favored by 3 -> our convention -3
        self.assertEqual(g["home_score"], 13.0)
        g2 = S["2026_02_WAS_LA"]
        self.assertEqual((g2["home"], g2["away"]), ("LAR", "WSH"))
        self.assertIsNone(g2["home_score"])
        self.assertTrue(g2["neutral"])


def fake_games():
    """Three teams; A's offense gains more EPA than anyone allows, C's defense allows the most."""
    rows = []
    for wk, (t, o, epa) in enumerate([("A", "B", 0.30), ("B", "A", -0.10), ("A", "C", 0.40), ("C", "A", 0.00),
                                       ("B", "C", 0.20), ("C", "B", 0.05)] * 2):
        rows.append({"game_id": f"g{wk // 2}", "week": 1 + wk // 2, "team": t, "opp": o, "loc": 0, "n": 60,
                     "epa": epa * 60, "sr": 27.0, "p_n": 35, "p_epa": epa * 35, "p_sr": 16, "r_n": 25, "r_epa": epa * 25,
                     "r_sr": 11, "nn": 50, "n_epa": 0, "n_sr": 0, "ed_n": 30, "ed_pass": 15, "cp_n": 30, "cpoe": 30.0,
                     "oe_n": 35, "pass_oe": 35.0, "expl": 6, "to": 1, "sacks": 2, "pts": 20})
    return rows


@unittest.skipUnless(HAVE_NP, "needs numpy")
class Ratings(unittest.TestCase):
    def setUp(self):
        N.ratings.cache_clear(); N.profiles.cache_clear()
        sched = {f"s{t}": {"season": 2026, "home": t} for t in "ABC"}
        self.p = [mock.patch.object(N, "team_games", lambda season, current=2026: fake_games() if season == 2026 else []),
                  mock.patch.object(N, "schedule", lambda current=2026: sched)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        N.ratings.cache_clear(); N.profiles.cache_clear()

    def test_offense_ranks_and_walk_forward(self):
        R = N.ratings(2026, 99, "epa", carry=0.0)
        self.assertGreater(R["tab"]["A"][0], R["tab"]["B"][0])
        self.assertGreater(R["tab"]["C"][1], R["tab"]["A"][1])   # C allows the most
        self.assertEqual(N.ratings(2026, 1, "epa", carry=0.0)["games"], 0)   # nothing before week 1

    def test_stats_dict_shape(self):
        d = N.stats_dict(2026, 99, "A", "B")
        self.assertEqual(set(d["teams"]), {"A", "B"})
        a = d["teams"]["A"]
        self.assertEqual(a["o_epa"][1], 1)
        for k in ("o_epa", "d_epa", "o_sr", "d_pass", "o_rush", "d_expl", "ed_pass", "proe", "cpoe", "to_pg"):
            self.assertEqual(len(a[k]), 2)
        self.assertAlmostEqual(a["ed_pass"][0], 0.5)
        self.assertEqual(a["games"], 4)

    def test_predict_uses_margin_map(self):
        mm = {"a": 2.0, "k_epa": 40.0, "k_sr": 0.0}
        self.assertGreater(N.predict(2026, 99, "A", "C", mm=mm), 2.0)
        self.assertAlmostEqual(N.predict(2026, 99, "A", "A", neutral=True, mm=mm), 0.0)


class NflTraits(unittest.TestCase):
    def test_32_team_cutoffs(self):
        u = lambda ro=None, rd=None: {"ro": ro, "rd": rd}
        T = {"pass": u(3, 30), "epa": u(15, 15)}
        good = {"pass": u(5, 10), "runrate": {"o": 0.45, "ro": 16}}
        weak_opp = {"pass": u(20, 10), "runrate": {"o": 0.45, "ro": 16}}
        kw = dict(facets=("epa", "sr", "pass", "rush", "expl"), top=E.NFL_TOP, exploit=E.NFL_EXPLOIT, bottom=E.NFL_BOTTOM)
        s, w = E.traits("BUF", "BAL", T, good, 32, **kw)
        self.assertEqual(s, ["pass game #3"])
        self.assertIn("exploitable", w[0])
        _, w = E.traits("BUF", "BAL", T, weak_opp, 32, **kw)
        self.assertIn("probably won't matter", w[0])

    def test_cell_format(self):
        T = {"cpoe": {"o": 4.67, "ro": 6}, "ed_pass": {"o": 0.48, "ro": 26}, "epa": {"o": 0.152, "d": 0.094, "ro": 1, "rd": 30}}
        self.assertIn("+4.7", E._ncell("cpoe", "o", T))
        self.assertIn("48%", E._ncell("ed_pass", "o", T))
        self.assertIn("+.15", E._ncell("epa", "o", T))
        self.assertIn("class='r'", E._ncell("epa", "d", T))
        self.assertEqual(E._ncell("sr", "o", T), "—")


class CfbDict(unittest.TestCase):
    def test_shape_matches_nfl_dict(self):
        P = {"_n": 138, "Georgia": {"epa": {"o": 0.21, "d": 0.01, "ro": 5, "rd": 12}, "sp": {"o": 20.1, "ro": 3}},
             "Florida": {}}
        d = E.cfb_stats_dict(P, "Georgia", "Florida", 9, 7.26)
        self.assertEqual(d["through_week"], 8)
        self.assertEqual(d["stats_home_margin"], 7.3)
        self.assertEqual(d["teams"]["Georgia"]["o_epa"], [0.21, 5])
        self.assertEqual(d["teams"]["Georgia"]["sp"], [20.1, 3])
        self.assertEqual(d["teams"]["Florida"]["d_line"], [None, None])


if __name__ == "__main__":
    unittest.main()
