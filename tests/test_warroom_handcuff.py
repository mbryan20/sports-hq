"""War Room handcuffs (fantasy rule 14, Nov 14): a backup RB behind his own starter (Braelon Allen behind Breece Hall)
carries injury insurance, so he is dropped only when the add clearly wins even after counting it, never while the starter
is hurt, and never when the move costs points this week (guillotine: survive first). Any drop of a handcuff shows the
side-by-side: what he scores if the starter sits, what the add brings week by week, who starts instead."""
import unittest

from tests.test_warroom_revamp import league, run_js


def roster_league(add_pw, starter_inj="", add_pos="WR"):
    """My team: QB, 2 RB starters, 3 WR, TE, K, DEF, 2 flex; Hall (NYJ, 11) with Allen (NYJ, 7.5) behind him, who scored 17
    in the two weeks Hall missed; Marks (HOU) a 5-point bench RB; one free agent 'add'."""
    players = {
        "qb": {"p": "QB", "t": "WAS", "pw": [20] * 4}, "rb1": {"t": "CAR", "pw": [15] * 4}, "rb2": {"t": "DAL", "pw": [14] * 4},
        "wr1": {"p": "WR", "t": "DET", "pw": [15] * 4}, "wr2": {"p": "WR", "t": "CIN", "pw": [14] * 4}, "wr3": {"p": "WR", "t": "LV", "pw": [9] * 4},
        "te": {"p": "TE", "t": "JAX", "pw": [8] * 4}, "k": {"p": "K", "t": "DET", "pw": [8] * 4}, "def": {"p": "DEF", "t": "GB", "pw": [7] * 4},
        "wr4": {"p": "WR", "t": "TEN", "pw": [10] * 4},
        "hall": {"n": "Breece Hall", "t": "NYJ", "pw": [11] * 4, "inj": starter_inj, "w": [18.8, 11.7, None, None, 10.2]},
        "allen": {"n": "Braelon Allen", "t": "NYJ", "pw": [7.5] * 4, "w": [4.0, 8.0, 18.1, 15.9, 4.4]},
        "marks": {"n": "Woody Marks", "t": "HOU", "pw": [5] * 4},
        "add": {"n": "Add Guy", "p": add_pos, "t": "MIN", "pw": add_pw},
    }
    D = league(players, roster=[s for s in players if s != "add"])
    for p in D["P"].values():
        p.setdefault("inj", ""); p.setdefault("st", "ACT")
    return D


class Handcuffs(unittest.TestCase):
    def test_allen_is_found_as_halls_handcuff(self):
        D = roster_league([1] * 4)
        got = run_js(D, "computeBase(); [handcuffPairs(roster(ME)), Math.round(asStarter('hall', 'allen', W0) * 10) / 10]")
        self.assertEqual(got[0], [["hall", "allen"]])
        self.assertEqual(got[1], 17.0)                    # his own average in the 2 weeks Hall missed

    def test_small_upgrade_never_drops_the_handcuff(self):
        # the add is a bench WR worth little: the model used to drop Allen (0 lineup points with Hall healthy)
        D = roster_league([10.5] * 4)
        got = run_js(D, "computeBase(); [bestDrop(ME, 'add'), handcuffCheck(ME, 'add', 'allen')]")
        self.assertNotEqual(got[0], "allen")
        hc = got[1]
        self.assertFalse(hc["ok"])
        self.assertEqual(hc["as_starter"], 17.0)
        self.assertEqual(hc["instead"]["name"], "Woody Marks")   # who starts if Hall sits and Allen is gone
        self.assertEqual(len(hc["weeks"]), 4)
        self.assertTrue(hc["verdict"].startswith("Keep Braelon Allen"))

    def test_big_upgrade_may_drop_him_with_the_trade_off_shown(self):
        D = roster_league([30] * 4)                       # a star WR who starts every week
        got = run_js(D, "computeBase(); const c = handcuffCheck(ME, 'add', 'allen'); [c.ok, c.verdict, c.add_total > 2 * c.insurance_total]")
        self.assertTrue(got[0])
        self.assertTrue(got[1].startswith("Drop Braelon Allen"))
        self.assertTrue(got[2])

    def test_never_while_the_starter_is_hurt(self):
        D = roster_league([30] * 4, starter_inj="Questionable")
        got = run_js(D, "computeBase(); [handcuffCheck(ME, 'add', 'allen').ok, bestDrop(ME, 'add')]")
        self.assertFalse(got[0])
        self.assertNotEqual(got[1], "allen")

    def test_try_a_move_shows_the_side_by_side_and_says_not(self):
        D = roster_league([10.5] * 4)
        got = run_js(D, "S.sims = 1000; const m = tryMove(['add'], ['allen']); [m.verdict, m.handcuffs.length, m.reasons.join(' ')]")
        self.assertEqual(got[0], "not")
        self.assertEqual(got[1], 1)
        self.assertIn("Handcuff (your rule 14)", got[2])
        self.assertIn("Without Braelon Allen: Woody Marks", got[2])
        self.assertIn("Week by week", got[2])

    def test_a_non_handcuff_bench_rb_is_unaffected(self):
        D = roster_league([10.5] * 4)
        got = run_js(D, "computeBase(); [isHandcuff(roster(ME), 'marks'), handcuffCheck(ME, 'add', 'marks')]")
        self.assertEqual(got, [False, None])

    def test_insurance_counts_in_the_team_total(self):
        # with Allen the expected week is better than without him (Hall may sit), by about miss chance x (17 - 5)
        D = roster_league([1] * 4)
        got = run_js(D, "computeBase(); const r = roster(ME); [weekTot(r, W0) - weekTot(r.filter(x => x !== 'allen'), W0), insurance(r, 'allen', W0)]")
        self.assertAlmostEqual(got[0], got[1], places=6)
        # 12% x (17 - 5) = 1.44 for Hall, plus 2 x 12% x (7.5 - 5) = 0.6 as the first fill-in for the other two RBs
        self.assertAlmostEqual(got[1], 2.04, places=2)


if __name__ == "__main__":
    unittest.main()
