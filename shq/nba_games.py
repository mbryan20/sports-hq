"""NBA games grid and streaming plan for a category league. Pure logic on ESPN's pro schedule, no AI.

- Games per NBA team for the rest of this matchup week and all of next week, grouped by count ("3 games: DAL, GS…"),
  with back-to-backs.
- My games left against my opponent's (best lineup each day, from shq/categories.py) and my games next week (same rule:
  each day only as many players count as there are starting spots).
- Streamers: the free agents worth the most over the games left this week (next week once this one is over), on the
  need-weighted value of shq/nba_swaps.py, with their game days. Ideas only: nothing is sent."""
from . import categories, nba_swaps, radar
from .espn_fantasy import BENCH

STREAMERS = 3


def week_days(league):
    """(this week's scoring periods still to tip off, next week's 7 periods)."""
    now = list(categories._days_left(league))
    last = now[-1] if now else league.period - 1
    return now, list(range(last + 1, last + 8))


def team_days(league, team, days):
    """The periods in `days` with a game for this pro team that hasn't tipped off."""
    games = (league.sched.get(team) or {}).get("games") or {}
    return [d for d in days for k, *_ in games.get(d, []) if k > league.ctx.now]


def b2b(days):
    return [(a, b) for a, b in zip(days, days[1:]) if b == a + 1]


def grid(league, days):
    """[[games, [abbrevs]]] most games first, and the teams with a back-to-back in `days`."""
    by_n, b2bs = {}, []
    for tid, t in league.sched.items():
        if not t.get("abbrev") or not tid:
            continue
        ds = team_days(league, tid, days)
        by_n.setdefault(len(ds), []).append(t["abbrev"])
        if b2b(ds):
            b2bs.append(t["abbrev"])
    return [[n, sorted(ts)] for n, ts in sorted(by_n.items(), reverse=True)], sorted(b2bs)


def lineup_games(league, roster, days, slots):
    """Games that count for a roster over `days`: each day at most `slots` healthy players who play."""
    usable = [p for p in roster if p.get("slot") != BENCH["nba"][1] and categories._healthy(league, p)]
    plays = {p["id"]: set(team_days(league, p.get("pro_team"), days)) for p in usable}
    total = 0
    for d in days:
        total += min(slots, sum(1 for p in usable if d in plays[p["id"]]))
    return total


def label_days(league, ds, dates):
    return "/".join(dates[d].strftime("%a")[:2] for d in ds if d in dates)


def span(days, dates):
    have = [dates[d] for d in days if d in dates]
    if not have:
        return ""
    a, b = have[0], have[-1]
    return f"{a.strftime('%a')} {a.strftime('%b')} {a.day}–{b.strftime('%a')} {b.strftime('%b')} {b.day}"


def build(league, cats=None):
    """{"now", "next", "mine", "streamers", "basis"} for an NBA category league tab."""
    if getattr(league, "sport", "nfl") != "nba":
        return None
    now_days, next_days = week_days(league)
    dates = radar.period_dates(league.sched)
    g_now, b_now = grid(league, now_days)
    g_next, b_next = grid(league, next_days)
    slots = sum(v for k, v in (league.data.get("slot_counts") or {}).items() if int(k) not in BENCH["nba"])
    roster = league.data["roster"]
    left = (cats or {}).get("games_left") or [lineup_games(league, roster, now_days, slots), None]
    mine = {"now": left[0], "opp": left[1], "next": lineup_games(league, roster, next_days, slots)}
    out = {
        "now": {"span": span(now_days, dates), "groups": g_now, "b2b": b_now},
        "next": {"span": span(next_days, dates), "groups": g_next, "b2b": b_next},
        "mine": mine, "streamers": streamers(league, cats, now_days, next_days, dates),
        "basis": "Games from ESPN's NBA schedule; yours and theirs count a game only when a starting spot is free that day. Streamers: free agents worth the most over those games, on the categories "
                 "you need this week (the Players page \"Wk\", need-weighted).",
    }
    return out


def streamers(league, cats, now_days, next_days, dates):
    block = getattr(league, "values", None)
    if not block:
        return []
    w = nba_swaps.weights(block, cats)
    horizon = 0 if any(team_days(league, t, now_days) for t in league.sched) else 1
    days = now_days if horizon == 0 else next_days
    when = "this week" if horizon == 0 else "next week"
    need = {r["cat"] for r in (cats or {}).get("rows") or [] if r["outlook"] in ("close", "lose")}
    pool = [p for p in block["players"] if not p["own"] and not p.get("out") and not nba_swaps.dead(p) and p["g"][horizon]]
    best = sorted(pool, key=lambda p: -nba_swaps.worth(p, block, w, horizon))[:STREAMERS]
    tid = {t["abbrev"]: k for k, t in league.sched.items() if t.get("abbrev")}
    out = []
    for p in best:
        ds = team_days(league, tid.get(p["team"]), days)
        helps = [c for c, z in sorted(zip(block["cats"], p["z"]), key=lambda t: (t[0] not in need, -t[1])) if z >= 0.4][:3]
        bb = b2b(ds)
        out.append(f"{p['name']} ({p['pos']}, {p['team']}, {p['pct']:.0f}% rostered): {len(ds)} game{'s' if len(ds) != 1 else ''} "
                   f"{when} ({label_days(league, ds, dates)}{', back-to-back' if bb else ''}), "
                   f"{nba_swaps.worth(p, block, w, horizon):+.1f} {when}"
                   + (f", helps {', '.join(helps)}" if helps else ""))
    return out
