"""Trade finder, trade offers, waiver adds and the value sources behind them (no network)."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import advice, espn_fantasy, trades, values, waivers

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
NO_FLEX = ["QB", "RB", "RB", "WR", "WR", "TE", "K"]


def p(name, pos, ppg, val, *, proj=None, bye=False, status=None, slot="BN"):
    return {"id": name, "key": name, "name": name, "positions": [pos], "ppg": ppg, "val": val,
            "proj": ppg if proj is None else proj, "bye": bye, "status": status, "team": "NYJ",
            "slot": slot, "started": False, "empty": False}


def roster(*players):
    return list(players)


class Lineup(unittest.TestCase):
    def test_flex_takes_best_leftover_and_kickers_are_ignored(self):
        mine = roster(p("Q", "QB", 20, 5000), p("R1", "RB", 15, 4000), p("R2", "RB", 12, 3000),
                      p("R3", "RB", 11, 2000), p("W1", "WR", 14, 4000), p("W2", "WR", 9, 1000),
                      p("W3", "WR", 10, 1500), p("T", "TE", 8, 900), p("K", "K", 9, 0))
        total, picks = trades.lineup(trades.skill_slots(SLOTS), mine)
        self.assertEqual(dict((s, x["name"]) for s, x in picks)["FLEX"], "R3")
        self.assertEqual(total, 20 + 15 + 12 + 14 + 10 + 8 + 11)

    def test_superflex_and_espn_op(self):
        self.assertEqual(trades.skill_slots(["FLEX", "QB", "OP", "SUPER_FLEX", "D/ST"]), ["QB", "FLEX", "OP", "SUPER_FLEX"])
        _, picks = trades.lineup(["QB", "OP"], [p("A", "QB", 20, 1), p("B", "QB", 18, 1)])
        self.assertEqual([x["name"] for _, x in picks], ["A", "B"])


class Offers(unittest.TestCase):
    def setUp(self):
        # I'm deep at RB and weak at WR; they're the mirror image
        self.mine = roster(p("My QB", "QB", 20, 5000), p("My RB1", "RB", 16, 5000), p("My RB2", "RB", 14, 4000),
                           p("My RB3", "RB", 13.5, 3800), p("My WR1", "WR", 12, 3000), p("My WR2", "WR", 6, 600),
                           p("My TE", "TE", 9, 1200))
        self.them = {"name": "Rival", "players": roster(
            p("Their QB", "QB", 19, 5000), p("Their RB1", "RB", 13, 3000), p("Their RB2", "RB", 5, 400),
            p("Their WR1", "WR", 16, 5000), p("Their WR2", "WR", 14, 3900), p("Their WR3", "WR", 13, 3500),
            p("Their TE", "TE", 8, 1000))}

    def test_fair_swap_that_helps_both(self):
        found = trades.offers(NO_FLEX, self.mine, [self.them])
        o = found[0]                                    # surplus RB3 for their WR2: both lineups jump
        self.assertEqual((o["give"], o["get"], o["my_gain"], o["their_gain"]),
                         (["My RB3 (RB)"], ["Their WR2 (WR)"], 8, 7.5))
        self.assertIn("Their WR2 starts for you", o["why"])
        self.assertIn("My RB3 starts for them over Their RB2 (5/gm)", o["why"])
        for o in found:
            self.assertTrue(trades.fair(o["give_value"], o["get_value"]))
        ids = [x for o in found for x in o["give"] + o["get"]]
        self.assertEqual(len(ids), len(set(ids)))       # no player in two offers

    def test_unfair_or_one_sided_deals_are_dropped(self):
        for x in self.them["players"]:
            x["val"] *= 3                               # everything they have is worth far more
        self.assertEqual(trades.offers(NO_FLEX, self.mine, [self.them]), [])
        for x in self.them["players"]:
            x["val"] //= 3
        self.them["players"] = [x for x in self.them["players"] if x["positions"] != ["RB"]] + \
            [p("Their RB1", "RB", 25, 3000), p("Their RB2", "RB", 24, 3000)]
        # they no longer need a running back, so nothing I offer at RB starts for them
        self.assertFalse(any("RB" in g for o in trades.offers(NO_FLEX, self.mine, [self.them]) for g in o["give"]))

    def test_package_discount(self):
        self.assertEqual(trades.package([1000, 3000]), 3000 + 800)
        self.assertTrue(trades.fair(3800, 3500))
        self.assertFalse(trades.fair(4000, 3500))

    def test_finder_names_weak_spot(self):
        lines = trades.finder(NO_FLEX, self.mine, [self.them, {"name": "B", "players": self.them["players"]}])
        self.assertTrue(any(l.startswith("Weak spot: WR (My WR2 6/gm, 3rd of 3)") for l in lines))


class Waivers(unittest.TestCase):
    def setUp(self):
        self.starters = [p("QB1", "QB", 20, 5000, slot="QB"), p("RB1", "RB", 15, 4000, slot="RB"),
                         p("RB2", "RB", 12, 3000, slot="RB"), p("WR1", "WR", 14, 4000, slot="WR"),
                         p("WR2", "WR", 10, 1500, slot="WR"), p("TE1", "TE", 8, 900, slot="TE"),
                         p("WR3", "WR", 9, 1000, slot="FLEX"), p("K1", "K", 0, 0, proj=6, slot="K"),
                         p("D1", "DEF", 0, 0, proj=5, slot="DEF")]
        self.bench = [p("Stash", "RB", 1, 2500), p("Scrub WR", "WR", 4, 50), p("Backup QB", "QB", 12, 300),
                      p("Bye RB", "RB", 8, 400, proj=0, bye=True)]

    def run_adds(self, fas, **kw):
        return waivers.adds(self.starters, self.bench, fas, SLOTS, **kw)

    def test_drops_the_weakest_bench_player_never_a_dynasty_stash(self):
        found = self.run_adds([p("Hot WR", "WR", 11, 800)], dynasty=True)
        self.assertEqual(found[0]["drop"]["name"], "Scrub WR")
        self.assertGreater(found[0]["gain"], 0)          # 11/gm beats WR3's 9 in the flex
        redraft = self.run_adds([p("Hot WR", "WR", 11, 800)])
        self.assertEqual(redraft[0]["drop"]["name"], "Stash")   # 1/gm and no dynasty: fair game

    def test_bye_week_does_not_make_a_player_droppable(self):
        self.assertGreater(waivers.score(self.bench[3], rostered=True), waivers.score(self.bench[3]))

    def test_backup_only_replaces_his_own_position(self):
        found = self.run_adds([p("Spare QB", "QB", 14, 400)])
        self.assertEqual(found[0]["drop"]["name"], "Backup QB")
        self.assertEqual(found[0]["gain"], 0)

    def test_open_spot_and_faab_bid(self):
        found = self.run_adds([p("Hot WR", "WR", 13, 800)], open_spots=1, faab=40, budget=100)
        self.assertIsNone(found[0]["drop"])
        lo, hi = found[0]["bid"]
        self.assertTrue(1 <= lo <= hi <= 40)
        self.assertIn("into your open roster spot", waivers.line(found[0]))
        self.assertEqual(waivers.bid(10, 100, 12), (12, 12))   # capped by what's left

    def test_streams_one_kicker_for_a_dollar(self):
        found = self.run_adds([p("K2", "K", 0, 0, proj=9), p("K3", "K", 0, 0, proj=8.5)], faab=50, budget=100)
        self.assertEqual([a["fa"]["name"] for a in found], ["K2"])
        self.assertEqual(found[0]["bid"], (0, 1))
        self.assertEqual(found[0]["drop"]["name"], "K1")


class Values(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = values.CACHE, values.get_json, values.ROS_FILE
        values.CACHE = Path(self.tmp.name)
        values.ROS_FILE = values.CACHE / "ros.json"
        self.calls = []

        def fake(url, params=None, **kw):
            self.calls.append(url)
            if "fantasycalc" in url:
                return [{"player": {"sleeperId": "1", "espnId": "99", "name": "A", "position": "WR"},
                         "value": 5000, "redraftValue": 4000},
                        {"player": {"sleeperId": "2", "name": "Pick", "position": "PICK"}, "value": 900}]
            week = int(url.rsplit("/", 1)[1])
            rows = [{"player_id": "1", "team": "NYJ", "stats": {"gp": 1, "rec": 5, "rec_yd": 60, "pts_ppr": 11}}]
            if week != 9:  # NYJ on bye in week 9
                rows.append({"player_id": "3", "team": "BUF", "stats": {"gp": 1, "rec": 1}})
            return rows if week != 9 else [{"player_id": "3", "team": "BUF", "stats": {"gp": 1, "rec": 1}}]
        values.get_json = fake

    def tearDown(self):
        values.CACHE, values.get_json, values.ROS_FILE = self.orig
        self.tmp.cleanup()

    def test_fantasycalc_cached_and_filtered(self):
        v = values.fantasycalc(True, 2, 12, 1)
        self.assertEqual(v, {"1": {"value": 5000, "redraft": 4000, "name": "A", "pos": "WR", "espn": "99"}})
        values.fantasycalc(True, 2, 12, 1)
        self.assertEqual(len(self.calls), 1)

    def test_ros_ppg_skips_byes(self):
        ros = values.ros_projections(2026, 8)
        self.assertEqual(sorted(ros["weeks"]), ["10", "11", "8", "9"])
        self.assertNotIn("pts_ppr", ros["weeks"]["8"]["stats"]["1"])
        self.assertEqual(values.ros_ppg(ros, "1", "NYJ", {"rec": 1, "rec_yd": 0.1}), 11.0)

    def test_settings(self):
        self.assertEqual(values.fc_settings(["QB", "RB", "SUPER_FLEX"], 12, {"rec": 1}), (2, 12, 1))
        self.assertEqual(values.fc_settings(["QB", "QB", "RB"], 10, {"rec": 0.5}), (2, 10, 0.5))
        self.assertEqual(values.fc_settings(["QB", "RB"], 18, {}), (1, 18, 0))
        self.assertEqual(values.espn_scoring([{"statId": 53, "points": 1.0}, {"statId": 999, "points": 3}]), {"rec": 1.0})

    def test_annotate_espn_league_maps_ids_through_fantasycalc(self):
        class Ctx:
            players = {"1": {"team": "NYJ"}}
            def ros(self):
                return values.ros_projections(2026, 8)
            def espn_to_sleeper(self):
                return {}
            def match(self, *a):
                return None

        class Lg:
            platform, sport, dynasty, team_count, slots, ctx = "espn", "nfl", False, 12, ["QB", "WR"], Ctx()
            starters = [{"id": "espn99", "key": 99, "name": "A", "positions": ["WR", "FLEX"], "team": "NYJ", "proj": 0}]
            bench, free_agents, others = [], [], []
            def value_scoring(self):
                return {"rec": 1, "rec_yd": 0.1}
        lg = Lg()
        self.assertTrue(values.annotate(lg))
        self.assertEqual((lg.starters[0]["sid"], lg.starters[0]["val"], lg.starters[0]["ppg"]), ("1", 4000, 11.0))


class EspnSnapshotShape(unittest.TestCase):
    def test_compact_carries_other_rosters_scoring_and_faab(self):
        entry = lambda pid, slot: {"lineupSlotId": slot, "playerPoolEntry": {"player": {
            "id": pid, "fullName": f"P{pid}", "proTeamId": 1, "eligibleSlots": [4, 23], "defaultPositionId": 3}}}
        raw = {"id": 5, "seasonId": 2026, "scoringPeriodId": 8, "status": {"currentMatchupPeriod": 8},
               "settings": {"name": "L", "size": 2, "scoringSettings": {"scoringType": "H2H_POINTS",
                                                                     "scoringItems": [{"statId": 53, "points": 0.5}]},
                            "rosterSettings": {"lineupSlotCounts": {"4": 2, "20": 5}},
                            "tradeSettings": {"deadlineDate": 1797580800000},
                            "acquisitionSettings": {"isUsingAcquisitionBudget": True, "acquisitionBudget": 100}},
               "teams": [{"id": 1, "name": "Me", "transactionCounter": {"acquisitionBudgetSpent": 30},
                          "roster": {"entries": [entry(10, 4)]}},
                         {"id": 2, "name": "Them", "roster": {"entries": [entry(20, 20)]}}], "schedule": []}
        snap = espn_fantasy.compact(raw, "nfl", 1)
        self.assertEqual(snap["teams"], [{"id": 2, "name": "Them", "roster": [snap["teams"][0]["roster"][0]]}])
        self.assertEqual(snap["teams"][0]["roster"][0]["name"], "P20")
        self.assertEqual((snap["size"], snap["scoring"], snap["faab"]), (2, {"rec": 0.5}, {"budget": 100, "spent": 30}))
        self.assertTrue(snap["trade_deadline"].startswith("2026-12"))
        from shq import save_espn
        self.assertIn('STATS = {"3": "pass_yd"', save_espn.js())
        self.assertNotIn("__STATS__", save_espn.js())


class AdviceWithoutValues(unittest.TestCase):
    def test_nba_and_bare_leagues_have_no_trade_block(self):
        class Lg:
            sport, platform, starters, bench, free_agents = "nba", "espn", [], [], []
        self.assertIsNone(advice.trade_block(Lg()))


if __name__ == "__main__":
    unittest.main()
