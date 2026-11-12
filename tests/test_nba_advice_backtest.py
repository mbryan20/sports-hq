"""NBA swaps and streamers backtest (shq/nba_advice_backtest.py) and its model-health checks: the morning's advice
rebuilt from a faked git history, judged on fake ESPN game logs. No network."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import health
from shq import nba_advice_backtest as ab

CT = dt.timezone(dt.timedelta(hours=-6))          # CST, Nov 2026
T = lambda d, h, m=0: int(dt.datetime(2026, 11, d, h, m, tzinfo=CT).timestamp())
DATES = {p: dt.date(2026, 11, 5) + dt.timedelta(days=p - 17) for p in range(16, 23)}     # 17 = Thu Nov 5 ... 20 = Sun Nov 8

SWAP = ("Drop Drop Guy (2 games this week, value -1.0/g), add Add Guy (PG, ATL, 2 games this week, value +2.0/g, 5% "
        "rostered): +6.0 this week over keeping Drop Guy (helps PTS). Dynasty: Drop Guy is 27.")
STREAMERS = ["Add Guy (PG, ATL, 5% rostered): 2 games this week (Th/Sa), +6.0 this week, helps PTS",
             "Next Guy (SG, BOS, 3% rostered): 2 games this week (Fr/Su), +4.0 this week",
             "Third Guy (C, CHI, 1% rostered): 1 game this week (Su), +1.5 this week"]


def player(pid, name, z, g, own=None, team="ATL"):
    return {"id": pid, "name": name, "team": team, "own": own, "z": z, "v": sum(z), "g": g, "pct": 5, "age": None, "out": False}


BLOCK = {"cats": ["PTS", "FG%"], "rev": [False, False], "repl": -1.0,
         "scale": {"PTS": [10, 5, None], "FG%": [0, 1, 0.5]},
         "players": [player("1", "Drop Guy", [-1, 0], [2, 3], own="me"), player("2", "Add Guy", [2, 0], [2, 3]),
                     player("3", "Next Guy", [1, 0], [2, 3], team="BOS"), player("4", "Third Guy", [0.5, 0], [1, 2], team="CHI")]}


def lineups(adds, streamers=STREAMERS, span="Thu Nov 5–Sun Nov 8"):
    adv = {"adds": adds, "cats": {"rows": [], "games_left": [0, 0]},
           "games": {"now": {"span": span}, "next": {"span": "Mon Nov 9–Sun Nov 15"}, "streamers": streamers}}
    return {"leagues": {"3-Ball BB": {"advice": adv, "bench": [{"slot": "IR", "name": "Hurt Guy"}]}}}


FILES = {
    ("p1", ab.PLAYERS): {"leagues": {"3-Ball BB": BLOCK}},
    ("early", ab.LINEUPS): lineups(["Drop Drop Guy (2 games this week, value -1.0/g), add Third Guy (C, CHI, 1 game this "
                                    "week, value +0.5/g, 1% rostered): +3.0 this week over keeping Drop Guy."]),
    ("thu", ab.LINEUPS): lineups([SWAP]),
    ("thu2", ab.LINEUPS): lineups([]),
    ("fri", ab.LINEUPS): lineups([SWAP, "Drop Gone Guy (1 game this week, value -3.0/g), add Nobody (PG, ATL, 1 game this "
                                        "week, value +1.0/g, 1% rostered): +4.0 this week over keeping Gone Guy."],
                                 span="Fri Nov 6–Sun Nov 8"),
}
LINEUP_VERSIONS = [(T(5, 7, 30), "early"), (T(5, 8, 5), "thu"), (T(5, 9, 0), "thu2"), (T(6, 8, 2), "fri")]
PLAYER_VERSIONS = [(T(5, 0, 4), "p1")]
load = lambda sha, path: FILES[(sha, path)]


def game(period, pts, fgm=0, fga=0, team=1):
    return [period, team, {"40": 30, "0": pts, "13": fgm, "14": fga}]


# Add Guy: 2 games in the window worth 3 each (PTS z 2, FG% made-above-rate 0), one before it and one after it that
# don't count. Drop Guy: 1 game worth 1. Next Guy: 1 game worth 0. Third Guy didn't play.
POOL = {"1": {"name": "Drop Guy", "games": [game(18, 10)]},
        "2": {"name": "Add Guy", "games": [game(16, 50), game(17, 20, 5, 10), game(19, 20, 5, 10), game(21, 50)]},
        "3": {"name": "Next Guy", "games": [game(18, 5)]},
        "4": {"name": "Third Guy", "games": []}}


def hist():
    return ab.history(LINEUP_VERSIONS, PLAYER_VERSIONS, load)


class Parse(unittest.TestCase):
    def test_swap_lines(self):
        s = ab.parse_swap(SWAP)
        self.assertEqual((s["drop"], s["add"], s["dead"], s["est"], s["when"], s["add_games"]),
                         ("Drop Guy", "Add Guy", False, 6.0, "this week", 2))
        dead = ab.parse_swap("Drop Kevin Porter Jr. (no NBA team, a dead roster spot), add Alex Caruso (PG/SG, OKC, 2 games "
                             "this week, value -2.1/g, 20% rostered): +1.2 this week (helps FG%).")
        self.assertEqual((dead["drop"], dead["add"], dead["dead"], dead["est"]), ("Kevin Porter Jr.", "Alex Caruso", True, 1.2))
        # a day-to-day drop and add (nested parentheses) behind the "move him out of IR first" head
        ir = ab.parse_swap("First move Big Man out of IR (Fix now): ESPN blocks every add and drop until he is on your bench; "
                           "your roster is full, so that takes a drop too: Bench Guy (value -4.0/g); then drop Isaiah Stewart "
                           "(1 game this week, day-to-day (ESPN: questionable), next game counted at 50%, value -3.0/g), add "
                           "Mo Bamba (C, UTAH, 1 game next week, day-to-day (ESPN: probable), value -2.8/g, 3% rostered): "
                           "+4.1 next week over keeping Isaiah Stewart (helps BLK).")
        self.assertEqual((ir["drop"], ir["add"], ir["est"], ir["when"], ir["add_games"]),
                         ("Isaiah Stewart", "Mo Bamba", 4.1, "next week", 1))
        self.assertIsNone(ab.parse_swap("Kevin Porter Jr. has no NBA team: a dead roster spot. Drop him for any free agent below."))
        self.assertIsNone(ab.parse_swap("Mitchell Robinson (C, BOS): 2 games left this week, 16.1% owned"))   # pre-Nov 6 list

    def test_streamer_lines_and_spans(self):
        s = ab.parse_streamer("Cam Spencer (PG/SG, MEM, 9% rostered, day-to-day (ESPN: probable)): 2 games this week "
                              "(Fr/Sa, back-to-back), -0.2 this week, helps FT%")
        self.assertEqual((s["name"], s["games"], s["est"], s["when"]), ("Cam Spencer", 2, -0.2, "this week"))
        self.assertEqual(ab.span_dates("Mon Dec 28–Sun Jan 3", dt.date(2026, 12, 28)), (dt.date(2026, 12, 28), dt.date(2027, 1, 3)))
        w = ab.windows({}, dt.date(2026, 11, 5))           # no games grid: this week runs to Sunday
        self.assertEqual(w, {"this week": (dt.date(2026, 11, 5), dt.date(2026, 11, 8)),
                             "next week": (dt.date(2026, 11, 9), dt.date(2026, 11, 15))})


class History(unittest.TestCase):
    def test_first_commit_from_8am_ct_with_ids(self):
        h = hist()
        self.assertEqual([m["day"] for m in h], ["2026-11-05", "2026-11-06"])     # 7:30 and the second Thu commit ignored
        thu, fri = h
        (s,) = thu["swaps"]
        self.assertEqual((s["drop_id"], s["add_id"], s["est"]), ("1", "2", 6.0))
        self.assertEqual([x["id"] for x in thu["streamers"]], ["2", "3", "4"])
        self.assertEqual(thu["ir"], {"Hurt Guy"})
        self.assertTrue(thu["dynasty"])                                           # from shq/config.py
        self.assertEqual(fri["windows"]["this week"], (dt.date(2026, 11, 6), dt.date(2026, 11, 8)))
        self.assertEqual(fri["unmatched"], ["Nobody"])
        self.assertEqual(ab.history(LINEUP_VERSIONS, PLAYER_VERSIONS, load, skip=[("3-Ball BB", "2026-11-05")])[0]["day"],
                         "2026-11-06")


class Score(unittest.TestCase):
    def test_swaps_and_streamers_judged_on_the_rest_of_the_week(self):
        res = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 9))
        (s,) = res["swaps"]                                                       # Friday's repeat counts once
        self.assertEqual(s["day"], "2026-11-05")
        self.assertEqual((s["add_stats"]["actual"], s["add_stats"]["played"], s["drop_stats"]["actual"]), (6.0, 2, 1.0))
        self.assertEqual((s["gain"], s["gain_pg"], s["hit"], s["err"]), (5.0, 2.5, True, -1.0))
        self.assertEqual((s["add_stats"]["exp_games"], s["add_stats"]["exp_pg"]), (2, 3.0))
        p1, p2 = res["streamers"]
        self.assertEqual((p1["pick"], p1["next"], p1["est_edge"], p1["edge"], p1["edge_pg"], p1["hit"]),
                         ("Add Guy", "Next Guy", 2.0, 6.0, 3.0, True))
        self.assertEqual((p2["edge"], p2["hit"]), (0.0, False))
        self.assertEqual(res["done"], ["3-Ball BB|2026-11-05", "3-Ball BB|2026-11-06"])
        sm = ab.summary(res)
        self.assertEqual((sm["swaps"]["n"], sm["swaps"]["gain"], sm["swaps"]["hit_rate"], sm["swaps"]["est_err"],
                          sm["swaps"]["est_bias"]), (1, 2.5, 1.0, 1.0, -1.0))
        self.assertEqual((sm["streamers"]["n"], sm["streamers"]["edge"], sm["streamers"]["hit_rate"]), (2, 1.5, 0.5))
        self.assertEqual(list(sm["weeks"]), ["2026-11-08"])
        self.assertEqual(sm["unmatched"], ["Nobody"])

    def test_unfinished_week_waits_or_is_provisional(self):
        res = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 7))
        self.assertEqual((res["swaps"], res["streamers"], res["done"]), ([], [], []))
        self.assertEqual(res["pending"], 6)                                        # 1 swap + 2 pairs, two mornings
        res = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 7), partial=True)      # games of Nov 5-6 only
        (s,) = res["partial"]["swaps"]
        self.assertEqual((s["gain"], s["partial"]), (2.0, True))
        self.assertEqual(res["swaps"], [])

    def test_stored_items_carry_over_and_rolled_off_logs_are_not_scored(self):
        first = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 9))
        again = ab.run(hist(), {}, DATES, dt.date(2026, 11, 9), previous=first)    # logs gone: stored items stand
        self.assertEqual((len(again["swaps"]), again["swaps"][0]["gain"], len(again["streamers"])), (1, 5.0, 2))
        stale = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 9), previous={**first, "v": ab.V + 1, "swaps": [{"v": 0}]})
        self.assertEqual(len(stale["swaps"]), 1)                                   # an old version is re-scored
        rolled = {pid: {**p, "games": [game(d, 10) for d in range(30, 30 + ab.LOG_KEEP)]} for pid, p in POOL.items()}
        self.assertEqual(ab.actual(rolled, "2", {17, 18}, BLOCK, {"PTS": 1, "FG%": 1}), (None, 0))
        lost = ab.run(hist(), {**rolled, "9": {"games": [game(40, 1)]}}, DATES, dt.date(2026, 11, 9))
        self.assertEqual((lost["swaps"], lost["lost"]), ([], 6))

    def test_compare_two_value_sources_on_the_same_history(self):
        flip = lambda p, m: {"2": [0, 0], "3": [3, 0]}.get(p["id"], p["z"])     # rates Next Guy above Add Guy
        out = ab.compare_sources(hist(), POOL, DATES, dt.date(2026, 11, 9), {"site": ab.site_source, "flip": flip})
        self.assertEqual((out["match"], out["match_swaps"]), (1.0, 1.0))          # the replay picks what the site showed
        self.assertEqual(out["overall"]["site"], {"stream": 1.0, "swap": 2.5, "n_stream": 3, "n_swap": 1})
        self.assertEqual(out["overall"]["flip"]["swap"], -0.5)                     # Next Guy (0) for Drop Guy (1), per 2 games
        self.assertEqual(out["diff"]["2026-11-08"]["flip"], {"stream": 0.0, "swap": -3.0})


class HealthChecks(unittest.TestCase):
    def test_info_until_enough_then_a_baseline(self):
        res = ab.run(hist(), POOL, DATES, dt.date(2026, 11, 9))
        s = ab.summary(res)
        base = {}
        j = lambda cid, v, n: health.judge(cid, v, n, base, "2026-11-12")
        rows = {r["id"]: r for r in health.swaps_checks(s, j)}
        self.assertEqual({r["status"] for r in rows.values()}, {"info"})
        self.assertEqual(base, {})                                                  # too few: no baseline
        self.assertEqual((rows["swap.gain"]["value"], rows["swap.hit"]["value"], rows["swap.est_err"]["value"],
                          rows["stream.edge"]["value"]), (2.5, 1.0, 1.0, 1.5))
        big = {"swaps": {**s["swaps"], "n": 25}, "streamers": {**s["streamers"], "n": 25}}
        rows = {r["id"]: r for r in health.swaps_checks(big, j)}
        self.assertEqual(rows["swap.gain"]["status"], "ok")
        self.assertEqual(base["swap.gain"]["n"], 25)
        self.assertEqual(rows["swap.est_bias"]["status"], "info")                  # shown, never judged
        worse = {"swaps": {**big["swaps"], "gain": -0.2, "hit_rate": 0.4}, "streamers": big["streamers"]}
        rows = {r["id"]: r for r in health.swaps_checks(worse, j)}
        self.assertEqual((rows["swap.gain"]["status"], rows["swap.hit"]["status"]), ("weak", "weak"))  # no better than keeping him
        notes = health.swaps_notes(s)
        self.assertIn("1 swaps judged: the add out-produced the drop in 1 (100%)", notes[0])
        self.assertTrue(any("info only" in n for n in notes))

    def test_section_runs_on_stored_items(self):
        first = ab.health(None, hist=hist(), pool=POOL, dates=DATES, today=dt.date(2026, 11, 9))
        self.assertEqual(first["summary"]["swaps"]["n"], 1)
        self.assertNotIn("partial", first)
        again = health.swaps_health(first, hist=[], pool={}, dates=DATES, today=dt.date(2026, 11, 10))
        self.assertEqual((again["summary"]["swaps"]["n"], again["summary"]["streamers"]["n"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
