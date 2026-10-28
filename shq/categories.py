"""NBA category matchup for head-to-head category leagues. Pure logic, no AI.

Reads the snapshot's "matchup" block (espn_fantasy.cat_matchup): this week's totals for me and my
opponent, and per-game averages for both rosters and the free agents. Projects the rest of the week
(each day, the best healthy players with a game fill the starting slots), then says per category
whether I'm on course to win, lose or it's close, which of my players have the most left to give in the
close ones, and which free agents would help there."""
from .config import TZ
from .espn_fantasy import BENCH, NBA_STATS, RATIO, SLOT_NAMES
from .status import OUTISH, worst

CLOSE_SHARE = 0.08                                       # counting stats: projected gap within 8%
CLOSE_RATIO = {19: 0.015, 20: 0.03, 21: 0.02, 35: 0.15}  # FG%, FT%, 3P%, A/TO: projected gap within this
NBA_POS = ("PG", "SG", "SF", "PF", "C")


def build(league):
    m = (getattr(league, "data", None) or {}).get("matchup")
    if not m or not m.get("cats") or not _this_week(league):
        return None
    slots = sum(v for k, v in league.data["slot_counts"].items() if int(k) not in BENCH["nba"])
    mine, my_games = _games_left(league, m["my_roster"], slots)
    opp, opp_games = _games_left(league, m["opp_roster"], slots)
    now_mine, now_opp = _totals(m["mine"], []), _totals(m["opp"], [])
    end_mine, end_opp = _totals(m["mine"], mine), _totals(m["opp"], opp)
    done = not (my_games or opp_games)
    rows, close = [], []
    for cat, reverse in m["cats"]:
        if cat not in NBA_STATS:
            continue
        a, b = _value(now_mine, cat, m["mine"]), _value(now_opp, cat, m["opp"])
        ea, eb = (a, b) if done else (_value(end_mine, cat), _value(end_opp, cat))
        outlook = _outlook(cat, reverse, ea, eb, strict=done)
        rows.append({"cat": NBA_STATS[cat], "me": _fmt(cat, a), "opp": _fmt(cat, b),
                     "now": _result(reverse, a, b), "outlook": outlook})
        if outlook == "close":
            close.append((_gap(cat, ea, eb), cat, reverse))
    close = [(cat, reverse) for _, cat, reverse in sorted(close)]
    outlooks = [r["outlook"] for r in rows]
    return {
        "rows": rows,
        "now": _record(r["now"] for r in rows),
        "proj": f"{outlooks.count('win')}-{outlooks.count('lose')}",
        "close": len(close),
        "games_left": [my_games, opp_games],
        "chase": [] if done else [_chase(league, cat, reverse, mine, end_mine) for cat, reverse in close[:3]]
                 or ["No category is within reach either way; nothing to chase."],
        "adds": [] if done else _adds(league, m.get("fa") or [], close, end_mine),
    }


def _this_week(league):
    """A morning laptop snapshot read on Monday before the sync still holds last week's totals."""
    cap = getattr(league, "captured", None)
    return not cap or cap.astimezone(TZ).isocalendar()[:2] == league.ctx.now.astimezone(TZ).isocalendar()[:2]


def _days_left(league):
    return range(league.period, league.period + 6 - league.ctx.now.astimezone(TZ).weekday() + 1)


def _game_days(league, p):
    """Scoring periods left this week with a game for the player's team that hasn't tipped off."""
    games = league.sched.get(p.get("pro_team"), {}).get("games", {})
    return [d for d in _days_left(league) for k, *_ in games.get(d, []) if k > league.ctx.now]


def _healthy(league, p):
    status, _ = worst(("ESPN", p.get("injury")), ("ESPN", league.inj.get(str(p["id"]))))
    return status not in OUTISH


def _games_left(league, roster, slots):
    """[(player, games)] that will count, filling the starting slots each day with the healthy players who
    play that day (ranked by points per game), and the total."""
    usable = [p for p in roster if p.get("slot") != BENCH["nba"][1] and _healthy(league, p)]
    days = {p["id"]: _game_days(league, p) for p in usable}
    counted = dict.fromkeys(days, 0)
    for d in _days_left(league):
        playing = sorted((p for p in usable if d in days[p["id"]]), key=lambda p: -p["avg"].get("0", 0))
        for p in playing[:slots]:
            counted[p["id"]] += 1
    out = [(p, counted[p["id"]]) for p in usable if counted[p["id"]]]
    return out, sum(g for _, g in out)


def _totals(score, players):
    tot = {int(k): v for k, v in score.items()}
    for p, g in players:
        for k, v in p["avg"].items():
            tot[int(k)] = tot.get(int(k), 0) + v * g
    return tot


def _value(tot, cat, score=None):
    if score and str(cat) in score:          # ESPN's own figure for the totals so far
        return score[str(cat)]
    if cat in RATIO:
        made, att = (tot.get(x, 0) for x in RATIO[cat])
        return made / att if att else None
    return tot.get(cat, 0)


def _result(reverse, a, b):
    if a is None or b is None or a == b:
        return "T"
    return "W" if (a > b) != reverse else "L"


def _gap(cat, a, b):
    if a is None or b is None:
        return 0
    return abs(a - b) / CLOSE_RATIO[cat] if cat in RATIO else abs(a - b) / max(CLOSE_SHARE * max(a, b), 1)


def _outlook(cat, reverse, a, b, strict=False):
    if strict:
        return {"W": "win", "L": "lose", "T": "tie"}[_result(reverse, a, b)]
    if _gap(cat, a, b) <= 1:
        return "close"
    return "win" if _result(reverse, a, b) == "W" else "lose"


def _record(results):
    results = list(results)
    w, l, t = (results.count(x) for x in "WLT")
    return f"{w}-{l}-{t}"


def _fmt(cat, v):
    if v is None:
        return "–"
    if cat in RATIO:
        return f"{v:.2f}" if cat == 35 else f"{v:.3f}".lstrip("0")
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def _help(cat, p, games, team_pct=None):
    """How much a player moves the category over his remaining games (ratio cats: made above the team's rate)."""
    if cat in RATIO:
        made, att = (p["avg"].get(str(x), 0) for x in RATIO[cat])
        return (made - (team_pct or 0) * att) * games
    return p["avg"].get(str(cat), 0) * games


def _per_game(cat, p):
    if cat in RATIO:
        made, att = (p["avg"].get(str(x), 0) for x in RATIO[cat])
        return f"{_fmt(cat, made / att)} on {att:.1f} {NBA_STATS[RATIO[cat][1]]}/g" if att else "no attempts"
    return f"{p['avg'].get(str(cat), 0):.1f}/g"


def _chase(league, cat, reverse, mine, end):
    """A close category: my players with the most left to give there over their remaining games."""
    name = NBA_STATS[cat]
    pct = _value(end, cat) if cat in RATIO else None
    ranked = sorted(((_help(cat, p, g, pct), p, g) for p, g in mine), key=lambda t: -t[0])
    who = " and ".join(f"{p['name']} ({g} games, {_per_game(cat, p)})" for v, p, g in ranked[:2] if v > 0)
    if reverse:
        return f"{name} is close: fewer games helps here" + (f"; most of yours come from {who}." if who else ".")
    return f"{name} is close. Keep in the lineup: {who}." if who else f"{name} is close; no one on your roster has much left there."


def _adds(league, fas, close, end):
    """Best free agent for each close category, by what he'd add over his games left this week."""
    out, seen = [], set()
    names = SLOT_NAMES["nba"]
    for cat, reverse in close:
        if reverse:
            continue
        pct = _value(end, cat) if cat in RATIO else None
        cands = [(_help(cat, p, len(_game_days(league, p)), pct), p) for p in fas
                 if p["avg"] and _healthy(league, p) and p["id"] not in seen]
        best = max(cands, key=lambda t: t[0], default=None)
        if not best or best[0] <= 0:
            continue
        p = best[1]
        seen.add(p["id"])
        pos = "/".join(x for x in NBA_POS if x in {names.get(e) for e in p.get("eligible", [])})
        team = league.sched.get(p.get("pro_team"), {}).get("abbrev", "FA")
        out.append(f"For {NBA_STATS[cat]}: {p['name']} ({pos}, {team}), {len(_game_days(league, p))} games left, "
                   f"{_per_game(cat, p)}")
    return out[:3]
