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

    def __init__(self):
        self.ir_seen = {}          # values.annotate's IR records (state/ir_seen.json for the real run)

    def ros(self):
        return ROS


def pl(sid, name, pos, status=None, news_at=None):
    return {"id": sid, "name": name, "positions": [pos], "team": None, "proj": 0, "status": status,
            "news": {"note": "x", "at": news_at} if news_at else None}


class Lg:
    platform, sport, dynasty, team_count, slots, scoring = "sleeper", "nfl", False, 12, ["QB", "WR", "WR"], SC

    def __init__(self, players):
        self.ctx, self.starters, self.bench, self.free_agents, self.others = Ctx(), players, [], [], []


def annotate(*players, seen=None):
    saved = values.fantasycalc
    values.fantasycalc = lambda *a: {}
    try:
        lg = Lg(list(players))
        if seen is not None:
            lg.ctx.ir_seen = seen
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
        # Q-043 follow-up: placement comes from the first run that saw the IR tag, not ESPN's latest blurb date
        placed = WEEK_START - dt.timedelta(days=9)
        seen = {WILLIS: {"last": "2026-11-09", "first": values.iso(placed), "placed": values.iso(placed)}}
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW), seen=seen)
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 0.0, 14.0, 14.0])
        self.assertEqual(seen[WILLIS]["last"], "2026-11-10")          # seen again today, placement kept

    def test_unconfirmed_ir_tag_is_not_zeroed(self):
        # status.confirm turns an IR tag ESPN doesn't back into Q: the projections stand
        by = annotate(pl(WILLIS, "Willis", "QB", status="Q", news_at=NOW))
        self.assertEqual([x for _, x in by["Willis"]["wk"]][1:], [14.0, 14.0, 14.0])

    def test_unknown_placement_means_minimum_served(self):
        # Q-043 follow-up: no record and no IR news in the last 7 days = on IR since before tracking began
        self.assertEqual(values.ir_games_left({"status": "IR"}, WEEK_START, None), 0)
        self.assertEqual(values.ir_games_left({"status": "IR"}, WEEK_START, NOW), values.IR_MIN_GAMES)
        self.assertEqual(values.ir_placed({}, "x", {"status": "IR"}, NOW), (None, True))
        old = {"status": "IR", "news": {"at": "2026-09-01T12:00:00Z"}}
        self.assertEqual(values.ir_placed({}, "x", old, NOW)[0], None)


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


# --- Q-043 follow-up (Tue Nov 10 evening): IR placement, really-out players, QB rooms ---------------------------------
LOCK, DARNOLD, MURRAY, ADAMS, EVANS, ETIENNE, STEVENSON, VET = "5854", "4943", "5849", "2133", "2216", "7543", "7611", "77"
RB = lambda rec: {"gp": 1, "rec": rec, "rec_yd": rec * 10}                # same points as WR: rec * 2
ALL2 = {"SEA", "MIN", "NO", "LAR", "SF", "NE", "LV"}
ROS2 = {"weeks": {
    "10": week(ALL2, [(LOCK, "SEA", QB(275, 1.75)), (COUSINS, "MIN", QB(225, 1.25)), (ETIENNE, "NO", RB(4.45))]),
    "11": week(ALL2 - {"SEA"}, [(MURRAY, "MIN", QB(250, 1.5)), (COUSINS, "LV", QB(300, 2)), (ADAMS, "LAR", WR(5)),
                                (EVANS, "SF", WR(9)), (ETIENNE, "NO", RB(4)), (STEVENSON, "NE", RB(6))]),
    "12": week(ALL2, [(DARNOLD, "SEA", QB(250, 1)), (MURRAY, "MIN", QB(250, 1.5)), (ADAMS, "LAR", WR(6)),
                      (EVANS, "SF", WR(9)), (ETIENNE, "NO", RB(4)), (STEVENSON, "NE", RB(6))]),
    "13": week(ALL2, [(DARNOLD, "SEA", QB(300, 2)), (MURRAY, "MIN", QB(250, 1.5)), (EVANS, "SF", WR(9)),
                      (ETIENNE, "NO", RB(4)), (STEVENSON, "NE", RB(5))]),
}}


def live2(team, stats=None, injury=None):
    return {"team": team, "player": {"team": team, "injury_status": injury}, "stats": stats or {}}


class Ctx2(Ctx):
    proj = {LOCK: live2("SEA", QB(275, 1.75)), DARNOLD: live2("SEA", injury="Out"), COUSINS: live2("MIN", QB(225, 1.25)),
            MURRAY: live2("MIN", injury="Out"), ADAMS: live2("LAR", injury="IR"), EVANS: live2("SF", injury="Out"),
            ETIENNE: live2("NO", RB(4.45), injury="IR"), STEVENSON: live2("NE")}
    players = {LOCK: {"team": "SEA", "position": "QB"}, DARNOLD: {"team": "SEA", "position": "QB", "injury_status": "Out"},
               COUSINS: {"team": "LV", "position": "QB"}, MURRAY: {"team": "MIN", "position": "QB", "injury_status": "Out"},
               ADAMS: {"team": "LAR", "injury_status": "IR"}, EVANS: {"team": "SF", "injury_status": "Out"},
               ETIENNE: {"team": "NO", "injury_status": "IR"}, STEVENSON: {"team": "NE"}}

    def ros(self):
        return ROS2


def annotate2(*players, seen=None):
    saved = values.fantasycalc
    values.fantasycalc = lambda *a: {}
    try:
        lg = Lg(list(players))
        lg.ctx = Ctx2()
        if seen is not None:
            lg.ctx.ir_seen = seen
        values.annotate(lg)
    finally:
        values.fantasycalc = saved
    return {p["name"]: [x for _, x in p["wk"]] for p in lg.starters}, {p["name"]: p["ppg"] for p in lg.starters}


def shown(sid, name, pos, status=None, why="", news_at=None):
    return {**pl(sid, name, pos, status, news_at), "why": why}


class IrPlacement(unittest.TestCase):
    def test_ir_player_sleeper_projects_this_week_is_not_zeroed(self):
        # Etienne: IR since Oct 1, ESPN's blurb re-dated tonight, Sleeper projects 8.9 this week. Before: [0, 0, 0, 0]
        seen = {}
        wk, ppg = annotate2(shown(ETIENNE, "Etienne", "RB", "IR", "Sleeper: IR", news_at=NOW), seen=seen)
        self.assertEqual(wk["Etienne"], [8.9, 8.0, 8.0, 8.0])
        self.assertEqual(seen[ETIENNE]["placed"], None)        # first sight while projected to play: minimum served

    def test_record_from_weeks_ago_beats_a_fresh_blurb(self):
        # still IR and not projected this week, but the record says placed Oct 1: the minimum is served
        seen = {WILLIS: {"last": "2026-11-09", "first": "2026-10-01T15:00:00Z", "placed": "2026-10-01T15:00:00Z"}}
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW), seen=seen)
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 14.0, 14.0, 14.0])      # before: [0, 0, 0, 0]

    def test_no_record_and_old_news_means_served(self):
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=WEEK_START - dt.timedelta(days=9)))
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 14.0, 14.0, 14.0])

    def test_new_stint_after_a_gap_counts_again(self):
        seen = {WILLIS: {"last": "2026-10-20", "first": "2026-10-01T15:00:00Z", "placed": "2026-10-01T15:00:00Z"}}
        by = annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW), seen=seen)
        self.assertEqual([x for _, x in by["Willis"]["wk"]], [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(seen[WILLIS]["placed"], values.iso(NOW))

    def test_records_save_prune_and_merge(self):
        from shq import statemerge
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ir_seen.json"
            values.save_ir_seen({"a": {"last": "2026-11-10", "first": "x", "placed": None},
                                 "old": {"last": "2026-08-01", "first": "x", "placed": None}}, NOW, path)
            self.assertEqual(list(values.load_ir_seen(path)), ["a"])
            other = Path(d) / "theirs.json"
            values.save_ir_seen({"a": {"last": "2026-11-11", "first": "x", "placed": None},
                                 "b": {"last": "2026-11-11", "first": "y", "placed": None}}, NOW, other)
            merged = statemerge.merge_files(path, other)
            self.assertEqual((merged["a"]["last"], sorted(merged)), ("2026-11-11", ["a", "b"]))

    def test_real_context_reads_and_writes_the_state_file_test_contexts_do_not(self):
        from shq.leagues import Context
        with tempfile.TemporaryDirectory() as d:
            saved = values.IR_SEEN
            values.IR_SEEN = Path(d) / "ir_seen.json"
            try:
                annotate(pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW))             # fake context: no file
                self.assertFalse(values.IR_SEEN.exists())
                ctx = Context.__new__(Context)
                for k in ("now", "week", "week_start", "games", "proj", "players", "espn_report", "espn_by_name"):
                    setattr(ctx, k, getattr(Ctx, k))
                ctx._ros = ROS
                lg = Lg([pl(WILLIS, "Willis", "QB", status="IR", news_at=NOW)])
                lg.ctx = ctx
                values.fantasycalc, saved_fc = (lambda *a: {}), values.fantasycalc
                try:
                    values.annotate(lg)
                finally:
                    values.fantasycalc = saved_fc
                self.assertEqual(values.load_ir_seen()[WILLIS]["placed"], values.iso(NOW))
            finally:
                values.IR_SEEN = saved


class ReallyOut(unittest.TestCase):
    def test_ir_tag_softened_to_q_gets_no_fill(self):
        # Davante Adams: Sleeper IR, ESPN Questionable -> shown Q. Before: [11.0, 10.0, 12.0, 11.0] (made-up 11.0s)
        wk, _ = annotate2(shown(ADAMS, "Adams", "WR", "Q", "Sleeper: IR, but ESPN says Questionable: unconfirmed"))
        self.assertEqual(wk["Adams"], [0.0, 10.0, 12.0, 0.0])

    def test_sleeper_out_shown_q_gets_nothing_this_week(self):
        # Mike Evans: Sleeper Out (players file and live row), shown Q. Before: [18.0, 18.0, 18.0, 18.0]
        wk, _ = annotate2(shown(EVANS, "Evans", "WR", "Q", "Sleeper: Out, but ESPN says Questionable: unconfirmed"))
        self.assertEqual(wk["Evans"], [0.0, 18.0, 18.0, 18.0])

    def test_doubtful_counts_as_out(self):
        # Stevenson (ESPN Doubtful). Before: [11.3, 12.0, 12.0, 10.0]
        wk, _ = annotate2(shown(STEVENSON, "Stevenson", "RB", "D", "ESPN: Doubtful"))
        self.assertEqual(wk["Stevenson"], [0.0, 12.0, 12.0, 10.0])

    def test_espn_report_tag_counts_for_an_espn_league_player(self):
        class C(Ctx2):
            espn_report = {"4569173": {"status": "Doubtful"}}
        p = {**shown(STEVENSON, "Stevenson", "RB", "Q", "ESPN: Questionable"), "id": "espn4569173", "key": 4569173}
        self.assertEqual(values.raw_status(p, C(), STEVENSON, None), "D")

    def test_healthy_player_without_a_live_row_gets_zero_this_week_not_his_average(self):
        ros = {"weeks": {"10": week({"SF"}, []), "11": week({"SF"}, [("7", "SF", WR(4))]),
                         "12": week({"SF"}, [("7", "SF", WR(5))])}}
        fills = values.week_fills(ros, "7", "SF", SC, values.per_game(ros, "7", "SF", SC), None, False)
        self.assertEqual([x for _, x in values.ros_weeks(ros, "7", "SF", SC, fills)], [0.0, 8.0, 10.0])


class QbRoom(unittest.TestCase):
    def test_fill_in_starter_is_not_filled_once_the_starter_is_projected_back(self):
        # Lock starts while Darnold is out; Sleeper projects Darnold back in weeks 12-13. Before: [18.0, None, 18.0, 18.0]
        wk, ppg = annotate2(pl(LOCK, "Lock", "QB"))
        self.assertEqual(wk["Lock"], [18.0, None, 0.0, 0.0])
        self.assertEqual(ppg["Lock"], 6.0)

    def test_traded_qb_backs_up_the_starter_projected_back(self):
        # Cousins (MIN this week while Murray is out); Murray projected 16 in weeks 11-13. Before: [14, 14, 14, 14]
        wk, _ = annotate2(pl(COUSINS, "Cousins", "QB"))
        self.assertEqual(wk["Cousins"], [14.0, 0.0, 0.0, 0.0])

    def test_healthy_benched_teammate_does_not_block_the_new_starter(self):
        # Mendoza: LV's new starter; a healthy vet still on LV keeps stale starter rows in weeks 11-12
        ros = {"weeks": {w: {**ROS["weeks"][w], "stats": dict(ROS["weeks"][w]["stats"]),
                             "team_of": dict(ROS["weeks"][w]["team_of"])} for w in ROS["weeks"]}}
        for w in ("11", "12"):
            ros["weeks"][w]["stats"][VET] = {"pass_yd": 300, "pass_td": 2}
            ros["weeks"][w]["team_of"][VET] = "LV"

        class C(Ctx):
            proj = {**Ctx.proj, VET: live("LV", QB(20, 0))}
            players = {**Ctx.players, VET: {"team": "LV", "position": "QB"}}

            def ros(self):
                return ros
        saved = values.fantasycalc
        values.fantasycalc = lambda *a: {}
        try:
            lg = Lg([pl(MENDOZA, "Mendoza", "QB")])
            lg.ctx = C()
            values.annotate(lg)
        finally:
            values.fantasycalc = saved
        self.assertEqual([x for _, x in lg.starters[0]["wk"]], [16.0, 16.0, 16.0, None])

    def test_other_positions_are_never_blocked(self):
        ros = {"weeks": {"10": week({"SF"}, [("7", "SF", WR(3))]), "11": week({"SF"}, [("8", "SF", QB(300, 2))])}}
        fills = values.week_fills(ros, "7", "SF", SC, 6.0, 6.0, False, Ctx2(), {"8": live2("SF", injury="Out")})
        self.assertEqual(fills, {"10": 6.0, "11": 6.0})


if __name__ == "__main__":
    unittest.main()
