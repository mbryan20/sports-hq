"""CFP/BTO bet sizing by expected prize (Nov 27): real weeks left, prize tables, rival habits from the anonymous
profile, the keep-the-posted-size rule (7%) and the lock guard."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "picks"))

try:
    import numpy as np
    from pp import pools as P, cards as C
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

CT = ZoneInfo("America/Chicago")


@unittest.skipUnless(HAVE_NP, "needs numpy")
class WeeksAndKeep(unittest.TestCase):
    def test_weeks_left(self):
        self.assertEqual(P.weeks_left_for("cfp", 13), 2)
        self.assertEqual(P.weeks_left_for("cfp", 14), 1)
        self.assertEqual(P.weeks_left_for("cfp", 15), 1)
        self.assertEqual(P.weeks_left_for("bto", 13), 4)

    def test_keep_within_margin_flip_beyond(self):
        t = [{"k": "a", "ev": 100.0}, {"k": "b", "ev": 106.0}, {"k": "c", "ev": 110.0}]
        key = lambda r: r["k"]
        self.assertEqual(P.keep_or_best(t[:2], t[1], "a", key)["k"], "a")       # 6% better: keep
        self.assertEqual(P.keep_or_best(t, t[2], "a", key)["k"], "c")           # 10% better: change
        self.assertEqual(P.keep_or_best(t, t[2], "a", key, margin=float("inf"))["k"], "a")   # locked
        self.assertEqual(P.keep_or_best(t, t[2], None, key)["k"], "c")
        self.assertEqual(P.keep_or_best(t, t[2], "zz", key)["k"], "c")          # posted size not in table
        z = [{"k": "a", "ev": 0.0}, {"k": "c", "ev": 5.0}]
        self.assertEqual(P.keep_or_best(z, z[1], "a", key, margin=float("inf"))["k"], "a")   # locked, zero EV

    def test_no_ev_rows_never_kept(self):
        t = [{"k": "a", "p_first": 0.1}, {"k": "b", "p_first": 0.2}]
        self.assertEqual(P.keep_or_best(t, t[1], "a", lambda r: r["k"])["k"], "b")


@unittest.skipUnless(HAVE_NP, "needs numpy")
class Plans(unittest.TestCase):
    FIELD = [30000, 25000, 20000, 15000, 12000, 9000]

    def test_cfp_plan_with_prizes(self):
        best, table = P.cfp_plan(14000, self.FIELD, [0.55], weeks_left=2, rebuy_ok=False,
                                 payouts=[300, 100, 50], opp_profile={"wager_share_quantiles": {"p10": 0.5, "p50": 0.75, "p90": 1.0},
                                                                     "bets_per_week_mean": 4.85})
        self.assertEqual(len(table), 5)                                       # 1 side x 5 sizes
        self.assertTrue(all({"ev", "p_paid", "later"} <= set(r) for r in table))
        self.assertEqual(best["ev"], max(r["ev"] for r in table))
        self.assertGreater(best["ev"], 0)

    def test_cfp_plan_without_prizes_is_unchanged_shape(self):
        best, table = P.cfp_plan(14000, self.FIELD, [0.55], weeks_left=1, rebuy_ok=False)
        self.assertNotIn("ev", best)
        self.assertEqual(best["p_first"], max(r["p_first"] for r in table))

    def test_profile_rivals_bet_within_rules(self):
        wk = P.cfp_opp_week_from({"wager_share_quantiles": {"p10": 0.5, "p50": 0.75, "p90": 1.0}, "bets_per_week_mean": 4.85})
        bal = np.full((2000, 3), 10000.0)
        out = wk(bal, np.random.default_rng(1))
        self.assertTrue((out >= 0).all() and (out <= 20000).all())
        self.assertIs(P.cfp_opp_week_from({}), P.cfp_opp_week)

    def test_bto_plan_with_pot_and_keep(self):
        best, table = P.bto_plan(9200, [12200, 11000, 10000, 9000, 8000], [0.55, 0.52, 0.6], "normal", 3, pot=3675)
        self.assertTrue(all("ev" in r and r["later"] in ("cautious", "all-in") for r in table))
        self.assertEqual(best["ev"], max(r["ev"] for r in table))
        worst = min(table, key=lambda r: r["ev"])
        kept, _ = P.bto_plan(9200, [12200, 11000, 10000, 9000, 8000], [0.55, 0.52, 0.6], "normal", 3, pot=3675,
                             keep=(worst["frac"], worst["split"]))
        expect = worst if worst["ev"] * 1.07 >= best["ev"] else best
        self.assertEqual((kept["frac"], kept["split"]), (expect["frac"], expect["split"]))


@unittest.skipUnless(HAVE_NP, "needs numpy")
class CardHelpers(unittest.TestCase):
    T = [{"bets": 2, "frac": 1.0, "rebuy": False, "p_first": 0.05, "p_top3": 0.2, "ev": 160.0, "p_paid": 0.6},
         {"bets": 1, "frac": 1.0, "rebuy": False, "p_first": 0.09, "p_top3": 0.28, "ev": 176.0, "p_paid": 0.3},
         {"bets": 1, "frac": 0.75, "rebuy": False, "p_first": 0.07, "p_top3": 0.25, "ev": 150.0, "p_paid": 0.4}]

    def test_legal_plans_rank_by_prize_and_keep(self):
        best, alt = C.cfp_legal_plans(self.T, 23808, 11904)
        self.assertEqual((best["bets"], best["frac"]), (1, 1.0))
        best, _ = C.cfp_legal_plans(self.T, 23808, 11904, keep=(2, 1.0))           # 10% better: change
        self.assertEqual(best["bets"], 1)
        best, _ = C.cfp_legal_plans(self.T, 23808, 11904, keep=(2, 1.0), locked=True)
        self.assertEqual(best["bets"], 2)
        note = C.sizing_note(best, self.T, lambda r: f"{r['bets']} bet(s)", lambda r: (r["bets"], r["frac"]), locked=True)
        self.assertIn("locked", note)

    def _published(self, d, pool, rows):
        p = Path(d) / f"data/published/{C.YEAR}-w13-{pool}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows))

    def test_posted_size_and_lock(self):
        with tempfile.TemporaryDirectory() as d:
            old = C.ROOT
            C.ROOT = Path(d)
            try:
                self.assertIsNone(C.posted_size(13, "cfp", 23808, [0.5, 1.0]))
                self._published(d, "cfp", {"A@B": {"wager": "11,904"}, "C@D": {"wager": "11,904"}})
                self.assertEqual(C.posted_size(13, "cfp", 23808, [0.5, 0.75, 1.0]), (2, 1.0, "equal"))
                self._published(d, "bto", {"A@B": {"wager": "$1,840"}, "C@D": {"wager": "$3,680"}})
                self.assertEqual(C.posted_size(13, "bto", 5520, [0.5, 1.0]), (2, 1.0, "lean"))
                self.assertIsNone(C.posted_size(13, "bto", 20000, [0.5, 1.0]))   # 28% matches no size tried
                self._published(d, "bto", {k: {"wager": f"${w:,}"} for k, w in zip("ABCD", (1890, 1890, 1900, 1900))})
                self.assertEqual(C.posted_size(13, "bto", 7580, [0.5, 1.0]), (4, 1.0, "equal"))   # $10 rounding
                c = {"games": [{"away": "A", "home": "B", "kick": "Fri 11/27 11:00 AM CT"},
                               {"away": "X", "home": "Y", "kick": "Thu 11/26 7:00 PM CT"}]}
                self.assertFalse(C.cfp_locked(c, 13, datetime(2026, 11, 27, 10, 30, tzinfo=CT)))   # X@Y not posted
                self.assertTrue(C.cfp_locked(c, 13, datetime(2026, 11, 27, 11, 5, tzinfo=CT)))
                self.assertTrue(C.cfp_locked({**c, "deadline": "2026-11-27T09:00:00-06:00"}, 13,
                                             datetime(2026, 11, 27, 10, 0, tzinfo=CT)))
                # his saved picks (not the card) decide: saved only Saturday games -> still open Fri 11:05
                sat = {**c, "games": c["games"] + [{"away": "S", "home": "T", "kick": "Sat 11/28 2:30 PM CT"}],
                       "saved": {"bets": [{"key": "S@T"}]}}
                self.assertFalse(C.cfp_locked(sat, 13, datetime(2026, 11, 27, 11, 5, tzinfo=CT)))
            finally:
                C.ROOT = old

    def test_locked_cfp_card_is_held(self):
        with tempfile.TemporaryDirectory() as d:
            old = C.ROOT
            C.ROOT = Path(d)
            try:
                self._published(d, "cfp", {"A@B": {"wager": "11,904"}})
                posted = {"id": "cfp", "rows": [{"key": "A@B", "pick": "A +3", "pick_team": "A", "changed": True}],
                          "notes": ["n", "A @ B: Yahoo has B to win (60%); CFP takes A. Different questions: who wins vs who covers."]}
                (Path(d) / "data/cards.json").write_text(json.dumps({"meta": {"week": 13}, "cards": [posted]}))
                slate = {"cfp": {"games": [{"away": "A", "home": "B", "kick": "Fri 11/27 11:00 AM CT"}]}}
                fresh = [{"id": "cfp", "rows": [{"key": "X@Y", "pick": "X -14.5"}]}, {"id": "yahoo", "rows": []}]
                C.hold_locked_cfp(fresh, slate, 13, datetime(2026, 11, 27, 10, 0, tzinfo=CT))
                self.assertEqual(fresh[0]["rows"][0]["key"], "X@Y")                  # not locked yet: new card
                C.hold_locked_cfp(fresh, slate, 13, datetime(2026, 11, 27, 21, 0, tzinfo=CT))
                self.assertEqual(fresh[0]["rows"][0]["pick"], "A +3")                # locked: posted card kept
                self.assertNotIn("changed", fresh[0]["rows"][0])
                self.assertTrue(fresh[0]["status"].startswith("Locked"))
                self.assertEqual(fresh[0]["notes"], ["n"])                          # cross-pool note not doubled
                self.assertEqual(fresh[1]["id"], "yahoo")
            finally:
                C.ROOT = old


if __name__ == "__main__":
    unittest.main()
