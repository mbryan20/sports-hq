"""Nightly model health (shq/health.py): status vs baselines, cut-odds scoring, the price-ladder backtest, and
our bid recommendations scored against what happened (git history faked)."""
import datetime as dt
import math
import os
import unittest
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import health

NOW = dt.datetime(2026, 11, 12, 13, 0, tzinfo=dt.timezone.utc)
TODAY = "2026-11-12"


class Judge(unittest.TestCase):
    def test_first_measurement_sets_the_baseline(self):
        base = {}
        row = health.judge("wr.proj_mae", 16.6, 81, base, TODAY)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(base["wr.proj_mae"]["value"], 16.6)
        self.assertEqual(base["wr.proj_mae"]["set"], TODAY)

    def test_watch_and_drift_by_tolerance(self):
        base = {"wr.proj_mae": {"value": 16.0, "set": "2026-11-03"}}          # lower is better, tolerance 2
        self.assertEqual(health.judge("wr.proj_mae", 17.5, 90, base, TODAY)["status"], "watch")
        self.assertEqual(health.judge("wr.proj_mae", 18.5, 90, base, TODAY)["status"], "drift")
        self.assertEqual(health.judge("wr.proj_mae", 12.0, 90, base, TODAY)["status"], "ok")   # better never drifts

    def test_floor_marks_weak_whatever_the_baseline(self):
        base = {"wr.cut_skill": {"value": -0.02, "set": "2026-11-03"}}
        row = health.judge("wr.cut_skill", -0.02, 8, base, TODAY)
        self.assertEqual((row["status"], row["floor"]), ("weak", 0.0))

    def test_target_checks_and_waiting(self):
        self.assertEqual(health.judge("wr.ladder_cov80", 0.79, 40, {}, TODAY)["status"], "ok")
        self.assertEqual(health.judge("wr.ladder_cov80", 0.6, 40, {}, TODAY)["status"], "drift")
        self.assertEqual(health.judge("wr.ladder_cov80", 0.6, 5, {}, TODAY)["status"], "waiting")   # too few claims
        self.assertEqual(health.judge("rec.would_win", None, 0, {}, TODAY)["status"], "waiting")

    def test_rollup(self):
        self.assertEqual(health.rollup([{"status": "ok"}, {"status": "weak"}]), "weak")
        self.assertEqual(health.rollup([{"status": "waiting"}]), "waiting")
        self.assertEqual(health.rollup([{"status": "info"}, {"status": "waiting"}]), "ok")


class CutOdds(unittest.TestCase):
    def test_lowest_probs(self):
        p = health.lowest_probs([100, 100, 100], 20)
        self.assertAlmostEqual(sum(p), 1, places=6)
        self.assertAlmostEqual(p[0], 1 / 3, places=3)
        p = health.lowest_probs([90, 110, 130], 20)
        self.assertGreater(p[0], p[1])
        self.assertGreater(p[1], p[2])

    def test_coin_toss_has_no_skill(self):
        s = health.cut_scores([({1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25}, 2)])
        self.assertAlmostEqual(s["skill"], 0, places=3)
        self.assertEqual(s["coin_toss"], round(math.log(4), 3))
        good = health.cut_scores([({1: 0.7, 2: 0.1, 3: 0.1, 4: 0.1}, 1)])
        self.assertGreater(good["skill"], 0)
        self.assertEqual(good["ranks"], [1])


class Ladder(unittest.TestCase):
    def test_win_chance_matches_model_js(self):
        lad = {"lo": [0.0, 0.5, 1.0, 1.5], "hi": []}
        self.assertEqual(health.win_chance(0, 10, lad), 0.25)       # $0 only "beats" claims nobody made
        self.assertEqual(health.win_chance(11, 10, lad), 0.75)      # beats 0, 5 and 10
        self.assertEqual(health.price_for(0.5, 10, lad), 6)

    def test_leave_one_run_out(self):
        # three runs; the estimate is always $10 and claims went for $5, $10, $15
        cases = [{"leg": L, "targets": [("A%d" % L, paid)]} for L, paid in ((3, 5), (4, 10), (5, 15))]
        est = [{"leg": c["leg"], "est": [10]} for c in cases]
        out = health.ladder_backtest(cases, est, {"A3": "RB", "A4": "WR", "A5": "RB"})
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["est_mae"], round((5 + 0 + 5) / 3, 1))
        self.assertIn("pos RB", out["by"])
        self.assertEqual(out["by"]["pos RB"]["n"], 2)


def fake_league():
    lg = object.__new__(health.League)
    lg.played, lg.me = 8, 1
    lg.display = {1: "me", 2: "rival", 3: "other"}
    lg.team_name = {1: "My Team", 2: "Rival FC", 3: "other"}
    lg.cut_week = {1: None, 2: None, 3: 8}
    lg.weekly = {8: [{"roster_id": 1, "points": 120, "players": ["a"]}, {"roster_id": 2, "points": 110, "players": ["b"]},
                     {"roster_id": 3, "points": 80, "players": ["c"]}]}
    lg.db = {"s1": {"full_name": "Star One", "position": "WR"}, "s2": {"full_name": "Cheap Two", "position": "RB"}}
    lg.kickoffs = {8: dt.datetime(2026, 10, 30, 0, 15, tzinfo=dt.timezone.utc), 9: dt.datetime(2026, 11, 6, 1, 15, tzinfo=dt.timezone.utc)}
    chop = int(dt.datetime(2026, 11, 3, 5, 56, tzinfo=dt.timezone.utc).timestamp() * 1000)     # Mon 11:56pm CT
    lg.txs = [
        {"type": "chopped", "leg": 8, "status_updated": chop, "roster_ids": [3]},
        {"transaction_id": "1", "type": "waiver", "status": "complete", "leg": 8, "roster_ids": [2], "adds": {"s1": 2}, "settings": {"waiver_bid": 40}},
        {"transaction_id": "2", "type": "waiver", "status": "failed", "leg": 8, "roster_ids": [1], "adds": {"s1": 1}, "settings": {"waiver_bid": 30}},
        {"transaction_id": "3", "type": "waiver", "status": "complete", "leg": 8, "roster_ids": [1], "adds": {"s2": 1}, "settings": {"waiver_bid": 4}},
    ]
    return lg


class Recommendations(unittest.TestCase):
    def test_bids_scored_against_the_waiver_run(self):
        lg = fake_league()
        run = lg.waiver_run(8)
        self.assertEqual(dt.datetime.fromtimestamp(run, health.dt.timezone.utc).strftime("%a %H:%M"), "Wed 08:15")   # 2:15am CST
        bids = {"week": 9, "cut": {"week": 8}, "bids": [
            {"sleeper_id": "s1", "name": "Star One", "source": "freed", "call": "Bid", "bid": 35, "win_chance": 0.6, "est_price": 30, "value": 50},
            {"sleeper_id": "s2", "name": "Cheap Two", "source": "freed", "call": "Bid", "bid": 3, "win_chance": 0.9, "est_price": 2, "value": 8},
            {"sleeper_id": "x", "name": "Free Guy", "source": "free agent", "call": "Add free", "bid": 0, "est_price": 0, "value": 0}]}
        dash = {"leagues": {"Guillotine": {"advice": {"guillotine": {"week": 9, "bids": [
            {"name": "Star One", "price": 33, "max": 38, "call": "bid"}], "freed": None, "teams": []}}}}}
        files = {("b1", "docs/war-room-v2/bids.json"): bids, ("d1", "docs/data/lineups.json"): dash}
        with mock.patch.object(health, "now_utc", return_value=NOW):
            o = health.rec_outcomes(lg, [(run - 3600, "b1")], [(run - 60, "d1")], load=lambda sha, path: files[(sha, path)])
        star, cheap = o["v2_rows"]
        self.assertEqual((star["would_win"], star["paid"], star["winner"], star["my_bid"]), (False, 40, "rival", 30))
        self.assertEqual((cheap["would_win"], cheap["paid"], cheap["i_won"]), (True, 4, True))      # nobody else bid
        self.assertEqual(o["n_rec"], 2)
        self.assertEqual(o["would_win"], 0.5)
        self.assertEqual(o["brier"], round(((0.6 - 0) ** 2 + (0.9 - 1) ** 2) / 2, 3))
        self.assertEqual(o["est_mae"], round((10 + 2) / 2, 1))
        self.assertEqual(o["dash_rows"][0]["would_win"], False)                                     # $33 < rival's $40
        self.assertEqual(o["winners_paid"][8][0]["paid"], 40)

    def test_nothing_before_tracking_started(self):
        lg = fake_league()
        with mock.patch.object(health, "now_utc", return_value=NOW):
            o = health.rec_outcomes(lg, [], [], load=lambda *a: None)
        self.assertEqual((o["runs"], o["n_rec"], o["would_win"]), ([], 0, None))


class ShownOdds(unittest.TestCase):
    def test_last_version_before_kickoff_is_scored(self):
        lg = fake_league()
        k = lg.kickoffs[8].timestamp()
        bids = {"week": 8, "cut_risks": [{"team": "me", "cut_risk_next_week": 0.1}, {"team": "rival", "cut_risk_next_week": 0.3},
                                         {"team": "other", "cut_risk_next_week": 0.6}]}
        late = {"week": 8, "cut_risks": [{"team": "other", "cut_risk_next_week": 0.01}]}       # after kickoff: ignored
        dash = {"leagues": {"Guillotine": {"advice": {"guillotine": {"week": 8, "teams": [
            {"name": "My Team", "cut": 0.2}, {"name": "Rival FC", "cut": 0.5}, {"name": "other", "cut": 0.3}]}}}}}
        files = {"b1": bids, "b2": late, "d1": dash}
        s = health.shown_cut_odds(lg, [(k - 100, "b1"), (k + 100, "b2")], [(k - 50, "d1")], load=lambda sha, path: files[sha])
        self.assertEqual(s["v2"]["cut_team_chance"], 0.6)
        self.assertEqual(s["dashboard"]["cut_team_chance"], 0.3)
        self.assertEqual(s["dashboard"]["ranks"], [2])


class FarWeeks(unittest.TestCase):
    def test_misses_by_weeks_ahead(self):
        lg = fake_league()
        lg.kickoffs[7] = lg.kickoffs[8] - dt.timedelta(days=7)
        P = {"a": {"p": "QB", "pw": [20, 30]}, "b": {"p": "QB", "pw": [20, 10]}, "c": {"p": "QB", "pw": [20, 20]}}
        page = {"week": 7, "P": P, "teams": {"1": {"roster": ["a"]}, "2": {"roster": ["b"]}, "3": {"roster": ["c"]}}}
        out = health.far_week_misses(lg, [(lg.kickoffs[7].timestamp() - 10, "p7")], load=lambda sha: page)
        # week 8 seen 2 weeks ahead: real 120/110/80 vs projected 30/10/20 -> misses 90/100/60, minus their mean 83.3
        sd = (sum(x * x for x in (90 - 250 / 3, 100 - 250 / 3, 60 - 250 / 3)) / 3) ** 0.5
        self.assertEqual(out[2], (round(sd, 1), 3))
        self.assertNotIn(1, out)                  # no page snapshot from before week 8 itself


if __name__ == "__main__":
    unittest.main()
