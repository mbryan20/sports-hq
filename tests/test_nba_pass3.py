"""Pass-3 review of the NBA league tabs (Tue Nov 10, ~6:20pm). Regressions, fixtures only (no network, no pushes):
1. Ball is Life: Austin Reaves, healthy, sat in an IR slot. The only mention was a collapsed note; "Fix now" said nothing
   to fix and Waiver adds suggested a drop ESPN blocks until he moves. Stempak (football) listed an add/drop fix before
   its IR line. Now the IR line is first and urgent everywhere, and the NBA add list starts with it.
2. 3-Ball BB: Isaiah Stewart, questionable for Wednesday, showed as a clean "+20.0 this week, 3 games".
3. Ball is Life: the radar protected Ryan Dunn (#230, -5.5/g, a starter whose rise the page never shows), so the
   swaps dropped John Collins and Draymond Green instead.
4. "Keep in the lineup" chase lines counted as lineup moves (KPI, layouts B and C, the NBA tile's MOVE chip).
5. Radar wording: the "may fade" reason said twice, "Waiver adds swaps him", "worth a start" for everyone on no-game
   days, "1 straight game of it so far", "+1.7 pts in 3 days" for % rostered.
6. "+20.0 this week" in Waiver adds vs "+11.6" in Streamers; Category adds naming a different player for the same need.
7. Dynasty ages rounded up (28.9 shown as 29).
8. Giannis "is Questionable" while ESPN's note said probable."""
import copy
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import unittest

os.environ["DRY_RUN"] = "1"

from shq import advice, digest, nba_swaps, radar, run, status
import test_digest as dg
import test_nba_one_answer as oa
import test_radar as rb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_AT = dt.datetime(2026, 11, 9, 23, 5, tzinfo=dt.timezone.utc)


def news(note):
    return {"note": note, "at": NEWS_AT, "url": "https://www.espn.com/nba/player/_/id/1"}


def values(**v):
    """test_nba_one_answer's values with some players' value per game changed."""
    out = copy.deepcopy(oa.VALUES)
    for p in out["players"]:
        p["v"] = v.get(p["name"].replace(" ", "_"), p["v"])
    return out


class IrFixFirst(oa.Base):
    """1. An IR slot ESPN won't allow blocks every add and drop: Fix now first, and the adds wait on it."""

    def test_nba_ir_is_urgent_and_first(self):
        lg = dg.League([dg.p("Playing C", "C", ["C"])], [], sport="nba")
        lg.ir_blocked = [{"name": "Austin Reaves", "status": None, "news": None}]
        items = digest.league_items(lg, dg.NOW)
        self.assertTrue(items[0]["urgent"])
        self.assertEqual(items[0]["text"], "Move Austin Reaves out of IR: ESPN lists him as active, so ESPN blocks adds and "
                                           "drops until he's on your bench; do this before any add or drop")
        self.assertEqual(digest.message(items)[0], "Today: 1 thing to fix")

    def test_football_ir_comes_before_an_add_drop_fix(self):
        """Stempak, Nov 10: the add/drop fix for an OUT starter was listed above "Move David Montgomery out of IR"."""
        lg = dg.League([dg.p("Hurt QB", "QB", ["QB"], status="OUT")], [dg.p("Spare QB", "BN", ["QB"], proj=8.0)])
        lg.ir_blocked = [{"name": "David Montgomery", "status": "Q", "news": None}]
        texts = [i["text"] for i in digest.league_items(lg, dg.NOW) if i["urgent"]]
        self.assertTrue(texts[0].startswith("Move David Montgomery out of IR: ESPN lists him Questionable"))
        self.assertTrue(texts[1].startswith("Hurt QB (QB) OUT → start Spare QB"))

    def swaps(self, open_spots):
        lg = oa.radar_league()
        lg.values = oa.VALUES
        lg.ir_blocked, lg.open_spots = [{"name": "Austin Reaves"}], open_spots
        return nba_swaps.build(lg, rb.CATS)

    def test_add_list_starts_with_the_ir_move_and_the_room_drop(self):
        s = self.swaps(0)
        self.assertEqual([(x["drop"]["name"], x["add"]["name"]) for x in s["swaps"]], [("Atlanta Riser", "Free Streamer")])
        self.assertEqual([p["name"] for p in s["room"]], ["Boston Guard"])     # the weakest bench player left
        first = s["lines"][0]
        self.assertTrue(first.startswith("First move Austin Reaves out of IR (Fix now): ESPN blocks every add and drop until "
                                         "he is on your bench; your roster is full, so that takes a drop too: Boston Guard "
                                         "(value -4.0/g); then drop Atlanta Riser ("), first)
        self.assertEqual(run.add_key(first), ("Free Streamer", "Atlanta Riser"))   # the weekly plan still reads it

    def test_radar_agrees_with_the_room_drop(self):
        """Draymond, live: the IR move's room drop must not also be "worth a start" on the radar."""
        lg = oa.radar_league()
        r = radar.block(lg, rb.CATS)
        s = self.swaps(0)
        radar.agree(r, [], lg.bench, rb.NOW, s, lg.starters)
        guard = next(i for i in r["rising"] if i["name"] == "Boston Guard")
        self.assertEqual(guard["verdict"], "rise may fade (no teammate's injury behind it); the add list below drops him to "
                                           "make room for Austin Reaves out of IR")
        self.assertEqual(guard["text"].count("may fade"), 1)

    def test_open_spot_needs_no_room_drop(self):
        s = self.swaps(1)
        self.assertEqual(s["room"], [])
        self.assertTrue(s["lines"][0].startswith("First move Austin Reaves out of IR (Fix now): ESPN blocks every add and drop "
                                                 "until he is on your bench; then drop Atlanta Riser ("))

    def test_fix_now_names_the_room_drop(self):
        s = self.swaps(0)
        items = [{"league": "BIL", "urgent": True, "text": "Move Austin Reaves out of IR: ESPN lists him as active, so ESPN "
                                                           "blocks adds and drops until he's on your bench; do this before any add or drop"},
                 {"league": "BIL", "urgent": False, "text": "5 of 9 starters play tonight"}]
        out = advice.ir_room(items, s)
        self.assertTrue(out[0]["text"].endswith("Your roster is full, so moving him takes a drop: Boston Guard (value -4.0/g), "
                                                "the weakest bench player Waiver adds doesn't already drop"))
        self.assertEqual(out[1], items[1])

    def test_league_tab_fix_now_and_adds(self):
        roster = oa.ROSTER + [{**rb.rp(300, "Austin Reaves", 2, 13), "injury": "DAY_TO_DAY"}]
        lg = oa.radar_league(roster)
        self.assertEqual([p["name"] for p in lg.ir_blocked], ["Austin Reaves"])
        saved = advice.player_values
        advice.player_values = lambda league: setattr(league, "values", oa.VALUES)   # values with a free agent worth adding
        try:
            tab = advice.build(lg, rb.NOW)
        finally:
            advice.player_values = saved
        self.assertTrue(tab["fixes"][0].startswith("Move Austin Reaves out of IR: ESPN lists him day-to-day, so ESPN blocks "
                                                   "adds and drops until he's on your bench; do this before any add or drop"))
        self.assertFalse(any("out of IR" in n for n in tab["notes"]))       # not tucked into the collapsed notes
        self.assertTrue(tab["adds"][0].startswith("First move Austin Reaves out of IR (Fix now): ESPN blocks every add and "
                                                  "drop until he is on your bench; then drop "), tab["adds"])


class QuestionableAdd(unittest.TestCase):
    """2. A day-to-day add shows his status, and his next game counts at his chance to play it."""

    def test_play_chance_from_espn_note(self):
        self.assertEqual(status.play_chance(None, None), 1.0)
        self.assertEqual(status.play_chance("Day-To-Day", "Stewart (ankle) is questionable for Wednesday's game."), 0.5)
        self.assertEqual(status.play_chance("Day-To-Day", "Antetokounmpo is probable for Tuesday's game."), 0.9)
        self.assertEqual(status.play_chance("Day-To-Day", "Doubtful for Friday."), 0.25)
        self.assertEqual(status.play_chance("Day-To-Day", "Rested Monday."), status.DTD_CHANCE)

    def stewart(self, **kw):
        return {"id": "9", "name": "Isaiah Stewart", "pos": "PF/C", "team": "MEM", "v": -3.0, "z": [1.0, 0.5], "g": [3, 4],
                "pct": 4.0, "inj": "Day-To-Day", "play": 0.5, "word": "questionable", **kw}

    def test_worth_counts_the_questionable_game_at_half(self):
        block = {"cats": ["BLK", "FG%"], "repl": -3.5}
        w = {"BLK": 1.0, "FG%": 1.0}
        healthy = nba_swaps.worth(self.stewart(inj=None, play=1.0), block, w, 0)
        hurt = nba_swaps.worth(self.stewart(), block, w, 0)
        self.assertAlmostEqual(hurt, healthy * 2.5 / 3)
        self.assertAlmostEqual(nba_swaps.worth(self.stewart(), block, w, 1), healthy * 4 / 3)   # next week: not discounted

    def test_add_line_names_his_status(self):
        drop = {"name": "De'Andre Hunter", "g": [3, 4], "v": -6.5, "age": 28.9}
        s = {"drop": drop, "add": self.stewart(), "gain": 15.1, "helps": ["FG%", "BLK"], "dead": False}
        text = nba_swaps.line(s, "this week", False)
        self.assertIn("add Isaiah Stewart (PF/C, MEM, 3 games this week, day-to-day (ESPN: questionable), next game counted "
                      "at 50%, value -3.0/g, 4% rostered)", text)

    def test_values_carry_the_chance(self):
        import test_nba_values as base
        from shq import nba_ages
        saved = radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates, dict(base.REPORT)
        radar.fetch_pool = lambda *a, **k: base.POOL
        radar.track_ownership = lambda pool, now: {}
        nba_ages.birth_dates = lambda: {}
        base.REPORT["6"] = {"status": "Day-To-Day", "name": "Bench Guy", "team": "ATL", "date": base.NOW,
                            "note": "Bench Guy (ankle) is questionable for Wednesday.", "url": "https://www.espn.com/nba/player/_/id/6"}
        try:
            lg = base.league()
            advice.player_values(lg)
            by = {p["name"]: p for p in lg.values["players"]}
            self.assertEqual((by["Bench Guy"]["play"], by["Bench Guy"]["word"]), (0.5, "questionable"))
            self.assertEqual((by["Volume Shooter"]["play"], by["Volume Shooter"]["word"]), (1.0, None))
        finally:
            radar.fetch_pool, radar.track_ownership, nba_ages.birth_dates, report = saved
            base.REPORT.clear()
            base.REPORT.update(report)


class RadarKeep(oa.Base):
    """3. Only bench risers the page shows are protected, and only while their value isn't well below the next drop."""

    def test_a_rising_starter_is_not_protected(self):
        roster = [oa.rb.rp(201, "Boston Big", 2, 12), oa.rb.rp(200, "Boston Guard", 2, 12), oa.rb.rp(101, "Atlanta Riser", 1, 0)]
        lg = oa.radar_league(roster)
        r = radar.block(lg, rb.CATS)
        self.assertEqual(r["keep"], [])                                     # Riser starts: his rise isn't shown
        self.assertNotIn("Atlanta Riser", [i["name"] for i in r["rising"]])

    def test_protection_follows_value(self):
        lg = oa.radar_league()
        lg.radar = radar.block(lg, rb.CATS)
        self.assertEqual(lg.radar["keep"], ["101"])
        lg.values = values()                                                # Riser -4.2 vs Boston Guard -4.0: kept
        self.assertEqual([x["drop"]["name"] for x in nba_swaps.build(lg, rb.CATS)["swaps"]], ["Boston Guard"])
        lg.values = values(Atlanta_Riser=-6.0)                              # 2.0/g below the next drop: Dunn's case
        s = nba_swaps.build(lg, rb.CATS)
        self.assertEqual([(x["drop"]["name"], x["unkept"]) for x in s["swaps"]], [("Atlanta Riser", True)])
        radar.agree(lg.radar, [], lg.bench, rb.NOW, s, lg.starters)
        text = next(i["text"] for i in lg.radar["rising"] if i["name"] == "Atlanta Riser")
        self.assertIn("Atlanta Riser (PG, ATL), on your bench: rising, but his value (-6.0/g) is well below the rest of your "
                      "roster; the add list below swaps him for Free Streamer (", text)
        self.assertNotIn("start", text.split(": minutes")[0])


class ChaseIsNotAMove(unittest.TestCase):
    """4. "Keep in the lineup" changes nothing: its own kind, after the adds on the tile, never counted as a move."""
    def setUp(self):
        with open(os.path.join(ROOT, "docs", "lib", "core.js"), encoding="utf-8") as f:
            self.SRC = f.read()

    def test_source(self):
        self.assertIn('L.chase.forEach(t => push("keep", t));', self.SRC)
        self.assertNotRegex(self.SRC, r'chase\[0\] \? \{ kind: "move"')
        self.assertIn('keep: "Keep"', self.SRC)
        top = re.search(r"const top = (.+?);\n", self.SRC, re.S).group(1)
        self.assertLess(top.index("adds[0]"), top.index("chase[0]"))
        with open(os.path.join(ROOT, "docs", "index.html"), encoding="utf-8") as f:
            index = f.read()
        self.assertIn('feed.filter(i => i.kind === "move").length', index)   # the KPI counts moves only

    def test_feed_and_tile_in_node(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        import test_core_js as cj
        data = {"lineups": {"leagues": {"3-Ball BB": {"sport": "nba", "platform": "espn", "starters": [], "bench": [], "advice": {
            "fixes": [], "moves": [], "adds": ["Drop A (3 games), add B (4 games): +5.0 this week over keeping A."],
            "cats": {"chase": ["FG% is close. Keep in the lineup: Walker Kessler (2 games, .690 on 9.2 FGA/g)."]}}}}}}
        expr = (f"(() => {{ const d = {json.dumps(data)}; return {{kinds: SHQ.feed(d).map(i => i.kind), "
                f"top: SHQ.leagues(d)[0].top.kind}}; }})()")
        out = subprocess.run([node, "-e", cj.LOAD, os.path.join(ROOT, "docs", "lib", "core.js"), expr],
                             check=True, capture_output=True, text=True, cwd=ROOT)
        got = json.loads(out.stdout)
        self.assertEqual(got, {"kinds": ["add", "keep"], "top": "add"})


class RadarWording(oa.Base):
    """5. One clear sentence per riser."""

    def test_rostered_change_reads_as_percent(self):
        hist = {f"2026-11-0{d}": {"7": 0.3} for d in range(6, 10)}
        hist["2026-11-09"]["7"] = 2.0
        self.assertEqual(radar.change_text("7", {"owned": 2.0, "change": 0.4}, hist), " (+1.7% in 3 days)")
        self.assertEqual(radar.change_text("7", {"owned": 0.0, "change": -0.1}, {}), " (-0.1% lately, ESPN's +/-)")

    def test_may_fade_reason_reads_plainly_and_once(self):
        lg = oa.radar_league()
        r = radar.block(lg, rb.CATS)
        guard = next(i for i in r["rising"] if i["name"] == "Boston Guard")
        self.assertNotIn("straight game of it so far", guard["text"])
        self.assertIn("no teammate's injury behind it and it hasn't lasted 4 straight games yet, so this may fade", guard["text"])
        lg.values = oa.VALUES
        lg.radar = r
        s = nba_swaps.build(lg, rb.CATS)
        radar.agree(r, [], lg.bench, rb.NOW, s, lg.starters)
        self.assertEqual(guard["text"].count("may fade"), 1)
        self.assertNotIn("Waiver adds swaps", guard["text"])
        self.assertIn("the add list below swaps him for Free Streamer", guard["text"])

    def test_no_game_day_verdict_follows_value(self):
        lg = oa.radar_league()
        r = radar.block(lg, rb.CATS)
        guard = next(b for b in lg.bench if b["key"] == 200)
        big = next(s for s in lg.starters if s["key"] == 201)
        big["cv"] = {"v": 0.0}
        guard["cv"] = {"v": -2.0}
        radar.agree(r, [], lg.bench, rb.NOW, None, lg.starters)
        said = next(i["verdict"] for i in r["rising"] if i["name"] == "Boston Guard")
        self.assertEqual(said, "keep him on the bench for now (no game today; his season value -2.0/g doesn't beat your "
                               "weakest starter, Boston Big, at +0.0/g, by 1+)")


class SameNumbers(unittest.TestCase):
    """6. A swap's gain names what it's over; Category adds don't repeat a need the swaps cover."""

    def test_gain_is_over_keeping_the_drop(self):
        s = {"drop": {"name": "De'Andre Hunter", "g": [3, 4], "v": -6.5}, "add": {"name": "Isaiah Stewart", "pos": "PF/C",
             "team": "MEM", "g": [3, 4], "v": -3.0, "pct": 4.0}, "gain": 20.0, "helps": ["FG%"], "dead": False}
        self.assertIn("): +20.0 this week over keeping De'Andre Hunter (helps FG%).", nba_swaps.line(s, "this week", False))

    def test_category_adds_skip_needs_the_swaps_cover(self):
        cats = {"adds": ["For BLK: Jerami Grant (PF, MEM), 3 games left, 1.0/g",
                         "For PTS: Ryan Rollins (PG/SG, MIL), 4 games left, 10.7/g"]}
        swaps = {"swaps": [{"helps": ["BLK", "FG%"]}]}
        self.assertEqual(advice.dedupe_cat_adds(cats, swaps)["adds"], ["For PTS: Ryan Rollins (PG/SG, MIL), 4 games left, 10.7/g"])
        self.assertEqual(advice.dedupe_cat_adds({"adds": ["For BLK: X"]}, None)["adds"], ["For BLK: X"])


class DynastyAge(unittest.TestCase):
    """7. Whole years: 28.9 is 28."""

    def test_age_is_whole_years(self):
        s = {"drop": {"name": "De'Andre Hunter", "g": [3, 4], "v": -6.5, "age": 28.9}, "add": {"name": "B", "pos": "C",
             "team": "MEM", "g": [3, 4], "v": -3.0, "pct": 4.0}, "gain": 5.0, "helps": [], "dead": False}
        self.assertTrue(nba_swaps.line(s, "this week", True).endswith("Dynasty: De'Andre Hunter is 28."))


class ProbableNotQuestionable(unittest.TestCase):
    """8. NBA day-to-day says what ESPN's note says."""

    def test_probable(self):
        tonight = dt.datetime(2026, 10, 30, 0, 30, tzinfo=dt.timezone.utc)
        giannis = {**dg.p("Giannis Antetokounmpo", "PF", ["PF"], status="Q", kickoff=tonight),
                   "news": news("Antetokounmpo is probable for Tuesday's game against the Jazz due to a right wrist sprain.")}
        items = digest.league_items(dg.League([giannis], [], sport="nba"), dg.NOW)
        self.assertTrue(items[0]["text"].startswith("Giannis Antetokounmpo (PF) is day-to-day (ESPN: probable), plays"))
        nfl = digest.league_items(dg.League([{**giannis, "news": None}], []), dg.NOW)
        self.assertTrue(any("is Questionable, plays" in i["text"] for i in nfl))


if __name__ == "__main__":
    unittest.main()
