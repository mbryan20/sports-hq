"""Q-057: game-day NBA status from the official NBA injury report and Sleeper (shq/nba_status.py), merged into ESPN's,
and how it feeds the one NBA lineup push a day. Fixtures only: no network, no real push."""
import datetime as dt
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import nba_lineup, nba_status as ns, notify, run
from shq.leagues import EspnLeague, view

UTC = dt.timezone.utc
REPORT_AT = dt.datetime(2026, 11, 12, 23, 30, tzinfo=UTC)      # 5:30pm CT (6:30pm ET) report
TIP = dt.datetime(2026, 11, 13, 1, 0, tzinfo=UTC)              # Thu 7:00pm CT, an 11/12 game on the report
TOMORROW_TIP = TIP + dt.timedelta(days=1)


def words(y, x, text):
    """One table cell as the PDF holds it: one token per word, left to right."""
    out = []
    for w in text.split():
        out.append((y, x, w))
        x += 6 * len(w) + 4
    return out


def header():
    return (words(533.3, 288.1, "Injury Report: 11/12/26 06:30 PM")
            + words(480.1, 23.1, "Game Date") + words(480.1, 119.6, "Game Time") + words(480.1, 200.0, "Matchup")
            + words(480.1, 264.2, "Team") + words(480.1, 425.0, "Player Name") + words(480.1, 585.7, "Current Status")
            + words(480.1, 666.1, "Reason") + words(49.9, 398.5, "Page 1 of 2"))


# page 1: a full row, a two-line reason centred on its row, a rest day, a team that hasn't submitted, the next game
PAGE1 = (header()
         + words(459.1, 24.1, "11/12/2026") + words(459.1, 120.6, "07:00 (ET)") + words(459.1, 201.0, "DET@WAS")
         + words(459.1, 265.2, "Detroit Pistons") + words(459.1, 426.0, "Duren, Jalen") + words(459.1, 586.7, "Out")
         + words(459.1, 667.1, "Injury/Illness - Right Hamstring Strain")
         + words(437.1, 426.0, "Harkless, Elijah") + words(437.1, 586.7, "Questionable") + words(437.1, 667.1, "G League - Two- Way")
         + words(415.0, 265.2, "Washington Wizards") + words(415.0, 667.1, "NOT YET SUBMITTED")
         + words(392.0, 201.0, "TOR@PHI") + words(392.0, 265.2, "Philadelphia 76ers")
         + words(392.0, 426.0, "Embiid, Joel") + words(392.0, 586.7, "Out")
         + words(399.0, 667.1, "Injury Management - Left") + words(385.0, 667.1, "Knee")
         + words(363.0, 426.0, "Johnson Jr., Morez") + words(363.0, 586.7, "Probable")
         + words(363.0, 667.1, "Injury/Illness - Left Shin / Tibia Contusion"))
# page 2: no header row; Philadelphia carries over from page 1, then tomorrow's game
PAGE2 = (words(533.3, 288.1, "Injury Report: 11/12/26 06:30 PM") + words(49.9, 398.5, "Page 2 of 2")
         + words(459.1, 426.0, "Dončić, Luka") + words(459.1, 586.7, "Available")
         + words(459.1, 667.1, "Injury/Illness - Right Thumb Splint")
         + words(437.1, 24.1, "11/13/2026") + words(437.1, 120.6, "07:00 (ET)") + words(437.1, 201.0, "MIL@ORL")
         + words(437.1, 265.2, "Milwaukee Bucks") + words(437.1, 426.0, "Antetokounmpo, Giannis") + words(437.1, 586.7, "Out")
         + words(437.1, 667.1, "Injury Management - Rest"))

ROWS = ns.parse_tokens([PAGE1, PAGE2])

INDEX_HTML = """<a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-12_05_15PM.pdf">5:15</a>
<a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-12_06_30PM.pdf">6:30</a>
<a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-12_11_45AM.pdf">11:45</a>
<a href="https://ak-static.cms.nba.com/wp-content/uploads/sites/4/2026/10/2026-27-Official-NBA-Playing-Rules.pdf">rules</a>"""

SLEEPER_JSON = {
    "1": {"full_name": "Luka Dončić", "team": "LAL", "injury_status": "DTD", "news_updated": 1794456630217},
    "2": {"full_name": "Stephen Curry", "team": "GSW", "injury_status": "Out", "news_updated": 1794462030183},
    "3": {"full_name": "Healthy Guy", "team": "BOS", "injury_status": None},
    "4": {"full_name": "Retired Guy", "team": None, "injury_status": "Out"},
    "5": {"full_name": "Grant Williams", "team": "CHA", "injury_status": "GTD", "news_updated": 1794443729148},
}


def espn(status, at):
    return {"status": status, "date": at, "note": f"{status} note", "url": "https://www.espn.com/nba/player/_/id/1"}


class Parse(unittest.TestCase):
    def test_rows_from_the_pdf_words(self):
        got = [(r["date"], r["team"], r["name"], r["status"], r["reason"]) for r in ROWS]
        self.assertEqual(got, [
            ("2026-11-12", "DET", "Jalen Duren", "Out", "Injury/Illness - Right Hamstring Strain"),
            ("2026-11-12", "DET", "Elijah Harkless", "Questionable", "G League - Two-Way"),
            ("2026-11-12", "WSH", None, None, "NOT YET SUBMITTED"),
            ("2026-11-12", "PHI", "Joel Embiid", "Out", "Injury Management - Left Knee"),       # two-line reason joined
            ("2026-11-12", "PHI", "Morez Johnson Jr.", "Probable", "Injury/Illness - Left Shin / Tibia Contusion"),
            ("2026-11-12", "PHI", "Luka Dončić", "Available", "Injury/Illness - Right Thumb Splint"),  # page 2 carries PHI
            ("2026-11-13", "MIL", "Giannis Antetokounmpo", "Out", "Injury Management - Rest"),
        ])

    def test_short_reasons(self):
        self.assertEqual([ns.short_reason(r) for r in ROWS if r["name"]],
                         ["right hamstring strain", "G League", "rest", "left shin / tibia contusion",
                          "right thumb splint", "rest"])

    def test_newest_link_and_season(self):
        links = ns.report_links(INDEX_HTML)
        self.assertEqual(len(links), 3)
        self.assertTrue(links[0][1].endswith("2026-11-12_06_30PM.pdf"))
        self.assertEqual(links[0][0].astimezone(UTC), REPORT_AT)
        self.assertEqual(ns.season_slug(dt.date(2026, 11, 12)), "2026-27")
        self.assertEqual(ns.season_slug(dt.date(2027, 4, 2)), "2026-27")

    def test_names_match_without_accents_or_suffixes(self):
        self.assertEqual(ns.key("Luka Dončić"), ns.key("Luka Doncic"))
        self.assertEqual(ns.key("Morez Johnson Jr."), "morez johnson")


class Fetch(unittest.TestCase):
    """Caching and never failing a run: both sources go through a fake `get`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = ns.REPORT_FILE, ns.SLEEPER_FILE, ns.pdf_tokens
        ns.REPORT_FILE = Path(self.tmp.name) / "report.json"
        ns.SLEEPER_FILE = Path(self.tmp.name) / "sleeper.json"
        ns.pdf_tokens = lambda data: [PAGE1, PAGE2]
        self.calls = []

    def tearDown(self):
        ns.REPORT_FILE, ns.SLEEPER_FILE, ns.pdf_tokens = self.saved
        self.tmp.cleanup()

    def get(self, url):
        self.calls.append(url)
        if self.down:
            raise ConnectionError("down")

        class R:
            text = INDEX_HTML
            content = b"%PDF"

            @staticmethod
            def json():
                return SLEEPER_JSON
        return R()

    def test_report_reads_newest_pdf_then_reuses_it(self):
        self.down = False
        now = REPORT_AT + dt.timedelta(minutes=5)
        rep = ns.official(now, True, self.get)
        self.assertEqual(rep["at"], "2026-11-12T23:30:00Z")
        self.assertEqual(len(rep["rows"]), 7)
        self.assertEqual(self.calls, ["https://official.nba.com/nba-injury-report-2026-27-season/",
                                      "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-12_06_30PM.pdf"])
        ns.official(now, True, self.get)                       # inside 10 minutes: no read at all
        self.assertEqual(len(self.calls), 2)
        cached = ns.load_json(ns.REPORT_FILE)
        cached["checked"] -= ns.REPORT_EVERY + 1
        ns.save_json(ns.REPORT_FILE, cached)
        ns.official(now, True, self.get)                       # index re-read, same PDF: not downloaded again
        self.assertEqual(len(self.calls), 3)

    def test_source_down_never_raises(self):
        self.down = True
        self.assertIsNone(ns.official(REPORT_AT, True, self.get))
        self.assertEqual(ns.sleeper(REPORT_AT, True, self.get), {})
        saved = ns.official, ns.sleeper
        try:                                                   # the run's loader swallows even an unexpected error
            def boom(*a, **k):
                raise RuntimeError("bug")
            ns.official = ns.sleeper = boom
            feed = ns.load(REPORT_AT)
        finally:
            ns.official, ns.sleeper = saved
        self.assertIsInstance(feed, ns.Feed)
        self.assertFalse(feed)

    def test_down_keeps_last_good_copy(self):
        self.down = False
        ns.official(REPORT_AT, True, self.get)
        ns.sleeper(REPORT_AT, True, self.get)
        for f, k in ((ns.REPORT_FILE, "checked"), (ns.SLEEPER_FILE, "_fetched")):
            c = ns.load_json(f)
            c[k] -= 7 * 3600
            ns.save_json(f, c)
        self.down = True
        self.assertEqual(len(ns.official(REPORT_AT + dt.timedelta(hours=1), True, self.get)["rows"]), 7)
        self.assertIn("luka doncic", ns.sleeper(REPORT_AT, True, self.get))

    def test_sleeper_slim_and_refresh_rate(self):
        self.down = False
        sl = ns.sleeper(REPORT_AT, True, self.get)
        self.assertEqual(sorted(sl), ["grant williams", "luka doncic", "stephen curry"])   # tagged, on a team
        self.assertEqual(sl["stephen curry"][0]["team"], "GS")                              # ESPN's abbreviation
        self.assertEqual(sl["luka doncic"][0]["status"], "DTD")
        ns.sleeper(REPORT_AT, True, self.get)
        self.assertEqual(len(self.calls), 1)                   # cached
        c = ns.load_json(ns.SLEEPER_FILE)
        c["_fetched"] = time.time() - ns.SLEEPER_GAME_DAY - 1
        ns.save_json(ns.SLEEPER_FILE, c)
        ns.sleeper(REPORT_AT, False, self.get)                 # off day: 6 hours
        self.assertEqual(len(self.calls), 1)
        ns.sleeper(REPORT_AT, True, self.get)                  # game day: 45 minutes
        self.assertEqual(len(self.calls), 2)


class Precedence(unittest.TestCase):
    def setUp(self):
        self.feed = ns.Feed({"at": "2026-11-12T23:30:00Z", "rows": ROWS},
                            {ns.key("Grant Williams"): [{"team": "CHA", "status": "GTD", "at": "2026-11-12T22:00:00Z"}],
                             ns.key("Stephen Curry"): [{"team": "GS", "status": "Out", "at": "2026-11-12T22:00:00Z"}]})
        self.healthy = (None, "", None, False)

    def test_official_rest_day_beats_older_espn(self):
        e = espn("Day-To-Day", REPORT_AT - dt.timedelta(hours=3))
        st, why, news, conflict, gd = self.feed.apply(("Q", "ESPN: Day-To-Day", None, False), e, "Joel Embiid", "PHI", TIP)
        self.assertEqual((st, why, conflict), ("OUT", "Out (rest) per NBA injury report, 5:30pm", False))
        self.assertTrue(gd["rest"])
        self.assertEqual(gd["src"], "nba")

    def test_rest_counts_for_that_game_only(self):
        self.assertIsNone(self.feed.row("Joel Embiid", "PHI", TOMORROW_TIP))
        st, *_ , gd = self.feed.apply(self.healthy, None, "Joel Embiid", "PHI", TOMORROW_TIP)
        self.assertEqual((st, gd), (None, None))
        st, why, *_ = self.feed.apply(self.healthy, None, "Giannis Antetokounmpo", "MIL", TIP)
        self.assertIsNone(st)                                  # his rest day is tomorrow's game

    def test_official_available_clears_an_older_espn_out(self):
        e = espn("Out", REPORT_AT - dt.timedelta(days=2))
        st, why, _, conflict, gd = self.feed.apply(("OUT", "ESPN: Out", None, False), e, "Luka Doncic", "LAL", TIP)
        self.assertIsNone(st)                                  # traded since ESPN's read: the one Luka on the report
        self.assertEqual(why, "Available (right thumb splint) per NBA injury report, 5:30pm")

    def test_newer_espn_note_that_disagrees_is_unconfirmed(self):
        e = espn("Day-To-Day", REPORT_AT + dt.timedelta(minutes=20))
        st, why, _, conflict, gd = self.feed.apply(("Q", "ESPN: Day-To-Day", None, False), e, "Jalen Duren", "DET", TIP)
        self.assertEqual((st, conflict), ("Q", True))
        self.assertIn("ESPN's newer note says Day-To-Day: unconfirmed", why)

    def test_newer_espn_note_that_agrees_keeps_espn(self):
        e = espn("Out", REPORT_AT + dt.timedelta(minutes=20))
        base = ("OUT", "ESPN: Out", None, False)
        self.assertEqual(self.feed.apply(base, e, "Jalen Duren", "DET", TIP), base + (None,))

    def test_not_submitted_team_falls_back_to_espn(self):
        e = espn("Out", REPORT_AT - dt.timedelta(hours=5))
        base = ("OUT", "ESPN: Out", None, False)
        self.assertEqual(self.feed.apply(base, e, "Bilal Coulibaly", "WSH", TIP), base + (None,))

    def test_sleeper_fills_a_gap(self):
        st, why, _, conflict, gd = self.feed.apply(self.healthy, None, "Grant Williams", "CHA", TIP)
        self.assertEqual((st, why, conflict, gd["src"]), ("Q", "Game-time decision per Sleeper, 4:00pm", False, "sleeper"))

    def test_sleeper_out_alone_is_unconfirmed(self):
        st, why, _, conflict, gd = self.feed.apply(self.healthy, None, "Stephen Curry", "GS", TIP)
        self.assertEqual((st, conflict), ("Q", True))
        self.assertEqual(why, "Out per Sleeper, 4:00pm, but not on ESPN's injury report: unconfirmed")

    def test_sleeper_older_than_espn_is_ignored(self):
        e = espn("Day-To-Day", REPORT_AT)
        base = ("Q", "ESPN: Day-To-Day", None, False)
        self.assertEqual(self.feed.apply(base, e, "Stephen Curry", "GS", TIP), base + (None,))

    def test_empty_feed_changes_nothing(self):
        feed = ns.Feed(None, None)
        self.assertFalse(feed)
        self.assertEqual(feed.apply(self.healthy, None, "Joel Embiid", "PHI", TIP), self.healthy + (None,))


class LeagueRows(unittest.TestCase):
    """EspnLeague rows and the view carry the merged status and the credit."""

    def league(self):
        lg = EspnLeague.__new__(EspnLeague)
        lg.sport, lg.period, lg.name, lg.platform, lg.week = "nba", 20, "Test BB", "espn", 3
        lg.sched = {1: {"abbrev": "PHI", "games": {20: [(TIP, 2, True)]}}, 2: {"abbrev": "TOR", "games": {20: [(TIP, 1, False)]}}}
        lg.report = {"77": espn("Day-To-Day", REPORT_AT - dt.timedelta(hours=3))}
        lg.gd = ns.Feed({"at": "2026-11-12T23:30:00Z", "rows": ROWS}, {})

        class Ctx:
            now = REPORT_AT
        lg.ctx = Ctx()
        return lg

    def test_row_and_view(self):
        lg = self.league()
        p = lg._player({"id": 77, "name": "Joel Embiid", "pro_team": 1, "eligible": [4], "slot": 4, "injury": "DAY_TO_DAY"})
        self.assertEqual((p["status"], p["why"]), ("OUT", "Out (rest) per NBA injury report, 5:30pm"))
        lg.starters, lg.bench, lg.opponent, lg.opp_proj = [p], [], None, None
        v = view(lg)
        self.assertEqual(v["starters"][0]["why"], "Out (rest) per NBA injury report, 5:30pm")
        self.assertIn("NBA injury report", v["status_basis"])
        self.assertIn("Sleeper", v["status_basis"])
        self.assertNotIn("ak-static", str(v))                  # the report itself is never linked or copied
        self.assertEqual(lg.gameday("77", "Joel Embiid", 1, "DAY_TO_DAY"), ("OUT", "Out (rest) per NBA injury report, 5:30pm"))
        self.assertIsNone(lg.gameday("78", "Nobody Listed", 1, None))


def player(name, slot, positions, v, *, status=None, why="", gd=None):
    return {"id": f"espn{name}", "key": name, "name": name, "slot": slot, "positions": positions, "status": status,
            "why": why, "gd": gd, "kickoff": TIP, "started": False, "bye": False, "proj": 0.0, "team": "PHI",
            "opp": "vs TOR", "cv": {"v": v, "rk": 50, "wk": 0, "src": "8 g"}}


REST = {"src": "nba", "status": "Out", "rest": True, "at": REPORT_AT}


class Lg:
    sport, key, week, name, can_write = "nba", "espn:nba:1", 3, "Test BB", False

    def __init__(self, starters, bench):
        self.starters, self.bench = starters, bench

    def best_fa(self, positions, now):
        return None


class PushRules(unittest.TestCase):
    """A starter newly Out or resting today rides in the one NBA lineup push; after it, the site only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = notify.ALERTS
        notify.ALERTS = Path(self.tmp.name) / "alerts.json"
        notify.sent.clear()

    def tearDown(self):
        notify.ALERTS = self.saved
        notify.sent.clear()
        self.tmp.cleanup()

    def resting(self):
        return Lg([player("Joel Embiid", "C", ["C", "UT"], 5.0, status="OUT",
                          why="Out (rest) per NBA injury report, 5:30pm", gd=REST),
                   player("Good G", "G", ["PG", "G"], 3.0)],
                  [player("Bench C", "BN", ["C", "UT"], 0.5), player("Bench G", "BN", ["PG", "G"], 0.4)])

    def test_rest_day_rides_in_the_one_push(self):
        before = TIP - dt.timedelta(hours=2)
        ms = nba_lineup.moves(self.resting(), before)
        self.assertEqual(ms[0]["why"], "Out (rest) per NBA injury report, 5:30pm")
        self.assertIn("over Joel Embiid at C: Out (rest) per NBA injury report, 5:30pm", ms[0]["text"])
        self.assertEqual(nba_lineup.send([self.resting()], before), "NBA lineup: 1 change before 7:00p tip")
        self.assertEqual(len(notify.sent), 1)
        self.assertIn("Out (rest) per NBA injury report", notify.sent[0]["message"])
        self.assertIn("espn:nba:1:w3:espnJoel Embiid:swap", notify.load_json(notify.ALERTS))
        self.assertEqual(nba_lineup.lines(self.resting(), before), [ms[0]["text"]])   # it was in the push: no tag

    def test_after_todays_push_a_new_out_is_site_only(self):
        before = TIP - dt.timedelta(hours=2, minutes=30)
        quiet = Lg([player("Joel Embiid", "C", ["C", "UT"], 5.0), player("Good G", "G", ["PG", "G"], 3.0)],
                   [player("Bench C", "BN", ["C", "UT"], 0.5), player("Bench G", "BN", ["PG", "G"], 9.0)])
        self.assertTrue(nba_lineup.send([quiet], before))      # today's push: Bench G over Good G
        self.assertTrue(nba_lineup.pushed_today(before))
        later = before + dt.timedelta(minutes=40)
        lg = self.resting()
        lg.bench[1]["cv"]["v"] = 9.0
        self.assertIsNone(nba_lineup.send([lg], later))        # Embiid rests now: no second push
        texts = nba_lineup.lines(lg, later)
        self.assertTrue(texts[0].endswith("(new since today's lineup push; not pushed)"))
        self.assertFalse(texts[1].endswith("not pushed)"))     # Bench G over Good G was in the push
        actions = run.injury_watch(lg, TIP - dt.timedelta(hours=1))   # the injury watch stays quiet too
        self.assertEqual(actions, ["site only (after today's NBA lineup push): Joel Embiid"])
        self.assertEqual(len(notify.sent), 1)

    def test_espn_only_out_keeps_the_injury_watch(self):
        """No official row behind the Out: the injury watch works as before (its own once-per-player push)."""
        lg = Lg([player("Hurt C", "C", ["C", "UT"], 5.0, status="OUT", why="ESPN: OUT")],
                [player("Bench C", "BN", ["C", "UT"], 0.5)])
        notify.mark([f"nba-lineup:{(TIP - dt.timedelta(hours=1)).astimezone(nba_lineup.TZ).date().isoformat()}"])
        self.assertEqual(run.injury_watch(lg, TIP - dt.timedelta(hours=1)), ["suggested Hurt C -> Bench C"])
        self.assertEqual(len(notify.sent), 1)


if __name__ == "__main__":
    unittest.main()
