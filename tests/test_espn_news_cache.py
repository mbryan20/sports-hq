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
        feed = {"feed": [{"headline": "Kincaid (hip) is questionable for Sunday", "published": "2026-10-30T15:00:00Z"}]}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(espn, "NEWS_FILE", pathlib.Path(d) / "news.json"), \
                mock.patch.object(espn, "get_json", return_value=feed) as gj:
            a = espn.player_news("123")
            b = espn.player_news("123")
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


if __name__ == "__main__":
    unittest.main()
