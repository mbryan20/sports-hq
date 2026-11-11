"""Try a move (Q-054): docs/lib/move.js's football and basketball verdicts, and the War Room model's tryMove(),
run through Node with fixtures (skipped when Node isn't installed; CI runs them)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVE = ("const fs=require('fs'),vm=require('vm');const ctx=vm.createContext({console});"
        "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);ctx.F=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
        "console.log(JSON.stringify(vm.runInContext(process.argv[3],ctx)))")
MODEL = ("const fs=require('fs'),vm=require('vm');const ctx=vm.createContext({D:JSON.parse(fs.readFileSync(process.argv[2],'utf8'))});"
         "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);console.log(JSON.stringify(vm.runInContext(process.argv[3],ctx)))")


def node_or_skip(case):
    node = os.environ.get("NODE") or shutil.which("node")
    if not node:
        case.skipTest("node not installed")
    return node


def run(case, prog, src, data, expr):
    node = node_or_skip(case)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
    try:
        out = subprocess.run([node, "-e", prog, os.path.join(ROOT, *src), f.name, expr], check=True, capture_output=True,
                             text=True, encoding="utf-8", cwd=ROOT)
        return json.loads(out.stdout)
    finally:
        os.unlink(f.name)


def nfl(pid, pos, proj, nxt, own=None, ros=None, **kw):
    return {"id": pid, "name": pid.title(), "pos": pos, "team": "X", "own": own, "proj": proj, "next": nxt,
            "ros": ros if ros is not None else proj, "opp": "BYE" if nxt and nxt[0] is None else "vs Y", **kw}


SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "K"]


def league(*extra, dynasty=False):
    mine = [nfl("qb", "QB", 20, [20, 20, 20, 20], "me"), nfl("rb", "RB", 12, [12, 12, 12, 12], "me"),
            nfl("wr", "WR", 11, [11, 11, 11, 11], "me"), nfl("te", "TE", 8, [8, 8, 8, 8], "me"),
            nfl("wr2", "WR", 9, [9, 9, 9, 9], "me"), nfl("bench", "RB", 3, [3, 3, 3, 3], "me", ros=3),
            {"id": "k", "name": "K", "pos": "K", "team": "X", "own": "me", "proj": 0, "next": [], "ros": None, "opp": "BYE"}]
    return {"week": 10, "partial": False, "dynasty": dynasty, "players": mine + list(extra)}


class Football(unittest.TestCase):
    def js(self, data, expr):
        return run(self, MOVE, ("docs", "lib", "move.js"), data, expr)

    def test_lineup_fills_restrictive_slots_first(self):
        # a QB in the superflex only after the RB/WR/TE slots that only they can fill
        ps = [{"pos": "QB", "v": 20}, {"pos": "QB", "v": 15}, {"pos": "RB", "v": 10}, {"pos": "WR", "v": 9}]
        got = self.js(ps, "SHQ.move.lineupTotal(F, ['SUPER_FLEX','QB','RB','WR','FLEX'], p => p.v)")
        self.assertEqual(got, 54)

    def test_a_starter_upgrade_is_worth_it(self):
        L = league(nfl("fa", "WR", 16, [16, 16, 16, 16]))
        got = self.js(L, "const r = SHQ.move.nflEval(F, %s, ['fa'], ['bench']); [r.verdict, r.head, r.drops.map(x => x.id)]" % json.dumps(SLOTS))
        self.assertEqual(got[0], "worth")
        self.assertEqual(got[2], ["bench"])
        self.assertEqual(got[1], "+28.0 lineup pts over 4 weeks")   # 16 at WR, the 11 moves to FLEX over the 9: +7 a week

    def test_no_drop_picks_the_cheapest_and_a_bye_is_named(self):
        L = league(nfl("fa", "RB", 0, [None, 14, 14, 14], ros=14))
        r = self.js(L, "const r = SHQ.move.nflEval(F, %s, ['fa'], []); [r.verdict, r.drops.map(x => x.id), r.reasons.join(' ')]" % json.dumps(SLOTS))
        self.assertEqual(r[1], ["bench"])                   # the 3-point bench RB costs nothing (never the kicker on a bye)
        self.assertIn("bye week 10", r[2])
        self.assertIn("costs you least", r[2])

    def test_a_kicker_counts_this_week_only(self):
        L = league({"id": "k2", "name": "K2", "pos": "K", "team": "Y", "own": None, "proj": 8, "next": [], "ros": None, "opp": "vs Z"})
        r = self.js(L, "const r = SHQ.move.nflEval(F, %s, ['k2'], ['k']); [r.verdict, r.head]" % json.dumps(SLOTS))
        self.assertEqual(r, ["worth", "+8.0 lineup pts over 4 weeks"])   # not +32 from one week's number

    def test_bench_swap_comes_down_to_depth_and_yours_is_unavailable(self):
        L = league(nfl("fa", "RB", 4, [4, 4, 4, 4], ros=4.5))
        r = self.js(L, "SHQ.move.nflEval(F, %s, ['fa'], ['bench']).verdict" % json.dumps(SLOTS))
        self.assertEqual(r, "coin")                         # +1.5/gm depth, lineup unchanged
        r = self.js(L, "SHQ.move.nflEval(F, %s, ['wr'], []).verdict" % json.dumps(SLOTS))
        self.assertEqual(r, "unavailable")

    def test_dynasty_value_tempers_a_points_gain(self):
        L = league(nfl("fa", "WR", 16, [16, 16, 16, 16], fc=200), dynasty=True)
        L["players"][2]["fc"] = 3000                        # dropping a valuable young WR for points now
        r = self.js(L, "const r = SHQ.move.nflEval(F, %s, ['fa'], ['wr']); [r.verdict, r.reasons.join(' ')]" % json.dumps(SLOTS))
        self.assertEqual(r[0], "coin")
        self.assertIn("give up 2,800 of FantasyCalc value", r[1])

    def test_search_folds_accents_and_prefers_name_starts(self):
        ps = [{"id": "1", "name": "Luka Dončić", "own": "x"}, {"id": "2", "name": "KC Concepcion", "own": None}, {"id": "3", "name": "Kevin Love", "own": None}]
        self.assertEqual(self.js(ps, "SHQ.move.search(F, 'doncic').map(p => p.id)"), ["1"])
        self.assertEqual(self.js(ps, "SHQ.move.search(F, 'k').length"), 0)          # 2+ letters
        self.assertEqual(self.js(ps, "SHQ.move.search(F, 'conc').map(p => p.id)"), ["2"])


class Basketball(unittest.TestCase):
    """Same numbers as the Players page's trade check: value above waiver level, fit, dynasty."""
    L = {"cats": ["PTS", "REB"], "trade": {"weights": [1.5, 0.5], "dynasty": False, "ranks": [10, 2], "profiles": {"a": [], "b": []}},
         "players": [{"id": "m1", "name": "Mine One", "pos": "PG", "team": "A", "own": "me", "v": 2, "rk": 50, "above": 3, "wk": 6, "dyn": 3,
                      "z": [1, 1], "g": [2, 3], "min": 30, "inj": None},
                     {"id": "m2", "name": "Mine Two", "pos": "C", "team": "B", "own": "me", "v": -1, "rk": 120, "above": 0, "wk": -2, "dyn": 0,
                      "z": [0, 1], "g": [3, 3], "min": 20, "inj": None},
                     {"id": "fa", "name": "Free Agent", "pos": "SG", "team": "C", "own": None, "v": 3, "rk": 40, "above": 4, "wk": 12, "dyn": 4,
                      "z": [2, -1], "g": [3, 4], "min": 31, "inj": "OUT", "out": True}]}

    def js(self, data, expr):
        return run(self, MOVE, ("docs", "lib", "move.js"), data, expr)

    def test_swap_for_the_worst_player_by_default(self):
        r = self.js(self.L, "const r = SHQ.move.nbaEval(F, ['fa'], []); [r.verdict, r.drops.map(x => x.id), r.reasons.join(' ')]")
        self.assertEqual(r[0], "worth")
        self.assertEqual(r[1], ["m2"])                      # nothing above waiver level: dropped first
        self.assertIn("Helps PTS +2.0", r[2])
        self.assertIn("check the news", r[2])               # listed OUT

    def test_dynasty_decides_on_dynasty_value(self):
        L = json.loads(json.dumps(self.L))
        L["trade"]["dynasty"] = True
        L["players"][2]["dyn"] = 2.8                        # 2.8 for 3: within 0.5 -> coin flip
        self.assertEqual(self.js(L, "SHQ.move.nbaEval(F, ['fa'], ['m1']).verdict"), "coin")


class WarRoomTryMove(unittest.TestCase):
    """warroom/model.js tryMove(): the same simulation as the bids table, for any add and drop."""
    @staticmethod
    def league(cut=None):
        P = {}
        def pl(s, pos, pw, **kw):
            P[s] = {"n": s.title(), "p": pos, "t": "X", "a": pw[1], "r": pw[1], "g": 6, "own": 0, "bye": [], "pw": pw, "inj": "", "st": "ACT", **kw}
        mine = []
        for i, (pos, v) in enumerate([("QB", 18), ("RB", 12), ("RB", 11), ("WR", 12), ("WR", 11), ("WR", 10), ("TE", 8),
                                      ("K", 7), ("DEF", 7), ("RB", 9), ("WR", 9), ("TE", 4)]):
            pl(f"m{i}", pos, [v] * 4, own=1); mine.append(f"m{i}")
        pl("ace", "WR", [0, 18, 18, 18], bye=[9])           # better WR, on a bye this week
        pl("dud", "TE", [1, 1, 1, 1])
        pl("theirs", "RB", [20] * 4, own=2)
        rivals = {str(t): {"n": f"r{t}", "faab": 50, "roster": [f"x{t}{i}" for i in range(12)]} for t in (2, 3, 4)}
        for t in (2, 3, 4):
            for i, s in enumerate(rivals[str(t)]["roster"]):
                pl(s, ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "K", "DEF", "RB", "WR", "TE"][i], [10.5] * 4, own=t)
        rivals["2"]["roster"].append("theirs")
        D = {"me": 1, "week": 9, "last_week": 12, "P": P, "hist": [], "dead": {}, "cut": cut, "waivers": "Wed 2:15a CT",
             "ladder": {"lo": [0, 0, 0.5, 1, 1, 2], "hi": []}, "sd": {"measured": 20, "growth": 0},
             "teams": {"1": {"n": "me", "faab": 40, "roster": mine}, **rivals}}
        return D

    def js(self, D, expr):
        return run(self, MODEL, ("warroom", "model.js"), D, expr)

    def test_an_upgrade_is_worth_it_and_a_dud_is_not(self):
        D = self.league()
        got = self.js(D, "S.sims = 2000; const a = tryMove(['ace'], ['m11']), b = tryMove(['dud'], ['m6']);"
                         "[a.verdict, a.g1, a.weeks.length, a.adds[0].status, b.verdict, a.reasons.join(' ')]")
        self.assertEqual(got[0], "worth")
        self.assertEqual(got[1], 0)                          # his bye week: no change this week
        self.assertEqual(got[2], 4)
        self.assertEqual(got[3], "free")
        self.assertEqual(got[4], "not")
        self.assertIn("Ace: bye week 9", got[5])
        self.assertIn("free agent: add him now for $0", got[5])

    def test_rostered_player_is_unavailable_and_missing_drop_is_picked(self):
        D = self.league()
        got = self.js(D, "S.sims = 1000; const a = tryMove(['theirs'], []), b = tryMove(['ace'], []);"
                         "[a.verdict, a.adds[0].owner, b.adds[0].autoDrop, b.drops[0].id]")
        self.assertEqual(got[:2], ["unavailable", "r2"])
        self.assertTrue(got[2])
        self.assertEqual(got[3], "m11")                      # the 4-point third TE costs the fewest points

    def test_on_waivers_shows_price_and_win_chance(self):
        D = self.league({"roster": 4, "week": 8, "confirmed": True, "freed_status": "on waivers"})
        D["teams"]["4"]["roster"].append("ace")
        D["P"]["ace"]["own"] = 4
        got = self.js(D, "S.sims = 1000; S.dpp = 5; const r = tryMove(['ace'], ['m11']), a = r.adds[0];"
                         "[a.status, typeof a.price, typeof a.chance, a.call, r.open, r.reasons.join(' ')]")
        self.assertEqual(got[0], "waivers")
        self.assertEqual(got[1:3], ["number", "number"])
        self.assertIn(got[3], ("Bid", "Coin flip", "Priced out", "Skip"))
        self.assertTrue(got[4])
        self.assertIn("on waivers until Wed 2:15a CT", got[5])

    def test_two_moves_at_once(self):
        D = self.league()
        got = self.js(D, "S.sims = 1000; const r = tryMove(['ace', 'dud'], ['m11', '']); [r.adds.length, r.drops.length, new Set(r.drops.map(d => d.id)).size]")
        self.assertEqual(got, [2, 2, 2])                     # the model's pick for the second never reuses the first drop


if __name__ == "__main__":
    unittest.main()
