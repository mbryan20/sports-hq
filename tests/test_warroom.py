"""War Room v2 data build: bid history by leg, confirmed vs projected cuts, freed players from an empty roster."""
import datetime as dt
import json
import os
import pathlib
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
        # the price calibration must not read this week's still-unclaimed players as "went for $0"
        self.assertNotIn(7, [c["leg"] for c in d["calib"]])

    def test_old_claim_of_a_freed_player_does_not_clear_waivers(self):
        # Nov 2-3: the cut team had won Jonathan Taylor in week 6; that old claim must not count as this
        # cut's waiver run (bids.json said "cleared" while Sleeper showed everyone on waivers until Wed)
        old = claim(3, "x2", 12, "complete", 5, 5)
        old["status_updated"] = CHOPPED_AT - 14 * 24 * 3600 * 1000
        wed_1am = dt.datetime(2026, 10, 28, 6, 0, tzinfo=dt.timezone.utc)
        d = model.build(wed_1am, self.nfl(), self.fetch([old]), players={})
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
                drops = [b["drop_id"] for b in out["bids"] if b["bid"] > 0]
                self.assertEqual(len(drops), len(set(drops)))            # Sleeper can't use one drop for two claims
                self.assertLessEqual(sum(b["bid"] for b in out["bids"]), out["budget"]["spendable"])
                self.assertEqual(out["freed_players"][0]["sleeper_id"], "x1")
            else:
                self.assertEqual((x1["source"], x1["est_price"], x1["your_max"]), ("free agent", 0, 0))
                self.assertIn(x1["call"], ("Add free", "Skip"))
                self.assertEqual(out["freed_players"], [])



class Calibration(unittest.TestCase):
    """The settings the model measures from league history instead of guessing (tested Nov 3 2026)."""
    def test_swing_is_the_spread_of_misses_after_each_weeks_shift(self):
        pos = lambda s: "QB"
        proj = {w: {"a": 20, "b": 20, "c": 20} for w in (1, 2)}
        # every team misses by the same amount in a week: that's a league-wide shift, not swing
        same = {w: [{"players": [s], "points": 30} for s in "abc"] for w in (1, 2)}
        self.assertEqual(model.measure_sd(same, proj, pos)[1], 6)          # too few team-weeks to trust
        many = {w: [{"players": ["a"], "points": 20 + d} for d in (-10, 10)] for w in range(1, 12)}
        sd, n = model.measure_sd(many, {w: {"a": 20} for w in range(1, 12)}, pos)
        self.assertEqual((sd, n), (10.0, 22))

    def test_price_ladder_splits_big_estimates(self):
        from warroom.build import ladder
        cases = [{"targets": [["a", 0], ["b", 10], ["c", 40]] + [[f"x{i}", 30] for i in range(12)]}]
        got = [{"est": [1, 5, 20] + [20] * 12}]
        lad = ladder(cases, got)
        self.assertEqual(lad["lo"], [0.0, 2.0])
        self.assertEqual(len(lad["hi"]), 13)
        self.assertEqual(lad["hi"][-1], 2.0)
        self.assertEqual(ladder(cases[:1], [{"est": [1, 5, 20] + [5] * 12}])["hi"], [])   # under 12 big ones: one ladder


class BidRules(unittest.TestCase):
    """Win chance from the ladder, and the bid that balances it against value (run through Node)."""
    def run_js(self, D, expr):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        js = ("const fs=require('fs'),vm=require('vm');const ctx=vm.createContext({D:JSON.parse(fs.readFileSync(process.argv[1],'utf8')),Math,JSON,Object,Set,String});"
              "vm.runInContext(fs.readFileSync('warroom/model.js','utf8'),ctx);console.log(JSON.stringify(vm.runInContext(process.argv[2],ctx)))")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(D, f)
        try:
            return json.loads(subprocess.run([node, "-e", js, f.name, expr], check=True, capture_output=True, text=True).stdout)
        finally:
            os.unlink(f.name)

    def test_win_chance_and_price(self):
        D = {"me": 1, "week": 9, "last_week": 10, "teams": {"1": {"n": "me", "faab": 50, "roster": []}}, "P": {}, "hist": [], "dead": {},
             "cut": None, "ladder": {"lo": [0, 0, 0.5, 1, 1, 2, 3, 4], "hi": []}}
        # estimate $10: past claims went for 0, 0, 5, 10, 10, 20, 30, 40
        self.assertEqual(self.run_js(D, "[winChance(0, 10), winChance(1, 10), winChance(11, 10), winChance(41, 10)]"), [0.25, 0.25, 0.625, 1])
        self.assertEqual(self.run_js(D, "[priceFor(.5, 10), priceFor(.8, 10)]"), [11, 31])

    # ---- Nov 10 review fixes (Q-038 to Q-041) ----
    @staticmethod
    def league(ladder, roster=(), players=None):
        """Weeks 9-12, my team (id 1, $10 FAAB) and one rival; players: id -> fields (pw = projections from week 9)."""
        P = {}
        for s, f in (players or {}).items():
            P[s] = {"n": s, "p": "RB", "t": "X", "a": 10, "r": 10, "g": 5, "own": 0, "bye": [], "pw": [10] * 4, **f}
        return {"me": 1, "week": 9, "last_week": 12, "P": P, "hist": [], "dead": {}, "cut": None, "ladder": ladder,
                "teams": {"1": {"n": "me", "faab": 10, "roster": list(roster)}, "2": {"n": "rival", "faab": 10, "roster": []}}}

    def test_zero_dollar_bid_keeps_its_payoff(self):
        # Barkley, Nov 10: 57% at both $0 and $1, value $3 -> $0 (worth $1.71) beats $1 ($1.14)
        D = self.league({"lo": [0, 0, 0, 0, 1, 1, 1], "hi": []}, players={"x": {}})
        row = "{s: 'x', freed: true, dW: 0, dWin: 0.03, gR: 1, est: 5, drop: 'a', th: []}"
        got = self.run_js(D, f"S.dpp = 1; const rows = [{row}]; decideAll(rows); [rows[0].call, rows[0].bid, rows[0].options.map(o => o.bid)]")
        self.assertEqual(got[:2], ["Bid", 0])
        self.assertIn(0, got[2])
        # when $1 does beat more past claims than $0, it is still chosen
        D["ladder"]["lo"] = [0, 0, 0.1, 0.1, 1, 1]
        got = self.run_js(D, f"S.dpp = 1; const rows = [{row}]; decideAll(rows); [rows[0].call, rows[0].bid]")
        self.assertEqual(got, ["Bid", 1])

    def test_rival_bids_on_the_win_chance_scale(self):
        D = self.league({"lo": [0.5, 0.5, 1, 1], "hi": []})
        got = self.run_js(D, "rivalBids({th: [{t: '2', bid: 18}], est: 19})")
        self.assertEqual(got, [{"t": "2", "bid": 9, "raw": 18}])            # half of past claims went for <= $10 of a $19 guess
        D["ladder"] = None
        self.assertEqual(self.run_js(D, "rivalBids({th: [{t: '2', bid: 18}], est: 19})"), [{"t": "2", "bid": 18, "raw": 18}])

    def test_out_now_is_never_a_free_add(self):
        D = self.league(None, players={"lj": {"p": "QB", "inj": "Out", "st": "RES", "pw": [0, 10, 10, 10]},
                                       "bye": {"bye": [9], "pw": [0, 10, 10, 10]}})
        got = self.run_js(D, "S.dpp = 1; const rows = [{s: 'lj', freed: false, dW: 0.1, dWin: 0.05, gR: 30, drop: 'a'},"
                             "{s: 'bye', freed: false, dW: 0.1, dWin: 0.05, gR: 30, drop: 'b'}]; decideAll(rows); rows.map(r => r.call)")
        self.assertEqual(got, ["Skip", "Add free"])                         # on a bye is not out

    def test_k_or_def_add_keeps_a_usable_rb(self):
        players = {f"r{i}": {"pw": [15] * 4} for i in range(1, 5)}
        players.update({"bh": {"a": 11.9, "pw": [8.1] * 4}, "cin": {"p": "DEF", "pw": [6.6] * 4}, "kk": {"p": "K", "pw": [7] * 4},
                        "min": {"p": "DEF", "pw": [7] * 4}, "rb9": {"pw": [9] * 4}})
        D = self.league(None, roster=["r1", "r2", "r3", "r4", "bh", "cin", "kk"], players=players)
        # bench RB and the old DEF both cost 0 lineup points; the RB is first, so he went before (Breece Hall, Nov 10)
        self.assertEqual(self.run_js(D, "[bestDrop(ME, 'min'), bestDrop(ME, 'rb9')]"), ["cin", "bh"])

    def test_no_paid_def_while_a_better_def_is_free(self):
        D = self.league({"lo": [0, 0, 0, 0, 1, 1, 1], "hi": []},
                        players={"min": {"p": "DEF"}, "bal": {"p": "DEF", "n": "BAL DEF"}})
        got = self.run_js(D, "S.dpp = 1; const rows = [{s: 'min', freed: true, dW: 0, dWin: 0.02, gR: 5, est: 2, drop: 'cin', th: []},"
                             "{s: 'bal', freed: false, dW: 0, dWin: 0.03, gR: 8, drop: 'cin'}]; decideAll(rows);"
                             "[rows[0].call, rows[0].bid, rows[0].why, rows[1].call]")
        self.assertEqual(got, ["Skip", 0, "BAL DEF is a free add and helps as much", "Add free"])


class PageText(unittest.TestCase):
    """A `${...}` inside a '...' or "..." string is printed as is ("Wk ${W0} proj" on the page, Nov 10)."""

    def test_no_template_in_plain_quotes(self):
        import re
        src = (pathlib.Path(__file__).resolve().parent.parent / "warroom" / "app.js").read_text(encoding="utf-8")
        # the page builds each table as `let h = ...;` on one line: a '...' one there must not hold ${
        bad = [ln.strip()[:70] for ln in src.splitlines() if re.match(r"\s*(let|const|var) \w+ = '", ln) and "${" in ln]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
