"""Players who changed teams or roles (the Nov 10 2026 trade deadline): rest-of-season numbers when Sleeper's later
weeks still carry the old team or nothing at all, which source decides a player's team and bye, a platform read
that predates a trade, and the IR minimum. Small fixtures, no network."""
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import espn_fantasy, values
from shq.leagues import EspnLeague, make_player

SC = {"rec": 1, "rec_yd": 0.1, "pass_yd": 0.04, "pass_td": 4}
WEEK_START = dt.datetime(2026, 11, 10, 6, 0, tzinfo=dt.timezone.utc)      # Tuesday of week 10
NOW = WEEK_START + dt.timedelta(hours=16)
SUN = dt.datetime(2026, 11, 15, 18, 0, tzinfo=dt.timezone.utc)
LATE = dt.datetime(2026, 11, 15, 21, 5, tzinfo=dt.timezone.utc)

ALLEN, DOWNS, COUSINS, MENDOZA, WILLIS = "1479", "9500", "1166", "13269", "8161"
WR = lambda rec: {"gp": 1, "rec": rec, "rec_yd": rec * 10}               # rec * 2 points
QB = lambda yds, td: {"gp": 1, "pass_yd": yds, "pass_td": td}


def week(teams, rows):
    """A week as values._slim stores it: rows are (pid, team the projection was made for, stats)."""
    return {"teams": sorted(teams), "stats": {pid: {k: v for k, v in s.items() if k != "gp"} for pid, _, s in rows},
            "team_of": {pid: t for pid, t, _ in rows}}


ALL = {"SF", "KC", "MIN", "LV", "MIA", "IND", "DAL", "GB"}
# Sleeper as it stood on deadline night: week 10 rebuilt for the new teams, weeks 11-12 still on the old teams (and
# nothing for the new LV starter), week 13 the IND and LV bye with no rows yet for the traded players' new teams
ROS = {"weeks": {
    "10": week(ALL, [(ALLEN, "SF", WR(3)), (DOWNS, "KC", WR(3.5)), (COUSINS, "MIN", QB(225, 1.25)),
                     (MENDOZA, "LV", QB(250, 1.5))]),
    "11": week(ALL, [(ALLEN, "IND", WR(5)), (DOWNS, "IND", WR(5)), (COUSINS, "LV", QB(300, 2)), (WILLIS, "MIA", QB(250, 1))]),
    "12": week(ALL, [(ALLEN, "IND", WR(5)), (DOWNS, "IND", WR(5)), (COUSINS, "LV", QB(300, 2)), (WILLIS, "MIA", QB(250, 1))]),
    "13": week(ALL - {"IND", "LV"}, [(WILLIS, "MIA", QB(250, 1))]),
}}


def live(team, stats=None, row_team=None):
    """A row of Sleeper's live (this week's) projections."""
    return {"team": row_team or team, "player": {"team": team}, "stats": stats or {}}


class Ctx:
    now, week, week_start = NOW, 10, WEEK_START
    games = {"SF": {"kickoff": LATE, "state": "pre", "opp": "DAL", "home": False},
             "KC": {"kickoff": SUN, "state": "pre", "opp": "ATL", "home": False},
             "MIN": {"kickoff": SUN, "state": "pre", "opp": "GB", "home": False},
             "LV": {"kickoff": LATE, "state": "pre", "opp": "SEA", "home": True},
             "IND": {"kickoff": SUN, "state": "pre", "opp": "MIA", "home": True}}
    proj = {ALLEN: live("SF", WR(3)), DOWNS: live("KC", WR(3.5)), COUSINS: live("MIN", QB(225, 1.25)),
            MENDOZA: live("LV", QB(250, 1.5)), WILLIS: live("MIA")}
    # the Sleeper players file, cached up to 6h: still on the pre-trade teams
    players = {ALLEN: {"team": "IND", "full_name": "Keenan Allen"}, DOWNS: {"team": "IND", "full_name": "Josh Downs"},
               COUSINS: {"team": "LV", "full_name": "Kirk Cousins"}, MENDOZA: {"team": "LV"}, WILLIS: {"team": "MIA"}}
    espn_report, espn_by_name = {}, {}

    def ros(self):
        return ROS


def pl(sid, name, pos, status=None, news_at=None):
    return {"id": sid, "name": name, "positions": [pos], "team": None, "proj": 0, "status": status,
            "news": {"note": "x", "at": news_at} if news_at else None}


class Lg:
    platform, sport, dynasty, team_count, slots, scoring = "sleeper", "nfl", False, 12, ["QB", "WR", "WR"], SC

    def __init__(self, players):
        self.ctx, self.starters, self.bench, self.free_agents, self.others = Ctx(), players, [], [], []


def annotate(*players):
    saved = values.fantasycalc
    values.fantasycalc = lambda *a: {}
    try:
        lg = Lg(list(players))
        values.annotate(lg)
    finally:
        values.fantasycalc = saved
    return {p["name"]: p for p in lg.starters}


class RestOfSeason(unittest.TestCase):
    def test_traded_players_use_their_new_team_projection_not_the_old_one_or_zero(self):
        by = annotate(pl(ALLEN, "Allen", "WR"), pl(COUSINS, "Cousins", "QB"))
        # before: 6, 10, 10 (IND rows) and 0 in week 13 (SF plays, no row), so 6.5/gm
        self.assertEqual(by["Allen"]["wk"], [(10, 6.0), (11, 6.0), (12, 6.0), (13, 6.0)])
        self.assertEqual(by["Allen"]["ppg"], 6.0)
        self.assertEqual([x for _, x in by["Cousins"]["wk"]], [14.0, 14.0, 14.0, 14.0])

    def test_new_starter_without_later_projections_is_not_zero(self):
        by = annotate(pl(MENDOZA, "Mendoza", "QB"))
        # before: [16, 0, 0, None] = 5.3/gm
        self.assertEqual([x for _, x in by["Mendoza"]["wk"]], [16.0, 16.0, 16.0, None])   # LV bye in week 13
        self.assertEqual(by["Mendoza"]["ppg"], 16.0)

    def test_bye_follows_the_live_team_not_the_cached_players_file(self):
        by = annotate(pl(DOWNS, "Downs", "WR"))
        # the players file still says IND (bye in week 13); Sleeper's live projections say KC, who play
        self.assertEqual(by["Downs"]["wk"][-1], (13, 7.0))
        self.assertEqual(by["Downs"]["ppg"], 7.0)

    def test_out_player_gets_no_fill(self):
        by = annotate(pl(ALLEN, "Allen", "WR", status="OUT"))
        self.assertEqual([x for _, x in by["Allen"]["wk"]], [6.0, 10.0, 10.0, 0.0])        # as Sleeper has it

    def test_average_of_current_weeks_when_there_is_no_live_row(self):
        ros = {"weeks": {"10": week({"SF"}, []), "11": week({"SF"}, [("7", "SF", WR(4))]),
                         "12": week({"SF"}, [("7", "SF", WR(5))])}}
        fill = values.per_game(ros, "7", "SF", SC)
        self.assertEqual(fill, 9.0)
        self.assertEqual([x for _, x in values.ros_weeks(ros, "7", "SF", SC, fill)], [9.0, 8.0, 10.0])
        self.assertIsNone(values.per_game(ros, "8", "SF", SC))   # nothing to go on: stays 0 as before


class InjuredReserve(unittest.TestCase):
    def test_fresh_ir_zeroes_the_minimum(self):
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW))
        # before: 0 this week, then 14, 14, 14 from projections made before the move
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(by["Willis"]["ppg"], 0.0)

    def test_ir_placed_two_weeks_ago_has_two_games_left(self):
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=WEEK_START - dt.timedelta(days=9)))
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 0.0, 14.0, 14.0])

    def test_unconfirmed_ir_tag_is_not_zeroed(self):
        # status.confirm turns an IR tag ESPN doesn't back into Q: the projections stand
        by = annotate(pl(WILLIS, "Willis", "QB", status="Q", news_at=NOW))
        self.assertEqual([x for _, x in by["Willis"]["wk"]][1:], [14.0, 14.0, 14.0])

    def test_unknown_date_means_full_minimum(self):
        self.assertEqual(values.ir_games_left({"status": "IR"}, WEEK_START), values.IR_MIN_GAMES)
        self.assertEqual(values.ir_games_left({"status": "IR", "news": {"at": "2026-09-01T12:00:00Z"}}, WEEK_START), 0)


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = values.get_json, values.ROS_FILE
        values.ROS_FILE = Path(self.tmp.name) / "ros.json"
        values.get_json = lambda url, params=None, **kw: [
            {"player_id": "1", "team": "IND", "stats": {"gp": 1, "rec": 5}},
            {"player_id": "2", "team": "KC", "stats": {}}]                    # placeholder row: no game projected

    def tearDown(self):
        values.get_json, values.ROS_FILE = self.orig
        self.tmp.cleanup()

    def test_row_team_is_kept_and_old_cache_shape_is_refetched(self):
        values.save_json(values.ROS_FILE, {"_fetched": 9e12, "key": [2026, 10], "weeks": {}})
        ros = values.ros_projections(2026, 10)
        self.assertEqual(ros["key"], [2026, 10, values.ROS_FORMAT])
        self.assertEqual(ros["weeks"]["10"]["team_of"], {"1": "IND"})
        self.assertEqual(ros["weeks"]["10"]["teams"], ["IND"])


class PlatformTeam(unittest.TestCase):
    def test_yahoo_read_before_the_trade_follows_sleeper(self):
        p = make_player(Ctx(), SC, COUSINS, "QB", name="Kirk Cousins", team="LV", positions=["QB"])
        # before: LV vs SEA at 21:05Z (3 hours late for locking)
        self.assertEqual((p["team"], p["opp"], p["kickoff"], p["bye"]), ("MIN", "@GB", SUN, False))

    def test_platform_team_kept_when_sleeper_agrees_or_has_no_row(self):
        p = make_player(Ctx(), SC, MENDOZA, "QB", name="Fernando Mendoza", team="LV", positions=["QB"])
        self.assertEqual((p["team"], p["opp"]), ("LV", "vs SEA"))
        p = make_player(Ctx(), SC, None, "WR", name="Unmapped", team="IND", positions=["WR"])
        self.assertEqual(p["team"], "IND")

    def test_espn_snapshot_before_the_trade_follows_sleeper(self):
        class ECtx(Ctx):
            def pro_schedule(self, sport, season):
                return {11: {"abbrev": "IND", "games": {10: [(SUN, 15, True)]}},
                        12: {"abbrev": "KC", "games": {10: [(SUN, 1, False)]}},
                        1: {"abbrev": "ATL", "games": {10: [(SUN, 12, True)]}},
                        13: {"abbrev": "LV", "games": {10: [(LATE, 26, True)]}},
                        16: {"abbrev": "MIN", "games": {10: [(SUN, 9, False)]}},
                        9: {"abbrev": "GB", "games": {10: [(SUN, 16, True)]}},
                        15: {"abbrev": "MIA", "games": {10: [(SUN, 11, False)]}}}

            def injury_report(self, sport):
                return {}

            def espn_to_sleeper(self):
                return {"3916148": DOWNS}

            def match(self, name, team, pos):
                return {"Kirk Cousins": COUSINS, "Fernando Mendoza": MENDOZA}.get(name)

        row = lambda pid, name, team, slot, elig: {"id": pid, "name": name, "pro_team": team, "eligible": elig,
                                                   "injury": "ACTIVE", "proj": 10.0, "owned": 50.0, "slot": slot}
        snap = {"captured": "2026-11-10T13:00:00Z", "sport": "nfl", "league_id": 7, "season": 2026, "scoring_period": 10,
                "matchup_period": 10, "opponent": "Them", "slot_counts": {"0": 1, "4": 1, "20": 2},
                "roster": [row(14880, "Kirk Cousins", 13, 0, [0, 20]), row(3916148, "Josh Downs", 11, 4, [4, 23, 20]),
                           row(4837248, "Fernando Mendoza", 13, 20, [0, 20])]}
        saved = espn_fantasy.load_snapshot
        espn_fantasy.load_snapshot = lambda sport, lid: snap
        try:
            lg = EspnLeague(ECtx(), {"name": "Test FB", "sport": "nfl", "league_id": 7, "team_id": 1, "private": True})
        finally:
            espn_fantasy.load_snapshot = saved
        by = {p["name"]: p for p in lg.starters + lg.bench}
        self.assertEqual((by["Kirk Cousins"]["team"], by["Kirk Cousins"]["opp"], by["Kirk Cousins"]["kickoff"]),
                         ("MIN", "@GB", SUN))
        self.assertEqual((by["Josh Downs"]["team"], by["Josh Downs"]["opp"]), ("KC", "@ATL"))
        self.assertEqual((by["Fernando Mendoza"]["team"], by["Fernando Mendoza"]["kickoff"]), ("LV", LATE))


if __name__ == "__main__":
    unittest.main()
