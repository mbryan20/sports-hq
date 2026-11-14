"""shq/ros.py: rest-of-season ranks from experts who updated recently and rank well for accuracy (rule 15, Nov 14)."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from shq import ros

NOW = dt.datetime(2026, 11, 14, 17, tzinfo=dt.timezone.utc)
DAY = 86400


def expert(i, name, days_ago, acc, link=True):
    return {"id": i, "name": name, "site": "x", "last_updated": int(NOW.timestamp()) - days_ago * DAY,
            "in_season_rank": str(acc) if acc else "", "rankings_link": f"https://fp/{name}.php?type=ros&position=RB" if link else ""}


def page(players, experts):
    ecr = {"players": [{"player_name": n, "player_team_id": t, "rank_ecr": r} for n, t, r in players], "total_experts": 6, "last_updated": "11/14"}
    return f"<script>var ecrData = {json.dumps(ecr)};\nvar expertGroupsData = {json.dumps({'expert_data': experts})};</script>"


def expert_page(order):
    return "".join(f'<tr><td class="center">{i}</td>\n<td class="player-label"><a class="fp-player-link" fp-player-name="{n}" href="#">{n}</a></td>\n'
                   f'<td class="center">{t}</td><td class="center">9</td></tr>' for i, (n, t) in enumerate(order, 1))


class Panel(unittest.TestCase):
    def test_only_fresh_accurate_public_experts(self):
        es = [expert(1, "fresh-good", 2, 20), expert(2, "stale-good", 30, 5), expert(3, "fresh-bad", 1, 120),
              expert(4, "fresh-good-private", 1, 10, link=False), expert(5, "no-accuracy", 1, None), expert(6, "week-old", 7, 40)]
        self.assertEqual([e["name"] for e in ros.panel(es, NOW)], ["fresh-good", "week-old"])

    def test_consensus_averages_and_counts_a_missing_player_last(self):
        a = [("Hall", "NYJ", 1), ("Allen", "NYJ", 2)]
        b = [("Allen", "NYJ", 1), ("Hall", "NYJ", 2), ("Marks", "HOU", 3)]
        got = ros.consensus([a, b])
        self.assertEqual(got[-1][0], "Marks")
        self.assertEqual({r[0]: r[3] for r in got}, {"Hall": 1.5, "Allen": 1.5, "Marks": 3.0})   # Marks: a's 2 + 1, b's 3

    def test_names_match_without_suffixes(self):
        self.assertEqual(ros._norm("KC Concepcion Jr."), ros._norm("KC Concepcion"))
        self.assertEqual(ros._norm("Davante Adams"), "davanteadams")          # a "v" inside a name stays
        self.assertEqual(ros._norm("Zonovan Knight"), ros._norm("Bam Knight"))


class Refresh(unittest.TestCase):
    def test_refresh_uses_the_panel_and_keeps_why_lines(self):
        fresh = [expert(i, f"e{i}", 1, 10 + i) for i in range(3)]
        rb = page([("Breece Hall", "NYJ", 18), ("Braelon Allen", "NYJ", 30)], fresh + [expert(9, "stale", 40, 1)])
        order = [("Braelon Allen", "NYJ"), ("Breece Hall", "NYJ")]
        def fetch(url):
            if "ros-ppr-rb" in url:
                return rb
            if "fp/e" in url:
                return expert_page(order)
            if "fp/stale" in url:
                raise AssertionError("stale expert fetched")
            return page([], [])                      # other positions: no experts -> fallback, nothing to match
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ros.json"
            p.write_text(json.dumps({"players": {"braelonallen|RB": {"name": "Braelon Allen", "pos": "RB", "team": "NYJ", "why": "keep me"},
                                                 "breecehall|RB": {"name": "Breece Hall", "pos": "RB", "team": "NYJ", "why": "x"}}}), encoding="utf-8")
            out = ros.refresh(NOW, fetch, p)
        allen = out["players"]["braelonallen|RB"]
        self.assertEqual((allen["rank"], allen["fp_rank"], allen["why"]), ("RB1", "RB30", "keep me"))
        self.assertEqual([e["name"] for e in out["method"]["RB"]["experts"]], ["e0", "e1", "e2"])
        self.assertTrue(out["method"]["QB"]["fallback"])


if __name__ == "__main__":
    unittest.main()
