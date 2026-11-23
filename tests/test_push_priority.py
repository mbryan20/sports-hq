"""Michael's rule (Nov 23, 2026): a push that needs him within 24 hours, is about money, or says something broke keeps
its sound (ntfy priority at least 4); everything else is silent (priority 2). Unsure = urgent.
Every push here goes to a stand-in or a mocked network call: nothing reaches ntfy."""
import datetime as dt
import os
import pathlib
import re
import sys
import unittest
from unittest import mock

os.environ["DRY_RUN"] = "1"

from shq import notify, pushes, radar, wrapup  # noqa: E402
from test_push_dedupe import (DIGEST_ITEMS, TUE_702, TUE_802, URLS, Pushes, kick_row, nba_league, riser,  # noqa: E402
                              wrap_model)

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "picks"))
from pp import lines as L, publish as P  # noqa: E402

UTC = dt.timezone.utc
CT = P.CT


class Level(unittest.TestCase):
    def test_urgent_is_at_least_4_and_keeps_higher(self):
        for f in (notify.level, P.level):
            self.assertEqual(f(True, None), 4)    # unset: ntfy's default 3 would ring, but urgent says 4
            self.assertEqual(f(True, 3), 4)
            self.assertEqual(f(True, 4), 4)
            self.assertEqual(f(True, 5), 5)       # CHECK LINEUP keeps its 5
            self.assertEqual(f(True, 9), 5)
            self.assertEqual(f(), 4)              # unsure = urgent

    def test_everything_else_is_silent(self):
        for f in (notify.level, P.level):
            self.assertEqual(f(False, None), 2)
            self.assertEqual(f(False, 5), 2)

    def test_shq_push_sends_the_level(self):
        with mock.patch.dict(os.environ, {"DRY_RUN": "0", "NTFY_TOPIC": "test-topic-not-real"}), \
                mock.patch.object(notify.session, "post") as post:
            notify.push("t", "m")
            notify.push("t", "m", priority=5)
            notify.push("t", "m", urgent=False)
        self.assertEqual([c.kwargs["json"]["priority"] for c in post.call_args_list], [4, 5, 2])
        self.assertEqual(notify.sent[-1]["priority"], 2)

    def test_picks_push_sends_the_level(self):
        with mock.patch.object(P, "topic", return_value="test-topic-not-real"), \
                mock.patch.object(P.requests, "post") as post:
            P.notify("t", "m")
            P.notify("t", "m", urgent=False)
        self.assertEqual([c.kwargs["headers"]["Priority"] for c in post.call_args_list], ["4", "2"])


class ShqPushes(Pushes):
    """Which Sports HQ pushes ring and which are silent."""
    def test_weekly_plan_is_silent(self):
        pushes.plan_push(dt.datetime(2026, 11, 11, 14, 2, tzinfo=UTC), 10)   # Wednesday: a catch-up plan push
        self.assertEqual([c["priority"] for c in self.calls], [2])

    def test_tuesday_bundle_rings_only_with_something_to_fix(self):
        self.write("data/weekly.json", {"generated": notify.iso(TUE_702), "week": 10, "leagues": []})
        self.write("data/digest.json", {"generated": notify.iso(TUE_802), "title": "x", "items": DIGEST_ITEMS})
        pushes.tuesday_push(TUE_802, [])
        self.assertEqual(self.calls[-1]["priority"], 4)

    def test_tuesday_bundle_all_clear_is_silent(self):
        self.write("data/weekly.json", {"generated": notify.iso(TUE_702), "week": 10, "leagues": []})
        self.write("data/digest.json", {"generated": notify.iso(TUE_802), "title": "x", "items": [DIGEST_ITEMS[1]]})
        pushes.tuesday_push(TUE_802, [])
        self.assertEqual(self.calls[-1]["priority"], 2)

    def test_digest_with_a_fix_rings(self):
        wed = dt.datetime(2026, 11, 11, 14, 2, tzinfo=UTC)
        self.assertTrue(pushes.digest_push(DIGEST_ITEMS, [], wed))
        pushes.digest_push([DIGEST_ITEMS[1]], [], wed, forced=True)          # forced, nothing urgent: silent
        self.assertEqual([c["priority"] for c in self.calls], [4, 2])

    def test_outage_rings(self):
        pushes.outage_push(dt.datetime(2026, 11, 10, 10, 30, tzinfo=UTC), ["ESPN stale"],
                           [kick_row("2026-11-09T08:55:00Z")])
        self.assertEqual([c["priority"] for c in self.calls], [4])

    def test_wrapup_is_silent(self):
        wrapup.send(wrap_model(TUE_802), URLS)
        self.assertEqual([c["priority"] for c in self.calls], [2])

    def test_radar_is_silent(self):
        now = TUE_702
        radar.send_all([(nba_league("Ball is Life", "bil", now), {"radar": {"rising": [riser("1", "A Riser")]}})])
        self.assertEqual([c["priority"] for c in self.calls], [2])


class PoolPicks(unittest.TestCase):
    SLATE = {"bto": {"games": [{"kick": "Sat 11/21 11:00 AM CT"}]},
             "cfp": {"deadline": "2026-11-21T11:00:00-06:00", "games": []},
             "yahoo": {"games": [{"kick": "Fri 11/20 5:00 PM"}, {"kick": "Thu 11/19 7:15 PM", "locked": True}]}}
    WED = dt.datetime(2026, 11, 18, 20, 0, tzinfo=CT)    # Wed 8pm: first lock (Yahoo Fri 5pm) is 45h away
    THU = dt.datetime(2026, 11, 19, 20, 0, tzinfo=CT)    # Thu 8pm: Yahoo Fri 5pm is 21h away

    def test_next_lock(self):
        self.assertEqual(P.next_lock(self.SLATE, self.WED), dt.datetime(2026, 11, 20, 17, 0, tzinfo=CT))
        sat = dt.datetime(2026, 11, 21, 9, 0, tzinfo=CT)
        self.assertEqual(P.next_lock(self.SLATE, sat), dt.datetime(2026, 11, 21, 11, 0, tzinfo=CT))
        self.assertEqual(P.next_lock({}, sat), None)
        fri = dt.datetime(2026, 11, 20, 18, 0, tzinfo=CT)           # BTO bets due Fri 8pm
        self.assertEqual(P.next_lock({"bto": {"games": [{"kick": "Sat 11/21 11:00 AM CT"}]}}, fri),
                         dt.datetime(2026, 11, 20, 20, 0, tzinfo=CT))

    def test_stage_rules(self):
        ok = "BTO (locks Fri 8pm): your saved picks match"
        self.assertFalse(P.push_urgent("postmortem", "x", True, self.SLATE, self.THU, note=True))
        self.assertTrue(P.push_urgent("final", ok, False, self.SLATE, self.WED))      # final: always rings
        self.assertTrue(P.push_urgent("bto-check", ok, False, self.SLATE, self.WED))  # any stage not listed: unsure
        self.assertFalse(P.push_urgent("draft", ok, False, self.SLATE, self.THU))     # nothing to fix: silent
        self.assertFalse(P.push_urgent("draft", "CHANGE: ...", True, self.SLATE, self.WED))   # lock 45h away
        self.assertTrue(P.push_urgent("draft", "CHANGE: ...", True, self.SLATE, self.THU))    # lock 21h away
        self.assertTrue(P.push_urgent("draft", "CFP: x (nothing saved yet)", False, self.SLATE, self.THU))
        self.assertTrue(P.push_urgent("draft", "CHANGE: ...", True, {}, self.WED))    # lock unknown: unsure
        self.assertTrue(P.push_urgent("draft", "build failed", False, self.SLATE, self.WED, note=True))
        sat = dt.datetime(2026, 11, 21, 8, 0, tzinfo=CT)
        self.assertTrue(P.push_urgent("refresh", "CHANGE: ...", True, self.SLATE, sat))
        self.assertFalse(P.push_urgent("refresh", ok, False, self.SLATE, sat))

    def test_stale_line_rings_only_when_its_pool_closes_within_a_day(self):
        now = dt.datetime(2026, 11, 19, 14, 0, tzinfo=UTC)
        soon = {"closes": "2026-11-20T08:00:00-06:00"}
        later = {"closes": "2026-11-21T11:00:00-06:00"}
        self.assertTrue(L.closes_soon([later, soon], now))
        self.assertFalse(L.closes_soon([later], now))
        self.assertTrue(L.closes_soon([{}], now))                       # no close time: unsure = urgent


class NoQuietPushSlipsBy(unittest.TestCase):
    """Guards: the silent pushes are exactly the ones in the table, nothing asks for a priority under 4, and every
    GitHub failure push rings."""
    def test_silent_call_sites(self):
        found = {}
        for f in list((ROOT / "shq").glob("*.py")) + list((ROOT / "picks" / "pp").glob("*.py")):
            n = f.read_text(encoding="utf-8").count("urgent=False")
            if n:
                found[f.relative_to(ROOT).as_posix()] = n
        self.assertEqual(found, {"shq/pushes.py": 1, "shq/radar.py": 1, "shq/wrapup.py": 1, "shq/run.py": 1})

    def test_no_low_priority_numbers(self):
        for f in list((ROOT / "shq").glob("*.py")) + list((ROOT / "picks" / "pp").glob("*.py")):
            self.assertIsNone(re.search(r"priority=[0-3]\b", f.read_text(encoding="utf-8")), f.name)

    def test_workflow_pushes_ring(self):
        for f in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = f.read_text(encoding="utf-8")
            for m in re.finditer(r"curl [^\n]*-H \"Title:[^\n]*", text):
                self.assertRegex(m.group(0), r"Priority: [45]", f"{f.name}: {m.group(0)[:80]}")


if __name__ == "__main__":
    unittest.main()
