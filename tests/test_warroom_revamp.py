"""War Room revamp (Nov 12, Michael approved parts 1-3): rival-by-rival prices, backup claims on one drop (Sleeper's
copy rule), and his rules as hard checks (reserve, league-winners, marginal claims at $0, never drop a likely starter)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from warroom.build import rival_model


def run_js(D, expr):
    node = os.environ.get("NODE") or shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not installed")
    js = ("const fs=require('fs'),vm=require('vm');const ctx=vm.createContext({D:JSON.parse(fs.readFileSync(process.argv[1],'utf8')),Math,JSON,Object,Set,String});"
          "vm.runInContext(fs.readFileSync('warroom/model.js','utf8'),ctx);console.log(JSON.stringify(vm.runInContext(process.argv[2],ctx)))")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(D, f)
    try:
        return json.loads(subprocess.run([node, "-e", js, f.name, expr], check=True, capture_output=True, text=True).stdout)
    finally:
        os.unlink(f.name)


def league(players=None, roster=(), rival_faab=10, model=None, ladder=None, rules=None):
    """Weeks 9-12, my team (id 1, $10 FAAB) and one rival (id 2)."""
    P = {}
    for s, f in (players or {}).items():
        P[s] = {"n": s, "p": "RB", "t": "X", "a": 10, "r": 10, "g": 5, "own": 0, "bye": [], "pw": [10] * 4, **f}
    D = {"me": 1, "week": 9, "last_week": 12, "P": P, "hist": [], "dead": {}, "cut": None, "ladder": ladder,
         "teams": {"1": {"n": "me", "faab": 10, "roster": list(roster)}, "2": {"n": "rival", "faab": rival_faab, "roster": []}}}
    if model:
        D["rival_model"] = model
    if rules:
        D["rules"] = rules
    return D


# one rival who always claims and always bids half his money
HALF = {"n": 1, "q_base": 1.0, "q": {}, "shares": {"0": [0.5]}, "all": [0.5], "scale": {}, "cap": {}}


class FitRivalModel(unittest.TestCase):
    def test_fit_from_past_runs_without_michael(self):
        cases = [{"leg": 2, "targets": [["p1", 40], ["p2", 0]],
                  "D": {"teams": {"1": {"faab": 100}, "2": {"faab": 50}, "14": {"faab": 100}}, "cut": {"roster": 9}}}]
        got = [{"est": [20, 1], "rival": [{"base": 10, "needs": {"1": 7, "2": 0.5, "14": 3}},
                                          {"base": 5, "needs": {"1": 0, "2": 2, "14": 1}}]}]
        hist = [{"leg": 2, "sid": "p1", "bids": [[14, 40], [1, 30]]}]
        m = rival_model(cases, got, hist, 14)
        self.assertEqual(m["n"], 4)                                  # Michael (14) is never a rival in the fit
        self.assertEqual(m["q_base"], 0.25)                          # 1 claim in 4 rival-player chances
        self.assertEqual(m["q"]["0,3"], 0.5)                         # top target, big need: (1 + 2 x 0.25) / (1 + 2)
        self.assertEqual(m["shares"], {"0": [0.3]})                  # $30 of his $100


class RivalPrices(unittest.TestCase):
    def chance(self, faab, bids):
        D = league(model=HALF, rival_faab=faab)
        return run_js(D, f"const r = {{rk: 0, needs: {{'2': 10}}}}; {json.dumps(bids)}.map(b => winChance(b, 5, r))")

    def test_ties_lose_and_any_rival_claim_beats_zero(self):
        # the rival bids $5 of his $10: $5 ties (Michael is last in waiver order), $6 wins
        self.assertEqual(self.chance(10, [0, 5, 6]), [0, 0, 1])

    def test_a_broke_rival_only_beats_a_zero_claim(self):
        self.assertEqual(self.chance(0, [0, 1]), [0, 1])

    def test_who_can_outbid_is_listed(self):
        D = league(model=HALF, rival_faab=87)
        got = run_js(D, "rivalOdds({rk: 0, needs: {'2': 10}})")
        self.assertEqual([(x["t"], x["faab"], x["bid"]) for x in got], [("2", 87, 44)])   # half of $87, rounded up


class Calls(unittest.TestCase):
    def decide(self, q, players=None, row=None):
        model = dict(HALF, q_base=q, shares={"0": [1.0]}, all=[1.0])
        D = league(players=players or {"x": {}}, model=model, rival_faab=100)
        row = row or "{s: 'x', freed: true, dW: 0, dWin: 0.1, gR: 10, gNear: 10, est: 5, drop: 'a', th: [], rk: 0, needs: {'2': 10}}"
        return run_js(D, f"S.dpp = 1; const rows = [{row}]; decideAll(rows); [rows[0].call, rows[0].bid, rows[0].why]")

    def test_long_shot_is_named_honestly(self):
        call, bid, _ = self.decide(0.85)                             # 15% at any bid he'd make
        self.assertEqual((call, bid), ("Long shot", 0))

    def test_under_ten_percent_is_skipped(self):
        call, _, why = self.decide(0.95)
        self.assertEqual((call, why), ("Skip", "under 10% to win at any bid worth making"))

    def test_marginal_claims_go_in_at_zero(self):
        call, bid, why = self.decide(0.0, players={"x": {"p": "K"}})
        self.assertEqual((call, bid, why), ("Bid", 0, "marginal (K): $0 claim, your rule"))
        _, bid, why = self.decide(0.0, row="{s: 'x', freed: true, dW: 0, dWin: 0.1, gR: 4, gNear: 1.5, est: 5, drop: 'a', th: [], rk: 0, needs: {'2': 10}}")
        self.assertEqual((bid, why), (0, "marginal (+1.5 lineup pts a week): $0 claim, your rule"))

    def test_big_money_only_for_league_winners(self):
        # a rival with $100 who always claims at $10, $20, $30 or $90: worth $50 to Michael, who has $60. Without the line he'd
        # bid $21 (50%); anyone not on his list is capped at 25% of $60 = $15, so $11 (25%)
        model = dict(HALF, q_base=1.0, shares={"0": [0.1, 0.2, 0.3, 0.9]}, all=[0.9])
        row = "{s: 'x', freed: true, dW: 0, dWin: 0.5, gR: 10, gNear: 10, est: 5, drop: 'a', th: [], rk: 0, needs: {'2': 10}}"
        D = league(players={"x": {"n": "Puka Nacua"}}, model=model, rival_faab=100)
        D["teams"]["1"]["faab"] = 60
        capped = run_js(D, f"S.dpp = 1; const rows = [{row}]; decideAll(rows); [rows[0].bid, rows[0].why]")
        self.assertEqual(capped, [11, "capped at $15 (would bid $21): big money only for players you've named league-winners"])
        D["rules"] = {"league_winners": ["Puka Nacua"]}
        self.assertEqual(run_js(D, f"S.dpp = 1; const rows = [{row}]; decideAll(rows); rows[0].bid"), 21)


class Backups(unittest.TestCase):
    def test_second_claim_on_the_same_drop_is_a_backup_below_it(self):
        D = league(players={"A": {}, "B": {}}, ladder={"lo": [0, 0, 0, 0, 1, 1, 1], "hi": []})
        rows = ("[{s: 'A', freed: true, dW: 0, dWin: 0.05, gR: 10, gNear: 10, est: 5, drop: 'x', th: []},"
                "{s: 'B', freed: true, dW: 0, dWin: 0.04, gR: 10, gNear: 10, est: 5, drop: 'x', th: []}]")
        got = run_js(D, "S.dpp = 1; BASE = {}; bestDrop = () => null; gains = r => { r.dW = 0; r.dWin = r.s === 'A' ? 0.05 : 0.04; };"
                        f"const rows = {rows}; decideAll(rows);"
                        "claimList(rows).map(r => [r.s, r.call, r.bid, r.drop, r.chainOrder, r.firesIf || null])")
        self.assertEqual(got, [["A", "Bid", 0, "x", 1, None], ["B", "Backup", 0, "x", 2, ["A"]]])

    def test_worst_case_is_the_top_bid_of_each_chain(self):
        D = league(players={"A": {}, "B": {}, "C": {}})
        rows = ("[{s: 'A', freed: true, call: 'Bid', bid: 4, drop: 'x'}, {s: 'B', freed: true, call: 'Backup', bid: 2, drop: 'x'},"
                "{s: 'C', freed: true, call: 'Coin flip', bid: 1, drop: 'y'}]")
        got = run_js(D, f"const c = {{}}; for (const r of claimList({rows})) c[r.drop] = Math.max(c[r.drop] || 0, r.bid);"
                        "Object.values(c).reduce((a, b) => a + b, 0)")
        self.assertEqual(got, 5)


class StarterGuard(unittest.TestCase):
    def test_never_drops_this_weeks_starter_for_an_add_who_would_not_start(self):
        players = {"q": {"p": "QB"}, "r1": {}, "r2": {}, "te": {"p": "TE"}, "k": {"p": "K"}, "d": {"p": "DEF"},
                   **{f"w{i}": {"p": "WR"} for i in range(1, 6)},
                   "s1": {"pw": [11, 0, 0, 0]},          # starts in week 9 only
                   "b1": {"pw": [0, 10, 10, 10]},        # bench now, needed later
                   "nb": {"pw": [1, 1, 1, 1]}}           # the add: never starts
        roster = ["q", "r1", "r2", "te", "k", "d", "w1", "w2", "w3", "w4", "w5", "s1", "b1"]
        D = league(players=players, roster=roster)
        # dropping s1 costs the fewest points over the weeks, but he starts this week and the add wouldn't take his spot
        self.assertNotEqual(run_js(D, "bestDrop(ME, 'nb')"), "s1")


class Rules(unittest.TestCase):
    def test_reserve_comes_from_rules_json(self):
        self.assertEqual(run_js(league(rules={"reserve": 7}), "S.reserve"), 7)
        self.assertEqual(run_js(league(), "S.reserve"), 5)

    def test_rules_file_is_valid(self):
        with open("warroom/rules.json", encoding="utf-8") as f:
            r = json.load(f)
        self.assertTrue({"reserve", "release_reserve_at_cut_risk", "release_min_survival_gain", "league_winners",
                         "big_bid_share", "big_bid_min", "marginal_pts_per_week"} <= set(r))
        self.assertTrue(0 < r["release_reserve_at_cut_risk"] < 1)


class ConditionalReserve(unittest.TestCase):
    """Rule 13 (Michael, Nov 12): keep the reserve while he's likely to survive; when his cut risk this week is high,
    a claim that lowers it may spend the reserve. Only survival claims ever touch it."""
    # a rival with $10 who always claims, at $1-$9; the player is worth $50 to Michael ($10 FAAB, $5 reserve) and is
    # on his league-winner list so the big-bid line doesn't bind
    MODEL = dict(HALF, q_base=1.0, shares={"0": [i / 10 for i in range(1, 10)]}, all=[0.9])

    def bid(self, cut_risk, cut_drop):
        D = league(players={"x": {}}, model=self.MODEL, rival_faab=10, rules={"league_winners": ["x"]})
        row = (f"{{s: 'x', freed: true, dW: 0, dWin: 0.5, dCut: {cut_drop}, gR: 10, gNear: 10, est: 5, drop: 'a', th: [],"
               " rk: 0, needs: {'2': 10}}")
        return run_js(D, f"S.dpp = 1; BASE = {{sim: {{[ME]: {{pCut: {{[W0]: {cut_risk}}}}}}}}};"
                         f"const rows = [{row}]; const m = decideAll(rows); [rows[0].bid, !!rows[0].usesReserve, m.released]")

    def test_safe_keeps_the_reserve(self):
        self.assertEqual(self.bid(0.06, 0.05), [5, False, False])

    def test_high_risk_releases_it_for_a_claim_that_keeps_him_alive(self):
        self.assertEqual(self.bid(0.30, 0.05), [10, True, True])

    def test_high_risk_never_spends_it_on_a_claim_that_doesnt_help_survival(self):
        self.assertEqual(self.bid(0.30, 0.01), [5, False, True])


if __name__ == "__main__":
    unittest.main()
