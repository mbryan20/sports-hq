"""Pool Picks push and checks: saved picks vs card, decision departures, push order, automatic rule checks."""
import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "picks"))
from pp import checks, push  # noqa: E402

CT = ZoneInfo("America/Chicago")
WED = datetime(2026, 10, 28, 21, 0, tzinfo=CT)
SAT = datetime(2026, 10, 31, 8, 0, tzinfo=CT)


def row(key, pick, wager="", team=None, why="edge", model=0.7, market=0.7):
    away, home = key.split("@")
    return {"key": key, "game": f"{away} @ {home}", "pick": pick, "wager": wager, "why": why,
            "pick_team": team or pick.split(" ")[0], "model": model, "market": market}


def cards():
    bto = {"id": "bto", "rows": [row("MIN@DET", "MIN +7.5 (LP 4)", "$1,300"), row("Florida@Georgia", "Georgia -11.5", "$660"),
                                 row("Northwestern@Oregon", "Oregon -3.5", "$660")]}
    cfp = {"id": "cfp", "rows": [row("Auburn@Ole Miss", "Auburn +13.5", "11,904", why="Stale pool line")]}
    yahoo = {"id": "yahoo", "rows": [row("Baylor@UCF", "UCF", team="UCF"), row("Wisconsin@Iowa", "Iowa", team="Iowa", market=0.56),
                                     row("Illinois@Maryland", "Illinois", team="Illinois", why="QB back")],
             "tiebreakers": ["TB1 Wisconsin @ Iowa: <b>Wisconsin 13, Iowa 23</b> (alt Wisconsin 14, Iowa 23)",
                             "TB2 most points: <b>Notre Dame</b> (17%), alt Georgia (8%)",
                             "TB2 fewest points: <b>Minnesota</b> (21%), alt Wisconsin (13%)"]}
    return [bto, cfp, yahoo]


def slate(**saved):
    s = {"bto": {"mode": "three", "balance": 2620, "games": [
            {"league": "NFL", "away": "MIN", "home": "DET", "home_spread": -3.5, "big": True, "kick": "Sun 11/1 12:00 PM CT"},
            {"league": "CFB", "away": "Florida", "home": "Georgia", "home_spread": -11.5, "kick": "Sat 10/31 2:30 PM CT"},
            {"league": "CFB", "away": "Northwestern", "home": "Oregon", "home_spread": -3.5, "kick": "Sat 10/31 2:30 PM CT"}]},
         "cfp": {"balance": 11904, "games": [{"away": "Auburn", "home": "Ole Miss", "home_spread": -13.5}]},
         "yahoo": {"tb1": [["Wisconsin", "Iowa"]], "games": [
            {"away": "Baylor", "home": "UCF", "kick": "Fri 10/30 6:30 PM"},
            {"away": "Wisconsin", "home": "Iowa", "kick": "Sat 10/31 11:00 AM"},
            {"away": "Illinois", "home": "Maryland", "kick": "Sat 10/31 11:00 AM"}]}}
    for pool, v in saved.items():
        s[pool]["saved"] = v
    return s


BTO_SAME = {"read": "x", "bets": [{"key": "MIN@DET", "pick": "MIN +7.5", "wager": 1300},
                                  {"key": "Florida@Georgia", "pick": "Georgia -11.5", "wager": 660},
                                  {"key": "Northwestern@Oregon", "pick": "Oregon -3.5", "wager": "$660"}]}


class SavedVsCard(unittest.TestCase):
    def test_ats_match_and_differ(self):
        c = cards()
        self.assertEqual(push.compare_ats(c[0], BTO_SAME), ("match", None))
        st, line = push.compare_ats(c[1], {"read": "x", "bets": [{"key": "Florida@Georgia", "pick": "Georgia -11.5", "wager": 11904}]})
        self.assertEqual(st, "differ")
        self.assertEqual(line, "CHANGE: CFP: yours Georgia -11.5 11,904 → card Auburn +13.5 11,904 (Stale pool line)")

    def test_ats_wager_change_is_a_change(self):
        mine = {"read": "x", "bets": [dict(b) for b in BTO_SAME["bets"]]}
        mine["bets"][0]["wager"] = 1000
        self.assertEqual(push.compare_ats(cards()[0], mine)[0], "differ")

    def test_change_line_carries_cover_comparison(self):
        card = dict(cards()[0], saved_vs="cover chance: yours SF -0.5 58% vs card MIN +8.5 (LP 4) 68%")
        mine = {"read": "x", "bets": [{"key": "SF@DAL", "pick": "SF -0.5", "wager": 3070}]}
        st, line = push.compare_ats(card, mine)
        self.assertEqual(st, "differ")
        self.assertIn("; cover chance: yours SF -0.5 58% vs card MIN +8.5 (LP 4) 68%)", line)

    def test_no_card_rows_is_not_a_change(self):
        card = {"id": "bto", "rows": [], "status": "Slate not read from the site yet (laptop run missed)."}
        self.assertEqual(push.compare_ats(card, BTO_SAME), ("nocard", None))
        alerts, body = push.compose([card], slate(bto=BTO_SAME), due=("bto",), now=WED)
        self.assertEqual(alerts, [])
        self.assertEqual(body, ["BTO (locks Fri 8pm): Slate not read from the site yet (laptop run missed)."])

    def test_ats_empty_and_unread(self):
        self.assertEqual(push.compare_ats(cards()[0], {"read": "x", "bets": []})[0], "empty")
        self.assertEqual(push.compare_ats(cards()[0], {"unread": "signed out"})[0], "unread")
        self.assertEqual(push.compare_ats(cards()[0], None)[0], "unread")

    def test_yahoo_pick_and_tb1(self):
        saved = {"read": "x", "picks": {"Baylor@UCF": "Baylor", "Wisconsin@Iowa": "Wisconsin", "Illinois@Maryland": "Illinois"},
                 "tb1": {"Wisconsin@Iowa": "Iowa 20, Wisconsin 17"}, "tb2": {"most": "Notre Dame", "fewest": "Minnesota"}}
        st, lines, unsaved = push.compare_yahoo(cards()[2], saved, slate()["yahoo"]["games"], SAT)
        # Baylor@UCF kicked off Friday, so it can't be a change any more
        self.assertEqual(lines, ["CHANGE: Yahoo: yours Wisconsin → card Iowa (edge)",
                                 "CHANGE: Yahoo TB1 Wisconsin @ Iowa: yours Iowa 20, Wisconsin 17 → card Wisconsin 13, Iowa 23"])
        self.assertEqual(unsaved, [])

    def test_tb_scores_order_insensitive(self):
        saved = {"read": "x", "picks": {"Wisconsin@Iowa": "Iowa", "Illinois@Maryland": "Illinois"},
                 "tb1": {"Wisconsin@Iowa": "Iowa 23, Wisconsin 13"}, "tb2": {"most": "notre dame", "fewest": "Minnesota"}}
        self.assertEqual(push.compare_yahoo(cards()[2], saved, slate()["yahoo"]["games"], SAT)[0], "match")

    def test_unsaved_tb1_is_a_change_on_the_final_call(self):
        sl = slate(yahoo={"read": "x", "picks": {"Wisconsin@Iowa": "Iowa", "Illinois@Maryland": "Illinois"}, "tb1": {}})
        alerts, body = push.compose(cards(), sl, due=("cfp", "yahoo"), now=SAT, final_call=True)
        self.assertIn("CHANGE: Yahoo: not saved yet: TB1 Wisconsin @ Iowa", alerts)
        alerts, _ = push.compose(cards(), sl, due=("cfp", "yahoo"), now=SAT, final_call=False)
        self.assertEqual(alerts, [])  # the Wednesday draft only lists it in the Yahoo line


class Message(unittest.TestCase):
    def test_order_and_match_lines(self):
        sl = slate(bto=BTO_SAME, cfp={"read": "x", "bets": [{"key": "Florida@Georgia", "pick": "Georgia -11.5", "wager": 11904}]})
        sl["decisions"] = {"differs": [{"date": "Oct 23", "old": "CFP all on one game", "new": "split", "because": "two stale lines"}]}
        title, msg, urgent = push.message(cards(), sl, "DRAFT", due=("bto", "cfp", "yahoo"), now=WED)
        lines = msg.split("\n")
        self.assertEqual(title, "Pool Picks DRAFT: 1 change to your saved picks")
        self.assertTrue(lines[0].startswith("CHANGE: CFP: yours Georgia -11.5"))
        self.assertTrue(lines[1].startswith("Differs from your decision on Oct 23: CFP all on one game → split, because"))
        self.assertEqual(lines[2], "BTO (locks Fri 8pm): your saved picks match")
        self.assertTrue(lines[3].startswith("CFP (locks Sat 11am): Auburn +13.5 11,904"))
        self.assertTrue(lines[4].startswith("Yahoo: 3 set; close calls: Wisconsin@Iowa: Iowa; TB1 Wisconsin 13, Iowa 23; TB2 most Notre Dame, fewest Minnesota"))
        self.assertEqual(lines[-1], push.PAGE)
        self.assertTrue(urgent)

    def test_only_due_pools_and_unread_note(self):
        _, msg, urgent = push.message(cards(), slate(cfp={"unread": "signed out"}), "SAT REFRESH", now=SAT)
        self.assertNotIn("BTO (", msg)  # Saturday's push covers CFP and Yahoo
        self.assertIn("CFP (locks Sat 11am): Auburn +13.5 11,904 (saved picks not read: signed out)", msg)
        self.assertFalse(urgent)


class AutoChecks(unittest.TestCase):
    def res(self, c, s, now=WED):
        return {r["check"]: r for r in checks.run(c, s, now)}

    def test_clean_card_passes(self):
        bad = [r for r in checks.run(cards(), slate(), WED) if not r["ok"]]
        self.assertEqual(bad, [])

    def test_bto_rule_breaks(self):
        c = cards()
        c[0]["rows"][1]["wager"] = "$655"   # not a $10 multiple
        c[0]["rows"][2]["wager"] = "$600"   # 1300 > 2 x 600
        c[0]["rows"].pop(0)                 # 2 bets in Three Bet mode, Big Game gone
        r = self.res(c, slate())
        self.assertFalse(r["BTO three mode: exactly 3 bets"]["ok"])
        self.assertFalse(r["BTO Big Game included"]["ok"])
        self.assertFalse(r["BTO wagers in $10 multiples"]["ok"])

    def test_bto_line_must_include_lp_and_not_be_locked(self):
        c = cards()
        c[0]["rows"][0]["pick"] = "MIN +7 (LP 4)"
        r = self.res(c, slate(), now=datetime(2026, 11, 1, 13, 0, tzinfo=CT))
        self.assertFalse(r["BTO lines = pool line + line points"]["ok"])
        self.assertFalse(r["BTO no pick on a locked game"]["ok"])

    def test_cfp_total_and_formats(self):
        c = cards()
        c[1]["rows"][0]["wager"] = "5,000"
        c[2]["rows"][0]["pick"] = "UCF -3.5"
        c[2]["rows"][1]["why"] = "Take Iowa if the QB plays"
        r = self.res(c, slate())
        self.assertFalse(r["CFP total 5,000 is 50-100% of 11,904"]["ok"])
        self.assertFalse(r["Yahoo format: straight-up (no spreads)"]["ok"])
        self.assertFalse(r["No 'if X then Y' hedging in picks or reasons"]["ok"])


if __name__ == "__main__":
    unittest.main()


class ChangedSince(unittest.TestCase):
    """Nov 12: every redraft's push opens with what moved since the last card, per pool, with the reason."""
    def prev(self):
        return {"meta": {"generated": "Wed Nov 11, 09:33 PM CT", "generated_iso": "a", "week": 11}, "cards": cards()}

    def test_lists_each_change_with_reason(self):
        new = cards()
        new[2]["rows"][1].update(pick="Wisconsin", pick_team="Wisconsin", why="Your pick kept")
        new[0]["rows"][1]["wager"] = "$700"
        lines = push.since_lines(new, self.prev())
        self.assertEqual(lines[0], "Changed since Wed Nov 11, 09:33 PM:")
        self.assertIn("BTO: Florida @ Georgia: wager $660 → $700", lines)
        self.assertIn("Yahoo: Wisconsin @ Iowa: Iowa → Wisconsin (Your pick kept)", lines)

    def test_says_when_nothing_changed(self):
        self.assertEqual(push.since_lines(cards(), self.prev()),
                         ["Changed since Wed Nov 11, 09:33 PM:", "no pick, line or wager changed."])
        self.assertEqual(push.since_lines(cards(), None), [])

    def test_push_leads_with_it(self):
        new = cards()
        new[2]["rows"][1].update(pick="Wisconsin", pick_team="Wisconsin")
        _, msg, _ = push.message(new, slate(), "DRAFT", due=("bto",), now=WED, prev=self.prev())
        self.assertTrue(msg.startswith("Changed since Wed Nov 11, 09:33 PM:\nYahoo: Wisconsin @ Iowa: Iowa → Wisconsin"))

    def test_prev_card_skips_the_current_version(self):
        import json as _j
        docs = {"s1": {"meta": {"generated_iso": "now", "week": 11}}, "s2": {"meta": {"generated_iso": "then", "week": 11}}}

        def git(*a):
            if a[0] == "log":
                return "s1\ns2\n"
            return _j.dumps(docs[a[1].split(":")[0]])
        self.assertEqual(push.prev_card({"generated_iso": "now", "week": 11}, git)["meta"]["generated_iso"], "then")
        self.assertIsNone(push.prev_card({"generated_iso": "now", "week": 12}, git))

    def test_ats_package_swap_is_one_line(self):
        new = cards()
        new[1]["rows"] = [row("Ole Miss@Oklahoma", "Oklahoma +1.5", "11,904", why="Pool +1.5 vs market -1.5")]
        lines = push.since_lines(new, self.prev())
        self.assertIn("CFP: Auburn @ Ole Miss Auburn +13.5 11,904 → Ole Miss @ Oklahoma Oklahoma +1.5 11,904 "
                      "(Pool +1.5 vs market -1.5)", lines)
