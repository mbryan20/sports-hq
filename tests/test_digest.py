"""Daily digest: once per day after 8am CT, urgent items for dead starters, quiet NBA off nights."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import advice, digest

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 29, 13, 30, tzinfo=UTC)          # Thu 8:30am CDT
TNF = dt.datetime(2026, 10, 30, 0, 15, tzinfo=UTC)           # Thu 7:15pm CDT
SUN = dt.datetime(2026, 11, 1, 18, 0, tzinfo=UTC)


def p(name, slot, positions, *, status=None, kickoff=SUN, bye=False, proj=10.0, pid=None):
    return {"id": pid or name, "name": name, "slot": slot, "positions": positions, "status": status, "why": "",
            "kickoff": None if bye else kickoff, "started": False, "bye": bye, "proj": proj, "team": "X"}


class League:
    name, sport, free_agents, opponent, opp_proj = "Test", "nfl", [], "Rival", 20.0
    def __init__(self, starters, bench, sport="nfl"):
        self.starters, self.bench, self.sport = starters, bench, sport
    def best_fa(self, positions, now):
        return None


class Digest(unittest.TestCase):
    def test_due_once_per_day(self):
        early = dt.datetime(2026, 10, 29, 12, 50, tzinfo=UTC)    # 7:50am CDT
        self.assertFalse(digest.due(early, None))
        self.assertTrue(digest.due(NOW, NOW - dt.timedelta(hours=20)))
        self.assertFalse(digest.due(NOW + dt.timedelta(hours=1), NOW))
        winter = dt.datetime(2026, 11, 5, 14, 5, tzinfo=UTC)    # 8:05am CST
        self.assertTrue(digest.due(winter, NOW))

    def test_nfl_bye_and_out(self):
        lg = League([p("Bye WR", "WR", ["WR"], bye=True), p("Hurt RB", "RB", ["RB"], status="OUT"),
                     p("Thu TE", "TE", ["TE"], status="Q", kickoff=TNF)],
                    [p("Spare WR", "BN", ["WR"], proj=8.0), p("Spare RB", "BN", ["RB"], proj=6.0)])
        items = digest.league_items(lg, NOW)
        texts = [i["text"] for i in items]
        self.assertTrue(any("Bye WR (WR) on BYE → start Spare WR" in t for t in texts))
        self.assertTrue(any("Hurt RB (RB) OUT → start Spare RB" in t for t in texts))
        self.assertTrue(any("Thu TE (TE) is Questionable" in t for t in texts))
        self.assertTrue(any("1 starters play today" in t for t in texts))
        title, _ = digest.message(items)
        self.assertEqual(title, "Today: 2 things to fix")

    def test_nba_off_night_is_quiet_without_bench_cover(self):
        tonight = dt.datetime(2026, 10, 30, 0, 30, tzinfo=UTC)
        lg = League([p("Idle G", "G", ["PG", "G"], bye=True), p("Playing C", "C", ["C"], kickoff=tonight)],
                    [p("Bench C", "BN", ["C"], kickoff=tonight)], sport="nba")
        items = digest.league_items(lg, NOW)
        self.assertFalse(any(i["urgent"] for i in items))
        lg.bench.append(p("Bench G", "BN", ["SG", "G"], kickoff=tonight))
        items = digest.league_items(lg, NOW)
        # listed, but not urgent: shq/nba_lineup.py pushes NBA lineup fixes once a day before the first tip (Q-032)
        self.assertTrue(any(not i["urgent"] and "start Bench G" in i["text"] for i in items))

    def test_guillotine_danger(self):
        lg = League([], [])
        lg.standing = {"rank": 11, "n": 12, "gap": -3.2}
        item = digest.league_items(lg, NOW)[0]
        self.assertTrue(item["urgent"])
        self.assertIn("DANGER ZONE", item["text"])

    def test_advice_block(self):
        lg = League([p("Hurt RB", "RB", ["RB"], status="OUT"), p("Weak WR", "WR", ["WR"], proj=3.0)],
                    [p("Spare RB", "BN", ["RB"], proj=6.0), p("Good WR", "BN", ["WR"], proj=9.0)])
        a = advice.build(lg, NOW)
        self.assertEqual(a["fixes"], ["Hurt RB (RB) OUT → start Spare RB (6.0 proj)"])
        self.assertEqual(a["moves"], ["Start Good WR (9.0) over Weak WR (3.0) at WR, +6.0"])
        self.assertIn("projected to lose by 17.0", a["matchup"])
        lg.standing = {"rank": 2, "n": 10, "gap": 30.0}
        a = advice.build(lg, NOW)
        self.assertTrue(a["matchup"].startswith("Projected 2 of 10"))
        self.assertFalse(a["danger"])


class FreeAgentFix(unittest.TestCase):
    """Nov 10, Domo Arigato: "Caleb Williams (QB) on BYE → start Carson Wentz" while Wentz projected 0 (a backup
    after Cousins' trade) and Drew Lock (SEA, 15.7) sat on waivers. A fill-in under MIN_FILL, or one a free agent
    beats by FA_EDGE+, becomes "add <FA> and start him"; the projection always shows, even 0."""
    SLOTS = ["QB", "RB", "WR", "SUPER_FLEX"]

    def league(self, starters, bench, fas, open_spots=0):
        lg = League(starters, bench)
        lg.free_agents, lg.open_spots, lg.slots = fas, open_spots, self.SLOTS
        return lg

    def fix(self, lg):
        return [i["text"] for i in digest.league_items(lg, NOW) if i["urgent"]]

    def test_zero_projection_bench_player_gives_way_to_free_agent(self):
        lg = self.league([p("Caleb Williams", "QB", ["QB"], bye=True, proj=0)],
                         [p("Carson Wentz", "BN", ["QB"], proj=0)],
                         [p("Drew Lock", "FA", ["QB"], proj=15.7), p("Waiver WR", "FA", ["WR"], proj=20.0)],
                         open_spots=1)
        self.assertEqual(self.fix(lg), ["Caleb Williams (QB) on BYE → add Drew Lock (X, 15.7 proj) into your open "
                                        "roster spot and start him (Carson Wentz projects 0)"])
        self.assertEqual(advice.build(lg, NOW)["fixes"], self.fix(lg))   # league tab says the same

    def test_questionable_free_agent_named_when_far_better(self):
        # Nov 10: Drew Lock (Q, expected to play, 18.7) vs Kyle McCord (healthy, 12.4) for Caleb Williams' bye
        dead = [p("Caleb Williams", "QB", ["QB"], bye=True, proj=0)]
        bench = [p("Carson Wentz", "BN", ["QB"], proj=0)]
        lock, mccord = p("Drew Lock", "FA", ["QB"], status="Q", proj=18.7), p("Kyle McCord", "FA", ["QB"], proj=12.4)
        self.assertIn("add Drew Lock (X, Q, 18.7 proj)", self.fix(self.league(dead, bench, [lock, mccord], 1))[0])
        lock["proj"] = 15.7                                            # live Nov 10 evening: 3.3 more, still Lock
        self.assertIn("add Drew Lock (X, Q, 15.7 proj)", self.fix(self.league(dead, bench, [lock, mccord], 1))[0])
        lock["proj"] = 14.0                                            # under Q_EDGE more: the healthy one
        self.assertIn("add Kyle McCord (X, 12.4 proj)", self.fix(self.league(dead, bench, [lock, mccord], 1))[0])
        lock["proj"], lock["conflict"] = 18.7, True                    # Sleeper Out, unconfirmed: never named
        self.assertIn("add Kyle McCord", self.fix(self.league(dead, bench, [lock, mccord], 1))[0])

    def test_free_agent_far_better_keeps_bench_fallback(self):
        lg = self.league([p("Hurt RB", "RB", ["RB"], status="OUT")], [p("Spare RB", "BN", ["RB"], proj=3.0)],
                         [p("Waiver RB", "FA", ["RB"], proj=9.5)])
        self.assertEqual(self.fix(lg), ["Hurt RB (RB) OUT → add Waiver RB (X, 9.5 proj) and start him "
                                        "(or start Spare RB, 3.0 proj); needs a roster spot"])

    def test_healthy_bench_player_clearly_best_is_unchanged(self):
        lg = self.league([p("Hurt RB", "RB", ["RB"], status="OUT")], [p("Zach Charbonnet", "BN", ["RB"], proj=12.8)],
                         [p("Waiver RB", "FA", ["RB"], proj=14.0), p("Big WR", "FA", ["WR"], proj=30.0)])
        self.assertEqual(self.fix(lg), ["Hurt RB (RB) OUT → start Zach Charbonnet (12.8 proj)"])

    def test_projection_shown_when_zero(self):
        lg = self.league([p("Caleb Williams", "QB", ["QB"], bye=True, proj=0)],
                         [p("Carson Wentz", "BN", ["QB"], proj=0)], [])   # no free agent to suggest
        self.assertEqual(self.fix(lg), ["Caleb Williams (QB) on BYE → start Carson Wentz (0 proj)"])

    def test_superflex_slot_takes_any_eligible_free_agent_and_qb_slot_only_qbs(self):
        fas = [p("Waiver QB", "FA", ["QB"], proj=14.0), p("Waiver WR", "FA", ["WR"], proj=18.0)]
        sf = self.league([p("Bye QB", "SUPER_FLEX", ["QB"], bye=True, proj=0)], [], fas)
        self.assertEqual(self.fix(sf), ["Bye QB (SUPER_FLEX) on BYE → no bench fit: add Waiver WR (X, 18.0 proj) "
                                        "and start him; needs a roster spot"])
        qb = self.league([p("Bye QB", "QB", ["QB"], bye=True, proj=0), p("Bye QB2", "SUPER_FLEX", ["QB"], bye=True, proj=0)],
                         [], fas, open_spots=2)
        self.assertEqual(self.fix(qb), ["Bye QB (QB) on BYE → no bench fit: add Waiver QB (X, 14.0 proj) into your open "
                                        "roster spot and start him",                       # never the WR at QB
                                        "Bye QB2 (SUPER_FLEX) on BYE → no bench fit: add Waiver WR (X, 18.0 proj) into "
                                        "your open roster spot and start him"])            # each FA named once

    def test_injury_watch_skips_zero_projection_swap_and_names_free_agent(self):
        from shq import notify, run
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)
        soon = NOW + dt.timedelta(hours=1)
        lg = self.league([p("Hurt QB", "QB", ["QB"], status="OUT", kickoff=soon)],
                         [p("Backup QB", "BN", ["QB"], proj=0, kickoff=soon)],
                         [p("Waiver QB", "FA", ["QB"], proj=15.7, kickoff=soon)])
        lg.key, lg.week, lg.can_write = "t", 10, False
        self.assertEqual(run.injury_watch(lg, NOW), ["no bench for Hurt QB"])
        self.assertIn("your best bench fit, Backup QB, projects 0 proj. Best FA: Waiver QB (X, 15.7 proj)",
                      notify.sent[-1]["message"])
        lg.bench[0]["proj"] = 12.0                                       # a real fill-in: swap stands, no FA tip
        notify.sent.clear()
        self.assertEqual(run.injury_watch(lg, NOW), ["suggested Hurt QB -> Backup QB"])
        self.assertNotIn("Better", notify.sent[-1]["message"])


class PassThreeFixes(unittest.TestCase):
    """Nov 10 pass-3 review: the Q mark sits inside the team bracket; a weak bench fill-in gives way to a free agent
    projecting double; a guillotine fix follows War Room v2 (free adds only, v2's drop, never a claim's drop)."""
    SLOTS = ["QB", "RB", "WR", "TE", "SUPER_FLEX"]
    league = FreeAgentFix.league
    fix = FreeAgentFix.fix

    def test_q_mark_inside_the_brackets(self):
        lock = {**p("Drew Lock", "FA", ["QB"], status="Q", proj=15.7), "team": "SEA"}
        lg = self.league([p("Caleb Williams", "QB", ["QB"], bye=True, proj=0)], [p("Carson Wentz", "BN", ["QB"], proj=0)],
                         [lock], 1)
        self.assertEqual(self.fix(lg), ["Caleb Williams (QB) on BYE → add Drew Lock (SEA, Q, 15.7 proj) into your open "
                                        "roster spot and start him (Carson Wentz projects 0)"])
        from shq import notify, run                                   # the injury-watch push says it the same way
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)
        soon = NOW + dt.timedelta(hours=1)
        lg = self.league([p("Hurt QB", "QB", ["QB"], status="OUT", kickoff=soon)],
                         [p("Backup QB", "BN", ["QB"], proj=4.0, kickoff=soon)],
                         [{**lock, "kickoff": soon}])
        lg.key, lg.week, lg.can_write = "t", 10, False
        run.injury_watch(lg, NOW)
        self.assertIn("Better: add Drew Lock (SEA, Q, 15.7 proj) and start him", notify.sent[-1]["message"])

    def test_weak_bench_fill_in_gives_way_to_a_free_agent_projecting_double(self):
        # 3-Ball FB, Nov 10: "start Kenyon Sadiq (4.0 proj)" for Goedert's bye; Pat Freiermuth (8.2) was a free agent
        goedert = p("Dallas Goedert", "TE", ["TE"], bye=True, proj=0)
        sadiq, pat = p("Kenyon Sadiq", "BN", ["TE"], proj=4.0), p("Pat Freiermuth", "FA", ["TE"], proj=8.2)
        self.assertEqual(self.fix(self.league([goedert], [sadiq], [pat])),
                         ["Dallas Goedert (TE) on BYE → add Pat Freiermuth (X, 8.2 proj) and start him "
                          "(or start Kenyon Sadiq, 4.0 proj); needs a roster spot"])
        sadiq["proj"] = 4.5                                            # 8.2 is under double: keep the bench option
        self.assertEqual(self.fix(self.league([goedert], [sadiq], [pat])),
                         ["Dallas Goedert (TE) on BYE → start Kenyon Sadiq (4.5 proj)"])
        sadiq["proj"], pat["proj"] = 6.0, 10.5                         # not weak, gap under FA_EDGE: bench
        self.assertEqual(self.fix(self.league([goedert], [sadiq], [pat])),
                         ["Dallas Goedert (TE) on BYE → start Kenyon Sadiq (6.0 proj)"])

    def guillotine(self, source="War Room v2"):
        """Nov 10 Guillotine: Goedert (TE) on bye, no TE on the bench. War Room v2: Harold Fannin a $1 claim (drop Woody
        Marks), Saquon Barkley a $1 claim (drop Khalil Shakir), Pat Freiermuth a free add (drop Woody Marks)."""
        row = lambda sid, name, call, free, drop, **k: {"sid": sid, "name": name, "pos": k.get("pos", "TE"),
                                                        "team": k.get("team", "PIT"), "proj": k.get("proj", 9.0),
                                                        "gain": 3.0, "call": call, "bid": k.get("bid", 0), "free": free,
                                                        "drop": drop, "v2": source == "War Room v2"}
        lg = self.league([p("Dallas Goedert", "TE", ["TE"], bye=True, proj=0)],
                         [p("Khalil Shakir", "BN", ["WR"], proj=8.3, pid="s1"),
                          p("Woody Marks", "BN", ["RB"], proj=7.5, pid="s2"),
                          p("Braelon Allen", "BN", ["RB"], proj=6.0, pid="s3")],
                         [p("Harold Fannin Jr.", "FA", ["TE"], proj=9.2, pid="12506"),
                          p("Pat Freiermuth", "FA", ["TE"], proj=8.0, pid="7600"),
                          p("Brenton Strange", "FA", ["TE"], proj=7.0, pid="9480"),
                          p("Jaylen Warren", "FA", ["RB"], proj=13.5, pid="8228")])
        lg.guillotine = {"bid_source": {"name": source}, "waivers": "Wed 2:15a", "waiting": ["8228"], "bids": [
            row("8228", "Jaylen Warren", "coin flip", False, "Braelon Allen", pos="RB", bid=2, proj=15.3),
            row("6804", "Jordan Love", "add free", True, "Woody Marks", pos="QB", team="GB", proj=20.2),
            row("12506", "Harold Fannin", "bid", False, "Woody Marks", team="CLE", bid=1),
            row("4866", "Saquon Barkley", "bid", False, "Khalil Shakir", pos="RB", team="PHI", bid=1, proj=0),
            row("5844", "T.J. Hockenson", "priced out", False, "Tre Tucker", team="MIN", proj=8.3),
            row("7600", "Pat Freiermuth", "add free", True, "Woody Marks", proj=9.1)]}
        return lg

    def test_guillotine_fix_names_a_free_add_with_war_room_v2s_drop(self):
        lg = self.guillotine()
        expect = ["Dallas Goedert (TE) on BYE → no bench fit: add Pat Freiermuth (X, 8.0 proj), drop Woody Marks "
                  "(7.5 proj) as War Room v2 says, and start him"]
        self.assertEqual(self.fix(lg), expect)                         # never Fannin: a claim until Wednesday's run
        self.assertEqual(advice.build(lg, NOW)["fixes"], expect)       # league page and Weekly say the same
        # a dashboard-model fallback (v2 stale) keeps the old rule: best free agent, claims included
        self.assertIn("add Harold Fannin Jr.", self.fix(self.guillotine(source="dashboard model"))[0])

    def test_guillotine_fix_never_drops_a_players_v2_drops_for_a_claim(self):
        from unittest import mock
        lg = self.guillotine()
        lg.guillotine["bids"] = [b for b in lg.guillotine["bids"] if b["name"] != "Pat Freiermuth"]   # no v2 row: _room
        lg._valued = True
        for fa in lg.free_agents:
            fa["ppg"] = fa["proj"]
        seen = []
        def adds(starters, bench, fas, slots, **kw):
            seen.append([b["name"] for b in bench])
            return [{"drop": bench[0]}] if bench else []
        with mock.patch.object(digest.waivers, "adds", adds):
            text = self.fix(lg)[0]
        self.assertEqual(seen, [[]])          # Shakir (Barkley claim's drop), Marks and Allen (claims' drops) kept
        self.assertIn("add Pat Freiermuth (X, 8.0 proj) and start him; needs a roster spot", text)

    def test_guillotine_adds_are_war_room_v2s_calls_and_drops(self):
        from shq import run
        lg = self.guillotine()
        lines = advice.adds(lg)
        self.assertEqual(lines, [
            "Add Jaylen Warren (RB, PIT, 15.3 proj) on waivers, drop Braelon Allen (War Room v2: coin flip, bid $2, "
            "+3.0 pts this week; claims run Wed 2:15a CT)",
            "Add Jordan Love (QB, GB, 20.2 proj) now, no claim needed, drop Woody Marks (War Room v2: add free, "
            "+3.0 pts this week)",
            "Add Harold Fannin (TE, CLE, 9.0 proj) on waivers, drop Woody Marks (War Room v2: bid, bid $1, "
            "+3.0 pts this week; claims run Wed 2:15a CT)"])
        self.assertEqual([run.add_key(x) for x in lines],      # the Weekly plan compares adds by (add, drop)
                         [("Jaylen Warren", "Braelon Allen"), ("Jordan Love", "Woody Marks"), ("Harold Fannin", "Woody Marks")])
        lg.guillotine["bid_source"] = {"name": "dashboard model"}
        self.assertNotIn("War Room v2", " ".join(advice.adds(lg)))


class LaptopKick(unittest.TestCase):
    """Q-029: a laptop-dispatched run can run beside a cron run, so the digest checks origin/main before building."""
    def test_digest_built_elsewhere_today_is_not_built_again(self):
        from shq import run
        ten_min_ago = NOW - dt.timedelta(minutes=10)
        yesterday = NOW - dt.timedelta(days=1)
        self.assertFalse(run.digest_due(NOW, yesterday, lambda: ten_min_ago))   # the other run already built it
        self.assertTrue(run.digest_due(NOW, yesterday, lambda: yesterday))
        self.assertTrue(run.digest_due(NOW, None, lambda: None))                # origin unreadable: build as before
        self.assertFalse(run.digest_due(NOW, ten_min_ago, lambda: self.fail("origin read when not due")))
        self.assertFalse(run.digest_due(NOW.replace(hour=12), yesterday, lambda: None))   # 7am CDT: not yet due


if __name__ == "__main__":
    unittest.main()
