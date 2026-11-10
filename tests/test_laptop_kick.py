"""Q-037: GitHub notices when the laptop stops starting jobs. The 2:55am model-health kick is the laptop's daily heartbeat;
from 4am CT with no model-health dispatch since 2:50am today, one push that day. Also the footer's "Laptop kick" row."""
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import notify, run  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, 10, 30, tzinfo=UTC)          # Tue 4:30am CST
KICK = dt.datetime(2026, 11, 10, 8, 55, 12, tzinfo=UTC)      # 2:55am CST
YESTERDAY = dt.datetime(2026, 11, 9, 8, 55, tzinfo=UTC)


class LaptopKicks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = notify.ALERTS, run.push_once
        notify.ALERTS = Path(self.tmp.name) / "alerts.json"
        run.push_once = notify.push_once          # other test files replace it with a no-dedup stand-in
        notify.sent.clear()

    def tearDown(self):
        notify.ALERTS, run.push_once = self.saved
        notify.sent.clear()
        self.tmp.cleanup()

    def test_kick_today_no_push(self):
        row = run.laptop_kicks(NOW, lambda: [YESTERDAY, KICK])
        self.assertEqual(row, {"job": "Laptop kick (laptop, daily 2:55am)", "last": "2026-11-10T08:55:12Z"})
        self.assertEqual(notify.sent, [])

    def test_no_kick_today_pushes_once_a_day(self):
        for minutes in (0, 10, 600):
            run.laptop_kicks(NOW + dt.timedelta(minutes=minutes), lambda: [YESTERDAY])
        self.assertEqual(len(notify.sent), 1)
        self.assertEqual(notify.sent[0]["title"], "Laptop didn't start today's Sports HQ jobs")
        self.assertIn("GitHub's own schedule (hours late) is all that's running", notify.sent[0]["message"])
        self.assertIn("laptop-kick-silent:2026-11-10", notify.load_json(notify.ALERTS))
        run.laptop_kicks(NOW + dt.timedelta(days=1), lambda: [YESTERDAY])       # the next day pushes again
        self.assertEqual(len(notify.sent), 2)

    def test_late_kick_counts(self):
        late = dt.datetime(2026, 11, 10, 12, 5, tzinfo=UTC)                     # 6:05am: the laptop woke and ran it
        run.laptop_kicks(late + dt.timedelta(minutes=5), lambda: [late])
        self.assertEqual(notify.sent, [])

    def test_before_4am_no_push(self):
        run.laptop_kicks(dt.datetime(2026, 11, 10, 9, 50, tzinfo=UTC), lambda: [YESTERDAY])   # 3:50am CST
        self.assertEqual(notify.sent, [])

    def test_unreadable_no_row_no_push(self):
        self.assertIsNone(run.laptop_kicks(NOW, lambda: None))
        self.assertEqual(notify.sent, [])

    def test_never_kicked(self):
        self.assertEqual(run.laptop_kicks(NOW, lambda: [])["last"], None)
        self.assertEqual(len(notify.sent), 1)

    def test_cdt(self):
        # summer: 2:55am CDT is 07:55Z; checked from 4am CDT (09:00Z)
        summer_kick = dt.datetime(2027, 6, 1, 7, 55, tzinfo=UTC)
        run.laptop_kicks(dt.datetime(2027, 6, 1, 9, 5, tzinfo=UTC), lambda: [summer_kick])
        self.assertEqual(notify.sent, [])

    def test_job_health_row_first_and_errors_contained(self):
        jobs = run.job_health(NOW, kicks=lambda now: {"job": "Laptop kick (laptop, daily 2:55am)", "last": None})
        self.assertEqual(jobs[0]["job"], "Laptop kick (laptop, daily 2:55am)")
        jobs = run.job_health(NOW, kicks=lambda now: 1 / 0)                       # a broken check never breaks the run
        self.assertNotIn("Laptop kick", " ".join(j["job"] for j in jobs))

    def test_gh_not_called_outside_actions(self):
        saved = os.environ.pop("GITHUB_ACTIONS", None)
        try:
            self.assertIsNone(run.gh_dispatches())
        finally:
            if saved is not None:
                os.environ["GITHUB_ACTIONS"] = saved


if __name__ == "__main__":
    unittest.main()
