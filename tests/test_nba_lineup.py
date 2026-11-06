"""B5: NBA daily lineup moves and the one push a day before the first tip (shq/nba_lineup.py)."""
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import nba_lineup, notify

UTC = dt.timezone.utc
NOON = dt.datetime(2026, 11, 5, 18, 0, tzinfo=UTC)            # Thu noon CST
TIP = dt.datetime(2026, 11, 6, 0, 30, tzinfo=UTC)             # Thu 6:30pm CST
LATE = dt.datetime(2026, 11, 6, 2, 0, tzinfo=UTC)             # Thu 8:00pm CST


def p(name, slot, positions, v, *, kickoff=TIP, bye=False, status=None):
    return {"id": f"espn{name}", "name": name, "slot": slot, "positions": positions, "status": status, "why": "",
            "kickoff": None if bye else kickoff, "started": False, "bye": bye, "proj": 0.0, "team": "BOS", "opp": "vs NY",
            "val": {"v": v, "rk": 50, "wk": 0, "src": "8 g"}}


class League:
    sport, key, week, name = "nba", "espn:nba:1", 3, "Test BB"
    def __init__(self, starters, bench):
        self.starters, self.bench = starters, bench


class Lineup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = notify.ALERTS
        notify.ALERTS = Path(self.tmp.name) / "alerts.json"
        notify.sent.clear()

    def tearDown(self):
        notify.ALERTS = self.saved
        self.tmp.cleanup()

    def league(self):
        return League([p("Idle G", "G", ["PG", "G", "UT"], 3.0, bye=True), p("Hurt C", "C", ["C", "UT"], 2.0, status="OUT"),
                       p("Weak F", "F", ["SF", "F", "UT"], -2.0), p("Good UT", "UT", ["SG", "UT"], 4.0)],
                      [p("Bench G", "BN", ["SG", "G", "UT"], 1.0), p("Bench C", "BN", ["C", "F", "UT"], 0.5),
                       p("Bench F", "BN", ["PF", "F", "UT"], 0.5), p("Idle Bench", "BN", ["SF", "F", "UT"], 9.0, bye=True)])

    def test_moves_fill_dead_starters_then_clear_upgrades(self):
        ms = nba_lineup.moves(self.league(), NOON)
        self.assertEqual([(m["start"], m["sit"], m["why"]) for m in ms],
                         [("Bench G", "Idle G", "no game today"), ("Bench C", "Hurt C", "OUT"),
                          ("Bench F", "Weak F", "+2.5 value/g")])
        self.assertIn("Start Bench G (BOS vs NY, Thu 6:30p) over Idle G at G: no game today", ms[0]["text"])

    def test_no_move_without_an_edge(self):
        lg = League([p("Starter", "F", ["SF", "F"], 1.0)], [p("Bench", "BN", ["SF", "F"], 1.5)])
        self.assertEqual(nba_lineup.moves(lg, NOON), [])                   # +0.5 is under MIN_EDGE
        lg.bench[0]["val"]["v"] = 2.5
        self.assertEqual(len(nba_lineup.moves(lg, NOON)), 1)

    def test_one_push_a_day_inside_the_window_and_out_starters_not_repeated(self):
        self.assertIsNone(nba_lineup.send([self.league()], NOON))          # 6.5h before tip: too early
        before = TIP - dt.timedelta(hours=2, minutes=30)
        title = nba_lineup.send([self.league()], before)
        self.assertEqual(title, "NBA lineup: 3 changes before 6:30p tip")
        self.assertIsNone(nba_lineup.send([self.league()], before + dt.timedelta(minutes=30)))   # once a day
        self.assertEqual(len(notify.sent), 1)
        seen = notify.load_json(notify.ALERTS)
        self.assertIn("espn:nba:1:w3:espnHurt C:swap", seen)               # the injury watch won't push him again
        self.assertIsNone(nba_lineup.send([self.league()], LATE))          # after tip-off

    def test_nothing_to_do_sends_nothing(self):
        lg = League([p("Good", "G", ["G"], 3.0)], [p("Worse", "BN", ["G"], 1.0)])
        self.assertIsNone(nba_lineup.send([lg], TIP - dt.timedelta(hours=1)))
        self.assertEqual(notify.sent, [])


if __name__ == "__main__":
    unittest.main()
