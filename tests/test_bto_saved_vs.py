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


if __name__ == "__main__":
    unittest.main()
