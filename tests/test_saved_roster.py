"""Saved-roster bridge: parsing what the laptop task scrapes, and running the watch on it."""
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import notify, run
from shq.leagues import SavedYahooLeague, name_key
from shq.save_roster import parse
from test_swap import NOW, Ctx

TEXT = """QB|Matthew Stafford|9265|LAR|QB|
RB|Starter RB|1|NYJ|RB|Out
RB|Other RB|2|DET|RB|
WR|A|3|DET|WR|
WR|B|4|DET|WR|
TE|C|5|DET|TE|
K|D|6|DET|K|
DEF|Chiefs|100012|KC|DEF|
BN|Bench RB|7|MIA|RB|
"""


class SavedRoster(unittest.TestCase):
    def test_parse_and_validate(self):
        players = parse(TEXT)
        self.assertEqual(len(players), 9)
        self.assertEqual(players[1]["status"], "Out")
        with self.assertRaises(ValueError):
            parse("BN|Somebody|7|MIA|RB|\n")  # no starters → page layout changed

    def test_name_key(self):
        self.assertEqual(name_key("Travis Etienne Jr."), "travis etienne")
        self.assertEqual(name_key("Amon-Ra St. Brown"), "amon ra st brown")

    def test_watch_suggests_swap_from_saved_roster(self):
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)
        lg = SavedYahooLeague(Ctx(), {"captured": "2026-10-25T13:00:00Z", "players": parse(TEXT)})
        self.assertEqual(run.injury_watch(lg, NOW), ["suggested Starter RB -> Bench RB"])
        self.assertIn("start Bench RB", notify.sent[-1]["message"])


if __name__ == "__main__":
    unittest.main()
