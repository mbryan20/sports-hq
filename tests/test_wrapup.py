"""Weekend wrap-up: edition timing, lineup review, standings, pool grading, ESPN results/box, and both renders."""
import datetime as dt
import os
import unittest
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import espn_fantasy as ef
from shq import notify, wrapup, wrapup_render

UTC = dt.timezone.utc
SUN_1PM = dt.datetime(2026, 11, 1, 19, 0, tzinfo=UTC)     # CST from Nov 1: 1pm
SUN_725 = dt.datetime(2026, 11, 2, 1, 20, tzinfo=UTC)     # SNF kickoff, 7:20pm CST
MNF = dt.datetime(2026, 11, 3, 1, 15, tzinfo=UTC)         # Mon 7:15pm CST


def games(sun="post", snf="post", mnf="pre"):
    return {"AAA": {"kickoff": SUN_1PM, "state": sun}, "BBB": {"kickoff": SUN_1PM, "state": sun},
            "CCC": {"kickoff": SUN_725, "state": snf}, "DDD": {"kickoff": SUN_725, "state": snf},
            "EEE": {"kickoff": MNF, "state": mnf}, "FFF": {"kickoff": MNF, "state": mnf}}


def at(day, hour, minute=0):
    """CST wall clock on Nov <day>, 2026."""
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=wrapup.TZ)


def pl(name, slot, pos, pts, proj, team="AAA"):
    return {"name": name, "slot": slot, "pos": pos, "pts": pts, "proj": proj, "team": team}


class Due(unittest.TestCase):
    def test_sunday_edition_after_snf_is_final(self):
        self.assertIsNone(wrapup.due(at(1, 21), 8, games(snf="in"), []))           # SNF still on
        self.assertEqual(wrapup.due(at(1, 22, 40), 8, games(), []), (8, "sunday"))
        self.assertEqual(wrapup.due(at(2, 8), 8, games(), []), (8, "sunday"))       # a late run Monday morning
        self.assertIsNone(wrapup.due(at(2, 8), 8, games(), [{"week": 8, "edition": "sunday"}]))
        self.assertIsNone(wrapup.due(at(1, 22, 40), 8, games(sun="pre", snf="pre"), []) )

    def test_final_from_tuesday_8am(self):
        nxt = {"AAA": {"kickoff": at(5, 19), "state": "pre"}}                        # Context moved to week 9
        self.assertIsNone(wrapup.due(at(2, 23), 9, nxt, []))                        # MNF just ended: wait for Tuesday
        self.assertIsNone(wrapup.due(at(3, 7, 50), 9, nxt, []))
        self.assertEqual(wrapup.due(at(3, 8, 5), 9, nxt, [{"week": 8, "edition": "sunday"}]), (8, "final"))
        self.assertEqual(wrapup.due(at(4, 12), 9, nxt, []), (8, "final"))           # Wednesday catch-up
        self.assertIsNone(wrapup.due(at(3, 9), 9, nxt, [{"week": 8, "edition": "final"}]))
        self.assertEqual(wrapup.due(at(5, 12), 9, nxt, [], force=True), (8, "final"))

    def test_force_mid_week_builds_sunday_edition(self):
        self.assertEqual(wrapup.due(at(1, 13), 8, games(sun="in", snf="pre"), [], force=True), (8, "sunday"))


class Review(unittest.TestCase):
    def test_bench_left_boom_bust(self):
        g = {"AAA": {"state": "post"}, "EEE": {"state": "pre"}}
        players = [pl("QB1", "QB", ["QB"], 20, 18), pl("RB1", "RB", ["RB"], 3, 15), pl("WR1", "WR", ["WR"], 30, 14),
                   pl("FLX", "FLEX", ["TE"], 5, 8), pl("Bench RB", "BN", ["RB"], 19, 10), pl("Hurt", "IR", ["WR"], 40, 0),
                   pl("Monday WR", "WR", ["WR"], 0, 12, team="EEE")]
        r = wrapup.lineup_review(players, g)
        self.assertEqual(r["left"], 16.0)                                   # Bench RB 19 over RB1 3; IR ignored
        self.assertEqual(r["miss"], "Bench RB (19.0) over RB1 (3.0) at RB")
        self.assertEqual(r["boom"], ["WR1 30.0 (proj 14.0)"])
        self.assertEqual(r["bust"], ["RB1 3.0 (proj 15.0)"])
        self.assertEqual([p["name"] for p in r["pending"]], ["Monday WR"])

    def test_best_lineup_fills_narrow_slots_first(self):
        total, _ = wrapup.best_lineup(["FLEX", "RB"], [pl("a", "BN", ["RB"], 10, 0), pl("b", "BN", ["WR"], 8, 0)])
        self.assertEqual(total, 18)


class Standings(unittest.TestCase):
    ROWS = [[1, 1, 100, 2, 90, "H", 0], [1, 3, 80, 4, 120, "A", 0],
            [2, 1, 70, 3, 110, "A", 0], [2, 2, 95, 4, 99, "A", 0],
            [3, 1, 130, 4, 100, "", 0], [3, 2, 50, 3, 60, "", 0]]

    def test_rank_and_movement(self):
        # through week 2: team 4 2-0, then 1-1 teams by points for (team 3 190, team 1 170)
        self.assertEqual(wrapup.standings(self.ROWS, 1, 2), (3, 4, "1-1", "2-0"))
        self.assertEqual(wrapup.standing_text(self.ROWS, 1, 2, True), "3rd of 4 (1-1, down 1; leader 2-0)")
        self.assertEqual(wrapup.standing_text(self.ROWS, 1, 3, False), "3rd of 4 (1-1; leader 2-0), before this week")

    def test_categories_count_each_category(self):
        rows = [[1, 1, 5, 2, 3, "H", 0], [1, 3, 8, 4, 0, "H", 0]]
        self.assertEqual(wrapup.standings(rows, 1, 1, cats=True), (2, 4, "5-3", "8-0"))

    def test_h2h_lines(self):
        self.assertEqual(wrapup.h2h_line(110, 100, "Rival", []), ("W", "Won 110.0-100.0 vs Rival, by 10.0"))
        res, text = wrapup.h2h_line(90, 100, "Rival", [pl("Mon", "WR", ["WR"], 0, 12)], [])
        self.assertEqual(res, "trailing")
        self.assertIn("still to play for you: Mon (proj 12.0); they're done", text)
        self.assertEqual(wrapup.h2h_line(90, 80, "Rival", [], opp_known=False)[0], "leading")

    def test_margin_matches_the_shown_scores(self):
        # week 9: ESPN's 182.76-7.04 showed "182.8-7.0 ... by 175.7"; 166.46-141.54 showed "166.5-141.5 ... by 24.9"
        self.assertEqual(wrapup.h2h_line(182.76, 7.04, "Rival", [])[1], "Won 182.8-7.0 vs Rival, by 175.8")
        self.assertEqual(wrapup.h2h_line(166.46, 141.54, "Rival", [])[1], "Won 166.5-141.5 vs Rival, by 25.0")
        self.assertEqual(wrapup.h2h_line(141.54, 166.46, "Rival", [])[1], "Lost 141.5-166.5 vs Rival, by 25.0")
        self.assertEqual(wrapup.h2h_line(100.04, 100.0, "Rival", [])[1], "Won 100.0-100.0 vs Rival, by less than 0.1")


class Pools(unittest.TestCase):
    EVENTS = {"401": {"state": "post", "home_score": "24", "away_score": "20"},
              "nfl-MIN-DET": {"state": "post", "home_score": "27", "away_score": "21"},
              "402": {"state": "in", "home_score": "7", "away_score": "0"}}

    def test_grade_ats_su_and_open(self):
        g = wrapup.grade_row
        self.assertEqual(g({"bd": "bd-nfl-MIN-DET", "game": "MIN @ DET ★", "pick": "MIN +7.5 (LP 4)", "pick_team": "MIN"}, self.EVENTS, True), 1.0)
        self.assertEqual(g({"bd": "bd-401", "game": "A @ B", "pick": "B -4", "pick_team": "B"}, self.EVENTS, True), 0.5)
        self.assertEqual(g({"bd": "bd-401", "game": "A @ B", "pick": "A", "pick_team": "A"}, self.EVENTS, False), 0.0)
        self.assertIsNone(g({"bd": "bd-402", "game": "C @ D", "pick": "D", "pick_team": "D"}, self.EVENTS, False))

    def test_merge_entries_keeps_card(self):
        old = {"pools": [{"id": "bto", "card": "2-1", "picks": [1]}], "entries": False}
        new = {"pools": [{"id": "bto", "card": None, "entered": "1-2 (-200)", "after": "$2,420, #22"}], "entries": True}
        wrapup.merge_entries(old, new)
        self.assertEqual(old["pools"][0], {"id": "bto", "card": "2-1", "picks": [1], "entered": "1-2 (-200)", "after": "$2,420, #22"})
        self.assertTrue(old["entries"])


class Espn(unittest.TestCase):
    def test_results_and_box(self):
        def side(tid, pts, wins=None, entries=None):
            s = {"teamId": tid, "totalPoints": pts, "totalProjectedPoints": pts + 5, "cumulativeScore": {"wins": wins or 0, "ties": 0}}
            if entries:
                s["rosterForCurrentScoringPeriod"] = {"entries": entries}
            return s
        entry = {"lineupSlotId": 2, "playerPoolEntry": {"player": {"fullName": "Run Back", "proTeamId": 1, "eligibleSlots": [2, 23, 20],
                 "stats": [{"scoringPeriodId": 8, "statSourceId": 0, "appliedTotal": 21.44}, {"scoringPeriodId": 8, "statSourceId": 1, "appliedTotal": 12.0},
                           {"scoringPeriodId": 7, "statSourceId": 0, "appliedTotal": 3.0}]}}}
        raw = {"settings": {"scoringSettings": {"scoringType": "H2H_POINTS"}},
               "schedule": [{"matchupPeriodId": 8, "winner": "UNDECIDED", "home": side(5, 101.234, entries=[entry]), "away": side(6, 99)},
                            {"matchupPeriodId": 8, "winner": "HOME", "home": side(7, 80)}]}       # bye: skipped
        self.assertEqual(ef.results(raw), [[8, 5, 101.23, 6, 99, "", 0]])
        b = ef.box(raw, 5, 8)
        self.assertEqual((b["pts"], b["opp_id"], b["opp_pts"]), (101.23, 6, 99))
        self.assertEqual(b["players"], [{"name": "Run Back", "slot": 2, "pro_team": 1, "eligible": [2, 23, 20], "pts": 21.44, "proj": 12.0}])
        raw["settings"]["scoringSettings"]["scoringType"] = "H2H_CATEGORY"
        raw["schedule"][0]["home"]["cumulativeScore"] = {"wins": 5, "ties": 1}
        self.assertEqual(ef.results(raw)[0][2], 5)
        self.assertEqual(ef.results(raw)[0][6], 1)

    def test_laptop_read_mid_game_is_not_final(self):
        """A 4:30pm laptop read can't call a late game final even when the game is final by Sunday night."""
        snap = {"captured": "2026-11-01T22:30:00Z", "team": {"id": 5, "name": "Me"}, "teams": [{"id": 6, "name": "Rival"}],
                "results": [[8, 5, 50.0, 6, 40.0, "", 0]],
                "box": {"8": {"period": 8, "pts": 50.0, "proj": 120, "opp_id": 6, "opp_pts": 40.0, "opp_proj": 110, "players": [
                    {"name": "Early QB", "slot": 0, "pro_team": 1, "eligible": [0, 7], "pts": 30.0, "proj": 20.0},
                    {"name": "Late RB", "slot": 2, "pro_team": 2, "eligible": [2, 23], "pts": 20.0, "proj": 15.0}]}}}
        g = {"AAA": {"kickoff": SUN_1PM, "state": "post"}, "LAT": {"kickoff": dt.datetime(2026, 11, 1, 21, 25, tzinfo=UTC), "state": "post"}}
        cfg = {"name": "Private", "sport": "nfl", "league_id": 1, "team_id": 5, "private": True}
        with mock.patch.object(ef, "load_snapshot", lambda s, l: snap), \
                mock.patch.object(wrapup, "_abbrevs", lambda s, y: {1: "AAA", 2: "LAT"}):
            sec = wrapup.espn_section(cfg, {}, 8, g, "sunday")
        self.assertEqual(sec["result"], "leading")
        self.assertIn("still to play for you: Late RB", sec["line"])
        self.assertIn("ESPN read by the laptop", sec["note"])

    def test_laptop_js_carries_results_and_box(self):
        js = ef.LAPTOP_SNAPSHOT_JS
        self.assertIn("results: res(raw)", js)
        self.assertIn("mBoxscore&scoringPeriodId", js)


MODEL = {
    "week": 8, "cfb_week": 9, "season": 2026, "edition": "sunday", "generated": "2026-11-02T04:40:00Z", "generated_label": "Sun Nov 1, 10:40p CT",
    "headline": ["Head-to-head: 2-1 → plus 1 open.", "Guillotine: Survived."],
    "leagues": [
        {"name": "Domo Arigato", "sport": "nfl", "result": "W", "line": "Won 120.0-100.0 vs Rival, by 20.0", "score": "120.0-100.0",
         "standing": "3rd of 12 (5-3, up 2; leader 7-1)", "bench": "4.0 pts left on the bench: A (9.0) over B (5.0) at WR",
         "boom": ["C 30.0 (proj 15.0)"], "bust": [], "next": ["Waiver: Add D (WR) — Bid $0–1"],
         "injuries": [{"text": "E (OUT): ruled out & done", "source": "ESPN, Nov 1", "url": "https://www.espn.com/nfl/player/_/id/1"}]},
        {"name": "Guillotine", "sport": "nfl", "result": "survived", "line": "Survived: 130.0", "score": "130.0, cut line 90.0",
         "chart": {"title": "Week 8 scores", "bars": [{"label": "Me", "value": 130.0, "me": True, "low": False},
                                                       {"label": "Them <b>", "value": 90.0, "me": False, "low": True}]}, "next": [], "injuries": []}],
    "pools": {"cfb_week": 9, "entries": False, "pools": [{"id": "bto", "title": "BTO Beat the Odds", "card": "2-1", "open": 0, "net": 660.0,
                                                         "picks": [{"pick": "MIN +7.5", "game": "MIN @ DET", "result": "W"}], "before": "$2,620 (#20 of 49)"}],
              "model": [], "stale": []},
    "warroom": {"lines": ["Week 8 cut: X (projected)."], "source": "War Room v2, test"},
    "numbers": ["Stale-line flags: 1 of 1 covered the pool line (backtest 61%)."],
}


class Render(unittest.TestCase):
    def test_html_escapes_and_links(self):
        page = wrapup_render.html(MODEL)
        self.assertIn("ruled out &amp; done", page)
        self.assertIn('href="2026-w08.pdf"', page)
        self.assertIn("Them &lt;b&gt;", page)
        self.assertIn("Monday night still to play", page)

    def test_pdf_builds(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab not installed")
        data = wrapup_render.pdf(MODEL)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 2000)

    def test_archive(self):
        page = wrapup_render.archive([{"week": 8, "cfb_week": 9, "edition": "final", "html": "2026-w08.html", "pdf": "2026-w08.pdf",
                                       "headline": ["H2H 2-1."]}])
        self.assertIn('href="2026-w08.pdf"', page)

    # week 9's real headline: 254 characters, which the old [:220] cut to "...Most left"
    W9 = ["Head-to-head: 4-1-1.", "Guillotine: survived, 5th of 10 with 133.0, 36.7 over the lowest team (MoneyManChas, 96.3).",
          "Picks card: Yahoo 16-9, CFP 1-0, BTO 1-2 (card as posted; your entries are graded Tuesday night).",
          "Most left on a bench: 15.6 in Domo Arigato."]

    def test_short_version_ends_on_a_whole_sentence(self):
        s = wrapup_render.short(" ".join(self.W9))
        self.assertLessEqual(len(s), 220)
        self.assertTrue(s.endswith("graded Tuesday night)."), s)
        self.assertNotIn("Most left", s)
        page = wrapup_render.archive([{"week": 9, "cfb_week": 10, "edition": "final", "html": "a.html", "headline": self.W9}])
        self.assertNotIn("Most left<", page)
        self.assertIn("Tuesday night).</td>", page)

    def test_short_version_falls_back_to_a_whole_word(self):
        s = wrapup_render.short("word " * 60)                    # one 300-character "sentence" with no full stop
        self.assertLessEqual(len(s), 220)
        self.assertTrue(s.endswith("word…"), s)
        self.assertEqual(wrapup_render.short("Short. Enough."), "Short. Enough.")
        self.assertEqual(wrapup_render.short("A" * 230 + "."), "A" * 219 + "…")   # one giant word: hard cut, still marked

    def test_push_opens_the_pdf(self):
        notify.sent.clear()
        with mock.patch.object(notify, "push_once", lambda key, title, msg, **kw: notify.push(title, msg, **kw)):
            wrapup.send(MODEL, {"pdf": "https://x/wrapups/2026-w08.pdf", "html": "https://x/wrapups/2026-w08.html"})
        self.assertEqual(notify.sent[-1]["click"], "https://x/wrapups/2026-w08.pdf")
        self.assertEqual(notify.sent[-1]["title"], "Weekend wrap-up: NFL wk 8 (Sunday)")


if __name__ == "__main__":
    unittest.main()
