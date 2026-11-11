"""Q-049: one push where two said the same thing. (1) NBA radar: one push a day for every NBA league together.
(2) Tuesday: the plan, the 8am digest and the wrap-up final are ONE push; the digest never repeats an injury-watch push.
(3) Stale pool lines: quiet 10pm-6am CT, at most one push a day. (4) Laptop/Chrome down: one push per outage.
Plus the dedupe state shared by parallel runs. Every push is captured by a stand-in: nothing here reaches ntfy."""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import notify, pushes, radar, run, statemerge, wrapup  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import lines as L  # noqa: E402

UTC = dt.timezone.utc
TUE_702 = dt.datetime(2026, 11, 10, 13, 2, tzinfo=UTC)       # Tue Nov 10, 7:02am CST
TUE_802 = dt.datetime(2026, 11, 10, 14, 2, tzinfo=UTC)       # 8:02am CST
WED_802 = dt.datetime(2026, 11, 11, 14, 2, tzinfo=UTC)


class Pushes(unittest.TestCase):
    """Temp state and data files; notify.push replaced by a recorder; the network can't be reached."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data").mkdir()
        self.calls = []

        def fake_push(title, message, priority=3, tags=None, click=None, actions=None, delay=None):
            self.calls.append({"title": title, "message": message, "click": click, "actions": actions, "delay": delay})
        self.patches = [mock.patch.object(notify, "ALERTS", self.tmp / "alerts.json"),
                        mock.patch.object(notify, "push", fake_push),
                        mock.patch.object(notify.session, "post", side_effect=AssertionError("network push")),
                        mock.patch.object(notify, "origin_state", side_effect=AssertionError("origin read")),
                        mock.patch.object(pushes, "DATA", self.tmp / "data"),
                        mock.patch.object(pushes, "WRAPUPS", self.tmp / "wrapups.json"),
                        mock.patch.dict(os.environ, {"DRY_RUN": "1", "NTFY_TOPIC": "", "GITHUB_ACTIONS": ""})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seen(self):
        return notify.load_json(notify.ALERTS, {}) or {}

    def write(self, name, obj):
        (self.tmp / name).write_text(json.dumps(obj), encoding="utf-8")


# ---------- (1) NBA radar ----------

def nba_league(name, key, now):
    return SimpleNamespace(name=name, key=key, week=4, sport="nba", ctx=SimpleNamespace(now=now))


def riser(pid, name):
    return {"id": pid, "name": name, "push": True, "text": f"{name} (G, ATL): minutes 12 → 30."}


class RadarOnePushADay(Pushes):
    NOW = dt.datetime(2026, 11, 10, 13, 2, tzinfo=UTC)   # 7:02am CST, both leagues in the same run

    def entries(self, now, a=("1", "A Riser"), b=("2", "B Riser")):
        return [(nba_league("Ball is Life", "bil", now), {"radar": {"rising": [riser(*a)]}}),
                (nba_league("3-Ball BB", "3b", now), {"radar": {"rising": [riser(*b)]}})]

    def test_both_leagues_one_push(self):
        title = radar.send_all(self.entries(self.NOW))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(title, "NBA rising free agents: A Riser + B Riser")
        self.assertIn("Ball is Life: A Riser", self.calls[0]["message"])
        self.assertIn("3-Ball BB: B Riser", self.calls[0]["message"])
        self.assertIn("radar:2026-11-10", self.seen())
        self.assertIn("bil:radar:w4:1", self.seen())                       # each player once per matchup week
        self.assertIn("3b:radar:w4:2", self.seen())

    def test_second_run_and_later_riser_same_day_wait(self):
        radar.send_all(self.entries(self.NOW))
        later = self.NOW + dt.timedelta(hours=6)                          # a new riser in the afternoon
        self.assertIsNone(radar.send_all(self.entries(later, a=("9", "Late Riser"))))
        self.assertEqual(len(self.calls), 1)
        tomorrow = self.NOW + dt.timedelta(days=1)                         # he goes out tomorrow; the others don't repeat
        self.assertEqual(radar.send_all(self.entries(tomorrow, a=("9", "Late Riser"))),
                         "Ball is Life: rising free agent Late Riser")
        self.assertEqual(len(self.calls), 2)

    def test_old_per_league_day_key_counts(self):
        notify.mark(["bil:radar:2026-11-10"])                              # pushed today by the code before Q-049
        self.assertIsNone(radar.send_all(self.entries(self.NOW)))
        self.assertEqual(self.calls, [])

    def test_run_queue_only_nba_leagues(self):
        nfl = SimpleNamespace(name="Domo", key="d", week=10, sport="nfl", ctx=SimpleNamespace(now=self.NOW))
        queue = [(lg, {"advice": adv}) for lg, adv in self.entries(self.NOW)] + [(nfl, {"advice": {}})]
        notes = []
        run.radar_push(queue, notes)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(notes, ["radar push: NBA rising free agents: A Riser + B Riser"])

    def test_quiet_overnight(self):
        self.assertIsNone(radar.send_all(self.entries(dt.datetime(2026, 11, 10, 4, tzinfo=UTC))))   # 10pm CST
        self.assertEqual(self.calls, [])


# ---------- (2) Tuesday morning: one push ----------

def wrap_model(now, week=9):
    return {"season": 2026, "week": week, "edition": "final", "generated": run.iso(now),
            "headline": ["Head-to-head: 4-1-1.", "Guillotine: survived, 5th of 10."]}


URLS = {"html": "https://mbryan20.github.io/sports-hq/wrapups/2026-w09.html",
        "pdf": "https://mbryan20.github.io/sports-hq/wrapups/2026-w09.pdf"}
DIGEST_ITEMS = [{"league": "Domo", "urgent": True, "text": "Elliott (K) on BYE → add Zvada (FA, 8.1 proj) and start him"},
                {"league": "Ball is Life", "urgent": False, "text": "Radar: Someone rising"}]


class TuesdayMorning(Pushes):
    def build_weekly(self, now):
        self.write("data/weekly.json", {"generated": run.iso(now), "week": 10, "leagues": []})
        return pushes.plan_push(now, 10)

    def build_digest(self, now, items=DIGEST_ITEMS, leagues=()):
        self.write("data/digest.json", {"generated": run.iso(now), "title": "x", "items": items})
        return pushes.digest_push(items, leagues, now)

    def build_wrapup(self, now):
        model = wrap_model(now)
        pushes.wrapup_deliver(now)(model, URLS)
        self.write("wrapups.json", {"issues": [{**{k: model[k] for k in ("season", "week", "edition", "generated",
                                                                           "headline")},
                                                "html": "2026-w09.html", "pdf": "2026-w09.pdf"}]})
        return model

    def test_plan_digest_wrapup_are_one_push(self):
        self.assertIsNone(self.build_weekly(TUE_702))                      # 7:02: plan built, push waits
        self.assertIsNone(pushes.tuesday_push(TUE_702, []))                 # not 8am yet
        self.assertFalse(self.build_digest(TUE_802))                        # 8:02: digest waits
        model = self.build_wrapup(TUE_802)                                  # wrap-up final waits
        self.assertEqual(self.calls, [])
        title = pushes.tuesday_push(TUE_802, [])
        self.assertEqual(len(self.calls), 1)
        c = self.calls[0]
        self.assertEqual(title, "Tuesday: 1 thing to fix · Week 10 plan · wk 9 wrap-up")
        self.assertIn("⚠ Domo: Elliott (K) on BYE → add Zvada", c["message"])
        self.assertIn("Week 10 plan: start/sit and FA adds are on the Weekly tab.", c["message"])
        self.assertIn("Head-to-head: 4-1-1.", c["message"])
        self.assertNotIn("Radar:", c["message"])                            # non-urgent lines stay on the Today tab
        self.assertEqual(c["click"], URLS["pdf"])                           # the wrap-up PDF link
        self.assertEqual([a["label"] for a in c["actions"]], ["PDF", "Web page"])
        self.assertEqual(c["delay"], "3m")
        # nothing pushes again by itself: later passes, a parallel run's leftovers, the wrap-up's own send
        self.assertIsNone(pushes.tuesday_push(TUE_802 + dt.timedelta(minutes=10), []))
        self.assertFalse(pushes.digest_push(DIGEST_ITEMS, [], TUE_802 + dt.timedelta(minutes=10)))
        self.assertFalse(pushes.plan_push(TUE_802 + dt.timedelta(minutes=10), 10))
        wrapup.send(model, URLS)
        self.assertEqual(len(self.calls), 1)
        for k in ("tuesday:2026-11-10", "weekly-plan:2026-11-10", "digest:2026-11-10", "wrapup:2026:9:final"):
            self.assertIn(k, self.seen())

    def test_one_late_pass_builds_everything(self):
        self.build_weekly(TUE_802)
        self.build_digest(TUE_802)
        self.build_wrapup(TUE_802)
        pushes.tuesday_push(TUE_802, [])
        self.assertEqual(len(self.calls), 1)

    def test_all_clear_digest_still_one_push(self):
        self.build_weekly(TUE_702)
        self.build_digest(TUE_802, items=[DIGEST_ITEMS[1]])
        self.build_wrapup(TUE_802)
        pushes.tuesday_push(TUE_802, [])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["message"].splitlines()[0], "Today: all clear.")

    def test_wrapup_that_fails_in_the_morning_pass_pushes_alone_later(self):
        self.build_weekly(TUE_702)
        self.build_digest(TUE_802)
        pushes.tuesday_push(TUE_802, [])                                    # wrap-up crashed this pass
        self.assertNotIn("wrap-up", self.calls[0]["title"])
        self.assertEqual(self.calls[0]["click"], notify.SITE_URL)
        model = wrap_model(TUE_802 + dt.timedelta(minutes=10))
        pushes.wrapup_deliver(TUE_802 + dt.timedelta(minutes=10))(model, URLS)   # next pass: its own push
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1]["title"], "Weekend wrap-up: NFL wk 9 final")

    def test_plan_built_after_the_morning_push_pushes_alone(self):
        self.build_digest(TUE_802)
        self.build_wrapup(TUE_802)
        pushes.tuesday_push(TUE_802, [])                                    # the 7am plan build had failed
        self.assertNotIn("plan", self.calls[0]["title"])
        self.assertTrue(self.build_weekly(TUE_802 + dt.timedelta(minutes=10)))
        self.assertEqual(self.calls[1]["title"], "Week 10 plan ready")

    def test_other_days_unchanged(self):
        self.write("data/weekly.json", {"generated": run.iso(WED_802), "week": 10, "leagues": []})
        self.assertTrue(pushes.plan_push(WED_802, 10))                      # a catch-up build on Wednesday
        self.assertTrue(self.build_digest(WED_802))                         # Wednesday's digest
        self.assertFalse(pushes.plan_push(WED_802 + dt.timedelta(hours=1), 10))
        self.assertIsNone(pushes.tuesday_push(WED_802, []))
        self.assertEqual([c["title"] for c in self.calls], ["Week 10 plan ready", "Today: 1 thing to fix"])

    def test_forced_wrapup_pushes_itself(self):
        pushes.wrapup_deliver(TUE_802, force=True)(wrap_model(TUE_802), URLS)
        self.assertEqual(len(self.calls), 1)

    def test_digest_skips_what_the_injury_watch_pushed(self):
        sun = dt.datetime(2026, 11, 15, 14, 5, tzinfo=UTC)                 # Sunday 8:05am CST
        lg = SimpleNamespace(name="Domo", key="espn:1", week=11,
                             starters=[{"id": "7", "name": "Hurt RB"}, {"id": "8", "name": "Bye WR"}], bench=[])
        items = [{"league": "Domo", "urgent": True, "text": "Hurt RB (RB) OUT → start Backup RB (9.1 proj)"},
                 {"league": "Domo", "urgent": True, "text": "Bye WR (WR) on BYE → start Bench WR (8.0 proj)"}]
        notify.mark(["espn:1:w11:7:swap"])                                  # the watch already said "make this swap"
        self.assertTrue(pushes.digest_push(items, [lg], sun))
        self.assertNotIn("Hurt RB", self.calls[0]["message"])
        self.assertIn("Bye WR", self.calls[0]["message"])
        self.assertEqual(self.calls[0]["title"], "Today: 1 thing to fix")
        self.calls.clear()
        notify.mark(["espn:1:w11:8:fa"])
        notify.ALERTS.write_text(json.dumps({k: v for k, v in self.seen().items() if not k.startswith("digest:")}))
        self.assertFalse(pushes.digest_push(items, [lg], sun))              # everything urgent was pushed already
        self.assertEqual(self.calls, [])


# ---------- (3) stale pool lines ----------

def ev(eid, away, home, spread, kick="2026-10-31T16:00Z"):
    team = lambda n: {"location": n, "abbreviation": n[:4].upper(), "displayName": n, "shortDisplayName": n}
    return L.parse_event({"id": eid, "date": kick, "competitions": [{
        "status": {"type": {"state": "pre"}},
        "competitors": [{"homeAway": "home", "team": team(home)}, {"homeAway": "away", "team": team(away)}],
        "odds": [{"spread": spread, "overUnder": 50.5, "provider": {"name": "DraftKings"},
                  "moneyline": {"home": {"close": {"odds": "-500"}}, "away": {"close": {"odds": "+380"}}}}]}]}, "CFB")


class StaleLines(unittest.TestCase):
    MIDNIGHT = dt.datetime(2026, 10, 31, 5, 0, tzinfo=UTC)       # Sat 12:00am CDT
    SIX30 = dt.datetime(2026, 10, 31, 11, 30, tzinfo=UTC)        # Sat 6:30am CDT

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        slate = {"cfbd_week": 9, "cfp": {"games": [{"away": "Auburn", "home": "Ole Miss", "home_spread": -13.5},
                                                   {"away": "Arizona", "home": "Texas Tech", "home_spread": -3.5}]}}
        (self.tmp / "slates").mkdir()
        (self.tmp / "slates/2026-w09.json").write_text(json.dumps(slate))
        self.events = {"CFB": [ev("10", "Auburn", "Ole Miss", -11.5), ev("11", "Arizona", "Texas Tech", -3.5)],
                       "NFL": []}
        self.notify = mock.MagicMock(return_value=True)
        self.patches = [mock.patch.object(L, "ROOT", self.tmp), mock.patch.object(L, "OUT", self.tmp / "out.json"),
                        mock.patch.object(L, "SENT", self.tmp / "sent.json"),
                        mock.patch("pp.publish.notify", self.notify),            # never a real ntfy call
                        mock.patch("pp.publish.requests.post", side_effect=AssertionError("network push")),
                        mock.patch.dict(os.environ, {"DRY_RUN": "0"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_at(self, now, origin=lambda: {}):
        return L.run(None, True, now, lambda league, week: self.events[league], origin=origin)[2]

    def test_quiet_hours_hold_then_push_at_6am(self):
        self.assertEqual(self.run_at(self.MIDNIGHT), [])                    # 12am: held, still flagged on the page
        out = json.loads((self.tmp / "out.json").read_text())
        self.assertTrue(out["rows"][0]["flag"])
        self.assertEqual(self.notify.call_count, 0)
        self.assertEqual([r["side"] for r in self.run_at(self.SIX30)], ["Auburn"])   # 6:30am: it goes
        self.assertEqual(self.notify.call_count, 1)
        self.assertEqual(L.held(dt.datetime(2026, 11, 5, 7, 29, tzinfo=UTC), {}), "quiet hours")   # the Nov 5 1:29am one
        self.assertEqual(L.held(dt.datetime(2026, 11, 5, 4, 0, tzinfo=UTC), {}), "quiet hours")    # Wed 10pm CST
        self.assertIsNone(L.held(dt.datetime(2026, 11, 5, 3, 59, tzinfo=UTC), {}))                 # 9:59pm CST
        self.assertIsNone(L.held(dt.datetime(2026, 11, 5, 12, 0, tzinfo=UTC), {}))                 # 6am CST

    def test_one_push_a_day(self):
        self.run_at(self.SIX30)
        self.events["CFB"][1] = ev("11", "Arizona", "Texas Tech", -1.0)       # a second line goes stale at 7:30
        self.assertEqual(self.run_at(self.SIX30 + dt.timedelta(hours=1)), [])
        self.assertEqual(self.notify.call_count, 1)
        sent = json.loads((self.tmp / "sent.json").read_text())
        self.assertIn("push-day:2026-10-31", sent)
        self.assertEqual(L.held(self.SIX30 + dt.timedelta(days=1, hours=1), sent), None)   # tomorrow 6:30am CST it can

    def test_line_another_run_pushed_is_skipped(self):
        theirs = {"9:cfp:Auburn @ Ole Miss": "2026-10-31T11:20:00+00:00"}
        self.assertEqual(self.run_at(self.SIX30, origin=lambda: theirs), [])
        self.assertEqual(self.notify.call_count, 0)
        self.assertIn("9:cfp:Auburn @ Ole Miss", json.loads((self.tmp / "sent.json").read_text()))

    def test_origin_not_read_outside_actions(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "NTFY_TOPIC": ""}), \
                mock.patch("subprocess.run", side_effect=AssertionError("git called")):
            self.assertEqual(L.origin_sent(), {})


# ---------- (4) laptop / Chrome outage: one push ----------

def kick_row(last):
    return {"job": "Laptop kick (laptop, daily 2:55am)", "last": last}


class OneOutageOnePush(Pushes):
    T = dt.datetime(2026, 11, 10, 10, 30, tzinfo=UTC)            # Tue 4:30am CST

    def test_every_symptom_in_one_push(self):
        causes = [pushes.stale_cause("Domo", self.T - dt.timedelta(hours=31)),
                  pushes.stale_cause("Stempak", self.T - dt.timedelta(hours=31)),
                  pushes.stale_cause("Kosmonauts", self.T - dt.timedelta(hours=31), "Yahoo (laptop roster sync)"),
                  run.KICK_SILENT]
        jobs = [kick_row("2026-11-09T08:55:00Z")]
        self.assertEqual(pushes.outage_push(self.T, causes, jobs), "Laptop/roster sync down")
        self.assertEqual(len(self.calls), 1)
        msg = self.calls[0]["message"]
        for who in ("Domo: last read from ESPN", "Stempak: last read from ESPN", "Kosmonauts: last read from Yahoo",
                    "No laptop kick since 2:55am today"):
            self.assertIn(who, msg)
        for minutes in (10, 600, 60 * 24):                                   # the same outage, later passes and days
            pushes.outage_push(self.T + dt.timedelta(minutes=minutes), causes, jobs)
        pushes.outage_push(self.T + dt.timedelta(hours=20), [], jobs)        # 12:30am: no kick check yet, still open
        pushes.outage_push(self.T + dt.timedelta(hours=24), [run.KICK_SILENT], jobs)
        self.assertEqual(len(self.calls), 1)

    def test_symptoms_found_in_different_passes_are_one_outage(self):
        jobs = [kick_row("2026-11-09T08:55:00Z")]
        pushes.outage_push(self.T, [run.KICK_SILENT], jobs)                 # 4:30am: no kick
        later = self.T + dt.timedelta(hours=30)                               # next day the snapshots go stale too
        pushes.outage_push(later, [pushes.stale_cause("Domo", later - dt.timedelta(hours=31)), run.KICK_SILENT], jobs)
        self.assertEqual(len(self.calls), 1)

    def test_recovery_then_a_new_outage_pushes_again(self):
        pushes.outage_push(self.T, [run.KICK_SILENT], [kick_row("2026-11-09T08:55:00Z")])
        back = self.T + dt.timedelta(days=1)
        pushes.outage_push(back, [], [kick_row(run.iso(back - dt.timedelta(hours=1)))])   # the laptop kicked again
        self.assertIn("laptop-up", self.seen())
        again = back + dt.timedelta(days=2)
        pushes.outage_push(again, [run.KICK_SILENT], [kick_row(run.iso(back))])
        self.assertEqual(len(self.calls), 2)

    def test_chrome_down_laptop_up_stays_one_push(self):
        stale = [pushes.stale_cause("Domo", self.T - dt.timedelta(hours=31))]
        pushes.outage_push(self.T, stale, [kick_row(run.iso(self.T - dt.timedelta(hours=1)))])
        nxt = self.T + dt.timedelta(days=1)                                   # the laptop still kicks; Chrome still down
        pushes.outage_push(nxt, stale, [kick_row(run.iso(nxt - dt.timedelta(hours=1)))])
        self.assertEqual(len(self.calls), 1)

    def test_no_symptoms_no_push(self):
        self.assertIsNone(pushes.outage_push(self.T, [], [kick_row(run.iso(self.T))]))
        self.assertEqual(self.calls, [])


# ---------- shared dedupe state across parallel runs ----------

class SharedState(Pushes):
    def test_key_pushed_by_another_run_is_not_pushed_again(self):
        with mock.patch.object(notify, "live", return_value=True), \
                mock.patch.object(notify, "origin_state", return_value={"digest:2026-11-10": "2026-11-10T14:01:00Z"}):
            self.assertFalse(notify.push_once("digest:2026-11-10", "t", "m"))
            self.assertTrue(notify.push_once("digest:2026-11-11", "t", "m"))
        self.assertEqual(len(self.calls), 1)
        self.assertIn("digest:2026-11-10", self.seen())                     # kept here: no fetch next pass

    def test_origin_never_read_outside_actions(self):
        self.assertTrue(notify.push_once("k", "t", "m"))                     # origin_state would raise if called
        self.assertFalse(notify.live())

    def test_merge_keeps_both_sides(self):
        a, b = self.tmp / "a.json", self.tmp / "b.json"
        a.write_text(json.dumps({"x": "2026-11-10T13:00:00Z", "both": "2026-11-10T13:00:00Z"}))
        b.write_text(json.dumps({"y": "2026-11-10T14:00:00Z", "both": "2026-11-10T14:00:00Z"}))
        statemerge.main(["o", str(a), str(b)])
        self.assertEqual(json.loads(a.read_text()), {"x": "2026-11-10T13:00:00Z", "both": "2026-11-10T14:00:00Z",
                                                     "y": "2026-11-10T14:00:00Z"})
        a.write_text("not json")
        statemerge.main(["o", str(a), str(b)])
        self.assertIn("y", json.loads(a.read_text()))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_rebase_with_theirs_keeps_both_runs_keys(self):
        """commit_data.sh's `git pull --rebase -X theirs` with the pushstate driver: neither run's keys are lost
        (without the driver, the kick run's key is dropped)."""
        self.assertEqual(self.rebase(driver=True), {"old", "kick-run", "cron-run"})
        self.assertEqual(self.rebase(driver=False), {"old", "cron-run"})

    def rebase(self, driver):
        repo = self.tmp / f"repo{int(driver)}"
        repo.mkdir()

        def git(*a, cwd=repo):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=cwd,
                                  check=True, capture_output=True, text=True)
        git("init", "-q", "-b", "main")
        if driver:
            git("config", "merge.pushstate.driver",
                f'"{Path(sys.executable).as_posix()}" "{Path(statemerge.__file__).as_posix()}" %O %A %B')
        (repo / ".gitattributes").write_text("state/alerts.json merge=pushstate\n")
        (repo / "state").mkdir()
        alerts = repo / "state" / "alerts.json"
        alerts.write_text(json.dumps({"old": "2026-11-09T00:00:00Z"}, indent=1))
        git("add", ".")
        git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "other")
        alerts.write_text(json.dumps({"old": "2026-11-09T00:00:00Z", "kick-run": "2026-11-10T14:01:00Z"}, indent=1))
        git("commit", "-q", "-am", "kick run")
        git("checkout", "-q", "main")
        alerts.write_text(json.dumps({"old": "2026-11-09T00:00:00Z", "cron-run": "2026-11-10T14:02:00Z"}, indent=1))
        git("commit", "-q", "-am", "cron run")
        git("rebase", "-q", "-X", "theirs", "other")
        return set(json.loads(alerts.read_text()))


if __name__ == "__main__":
    unittest.main()
