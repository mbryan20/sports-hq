"""War Room v2 data build: bid history by leg, confirmed vs projected cuts, freed players from an empty roster."""
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ["DRY_RUN"] = "1"

from warroom import model

NOW = dt.datetime(2026, 11, 3, 13, 0, tzinfo=dt.timezone.utc)   # Tue 7am CT


def claim(rid, pid, bid, status, leg, tid):
    return {"transaction_id": tid, "type": "waiver", "status": status, "roster_ids": [rid], "adds": {pid: rid},
            "leg": leg, "settings": {"waiver_bid": bid}, "status_updated": 1793000000000 + tid}


class History(unittest.TestCase):
    def test_bids_by_leg_with_share_of_budget(self):
        txs = [claim(1, "A", 50, "complete", 1, 1), claim(2, "A", 40, "failed", 1, 2),
               claim(1, "B", 30, "complete", 3, 3), claim(2, "B", 75, "failed", 3, 4),
               claim(2, "C", 5, "failed", 3, 5)]                       # nobody won C: not a market row
        hist, before, spent = model.claims_history(txs, 200)
        self.assertEqual([(h["leg"], h["sid"], h["win"], h["bid"]) for h in hist], [(1, "A", 1, 50), (3, "B", 1, 30)])
        self.assertEqual(hist[1]["pct"], [[2, 75, 38], [1, 30, 20]])  # roster 1 had $150 left going into leg 3
        self.assertEqual(spent, {1: 80, 2: 0})
        self.assertEqual(before["1"][3], 150)


class FakeNfl:
    ids, pts, defpts, cur, injuries, bye = {}, {}, {}, {}, {}, {}

    def __init__(self, final=(), weekly=None):
        self.final, self.weekly = set(final), weekly or {}

    def final_weeks(self):
        return self.final

    def stats_weeks(self):
        return {w for v in self.weekly.values() for w in v}

    def player(self, sid, db=None):
        return {"name": sid, "pos": "WR", "team": "KC", "gsis": sid}

    def week_points(self, sid, week, info=None):
        return self.weekly.get(sid, {}).get(week)


def league(rosters, txs=(), matchups=None, last_scored=7):
    lid = model.LEAGUE_ID
    base = model.BASE
    data = {
        f"{base}/league/{lid}": {"name": "Test", "settings": {"waiver_budget": 200, "leg": 8, "last_scored_leg": last_scored},
                                 "scoring_settings": {"rec": 0.5}},
        f"{base}/league/{lid}/rosters": rosters,
        f"{base}/league/{lid}/users": [{"user_id": f"u{r['roster_id']}", "display_name": f"T{r['roster_id']}"} for r in rosters],
        f"{base}/user/{model.SLEEPER_USERNAME}": {"user_id": "u1"},
    }
    for w in range(1, 10):
        data[f"{base}/league/{lid}/transactions/{w}"] = [t for t in txs if t["leg"] == w]
    for w, ms in (matchups or {}).items():
        data[f"{base}/league/{lid}/matchups/{w}"] = ms
    return lambda url, params=None: data.get(url, [])


def roster(rid, players, eliminated=None, used=0):
    st = {"waiver_budget_used": used}
    if eliminated:
        st["eliminated"] = eliminated
    return {"roster_id": rid, "owner_id": f"u{rid}", "players": players, "starters": players[:1], "settings": st}


@mock.patch("warroom.model.espn.games", lambda season, week: {})   # no live scoreboard in tests
class Cut(unittest.TestCase):
    def test_confirmed_cut_takes_players_from_the_chop_even_with_an_empty_roster(self):
        chop = {"transaction_id": 99, "type": "chopped", "status": "complete", "roster_ids": [3], "leg": 7,
                "drops": {"x1": 3, "x2": 3}, "status_updated": 1793000000000}
        fetch = league([roster(1, ["a"]), roster(2, ["b"]), roster(3, [], eliminated=7)], [chop],
                       {7: [{"roster_id": 1, "points": 120, "starters": ["a"]}, {"roster_id": 2, "points": 110, "starters": ["b"]},
                            {"roster_id": 3, "points": 90, "starters": ["x1"], "players": ["x1", "x2"]}]})
        d = model.build(NOW, FakeNfl(final={7}, weekly={"a": {7: 10}, "x1": {7: 8}, "x2": {7: 5}}), fetch, players={})
        self.assertEqual((d["week"], d["cut"]["roster"], d["cut"]["confirmed"]), (8, 3, True))
        self.assertEqual(sorted(d["teams"]["3"]["roster"]), ["x1", "x2"])
        self.assertEqual(d["last_week"], 8)                      # two teams left: one more cut
        self.assertIn("(confirmed)", d["asof"])

    def test_monday_night_cut_is_projected_until_sleeper_marks_it(self):
        # week 8 is final in nflverse but Sleeper hasn't scored it or chopped anyone yet
        fetch = league([roster(1, ["a"]), roster(2, ["b"]), roster(3, ["c"])], [],
                       {8: [{"roster_id": 1, "points": 120, "starters": ["a"]}, {"roster_id": 2, "points": 95, "starters": ["b"]},
                            {"roster_id": 3, "points": 100, "starters": ["c"]}]})
        d = model.build(NOW, FakeNfl(final={7, 8}), fetch, players={})
        self.assertEqual((d["week"], d["cut"]["roster"], d["cut"]["confirmed"]), (9, 2, False))
        self.assertEqual((d["teams"]["2"]["roster"], d["dead"]), (["b"], {}))   # still listed, so its players show as freed
        self.assertIn("projected", d["asof"])

    def test_nflverse_overrides_sleeper_only_while_sleeper_is_still_scoring(self):
        ms = {8: [{"roster_id": 1, "points": 100, "starters": ["a"]}, {"roster_id": 2, "points": 90, "starters": ["b"]}]}
        nfl = FakeNfl(final={7, 8}, weekly={"a": {8: 80.0}, "b": {8: 90.0}})   # nflverse: a really scored 80
        d = model.build(NOW, nfl, league([roster(1, ["a"]), roster(2, ["b"])], [], ms), players={})
        self.assertEqual(d["cut"]["roster"], 1)
        self.assertIn("note", d["cut"])
        # once Sleeper has scored the week, its official points decide
        d = model.build(NOW, nfl, league([roster(1, ["a"]), roster(2, ["b"])], [], ms, last_scored=8), players={})
        self.assertEqual(d["cut"]["roster"], 2)
        self.assertNotIn("note", d["cut"])


CHOPPED_AT = 1793077200000            # Tue Oct 27 2026, ~3:20pm CT


def chopped():
    return {"transaction_id": 99, "type": "chopped", "status": "complete", "roster_ids": [3], "leg": 7,
            "drops": {"x1": 3, "x2": 3}, "status_updated": CHOPPED_AT}


@mock.patch("warroom.model.espn.games", lambda season, week: {})
class FreedStatus(unittest.TestCase):
    """Freed players can only be bid on until the waiver run after the cut; then they're free agents."""
    def fetch(self, txs):
        return league([roster(1, ["a"]), roster(2, ["b"]), roster(3, [], eliminated=7)], [chopped()] + txs,
                      {7: [{"roster_id": 1, "points": 120, "starters": ["a"]}, {"roster_id": 2, "points": 110, "starters": ["b"]},
                           {"roster_id": 3, "points": 90, "starters": ["x1"], "players": ["x1", "x2"]}]})

    def nfl(self):
        # two games each: the model only treats players with 2+ games as free agents worth listing
        return FakeNfl(final={7}, weekly={"a": {6: 10, 7: 10}, "b": {6: 9, 7: 9}, "x1": {6: 18, 7: 18}, "x2": {6: 5, 7: 5}})

    def test_on_waivers_until_the_run(self):
        wed_1am = dt.datetime(2026, 10, 28, 6, 0, tzinfo=dt.timezone.utc)
        d = model.build(wed_1am, self.nfl(), self.fetch([]), players={})
        self.assertEqual(d["cut"]["freed_status"], "on waivers")

    def test_cleared_once_claims_processed_after_the_chop(self):
        run = claim(2, "x2", 4, "complete", 7, 7)
        run["status_updated"] = CHOPPED_AT + 15 * 3600 * 1000
        d = model.build(NOW, self.nfl(), self.fetch([run]), players={})
        self.assertEqual(d["cut"]["freed_status"], "cleared")

    def test_cleared_when_the_run_time_has_passed_even_with_no_claims(self):
        thu = dt.datetime(2026, 10, 29, 15, 0, tzinfo=dt.timezone.utc)
        d = model.build(thu, self.nfl(), self.fetch([]), players={})
        self.assertEqual(d["cut"]["freed_status"], "cleared")

    def test_export_has_no_faab_prices_once_cleared(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        thu = dt.datetime(2026, 10, 29, 15, 0, tzinfo=dt.timezone.utc)
        for when, is_open in ((dt.datetime(2026, 10, 28, 6, 0, tzinfo=dt.timezone.utc), True), (thu, False)):
            d = model.build(when, self.nfl(), self.fetch([]), players={})
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(d, f)
            try:
                out = json.loads(subprocess.run([node, "warroom/export.js", f.name], check=True, capture_output=True,
                                                text=True, encoding="utf-8").stdout)
            finally:
                os.unlink(f.name)
            self.assertEqual(out["waivers_open"], is_open)
            x1 = next(b for b in out["bids"] if b["sleeper_id"] == "x1")
            if is_open:
                self.assertEqual(x1["source"], "freed")
                self.assertEqual(out["freed_players"][0]["sleeper_id"], "x1")
            else:
                self.assertEqual((x1["source"], x1["est_price"], x1["your_max"]), ("free agent", 0, 0))
                self.assertIn(x1["call"], ("Add free", "Skip"))
                self.assertEqual(out["freed_players"], [])


if __name__ == "__main__":
    unittest.main()
