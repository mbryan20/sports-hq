"""Baseball helpers (shq/mlb_prospects.py, shq/mlb_backtest.py): pure logic, no network."""
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import mlb_backtest as bt
from shq import mlb_prospects as mp


class Helpers(unittest.TestCase):
    def test_outs_from_innings(self):
        self.assertEqual(mp.outs("123.1"), 370)
        self.assertEqual(mp.outs("0.2"), 2)
        self.assertEqual(mp.outs(None), 0)

    def test_sheet_name_key_matches_nicknames(self):
        self.assertEqual(mp.key("Leodalis De Vries"), mp.key("Leo De Vries"))
        self.assertEqual(mp.key("Jesús Made"), mp.key("Jesus Made"))
        self.assertEqual(mp.key("George Lombard Jr."), mp.key("George Lombard Jr"))

    def test_pipeline_term(self):
        self.assertEqual(mp.pipe_term(None), 0.0)
        self.assertEqual(mp.pipe_term(1), 1.0)
        self.assertAlmostEqual(mp.pipe_term(100), 0.3)

    def test_espn_lookup_needs_same_team(self):
        pool = {"cade smith": [{"espn_id": 1, "team": "CLE", "owned": 50, "owner": (3, "X")}]}
        self.assertIsNone(mp.lookup(pool, "Cade Smith", "NYY"))      # a different Cade Smith
        self.assertEqual(mp.lookup(pool, "Cade Smith", "CLE")["espn_id"], 1)
        pool = {"jesus made": [{"espn_id": 2, "team": "FA", "owned": 2, "owner": None}]}
        self.assertEqual(mp.lookup(pool, "Jesús Made", "MIL")["espn_id"], 2)

    def test_auc_and_top_hits(self):
        self.assertEqual(mp.auc([3, 2, 1], [True, False, False]), 1.0)
        self.assertEqual(mp.auc([1, 2, 3], [True, False, False]), 0.0)
        self.assertEqual(mp.top_hits([0.9, 0.1, 0.8], [True, True, False], 2), 1)

    def test_savant_name_normalized(self):
        self.assertEqual(bt.norm("Ward, Taylor"), "taylor ward")
        self.assertEqual(bt.norm("Acuña Jr., Ronald"), "ronald acuna")


if __name__ == "__main__":
    unittest.main()
