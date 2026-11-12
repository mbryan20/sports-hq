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
        self.assertEqual((url, params), ("https://www.darko.app/projections/__data.json", None))
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
        self.assertIn("down", json.loads((darko.CACHE_DIR / "live.json").read_text())["error"])
        with mock.patch("traceback.print_exc"):
            self.assertEqual(darko.fetch("2026-11-13", get=self.get({}, status=503)), (None, None))
            self.assertEqual(darko.fetch("2026-11-14", get=self.get({"nodes": []})), (None, None))   # page changed

    def test_time_machine_reads_are_kept_for_good(self):
        darko.fetch("2026-11-12", asof="2026-11-06", get=self.get(LIST_PAGE))
        self.assertEqual(self.calls[0][1], {"asof": "2026-11-06"})
        darko.fetch("2026-11-20", asof="2026-11-06", get=self.get(LIST_PAGE))
        self.assertEqual(len(self.calls), 1)


class Factors(Tmp):
    def test_minutes_factor_by_name(self):
        rows = [{"name": "Nikola Jokić", "min": 34.0}, {"name": "Ernest Udeh, Jr.", "min": 1.6},
                {"name": "Twin", "min": 20.0}, {"name": "Short Line", "min": 10.0}, {"name": "Nobody", "min": 9.0}]
        names = {"1": "Nikola Jokic", "2": "Ernest Udeh Jr.", "3": "Twin", "4": "Twin", "5": "Short Line"}
        lines = {"1": 34.0, "2": 3.2, "3": 20, "4": 20, "5": 0.5}
        self.assertEqual(darko.factors(rows, lines, names), {"1": 1.0, "2": 0.5})   # twins and a sub-1-minute line skipped

    def test_snapshot_one_day_per_line_and_kept_days(self):
        for i in range(darko.KEEP_DAYS + 2):
            day = (dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat()
            darko.record(day, [{"name": "A", "min": 30.0}], "x", {"1": 20.0}, {"1": "A"})
        text = darko.SNAP.read_text()
        days = darko.load()["days"]
        self.assertEqual(len(days), darko.KEEP_DAYS)
        self.assertNotIn("2026-10-01", days)
        self.assertEqual(days["2026-11-30"], {"asof": "x", "how": "live", "m": {"1": 1.5}})
        self.assertEqual(len(text.splitlines()), darko.KEEP_DAYS + 2)
        darko.record("2026-11-30", [{"name": "A", "min": 10.0}], "y", {"1": 20.0}, {"1": "A"})   # a kept day stands
        self.assertEqual(darko.load()["days"]["2026-11-30"]["m"], {"1": 1.5})
        self.assertIsNone(darko.record("2026-12-01", [], "y", {}, {}))

    def test_switch_uses_the_newest_recent_snapshot(self):
        darko.record("2026-11-10", [{"name": "A", "min": 30.0}], "2026-11-09", {"1": 20.0}, {"1": "A"})
        self.assertEqual(darko.today_factors("2026-11-12"), ({"1": 1.5}, "2026-11-09", "2026-11-10"))
        self.assertEqual(darko.today_factors("2026-11-14"), ({}, None, None))      # too old
        self.assertEqual(darko.today_factors("2026-11-09"), ({}, None, None))      # nothing on or before


class Track(Tmp):
    POOL = {"1": {"name": "Nikola Jokic", "season": {"40": 34.0}, "gp": 9, "proj": {}},
            "2": {"name": "Ernest Udeh Jr.", "season": {"40": 3.2}, "gp": 6, "proj": {}},
            "3": {"name": "No Minutes", "season": {"0": 3}, "gp": 6, "proj": {}}}
    at = lambda self, h: dt.datetime(2026, 11, 12, h + 6, 0, tzinfo=dt.timezone.utc)   # h am CT

    def test_once_a_day_from_7am_ct(self):
        self.assertIsNone(darko.track(self.at(6), pool=self.POOL, get=self.get(LIST_PAGE)))
        self.assertEqual(self.calls, [])                                               # before 7am: no read
        msg = darko.track(self.at(8), pool=self.POOL, get=self.get(LIST_PAGE))
        self.assertIn("2 players", msg)
        self.assertEqual(darko.load()["days"]["2026-11-12"], {"asof": "2026-11-10", "how": "live", "m": {"1": 1.03, "2": 0.5}})
        self.assertIsNone(darko.track(self.at(9), pool=self.POOL, get=self.get(LIST_PAGE)))
        self.assertEqual(len(self.calls), 1)

    def test_never_fails_a_run(self):
        with mock.patch("traceback.print_exc"):
            msg = darko.track(self.at(8), pool=self.POOL, get=self.get(ConnectionError("down")))
            self.assertIn("no reading today (ConnectionError: down)", msg)
            with mock.patch.object(darko, "load", side_effect=RuntimeError("bad file")):
                self.assertIsNone(darko.track(self.at(8), pool=self.POOL, get=self.get(LIST_PAGE)))

    def test_backfill_reads_each_missing_morning_once(self):
        block = {"players": [{"id": "1", "name": "Nikola Jokic", "min": 17.0}, {"id": "9", "name": "Ernest Udeh, Jr.", "min": 0}]}
        hist = [{"day": "2026-11-06", "block": block}, {"day": "2026-11-06", "block": block}, {"day": "2026-11-07", "block": block}]
        darko.record("2026-11-07", [{"name": "A", "min": 1.0}], "z", {"1": 1.0}, {"1": "A"})
        self.assertEqual(darko.backfill(hist, get=self.get(LIST_PAGE)), ["2026-11-06"])
        self.assertEqual([c[1] for c in self.calls], [{"asof": "2026-11-06"}])
        self.assertEqual(darko.load()["days"]["2026-11-06"], {"asof": "2026-11-10", "how": "time machine", "m": {"1": 2.05}})


if __name__ == "__main__":
    unittest.main()
