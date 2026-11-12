"""Picks page history (pp.history): card-version diffs, week grouping, shallow rebuilds, and line-series building.
Fixtures only, no network, no real git."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import history as H  # noqa: E402
from pp import lines as L  # noqa: E402


def card(stage, gen, rows_bto=(), rows_yahoo=(), tbs=(), week=11, label="Week of Nov 12 - Nov 16, 2026 (Yahoo Week 11, BTO Week 11)"):
    return {"meta": {"stage": stage, "week": week, "week_label": label, "generated_iso": gen},
            "cards": [{"id": "yahoo", "title": "Yahoo pick'em", "rows": list(rows_yahoo), "tiebreakers": list(tbs)},
                      {"id": "bto", "title": "BTO Beat the Odds", "rows": list(rows_bto)},
                      {"id": "survivor", "title": "Survivor", "status": "Eliminated in Week 7 (NYJ).", "rows": []}]}


def bto(pick, team, model, wager, why="Pool -7.5 vs market -10; cover 70%", key="USC@Indiana", game="USC @ Indiana"):
    return {"game": game, "pick": pick, "pick_team": team, "model": model, "market": 0.5, "wager": wager, "why": why, "key": key}


def yah(team, model, key="Kansas@West Virginia", game="Kansas @ West Virginia", pick=None):
    return {"game": game, "pick": pick or team, "pick_team": team, "model": model, "market": 0.56, "wager": "", "why": "", "key": key}


class FakeGit:
    """Answers `git log`, `git show sha:path` and `git rev-parse --is-shallow-repository` from a list of commits."""
    def __init__(self, commits, shallow=False):
        self.commits, self.shallow = commits, shallow  # [(sha, iso, subject, doc)] oldest first

    def __call__(self, *a):
        if a[0] == "log":
            return "\n".join(f"{s} {t} {subj}" for s, t, subj, _ in reversed(self.commits))
        if a[0] == "show":
            sha = a[1].split(":")[0]
            return json.dumps(next(d for s, _, _, d in self.commits if s == sha))
        if a[0] == "rev-parse":
            return "true" if self.shallow else "false"
        return ""


class SplitAndExtract(unittest.TestCase):
    def test_split_pick(self):
        self.assertEqual(H.split_pick("Indiana -3.5 (LP 4)", "Indiana"), ("Indiana", "-3.5 (LP 4)"))
        self.assertEqual(H.split_pick("MIN +7.5", "MIN"), ("MIN", "+7.5"))
        self.assertEqual(H.split_pick("Maryland (dog)", "Maryland"), ("Maryland", ""))

    def test_extract_reads_pool_and_market_lines_and_tiebreakers(self):
        tbs = ["TB2 most points: <b>Boise St.</b> (10%), alt Miami (FL) (8%)", "TB2 locks Fri, Nov 13 5:55 pm CST"]
        p = H.extract(card("draft", "2026-11-12T03:33:00+00:00", [bto("Indiana -3.5 (LP 4)", "Indiana", 0.6969, "$3,070")],
                           [yah("West Virginia", 0.46)], tbs))
        r = p["bto"]["rows"]["USC@Indiana"]
        self.assertEqual((r["line"], r["pool"], r["mkt"], r["p"], r["pm"]), ("-3.5 (LP 4)", -7.5, -10.0, 0.697, None))
        self.assertEqual(p["yahoo"]["rows"]["TB2 most points"]["pick"], "Boise St.")
        self.assertNotIn("TB2 locks Fri, Nov 13 5", p["yahoo"]["rows"])
        self.assertEqual(p["survivor"]["status"], "Eliminated in Week 7 (NYJ).")


class Diff(unittest.TestCase):
    def pools(self, *a, **k):
        return H.extract(card(*a, **k))

    def test_pick_line_cover_wager(self):
        a = self.pools("draft", "x", [bto("Indiana -7.5", "Indiana", 0.58, "$660")], [yah("Kansas", 0.52)])
        b = self.pools("final", "y", [bto("Indiana -6.5", "Indiana", 0.54, "$1,300", why="Pool -6.5 vs market -9")],
                       [yah("West Virginia", 0.54)])
        ch = H.diff_pool(a["bto"], b["bto"], "bto")
        self.assertEqual(ch[0]["fields"], ["line", "mkt", "p", "wager"])
        self.assertEqual(ch[0]["text"], "USC @ Indiana: line -7.5 → -6.5, market -10 → -9, cover 58% → 54%, "
                                        "wager $660 → $1,300")
        y = H.diff_pool(a["yahoo"], b["yahoo"], "yahoo")
        self.assertEqual(y[0]["text"], "Kansas @ West Virginia: Kansas → West Virginia")
        self.assertEqual(y[0]["fields"], ["pick"])  # 52% -> 54% is under Yahoo's 3-point bar

    def test_small_moves_skipped_big_ones_kept(self):
        a = self.pools("draft", "x", [bto("Indiana -7.5", "Indiana", 0.580, "$660")], [yah("Kansas", 0.62)])
        b = self.pools("final", "y", [bto("Indiana -7.5", "Indiana", 0.571, "$660")], [yah("Kansas", 0.67)])
        self.assertEqual(H.diff_pool(a["bto"], b["bto"], "bto"), [])
        self.assertEqual(H.diff_pool(a["yahoo"], b["yahoo"], "yahoo")[0]["text"], "Kansas @ West Virginia: win 62% → 67%")

    def test_added_and_dropped(self):
        a = self.pools("draft", "x", [bto("Indiana -7.5", "Indiana", 0.58, "$660")])
        b = self.pools("final", "y", [bto("Alabama -15.5", "Alabama", 0.56, "$660", key="Alabama@Vanderbilt",
                                          game="Alabama @ Vanderbilt")])
        ch = H.diff_pool(a["bto"], b["bto"], "bto")
        self.assertEqual([c["fields"] for c in ch], [["added"], ["dropped"]])
        self.assertEqual(ch[1]["text"], "USC @ Indiana: dropped Indiana -7.5")
        self.assertEqual(H.diff_pool(None, b["bto"], "bto"), [])


class Build(unittest.TestCase):
    def commits(self):
        d = card("draft", "2026-11-12T03:33:00+00:00", [bto("Indiana -3.5 (LP 4)", "Indiana", 0.697, "$3,070")], [yah("Kansas", 0.52)])
        same = json.loads(json.dumps(d))  # re-render: same picks
        f = card("final", "2026-11-13T02:00:00+00:00", [bto("Indiana -2.5 (LP 5)", "Indiana", 0.66, "$3,070")], [yah("Kansas", 0.53)])
        old = card("refresh", "2026-11-07T14:06:00+00:00", [bto("NE -0.5 (LP 2)", "NE", 0.585, "$830", key="GB@NE", game="GB @ NE")],
                   week=10, label="Week of Nov 5 - Nov 9, 2026 (Yahoo Week 10, BTO Week 10)")
        return [("a0", "2026-11-07T08:10:39-06:00", "Pool picks: refresh", old),
                ("a1", "2026-11-12T07:16:56-06:00", "Pool picks: draft", d),
                ("a2", "2026-11-12T08:00:00-06:00", "Picks: re-rendered", same),
                ("a3", "2026-11-13T09:01:47Z", "Picks backup card: final", f),
                ("a4", "2026-11-13T16:00:06-06:00", "Restore Thursday's draft", d)]

    def test_versions_fold_label_and_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            page, versions = H.build(git=FakeGit(self.commits()), cards_path=pathlib.Path(tmp) / "none.json",
                                     now=datetime(2026, 11, 13, 23, tzinfo=timezone.utc))
        self.assertEqual([w["week"] for w in page["weeks"]], [11, 10])
        wk = page["weeks"][0]
        self.assertEqual([v["label"] for v in wk["versions"]],
                         ["Wed 9:33 PM draft", "Thu 8:00 PM final (backup)", "Fri 4:00 PM draft (restored)"])
        b = next(p for p in wk["pools"] if p["id"] == "bto")
        self.assertEqual(b["cols"], [0, 1, 2])
        self.assertEqual(b["changes"][1][0]["text"], "USC @ Indiana: line -3.5 (LP 4) → -2.5 (LP 5), cover 70% → 66%")
        y = next(p for p in wk["pools"] if p["id"] == "yahoo")
        self.assertEqual((y["cols"], y["hidden"]), ([0, 2], 1))  # 1-point wiggle hidden; last version always shown
        self.assertEqual([v["id"] for v in versions], ["a1", "a2", "a3", "a4"])  # newest week only

    def test_uncommitted_build_is_added(self):
        new = card("final", "2026-11-14T01:00:00+00:00", [bto("Indiana -1.5 (LP 6)", "Indiana", 0.64, "$3,070")])
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "cards.json"
            p.write_text(json.dumps(new))
            page, versions = H.build(git=FakeGit(self.commits()), cards_path=p, now=datetime(2026, 11, 14, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(page["weeks"][0]["versions"][-1]["id"], "local")
        self.assertNotIn("local", [v["id"] for v in versions])

    def test_shallow_checkout_keeps_stored_versions_and_old_weeks(self):
        full, _ = H.build(git=FakeGit(self.commits()), cards_path="nope.json")
        _, stored = H.build(git=FakeGit(self.commits()), cards_path="nope.json")
        shallow = FakeGit(self.commits()[-1:], shallow=True)
        page, _ = H.build(git=shallow, cards_path="nope.json", stored=stored, previous=full)
        self.assertEqual([w["week"] for w in page["weeks"]], [11, 10])
        self.assertEqual([v["label"] for v in page["weeks"][0]["versions"]], [v["label"] for v in full["weeks"][0]["versions"]])


class LineSeries(unittest.TestCase):
    def row(self, pool, game, side, pool_line, mkt, kick="2026-11-14T20:30Z"):
        return {"pool": pool, "league": "CFB", "game": game, "side": side, "pool_line": pool_line, "market_line": mkt, "kick": kick}

    def test_home_perspective_change_only_and_side_flip(self):
        s = {}
        H.update_series(s, "t1", [self.row("cfp", "USC @ Indiana", "Indiana", -7.5, -10)])
        H.update_series(s, "t2", [self.row("cfp", "USC @ Indiana", "Indiana", -7.5, -10)])
        H.update_series(s, "t3", [self.row("cfp", "USC @ Indiana", "Indiana", -7.5, -9.5)])
        # market moves past the pool line: the value side flips to USC, lines are now USC's
        H.update_series(s, "t4", [self.row("cfp", "USC @ Indiana", "USC", 7.5, 6.5)])
        g = s["games"]["USC @ Indiana"]
        self.assertEqual(g["market"], [["t1", -10.0], ["t3", -9.5], ["t4", -6.5]])
        self.assertEqual(g["pools"]["cfp"], [["t1", -7.5]])
        self.assertEqual((g["home"], g["away"], g["seen"]), ("Indiana", "USC", "t4"))

    def test_extra_yahoo_lines_and_openers(self):
        s = {}
        rows = [self.row("bto", "USC @ Indiana", "Indiana", -7.5, -10)]
        extra = [{"game": "USC @ Indiana", "league": "CFB", "market_home": None, "open_home": -9.5},
                 {"game": "Kansas @ West Virginia", "league": "CFB", "market_home": -2.5, "open_home": -1.5}]
        H.update_series(s, "t1", rows, extra)
        H.update_series(s, "t2", rows, [dict(extra[1], market_home=-3.0)])
        self.assertEqual(s["games"]["USC @ Indiana"]["open"], -9.5)
        self.assertEqual(s["games"]["Kansas @ West Virginia"]["market"], [["t1", -2.5], ["t2", -3.0]])
        self.assertEqual(s["games"]["Kansas @ West Virginia"]["pools"], {})

    def test_merge_refolds_in_time_order(self):
        a = {"games": {"G @ H": {"market": [["2026-11-11T01:00Z", -3.0], ["2026-11-11T05:00Z", -3.5]], "pools": {}}}}
        b = {"games": {"G @ H": {"market": [["2026-11-11T03:00Z", -3.0], ["2026-11-11T07:00Z", -4.0]], "pools": {}}}}
        m = H.merge_stores(a, b)
        self.assertEqual(m["games"]["G @ H"]["market"], [["2026-11-11T01:00Z", -3.0], ["2026-11-11T05:00Z", -3.5],
                                                         ["2026-11-11T07:00Z", -4.0]])

    def test_backfill_from_pick_lines_history(self):
        snaps = [("s1", "2026-11-12T01:07:07Z", "data", {"updated": "2026-11-11T19:07:00-06:00", "week": 11,
                                                         "rows": [self.row("cfp", "USC @ Indiana", "Indiana", -7.5, -9.5)]}),
                 ("s2", "2026-11-12T03:07:05Z", "data", {"updated": "2026-11-11T21:07:00-06:00", "week": 11,
                                                         "rows": [self.row("cfp", "USC @ Indiana", "Indiana", -7.5, -10)]})]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(H.backfill_lines(git=FakeGit(snaps), out_dir=tmp), [11])
            d = json.loads((pathlib.Path(tmp) / "2026-w11.json").read_text())
        self.assertEqual(d["games"]["USC @ Indiana"]["market"], [["2026-11-12T01:07Z", -9.5], ["2026-11-12T03:07Z", -10.0]])


class LinesRunHook(unittest.TestCase):
    """pp.lines.run appends each scan to the week's line file next to pick_lines.json."""
    def test_scan_appends_history(self):
        def ev(eid, away, home, spread, open_=None):
            team = lambda n: {"location": n, "abbreviation": n[:4].upper(), "displayName": n, "shortDisplayName": n}
            odds = {"spread": spread, "overUnder": 50.5, "provider": {"name": "DraftKings"}}
            if open_ is not None:
                odds["pointSpread"] = {"home": {"open": {"line": str(open_)}}}
            return L.parse_event({"id": eid, "date": "2026-11-14T20:30Z", "competitions": [{
                "status": {"type": {"state": "pre"}},
                "competitors": [{"homeAway": "home", "team": team(home)}, {"homeAway": "away", "team": team(away)}],
                "odds": [odds]}]}, "CFB")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "slates").mkdir()
            (tmp / "slates/2026-w11.json").write_text(json.dumps({"cfbd_week": 11,
                "cfp": {"games": [{"away": "USC", "home": "Indiana", "home_spread": -7.5}]},
                "yahoo": {"games": [{"away": "Kansas", "home": "West Virginia"}]}}))
            events = [ev("1", "USC", "Indiana", -10, open_=-9.5), ev("2", "Kansas", "West Virginia", -2.5)]
            with mock.patch.object(L, "ROOT", tmp), mock.patch.object(L, "OUT", tmp / "out.json"), \
                    mock.patch.object(L, "SENT", tmp / "sent.json"), mock.patch.dict(os.environ, {"DRY_RUN": "1"}):
                L.run(None, False, datetime(2026, 11, 12, 15, tzinfo=timezone.utc), lambda lg, wk: events if lg == "CFB" else [])
            d = json.loads((tmp / "pick_line_history/2026-w11.json").read_text())
        g = d["games"]["USC @ Indiana"]
        self.assertEqual((g["market"], g["pools"]["cfp"], g["open"]), ([["2026-11-12T15:00Z", -10.0]], [["2026-11-12T15:00Z", -7.5]], -9.5))
        self.assertEqual(d["games"]["Kansas @ West Virginia"]["market"], [["2026-11-12T15:00Z", -2.5]])


if __name__ == "__main__":
    unittest.main()
