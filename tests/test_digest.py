"""Daily digest: once per day after 8am CT, urgent items for dead starters, quiet NBA off nights."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import advice, digest

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 29, 13, 30, tzinfo=UTC)          # Thu 8:30am CDT
TNF = dt.datetime(2026, 10, 30, 0, 15, tzinfo=UTC)           # Thu 7:15pm CDT
SUN = dt.datetime(2026, 11, 1, 18, 0, tzinfo=UTC)


def p(name, slot, positions, *, status=None, kickoff=SUN, bye=False, proj=10.0, pid=None):
    return {"id": pid or name, "name": name, "slot": slot, "positions": positions, "status": status, "why": "",
            "kickoff": None if bye else kickoff, "started": False, "bye": bye, "proj": proj, "team": "X"}


class League:
    name, sport, free_agents, opponent, opp_proj = "Test", "nfl", [], "Rival", 20.0
    def __init__(self, starters, bench, sport="nfl"):
        self.starters, self.bench, self.sport = starters, bench, sport
    def best_fa(self, positions, now):
        return None


class Digest(unittest.TestCase):
    def test_due_once_per_day(self):
        early = dt.datetime(2026, 10, 29, 12, 50, tzinfo=UTC)    # 7:50am CDT
        self.assertFalse(digest.due(early, None))
        self.assertTrue(digest.due(NOW, NOW - dt.timedelta(hours=20)))
        self.assertFalse(digest.due(NOW + dt.timedelta(hours=1), NOW))
        winter = dt.datetime(2026, 11, 5, 14, 5, tzinfo=UTC)    # 8:05am CST
        self.assertTrue(digest.due(winter, NOW))

    def test_nfl_bye_and_out(self):
        lg = League([p("Bye WR", "WR", ["WR"], bye=True), p("Hurt RB", "RB", ["RB"], status="OUT"),
                     p("Thu TE", "TE", ["TE"], status="Q", kickoff=TNF)],
                    [p("Spare WR", "BN", ["WR"], proj=8.0), p("Spare RB", "BN", ["RB"], proj=6.0)])
        items = digest.league_items(lg, NOW)
        texts = [i["text"] for i in items]
        self.assertTrue(any("Bye WR (WR) on BYE → start Spare WR" in t for t in texts))
        self.assertTrue(any("Hurt RB (RB) OUT → start Spare RB" in t for t in texts))
        self.assertTrue(any("Thu TE (TE) is Questionable" in t for t in texts))
        self.assertTrue(any("1 starters play today" in t for t in texts))
        title, _ = digest.message(items)
        self.assertEqual(title, "Today: 2 things to fix")

    def test_nba_off_night_is_quiet_without_bench_cover(self):
        tonight = dt.datetime(2026, 10, 30, 0, 30, tzinfo=UTC)
        lg = League([p("Idle G", "G", ["PG", "G"], bye=True), p("Playing C", "C", ["C"], kickoff=tonight)],
                    [p("Bench C", "BN", ["C"], kickoff=tonight)], sport="nba")
        items = digest.league_items(lg, NOW)
        self.assertFalse(any(i["urgent"] for i in items))
        lg.bench.append(p("Bench G", "BN", ["SG", "G"], kickoff=tonight))
        items = digest.league_items(lg, NOW)
        self.assertTrue(any(i["urgent"] and "start Bench G" in i["text"] for i in items))

    def test_guillotine_danger(self):
        lg = League([], [])
        lg.standing = {"rank": 11, "n": 12, "gap": -3.2}
        item = digest.league_items(lg, NOW)[0]
        self.assertTrue(item["urgent"])
        self.assertIn("DANGER ZONE", item["text"])

    def test_advice_block(self):
        lg = League([p("Hurt RB", "RB", ["RB"], status="OUT"), p("Weak WR", "WR", ["WR"], proj=3.0)],
                    [p("Spare RB", "BN", ["RB"], proj=6.0), p("Good WR", "BN", ["WR"], proj=9.0)])
        a = advice.build(lg, NOW)
        self.assertEqual(a["fixes"], ["Hurt RB (RB) OUT → start Spare RB (6.0 proj)"])
        self.assertEqual(a["moves"], ["Start Good WR (9.0) over Weak WR (3.0) at WR, +6.0"])
        self.assertIn("projected to lose by 17.0", a["matchup"])
        lg.standing = {"rank": 2, "n": 10, "gap": 30.0}
        a = advice.build(lg, NOW)
        self.assertTrue(a["matchup"].startswith("Projected 2 of 10"))
        self.assertFalse(a["danger"])


if __name__ == "__main__":
    unittest.main()
