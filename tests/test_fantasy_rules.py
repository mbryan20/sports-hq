"""Michael's fantasy rules in the NBA swaps (shq/nba_swaps.py; Drive: Claude Home/claude-audit/fantasy-rules.md).
Built from the three moves he rejected on Nov 12, with the real values from that day's docs/data/players.json."""
import datetime as dt
import types
import unittest

from shq import digest, nba_swaps


def pl(pid, name, v, mins, dmin, age, own=None, pct=10.0, g=(2, 4), z=None):
    return {"id": pid, "name": name, "team": "PHI", "pos": "F", "own": own, "v": v, "min": mins, "dmin": dmin, "age": age,
            "pct": pct, "g": list(g), "z": z or [v / 3] * 3, "out": False, "play": 1.0}


def league(players, roster_ids, dynasty=False, ir=None, open_spots=0):
    block = {"cats": ["PTS", "REB", "AST"], "players": players, "repl": -3.0}
    return types.SimpleNamespace(
        values=block, dynasty=dynasty, radar=None, ir_blocked=ir or [], open_spots=open_spots, name="Test",
        data={"roster": [{"id": i, "slot": 12} for i in roster_ids]})


# a strong core that is never a drop in any of these cases
CORE = [pl(f"c{i}", f"Core {i}", 4.0 + i, 32, 0, 25, own="me", pct=95) for i in range(3)]


class DynastyNeverStreams(unittest.TestCase):
    """3-Ball Dynasty, Nov 12: "drop Saddiq Bey (27, no game today), add Paul Reed, start him tonight"."""
    BEY = pl("bey", "Saddiq Bey", -2.44, 26.8, -0.7, 27.6, own="me", pct=32.4, g=(2, 4))
    # Reed's this-week line is far better (a big stream gain), but he is the same age and only 1.3/g better
    REED = pl("reed", "Paul Reed", -1.12, 26.0, -3.3, 27.4, pct=37.7, g=(4, 4), z=[3, 3, 3])

    def test_bey_for_reed_is_not_suggested(self):
        lg = league(CORE + [self.BEY, self.REED], [p["id"] for p in CORE] + ["bey"], dynasty=True)
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])

    def test_same_swap_was_a_stream_before(self):
        """The same pair in a redraft league with Bey his lowest player and no role would still not stream: Bey plays
        26.8 min/g, so he has a real role (rule 4)."""
        lg = league(CORE + [self.BEY, self.REED], [p["id"] for p in CORE] + ["bey"])
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])

    def test_a_clear_long_term_upgrade_is_still_suggested(self):
        young = pl("yng", "Young Starter", 1.0, 28.0, 3.0, 22.5, pct=20)
        lg = league(CORE + [self.BEY, self.REED, young], [p["id"] for p in CORE] + ["bey"], dynasty=True)
        s = nba_swaps.build(lg)
        self.assertEqual([(x["drop"]["name"], x["add"]["name"], x["kind"]) for x in s["swaps"]],
                         [("Saddiq Bey", "Young Starter", "upgrade")])
        self.assertEqual(s["lines"][0], "Drop Saddiq Bey (value -2.4/g, 27 min/g, 27), add Young Starter (F, PHI, value "
                                        "+1.0/g, 28 min/g, 22, 20% rostered): +3.4/g for the rest of the season, 5 years younger "
                                        "(helps PTS, REB, AST).")
        self.assertNotIn("this week", s["lines"][0])

    def test_an_older_add_never_passes_in_dynasty(self):
        vet = pl("vet", "Old Vet", 0.5, 30.0, 0, 33.0, pct=30)
        lg = league(CORE + [self.BEY, vet], [p["id"] for p in CORE] + ["bey"], dynasty=True)
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])


class NeverCutARotationPlayer(unittest.TestCase):
    """Ball is Life (We playin), Nov 12: "drop Obi Toppin for Jordan Goodwin"."""
    TOPPIN = pl("top", "Obi Toppin", -4.62, 21.2, 4.1, 28.7, own="me", pct=8.8, g=(2, 3))
    GOODWIN = pl("good", "Jordan Goodwin", -1.94, 18.0, -3.3, 28.1, pct=3.0, g=(4, 3), z=[3, 3, 3])

    def test_toppin_for_goodwin_is_not_suggested(self):
        lg = league(CORE + [self.TOPPIN, self.GOODWIN], [p["id"] for p in CORE] + ["top"])
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])

    def test_a_stream_costs_only_the_lowest_player_with_no_role(self):
        deep = pl("deep", "Deep Bench", -4.0, 9.0, 0, 30, own="me", pct=1, g=(1, 3))
        hot = pl("hot", "Hot Streamer", -4.5, 17.0, 0, 26, pct=5, g=(4, 3), z=[3, 3, 3])
        lg = league(CORE + [self.TOPPIN, deep, hot], [p["id"] for p in CORE] + ["top", "deep"])
        s = nba_swaps.build(lg)
        # Toppin is the lowest-value player but has a role, so he can't be streamed; Deep Bench isn't the lowest
        self.assertEqual(s["swaps"], [])
        lg = league(CORE + [deep, hot], [p["id"] for p in CORE] + ["deep"])
        s = nba_swaps.build(lg)
        self.assertEqual([(x["drop"]["name"], x["add"]["name"], x["kind"]) for x in s["swaps"]],
                         [("Deep Bench", "Hot Streamer", "stream")])
        self.assertIn("Deep Bench is your lowest-value player and has no real role (9 min/g)", s["lines"][0])

    def test_dynasty_never_streams(self):
        deep = pl("deep", "Deep Bench", -4.0, 9.0, 0, 30, own="me", pct=1, g=(1, 3))
        hot = pl("hot", "Hot Streamer", -4.5, 17.0, 0, 26, pct=5, g=(4, 3), z=[3, 3, 3])
        lg = league(CORE + [deep, hot], [p["id"] for p in CORE] + ["deep"], dynasty=True)
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])

    def test_a_rising_player_is_kept_unless_the_add_rises_too(self):
        """Live Nov 12: Peyton Watson (28 min/g, up 4.7) for Matisse Thybulle (+1.6/g, flat) and Toppin (up 4.1) for
        Ziaire Williams (+2.9/g, up 5.8)."""
        watson = pl("wat", "Peyton Watson", -3.51, 27.8, 4.7, 24.2, own="me", pct=20)
        thybulle = pl("thy", "Matisse Thybulle", -1.0, 24.3, 0.5, 29.7, pct=4)
        ziaire = pl("zia", "Ziaire Williams", -1.71, 24.1, 5.8, 25.2, pct=6)
        lg = league(CORE + [watson, thybulle], [p["id"] for p in CORE] + ["wat"])
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])
        lg = league(CORE + [self.TOPPIN, ziaire], [p["id"] for p in CORE] + ["top"])
        self.assertEqual([(x["drop"]["name"], x["add"]["name"], x["kind"]) for x in nba_swaps.build(lg)["swaps"]],
                         [("Obi Toppin", "Ziaire Williams", "upgrade")])

    def test_dynasty_never_adds_a_shrinking_role(self):
        """Live Nov 12: Donte DiVincenzo (29) for Paul Reed (27, +2.1/g) passed age and value, but Reed's minutes are
        down 3.3."""
        dv = pl("dv", "Donte DiVincenzo", -3.25, 24.1, None, 29.8, own="me", pct=30)
        reed = DynastyNeverStreams.REED
        lg = league(CORE + [dv, reed], [p["id"] for p in CORE] + ["dv"], dynasty=True)
        self.assertEqual(nba_swaps.build(lg)["swaps"], [])


class IrMoveEarnsItsPlace(unittest.TestCase):
    """We playin, Nov 12: "move Ajay Mitchell out of IR" on a day he has no game, which forced a drop."""
    DEEP = pl("deep", "Deep Bench", -4.0, 9.0, 0, 30, own="me", pct=1, g=(1, 3))
    SPARE = pl("spare", "Spare Big", -3.5, 10.0, 0, 31, own="me", pct=2, g=(2, 3))
    FA = pl("fa", "Good Add", 0.0, 30.0, 2.0, 24, pct=20)

    def build(self, bye, open_spots=0):
        ajay = {"name": "Ajay Mitchell", "bye": bye, "status": None, "news": None}
        lg = league(CORE + [self.DEEP, self.SPARE, self.FA], [p["id"] for p in CORE] + ["deep", "spare"], ir=[ajay],
                    open_spots=open_spots)
        return lg, nba_swaps.build(lg)

    def test_no_game_today_means_he_stays_and_no_pickups(self):
        _, s = self.build(bye=True)
        self.assertEqual((s["swaps"], s["room"]), ([], []))
        self.assertEqual(s["lines"], ["Leave Ajay Mitchell in IR for now: moving him out takes a drop with your roster "
                                      "full, and he has no game today. ESPN blocks adds and drops until he moves, so no "
                                      "pickups today; move him on a day he plays."])

    def test_fix_now_does_not_tell_him_to_move_him(self):
        lg, _ = self.build(bye=True)
        lg.sport, lg.starters, lg.bench = "nba", [], []
        items = digest.league_items(lg, dt.datetime(2026, 11, 12, 12, tzinfo=dt.timezone.utc))
        ir = [i for i in items if "Ajay Mitchell" in i["text"]]
        self.assertEqual(len(ir), 1)
        self.assertFalse(ir[0]["urgent"])
        self.assertTrue(ir[0]["text"].startswith("Leave Ajay Mitchell in IR today: he has no game"))

    def test_on_a_game_day_the_move_pairs_with_a_good_add(self):
        _, s = self.build(bye=False)
        self.assertIsNone(s["hold"])
        self.assertEqual([p["name"] for p in s["room"]], ["Spare Big"])      # the weakest player left, no real role
        self.assertTrue(s["lines"][0].startswith("First move Ajay Mitchell out of IR (Fix now)"))
        self.assertIn("then drop Deep Bench (", s["lines"][0])

    def test_an_open_spot_needs_no_drop_any_day(self):
        _, s = self.build(bye=True, open_spots=1)
        self.assertIsNone(s["hold"])
        self.assertEqual(s["room"], [])


class OneDropPerAdd(unittest.TestCase):
    def test_every_add_line_names_exactly_one_drop(self):
        young = pl("yng", "Young Starter", 1.0, 28.0, 3.0, 22.5, pct=20)
        bey = DynastyNeverStreams.BEY
        lg = league(CORE + [bey, young], [p["id"] for p in CORE] + ["bey"], dynasty=True)
        for text in nba_swaps.build(lg)["lines"]:
            self.assertEqual(text.count("Drop "), 1)
            self.assertNotIn(" or ", text)


if __name__ == "__main__":
    unittest.main()
