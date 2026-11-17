"""Rule 14 (fantasy-rules.md, Nov 14): a handcuff (Braelon Allen behind Breece Hall) is dropped only when the add
clearly beats his injury insurance, and the step then shows the trade-off. Football pickup code: shq/waivers.py
(valued leagues) and shq/swap.fa_adds (the fallback without week-by-week projections)."""
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import swap, waivers

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
WEEKS = (11, 12, 13, 14)


def pl(name, pos, ppg, team, val=1000, status=None, wk=None, slot="BN"):
    return {"id": name, "key": name, "name": name, "positions": [pos], "ppg": ppg, "val": val, "proj": ppg,
            "bye": False, "status": status, "team": team, "slot": slot, "started": False, "empty": False,
            "wk": list(zip(WEEKS, wk or [ppg] * 4))}


def team(hall_status=None, allen_team="NYJ"):
    starters = [pl("QB1", "QB", 20, "BUF", slot="QB"), pl("Breece Hall", "RB", 16, "NYJ", 6000, hall_status, slot="RB"),
                pl("Josh Jacobs", "RB", 15, "GB", 6000, slot="RB"), pl("WR1", "WR", 14, "MIN", slot="WR"),
                pl("WR2", "WR", 12, "DET", slot="WR"), pl("TE1", "TE", 9, "KC", slot="TE"),
                pl("Woody Marks", "RB", 8.2, "HOU", 3000, slot="FLEX")]
    bench = [pl("Braelon Allen", "RB", 7, allen_team, 1000), pl("WR3", "WR", 7, "SEA", 3000)]
    return starters, bench


def drops(found):
    return [a["drop"]["name"] for a in found if a["drop"]]


class Handcuff(unittest.TestCase):
    def test_allen_is_hall_s_handcuff(self):
        starters, bench = team()
        roster = starters + bench
        self.assertEqual(swap.handcuff_of(bench[0], roster)["name"], "Breece Hall")
        self.assertIsNone(swap.handcuff_of(starters[1], roster))          # the starter isn't his own handcuff
        self.assertIsNone(swap.handcuff_of(starters[6], roster))          # Marks: no teammate on the roster

    def test_a_small_upgrade_never_drops_the_handcuff(self):
        # (a) an RB a bit better than Allen: a backup swap worth ~0.5 pts over 4 weeks vs ~2.5 of Hall insurance
        starters, bench = team()
        found = waivers.adds(starters, bench, [pl("Meh RB", "RB", 8.5, "CHI")], SLOTS)
        self.assertNotIn("Braelon Allen", drops(found))

    def test_a_big_upgrade_may_drop_him_and_says_the_trade_off(self):
        # (b) a 22/gm starter: +40ish over 4 weeks dwarfs the insurance
        starters, bench = team()
        found = waivers.adds(starters, bench, [pl("Stud RB", "RB", 22, "ATL")], SLOTS)
        self.assertEqual(drops(found)[0], "Braelon Allen")
        c = found[0]["cuff"]
        self.assertTrue(c["ok"])
        self.assertGreater(c["gain"], waivers.CUFF_MARGIN * c["ins"])
        text = waivers.line(found[0])
        for bit in ("Drops a handcuff: Braelon Allen ~14 pts/wk if Breece Hall sits",
                    "Breece Hall: 12%/wk risk, Claude's estimate of a typical RB's weekly chance to miss a game",
                    "without Braelon Allen, Woody Marks (RB) starts (8.2)",
                    "Stud RB adds +", "over the next 4 weeks", "pts of insurance from Braelon Allen",
                    "worth it because Stud RB gains about ", "times what Braelon Allen is worth as insurance"):
            self.assertIn(bit, text)

    def test_an_add_that_only_helps_late_keeps_him(self):
        # Nov 16 (Cousins for Allen): nothing gained in the first 3 weeks, so Allen stays even for a big late gain
        starters, bench = team()
        late = pl("Late RB", "RB", 22, "ATL", wk=[0, 0, 0, 40])
        self.assertNotIn("Braelon Allen", drops(waivers.adds(starters, bench, [late], SLOTS)))
        self.assertEqual((waivers.CUFF_MARGIN, waivers.CUFF_MIN_GAP, waivers.CUFF_SOON), (2.5, 8.0, 3))

    def test_never_dropped_while_his_starter_is_tagged(self):
        # (c) Hall Questionable (or worse): Allen stays whatever the add is worth
        for tag in ("Q", "D", "OUT", "IR"):
            starters, bench = team(hall_status=tag)
            found = waivers.adds(starters, bench, [pl("Stud RB", "RB", 22, "ATL")], SLOTS)
            self.assertNotIn("Braelon Allen", drops(found), tag)

    def test_a_non_handcuff_rb_is_unaffected(self):
        # (d) the same small upgrade, Allen on another team: the old depth swap goes ahead, no trade-off text
        starters, bench = team(allen_team="MIA")
        found = waivers.adds(starters, bench, [pl("Meh RB", "RB", 8.5, "CHI")], SLOTS)
        self.assertEqual(drops(found), ["Braelon Allen"])
        self.assertIsNone(found[0]["cuff"])
        self.assertNotIn("handcuff", waivers.line(found[0]))

    def test_guillotine_needs_the_win_this_week(self):
        # the add is on bye this week: wins the 4 weeks, loses this week's cut odds, so not in the guillotine
        later = pl("Stud RB", "RB", 22, "ATL", wk=[None, 22, 22, 22])
        starters, bench = team()
        self.assertEqual(drops(waivers.adds(starters, bench, [later], SLOTS))[:1], ["Braelon Allen"])
        starters, bench = team()
        found = waivers.adds(starters, bench, [later], SLOTS, guillotine=True)
        self.assertNotIn("Braelon Allen", drops(found))
        starters, bench = team()
        found = waivers.adds(starters, bench, [pl("Stud RB", "RB", 22, "ATL")], SLOTS, guillotine=True)
        self.assertIn("which counts most for surviving the cut", waivers.line(found[0]))

    def test_history_beats_the_share_estimate(self):
        starters, bench = team()
        hall, allen = starters[1], bench[0]
        hall["hist"] = {"1": 18, "2": 20, "5": 15}
        allen["hist"] = {"1": 3, "2": 4, "3": 19, "4": 17, "5": 2}       # weeks 3-4: Hall sat
        self.assertEqual(waivers._as_starter(allen, hall, 11), (18.0, True))
        hall["hist"] = {"1": 18, "2": 20, "3": 15, "5": 15}                # only one such week: the 85% estimate
        self.assertEqual(waivers._as_starter(allen, hall, 11), (waivers.CUFF_SHARE * 16, False))

    def test_fallback_list_never_names_a_handcuff(self):
        starters, bench = team()
        roster = starters + bench
        found = swap.fa_adds(roster, [pl("Meh RB", "RB", 8.5, "CHI")])
        self.assertEqual(found[0][2]["name"], "Woody Marks")                 # the weakest RB that isn't a handcuff
        starters[1]["status"] = "OUT"                                        # Hall can't be named; Allen is all that's left
        found = swap.fa_adds([starters[1], bench[0]], [pl("Meh RB", "RB", 8.5, "CHI")])
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
