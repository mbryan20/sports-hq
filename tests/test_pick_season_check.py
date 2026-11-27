import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "picks"))
from pp import season_check as S  # noqa: E402


def card(rows):
    return [{"id": "yahoo", "rows": rows}, {"id": "cfp", "rows": [{"key": "X@Y", "model": 0.6, "market": 0.6, "pick_team": "Y"}]}]


class SeasonCheck(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data" / "postmortem").mkdir(parents=True)

    def pm(self, week, picks):
        (self.root / "data" / "postmortem" / f"2026-w{week:02d}.json").write_text(
            json.dumps({"week": week, "pools": {"yahoo": {"card": {"picks": picks}}}}))

    def test_counts_and_disagreements(self):
        S.log_rows(card([
            {"key": "A@B", "pick_team": "B", "model": 0.45, "market": 0.55},   # disagree, B won: market right
            {"key": "C@D", "pick_team": "D", "model": 0.80, "market": 0.85},   # agree, D lost: both wrong
            {"key": "E@F", "pick_team": "F", "model": 0.70, "market": 0.70},   # pick changed later: skipped
            {"key": "G@H", "pick_team": "H", "model": 0.60, "market": None},   # no market: not logged
        ]), 10, 2026, root=self.root)
        self.pm(10, [{"key": "A@B", "pick": "B", "result": 1.0}, {"key": "C@D", "pick": "D", "result": 0.0},
                     {"key": "E@F", "pick": "E", "result": 1.0}])
        s = S.summary(self.root)
        self.assertEqual((s["n"], s["market"], s["model"], s["dis"], s["dis_market"], s["dis_model"]), (2, 1, 0, 1, 1, 0))
        self.assertEqual((s["close"], s["close_market"]), (1, 1))
        self.assertIn("week 10, 2 graded", S.line(self.root))

    def test_ungraded_week_ignored_and_empty_is_none(self):
        self.assertIsNone(S.line(self.root))
        S.log_rows(card([{"key": "A@B", "pick_team": "B", "model": 0.5, "market": 0.6}]), 13, 2026, root=self.root)
        self.assertIsNone(S.line(self.root))  # week 13 not graded yet

    def test_only_yahoo_rows_logged(self):
        S.log_rows(card([{"key": "A@B", "pick_team": "B", "model": 0.5, "market": 0.6}]), 11, 2026, root=self.root)
        rows = json.loads((self.root / "data" / "model_log" / "2026-w11.json").read_text())
        self.assertEqual([r["key"] for r in rows], ["A@B"])


if __name__ == "__main__":
    unittest.main()
