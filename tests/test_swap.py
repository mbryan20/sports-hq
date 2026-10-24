"""Dry-run of the Yahoo auto-swap against a fake Yahoo API: decide the swap, send the lineup XML,
read the roster back, confirm, and produce the "Swapped X → Y" push. No network."""
import datetime as dt
import os
import unittest
import xml.etree.ElementTree as ET

os.environ["DRY_RUN"] = "1"  # never hit ntfy from tests

from shq import notify, run
from shq.leagues import YahooLeague
from shq.swap import fa_adds, plan_injury_swaps, start_sit
from shq.yahoo import YahooWriteDenied

NOW = dt.datetime(2026, 10, 25, 16, 0, tzinfo=dt.timezone.utc)   # 11am CT Sunday
NOON = dt.datetime(2026, 10, 25, 17, 0, tzinfo=dt.timezone.utc)  # noon CT kickoff
LATE = dt.datetime(2026, 10, 25, 20, 25, tzinfo=dt.timezone.utc)


def yp(key, name, pos, team, slot, status=None):
    return {"key": key, "yahoo_id": key.split(".")[-1], "name": name, "team": team, "pos": pos,
            "eligible": [pos], "slot": slot, "status": status}


class FakeYahoo:
    """Mimics the bits of the Yahoo API YahooLeague uses, applying PUTs to its in-memory roster."""

    def __init__(self, roster, writable=True, ignore_writes=False):
        self.roster_ = {p["key"]: dict(p) for p in roster}
        self.writable, self.ignore_writes, self.puts = writable, ignore_writes, []

    def my_team(self, name, season):
        return "461.l.1", "461.l.1.t.3", "My Team"

    def roster(self, tk, week):
        return [dict(p) for p in self.roster_.values()]

    def opponent(self, tk, week):
        return "Rival"

    def free_agents(self, lk, pos, count=25):
        return [yp("461.p.900", "Waiver Wire WR", "WR", "NYJ", None)] if pos == "WR" else []

    def set_positions(self, tk, week, moves):
        from shq.yahoo import lineup_xml
        if not self.writable:
            raise YahooWriteDenied("HTTP 403")
        xml = lineup_xml(week, moves)
        self.puts.append(xml)
        if self.ignore_writes:
            return
        for p in ET.fromstring(xml).iter("player"):
            self.roster_[p.findtext("player_key")]["slot"] = p.findtext("position")


class Ctx:
    week, now = 7, NOW
    games = {
        "NYJ": {"kickoff": NOON, "state": "pre", "opp": "MIA", "home": True},
        "MIA": {"kickoff": NOON, "state": "pre", "opp": "NYJ", "home": False},
        "DET": {"kickoff": LATE, "state": "pre", "opp": "GB", "home": True},
        "GB": {"kickoff": LATE, "state": "pre", "opp": "DET", "home": False},
    }
    proj = {"s1": {"stats": {"rec": 6, "rec_yd": 80}}, "s2": {"stats": {"rec": 4, "rec_yd": 50}},
            "s3": {"stats": {"rec": 3, "rec_yd": 30}}, "s9": {"stats": {"rec": 5, "rec_yd": 70}}}
    players = {}
    espn_inj = {}
    yahoo_to_sleeper = {"101": "s1", "102": "s2", "103": "s3", "900": "s9"}


ROSTER = [
    yp("461.p.101", "Starter WR", "WR", "NYJ", "WR", status="O"),   # ruled out, noon game
    yp("461.p.104", "Other WR", "WR", "DET", "WR"),
    yp("461.p.102", "Bench WR", "WR", "MIA", "BN"),                 # healthy, noon game
    yp("461.p.103", "Bench WR Q", "WR", "MIA", "BN", status="Q"),   # questionable: not "healthy"
    yp("461.p.105", "Bench RB", "RB", "MIA", "BN"),                 # wrong position (no flex)
]


class SwapDryRun(unittest.TestCase):
    def setUp(self):
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)

    def league(self, **kw):
        lg = YahooLeague(Ctx(), client=FakeYahoo(ROSTER, **kw))
        return lg

    def test_plan_picks_healthy_same_position(self):
        lg = self.league()
        plan = plan_injury_swaps(lg.starters, lg.bench, NOW)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["out"]["name"], "Starter WR")
        self.assertEqual(plan[0]["in"]["name"], "Bench WR")

    def test_outside_window_does_nothing(self):
        lg = self.league()
        self.assertEqual(plan_injury_swaps(lg.starters, lg.bench, NOON - dt.timedelta(hours=3)), [])
        self.assertEqual(plan_injury_swaps(lg.starters, lg.bench, NOON + dt.timedelta(minutes=1)), [])

    def test_swap_executes_and_reads_back(self):
        os.environ["DRY_RUN"] = "0"
        try:
            lg = self.league()
            actions = run.injury_watch(lg, NOW)
        finally:
            os.environ["DRY_RUN"] = "1"
        self.assertEqual(actions, ["swapped Starter WR -> Bench WR"])
        put = lg.y.puts[0]
        self.assertIn("<player_key>461.p.101</player_key><position>BN</position>", put)
        self.assertIn("<player_key>461.p.102</player_key><position>WR</position>", put)
        self.assertEqual(lg.y.roster_["461.p.102"]["slot"], "WR")
        self.assertEqual(notify.sent[-1]["message"].split(" (")[0], "Swapped Starter WR → Bench WR")

    def test_readback_mismatch_alerts(self):
        os.environ["DRY_RUN"] = "0"
        try:
            lg = self.league(ignore_writes=True)
            actions = run.injury_watch(lg, NOW)
        finally:
            os.environ["DRY_RUN"] = "1"
        self.assertEqual(actions, ["swap unconfirmed Starter WR"])
        self.assertIn("CHECK LINEUP", notify.sent[-1]["title"])

    def test_no_write_scope_falls_back_to_push(self):
        os.environ["DRY_RUN"] = "0"
        try:
            lg = self.league(writable=False)
            actions = run.injury_watch(lg, NOW)
        finally:
            os.environ["DRY_RUN"] = "1"
        self.assertEqual(actions, ["suggested Starter WR -> Bench WR"])
        self.assertIn("start Bench WR", notify.sent[-1]["message"])

    def test_no_bench_suggests_free_agent_never_adds(self):
        roster = [p for p in ROSTER if p["key"] != "461.p.102"]
        lg = YahooLeague(Ctx(), client=FakeYahoo(roster))
        actions = run.injury_watch(lg, NOW)
        self.assertEqual(actions, ["no bench for Starter WR"])
        self.assertIn("Best FA: Waiver Wire WR", notify.sent[-1]["message"])
        self.assertEqual(lg.y.puts, [])  # nothing written: no add/drop

    def test_weekly_helpers(self):
        lg = self.league()
        self.assertTrue(start_sit(lg.starters, lg.bench))
        self.assertEqual(fa_adds(lg.starters + lg.bench, lg.free_agents)[0][1]["name"], "Waiver Wire WR")

    def test_weekly_due_tuesday_7am_ct(self):
        tue_655 = dt.datetime(2026, 11, 3, 12, 55, tzinfo=dt.timezone.utc)  # CST after DST ends: 6:55am
        tue_705 = dt.datetime(2026, 11, 3, 13, 5, tzinfo=dt.timezone.utc)
        last = dt.datetime(2026, 10, 27, 12, 5, tzinfo=dt.timezone.utc)     # previous Tue 7:05 CDT
        self.assertFalse(run.weekly_due(tue_655, last))
        self.assertTrue(run.weekly_due(tue_705, last))
        self.assertFalse(run.weekly_due(tue_705 + dt.timedelta(hours=1), tue_705))


if __name__ == "__main__":
    unittest.main()
