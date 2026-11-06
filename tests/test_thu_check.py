"""R2: Thursday 4pm BTO check (picks/pp/thu_check.py): only in weeks with a Thursday BTO game, only when the saved bets
differ from the published card, one "yours → card" line per game (Thursday's first) and the lock time."""
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import thu_check  # noqa: E402

CT = ZoneInfo("America/Chicago")
THU_4PM = datetime(2026, 11, 5, 16, 0, tzinfo=CT)
SLATE = {"bto": {"games": [
    {"league": "NFL", "away": "JAX", "home": "BAL", "kick": "Thu 11/5 7:15 PM CT", "locked": False},
    {"league": "CFB", "away": "Miami", "home": "Notre Dame", "kick": "Sat 11/7 6:30 PM CT", "locked": False},
    {"league": "NFL", "away": "GB", "home": "NE", "kick": "Sun 11/8 12:00 PM CT", "locked": False}]}}
CARD = {"JAX@BAL": {"pick": "BAL +5.5", "wager": "$600", "stage": "final"},
        "Miami@Notre Dame": {"pick": "Notre Dame -2.5 (LP 3)", "wager": "$1,660", "stage": "final"}}
SAME = {"read": "x", "bets": [{"key": "JAX@BAL", "pick": "BAL +5.5", "wager": 600},
                              {"key": "Miami@Notre Dame", "pick": "Notre Dame -2.5 (LP 3)", "wager": 1660}]}


class ThuCheck(unittest.TestCase):
    def test_only_weeks_with_a_thursday_game_still_to_play(self):
        self.assertEqual([k for _, k in thu_check.thursday_games(SLATE, THU_4PM)], ["JAX@BAL"])
        self.assertEqual(thu_check.thursday_games(SLATE, THU_4PM.replace(hour=20)), [])          # already kicked off
        no_thu = {"bto": {"games": SLATE["bto"]["games"][1:]}}
        self.assertEqual(thu_check.thursday_games(no_thu, THU_4PM), [])
        self.assertIsNone(thu_check.message(SAME, CARD, [], 10))

    def test_no_push_when_saved_bets_match(self):
        games = thu_check.thursday_games(SLATE, THU_4PM)
        self.assertIsNone(thu_check.message(SAME, CARD, games, 10))
        same_text = {"read": "x", "bets": [{**b, "wager": f"${b['wager']:,}"} for b in SAME["bets"]]}
        self.assertIsNone(thu_check.message(same_text, CARD, games, 10))                       # "$1,660" == 1660

    def test_differences_list_yours_then_card_thursday_first_with_the_lock(self):
        games = thu_check.thursday_games(SLATE, THU_4PM)
        mine = {"read": "x", "bets": [{"key": "Miami@Notre Dame", "pick": "Miami +5.5", "wager": 600},
                                      {"key": "JAX@BAL", "pick": "JAX -5.5 (LP 4)", "wager": 600},
                                      {"key": "GB@NE", "pick": "NE -2.5", "wager": 830}]}
        title, body = thu_check.message(mine, CARD, games, 10)
        self.assertEqual(title, "BTO: saved bets differ from the card, JAX @ BAL locks Thu 7:15pm CT")
        lines = body.split("\n")
        self.assertEqual(lines[0], "JAX @ BAL: yours JAX -5.5 (LP 4) $600 → card BAL +5.5 $600")
        self.assertIn("Miami @ Notre Dame: yours Miami +5.5 $600 → card Notre Dame -2.5 (LP 3) $1,660", lines)
        self.assertIn("GB @ NE: yours NE -2.5 $830 → card no bet", lines)
        self.assertIn("Edit in BTO before Thu 7:15pm CT", lines[-1])

    def test_unreadable_saved_bets_still_warn_before_the_lock(self):
        title, body = thu_check.message({"unread": "signed out"}, CARD, thu_check.thursday_games(SLATE, THU_4PM), 10)
        self.assertIn("before Thu 7:15pm CT", title)
        self.assertIn("signed out", body)


if __name__ == "__main__":
    unittest.main()
