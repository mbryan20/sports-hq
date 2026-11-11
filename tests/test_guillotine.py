"""Guillotine survival odds and bid guidance: lineups, the simulation, bid math, War Room v2's calls on the
league page (and the fallback), and the danger push."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import digest, guillotine as g

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 29, 13, 30, tzinfo=UTC)          # Thu 8:30am CDT
SUN = dt.datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
SLOTS = ["QB", "RB", "WR", "FLEX"]


def e(pid, pos, mean, sd=6.0, locked=False):
    return {"id": pid, "positions": [pos], "mean": mean, "sd": sd, "locked": locked}


class Ctx:
    """Just enough of leagues.Context for make_player: one team per player, every game Sunday."""
    def __init__(self, players, started=()):
        self.now, self.week, self.espn_inj = NOW, 8, {}
        self.espn_report, self.espn_by_name, self.week_start = {}, {}, None
        self.players = {pid: {"full_name": pid, "position": pos, "fantasy_positions": [pos], "team": team}
                        for pid, pos, team, _ in players}
        self.proj = {pid: {"stats": {"pts": proj}} for pid, _, _, proj in players}
        self.games = {team: {"kickoff": SUN, "state": "post" if team in started else "pre", "home": True, "opp": "X"}
                      for _, _, team, _ in players}


def roster(rid, owner, pids, starters):
    return {"roster_id": rid, "owner_id": owner, "players": pids, "starters": starters,
            "settings": {"waiver_budget_used": 200 - {1: 60, 2: 150, 3: 5}[rid]}}


class League:
    key, scoring, faab_budget, roster_slots, my_roster_id = "sleeper:1", {"pts": 1}, 200, SLOTS, 1
    free_agents = []
    users = [{"user_id": "me", "display_name": "michael"}, {"user_id": "b", "display_name": "Rich"},
             {"user_id": "c", "display_name": "Weak", "metadata": {"team_name": "Weak Sauce"}}]

    def __init__(self, rosters, matchups=()):
        self.rosters, self.matchups = rosters, list(matchups)


class Lineup(unittest.TestCase):
    def test_flex_takes_the_best_left_after_fixed_slots(self):
        pool = {p["id"]: p for p in [e("q", "QB", 20), e("r1", "RB", 15), e("r2", "RB", 12), e("w", "WR", 10)]}
        mean, sd = g.lineup(SLOTS, [], pool)
        self.assertEqual(mean, 57)           # QB 20 + RB 15 + WR 10 + FLEX RB 12
        self.assertAlmostEqual(sd, 12.0)     # four starters with SD 6

    def test_locked_starter_keeps_his_slot_and_bench_locked_cannot_play(self):
        pool = {p["id"]: p for p in [e("q", "QB", 20), e("r1", "RB", 3, sd=0, locked=True),
                                    e("r2", "RB", 12), e("w", "WR", 10), e("w2", "WR", 30, locked=True)]}
        mean, _ = g.lineup(SLOTS, ["q", "r1", "w", "r2"], pool)
        self.assertEqual(mean, 45)           # r1 is locked at RB with 3 real points; w2's game started on the bench

    def test_empty_slots_count_zero(self):
        mean, _ = g.lineup(SLOTS, [], {"q": e("q", "QB", 20)})
        self.assertEqual(mean, 20)


class Simulation(unittest.TestCase):
    def test_far_worse_team_is_almost_always_cut(self):
        z = g.draws(3, 2000, "t")
        odds = g.cut_odds([(130, 20), (128, 20), (60, 20)], z)
        self.assertGreater(odds[2], 0.98)
        self.assertAlmostEqual(sum(odds), 1.0)

    def test_equal_teams_split_the_risk(self):
        z = g.draws(4, 4000, "t")
        for p in g.cut_odds([(100, 20)] * 4, z):
            self.assertAlmostEqual(p, 0.25, delta=0.03)

    def test_same_seed_same_answer(self):
        self.assertEqual(g.draws(2, 10, "a"), g.draws(2, 10, "a"))

    def test_my_cut_matches_full_odds(self):
        stats = [(110, 20), (120, 20), (100, 20)]
        z = g.draws(3, 3000, "t")
        low = g.others_low(stats, z, 2)
        self.assertAlmostEqual(g.my_cut(100, 20, z, 2, low), g.cut_odds(stats, z)[2])
        self.assertLess(g.my_cut(115, 20, z, 2, low), g.my_cut(100, 20, z, 2, low))


class Bids(unittest.TestCase):
    def test_rival_bid(self):
        self.assertEqual(g.rival_bid(100, 0.5, "RB", 15), 0)       # doesn't help him
        self.assertEqual(g.rival_bid(0, 8, "RB", 15), 0)           # broke
        self.assertEqual(g.rival_bid(100, 6, "RB", 16), 25)        # full need, stud: 25% of $100
        self.assertEqual(g.rival_bid(100, 3, "RB", 11), 6)         # half need, half quality
        self.assertEqual(g.rival_bid(100, 9, "DEF", 16), g.KDEF_CAP)
        self.assertEqual(g.rival_bid(100, 6, "RB", 16, bold=0.6), 60)   # a rival who has gone big before

    def test_boldness_from_waiver_history(self):
        claim = lambda rid, leg, bid, status: {"type": "waiver", "status": status, "roster_ids": [rid], "leg": leg,
                                               "created": leg, "settings": {"waiver_bid": bid}}
        past = [claim(2, 1, 50, "complete"), claim(2, 3, 60, "failed"), claim(3, 2, 10, "failed"),
                {"type": "free_agent", "status": "complete", "roster_ids": [3], "leg": 2}]
        bold = g.boldness(past, 200)
        self.assertEqual(bold[2], 0.4)       # $60 of the $150 left after week 1's $50 win
        self.assertEqual(bold[3], 0.05)

    def test_my_max_keeps_a_reserve_and_rises_with_danger(self):
        self.assertEqual(g.RESERVE, 5)                             # War Room v2's default reserve
        self.assertEqual(g.my_max(4, 10, 0.5), 0)                  # all of it is reserve
        self.assertEqual(g.my_max(8, 10, 0.5, reserve=10), 0)
        self.assertGreater(g.my_max(10, 9, 0.1), 0)                # $10 with a $5 reserve leaves money to bid
        calm, scared = g.my_max(60, 3, 0.05), g.my_max(60, 3, 0.4)
        self.assertLess(calm, scared)
        self.assertLessEqual(g.my_max(60, 30, 0.9), 60 - g.RESERVE)

    def test_next_waivers_is_wednesday_215_ct(self):
        run = g.next_waivers(NOW)                                  # Thursday → next Wednesday
        self.assertEqual((run.weekday(), run.hour, run.minute, run.day), (2, 2, 15, 4))
        tue = dt.datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
        self.assertEqual(g.next_waivers(tue).day, 4)


class Analyze(unittest.TestCase):
    def setUp(self):
        players = [("mq", "QB", "KC", 20), ("mr", "RB", "BUF", 14), ("mw", "WR", "DAL", 12), ("mf", "RB", "SF", 9),
                   ("bq", "QB", "PHI", 24), ("br", "RB", "DET", 16), ("bw", "WR", "MIA", 15), ("bf", "WR", "CIN", 12),
                   ("cq", "QB", "NYJ", 12), ("cr", "RB", "NYG", 6), ("cw", "WR", "TEN", 5), ("cf", "WR", "CLE", 13),
                   ("fa", "WR", "LV", 14), ("fk", "WR", "NO", 4)]
        self.ctx = Ctx(players)
        self.lg = League([roster(1, "me", ["mq", "mr", "mw", "mf"], ["mq", "mr", "mw", "mf"]),
                          roster(2, "b", ["bq", "br", "bw", "bf"], ["bq", "br", "bw", "bf"]),
                          roster(3, "c", ["cq", "cr", "cw", "cf"], ["cq", "cr", "cw", "cf"]),
                          {"roster_id": 4, "owner_id": "x", "players": [], "starters": []}])  # already cut
        from shq.leagues import make_player
        self.lg.free_agents = [make_player(self.ctx, {"pts": 1}, pid, "FA") for pid in ("fa", "fk")]

    def test_odds_rank_and_bids(self):
        out = g.analyze(self.lg, self.ctx, NOW, sims=2000, past=[], v2={})
        self.assertEqual((out["n"], out["rank"], out["faab"]), (3, 2, 60))
        self.assertEqual(out["teams"][0]["name"], "Weak Sauce (Weak)")    # most at risk first; team name (username), Q-048
        self.assertGreater(out["teams"][0]["cut"], out["cut"])
        self.assertAlmostEqual(out["cut"] + out["survive"], 1.0)
        self.assertEqual([b["name"] for b in out["bids"]], ["fa"])  # fk adds nothing to my lineup
        b = out["bids"][0]
        self.assertEqual(b["gain"], 5.0)                           # 14 replaces the 9-point FLEX
        self.assertLess(b["cut_with"], out["cut"])
        self.assertEqual(out["freed"]["team"], "Weak Sauce (Weak)")
        self.assertEqual([r["name"] for r in out["rich"]], ["Rich", "Weak Sauce (Weak)"])
        self.assertEqual(out["waivers"], "Wed 2:15a")

    def test_final_games_use_real_points(self):
        self.ctx.games["KC"]["state"] = "post"
        self.lg.matchups = [{"players_points": {"mq": 2.0}}]
        from shq.leagues import make_player
        p = make_player(self.ctx, {"pts": 1}, "mq", "QB")
        p["started"] = True
        self.assertEqual(g.entry(p, self.ctx, {"mq": 2.0})["mean"], 2.0)
        self.assertEqual(g.entry(p, self.ctx, {"mq": 2.0})["sd"], 0.0)

    def test_one_team_left(self):
        self.lg.rosters = self.lg.rosters[:1]
        self.assertIsNone(g.analyze(self.lg, self.ctx, NOW, sims=100, past=[], v2={}))


def v2_fixture(week=8, run="2026-11-04T08:15:00Z", reserve=3):
    """A War Room v2 bids.json in its published shape (incl. the `raw` rival bids and a $0 Bid row)."""
    row = lambda name, call, bid, source, **k: {
        "sleeper_id": name, "name": name, "pos": "TE", "team": "PIT", "call": call, "bid": bid, "source": source,
        "drop": "cw", "why": k.get("why"), "win_chance": k.get("win"), "your_max": k.get("max", 0), "est_price": k.get("est", 0),
        "gain_next_week": k.get("gain", 9.1), "gain_rest_of_season": 11.0, "proj_next_week": 9.1, "injury": None,
        "likely_rival_bids": k.get("rivals", []), "bid_options": [], "value": 3}
    return {
        "week": week, "next_waiver_run": run, "reserve": reserve, "my_faab": 10, "data_as_of": "Week 7 final",
        "budget": {"spendable": 10 - reserve},
        "bids": [row("Warren", "Coin flip", 2, "freed", win=0.21, max=5, est=13, why=None,
                     rivals=[{"team": "damon", "bid": 16, "raw": 15.6}]),
                 row("Fannin", "Bid", 1, "freed", win=0.65, max=3),
                 row("Freiermuth", "Add free", 0, "free agent", why="free agent"),
                 row("Zero", "Bid", 0, "freed", win=0.4, why="nobody else needs him"),
                 row("Hockenson", "Priced out", 0, "freed", win=0.57, why="likely price is above his value to you"),
                 row("Higbee", "Skip", 0, "free agent", why="adds too little to matter")]}


class WarRoomV2(unittest.TestCase):
    """The league page shows War Room v2's calls when its bids.json is current; otherwise the model's own,
    with the same reserve and free agents as free adds."""
    setUp = Analyze.setUp

    def test_current_bids_json_replaces_the_model_bids(self):
        out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[], v2=v2_fixture())
        self.assertEqual(out["bid_source"]["name"], "War Room v2")
        self.assertEqual(out["bid_source"]["url"], "war-room-v2/")
        self.assertEqual(out["reserve"], 3)
        self.assertIsNone(out["freed"])
        self.assertEqual([b["name"] for b in out["model"]["bids"]], ["fa"])     # the model's own, kept aside
        by = {b["name"]: b for b in out["bids"]}
        self.assertEqual(list(by), ["Warren", "Fannin", "Freiermuth", "Zero", "Hockenson"])   # v2 order, no Skip
        self.assertEqual((by["Warren"]["call"], by["Warren"]["bid"], by["Warren"]["price"]), ("coin flip", 2, 2))
        self.assertEqual(by["Warren"]["rivals"], [{"name": "damon", "bid": 16}])
        self.assertEqual((by["Fannin"]["call"], by["Fannin"]["bid"], by["Fannin"]["win_chance"]), ("bid", 1, 0.65))
        self.assertEqual((by["Freiermuth"]["call"], by["Freiermuth"]["bid"], by["Freiermuth"]["free"]), ("add free", 0, True))
        self.assertEqual((by["Zero"]["call"], by["Zero"]["bid"]), ("bid", 0))   # a $0 claim, not dropped
        self.assertEqual(by["Hockenson"]["why"], "likely price is above his value to you")
        self.assertTrue(all(b["v2"] and b["drop"] == "cw" for b in out["bids"]))
        self.assertFalse(any(b["call"] == "priced out" and b["name"] == "Freiermuth" for b in out["bids"]))

    def test_live_team_wins_over_a_stale_bids_json_team(self):
        # Nov 10: bids.json (built 21:26Z) still said "Kirk Cousins, LV" after his trade to MIN that day
        v2 = v2_fixture()
        v2["bids"][2].update(sleeper_id="fa", team="KC")                # SHQ's live data has "fa" on LV
        out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[], v2=v2)
        by = {b["name"]: b for b in out["bids"]}
        self.assertEqual(by["Freiermuth"]["team"], "LV")
        self.assertEqual(by["Warren"]["team"], "PIT")                    # unknown to SHQ: v2's team stays
        self.assertEqual(g.v2_rows(v2)[2]["team"], "KC")
        self.assertEqual(out["waiting"], [])

    def test_stale_bids_json_falls_back_with_its_reserve(self):
        for v2 in (v2_fixture(week=7), v2_fixture(run="2026-10-28T08:15:00Z")):   # last week's / waivers already ran
            out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[], v2=v2)
            self.assertEqual(out["bid_source"], {"name": "dashboard model"})
            self.assertEqual(out["reserve"], 3)
            self.assertIsNone(out["model"])
            self.assertFalse(any(b.get("v2") for b in out["bids"]))

    def test_fallback_free_agent_is_a_free_add_and_freed_player_is_a_bid(self):
        out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[], v2={})
        self.assertEqual(out["reserve"], g.RESERVE)
        b = out["bids"][0]
        self.assertEqual((b["name"], b["call"], b["price"], b["max"], b["free"], b["rivals"]), ("fa", "add free", 0, 0, True, []))
        # a cut just freed "fa" and its waiver run hasn't happened: now it takes a FAAB claim
        chop = {"type": "chopped", "status": "complete", "drops": {"fa": 4}, "status_updated": NOW.timestamp() * 1000 - 3600e3}
        out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[chop], v2={})
        b = out["bids"][0]
        self.assertIn(b["call"], ("bid", "coin flip", "priced out"))
        self.assertGreater(b["price"], 0)
        self.assertNotIn("free", b)
        self.assertEqual(b["max"], g.my_max(60, b["gain"], out["cut"], g.RESERVE))

    def test_malformed_bids_json_falls_back(self):
        bad = v2_fixture()
        bad["bids"][0]["bid"] = "lots"
        out = g.analyze(self.lg, self.ctx, NOW, sims=500, past=[], v2=bad)
        self.assertEqual(out["bid_source"], {"name": "dashboard model"})
        self.assertEqual(out["bids"][0]["call"], "add free")

    def test_on_waivers_clears_after_the_run(self):
        at = NOW.timestamp() * 1000 - 3600e3
        chop = {"type": "chopped", "drops": {"a": 1, "b": 2}, "status_updated": at}
        self.assertEqual(g.on_waivers([chop], NOW), {"a", "b"})
        run = {"type": "waiver", "status": "complete", "status_updated": at + 1}
        self.assertEqual(g.on_waivers([chop, run], NOW), set())
        self.assertEqual(g.on_waivers([chop], NOW + dt.timedelta(days=8)), set())   # its Wednesday run is long past

    def test_load_v2_and_reserve(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bids.json"
            self.assertIsNone(g.load_v2(path))                     # missing
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(g.load_v2(path))
            path.write_text(json.dumps(v2_fixture()), encoding="utf-8")
            self.assertEqual(g.load_v2(path)["reserve"], 3)
        self.assertEqual(g.reserve_of(None), g.RESERVE)
        self.assertEqual(g.reserve_of({"reserve": 0}), 0)          # the last weeks: no reserve
        self.assertEqual(g.reserve_of({"reserve": "5"}), g.RESERVE)


class DangerPush(unittest.TestCase):
    class Lg:
        name, key, week = "Guillotine", "sleeper:1", 8

    def test_push_only_over_20_percent(self):
        lg = self.Lg()
        lg.standing = {"rank": 5, "n": 11, "gap": 12.0, "cut": 0.12}
        self.assertIsNone(digest.danger_push(lg))
        self.assertFalse(digest.standing_item(lg)["urgent"])
        lg.standing["cut"] = 0.31
        key, title, msg = digest.danger_push(lg)
        self.assertEqual(key, "sleeper:1:w8:cut-danger")
        self.assertIn("31% elimination risk", title)
        item = digest.standing_item(lg)
        self.assertTrue(item["urgent"])
        self.assertIn("31% chance of being cut", item["text"])


if __name__ == "__main__":
    unittest.main()
