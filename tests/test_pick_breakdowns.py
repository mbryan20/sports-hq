"""Pool Picks per-game breakdowns: rule-4 strengths/weaknesses, matchup edges, note matching, line text,
ESPN extras, and the page's expand rows (one <template> per game)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import explain as E  # noqa: E402
from pp import lines as L  # noqa: E402

try:
    import numpy  # noqa: F401
    HAVE_NP = True
except ImportError:  # test.yml installs numpy; requirements.txt (the 10-minute run) does not
    HAVE_NP = False

N = 138


def unit(ro=None, rd=None):
    return {"ro": ro, "rd": rd}


class Traits(unittest.TestCase):
    def test_weakness_exploitable_only_if_opponent_is_good_at_it(self):
        T = {"rush": unit(60, 120)}                         # run defense #120
        good = {"rush": unit(10, 60), "runrate": {"o": 0.55, "ro": 30}}
        bad = {"rush": unit(100, 60), "runrate": {"o": 0.55, "ro": 30}}
        _, w = E.traits("Florida", "Georgia", T, good, N)
        self.assertIn("exploitable", w[0])
        _, w = E.traits("Florida", "Georgia", T, bad, N)
        self.assertIn("probably won't matter", w[0])
        self.assertIn("only #100", w[0])

    def test_pass_heavy_opponent_cannot_exploit_run_defense(self):
        T = {"rush": unit(60, 125)}
        O = {"rush": unit(20, 60), "runrate": {"o": 0.35, "ro": 130}}  # good per carry but rarely runs
        _, w = E.traits("A", "B", T, O, N)
        self.assertIn("probably won't matter", w[0])
        self.assertIn("rarely runs", w[0])

    def test_strengths_are_top_ranked_units(self):
        s, w = E.traits("A", "B", {"epa": unit(3, 70), "pass": unit(40, 9)}, {}, N)
        self.assertEqual(s, ["offense #3", "pass defense #9"])
        self.assertEqual(w, [])


class Edges(unittest.TestCase):
    def test_biggest_mismatch_first_and_named_for_the_winner(self):
        A = {"pass": unit(100, 110), "runrate": {"o": 0.6}, "rush": unit(60, 40)}   # Florida pass D #110
        H = {"pass": unit(9, 60), "rush": unit(67, 60), "runrate": {"o": 0.5}}     # Georgia pass O #9
        ed = E.edges("Florida", "Georgia", A, H, N)
        self.assertTrue(ed)
        self.assertIn("Georgia's pass game (#9)", ed[0])
        self.assertTrue(ed[0].endswith("edge <b>Georgia</b>"))

    def test_small_gaps_are_not_edges(self):
        A = {"epa": unit(40, 40)}
        H = {"epa": unit(45, 45)}
        self.assertEqual(E.edges("A", "H", A, H, N), [])


class Text(unittest.TestCase):
    def test_fav_line_and_by(self):
        self.assertEqual(E.fav_line("Georgia", "Florida", -12.5), "Georgia -12.5")
        self.assertEqual(E.fav_line("USC", "Ohio State", 6.5), "Ohio State -6.5")
        self.assertEqual(E.fav_line("A", "B", 0), "A PK")
        self.assertEqual(E.by("H", "A", -3.0), "A by 3.0")

    def test_move_names_key_numbers(self):
        self.assertEqual(E._move(-7.5, -3.5, "Oregon", "Northwestern"), "moved 4 toward Northwestern, through 7")
        self.assertEqual(E._move(-1.5, 1.5, "Tech", "Arizona"), "moved 3 toward Arizona")
        self.assertEqual(E._move(-3, -3, "A", "B"), "no movement since the open")

    def test_notes_skip_other_schools_with_the_same_word(self):
        notes = ["Clemson @ Florida State: FSU -6.5 since Mon.", "Florida vs Georgia: venue is Atlanta.",
                 "Miami (OH) note", "Ohio St. @ USC: QB unnamed"]
        self.assertEqual(E.notes_for(notes, {"Florida", "Georgia"}), ["Florida vs Georgia: venue is Atlanta."])
        self.assertEqual(E.notes_for(notes, {"Ohio St.", "USC"}), ["Ohio St. @ USC: QB unnamed"])

    def test_kick_is_central_time(self):
        self.assertEqual(E.kick_ct("2026-10-31T19:30:00.000Z"), "Sat Oct 31, 2:30 PM")


class EspnExtras(unittest.TestCase):
    def test_parse_event_keeps_tv_opener_record_rank(self):
        e = {"id": "1", "date": "2026-10-31T19:30Z", "competitions": [{
            "status": {"type": {"state": "pre"}}, "broadcasts": [{"names": ["ABC"]}, {"names": ["ABC", "Disney+"]}],
            "venue": {"fullName": "Mercedes-Benz Stadium", "indoor": True},
            "competitors": [
                {"homeAway": "home", "team": {"location": "Georgia", "abbreviation": "UGA"}, "curatedRank": {"current": 3},
                 "records": [{"type": "total", "summary": "6-1"}], "score": "0"},
                {"homeAway": "away", "team": {"location": "Florida", "abbreviation": "FLA"}, "curatedRank": {"current": 99},
                 "records": [{"type": "total", "summary": "5-2"}], "score": "0"}],
            "odds": [{"spread": -11.5, "overUnder": 56.5, "provider": {"name": "DraftKings"},
                      "pointSpread": {"home": {"open": {"line": "-12"}}}}]}]}
        r = L.parse_event(e, "CFB")
        self.assertEqual((r["tv"], r["venue"], r["indoor"]), ("ABC, Disney+", "Mercedes-Benz Stadium", True))
        self.assertEqual(r["open_home_spread"], -12.0)
        self.assertEqual((r["home_record"], r["home_rank"], r["away_rank"]), ("6-1", 3, None))


@unittest.skipUnless(HAVE_NP, "needs numpy (cards module)")
class PageRows(unittest.TestCase):
    def test_rows_expand_and_each_game_ships_once(self):
        from pp import cards as C
        row = {"game": "Florida @ Georgia", "pick": "Georgia", "model": 0.8, "market": 0.78, "wager": "", "why": "x",
               "source": "https://example.com", "key": "Florida@Georgia", "pick_team": "Georgia", "bd": "bd-1"}
        plain = {**row, "game": "Other", "key": "Other", "bd": None}
        cards = [{"id": "yahoo", "title": "Yahoo", "rows": [row, plain]}, {"id": "cfp", "title": "CFP", "rows": [dict(row)]}]
        meta = {"stage_label": "FINAL", "week_label": "wk", "generated": "now", "calibration": [], "breakdowns": "Sat"}
        games = [{"id": "bd-1", "kick": "2026-10-31T19:30:00.000Z", "label": "Florida @ Georgia", "market": "Georgia -11.5",
                  "pools": [("yahoo", True), ("cfp", True), ("bto", False)], "html": "<div class='bd'>panel</div>"}]
        page = C.render(cards, meta, games)
        self.assertEqual(page.count('data-bd="bd-1"'), 3)          # Yahoo row, CFP row, All games row
        self.assertEqual(page.count("<template id=\"bd-1\">"), 1)   # panel shipped once
        self.assertEqual(page.count("class='bdr' hidden"), 3)
        self.assertIn("<tr><td>Other</td>", page)                   # a row without a breakdown stays plain
        self.assertIn("breakdowns Sat", page)


if __name__ == "__main__":
    unittest.main()
