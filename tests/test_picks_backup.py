"""Picks backup card (Q-055): lines when CFBD can't be called, model fallbacks, and the workflow's push text.
Fixtures only, no network."""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "picks"))
from pp import http as H  # noqa: E402
from pp import market as MK  # noqa: E402
from pp import lines as L  # noqa: E402
from pp import backup as B  # noqa: E402


def cfbd_rec(gid, week, away, home, spread, opn=None, total=55.5, hml=None, aml=None):
    return {"id": gid, "season": 2026, "week": week, "homeTeam": home, "awayTeam": away,
            "lines": [{"provider": "DraftKings", "spread": spread, "spreadOpen": opn, "overUnder": total,
                       "homeMoneyline": hml, "awayMoneyline": aml}]}


def espn_raw(eid, away, home, spread, total=50.5, opener=None):
    """One event as ESPN's college scoreboard JSON has it (trimmed to the fields pp.lines.parse_event reads)."""
    team = lambda n: {"location": n, "abbreviation": n[:4].upper(), "displayName": n, "shortDisplayName": n, "name": n}
    odds = {"details": f"X {spread}", "spread": spread, "overUnder": total, "provider": {"name": "DraftKings"},
            "moneyline": {"home": {"close": {"odds": "-200"}}, "away": {"close": {"odds": "+170"}}}}
    if opener is not None:
        odds["pointSpread"] = {"home": {"open": {"line": f"{opener:+g}"}}}
    return {"id": str(eid), "date": "2026-11-14T17:00Z", "competitions": [{
        "status": {"type": {"state": "pre"}},
        "competitors": [{"homeAway": "home", "team": team(home)}, {"homeAway": "away", "team": team(away)}],
        "odds": [odds]}]}


GAMES = [{"id": 501, "week": 12, "homeTeam": "Ole Miss", "awayTeam": "Georgia"},
         {"id": 502, "week": 12, "homeTeam": "Texas", "awayTeam": "Miami"},          # ESPN lists it the other way round
         {"id": 503, "week": 12, "homeTeam": "San Diego State", "awayTeam": "Boise State"}]  # ESPN id differs


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cache = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(H, "CACHE", cache), mock.patch.object(H, "BUDGET_FILE", cache / "cfbd_calls.json"),
                        mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CFBD_API_KEY": ""})]
        for p in self.patches:
            p.start()
        H.STALE.clear()
        MK.NOTE.clear()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        H.STALE.clear()
        MK.NOTE.clear()
        self.tmp.cleanup()

    def save(self, endpoint, data, age_h=0, **params):
        p = H._path("cfbd", H.CFBD_BASE + endpoint, params)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
        t = time.time() - age_h * 3600
        os.utime(p, (t, t))
        return p


class CachedAnyAge(Base):
    def test_no_key_uses_week_copy_of_any_age_and_says_when(self):
        self.save("/lines", [cfbd_rec(501, 12, "Georgia", "Ole Miss", 3.5, opn=4.5)], age_h=24 * 30, year=2026, week=12)
        with mock.patch.object(H, "_key", return_value=None), mock.patch.object(H.requests, "get") as get:
            out = MK.lines(2026, 12, max_age_h=6, games=GAMES)
        get.assert_not_called()
        self.assertEqual(out[501]["home_spread"], 3.5)
        self.assertEqual(out[501]["open_spread"], 4.5)
        self.assertEqual(len(MK.NOTE), 1)
        self.assertIn("no CFBD API key is set", MK.NOTE[0])
        self.assertIn("saved CFBD lines as of", MK.NOTE[0])
        self.assertIn(" CT", MK.NOTE[0])

    def test_http_error_falls_back_to_saved_copy(self):
        self.save("/lines", [cfbd_rec(501, 12, "Georgia", "Ole Miss", -2.5)], age_h=48, year=2026, week=12)
        with mock.patch.object(H, "_key", return_value="test-key"), \
                mock.patch.object(H.requests, "get", side_effect=H.requests.ConnectionError("down")):
            out = MK.lines(2026, 12, max_age_h=6)
        self.assertEqual(out[501]["home_spread"], -2.5)
        self.assertTrue(H.STALE and "CFBD didn't answer" in H.STALE[-1][1])
        self.assertNotIn("test-key", MK.NOTE[0])

    def test_budget_used_up_is_named(self):
        self.save("/games", [{"id": 1}], age_h=100, year=2026)
        H.BUDGET_FILE.write_text(json.dumps({datetime.now(timezone.utc).strftime("%Y-%m"): 900}))
        with mock.patch.object(H, "_key", return_value="test-key"), mock.patch.object(H.requests, "get") as get:
            self.assertEqual(H.cfbd("/games", max_age_h=20, year=2026), [{"id": 1}])
        get.assert_not_called()
        self.assertIn("budget (900) is used up", H.STALE[-1][1])

    def test_nothing_saved_raises_plain_words(self):
        with mock.patch.object(H, "_key", return_value=None):
            with self.assertRaises(H.CFBDUnavailable) as cm:
                H.cfbd("/talent", year=2026)
        self.assertEqual(str(cm.exception), "CFBD /talent unavailable (no CFBD API key is set) and no saved copy")
        self.assertEqual(cm.exception.why, "no CFBD API key is set")

    def test_actions_checkout_time_is_not_claimed(self):
        self.save("/lines", [cfbd_rec(501, 12, "Georgia", "Ole Miss", 3.5)], age_h=24 * 9, year=2026, week=12)
        with mock.patch.object(H, "_key", return_value=None), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            MK.lines(2026, 12, max_age_h=6)
        self.assertIn("older saved CFBD lines (save time unknown)", MK.NOTE[0])


class EspnFallback(Base):
    def scoreboard(self):
        return {"events": [espn_raw(501, "Georgia", "Ole Miss", 3.5, opener=4.5),
                           espn_raw(502, "Texas", "Miami", 6.5),            # ESPN: Miami home; CFBD: Texas home
                           espn_raw(9999, "Boise State", "San Diego State", -1.5),  # id unknown: match by name (SDSU alias)
                           espn_raw(777, "Navy", "Army", None),            # no line yet
                           espn_raw(778, "Duke", "Wake Forest", 2.5)]}     # not on this CFBD week

    def test_no_saved_lines_uses_espn_scoreboard(self):
        with mock.patch.object(H, "_key", return_value=None), \
                mock.patch.object(L, "get_json", return_value=self.scoreboard()) as gj:
            out = MK.lines(2026, 12, max_age_h=6, games=GAMES)
        args, kw = gj.call_args
        self.assertEqual(args[0], "espn")
        self.assertIn("college-football/scoreboard", args[1])
        self.assertEqual((kw["groups"], kw["limit"], kw["week"], kw["dates"]), (80, 300, 12, 2026))
        self.assertEqual(set(out), {501, 502, 503})
        self.assertEqual(out[501]["home_spread"], 3.5)
        self.assertEqual(out[501]["open_spread"], 4.5)
        self.assertEqual(out[501]["total"], 50.5)
        self.assertAlmostEqual(out[501]["p_home"], (2 / 3) / (2 / 3 + 100 / 270), places=6)
        self.assertEqual(out[502]["home_spread"], -6.5)  # flipped to CFBD's home team
        self.assertLess(out[502]["p_home"], 0.5)
        self.assertEqual(out[503]["home_spread"], -1.5)
        self.assertTrue(out[501]["src"].startswith("ESPN DraftKings"))
        self.assertIn("ESPN's scoreboard for 3 games", MK.NOTE[0])
        self.assertIn("no CFBD API key is set", MK.NOTE[0])

    def test_saved_season_copy_fills_games_espn_lacks(self):
        self.save("/lines", [cfbd_rec(503, 12, "Boise State", "San Diego State", 2.0, opn=1.0),
                             cfbd_rec(501, 12, "Georgia", "Ole Miss", 7.0, opn=6.0),
                             cfbd_rec(400, 11, "A", "B", 1.0)], age_h=24 * 16, year=2026)
        sb = {"events": [espn_raw(501, "Georgia", "Ole Miss", 3.5)]}
        with mock.patch.object(H, "_key", return_value=None), mock.patch.object(L, "get_json", return_value=sb):
            out = MK.lines(2026, 12, games=GAMES)
        self.assertEqual(out[501]["home_spread"], 3.5)    # ESPN is fresher
        self.assertEqual(out[501]["open_spread"], 6.0)    # opener kept from CFBD when ESPN has none
        self.assertEqual(out[503]["home_spread"], 2.0)    # only the saved copy has it
        self.assertNotIn(400, out)                        # other weeks left out
        self.assertIn("saved CFBD lines as of", MK.NOTE[0])
        self.assertIn("for 2 games", MK.NOTE[0])

    def test_nothing_anywhere_is_a_plain_failure(self):
        with mock.patch.object(H, "_key", return_value=None), \
                mock.patch.object(L, "get_json", side_effect=OSError("offline")):
            with self.assertRaises(MK.LinesUnavailable) as cm:
                MK.lines(2026, 12, games=GAMES)
        self.assertEqual(str(cm.exception), "no betting lines for week 12 (no CFBD API key is set, no saved CFBD lines, "
                                            "and ESPN's scoreboard had none)")

    def test_season_backtest_call_still_raises(self):
        with mock.patch.object(H, "_key", return_value=None):
            with self.assertRaises(H.CFBDUnavailable):
                MK.lines(2026)


class ModelFallbacks(Base):
    def test_extras_fall_back_when_nothing_saved(self):
        from pp import model as M, weather as W
        for f in (M._ret, M._sp, M.fbs_teams, M.games, W.venues):
            f.cache_clear()
        self.save("/games", [{"id": 1, "week": 12, "homeTeam": "Texas", "awayTeam": "Idaho",
                              "homeClassification": "fbs", "awayClassification": "fcs", "seasonType": "regular"}],
                  year=2026, classification="fbs")
        try:
            with mock.patch.object(H, "_key", return_value=None):
                self.assertEqual(M._ret(2026), {})
                self.assertEqual(M._sp(2025), {})
                self.assertEqual(M.fbs_teams(2026), {"Texas"})
                self.assertEqual(W.venues(), {})
        finally:
            for f in (M._ret, M._sp, M.fbs_teams, M.games, W.venues):
                f.cache_clear()


TRACE = """Traceback (most recent call last):
  File "/home/runner/work/sports-hq/sports-hq/picks/pp/cards.py", line 68, in __init__
    self.lines = overlay(lines(YEAR, week, max_age_h=6, games=self.games), week, YEAR, self.games)
pp.market.LinesUnavailable: no betting lines for week 12 (no CFBD API key is set, no saved CFBD lines, and ESPN's scoreboard had none)
"""


class PushText(unittest.TestCase):
    def test_failure_text_names_slot_and_reason(self):
        msg = B.failure_text("Wed 9pm draft", B.reason(TRACE, {"build": "failure"}))
        self.assertEqual(msg, "No picks card reached the site for the Wed 9pm draft slot, and the backup couldn't build one: "
                              "no betting lines for week 12 (no CFBD API key is set, no saved CFBD lines, and ESPN's "
                              "scoreboard had none).")

    def test_reasons(self):
        cfbd = "Traceback...\npp.http.CFBDUnavailable: CFBD /games unavailable (no CFBD API key is set) and no saved copy\n"
        self.assertEqual(B.reason(cfbd, {"build": "failure"}), "CFBD /games unavailable (no CFBD API key is set) and no saved copy")
        crash = "Traceback...\nKeyError: 'home'\n"
        self.assertEqual(B.reason("x\nValueError: bad week\n", {"build": "failure"}), "the card build crashed (ValueError: bad week)")
        self.assertEqual(B.reason(crash, {"build": "failure"}), "the card build crashed (KeyError: 'home')")
        self.assertEqual(B.reason("loading\nYahoo game not found in CFBD week 12: {...}\n", {"build": "failure"}),
                         "the card build stopped: Yahoo game not found in CFBD week 12: {...}")
        self.assertIn("saving it to GitHub failed", B.reason("", {"build": "success", "push": "failure"}))
        self.assertIn("check for the laptop's card failed", B.reason("", {"decide": "failure"}))
        self.assertIn("setup steps failed", B.reason("", {}))

    def test_slot_labels(self):
        self.assertEqual(B.slot("45 3 * * 4"), ("Wed 9pm draft", "draft"))
        self.assertEqual(B.slot("45 2 * * 5"), ("Thu 8pm BTO final", "final"))
        self.assertEqual(B.slot("45 3 * * 6"), ("Fri 9pm final", "final"))
        self.assertEqual(B.slot("45 14 * * 6"), ("Sat 8am refresh", "refresh"))
        self.assertEqual(B.slot("", "final"), ("manual final", "final"))

    def test_fail_cli_prints_text(self):
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / "build.log"
            log.write_text(TRACE, encoding="utf-8")
            with mock.patch.dict(os.environ, {"OUTCOME_DECIDE": "success", "OUTCOME_BUILD": "failure", "OUTCOME_PUSH": "skipped"}), \
                    mock.patch("builtins.print") as pr:
                B.main(["fail", "--cron", "45 3 * * 4", "--log", str(log)])
        self.assertTrue(pr.call_args[0][0].startswith("No picks card reached the site for the Wed 9pm draft slot"))


class Fresh(unittest.TestCase):
    NOW = datetime(2026, 11, 12, 11, 52, tzinfo=timezone.utc)  # Nov 12: the Wed 9pm slot's run came 8h late

    def test_late_run_after_laptop_card_is_fresh(self):
        meta = {"generated_iso": "2026-11-12T03:33:00+00:00"}  # Wed 9:33pm CT draft
        self.assertTrue(B.fresh(meta, "45 3 * * 4", self.NOW))

    def test_last_weeks_card_is_not_fresh(self):
        meta = {"generated_iso": "2026-11-07T14:10:00+00:00"}  # Sat refresh
        self.assertFalse(B.fresh(meta, "45 3 * * 4", self.NOW))

    def test_slot_opens_two_hours_early(self):
        self.assertTrue(B.fresh({"generated_iso": "2026-11-12T01:46:00+00:00"}, "45 3 * * 4", self.NOW))
        self.assertFalse(B.fresh({"generated_iso": "2026-11-12T01:44:00+00:00"}, "45 3 * * 4", self.NOW))

    def test_workflow_stays_quiet_when_fresh(self):
        wf = (ROOT / ".github/workflows/picks-backup.yml").read_text(encoding="utf-8")
        self.assertIn("if: failure() && (steps.s.outputs.fresh != '1' || github.event_name == 'workflow_dispatch')", wf)
        self.assertEqual(wf.count("if: steps.s.outputs.fresh == '0' || github.event_name == 'workflow_dispatch'"), 2)
        self.assertIn('-d "Laptop run missed; model-only card (no fresh injury research)."', wf)
        self.assertNotIn("Backup card build failed. Tap for logs.", wf)


if __name__ == "__main__":
    unittest.main()
