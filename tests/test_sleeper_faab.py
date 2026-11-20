"""Bids and FAAB only in Sleeper leagues that really bid (Nov 20, Michael: "There's no FAAB in that league")."""
import unittest

from shq.leagues import sleeper_faab
from shq.waivers import bid


class SleeperFaab(unittest.TestCase):
    def test_rolling_waivers_with_leftover_budget_have_no_bids(self):
        # Sunday's Best (Domo Arigato), read from Sleeper Nov 20: waiver_type 0, waiver_budget 100
        self.assertEqual(sleeper_faab({"waiver_type": 0, "waiver_budget": 100}, {"waiver_budget_used": 0}), (0, None))
        self.assertEqual(sleeper_faab({"waiver_type": 1, "waiver_budget": 100}, {}), (0, None))

    def test_faab_league_keeps_budget_and_money_left(self):
        # Guillotine, read Nov 20: waiver_type 2, waiver_budget 200
        self.assertEqual(sleeper_faab({"waiver_type": 2, "waiver_budget": 200}, {"waiver_budget_used": 45}), (200, 155))

    def test_missing_type_or_budget(self):
        self.assertEqual(sleeper_faab({"waiver_budget": 200}, {"waiver_budget_used": 10}), (200, 190))
        self.assertEqual(sleeper_faab({"waiver_type": 2}, {}), (0, None))
        self.assertEqual(sleeper_faab(None, None), (0, None))

    def test_no_budget_means_no_bid_text(self):
        # advice passes faab=None and budget=0 for a no-bid league, and waivers only bids when both are set
        budget, left = sleeper_faab({"waiver_type": 0, "waiver_budget": 100}, {})
        self.assertFalse(left is not None and budget)
        self.assertTrue(bid(3.0, 200, 155))


if __name__ == "__main__":
    unittest.main()
