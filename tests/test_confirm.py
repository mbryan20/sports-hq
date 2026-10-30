"""A status that would bench someone needs ESPN's dated injury-report note behind it (the Jeremiyah Love case:
Sleeper still said Out from last week while ESPN had him Questionable and expected to play)."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import digest
from shq.status import confirm

UTC = dt.timezone.utc
TUE = dt.datetime(2026, 10, 27, 5, 0, tzinfo=UTC)            # Tue 12am CDT
FRI = dt.datetime(2026, 10, 30, 17, 46, tzinfo=UTC)
LAST_SUN = dt.datetime(2026, 10, 25, 16, 0, tzinfo=UTC)
URL = "https://www.espn.com/nfl/player/_/id/4870808/jeremiyah-love"


def entry(status, date, note="Coach said Friday that Love (ankle) is expected to play Sunday."):
    return {"status": status, "name": "Jeremiyah Love", "team": "ARI", "date": date, "note": note, "url": URL}


class Confirm(unittest.TestCase):
    def test_espn_disagrees(self):
        status, why, news, conflict = confirm("OUT", "Sleeper: Out", entry("Questionable", FRI), TUE)
        self.assertEqual(status, "Q")
        self.assertTrue(conflict)
        self.assertIn("ESPN says Questionable", why)
        self.assertEqual(news["url"], URL)

    def test_last_weeks_out_is_not_this_weeks(self):
        status, why, _, conflict = confirm("OUT", "Sleeper: Out", entry("Out", LAST_SUN), TUE)
        self.assertEqual((status, conflict), ("Q", True))
        self.assertIn("from last week", why)

    def test_not_on_report(self):
        self.assertEqual(confirm("OUT", "Yahoo: O", None, TUE)[0], "Q")

    def test_confirmed_out_and_ir(self):
        self.assertEqual(confirm("OUT", "Sleeper: Out", entry("Out", FRI), TUE)[:2], ("OUT", "Sleeper: Out"))
        # IR lasts for weeks, so an old note still counts
        self.assertFalse(confirm("IR", "Sleeper: IR", entry("Injured Reserve", LAST_SUN), TUE)[3])

    def test_digest_cites_and_never_benches_on_a_conflict(self):
        status, why, news, conflict = confirm("OUT", "Sleeper: Out", entry("Questionable", FRI), TUE)
        sun = dt.datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
        love = {"id": "1", "name": "Jeremiyah Love", "slot": "RB", "positions": ["RB"], "status": status, "why": why,
                "news": news, "conflict": conflict, "kickoff": sun, "started": False, "bye": False, "proj": 9.5}
        spare = {**love, "id": "2", "name": "Spare RB", "status": None, "why": "", "news": None, "conflict": False, "proj": 5.8}

        class League:
            name, sport, free_agents, starters, bench = "Domo", "nfl", [], [love], [spare]
        items = digest.league_items(League, FRI)
        self.assertFalse(any(i["urgent"] for i in items))
        self.assertIn("Check before benching [ESPN, Fri 12:46p: Coach said Friday", items[0]["text"])


if __name__ == "__main__":
    unittest.main()
