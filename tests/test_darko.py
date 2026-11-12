"""DARKO's next-game projections (shq/darko.py): the page-data decoder, one read a day with a cache, our derived minutes
factors (matched by name), the daily snapshot and its backfill. Fixtures only, no network."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import darko

# the Projections page's data: a list of player objects (devalue: indexes into one flat array)
LIST_PAGE = {"type": "data", "nodes": [None, {"type": "data", "data": [
    {"players": 1, "asOf": 2, "history": -1},
    [3, 6, 10],
    "2026-11-10",
    {"player_name": 4, "team_name": 9, "x_minutes": 5, "date": 2},
    "Nikola Jokić", 34.85,
    {"player_name": 7, "team_name": 9, "x_minutes": 8, "date": 11},
    "Ernest Udeh, Jr.", 1.6, "Denver Nuggets",
    {"player_name": 12, "x_minutes": 13},
    ["Date", "2026-11-11T00:00:00Z"],
    "No Minutes Guy", "n/a"]}]}
# the leaderboard's form: {"keys", "values"} columns
COLUMN_PAGE = {"type": "data", "nodes": [None, {"type": "data", "data": [
    {"players": 1, "asOf": -1, "ratingsThrough": 8},
    {"keys": 2, "values": 5}, [3, 4], "player_name", "x_minutes", [6, 7], [9, 10], [11, 12], "2026-11-09",
    "Star", "Bench Guy", 30.0, 12.0]}]}


class Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise darko.requests.HTTPError(f"{self.status}")

    def json(self):
        return self.payload


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(darko, "CACHE_DIR", root / "cache"), mock.patch.object(darko, "SNAP", root / "nba_darko.json")]
        for p in self.patches:
            p.start()
        self.calls = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def get(self, payload, status=200):
        def fn(url, params=None, headers=None, timeout=None):
            self.calls.append((url, params, headers))
            if isinstance(payload, Exception):
                raise payload
            return Resp(payload, status)
        return fn


class Decode(unittest.TestCase):
    def test_list_and_column_forms(self):
        rows, asof = darko.decode(LIST_PAGE)
        self.assertEqual(asof, "2026-11-10")
        self.assertEqual([(r["name"], r["min"]) for r in rows], [("Nikola Jokić", 34.85), ("Ernest Udeh, Jr.", 1.6)])
        self.assertEqual(rows[0]["team"], "Denver Nuggets")
        self.assertIsNone(rows[1]["date"])                       # a typed value (Date) is not read
        rows, asof = darko.decode(COLUMN_PAGE)
        self.assertEqual(([(r["name"], r["min"]) for r in rows], asof), ([("Star", 30.0), ("Bench Guy", 12.0)], "2026-11-09"))

    def test_anything_else_is_empty(self):
        for bad in (None, {}, {"nodes": [None]}, {"nodes": [{"type": "data", "data": []}]}, {"nodes": [{"type": "data", "data": [5]}]}):
            self.assertEqual(darko.decode(bad), ([], None))


class Fetch(Tmp):
    def test_one_read_a_day_with_a_generic_user_agent(self):
        rows, asof = darko.fetch("2026-11-12", get=self.get(LIST_PAGE))
        self.assertEqual((len(rows), asof), (2, "2026-11-10"))
        url, params, headers = self.calls[0]
        self.assertEqual((url, params), ("https://www.darko.app/projections/__data.json", {"asof": "2026-11-12"}))
        self.assertNotIn("sports", headers["User-Agent"].lower())
        again = darko.fetch("2026-11-12", get=self.get(COLUMN_PAGE))   # same day: the cached read
        self.assertEqual((len(again[0]), len(self.calls)), (2, 1))
        darko.fetch("2026-11-13", get=self.get(COLUMN_PAGE))           # next day: read again
        self.assertEqual(len(self.calls), 2)

    def test_a_failed_read_returns_nothing_and_waits_for_tomorrow(self):
        with mock.patch("traceback.print_exc"):
            self.assertEqual(darko.fetch("2026-11-12", get=self.get(ConnectionError("down"))), (None, None))
            self.assertEqual(darko.fetch("2026-11-12", get=self.get(LIST_PAGE)), (None, None))
        self.assertEqual(len(self.calls), 1)
        self.assertIn("down", darko.error("2026-11-12"))
        with mock.patch("traceback.print_exc"):
            self.assertEqual(darko.fetch("2026-11-13", get=self.get({}, status=503)), (None, None))
            self.assertEqual(darko.fetch("2026-11-14", get=self.get({"nodes": []})), (None, None))   # page changed


class Factors(Tmp):
    def test_minutes_factor_by_name_to_the_nearest_005(self):
        rows = [{"name": "Nikola Jokić", "min": 34.0}, {"name": "Ernest Udeh, Jr.", "min": 1.6},
                {"name": "Twin", "min": 20.0}, {"name": "Short Line", "min": 10.0}, {"name": "Nobody", "min": 9.0},
                {"name": "Up A Bit", "min": 20.6}]
        names = {"1": "Nikola Jokic", "2": "Ernest Udeh Jr.", "3": "Twin", "4": "Twin", "5": "Short Line", "6": "Up A Bit"}
        lines = {"1": 34.0, "2": 3.2, "3": 20, "4": 20, "5": 0.5, "6": 20.0}
        self.assertEqual(darko.factors(rows, lines, names), {"1": 1.0, "2": 0.5, "6": 1.05})   # twins, sub-1-minute line skipped
        self.assertEqual(darko.factors(rows, lines, names, keep={"2"}), {"2": 0.5})
        self.assertEqual((darko.step(1.024), darko.step(1.026), darko.step(0.731)), (1.0, 1.05, 0.75))

    def test_keeps_my_roster_named_and_the_next_ranked_free_agents(self):
        fas = [{"id": f"f{i}", "own": None, "v": 11 - i} for i in range(12)]
        block = {"players": [{"id": "1", "own": "me", "v": -3}, {"id": "7", "own": "Them", "v": 5}, *fas,
                             {"id": "x", "own": None, "v": -9}]}
        keep = darko.keep_ids([(block, {"x"})])
        self.assertEqual(keep, {"1", "x"} | {f"f{i}" for i in range(darko.TOP_FA)})         # another team's "7": not needed
        self.assertEqual(darko.keep_ids([(None, ())]), set())

    def test_names_from_the_shown_advice(self):
        block = {"players": [{"id": "1", "name": "Drop Guy"}, {"id": "2", "name": "Add Guy"}, {"id": "3", "name": "Next Guy"},
                             {"id": "4", "name": "Other Guy"}]}
        adv = {"adds": ["Drop Drop Guy (2 games this week, value -1.0/g), add Add Guy (PG, ATL, 2 games this week, value "
                        "+2.0/g, 5% rostered): +6.0 this week over keeping Drop Guy (helps PTS).", "Not a swap line."],
               "games": {"streamers": ["Next Guy (SG, BOS, 3% rostered): 2 games this week (Fr/Su), +4.0 this week"]}}
        self.assertEqual(darko.named(block, adv), {"1", "2", "3"})
        self.assertEqual(darko.named(block, None), set())

    def test_snapshot_one_day_per_line_and_kept_days(self):
        for i in range(darko.KEEP_DAYS + 2):
            day = (dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat()
            darko.record(day, [{"name": "A", "min": 30.0}], {"1": 20.0}, {"1": "A"}, {"1"})
        text = darko.SNAP.read_text()
        days = darko.load()["days"]
        self.assertEqual(len(days), darko.KEEP_DAYS)
        self.assertNotIn("2026-10-01", days)
        self.assertEqual(days["2026-11-30"], {"how": "daily", "m": {"1": 1.5}})        # our factor only: no DARKO date
        self.assertEqual(len(text.splitlines()), darko.KEEP_DAYS + 2)
        darko.record("2026-11-30", [{"name": "A", "min": 10.0}], {"1": 20.0}, {"1": "A"}, {"1"})   # a kept day stands
        self.assertEqual(darko.load()["days"]["2026-11-30"]["m"], {"1": 1.5})
        self.assertIsNone(darko.record("2026-12-01", [], {}, {}, set()))
        self.assertIsNone(darko.record("2026-12-01", [{"name": "A", "min": 30.0}], {"1": 20.0}, {"1": "A"}, {"2"}))

    def test_switch_uses_the_newest_recent_snapshot(self):
        darko.record("2026-11-10", [{"name": "A", "min": 30.0}], {"1": 20.0}, {"1": "A"}, {"1"})
        self.assertEqual(darko.today_factors("2026-11-12"), ({"1": 1.5}, "2026-11-10"))
        self.assertEqual(darko.today_factors("2026-11-14"), ({}, None))      # too old
        self.assertEqual(darko.today_factors("2026-11-09"), ({}, None))      # nothing on or before


class Track(Tmp):
    POOL = {"1": {"name": "Nikola Jokic", "season": {"40": 33.0}, "gp": 9, "proj": {}},
            "2": {"name": "Ernest Udeh Jr.", "season": {"40": 3.2}, "gp": 6, "proj": {}},
            "3": {"name": "No Minutes", "season": {"0": 3}, "gp": 6, "proj": {}}}
    BLOCKS = [({"players": [{"id": "1", "own": "me", "v": 2}, {"id": "2", "own": None, "v": -4}]}, set())]
    at = lambda self, h: dt.datetime(2026, 11, 12, h + 6, 0, tzinfo=dt.timezone.utc)   # h am CT

    def test_once_a_day_from_7am_ct_for_the_kept_players(self):
        self.assertIsNone(darko.track(self.at(6), self.BLOCKS, pool=self.POOL, get=self.get(LIST_PAGE)))
        self.assertEqual(self.calls, [])                                               # before 7am: no read
        self.assertIsNone(darko.track(self.at(8), [], pool=self.POOL, get=self.get(LIST_PAGE)))
        self.assertEqual(self.calls, [])                                               # no basketball tabs: no read
        msg = darko.track(self.at(8), self.BLOCKS, pool=self.POOL, get=self.get(LIST_PAGE))
        self.assertEqual(msg, "darko: 2 players' minutes factors for 2026-11-12")
        self.assertEqual(darko.load()["days"]["2026-11-12"], {"how": "daily", "m": {"1": 1.05, "2": 0.5}})
        self.assertIsNone(darko.track(self.at(9), self.BLOCKS, pool=self.POOL, get=self.get(LIST_PAGE)))
        self.assertEqual(len(self.calls), 1)
        old = darko.CACHE_DIR / "asof-2026-10-01.json"                                  # cached reads 14+ days old go
        old.write_text("{}")
        darko.track(self.at(8) + dt.timedelta(days=1), self.BLOCKS, pool=self.POOL, get=self.get(LIST_PAGE))
        self.assertFalse(old.exists())
        self.assertTrue((darko.CACHE_DIR / "asof-2026-11-12.json").exists())

    def test_never_fails_a_run(self):
        with mock.patch("traceback.print_exc"):
            msg = darko.track(self.at(8), self.BLOCKS, pool=self.POOL, get=self.get(ConnectionError("down")))
            self.assertIn("no reading today (ConnectionError: down)", msg)
            with mock.patch.object(darko, "load", side_effect=RuntimeError("bad file")):
                self.assertIsNone(darko.track(self.at(8), self.BLOCKS, pool=self.POOL, get=self.get(LIST_PAGE)))

    def test_run_blocks_from_the_basketball_tabs(self):
        class Lg:
            def __init__(self, name, sport, values):
                self.name, self.sport, self.values = name, sport, values
        block = {"players": [{"id": "5", "name": "Add Guy", "own": None}]}
        views = {"BB": {"advice": {"games": {"streamers": ["Add Guy (PG, ATL, 5% rostered): 2 games this week (Th/Sa), +6.0 this week"]}}}}
        out = darko.run_blocks([Lg("BB", "nba", block), Lg("FB", "nfl", {"players": []}), Lg("X", "nba", None)], views)
        self.assertEqual(out, [(block, {"5"})])

    def test_backfill_reads_each_missing_morning_once_for_the_kept_players(self):
        block = {"players": [{"id": "1", "name": "Nikola Jokic", "min": 17.0, "own": None, "v": -1},
                             {"id": "2", "name": "Ernest Udeh, Jr.", "min": 3.2, "own": None, "v": -2},
                             *[{"id": f"f{i}", "name": f"F {i}", "min": 20.0, "own": None, "v": 5} for i in range(10)]]}
        named = {"swaps": [{"add_id": "1", "drop_id": None}], "streamers": []}
        hist = [{"day": "2026-11-06", "block": block, **named}, {"day": "2026-11-06", "block": block, **named},
                {"day": "2026-11-07", "block": block, **named}]
        darko.record("2026-11-07", [{"name": "A", "min": 1.0}], {"1": 1.0}, {"1": "A"}, {"1"})
        self.assertEqual(darko.backfill(hist, get=self.get(LIST_PAGE)), ["2026-11-06"])
        self.assertEqual([c[1] for c in self.calls], [{"asof": "2026-11-06"}])
        # Jokic: named by the swap; Udeh: matched but neither rostered, named nor a top-10 free agent
        self.assertEqual(darko.load()["days"]["2026-11-06"], {"how": "backfill", "m": {"1": 2.05}})


if __name__ == "__main__":
    unittest.main()
