"""B6: NBA trade checker data and verdict (shq/nba_trade.py; docs/players/index.html mirrors trade() in JavaScript)."""
import unittest

from shq import nba_trade


def pl(pid, own, v, z, age=None, team="BOS"):
    return {"id": pid, "own": own, "v": v, "z": z, "age": age, "team": team}


def block(dynasty=False):
    b = {"cats": ["PTS", "AST", "REB"], "repl": -3.0, "players": [
        pl("1", "me", 4.0, [3.0, 0.5, 0.5], age=27),          # my star
        pl("2", "me", -1.0, [-0.5, 0.0, -0.5], age=31),       # my old bench guy
        pl("3", "me", -5.0, [-2.0, -2.0, -1.0], age=20),      # my prospect, below waiver level
        pl("4", "me", 1.0, [0.0, 1.0, 0.0], team="FA"),       # no NBA team: a dead spot
        pl("10", "Them", 5.0, [0.5, 4.0, 0.5], age=22),       # their young star, assists
        pl("11", "Them", -2.0, [0.0, -1.0, -1.0], age=25),
        pl("12", "Others", 2.0, [1.0, 0.0, 1.0], age=34),
        pl("20", None, -3.0, [0.0, 0.0, 0.0], age=24),        # free agent: not in any profile
    ]}
    return nba_trade.annotate(b, dynasty)


class Trade(unittest.TestCase):
    def test_value_above_waiver_level(self):
        b = block()
        by = {p["id"]: p for p in b["players"]}
        self.assertEqual((by["1"]["above"], by["2"]["above"], by["3"]["above"]), (7.0, 2.0, 0.0))
        self.assertEqual(by["4"]["above"], 0.0)                               # no NBA team counts 0
        self.assertNotIn("dyn", by["1"])                                      # not a dynasty league

    def test_age_curve_and_prospect_bonus(self):
        self.assertEqual([nba_trade.age_mult(a) for a in (19.5, 22.2, 26, 29.4, 31, 35)], [1.5, 1.3, 1.0, 0.9, 0.7, 0.4])
        self.assertEqual(nba_trade.age_mult(None), 1.0)
        by = {p["id"]: p for p in block(dynasty=True)["players"]}
        self.assertEqual(by["1"]["dyn"], 7.0)                                 # 27: as is
        self.assertEqual(by["2"]["dyn"], 1.4)                                 # 31: 2.0 x 0.7
        self.assertEqual(by["3"]["dyn"], 1.8)                                 # 20, below waiver level: prospect bonus 3 x 0.6
        self.assertEqual(by["10"]["dyn"], round(8.0 * 1.3 + 0.6, 2))         # 22: grows, plus a year of bonus

    def test_profiles_ranks_and_weights(self):
        t = block()["trade"]
        self.assertEqual(set(t["profiles"]), {"me", "Them", "Others"})
        self.assertEqual(t["profiles"]["me"], [0.5, -0.5, -1.0])
        self.assertEqual(t["ranks"], [2, 3, 3])                               # Others beat my 0.5 in PTS; last in AST, REB
        self.assertEqual(t["weights"], [0.75, 1.125, 1.125])                   # last third weighs 1.5, middle 1, averaged to 1

    def test_verdicts(self):
        b = block()
        r = nba_trade.trade(b, ["1"], ["10"])
        self.assertEqual(r["now"], 1.0)                                       # 8 above waiver level for 7
        self.assertEqual(r["cats"], [-2.5, 3.5, 0.0])
        self.assertGreater(r["fit"], r["now"])                                # gains in AST, my weakest
        self.assertEqual(r["verdict"], "accept")
        self.assertEqual(nba_trade.trade(b, ["2", "3"], ["11"])["verdict"], "decline")   # 2 above waiver level for 1
        self.assertEqual(nba_trade.trade(b, ["4"], ["11"])["now"], 1.0)                  # a dead spot is worth 0 in a trade
        # a dead spot for a waiver-level player: nothing changes
        self.assertEqual(nba_trade.trade(b, ["4"], ["20"])["now"], 0.0)

    def test_dynasty_verdict_uses_the_age_curve(self):
        b = block(dynasty=True)
        r = nba_trade.trade(b, ["3"], ["11"])
        self.assertEqual(r["now"], 1.0)                                       # 1 above waiver level for a prospect at 0
        self.assertEqual(r["dyn"], round(1.0 - 1.8, 2))                       # but the 20-year-old is worth more long term
        self.assertEqual(r["verdict"], "decline")


if __name__ == "__main__":
    unittest.main()
