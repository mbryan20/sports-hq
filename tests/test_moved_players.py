"""Model health's weekly check of traded, injured and newly starting players (shq/health.py moved_week / moved_health /
moved_checks): Q-043's rules against what actually happened. No network: git versions of docs/data/players_nfl.json
and state/ir_seen.json and Sleeper's stats and projections are faked."""
import copy
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import health

UTC = dt.timezone.utc
K = dt.datetime(2026, 11, 13, 1, 15, tzinfo=UTC)          # week 10's first kickoff (Thursday night)
THU, SUN = "2026-11-13T01:15:00+00:00", "2026-11-15T18:00:00+00:00"
DAY = 86400
SCORING = {"rec": 1, "rec_yd": 0.1, "rush_yd": 0.1, "pass_yd": 0.04, "pass_td": 4, "rec_td": 6, "rush_td": 6}
DB = {"100": {"full_name": "Both Leagues", "espn_id": 9100}, "200": {"full_name": "Espn Only", "espn_id": 9200},
      "300": {"full_name": "Name Match", "position": "WR", "team": "GB"}}       # no espn_id: matched by name and team


def P(pid, name, pos, team, proj, inj=None, opp="vs X", kick=SUN):
    return {"id": pid, "name": name, "pos": pos, "team": team, "proj": proj, "inj": inj, "opp": opp, "kick": kick,
            "next": [proj, 5.0, 5.0, 5.0]}


def first_copy():
    domo = [P("1", "Traded Guy", "WR", "KC", 12, kick=THU), P("2", "Ir Guy", "RB", "BAL", 0, "IR"),
            P("3", "Thursday Q", "WR", "NYJ", 9, "Q"), P("4", "Sunday Q", "RB", "DAL", 7, "Q"),
            P("5", "New Qb", "QB", "LV", 15), P("6", "Bye Qb", "QB", "SEA", 17), P("100", "Both Leagues", "WR", "MIA", 10),
            P("50", "Steady A", "WR", "BUF", 10), P("51", "Steady B", "RB", "DET", 8), P("52", "Deep Backup", "RB", "DET", 0),
            P("60", "On Bye", "WR", "PIT", 0, opp="BYE"), P("70", "Kicker", "K", "BUF", 8)]
    stempak = [P("9100", "Both Leagues", "WR", "MIA", 99, "Q"), P("9200", "Espn Only", "TE", "CHI", 4),
               P("9300", "Name Match Jr.", "WR", "GB", 6, "D")]
    stale = [P("50", "Steady A", "WR", "BUF", 50)]                       # a league still on last week: ignored
    return {"leagues": {"Stempak": {"week": 10, "players": stempak}, "Domo Arigato": {"week": 10, "players": domo},
                        "Guillotine": {"week": 9, "players": stale}}}


def sunday_copy():
    d = copy.deepcopy(first_copy())
    p3 = next(p for p in d["leagues"]["Domo Arigato"]["players"] if p["id"] == "3")
    p3.update(inj="OUT", proj=0.0)                                        # ruled out Friday: the site showed 0 by Sunday
    return d


OLD = {"leagues": {"Domo Arigato": {"week": 8, "players": [P("1", "Traded Guy", "WR", "IND", 11), P("5", "New Qb", "QB", "LV", 0)]}}}
FILES = {("old", health.PLAYERS_NFL): OLD, ("v1", health.PLAYERS_NFL): first_copy(), ("v2", health.PLAYERS_NFL): sunday_copy(),
         ("ir1", health.IR_SEEN_PATH): {"espn:9200": {"last": "2026-11-12", "first": "2026-11-11T00:57:00Z", "placed": None}}}
VERSIONS = [(int((K - dt.timedelta(days=15)).timestamp()), "old"), (int((K - dt.timedelta(hours=1)).timestamp()), "v1"),
            (int((K + dt.timedelta(days=2)).timestamp()), "v2")]
IR_VERSIONS = [(int((K - dt.timedelta(days=2)).timestamp()), "ir1")]
STATS = {"1": {"gp": 1, "rec": 5, "rec_yd": 50}, "2": {"gp": 1, "rush_yd": 80}, "3": {"gms_active": 1},
         "5": {"gp": 1, "pass_yd": 250, "pass_td": 1}, "6": {"gp": 1, "pass_yd": 200}, "100": {"gp": 1, "rec": 4, "rec_yd": 40},
         "200": {"gp": 1, "pts_half_ppr": 5.5, "rec": 9}, "50": {"gp": 1, "rec": 6, "rec_yd": 70}, "51": {"gp": 1, "rush_yd": 50},
         "300": {"gp": 1, "pts_half_ppr": 6.2}}
QB9 = [{"player_id": "99", "team": "LV", "opponent": "SF", "stats": {"pts_half_ppr": 14}}]     # LV played, New Qb unprojected; SEA on bye
QB8 = [{"player_id": "6", "team": "SEA", "opponent": "ARI", "stats": {"pts_half_ppr": 18}}]
ALL8 = [{"player_id": "1", "team": "IND", "opponent": "HOU"}, {"player_id": "50", "team": "BUF", "opponent": "MIA"}]


class Fetch:
    def __init__(self):
        self.calls = []

    def __call__(self, url, params=None):
        self.calls.append(url)
        if url.endswith("/stats/nfl/regular/2026/10"):
            return STATS
        qb_only = [v for k, v in (params or []) if k == "position[]"] == ["QB"]
        if url.endswith("/projections/nfl/2026/9"):
            return QB9 if qb_only else []
        if url.endswith("/projections/nfl/2026/8"):
            return QB8 if qb_only else ALL8
        raise AssertionError(f"unexpected fetch {url}")


def load(sha, path):
    return copy.deepcopy(FILES[(sha, path)])


def scoring_of(name):
    return SCORING if name == "Domo Arigato" else None                  # Stempak unreadable: half-PPR


def week10(versions=VERSIONS, fetch=None):
    return health.moved_week(10, K.timestamp(), versions, IR_VERSIONS, load, fetch or Fetch(), DB, scoring_of)


class MovedWeek(unittest.TestCase):
    def setUp(self):
        self.x = week10()
        self.by = {g["name"]: g for g in self.x["group"]}

    def test_who_is_in_the_group_and_why(self):
        x, by = self.x, self.by
        self.assertEqual(sorted(by), ["Both Leagues", "Espn Only", "Ir Guy", "Name Match Jr.", "New Qb", "Sunday Q", "Thursday Q",
                                      "Traded Guy"])
        self.assertEqual(by["Traded Guy"]["why"], ["new team (IND to KC)"])
        self.assertEqual(by["Ir Guy"]["why"], ["tagged IR"])
        self.assertEqual(by["Thursday Q"]["why"], ["tagged OUT"])                 # worst tag, his game's copy included
        self.assertEqual(by["Both Leagues"]["why"], ["tagged Q"])                 # ESPN league's tag, Sleeper id via espn_id
        self.assertEqual(by["Espn Only"]["why"], ["on our IR list"])              # state/ir_seen.json "espn:9200"
        self.assertEqual(by["New Qb"]["why"], ["new starter (projected 0 the week before)"])
        self.assertNotIn("Bye Qb", by)          # bye the week before: compared with the week before that (18)
        self.assertEqual(by["Name Match Jr."]["why"], ["tagged D"])
        self.assertEqual((x["n"], x["n_others"], x["tagged"], x["new_team"], x["new_starters"]), (8, 4, 6, 1, 1))
        self.assertEqual(x["teams_from"], "the players file as of Oct 29")
        self.assertEqual((x["players_version"], x["players_as_of"]), ("v1", "2026-11-13T00:15:00Z"))

    def test_projection_and_points(self):
        by = self.by
        self.assertEqual((by["Both Leagues"]["proj"], by["Both Leagues"]["actual"]), (10, 8.0))   # Sleeper league's row, its scoring
        self.assertEqual(by["Espn Only"]["actual"], 5.5)                                         # half-PPR when scoring unknown
        self.assertEqual((by["Thursday Q"]["proj"], by["Thursday Q"]["played"]), (0.0, False))   # Sunday's copy: 0, no miss
        self.assertEqual(by["Traded Guy"]["actual"], 10.0)

    def test_misses_and_error(self):
        x = self.x
        self.assertEqual((x["zeroed"], x["inactive"], x["flagged_total"]), (1, 1, 1 + 1))
        self.assertEqual([(f["name"], f["miss"]) for f in x["flagged"]], [("Ir Guy", "zeroed"), ("Sunday Q", "inactive")])
        # group: |12-10| + |0-8| + |7-0| + |15-14| + |10-8| + |4-5.5| + |6-6.2| over 7 (Thursday Q projected 0 and sat: left out)
        self.assertEqual((x["mae"], x["mae_n"]), (3.1, 7))
        # everyone else: Bye Qb 9, Steady A 3, Steady B 3 (Deep Backup 0 and sat; the bye and the kicker are left out)
        self.assertEqual((x["others_mae"], x["others_mae_n"]), (5.0, 3))

    def test_notes_in_plain_english(self):
        notes = health.moved_notes({"10": self.x})
        self.assertTrue(notes[0].startswith("Week 10: 8 players were hurt, on a new team or newly starting going in"), notes[0])
        self.assertIn("1 we projected at 0 scored 5+; 1 we projected at 5+ did not play", notes[0])
        self.assertIn("Week 10: Ir Guy (BAL, tagged IR): we projected 0, he scored 8.", notes)
        self.assertIn("Week 10: Sunday Q (DAL, tagged Q): we projected 7, he did not play.", notes)
        self.assertIn("the players file as of Oct 29", notes[-1])

    def test_team_14_days_back_from_sleeper_when_the_file_is_younger(self):
        f = Fetch()
        x = week10(versions=VERSIONS[1:], fetch=f)
        self.assertEqual(x["teams_from"], "Sleeper's week-8 projections")
        self.assertIn("new team (IND to KC)", {g["name"]: g for g in x["group"]}["Traded Guy"]["why"])

    def test_nothing_before_the_first_copy(self):
        self.assertIsNone(week10(versions=VERSIONS[2:]))           # only a copy from after the kickoff


class MovedHealth(unittest.TestCase):
    STORED = {"9": {"v": health.MOVED_V, "week": 9, "n": 3}}

    def test_stored_weeks_kept_and_a_week_waits_for_monday_night(self):
        f = Fetch()
        h = health.moved_health(K + dt.timedelta(days=4), fetch=f, versions=VERSIONS, ir_versions=IR_VERSIONS, load=load,
                                first_kicks={10: K}, last=10, previous=self.STORED, db=DB, scoring_of=scoring_of)
        self.assertEqual(list(h["weeks"]), ["9"])
        self.assertEqual(f.calls, [])                              # nothing re-fetched or recomputed
        h = health.moved_health(K + dt.timedelta(days=5, hours=7), fetch=f, versions=VERSIONS, ir_versions=IR_VERSIONS,
                                load=load, first_kicks={10: K}, last=10, previous=self.STORED, db=DB, scoring_of=scoring_of)
        self.assertEqual(list(h["weeks"]), ["9", "10"])
        self.assertEqual(h["weeks"]["9"], self.STORED["9"])
        self.assertEqual(h["weeks"]["10"]["zeroed"], 1)

    def test_an_old_format_week_is_recomputed(self):
        h = health.moved_health(K + dt.timedelta(days=6), fetch=Fetch(), versions=VERSIONS, ir_versions=IR_VERSIONS, load=load,
                                first_kicks={10: K}, last=10, previous={"10": {"v": 0}}, db=DB, scoring_of=scoring_of)
        self.assertEqual(h["weeks"]["10"]["v"], health.MOVED_V)


class MovedChecks(unittest.TestCase):
    def judge(self, base):
        return lambda cid, value, n: health.judge(cid, value, n, base, "2026-11-18")

    def test_quiet_week_is_info(self):
        checks = health.moved_checks({"10": week10()}, self.judge({}))
        self.assertEqual({c["id"]: c["status"] for c in checks},
                         {"moved.zeroed": "info", "moved.inactive": "info", "moved.mae": "info", "moved.others_mae": "info",
                          "moved.mae_gap": "info"})
        self.assertEqual(next(c for c in checks if c["id"] == "moved.mae_gap")["value"], -1.9)
        self.assertTrue(all(c["week"] == 10 for c in checks))

    def test_judged_against_a_baseline_with_ten_or_more(self):
        base = {}
        week = {"week": 11, "n": 40, "n_others": 300, "zeroed": 0, "inactive": 1, "mae": 4.0, "others_mae": 3.5}
        first = {c["id"]: c["status"] for c in health.moved_checks({"11": week}, self.judge(base))}
        self.assertEqual((first["moved.zeroed"], first["moved.mae_gap"]), ("ok", "ok"))
        self.assertEqual(base["moved.zeroed"]["value"], 0)
        worse = {c["id"]: c["status"] for c in health.moved_checks({"12": {**week, "week": 12, "zeroed": 3, "mae": 6.0}},
                                                                   self.judge(base))}
        self.assertEqual((worse["moved.zeroed"], worse["moved.mae_gap"]), ("drift", "drift"))

    def test_waiting_before_any_week(self):
        checks = health.moved_checks({}, self.judge({}))
        self.assertTrue(all(c["status"] == "waiting" for c in checks))
        self.assertIn("Waiting for week 9", health.moved_notes({})[0])


if __name__ == "__main__":
    unittest.main()
