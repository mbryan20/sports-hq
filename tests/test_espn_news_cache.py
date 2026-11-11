"""shq.espn.player_news: one ESPN request per player per hour, however often the run loop asks."""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from shq import espn  # noqa: E402


class NewsCache(unittest.TestCase):
    def test_second_call_within_an_hour_uses_cache(self):
        feed = {"feed": [{"type": "Rotowire", "headline": "Kincaid (hip) is questionable for Sunday",
                          "published": "2026-10-30T15:00:00Z"}]}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(espn, "NEWS_FILE", pathlib.Path(d) / "news.json"), \
                mock.patch.object(espn, "get_json", return_value=feed) as gj:
            a = espn.player_news("123", name="Dalton Kincaid")
            b = espn.player_news("123", name="Dalton Kincaid")
            espn.player_news("456")
        self.assertEqual(a, b)
        self.assertEqual(a["note"], feed["feed"][0]["headline"])
        self.assertEqual(gj.call_count, 2)          # 123 once, 456 once

    def test_empty_feed_is_cached_as_none(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(espn, "NEWS_FILE", pathlib.Path(d) / "news.json"), \
                mock.patch.object(espn, "get_json", return_value={"feed": []}) as gj:
            self.assertIsNone(espn.player_news("9"))
            self.assertIsNone(espn.player_news("9"))
        self.assertEqual(gj.call_count, 1)


ROUNDUP = {"type": "Story", "headline": "Fantasy buzz: Malik Willis placed on IR, are there any Dolphins you should start?",
           "published": "2026-11-10T21:54:11Z",
           "story": "<p>Buzz file.</p>" + "<p>Garrett Wilson, Rhamondre Stevenson and more.</p>" * 400}
PICKUPS = {"type": "Story", "headline": "Gibbs, Allen, JSN and more Knockout league pickups for Week 10",
           "published": "2026-11-10T21:31:22Z", "story": "<p>Allen ...</p>" * 400}
note = lambda text, at: {"type": "Rotowire", "headline": text, "published": at, "story": f"<p>{text}</p>"}


class OwnNews(unittest.TestCase):
    """Nov 10: "Fantasy buzz: Malik Willis placed on IR ..." (a roundup) was cited for Rhamondre Stevenson and Garrett
    Wilson. The feed is read 5 deep and the first item about the player himself wins."""
    def test_roundup_first_in_the_feed_is_skipped_for_the_players_own_note(self):
        feed = [ROUNDUP, note("The knee injury that Stevenson sustained ... the next few weeks.", "2026-11-10T15:46:24Z"),
                note("Stevenson is dealing with a knee tendon issue.", "2026-11-10T02:32:46Z")]
        self.assertEqual(espn.pick_news(feed, "Rhamondre Stevenson")["note"],
                         "The knee injury that Stevenson sustained ... the next few weeks.")
        wilson = espn.pick_news([ROUNDUP, PICKUPS, note("Wilson (concussion) is out for Sunday's game.", "2026-11-06T16:16:24Z")],
                                "Garrett Wilson")
        self.assertEqual(wilson["note"], "Wilson (concussion) is out for Sunday's game.")

    def test_nothing_about_him_means_no_citation(self):
        self.assertIsNone(espn.pick_news([ROUNDUP, PICKUPS], "Garrett Wilson"))
        self.assertIsNone(espn.pick_news([ROUNDUP, note("Achane (ankle) practiced.", "2026-11-10T15:00:00Z")],
                                         "Rhamondre Stevenson"))

    def test_headline_naming_him_counts_and_a_roundup_headline_never_beats_his_note(self):
        story = {"type": "HeadlineNews", "headline": "Patriots' Stevenson to miss weeks with knee injury", "story": "x"}
        self.assertEqual(espn.pick_news([ROUNDUP, story], "Rhamondre Stevenson Jr.")["note"], story["headline"])
        keenan = note("Allen caught four passes Sunday.", "2026-11-09T22:00:00Z")
        self.assertEqual(espn.pick_news([PICKUPS, keenan], "Keenan Allen")["note"], keenan["headline"])

    def test_player_news_asks_for_five_items_and_filters(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(espn, "NEWS_FILE", pathlib.Path(d) / "news.json"), \
                mock.patch.object(espn, "get_json", return_value={"feed": [ROUNDUP]}) as gj:
            self.assertIsNone(espn.player_news("4569618", name="Garrett Wilson"))
        self.assertEqual(gj.call_args[0][1]["limit"], 5)


if __name__ == "__main__":
    unittest.main()
