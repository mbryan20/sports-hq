"""Players page (docs/players/index.html): every column header has a plain-English explanation, the "How to read this
table" legend is there, and the outside experts' ROS ranks are NOT on the page (private Doc only, Nov 14). Reads the page
as text."""
import json
import os
import re
import shutil
import subprocess
import unittest

from shq.espn_fantasy import NBA_STATS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "docs", "players", "index.html")


def page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def block(text, start, end="\n  };"):
    """The text from `start` to the first `end` after it."""
    i = text.index(start)
    return text[i:text.index(end, i)]


def help_keys(text, name):
    """Keys of a HELP_* object: lines like '    v: L => ({ t: ...'."""
    return re.findall(r"^    (\w+): (?:\w+|\(\)) => \(\{", block(text, f"const {name} = {{"), re.M)


def header_cols(text, fn):
    """The column ids in a render function's `const cols = [...]` header list."""
    body = text[text.index(fn):]
    cols = block(body, "const cols = [", "].filter(Boolean)")
    return re.findall(r'\bcol: "(\w+)",', cols), cols


class EveryColumnExplained(unittest.TestCase):
    def setUp(self):
        self.text = page()

    def test_basketball_columns(self):
        cols, src = header_cols(self.text, "function render()")
        keys = help_keys(self.text, "HELP_NBA")
        self.assertGreaterEqual(len(cols), 8)
        for c in cols:
            self.assertIn(c, keys, f"basketball column {c!r} has no explanation in HELP_NBA")
        # category columns are "c<i>" and explained from CAT_HELP
        self.assertIn('col: "c" + i', src)
        self.assertIn(r"/^c\d+$/.test(col)", self.text)

    def test_football_columns(self):
        cols, _ = header_cols(self.text, "function renderNFL(")
        keys = help_keys(self.text, "HELP_NFL")
        for c in ("rk", "name", "ros", "proj", "wkrk", "exp", "explately", "fc", "next"):
            self.assertIn(c, cols)
        for c in cols:
            self.assertIn(c, keys, f"football column {c!r} has no explanation in HELP_NFL")

    def test_every_nba_category_explained(self):
        cat_help = block(self.text, "const CAT_HELP = {")
        for name in NBA_STATS.values():
            self.assertRegex(cat_help, r'(^|[\s{,])("?)' + re.escape(name) + r'\2: "', f"category {name} has no explanation")

    def test_each_explanation_has_what_and_whats_good(self):
        for name in ("HELP_NBA", "HELP_NFL"):
            b = block(self.text, f"const {name} = {{")
            n = len(help_keys(self.text, name))
            self.assertEqual(len(re.findall(r"\bt: ", b)), n, name)
            self.assertEqual(len(re.findall(r"\bd: ", b)), n, name)
            self.assertEqual(len(re.findall(r"\bg: ", b)), n, name)

    def test_headers_only_built_through_hcell(self):
        """Every header cell gets the ⓘ button: head rows come from hcell, never a hand-written <th>."""
        heads = re.findall(r"const head = (`<tr>.*)", self.text)
        self.assertEqual(len(heads), 2)
        for h in heads:
            self.assertIn("cols.map(hcell)", h)
            self.assertNotIn("<th", h)
        self.assertIn('data-explain="${c.col}"', block(self.text, "function hcell(", "\n  }"))

    def test_legend_and_intro(self):
        self.assertEqual(self.text.count("legendHTML(LEGEND_"), 2)
        self.assertIn("How to read this table", self.text)
        self.assertEqual(self.text.count('<p class="intro">'), 2)


class OutsideRosRanksArePrivate(unittest.TestCase):
    """Michael, Nov 14: "1: private Doc". FantasyPros' terms forbid republishing, and this page is public."""
    def test_no_expert_ranks_on_the_page(self):
        text = page()
        self.assertNotIn('S.loadFile("ros")', text)
        self.assertNotIn('col: "rr"', text)
        self.assertNotIn("FantasyPros", text)
        self.assertIn("docs.google.com/document/d/", text)    # one link to his private Doc


if __name__ == "__main__":
    unittest.main()
