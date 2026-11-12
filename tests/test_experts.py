"""Q-052: ESPN experts' consensus ranks (shq/experts.py): compacting ESPN's feed, position ranks and parked (bye/out)
players, matching players across ESPN/Sleeper/Yahoo, labels, the 3-hour cache that never fails a run, the "where we
disagree" list, the league block, the pairs backtest, the Players page fields and the nightly health check. Fixtures
only, no network."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from shq import experts, health, nfl_players, values

L = "Ann Bob Cal Dan Eli Fay Gus".split()
NOW = dt.datetime(2026, 11, 12, 18, 0, tzinfo=dt.timezone.utc)


def espn_player(pid, name, pos_id, team_id, weeks):
    """weeks: {week: [expert ranks]} -> one kona_player_info entry (plus ESPN's own averaged row, which is skipped)."""
    rk = {str(w): [{"rank": r, "rankSourceId": i + 3, "rankType": "PPR"} for i, r in enumerate(rs)]
                  + [{"rank": 0, "averageRank": 99.0, "rankSourceId": 0, "rankType": "PPR"},
                     {"rank": 1, "rankSourceId": 7, "rankType": "STANDARD"}]
          for w, rs in weeks.items()}
    return {"player": {"id": pid, "fullName": name, "defaultPositionId": pos_id, "proTeamId": team_id, "rankings": rk}}


def feed():
    """Week 9 and 10 ranks for 8 WRs, 3 RBs; the last WR is parked at the bottom in week 10 (on a bye)."""
    wr = [espn_player(100 + i, f"Wr {L[i]}", 3, 6, {9: [i + 1] * 4, 10: [i + 1] * 4}) for i in range(7)]
    wr.append(espn_player(200, "Parked Guy", 3, 12, {9: [2, 2, 3, 3], 10: [60, 61, 62, 63]}))
    rb = [espn_player(300, "Rb One", 2, 6, {9: [1, 1, 1], 10: [1, 2, 1]}),
          espn_player(301, "Rb Two", 2, 6, {9: [3, 3, 3], 10: [3, 3, 3]}),
          espn_player(302, "Rb Thin", 2, 6, {10: [2, 2]})]                     # only 2 experts: not ranked
    return {"players": wr + rb + [{"player": {"id": 9, "fullName": "Kicker", "defaultPositionId": 5}}]}


def pl(pid, name, pos, proj, slot="BN", **kw):
    return {"id": pid, "key": kw.pop("key", None), "name": name, "positions": [pos], "team": kw.pop("team", "DAL"),
            "proj": proj, "slot": slot, "status": kw.pop("status", None), "bye": kw.pop("bye", False),
            "started": False, "kickoff": NOW + dt.timedelta(days=3), "empty": False, **kw}


class Ctx:
    def __init__(self, ranks, week=10):
        self.week, self.now, self._experts = week, NOW, ranks


class League:
    sport, platform = "nfl", "sleeper"

    def __init__(self, ctx, starters, bench, fas, others=()):
        self.ctx, self.week, self.starters, self.bench, self.free_agents = ctx, ctx.week, starters, bench, fas
        self.others = list(others)


class Compact(unittest.TestCase):
    def test_compact_averages_experts_and_skips_espn_average_and_thin(self):
        c = experts.compact(feed())
        self.assertEqual(c["players"]["200"], ["Parked Guy", "WR", "KC"])
        self.assertNotIn("9", c["players"])                                   # kickers aren't in this feed
        self.assertEqual(c["weeks"]["9"]["200"], [2.5, 2, 3, 4])              # avg, best, worst, experts
        self.assertEqual(c["weeks"]["10"]["300"], [1.33, 1, 2, 3])
        self.assertNotIn("302", c["weeks"]["10"])                             # 2 experts < MIN_EXPERTS

    def test_position_ranks_and_parked_players(self):
        c = experts.compact(feed())
        ranks, idle = experts.position_ranks(c["weeks"]["10"], c["players"])
        self.assertEqual((ranks["100"], ranks["106"], ranks["200"]), (1, 7, 8))
        self.assertEqual(idle, {"200"})                 # bottom 15% of each list, rounded down: 1 of 8 WRs, 0 of 2 RBs

    def test_ranks_of_this_week_lately_and_labels(self):
        c = experts.compact(feed())
        r = experts.Ranks(c, 10, {"s1": {"espn_id": 102}})
        x = r.of({"id": "s1", "name": "Somebody Else", "positions": ["WR"]})          # Sleeper's espn_id
        self.assertEqual((x["pos"], x["wk"], x["lately"], x["n"]), ("WR", 3, 4, 4))   # week 9: Parked Guy ranked 3rd
        self.assertEqual(experts.label(x), "WR3 this week, WR4 lately")
        parked = r.of({"id": "espn200", "key": 200, "name": "x", "positions": ["WR"]})  # ESPN league id
        self.assertTrue(parked["idle"])
        self.assertIsNone(parked["wk"])
        self.assertEqual(experts.label(parked), "not ranked to play this week, WR3 lately")
        by_name = r.of({"id": "yahoo1", "name": "Wr Eli", "positions": ["WR"], "team": "DAL"})
        self.assertEqual(by_name["wk"], 5)
        self.assertIsNone(r.of({"id": "?", "name": "Nobody", "positions": ["WR"]}))
        r11 = experts.Ranks(c, 11)
        self.assertFalse(r11.published)
        self.assertEqual(experts.label(r11.of({"id": "?", "name": "Wr Ann", "positions": ["WR"]})),
                         "WR1 lately (this week's ranks aren't out yet)")


class Lately(unittest.TestCase):
    def test_injured_weeks_skipped(self):
        """WR10-12 for three weeks, then ranked WR100 while hurt: lately stays WR11, not WR100."""
        players = {str(i): [f"Filler {i}", "WR", "DAL"] for i in range(130)}
        players["x"] = ["Hurt Guy", "WR", "DAL"]
        weeks = {}
        for w, rk in ((4, 10), (5, 12), (6, 11), (7, 100), (8, 100)):
            rows = {str(i): [i + (1 if i >= rk - 1 else 0) + 0.0, 1, 1, 4] for i in range(130)}
            rows["x"] = [rk - 0.5, 1, 1, 4]
            weeks[str(w)] = rows
        r = experts.Ranks({"players": players, "weeks": weeks}, 9)
        x = r.of({"id": "?", "name": "Hurt Guy", "positions": ["WR"]})
        self.assertEqual(x["lately"], 11)


class Cache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "exp.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_fresh_cache_is_used_then_refreshed_after_max_age(self):
        calls = []

        def get(url, params=None, **kw):
            calls.append(kw["headers"]["X-Fantasy-Filter"])
            self.assertNotIn("@", url + str(params) + str(kw))         # nothing personal in the request
            return feed()
        d = experts.load(2026, 1, 10, now=1000.0, get=get, path=self.path)
        self.assertEqual(len(calls), 1)
        self.assertIn('"filterRanksForScoringPeriodIds": {"value": [4, 5, 6, 7, 8, 9, 10]}', calls[0])
        experts.load(2026, 1, 10, now=1000.0 + experts.MAX_AGE - 1, get=get, path=self.path)
        self.assertEqual(len(calls), 1)
        experts.load(2026, 1, 10, now=1000.0 + experts.MAX_AGE + 1, get=get, path=self.path)
        self.assertEqual(len(calls), 2)
        self.assertEqual(d["week"], 10)

    def test_espn_down_uses_old_cache_then_none_never_raises(self):
        def ok(url, params=None, **kw):
            return feed()

        def down(url, params=None, **kw):
            raise ConnectionError("ESPN down")
        experts.load(2026, 1, 10, now=0.0, get=ok, path=self.path)
        d = experts.load(2026, 1, 10, now=1e9, get=down, path=self.path)
        self.assertIn("200", d["players"])
        self.assertIsNone(experts.load(2026, 1, 10, now=0.0, get=down, path=Path(self.dir.name) / "none.json"))


class LeaguePage(unittest.TestCase):
    def ranks(self, week=10):
        return experts.Ranks(experts.compact(feed()), week)

    def league(self, ranks):
        starters = [pl("a", "Wr Gus", "WR", 9.0, "WR"), pl("b", "Rb Two", "RB", 10.0, "RB")]
        bench = [pl("c", "Wr Ann", "WR", 8.0)]                         # experts: WR1, we keep Wr Gus (WR7)
        fas = [pl("d", "Wr Bob", "WR", 7.5, "FA"), pl("e", "Wr Cal", "WR", 7.0, "FA")]
        return League(Ctx(ranks), starters, bench, fas)

    def test_disagreements_show_both_numbers_once_per_starter(self):
        experts.BIG["WR"] = 3   # small fixture lists
        try:
            lg = self.league(self.ranks())
            experts.annotate(lg, lg.ctx._experts)
            lines = experts.disagreements(lg)
        finally:
            experts.BIG["WR"] = 10
        self.assertEqual(lines[0], "Experts would start Wr Ann (WR1) over your Wr Gus (WR7) at WR; we keep Wr Gus: 9.0 vs 8.0 projected.")
        fa = [t for t in lines if t.startswith("Free agent")]
        self.assertEqual(fa, ["Free agent Wr Bob (DAL) is WR2 with the experts this week, ahead of your starter Wr Gus (WR7); we project 7.5 vs 9.0."])

    def test_our_move_against_the_experts(self):
        experts.BIG["WR"] = 3
        try:
            lg = self.league(self.ranks())
            experts.annotate(lg, lg.ctx._experts)
            s, b = lg.starters[0], lg.bench[0]
            # we'd start Wr Gus (WR7) over Wr Ann (WR1) if the roles were swapped
            lines = experts.disagreements(League(lg.ctx, [b], [s], []), moves=[(b, s, 1.0)])
        finally:
            experts.BIG["WR"] = 10
        self.assertEqual(lines, ["We say start Wr Gus over Wr Ann (9.0 vs 8.0 projected); experts rank Wr Ann WR1, Wr Gus WR7."])

    def test_block_names_for_advice_lines_and_unpublished_week(self):
        lg = self.league(self.ranks())
        b = experts.block(lg, ["Add Wr Cal (WR, DAL) for Rb Two"])
        self.assertEqual(b["names"]["Wr Cal"], "WR3 this week, WR4 lately")
        self.assertIn("Rb Two", b["names"])                          # my roster is always tagged
        self.assertNotIn("Wr Bob", b["names"])                         # a free agent no line names isn't
        self.assertTrue(b["published"])
        self.assertIn("Sleeper's projections", b["basis"])
        self.assertIn("only by a number, not a name", b["basis"])   # Michael asked which experts: say plainly ESPN doesn't name them
        lg11 = self.league(self.ranks(11))
        lg11.ctx.week = 11
        b11 = experts.block(lg11, [])
        self.assertFalse(b11["published"])
        self.assertEqual(b11["disagree"], [])
        self.assertIn("aren't out yet", b11["basis"])

    def test_no_ranks_no_block(self):
        lg = self.league(None)
        self.assertIsNone(experts.block(lg, []))
        self.assertEqual(experts.extra_names(lg, ["Wr Bob"]), {})

    def test_extra_names_for_guillotine_bids(self):
        lg = self.league(self.ranks())
        self.assertEqual(experts.extra_names(lg, ["Wr Dan", None, "Nobody"]), {"Wr Dan": "WR4 this week, WR5 lately"})

    def test_players_page_fields(self):
        lg = self.league(self.ranks())
        experts.annotate(lg, lg.ctx._experts)
        saved = values.annotate
        values.annotate = lambda league: False
        try:
            rows = {r["name"]: r for r in nfl_players.build(lg)["players"]}
        finally:
            values.annotate = saved
        self.assertEqual((rows["Wr Ann"]["exp_wk"], rows["Wr Ann"]["exp_lately"], rows["Wr Ann"]["exp_range"]), (1, 1, [1, 1, 4]))


class Backtest(unittest.TestCase):
    def test_pairs_accuracy(self):
        rows = [{"pos": "WR", "rk": i, "proj": p, "pts": a}
                for i, (p, a) in enumerate([(20, 30), (18, 10), (16, 25), (14, 5), (12, 8)], 1)]
        res = experts.pairs_accuracy({9: rows})
        self.assertEqual(res["n"], 10)
        # Sleeper and the experts order these the same way, so they agree; 8 of 10 pairs have the higher scorer first
        self.assertEqual((res["sleeper"], res["experts"]), (0.8, 0.8))
        self.assertEqual(res["edge"], round(res["blend"] - res["sleeper"], 4))

    def test_backtest_rows_skip_parked_and_unplayed(self):
        c = experts.compact(feed())
        db = {"s0": {"full_name": "Wr Ann", "position": "WR"}, "s200": {"full_name": "Parked Guy", "position": "WR"},
              "s1": {"full_name": "Wr Bob", "position": "WR", "espn_id": 101}}
        proj = {"s0": {"pts_half_ppr": 15.0}, "s200": {"pts_half_ppr": 0.0}, "s1": {"pts_half_ppr": 12.0}}
        stats = {"s0": {"gp": 1, "pts_half_ppr": 20.0}, "s1": {"gp": 0}}
        rows = experts.backtest_rows(c, 10, proj, stats, db)
        self.assertEqual([(r["sid"], r["rk"], r["proj"], r["pts"]) for r in rows], [("s0", 1, 15.0, 20.0)])


class Health(unittest.TestCase):
    def test_our_calls_from_lineups_history(self):
        kick = dt.datetime(2026, 11, 5, 1, 15, tzinfo=dt.timezone.utc)      # Thursday night game, week 10
        lock = health.sunday_lock(kick)
        versions = [(lock - 100, "old"), (lock + 100, "late")]
        docs = {"old": {"week": 10, "leagues": {"Stempak": {"advice": {"moves": ["Start A B (6.9) over C D (13.3) at FLEX, +1.0",
                                                                                  "Add someone"]}}}}}
        calls = health.our_calls([10], {10: kick}, versions, lambda sha, path: docs[sha])
        self.assertEqual(calls, [(10, "Stempak", "A B", "C D")])
        self.assertEqual(dt.datetime.fromtimestamp(lock, dt.timezone.utc).strftime("%a %H:%M"), "Sun 16:30")

    def test_experts_health_end_to_end(self):
        c_feed = feed()
        sl = {f"s{i}": {"full_name": f"Wr {n}", "position": "WR"} for i, n in enumerate(L)}

        def fetch(url, params=None, **kw):
            if "state/nfl" in url:
                return {"week": 11, "season_type": "regular"}
            if "kona_player_info" in str(params):
                return c_feed
            stats = "stats/nfl" in url
            return [{"player_id": f"s{i}", "stats": ({"gp": 1, "pts_half_ppr": float(10 - i if i != 3 else 20)} if stats
                                                       else {"pts_half_ppr": float(10 - i)})} for i in range(7)]
        kick = dt.datetime(2026, 11, 5, 1, 15, tzinfo=dt.timezone.utc)
        doc = {"week": 10, "leagues": {"Stempak": {"advice": {"moves": ["Start Wr Gus (4.0) over Wr Ann (10.0) at WR, +1.0"]}}}}
        h = health.experts_health(fetch, players=sl, versions=[(0, "v")], load=lambda s, p: doc,
                                  first_kicks={10: kick, 9: kick - dt.timedelta(days=7)})
        self.assertEqual(h["weeks"], list(range(1, 11)))
        self.assertGreater(h["acc"]["n"], 0)
        self.assertEqual(h["calls"]["n"], 1)
        self.assertEqual(h["calls"]["right"], 0)               # Wr Gus scored 4, Wr Ann scored 10
        self.assertEqual(h["calls"]["experts_split"], 1)       # the experts had Wr Ann first


if __name__ == "__main__":
    unittest.main()
