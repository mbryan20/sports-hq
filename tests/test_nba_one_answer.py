"""Q-047: one answer per NBA player on a league tab. Regressions for the three contradictions on the live site on Nov 10:
1. Ball is Life: the radar said "Obi Toppin, on your bench: start him" while Waiver adds (and the weekly plan) said
   "Drop Obi Toppin"; the weekly plan dropped Draymond Green while the radar had him rising.
2. 3-Ball BB: the chase said "FG% is close. Keep in the lineup: Jarrett Allen" with Allen on the bench and shrinking.
3. 3-Ball BB: the radar said "start him" for three bench players while Lineup moves was empty.
Fixtures only, no network (the radar's ESPN pool is test_radar.POOL)."""
import copy
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

from shq import advice, categories, nba_lineup, nba_swaps, notify, radar, run
from shq.leagues import EspnLeague
import test_categories as cb
import test_radar as rb

# my roster in the radar fixture: Atlanta Riser (101) rising because Atlanta Star is out (Toppin: a rise with a cause),
# Boston Guard (200) rising with no cause after 3 games (may fade), Boston Big (201) starting and shrinking
ROSTER = [rb.rp(201, "Boston Big", 2, 0), rb.rp(200, "Boston Guard", 2, 12), rb.rp(101, "Atlanta Riser", 1, 12)]


def radar_league(roster=ROSTER):
    import shq.espn_fantasy as ef
    snap = copy.deepcopy(rb.SNAP)
    snap["roster"] = copy.deepcopy(roster)
    ef.load_snapshot = lambda sport, lid: snap
    return EspnLeague(rb.Ctx(), {"name": "Test BB", "sport": "nba", "league_id": 190278, "team_id": 5, "private": True})


def vp(pid, name, own, team, v, z, g, pct=5.0):
    return {"id": pid, "name": name, "own": own, "team": team, "pos": "PG", "v": v, "z": z, "g": g, "pct": pct}


VALUES = {"cats": ["AST", "3PM"], "repl": -0.5, "players": [
    vp("101", "Atlanta Riser", "me", "ATL", -4.2, [-1, -1], [3, 3]),       # the worst value: the drop without the radar
    vp("200", "Boston Guard", "me", "BOS", -4.0, [-1, -1], [2, 3]),
    vp("201", "Boston Big", "me", "BOS", 3.0, [1, 1], [2, 3]),
    vp("900", "Free Streamer", None, "UTA", -1.0, [0.5, 0.5], [4, 3], pct=3.0)]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = radar.OWNED, notify.ALERTS, radar.fetch_pool
        radar.OWNED, notify.ALERTS = Path(self.tmp.name) / "owned.json", Path(self.tmp.name) / "alerts.json"
        radar.fetch_pool = lambda *a, **k: rb.POOL

    def tearDown(self):
        radar.OWNED, notify.ALERTS, radar.fetch_pool = self.saved
        self.tmp.cleanup()


class RisingIsNotADrop(Base):
    """1. A player of mine the radar has rising is never a drop, unless his rise may fade."""

    def test_keep_is_my_risers_that_wont_fade(self):
        lg = radar_league()
        r = radar.block(lg, rb.CATS)
        self.assertEqual(r["keep"], ["101"])                               # the injury-caused rise; not the may-fade one
        self.assertEqual({i["name"]: i["fade"] for i in r["rising"] if i["where"] == "bench"},
                         {"Atlanta Riser": False, "Boston Guard": True})

    def test_fades_matches_the_text(self):
        tg = radar.team_games(rb.POOL)
        guard = radar.role(rb.POOL["200"], tg, 9)
        self.assertTrue(radar.fades(guard, [], set()))                      # no cause, 3 straight games
        self.assertFalse(radar.fades({**guard, "streak": 4}, [], set()))    # Draymond: 4+ straight games, kept
        self.assertFalse(radar.fades(guard, ["100"], {"100"}))              # his teammate is still out
        self.assertTrue(radar.fades(guard, ["100"], set()))                 # the teammate is back: "so this may fade"

    def test_swaps_and_weekly_plan_skip_a_rising_player(self):
        lg = radar_league()
        lg.values = VALUES
        without = nba_swaps.build(lg, rb.CATS)
        self.assertEqual(without["swaps"][0]["drop"]["name"], "Atlanta Riser")   # what the site said before
        lg.radar = radar.block(lg, rb.CATS)
        s = nba_swaps.build(lg, rb.CATS)
        drops = [x["drop"]["name"] for x in s["swaps"]]
        self.assertNotIn("Atlanta Riser", drops)
        self.assertEqual(drops, ["Boston Guard"])                           # may fade: still a drop candidate
        self.assertIn("never drops a player the trend radar has rising unless it may fade", s["basis"])
        lg.swaps = s
        weekly = run.nba_weekly_section(lg)["adds"]
        self.assertFalse(any("Drop Atlanta Riser" in a for a in weekly))
        self.assertTrue(weekly[0].startswith("Drop Boston Guard"))


class KeepInTheLineup(unittest.TestCase):
    """2. "Keep in the lineup" names only players starting now whose role isn't shrinking."""

    def test_bench_player_is_not_kept_in_the_lineup(self):
        c = categories.build(cb.league())
        self.assertEqual(c["chase"], ["3PM is close. Keep in the lineup: Atlanta Star (3 games, 3.0/g)."])  # Boston Wing: BN
        self.assertNotIn("Boston Wing", " ".join(c["chase"]))

    def test_shrinking_starter_is_not_kept_in_the_lineup(self):
        c = categories.build(cb.league(), skip=["1"])                       # Atlanta Star's minutes 28 → 18
        self.assertEqual(c["chase"], ["3PM is close; none of your starters has much left there."])

    def test_radar_shrink_ids_reach_the_chase(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = radar.OWNED, radar.fetch_pool
            radar.OWNED, radar.fetch_pool = Path(tmp) / "owned.json", lambda *a, **k: rb.POOL
            try:
                lg = radar_league()
                self.assertEqual(radar.block(lg, rb.CATS)["shrink_ids"], ["201"])
            finally:
                radar.OWNED, radar.fetch_pool = saved


class StartHimOnlyWithAMove(Base):
    """3. The radar says "start him" only when today's Lineup moves start him; otherwise why not."""

    def setUp(self):
        super().setUp()
        self.lg = radar_league()
        self.r = radar.block(self.lg, rb.CATS)
        self.guard = next(b for b in self.lg.bench if b["key"] == 200)
        self.big = next(s for s in self.lg.starters if s["key"] == 201)

    def plays_today(self, bench_v, starter_v):
        tip = rb.NOW + dt.timedelta(hours=4)
        for row, v in ((self.guard, bench_v), (self.big, starter_v)):
            row.update(kickoff=tip, bye=False, started=False, status=None, cv={"v": v})

    def bench_text(self, name):
        return next(i["text"] for i in self.r["rising"] if i["name"] == name)

    def test_no_game_today_is_not_start_him(self):
        self.assertIsNone(self.guard["kickoff"])                            # BOS doesn't play in period 9
        moves = nba_lineup.moves(self.lg, rb.NOW)                           # ATL plays: the Riser fills Boston Big's idle slot
        self.assertEqual([(m["start"], m["why"]) for m in moves], [("Atlanta Riser", "no game today")])
        radar.agree(self.r, moves, self.lg.bench, rb.NOW)
        text = self.bench_text("Boston Guard")
        self.assertIn("Boston Guard (PG, BOS), on your bench, worth a start on his next game day (no game today): minutes", text)
        self.assertNotIn("start him", text)
        self.assertIn("Atlanta Riser (PG, ATL), on your bench, start him today (it's in Lineup moves): minutes",
                      self.bench_text("Atlanta Riser"))

    def test_a_lineup_move_backs_start_him(self):
        self.plays_today(3.0, 0.0)
        moves = nba_lineup.moves(self.lg, rb.NOW)
        self.assertEqual([(m["start"], m["sit"]) for m in moves], [("Boston Guard", "Boston Big")])
        radar.agree(self.r, moves, self.lg.bench, rb.NOW)
        self.assertIn("Boston Guard (PG, BOS), on your bench, start him today (it's in Lineup moves): minutes",
                      self.bench_text("Boston Guard"))

    def test_plays_today_without_an_edge_is_consider(self):
        self.plays_today(0.5, 0.0)                                          # +0.5: under nba_lineup.MIN_EDGE
        moves = nba_lineup.moves(self.lg, rb.NOW)
        self.assertEqual(moves, [])
        radar.agree(self.r, moves, self.lg.bench, rb.NOW)
        text = self.bench_text("Boston Guard")
        self.assertIn("on your bench, consider starting him (no lineup move today: his season value doesn't beat a "
                      "starter who plays today by 1+ value/g)", text)
        self.assertNotIn("start him", text)

    def test_questionable_today_is_if_he_plays(self):
        self.plays_today(3.0, 0.0)
        self.guard["status"] = "Q"
        radar.agree(self.r, nba_lineup.moves(self.lg, rb.NOW), self.lg.bench, rb.NOW)
        self.assertIn("consider starting him if he plays (Q today)", self.bench_text("Boston Guard"))

    def test_a_dropped_may_fade_riser_gets_no_start_verdict(self):
        """Draymond, Nov 10: "worth a start" on the radar while Waiver adds swapped him out. The swap's drop gets the swap."""
        self.plays_today(3.0, 0.0)
        self.lg.values = VALUES
        self.lg.radar = self.r
        swaps = nba_swaps.build(self.lg, rb.CATS)
        self.assertEqual([(x["drop"]["name"], x["add"]["name"]) for x in swaps["swaps"]], [("Boston Guard", "Free Streamer")])
        moves = nba_lineup.moves(self.lg, rb.NOW)
        self.assertIn("Boston Guard", [m["start"] for m in moves])           # agree() alone: the swap's drop wins (advice.build never lets a move's start be dropped)
        radar.agree(self.r, moves, self.lg.bench, rb.NOW, swaps)
        text = self.bench_text("Boston Guard")
        self.assertIn(f"Boston Guard (PG, BOS), on your bench: rise may fade (no teammate's injury behind it); Waiver adds "
                      f"swaps him for Free Streamer (+{swaps['swaps'][0]['gain']:.1f} this week): minutes", text)
        self.assertNotIn("start", text.split(": minutes")[0])

    def test_waiver_adds_never_drop_a_player_lineup_moves_starts(self):
        """One answer per player: Lineup moves "Start Boston Guard" and Waiver adds "Drop Boston Guard" can't both show."""
        self.plays_today(3.0, 0.0)
        self.lg.values = VALUES
        self.lg.radar = self.r
        moves = nba_lineup.moves(self.lg, rb.NOW)
        self.assertEqual([m["start"] for m in moves], ["Boston Guard"])
        self.assertEqual([x["drop"]["name"] for x in nba_swaps.build(self.lg, rb.CATS)["swaps"]], ["Boston Guard"])
        s = nba_swaps.build(self.lg, rb.CATS, [m["start_key"] for m in moves])
        self.assertNotIn("Boston Guard", [x["drop"]["name"] for x in s["swaps"]])
        self.lg.cats = rb.CATS
        lines = advice.adds(self.lg, [m["start_key"] for m in moves])
        self.assertFalse(any(a.startswith("Drop Boston Guard") for a in lines))
        radar.agree(self.r, moves, self.lg.bench, rb.NOW, self.lg.swaps)
        self.assertIn("on your bench, start him today (it's in Lineup moves)", self.bench_text("Boston Guard"))

    def test_advice_tab_never_says_start_him_without_a_move(self):
        """The whole tab: every radar "start him" names a player Lineup moves starts, for both bench risers."""
        tab = advice.build(self.lg, rb.NOW)
        starts = {m.split(" (")[0].removeprefix("Start ") for m in tab["moves"]}
        for i in tab["radar"]["rising"]:
            if "start him" in i["text"]:
                self.assertIn(i["name"], starts)
        self.assertTrue(all("on your bench, " in i["text"] for i in tab["radar"]["rising"] if i["where"] == "bench"))
        said = {i["name"]: i.get("verdict") for i in tab["radar"]["rising"] if i["where"] == "bench"}
        self.assertEqual(said, {"Atlanta Riser": "start him today (it's in Lineup moves)",
                                "Boston Guard": "worth a start on his next game day (no game today)"})
        self.assertIn("Atlanta Riser", starts)
        for a in tab["adds"]:                                               # no "Drop X" for a player told to start
            self.assertFalse(any(a.startswith(f"Drop {n} ") for n, v in said.items() if "start" in (v or "")))


if __name__ == "__main__":
    unittest.main()
