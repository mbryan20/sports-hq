"""Our player values vs the market (shq/pv_data.py, pv_model.py, pv_train.py, pv_calls.py): features, guards, the ship test,
the decision value advice uses, trade ranking, value calls and rookie picks."""
import datetime as dt
import math
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from shq import draft_race, nfl_players, pv_calls, pv_data, pv_model, pv_score, pv_train, trades  # noqa: E402

NOV = dt.datetime(2026, 11, 20, 18, tzinfo=dt.timezone.utc)
GATE_OK = {"pass": True}


def model(ver="in", pos="QB", w=None, ok=True, shrink=1.0):
    return {"versions": {ver: {pos: {"w": w or [0.0, 0.5, 0.0], "shrink": shrink, "gate": {"pass": ok},
                                     "by_year": {"2022": {"cut": 0.1}, "2023": {"cut": 0.05}, "2024": {"cut": -0.01},
                                                 "2025": {"cut": 0.02}}}}}}


class Feats:
    """Stand-in for pv_model.Features: fixed features per sleeper id."""
    def __init__(self, by_sid, ver="in"):
        self.by, self.ver = by_sid, ver

    def of(self, sid):
        return self.by.get(sid)


QB_GOOD = {"g": 10, "ppg": 22.0, "tshare": 0.0, "epa_db": 0.30}


class Data(unittest.TestCase):
    def test_to_date_needs_three_games_and_forty_dropbacks(self):
        rows = [{"wk": w, "team": "SF", "ppr": 20.0, "ts": None, "db": 15, "epa": 3.0} for w in (1, 2, 3, 5)]
        self.assertIsNone(pv_data.to_date(rows, 2))
        f = pv_data.to_date(rows, 4)     # weeks 1-3 only: the week-5 game isn't read (no peeking ahead)
        self.assertEqual(f["g"], 3)
        self.assertAlmostEqual(f["epa_db"], 9.0 / 45)
        self.assertIsNone(pv_data.to_date([{**r, "db": 10} for r in rows], 3)["epa_db"])   # 30 dropbacks: too few

    def test_read_week_keeps_regular_season_skill_players(self):
        text = ("player_id,position,season_type,week,team,fantasy_points_ppr,target_share,attempts,sacks_suffered,passing_epa\n"
                "a,WR,REG,1,SF,12.5,0.25,0,0,0\nb,K,REG,1,SF,9,,,,\na,WR,POST,19,SF,30,0.4,0,0,0\n")
        out = pv_data.read_week(text)
        self.assertEqual(list(out), ["a"])
        self.assertEqual(out["a"][0]["ts"], 0.25)

    def test_fc_snapshot_once_a_day_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            old = pv_data.FC_HISTORY
            pv_data.FC_HISTORY = pathlib.Path(d)
            try:
                self.assertTrue(pv_data.save_fc_snapshot("2qb-12t-1ppr", {"1": 5000, "2027 1st": 2800}, NOV))
                b = (pathlib.Path(d) / "2026-11-20.json.gz").read_bytes()
                self.assertFalse(pv_data.save_fc_snapshot("2qb-12t-1ppr", {"1": 1}, NOV))   # first one of the day stays
                self.assertTrue(pv_data.save_fc_snapshot("2qb-10t-1ppr", {"1": 4900}, NOV))
                self.assertEqual(pv_data.load_fc_snapshot("2026-11-20", "2qb-12t-1ppr"), {"1": 5000, "2027 1st": 2800})
                self.assertNotEqual(b, (pathlib.Path(d) / "2026-11-20.json.gz").read_bytes())
            finally:
                pv_data.FC_HISTORY = old


class Model(unittest.TestCase):
    def test_versions_by_date(self):
        self.assertEqual(pv_model.version(NOV, 12), "in")
        self.assertEqual(pv_model.version(dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc), 3), "off")   # weeks 1-3
        self.assertEqual(pv_model.version(dt.datetime(2027, 1, 10, tzinfo=dt.timezone.utc), 18), "in")
        self.assertEqual(pv_model.version(dt.datetime(2027, 3, 1, tzinfo=dt.timezone.utc), 1), "off")
        self.assertEqual(pv_model.last_full_season(dt.datetime(2027, 3, 1)), 2026)
        self.assertEqual(pv_model.last_full_season(NOV), 2025)

    def test_call_edge_capped_and_live(self):
        m, st = model(w=[0.0, 5.0, 0.0]), {}
        c = pv_model.call(m, st, Feats({"q": QB_GOOD}), "QB", 6000, "q")
        self.assertEqual(c["edge"], pv_model.CAP)                       # +35% at most
        self.assertEqual(c["ours"], int(round(6000 * math.exp(0.35), -1)))
        self.assertTrue(c["live"] and c["capped"])
        self.assertIn("EPA per dropback +0.30", c["why"])
        self.assertIn("beat the market in 3 of the last 4 seasons", c["record"])
        self.assertIn("too new to score", c["record"])

    def test_guards_give_no_call(self):
        m, f = model(), Feats({"q": QB_GOOD})
        self.assertIsNone(pv_model.call(m, {}, f, "QB", 900, "q"))                    # under 1,000: market only
        self.assertIsNone(pv_model.call(m, {}, f, "QB", 6000, "q", status_tag="IR"))  # out for a while
        self.assertIsNone(pv_model.call(m, {}, f, "QB", 6000, "q", fill_in=True))      # backup / fill-in QB
        self.assertIsNone(pv_model.call(m, {}, Feats({}), "QB", 6000, "q"))            # too few games
        self.assertIsNone(pv_model.call(m, {}, f, "RB", 6000, "q"))                    # no RB model this version

    def test_drew_lock_case_fill_in_qb(self):
        fc = {"darnold": {"pos": "QB", "value": 5200}, "lock": {"pos": "QB", "value": 1100}, "jsn": {"pos": "WR", "value": 9000}}
        team = {"darnold": "SEA", "lock": "SEA", "jsn": "SEA"}.get
        self.assertEqual(pv_model.qb_fill_ins(fc, team), {"lock"})

    def test_failed_or_paused_position_is_not_live(self):
        f = Feats({"q": QB_GOOD})
        self.assertFalse(pv_model.call(model(ok=False), {}, f, "QB", 6000, "q")["live"])
        paused = {"paused": {"in:QB": "right on 12 of the last 30 calls"}}
        c = pv_model.call(model(), paused, f, "QB", 6000, "q")
        self.assertFalse(c["live"])
        self.assertIn("paused", c["record"])

    def test_decision_value_uses_ours_only_where_live(self):
        p = {"val": 5000, "pv": {"ours": 6000, "live": True, "edge": 0.18}}
        self.assertEqual(pv_model.dv(p), 6000)
        self.assertEqual(pv_model.dv({**p, "pv": {**p["pv"], "live": False}}), 5000)
        self.assertEqual(pv_model.dv(p, use="market"), 5000)                          # pick B
        self.assertEqual(pv_model.dv({"val": 5000, "pv": None}), 5000)

    def test_annotate_puts_calls_on_players(self):
        players = [{"sid": "q", "val": 6000, "positions": ["QB"]}, {"sid": "lock", "val": 1100, "positions": ["QB"]},
                   {"sid": "w", "val": 4000, "positions": ["WR"]}]
        fc = {"q": {"pos": "QB", "value": 6000}, "lock": {"pos": "QB", "value": 1100}, "w": {"pos": "WR", "value": 4000}}
        team = {"q": "SF", "lock": "SF", "w": "SF"}.get
        n = pv_model.annotate(players, fc, team, {}, NOV, 12, model=model(), status={},
                              feats=Feats({"q": QB_GOOD, "lock": QB_GOOD}))
        self.assertEqual(n, 1)
        self.assertIsNotNone(players[0]["pv"])
        self.assertIsNone(players[1]["pv"])      # fill-in behind a higher-valued QB
        self.assertIsNone(players[2]["pv"])      # no WR entry in this model

    def test_rookie_trial_never_live(self):
        m = {"rookie": {"WR": {"w": [0.0, -0.2, 0.0], "shrink": 1.0}}}
        c = pv_model.rookie_call(m, "WR", 3000, {"pick": 8, "round": 1}, math.log(2000), NOV)
        self.assertTrue(c["trial"])
        self.assertFalse(c["live"])
        self.assertGreater(c["edge"], 0)          # an early pick: the trial leans up
        self.assertEqual(pv_model.dv({"val": 3000, "pv": c}), 3000)


class Train(unittest.TestCase):
    def rows(self, years=range(2019, 2026), slope=0.3):
        out = []
        for y in years:
            a = dt.date(y, 10, 6)
            for i in range(40):
                s = (i - 20) / 10
                ch = slope * s + (0.02 if i % 2 else -0.02)
                out.append({"ver": "in", "pos": "WR", "year": y, "anchor": a, "end": a + dt.timedelta(days=365), "g": f"{y}{i}",
                            "age": 24, "v": 3000, "ch": ch, "x": [1.0, s, 0.0]})
        pv_train.relative(out)
        return out

    def test_walk_uses_only_rows_finished_before_the_test_year(self):
        seen = []
        orig = pv_train.fit

        def spy(train):
            seen.append(max(r["end"] for r in train))
            return orig(train)
        pv_train.fit = spy
        try:
            by = pv_train.walk(self.rows(), 2022)
        finally:
            pv_train.fit = orig
        self.assertEqual(sorted(by), [2022, 2023, 2024, 2025])
        self.assertTrue(all(d <= dt.date(2022, 10, 6) for d in seen[:1]))   # 2022's model: nothing ending after Oct 6, 2022
        self.assertGreater(by[2024]["cut"], 0.5)                           # a real signal is found

    def test_gate_needs_all_four_parts(self):
        good = {y: {"cut": 0.05, "n": 30, "calls": 8, "right": 6, "e0": 10.0, "e1": 9.5} for y in (2022, 2023, 2024, 2025)}
        self.assertTrue(pv_train.gate(good)["pass"])
        few = {y: {**d, "calls": 2, "right": 2} for y, d in good.items()}
        self.assertIn("big calls", pv_train.gate(few)["why"])
        wrong = {y: {**d, "right": 3} for y, d in good.items()}       # 12 of 32 right
        self.assertFalse(pv_train.gate(wrong)["pass"])
        three = {y: d for y, d in good.items() if y != 2022}
        self.assertIn("better in only", pv_train.gate(three)["why"])   # needs 4 test seasons

    def test_no_signal_no_ship(self):
        m = pv_train.train(self.rows(slope=0.0))
        self.assertFalse(m["versions"]["in"]["WR"]["gate"]["pass"])


def P(pid, name, pos, val, pv=None, team="SF", ppg=10.0):
    return {"id": pid, "name": name, "positions": [pos], "val": val, "pv": pv, "team": team, "ppg": ppg, "proj": ppg,
            "status": None, "bye": False, "started": False, "key": pid}


class Advice(unittest.TestCase):
    def test_trade_offers_rank_by_ours_but_stay_fair_by_market(self):
        slots = ["QB", "WR", "WR"]
        # my spare QB for their WR: both lineups improve, the values are within 10% by the market
        mine = [P("m1", "My QB", "QB", 6000, ppg=18), P("m2", "Spare QB", "QB", 5000, ppg=16), P("m3", "My WR", "WR", 1500, ppg=8),
                P("m4", "My WR2", "WR", 1400, ppg=7)]
        up = {"ours": 6600, "live": True, "edge": 0.2}
        theirs = [P("t1", "Their QB", "QB", 2000, ppg=10), P("t2", "Their WR", "WR", 5100, pv=up, ppg=14),
                  P("t3", "Their WR2", "WR", 900, ppg=13), P("t4", "Their WR3", "WR", 800, ppg=12)]
        found = trades.offers(slots, mine, [{"name": "Rival", "players": theirs}])
        top = found[0]
        self.assertEqual(top["get"], ["Their WR (WR)"])
        self.assertEqual(top["ours_gain"], 1500)
        self.assertIn("By our values you gain about 1,500", top["why"])
        self.assertLessEqual(abs(top["get_value"] - top["give_value"]) / max(top["get_value"], top["give_value"]), trades.TOLERANCE)

    def test_draft_pick_mode_uses_ours_where_live(self):
        fa = P("f", "Riser", "WR", 1100, pv={"ours": 1400, "live": True, "edge": 0.24})
        drop = P("d", "Vet", "WR", 1000)
        self.assertTrue(draft_race.keep_add({"fa": fa, "drop": drop}))     # 400 by ours
        fa["pv"]["live"] = False
        self.assertFalse(draft_race.keep_add({"fa": fa, "drop": drop}))    # 100 by the market

    def test_players_page_hides_failed_positions(self):
        class L:
            sport, platform, week, others = "nfl", "sleeper", 12, [{"name": "Rival", "players": []}]
            fc_settings = {"dynasty": True}
            starters = [dict(P("a", "Live QB", "QB", 7000, pv={"ours": 8000, "edge": 0.13, "why": "x", "record": "r",
                                                                 "live": True, "ver": "in"}), status=None),
                        dict(P("b", "Off RB", "RB", 5000, pv={"ours": 6000, "edge": 0.18, "why": "y", "record": "r",
                                                               "live": False, "ver": "in"}), status=None)]
            bench, free_agents = [], []
        orig = nfl_players.values.annotate
        nfl_players.values.annotate = lambda lg: True
        try:
            rows = {r["name"]: r for r in nfl_players.build(L)["players"]}
        finally:
            nfl_players.values.annotate = orig
        self.assertEqual(rows["Live QB"]["pv"]["e"], 14)
        self.assertNotIn("pv", rows["Off RB"])

    def test_value_calls_and_picks(self):
        live = lambda e: {"ours": 1, "edge": e, "live": True, "why": "target share 28%, 14.4 pts/g this season", "record": "r"}

        class L:
            starters = [P("s1", "Sell Me", "WR", 1526, pv={**live(-0.25), "ours": 1190})]
            bench = [P("s2", "Small", "WR", 1500, pv=live(-0.05))]
            others = [{"name": "Buttered Toast!", "players": [P("b1", "Brock Purdy", "QB", 6452, pv={**live(0.3), "ours": 8710})]}]
        buys, sells = pv_calls.calls(L)
        self.assertEqual([p["name"] for p, _ in buys], ["Brock Purdy"])
        self.assertEqual([p["name"] for p, _ in sells], ["Sell Me"])     # -5% is under the 10% bar
        self.assertTrue(pv_calls.line("Buy", buys[0][0], "Buttered Toast!").startswith(
            "Buy: Brock Purdy (Buttered Toast!): market 6,452, ours 8,710 (+35%). Target share"))

    def test_sleeper_picks_follow_trades(self):
        class L:
            settings, my_roster_id, rosters = {"draft_rounds": 2}, 1, [{"roster_id": 1}, {"roster_id": 2}]
            team_names = {1: "me", 2: "Rival"}
            key = "sleeper:1"
        traded = [{"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2},     # my 2027 1st went to Rival
                  {"season": "2027", "round": 2, "roster_id": 2, "owner_id": 1}]     # I got Rival's 2027 2nd
        picks = pv_calls.sleeper_picks(L, traded, seasons=[2027])
        self.assertEqual(picks, [(2027, 2, None), (2027, 2, "Rival")])
        L.race, L.team_count = {"pick": 2}, 12
        line = pv_calls.picks_line(L, [(2027, 1, None), (2027, 2, "Rival")],
                                   {"2027 1st (Early)": 4900, "2027 1st": 2850, "2027 2nd": 1570})
        self.assertIn("2027 1st (early) 4,900", line)
        self.assertIn("2027 2nd via Rival 1,570", line)
        self.assertIn("6,470 in all", line)


class Score(unittest.TestCase):
    def data(self, fc, pv=None):
        players = [{"id": str(i), "pos": "WR", "fc": v, **({"pv": pv[i]} if pv and i in pv else {})} for i, v in enumerate(fc)]
        return {"leagues": {"Domo Arigato": {"dynasty": True, "players": players}, "Kosmonauts": {"dynasty": False, "players": []}}}

    def test_log_weekly_in_season_only(self):
        tue = dt.datetime(2026, 11, 24, 9, tzinfo=dt.timezone.utc)
        self.assertTrue(pv_score.due(tue, dt.date(2026, 11, 23)))
        self.assertFalse(pv_score.due(dt.datetime(2026, 11, 25, tzinfo=dt.timezone.utc), dt.date(2026, 11, 24)))
        self.assertFalse(pv_score.due(dt.datetime(2027, 3, 3, tzinfo=dt.timezone.utc), None))     # March: no scoring
        with tempfile.TemporaryDirectory() as d:
            path = pv_score.log(tue, self.data([5000, 900]), pathlib.Path(d))
            self.assertEqual([r["id"] for r in pv_pick(path)["leagues"]["Domo Arigato"]], ["0"])   # 1,000+ only

    def test_score_against_the_same_position_and_pause(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            then = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
            up = {"e": 20, "live": True, "v": "in"}
            pv_score.log(then.replace(day=1), self.data([3000, 3000, 3000, 3000, 3000, 3000],
                                                         {0: up, 1: up, 2: {**up, "e": -20}, 3: {**up, "live": False}}), d)
            now = then + dt.timedelta(days=90)
            # everyone fell 20% but player 0 held: he beat his position; 1 fell most (call wrong); 2 fell most (sell right)
            out = pv_score.score(now, self.data([3000, 1800, 1800, 2400, 2400, 2400]), d)
            self.assertEqual(sorted(ok for _, ok in out["in:WR"]), [False, True, True])
            bad = {"in:WR": [("2026-09-01", False)] * 20 + [("2026-09-01", True)] * 10}
            st = pv_score.status(now, bad, old={})
            self.assertIn("in:WR", st["paused"])
            self.assertEqual(st["live"]["in:WR"], {"right": 10, "calls": 30})
            self.assertIn("in:WR", pv_score.status(now, {}, old=st)["paused"])     # stays paused until a review clears it


def pv_pick(path):
    import json
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
