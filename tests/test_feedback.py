"""Site feedback issues become one FEEDBACK.md line each, in the Inbox section."""
import unittest

from shq import feedback

BODY = ("Love the tiles,\nbut the bar is too thin\n\n---\nMood: 👍 Like\nLayout: A · Scoreboard\nSpot: Domo Arigato tile\n"
        "Screen: 375px, dark\nPage: https://mbryan20.github.io/sports-hq/lab/a/\n")
URL = "https://github.com/mbryan20/sports-hq/issues/7"
DOC = "# Feedback\n\nintro\n\n## Inbox\n\n## Handled\n\n- old one\n"


class Feedback(unittest.TestCase):
    def test_entry_from_site_issue(self):
        line = feedback.entry("7", URL, "2026-11-01T03:30:00Z", "Feedback: 👍 Like · A", BODY)
        # 03:30 UTC Nov 1 is still Oct 31 in Chicago
        self.assertEqual(line, '- 2026-10-31 👍 Like · A · Scoreboard · Domo Arigato tile · 375px, dark: '
                               f'"Love the tiles, but the bar is too thin" ([#7]({URL}))')

    def test_no_comment_and_hand_typed(self):
        body = "(no comment)\n\n---\nMood: 👎 Dislike\nLayout: B · Command center\nSpot: Inbox\n"
        self.assertEqual(feedback.entry("8", URL, "2026-10-31T15:00:00Z", "x", body),
                         f"- 2026-10-31 👎 Dislike · B · Command center · Inbox ([#8]({URL}))")
        # typed straight into GitHub: no metadata block
        self.assertIn('Feedback: "Make the scores bigger"', feedback.entry("9", URL, "2026-10-31T15:00:00Z", "Make it pop", "Make the scores bigger"))
        self.assertIn('Feedback: "Make it pop"', feedback.entry("9", URL, "2026-10-31T15:00:00Z", "Feedback: Make it pop", ""))

    def test_long_text_is_cut(self):
        line = feedback.entry("10", URL, "2026-10-31T15:00:00Z", "t", "x" * 2000)
        self.assertLess(len(line), 800)
        self.assertIn("…", line)

    def test_add_goes_to_end_of_inbox(self):
        one = feedback.add(DOC, "- first")
        two = feedback.add(one, "- second")
        self.assertEqual(two, "# Feedback\n\nintro\n\n## Inbox\n\n- first\n- second\n\n## Handled\n\n- old one\n")

    def test_add_creates_sections(self):
        self.assertEqual(feedback.add("# Feedback\n", "- a"), "# Feedback\n\n## Inbox\n\n- a\n\n## Handled\n")


if __name__ == "__main__":
    unittest.main()
