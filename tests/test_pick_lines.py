"""Pool Picks stale-line scanner: key-number gains, value side, ESPN matching, push dedup and cadence."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import lines as L  # noqa: E402


def ev(eid, away, home, spread, kick="2026-10-31T16:00Z", state="pre", league="CFB"):
    team = lambda n: {"location": n, "abbreviation": n[:4].upper(), "displayName": n, "shortDisplayName": n}
    return L.parse_event({"id": eid, "date": kick, "competitions": [{
        "status": {"type": {"state": state}},
        "competitors": [{"homeAway": "home", "team": team(home)}, {"homeAway": "away", "team": team(away)}],
        "odds": [{"spread": spread, "overUnder": 50.5, "provider": {"name": "DraftKings"},
                  "moneyline": {"home": {"close": {"odds": "-500"}}, "away": {"close": {"odds": "+380"}}}}]}]}, league)


class KeyNumbers(unittest.TestCase):
    def test_dog_gains_three(self):
        self.assertEqual(L.key_crossed(3.5, 2.5, (3, 7)), [3])

    def test_push_to_win_counts(self):
        self.assertEqual(L.key_crossed(-6.5, -7, (3, 7, 10, 14)), [7])  # Utah -6.5 vs -7: a 7-pt win now covers
        self.assertEqual(L.key_crossed(3.5, 3, (3, 7)), [3])

    def test_no_key_between(self):
        self.assertEqual(L.key_crossed(13.5, 11.5, (3, 7, 10, 14)), [])
        self.assertEqual(L.key_crossed(-8.5, -9.5, (3, 7, 10, 14)), [])


class GapRow(unittest.TestCase):
    def test_auburn_example(self):
        sg = {"away": "Auburn", "home": "Ole Miss", "home_spread": -13.5}
        r = L.gap_row("cfp", sg, ev("1", "Auburn", "Ole Miss", -11.75), False, "CFB")
        self.assertEqual((r["side"], r["pool_line"], r["market_line"], r["gap"], r["flag"]), ("Auburn", 13.5, 11.75, 1.75, True))

    def test_home_value_and_key_flag(self):
        sg = {"away": "Utah", "home": "Cincinnati", "home_spread": 6.5}
        r = L.gap_row("cfp", sg, ev("2", "Utah", "Cincinnati", 7.0), False, "CFB")
        self.assertEqual((r["side"], r["pool_line"], r["keys"], r["flag"]), ("Utah", -6.5, [7], True))

    def test_small_gap_not_flagged(self):
        sg = {"away": "Oklahoma State", "home": "Iowa State", "home_spread": 8.5}
        r = L.gap_row("cfp", sg, ev("3", "Oklahoma State", "Iowa State", 9.5), False, "CFB")
        self.assertFalse(r["flag"])

    def test_flipped_neutral_site(self):
        e = ev("4", "Georgia", "Florida", 11.5)  # ESPN lists the pool's home team as away
        found, flipped = L.find([e], "Florida", "Georgia")
        self.assertTrue(flipped)
        r = L.gap_row("cfp", {"away": "Florida", "home": "Georgia", "home_spread": -11.5}, found, flipped, "CFB")
        self.assertEqual(r["gap"], 0)


class Matching(unittest.TestCase):
    def test_pool_spellings(self):
        events = [ev("5", "Boston College", "Duke", -7), ev("6", "Miami", "North Carolina", 14)]
        self.assertEqual(L.find(events, "Boston Coll.", "Duke")[0]["id"], "5")
        self.assertEqual(L.find(events, "Miami (FL)", "N. Carolina")[0]["id"], "6")

    def test_moneyline_devig(self):
        self.assertAlmostEqual(ev("7", "A", "B", -10)["p_home"], (500 / 600) / (500 / 600 + 100 / 480), places=6)


class Scan(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        slate = {"cfbd_week": 9, "cfp": {"games": [
            {"away": "Auburn", "home": "Ole Miss", "home_spread": -13.5},
            {"away": "Arizona", "home": "Texas Tech", "home_spread": -3.5}]},
            "bto": {"games": [{"league": "NFL", "away": "MIN", "home": "DET", "home_spread": -3.5, "nfl_week": 8}]}}
        (self.tmp / "slates").mkdir()
        (self.tmp / "slates/2026-w09.json").write_text(json.dumps(slate))
        self.events = {"CFB": [ev("10", "Auburn", "Ole Miss", -11.5), ev("11", "Arizona", "Texas Tech", -3.5)],
                       "NFL": [ev("12", "MIN", "DET", -3.0, kick="2026-11-01T17:00Z", league="NFL")]}
        self.patches = [mock.patch.object(L, "ROOT", self.tmp), mock.patch.object(L, "OUT", self.tmp / "out.json"),
                        mock.patch.object(L, "SENT", self.tmp / "sent.json"),
                        mock.patch.dict(os.environ, {"DRY_RUN": "0"})]  # other test modules leave DRY_RUN=1
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def fetch(self, league, week):
        return self.events[league]

    def test_deadlines_close_pools(self):
        before = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)  # Fri 7am CT: BTO (due Fri 8pm) still open
        _, rows = L.scan(None, before, self.fetch)
        self.assertEqual({r["pool"] for r in rows}, {"bto", "cfp"})
        after = datetime(2026, 10, 31, 15, tzinfo=timezone.utc)  # Sat 10am CT: BTO closed, CFP open
        _, rows = L.scan(None, after, self.fetch)
        self.assertEqual({r["pool"] for r in rows}, {"cfp"})
        _, rows = L.scan(None, datetime(2026, 10, 31, 16, 5, tzinfo=timezone.utc), self.fetch)  # after CFP's 11am lock
        self.assertEqual(rows, [])

    def test_push_once_per_game(self):
        now = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)
        with mock.patch("pp.publish.notify", return_value=True) as n:
            _, rows, pushed = L.run(None, True, now, self.fetch)
            self.assertEqual([r["side"] for r in pushed], ["Auburn"])
            _, _, pushed2 = L.run(None, True, now, self.fetch)
            self.assertEqual(pushed2, [])
            self.assertEqual(n.call_count, 1)
        out = json.loads((self.tmp / "out.json").read_text())
        self.assertEqual(out["rows"][0]["side"], "Auburn")

    def test_failed_push_retries(self):
        now = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)
        with mock.patch("pp.publish.notify", return_value=False):
            self.assertEqual(L.run(None, True, now, self.fetch)[2], [])
        with mock.patch("pp.publish.notify", return_value=True):
            self.assertEqual(len(L.run(None, True, now, self.fetch)[2]), 1)

    def test_due_cadence(self):
        self.assertFalse(L.due(datetime(2026, 11, 1, 15, tzinfo=timezone.utc)))  # Sunday
        (self.tmp / "out.json").write_text(json.dumps({"updated": "2026-10-28T10:00:00-05:00"}))
        self.assertFalse(L.due(datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc)))  # Wed 11am CT, 1h later
        self.assertTrue(L.due(datetime(2026, 10, 28, 17, 0, tzinfo=timezone.utc)))   # 2h later
        (self.tmp / "out.json").write_text(json.dumps({"updated": "2026-10-31T08:00:00-05:00"}))
        self.assertTrue(L.due(datetime(2026, 10, 31, 13, 30, tzinfo=timezone.utc)))  # Sat 8:30am CT, 30 min before CFP lock run-up


if __name__ == "__main__":
    unittest.main()
