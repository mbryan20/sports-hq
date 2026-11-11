"""NBA trend radar: usage from box scores, rising/shrinking roles, who absorbs an injured starter's minutes,
category fit, cited injuries, and the push caps."""
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import digest, notify, radar
from shq.leagues import EspnLeague

NOW = dt.datetime(2026, 10, 28, 15, 0, tzinfo=dt.timezone.utc)      # Wed 10am CT, scoring period 9
TIP = lambda day: NOW + dt.timedelta(days=day - 9, hours=8)
NEWS = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.timezone.utc)


def g(period, team, mins, fga=0, fta=0, to=0, start=0, **cats):
    return [period, team, {"40": mins, "14": fga, "16": fta, "11": to, "41": start, **cats}]


def player(name, team, games, pos=1, owned=5.0, season=None):
    mins = sum(x[2]["40"] for x in games) or 1
    return {"name": name, "team": team, "pos": pos, "eligible": [0, 12], "injury": "ACTIVE", "owned": owned, "change": 1.2,
            "season": season or {"40": mins / max(len(games), 1), "41": sum(x[2]["41"] for x in games) / max(len(games), 1)},
            "games": games}


# ATL (1): the starter (100) played periods 1-5 and has been out since; the free agent (101) took his minutes.
# BOS (2): my bench guard (200) is rising; my starter (201) lost minutes and is day-to-day.
POOL = {
    "100": player("Atlanta Star", 1, [g(d, 1, 34, fga=20, fta=6, to=3, start=1) for d in range(1, 6)], season={"40": 34, "41": 1}),
    "101": player("Atlanta Riser", 1, [g(d, 1, 12, fga=4, start=0, **{"3": 2, "17": 1}) for d in range(1, 6)]
                  + [g(d, 1, 32, fga=14, fta=4, to=2, start=1, **{"3": 7, "17": 3}) for d in range(6, 9)], owned=8.0),
    "102": player("Atlanta Vet", 1, [g(d, 1, 30, fga=10, fta=2, to=1, start=1) for d in range(1, 9)]),
    "103": player("Atlanta Filler", 1, [g(d, 1, 164 if d < 6 else 146, fga=50, fta=10, to=8, start=1) for d in range(1, 9)]),
    "200": player("Boston Guard", 2, [g(d, 2, 15, fga=5, **{"3": 3}) for d in range(1, 6)]
                  + [g(d, 2, 31, fga=12, fta=3, to=2, start=1, **{"3": 6}) for d in range(6, 9)]),
    "201": player("Boston Big", 2, [g(d, 2, 33, fga=12, start=1) for d in range(1, 6)] + [g(d, 2, 18, fga=6) for d in range(6, 9)],
                  pos=5, owned=90.0),
    "202": player("Boston Filler", 2, [g(d, 2, 192 if d < 6 else 191, fga=60, fta=15, to=10, start=1) for d in range(1, 9)]),
}
REPORT = {
    "100": {"status": "Out", "name": "Atlanta Star", "team": "ATL", "date": NEWS, "note": "Star (ankle) will miss two weeks.",
            "url": "https://www.espn.com/nba/player/_/id/100"},
    "201": {"status": "Day-To-Day", "name": "Boston Big", "team": "BOS", "date": NEWS, "note": "Big (back) is day-to-day.",
            "url": "https://www.espn.com/nba/player/_/id/201"},
}


class Ctx:
    now, week, week_start = NOW, 8, None
    def pro_schedule(self, sport, season):
        played = {d: [(TIP(d), 0, True)] for d in range(1, 9)}
        return {1: {"abbrev": "ATL", "games": {**played, **{d: [(TIP(d), 2, True)] for d in (9, 11, 12, 13)}}},
                2: {"abbrev": "BOS", "games": {**played, **{d: [(TIP(d), 1, False)] for d in (10, 12)}}}}
    def injury_report(self, sport):
        return REPORT


def rp(pid, name, team, slot):
    return {"id": pid, "name": name, "pro_team": team, "eligible": [0, 12], "pos": 1, "injury": "ACTIVE", "proj": None,
            "owned": 1.0, "slot": slot}


SNAP = {"captured": "2026-10-28T14:00:00Z", "sport": "nba", "league_id": 190278, "season": 2027, "league_name": "Test",
        "scoring_period": 9, "matchup_period": 2, "scoring_type": "H2H_CATEGORY", "team": {"id": 5, "name": "Me"},
        "opponent": "Them", "slot_counts": {"0": 1, "12": 3, "13": 1},
        "roster": [rp(201, "Boston Big", 2, 0), rp(200, "Boston Guard", 2, 12)],
        "teams": [{"id": 9, "name": "Them", "roster": [rp(102, "Atlanta Vet", 1, 0), rp(100, "Atlanta Star", 1, 13)]}],
        "free_agents": [], "matchup": {"cats": [[3, False], [17, False], [6, False], [11, True]], "mine": {}, "opp": {},
                                       "opp_id": 9, "avg": {}, "fa_more": []}}
CATS = {"rows": [{"cat": "AST", "outlook": "lose"}, {"cat": "3PM", "outlook": "close"}, {"cat": "REB", "outlook": "win"},
                 {"cat": "TO", "outlook": "lose"}], "games_left": [5, 3]}


def league():
    import shq.espn_fantasy as ef
    ef.load_snapshot = lambda sport, lid: SNAP
    return EspnLeague(Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 190278, "team_id": 5, "private": True})


class Radar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = radar.OWNED, notify.ALERTS, radar.fetch_pool
        radar.OWNED, notify.ALERTS = Path(self.tmp.name) / "owned.json", Path(self.tmp.name) / "alerts.json"
        radar.fetch_pool = lambda *a, **k: POOL
        notify.sent.clear()

    def tearDown(self):
        radar.OWNED, notify.ALERTS, radar.fetch_pool = self.saved
        self.tmp.cleanup()

    def test_usage_is_the_share_of_team_plays_on_the_floor(self):
        tg = radar.team_games(POOL)
        team_plays = (20 + 0.44 * 6 + 3) + 4 + (10 + 0.44 * 2 + 1) + (50 + 0.44 * 10 + 8)
        self.assertEqual(tg[(1, 1)], [240.0, round(team_plays, 2)])        # minutes and plays summed over the team
        w = radar.window([POOL["100"]["games"][0]], tg)
        plays = 20 + 0.44 * 6 + 3
        self.assertAlmostEqual(w["usg"], 100 * plays / 34 / (tg[(1, 1)][1] / 48))

    def test_rising_role_counts_missed_games_as_zero(self):
        tg = radar.team_games(POOL)
        rl = radar.role(POOL["101"], tg, 9)
        self.assertEqual((round(rl["base"]["min"]), round(rl["recent"]["min"]), rl["started"]), (12, 32, True))
        self.assertTrue(radar.rising(rl))
        self.assertTrue(radar.shrinking(radar.role(POOL["201"], tg, 9)))
        self.assertFalse(radar.rising(radar.role(POOL["102"], tg, 9)))   # same role all season
        self.assertIsNone(radar.role(POOL["100"], tg, 30))               # his last games are stale
        traded = {**POOL["101"], "team": 2, "games": [[d, 1, st] for d, _, st in POOL["101"]["games"][:5]]
                  + [[d, 2, st] for d, _, st in POOL["101"]["games"][5:]]}
        self.assertIsNone(radar.role(traded, tg, 9))                     # no games here before the 3 since his trade

    def test_back_from_an_absence_is_not_a_riser(self):
        tg = radar.team_games(POOL)
        back = player("Atlanta Returner", 1, [g(2, 1, 28, fga=10)] + [g(d, 1, 30, fga=12, start=1) for d in (6, 7, 8)])
        rl = radar.role(back, tg, 9)
        self.assertEqual((rl["base"]["played"], rl["base"]["n"], rl["back"]), (1, 5, True))   # sat 4 of 5 earlier games
        self.assertFalse(radar.rising(rl))
        self.assertFalse(radar.role(POOL["101"], tg, 9)["back"])

    def test_cause_ranks_first_and_an_unexplained_jump_may_fade(self):
        tg = radar.team_games(POOL)
        riser, guard = radar.role(POOL["101"], tg, 9), radar.role(POOL["200"], tg, 9)
        self.assertEqual((riser["streak"], guard["streak"]), (3, 3))
        self.assertFalse(radar.may_fade(riser, ["100"]))                  # Atlanta Star's absence explains it
        self.assertTrue(radar.may_fade(guard, []))                        # no cause, 3 games of it so far
        self.assertFalse(radar.may_fade({**guard, "streak": 4}, []))
        out = {"100"}
        self.assertLess(radar.rank_key(riser, ["100"], out, 0.1), radar.rank_key(guard, [], out, 9.0))   # cause beats fit
        self.assertGreater(radar.rank_key(riser, ["100"], set(), 0.1), radar.rank_key(guard, [], set(), 9.0))
        self.assertLess(radar.rank_key(guard, [], set(), 2.0, games=3), radar.rank_key(riser, [], set(), 5.0, games=1))

    def test_injured_starter_and_who_absorbs_his_minutes(self):
        gains = radar.with_without(POOL, radar.team_games(POOL), "100")
        self.assertEqual(gains[0][1], "101")
        self.assertEqual((round(gains[0][2]["min"]), round(gains[0][3]["min"])), (12, 32))

    def test_league_block(self):
        lg = league()
        r = radar.block(lg, CATS)
        self.assertEqual(r["need"], ["AST (losing)", "3PM (close)"])      # TO is reversed: never "needed"
        self.assertEqual([i["where"] for i in r["rising"]], ["bench", "fa"])
        self.assertIn("no teammate's injury behind it and it hasn't lasted 4 straight games yet, so this may fade", r["rising"][0]["text"])
        self.assertTrue(r["rising"][0]["fade"])
        self.assertIn("; may fade (ESPN game logs", r["rising"][0]["short"])
        fa = r["rising"][1]
        self.assertFalse(fa["fade"])
        self.assertNotIn("may fade", fa["text"])
        self.assertIn("Atlanta Riser (PG, ATL), free agent, rostered 8% (+1.2% lately, ESPN's +/-)", fa["text"])
        self.assertIn("minutes 12 → 32 in his last 3 games", fa["text"])
        self.assertIn("since Atlanta Star went out [ESPN Oct 25: Out, Star (ankle) will miss two weeks.]", fa["text"])
        self.assertIn("Fits AST (losing), 3PM (close)", fa["text"])
        self.assertIn("4 games left this week", fa["text"])
        self.assertIn(["ESPN Oct 25", "https://www.espn.com/nba/player/_/id/100"], fa["links"])
        self.assertTrue(fa["push"])
        self.assertFalse(r["rising"][0]["push"])                           # my bench: no push, just "start him"
        (shrink,) = r["shrinking"]
        self.assertIn("Boston Big (C, BOS): minutes 33 → 18", shrink["text"])
        self.assertIn("ESPN's injury report [ESPN Oct 25: Day-To-Day", shrink["text"])
        (inj,) = r["injuries"]
        self.assertIn("Atlanta Star (ATL) is out [ESPN Oct 25: Out", inj["text"])
        self.assertIn("Atlanta Riser (FA) 12 → 32 min", inj["text"])

    def test_week_over_ranks_for_every_category(self):
        self.assertEqual(radar.needed(league(), {"rows": CATS["rows"], "games_left": [0, 0]}), {3: "all", 17: "all", 6: "all"})

    def test_push_once_a_day_and_once_a_week_per_player(self):
        lg = league()
        advice = {"radar": radar.block(lg, CATS)}
        self.assertIn("rising free agent Atlanta Riser", radar.send_alerts(lg, advice))
        self.assertIsNone(radar.send_alerts(lg, advice))                  # same day
        lg.ctx.now = NOW + dt.timedelta(days=1)
        self.assertIsNone(radar.send_alerts(lg, advice))                  # next day, same player, same week
        self.assertEqual(len(notify.sent), 1)
        lg.ctx.now = NOW.replace(hour=4)                                   # 11pm CT
        notify.ALERTS.unlink()
        self.assertIsNone(radar.send_alerts(lg, advice))

    def test_digest_lines_are_short_and_dated(self):
        lg = league()
        lg.radar = radar.block(lg, CATS)
        self.assertFalse(any(i["text"].startswith("Radar:") for i in digest.league_items(lg, NOW)))   # not in the tab's notes
        items = [i for i in digest.build([lg], NOW) if i["text"].startswith("Radar:")]
        self.assertEqual(len(items), 3)
        self.assertFalse(any(i["urgent"] for i in items))
        self.assertIn("Atlanta Riser (ATL, FA 8%): minutes 12 → 32", items[1]["text"])
        self.assertIn("(ESPN game logs through Oct 27)", items[1]["text"])
        self.assertIn("Boston Big (BOS, yours): minutes 33 → 18, lost his starting spot [ESPN Oct 25: Day-To-Day", items[2]["text"])

    def test_ownership_history_once_a_day(self):
        radar.track_ownership(POOL, NOW)
        radar.track_ownership({**POOL, "101": {**POOL["101"], "owned": 50}}, NOW + dt.timedelta(hours=2))
        hist = radar.load_json(radar.OWNED)
        self.assertEqual(list(hist), ["2026-10-28"])
        self.assertEqual(hist["2026-10-28"]["101"], 8.0)
        self.assertNotIn("201", hist["2026-10-28"])                          # 90% owned: not a market riser


class Backtest(unittest.TestCase):
    def test_rosters_rewind_and_flags_use_only_earlier_games(self):
        from shq import radar_backtest as bt
        txns = [(3, "ADD", "101"), (7, "ADD", "101"), (7, "DROP", "300"), (8, "DROP", "102")]
        self.assertEqual(bt.rostered_at({"101", "201"}, txns, 7), {"201", "300", "102"})   # adds from 7 on undone, later drops restored
        more = lambda pid, mins, days=(9, 10, 11), **kw: {**POOL[pid], "games": POOL[pid]["games"]
                                                         + [g(d, 1, mins, start=1, **kw) for d in days]}
        steady = lambda name, pts, owned: player(name, 1, [g(d, 1, 10, fga=3, **{"0": pts}) for d in range(1, 12)], owned=owned)
        pool = {**POOL, "101": more("101", 30, days=(9, 10), fga=12, **{"0": 20}), "102": more("102", 30, fga=10),
                "103": more("103", 180, fga=50),
                "104": steady("Most Owned Today", 2, 60.0), "105": steady("Most Owned That Morning", 20, 1.0)}
        rostered = {"102", "103", "200", "201", "202"}
        dates = {d: dt.date(2026, 10, 27) + dt.timedelta(days=d) for d in (9, 10, 11)}           # period 9 = Nov 5
        owned = {"2026-11-05": {"105": 50.0, "101": 8.0}}                                       # 104 was under 0.5%
        cats = [(0, False)]
        old = bt.FIRST, bt.WIRE
        bt.FIRST, bt.WIRE = 9, 1
        try:
            res = bt.run(pool, rostered, [(10, "ADD", "101")], cats, 11, dates, owned)
            s = bt.summary(res)
        finally:
            bt.FIRST, bt.WIRE = old
        # flagged the morning of period 9 from games 1-8 only, then judged on the team's next 3 games (9-11), the one he
        # missed counting as 0 minutes; later mornings have too few games after them to score
        self.assertEqual(res["mornings"], [9, 10, 11])
        (f,) = res["log"]
        self.assertEqual((f["day"], f["id"], round(f["base"]), round(f["flag"]), f["after"], f["played"], f["held"], f["added"]),
                         (9, "101", 12, 32, 20, 2, True, 10))
        self.assertEqual((f["cause"], f["fade"], f["shown"]), ("Atlanta Star", False, True))
        # the old suggestion is the free agent most owned that morning (105), not today (104)
        sc = {"z": radar.z_scales(pool, radar.team_games(pool))}
        self.assertEqual(res["wire"], [(9, bt.value(sc, cats, pool["105"]["games"][8:11]))])
        self.assertEqual((s["shown"]["n"], s["shown"]["held_rate"], s["flags"]["edge_n"], s["wire_mornings"]), (1, 1.0, 1, 1))
        self.assertEqual(s["flags"]["edge"], round(f["value"] - res["wire"][0][1], 2))
        self.assertEqual(bt.before(pool, 6)["101"]["games"][-1][0], 5)
        self.assertEqual(bt.day_date({14: dt.date(2026, 11, 2), 16: dt.date(2026, 11, 4)}, 15), dt.date(2026, 11, 3))


if __name__ == "__main__":
    unittest.main()
