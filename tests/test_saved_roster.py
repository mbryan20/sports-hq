"""Saved-roster bridge: parsing what the laptop task scrapes, and running the watch on it."""
import datetime as dt
import os
import unittest

os.environ["DRY_RUN"] = "1"

from shq import advice, notify, run
from shq.common import iso
from shq.leagues import SavedYahooLeague, name_key
from shq.save_roster import parse, parse_free_agents
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

# what the FA snippets return: the top available players per position (filler pads out validation)
FILLER = "".join(f"FA|Filler {pos} {i}|{50 + 10 * n + i}|DET|{pos}|\n"
                 for n, pos in enumerate(("QB", "TE", "K", "DEF")) for i in range(5))
FAS = """FA|Waiver RB|101|MIA|RB|
FA|Hurt RB|102|MIA|RB|IR-Return
FA|Waiver WR|900|MIA|WR|Questionable
""" + FILLER


def saved(text, fa_age=dt.timedelta(hours=2)):
    data = {"captured": "2026-10-25T13:00:00Z", "players": parse(text)}
    fas = parse_free_agents(text)
    if fas:
        data.update(free_agents=fas, fa_captured=iso(NOW - fa_age))
    return data


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

    def test_parse_free_agents(self):
        self.assertIsNone(parse_free_agents(TEXT))              # FA read skipped: keep the old list
        fas = parse_free_agents(TEXT + FAS)
        self.assertEqual(len(fas), 23)
        self.assertEqual(len(parse(TEXT + FAS)), 9)              # roster ignores FA lines
        self.assertEqual(fas[1]["status"], "IR-Return")
        with self.assertRaises(ValueError):
            parse_free_agents(TEXT + "FA|Lonely RB|101|MIA|RB|\n")  # too few: page layout changed
        with self.assertRaises(ValueError):
            parse_free_agents(TEXT + FAS + "FA|Flex Guy|77|MIA|W/R/T|\n")

    def test_free_agents_mapped_and_ranked(self):
        lg = SavedYahooLeague(Ctx(), saved(TEXT + FAS))
        self.assertEqual([(p["name"], p["id"], p["positions"]) for p in lg.free_agents[:2]],
                         [("Waiver RB", "s1", ["RB"]), ("Waiver WR", "s9", ["WR"])])   # by projection
        self.assertEqual(next(p for p in lg.free_agents if p["name"] == "Hurt RB")["status"], "IR")
        self.assertEqual(lg.best_fa(["RB"], NOW)["name"], "Waiver RB")    # skips the IR one
        stale = SavedYahooLeague(Ctx(), saved(TEXT + FAS, fa_age=dt.timedelta(days=3)))
        self.assertEqual(stale.free_agents, [])

    def test_watch_pushes_best_fa_when_bench_is_empty(self):
        notify.sent.clear()
        run.push_once = lambda key, title, msg, **kw: notify.push(title, msg)
        text = TEXT.replace("BN|Bench RB|7|MIA|RB|", "BN|Bench TE|7|MIA|TE|") + FAS
        lg = SavedYahooLeague(Ctx(), saved(text))
        self.assertEqual(run.injury_watch(lg, NOW), ["no bench for Starter RB"])
        self.assertIn("Best FA: Waiver RB", notify.sent[-1]["message"])

    def test_adds_on_tab_and_weekly(self):
        lg = SavedYahooLeague(Ctx(), saved(TEXT + FAS))
        adds = advice.build(lg, NOW)["adds"]
        self.assertEqual(adds, ["Waiver RB (RB, MIA, 11.0 proj) for Other RB (0.0)",
                                "Waiver WR (WR, MIA, 9.5 proj) for A (0.0)"])
        self.assertTrue(run.weekly_section(lg)["adds"][0].startswith("Add Waiver RB"))


if __name__ == "__main__":
    unittest.main()
