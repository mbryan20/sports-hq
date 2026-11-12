import os, sys, unittest
from pathlib import Path

os.environ["DRY_RUN"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "picks"))
from pp import cards  # noqa: E402
from pp.sim import p_cover  # noqa: E402
import numpy as np  # noqa: E402

M = np.random.default_rng(0).normal(2.0, 13.5, 20000)   # simulated margins for the favored side


def cand(away, home, side_home, margin, line):
    return {"sg": {"away": away, "home": home}, "home": side_home, "margin": margin, "line": line}


CANDS = [cand("SF", "DAL", True, -M, 4.5), cand("SF", "DAL", False, M, -4.5),
         cand("MIN", "GB", True, M, -4.5), cand("MIN", "GB", False, -M, 4.5)]
ROWS = [{"key": "MIN@GB", "pick_team": "MIN", "pick": "MIN +8.5 (LP 4)", "model": 0.68}]


class SavedVsCard(unittest.TestCase):
    def test_compares_his_bet_at_his_line(self):
        vs = cards.saved_vs_card(CANDS, [{"key": "SF@DAL", "pick": "SF -0.5", "wager": 3070}], ROWS)
        self.assertEqual(vs, f"cover chance: yours SF -0.5 {p_cover(M, -0.5) * 100:.0f}% vs card MIN +8.5 (LP 4) 68%")

    def test_none_when_same_game_and_side(self):
        self.assertIsNone(cards.saved_vs_card(CANDS, [{"key": "MIN@GB", "pick": "MIN +7.5", "wager": 3070}], ROWS))

    def test_none_when_nothing_saved_or_unknown_game(self):
        self.assertIsNone(cards.saved_vs_card(CANDS, [], ROWS))
        self.assertIsNone(cards.saved_vs_card(CANDS, [{"key": "X@Y", "pick": "X -1", "wager": 1}], ROWS))


class CfpLegalPlans(unittest.TestCase):
    T = [{"bets": 2, "frac": 0.9, "rebuy": False, "p_first": 0.060, "p_top3": 0.2},
         {"bets": 2, "frac": 1.0, "rebuy": False, "p_first": 0.059, "p_top3": 0.2},
         {"bets": 2, "frac": 1.0, "rebuy": True, "p_first": 0.0585, "p_top3": 0.2},
         {"bets": 1, "frac": 0.75, "rebuy": False, "p_first": 0.050, "p_top3": 0.2}]

    def test_drops_bets_under_the_minimum(self):
        best, alt = cards.cfp_legal_plans(self.T, 23808, 11904)
        self.assertEqual((best["bets"], best["frac"]), (2, 1.0))       # 2 x 10,713 is illegal
        self.assertEqual((alt["bets"], alt["frac"]), (1, 0.75))       # not the rebuy twin of best

    def test_no_minimum_keeps_the_best(self):
        self.assertEqual(cards.cfp_legal_plans(self.T, 23808, 0)[0]["frac"], 0.9)


class CrossPoolNote(unittest.TestCase):
    def test_notes_when_yahoo_and_ats_pick_different_teams(self):
        cs = [{"id": "yahoo", "rows": [{"key": "Mississippi@Oklahoma", "pick_team": "Mississippi", "model": 0.52}]},
              {"id": "cfp", "title": "CFP 2026 points pool", "notes": [], "rows": [
                  {"key": "Ole Miss@Oklahoma", "game": "Ole Miss @ Oklahoma", "pick_team": "Oklahoma",
                   "pick": "Oklahoma +1.5", "model": 0.56, "why": "Pool +1.5 vs market -1.5; cover 56%"}]}]
        cards.cross_pool_notes(cs)
        self.assertEqual(cs[1]["notes"], ["Ole Miss @ Oklahoma: Yahoo has Mississippi to win (52%); CFP takes Oklahoma +1.5 "
                                          "(Pool +1.5 vs market -1.5; cover 56%). Different questions: who wins vs who covers."])

    def test_silent_when_same_team(self):
        cs = [{"id": "yahoo", "rows": [{"key": "A@B", "pick_team": "B", "model": 0.6}]},
              {"id": "cfp", "title": "CFP", "notes": [], "rows": [{"key": "A@B", "game": "A @ B", "pick_team": "B",
                                                                   "pick": "B -3", "model": 0.55, "why": "x"}]}]
        cards.cross_pool_notes(cs)
        self.assertEqual(cs[1]["notes"], [])


if __name__ == "__main__":
    unittest.main()
