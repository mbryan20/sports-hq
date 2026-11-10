"""Q-047: the Weekly plan, the Today check and the league tiles agree with the live league page (fixtures, no network)."""
import datetime as dt
import os
import unittest
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import advice, digest, guillotine, health, notify, run, wrapup, wrapup_render
from shq.leagues import view

UTC = dt.timezone.utc
TUE_5PM = dt.datetime(2026, 11, 10, 23, 0, tzinfo=UTC)        # Tue 5:00pm CST
TUE_8AM = dt.datetime(2026, 11, 10, 14, 2, tzinfo=UTC)
SUN = dt.datetime(2026, 11, 15, 18, 0, tzinfo=UTC)


def p(name, slot, positions, *, status=None, bye=False, proj=10.0, why=""):
    return {"id": name, "key": None, "name": name, "slot": slot, "positions": positions, "status": status, "why": why,
            "kickoff": None if bye else SUN, "started": False, "bye": bye, "proj": proj, "team": "X", "opp": "Y"}


class League:
    sport, free_agents, opponent, opp_proj, platform, week = "nfl", [], "Rival", 120.0, "espn", 10

    def __init__(self, name, starters, bench):
        self.name, self.starters, self.bench = name, starters, bench

    def best_fa(self, positions, now):
        return None


def stempak():
    """Stempak on Nov 10: Malik Willis on IR in the QB slot, still carrying a 16-point projection."""
    return League("Stempak", [p("Josh Allen", "QB", ["QB"], proj=27.9), p("Malik Willis", "QB", ["QB"], status="IR", proj=16.0),
                              p("Chase Brown", "FLEX", ["RB"], proj=13.6)],
                  [p("Zay Flowers", "BN", ["WR"], proj=14.6)])


class LeagueTotal(unittest.TestCase):
    def test_starter_on_ir_counts_zero_in_the_tile_total(self):
        lg = stempak()
        v = view(lg, advice.build(lg, TUE_5PM))
        self.assertEqual(v["proj"], 41.5)                      # 27.9 + 13.6, not 57.5 with Willis
        self.assertTrue(v["advice"]["matchup"].startswith("41.5 vs 120.0"))   # tile and headline agree

    def test_bye_out_doubtful_and_empty_count_zero(self):
        lg = League("T", [p("A", "QB", ["QB"], proj=20), p("B", "RB", ["RB"], bye=True, proj=9),
                          p("C", "WR", ["WR"], status="OUT", proj=8), p("D", "TE", ["TE"], status="D", proj=7),
                          {**p("E", "K", ["K"], proj=5), "empty": True}, p("F", "WR", ["WR"], status="Q", proj=6)], [])
        self.assertEqual(view(lg)["proj"], 26.0)                # healthy 20 + Questionable 6


class WeeklyPlan(unittest.TestCase):
    TUESDAY = {"generated": "2026-11-10T13:02:35Z", "week": 10, "leagues": [
        {"name": "Domo Arigato", "week": 10, "start_sit": ["Start Zach Charbonnet (12.8) over Rhamondre Stevenson (OUT) at RB"],
         "adds": ["Add Drew Lock (QB, SEA, 5.4/gm, value 1,134) into your open roster spot: fills in at QB in week 10, +5.6 pts over the next 4 weeks. Bid $1–3",
                  "Add Chris Boswell (K, PIT, 8.2 proj this week), drop Jake Elliott (0 proj). Bid $0–1"]},
        {"name": "Stempak", "week": 10, "start_sit": ["Start Zay Flowers (14.6) over Chase Brown (13.6) at FLEX"],
         "adds": ["Add Aaron Rodgers (QB, PIT, 18.3/gm, value 1,523) for Chig Okonkwo (TE, your TE3, 9.1/gm): fills in at QB in week 10, +7.9 pts over the next 4 weeks",
                  "Add Jordyn Tyson (WR, NO, 11.2/gm, value 1,063) for Josh Downs (WR, your WR5, 9.3/gm): better backup WR, +1.9 pts over the next 4 weeks"]},
        {"name": "Ball is Life", "week": 4, "start_sit": ["Fewest games left this week: Jaden McDaniels (2)"],
         "adds": ["Drop Draymond Green (2 games this week, value -2.9/g), add Isaiah Jackson (PF/C, LAC, 3 games this week, value -2.8/g, 6% rostered): +8.0 this week (helps FG%, PTS, STL)."]}]}
    DOMO_FIXES = ["Caleb Williams (QB) on BYE → add Kyle McCord (MIA, 12.4 proj) into your open roster spot and start him (Carson Wentz projects 0)",
                  "Rhamondre Stevenson (RB) OUT (Sleeper: Out) → start Zach Charbonnet (12.8 proj)",
                  "Jake Elliott (K) on BYE → no bench fit: add Dominic Zvada (NYG, 8.7 proj), drop Jake Elliott (0 proj), and start him"]
    DOMO_ADDS = ["Add Drew Lock (QB, SEA, 15.7/gm, value 1,131) into your open roster spot: fills in at QB in weeks 10, 13, +10.7 pts over the next 4 weeks. Bid $1–3",
                 "Add Dominic Zvada (K, NYG, 8.7 proj this week), drop Jake Elliott (0 proj). Bid $0–1"]
    BIL_ADDS = ["Drop Obi Toppin (3 games this week, value -4.2/g), add Mo Bamba (C, UTAH, 4 games this week, value -3.1/g, 3% rostered): +18.5 this week (helps BLK, REB, FG%).",
                "Drop Ryan Dunn (3 games this week, value -5.5/g), add Isaiah Jackson (PF/C, LAC, 3 games this week, value -1.9/g, 6% rostered): +12.2 this week (helps REB, BLK, FG%)."]

    def setUp(self):
        import copy
        self.weekly = copy.deepcopy(self.TUESDAY)
        self.domo = League("Domo Arigato", [p("Caleb Williams", "QB", ["QB"], bye=True, proj=0),
                                            p("Rhamondre Stevenson", "RB", ["RB"], status="OUT", proj=0),
                                            p("Jake Elliott", "K", ["K"], bye=True, proj=0)],
                           [p("Zach Charbonnet", "BN", ["RB"], proj=12.8)])
        self.st = stempak()
        st_adv = advice.build(self.st, TUE_5PM)
        self.views = {"Domo Arigato": {"advice": {"fixes": self.DOMO_FIXES, "adds": self.DOMO_ADDS}},
                      "Stempak": {"advice": st_adv},
                      "Ball is Life": {"advice": {"fixes": [], "adds": self.BIL_ADDS}}}

    def test_every_run_takes_the_live_fixes_and_adds_and_keeps_tuesdays_list(self):
        w = run.refresh_weekly(self.weekly, [self.domo, self.st], self.views, TUE_5PM)
        domo, stem, bil = w["leagues"]
        self.assertEqual(domo["start_sit"], self.DOMO_FIXES)     # QB and K bye fixes included, no duplicate RB line
        self.assertEqual(domo["adds"], self.DOMO_ADDS)
        self.assertEqual(domo["plan_adds"], self.TUESDAY["leagues"][0]["adds"])
        self.assertEqual(domo["plan_changed"], [self.TUESDAY["leagues"][0]["adds"][1]])   # Boswell, now Zvada
        # Stempak: the Willis IR fix leads, then the healthy upgrade
        self.assertTrue(stem["start_sit"][0].startswith("Malik Willis (QB) IR"))
        self.assertEqual(stem["start_sit"][-1], "Start Zay Flowers (14.6) over Chase Brown (13.6) at FLEX")
        # basketball: same add, different drop is a changed move
        self.assertEqual(bil["adds"], self.BIL_ADDS)
        self.assertEqual(bil["plan_changed"], self.TUESDAY["leagues"][2]["adds"])
        self.assertEqual(w["generated"], "2026-11-10T13:02:35Z")   # Tuesday's framing stays
        self.assertEqual(w["start_sit_updated"], "2026-11-10T23:00:00Z")

    def test_tuesdays_list_is_kept_across_runs_and_stale_views_change_nothing(self):
        run.refresh_weekly(self.weekly, [self.domo], self.views, TUE_5PM)
        self.views["Domo Arigato"]["advice"]["adds"] = self.DOMO_ADDS[:1]
        self.views["Ball is Life"] = {"stale": True, "advice": {"adds": ["Add Nobody (C, X)"]}}
        w = run.refresh_weekly(self.weekly, [self.domo], self.views, TUE_5PM)
        self.assertEqual(w["leagues"][0]["plan_adds"], self.TUESDAY["leagues"][0]["adds"])
        self.assertEqual(w["leagues"][2]["adds"], self.BIL_ADDS)       # the stale league keeps its last live list

    def test_tuesday_build_uses_the_same_runs_advice(self):
        sec = run.weekly_section(self.domo, self.views["Domo Arigato"]["advice"])
        self.assertEqual((sec["start_sit"], sec["adds"]), (self.DOMO_FIXES, self.DOMO_ADDS))

    def test_add_keys(self):
        self.assertEqual(run.add_key(self.DOMO_ADDS[1]), ("Dominic Zvada", "Jake Elliott"))
        self.assertEqual(run.add_key(self.TUESDAY["leagues"][1]["adds"][1]), ("Jordyn Tyson", "Josh Downs"))
        self.assertEqual(run.add_key(self.DOMO_ADDS[0]), ("Drew Lock", None))
        self.assertEqual(run.add_key(self.BIL_ADDS[1]), ("Isaiah Jackson", "Ryan Dunn"))
        self.assertEqual(run.add_key("Geno Smith (QB, NYJ, 20.5 proj) for Travis Etienne Jr. (5.0)"),
                         ("Geno Smith", "Travis Etienne Jr."))


class TodayCheck(unittest.TestCase):
    def setUp(self):
        notify.sent.clear()
        self.lg = League("Domo Arigato", [p("Rhamondre Stevenson", "RB", ["RB"], proj=11.8)],
                         [p("Zach Charbonnet", "BN", ["RB"], proj=12.8)])
        self.morning = {"generated": "2026-11-10T14:02:26Z", "title": "Today: 0 things to fix", "items":
                        digest.build([self.lg], TUE_8AM) + [{"league": "Guillotine", "urgent": False, "text": "projected 6 of 9"}]}

    def test_later_run_updates_items_in_place_without_a_push(self):
        self.lg.starters[0]["status"] = "OUT"                      # ruled out after the 8am check
        out = run.refresh_digest(self.morning, [self.lg], TUE_5PM)
        texts = [i["text"] for i in out["items"]]
        self.assertIn("Rhamondre Stevenson (RB) OUT → start Zach Charbonnet (12.8 proj)", texts)
        self.assertEqual(texts, advice.build(self.lg, TUE_5PM)["fixes"] + ["projected 6 of 9"])
        self.assertEqual(out["title"], "Today: 1 thing to fix")
        self.assertEqual(out["generated"], self.morning["generated"])   # still the 8am check, updated in place
        self.assertEqual(out["updated"], "2026-11-10T23:00:00Z")
        self.assertEqual(notify.sent, [])

    def test_unchanged_or_yesterdays_digest_is_left_alone(self):
        self.assertIsNone(run.refresh_digest(self.morning, [self.lg], TUE_5PM))
        old = {**self.morning, "generated": "2026-11-09T14:02:26Z"}
        self.lg.starters[0]["status"] = "OUT"
        self.assertIsNone(run.refresh_digest(old, [self.lg], TUE_5PM))
        self.assertEqual(notify.sent, [])


class GuillotineNames(unittest.TestCase):
    USERS = [{"user_id": "1", "display_name": "damonhawk1", "metadata": {"team_name": "Off with his head"}},
             {"user_id": "2", "display_name": "GoodFellas77", "metadata": {"team_name": " GoodFellas "}},
             {"user_id": "3", "display_name": "robert8063"},
             {"user_id": "4", "display_name": "Same", "metadata": {"team_name": "same"}}]

    def test_team_name_with_username(self):
        self.assertEqual([guillotine.team_label(u) for u in self.USERS],
                         ["Off with his head (damonhawk1)", "GoodFellas (GoodFellas77)", "robert8063", "same"])

    def test_v2_rivals_use_the_same_labels(self):
        v2 = {"bids": [{"sleeper_id": "8228", "name": "Jaylen Warren", "call": "Coin flip", "bid": 2,
                        "likely_rival_bids": [{"team": "damonhawk1", "bid": 16}, {"team": "gone", "bid": 3}]}]}
        row = guillotine.v2_rows(v2, guillotine.labels(self.USERS))[0]
        self.assertEqual(row["rivals"], [{"name": "Off with his head (damonhawk1)", "bid": 16}, {"name": "gone", "bid": 3}])
        self.assertEqual(row["sid"], "8228")

    def test_wrapup_war_room_lines_and_chart_keep_the_whole_name(self):
        views = {"Guillotine": {"advice": {"guillotine": {"labels": guillotine.labels(self.USERS)}}}}
        bids = {"cut": {"team": "GoodFellas77", "week": 9, "confirmed": True},
                "cut_risks": [{"team": "damonhawk1", "cut_risk_next_week": 0.4}]}
        with mock.patch.object(wrapup, "load_json", return_value=bids):
            lines = wrapup.warroom_section(wrapup._v2_names(views))["lines"]
        self.assertEqual(lines[0], "Week 9 cut: GoodFellas (GoodFellas77) (confirmed).")
        self.assertEqual(lines[1], "Most at risk: Off with his head (damonhawk1) 40%.")
        svg = wrapup_render._chart_svg({"title": "t", "bars": [
            {"label": "Off with his head (damonhawk1)", "value": 98.3, "me": False, "low": True},
            {"label": "x" * 40, "value": 120.0, "me": True, "low": False}]})
        self.assertIn(">Off with his head (damonhawk1)</text>", svg)
        self.assertIn(">" + "x" * 31 + "…</text>", svg)


class HealthBids(unittest.TestCase):
    def test_dashboard_rows_come_from_the_old_model_matched_by_sleeper_id(self):
        from test_health import NOW, fake_league
        lg = fake_league()
        lg.db["s3"] = {"full_name": "Harold Fannin Jr.", "position": "TE"}
        lg.txs.append({"transaction_id": "4", "type": "waiver", "status": "complete", "leg": 8, "roster_ids": [2],
                       "adds": {"s3": 2}, "settings": {"waiver_bid": 6}})
        runs = lg.waiver_run(8)
        dash = {"leagues": {"Guillotine": {"advice": {"guillotine": {
            "week": 9, "bid_source": {"name": "War Room v2", "url": "war-room-v2/"},
            "bids": [{"name": "Star One", "sid": "s1", "price": 35, "call": "bid", "v2": True}],     # v2's own call
            "model": {"bids": [{"name": "Star One", "sid": "s1", "price": 33, "max": 38, "call": "bid"},
                               {"name": "Harold Fannin", "price": 7, "max": 9, "call": "bid"}],          # no id: name match
                      "freed": None}}}}}}
        with mock.patch.object(health, "now_utc", return_value=NOW):
            o = health.rec_outcomes(lg, [], [(runs - 60, "d1")], load=lambda sha, path: dash)
        rows = {r["player"]: r for r in o["dash_rows"]}
        self.assertEqual(set(rows), {"Star One", "Harold Fannin"})
        self.assertEqual(rows["Star One"]["bid"], 33)                       # the model's price, not v2's 35
        self.assertEqual((rows["Harold Fannin"]["paid"], rows["Harold Fannin"]["would_win"]), (6, True))

    def test_cut_odds_read_the_new_team_labels(self):
        from test_health import fake_league
        lg = fake_league()
        lg.label = {1: "My Team (me)", 2: "Rival FC (rival)", 3: "other"}
        k = lg.kickoffs[8].timestamp()
        dash = {"leagues": {"Guillotine": {"advice": {"guillotine": {"week": 8, "teams": [
            {"name": "My Team (me)", "cut": 0.2}, {"name": "Rival FC (rival)", "cut": 0.5}, {"name": "other", "cut": 0.3}]}}}}}
        s = health.shown_cut_odds(lg, [], [(k - 50, "d1")], load=lambda sha, path: dash)
        self.assertEqual(s["dashboard"]["cut_team_chance"], 0.3)
        self.assertEqual(s["dashboard"]["ranks"], [2])


if __name__ == "__main__":
    unittest.main()
