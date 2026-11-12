"""Backtest for the NBA Waiver adds swaps (shq/nba_swaps.py) and streamers (shq/nba_games.py): did the advice pay off?

What the site advised each morning is rebuilt from git history: the first docs/data/lineups.json commit at or after
8am CT each day (both basketball leagues' advice.adds swaps and advice.games.streamers, as shown), with the
docs/data/players.json committed with it (names to ESPN ids, each player's category z-scores, the league's z scale and
waiver-level value that morning). Swap advice starts Nov 6 (before that the adds were a most-owned list with no drop).

Each suggestion is judged over the rest of the fantasy week it was made for (the advice's own "Thu Nov 12–Sun Nov 15"
span; the next week's span when it said "next week") once that week is over, on ESPN's game logs (shq/radar.py's
player pool), in that league's own units: each game's category z-scores on that morning's league scale, weighted by
that morning's category need exactly as the site weighted them, minus a waiver-level player's value, summed over the
games he played (a missed game adds 0, as the site's worth counts an out player). So "+N this week" on the page and the
actual number here are the same kind of number.
- Swaps: actual gain = the add's actual worth minus the drop's (a dead roster spot is 0). Gain per game is that over the
  games the site counted for the add; a hit is a swap whose add out-produced the drop; estimate error is the shown "+N"
  vs the actual gain. The same swap shown on several mornings of a week counts once, at its first morning.
- Streamers: each listed streamer vs the next one in the same list (1 vs 2, 2 vs 3): the edge the order promised
  (their shown "+N" apart) vs what happened, per game of the higher-ranked streamer. Once per week per pair.
Scored suggestions are kept in docs/data/health.json (shq/health.py passes last night's back in), so the sample keeps
growing after the game logs (ESPN keeps each player's last 20) roll past them.

compare_sources() replays the picks with another value source on the same history. trial() is the nightly value-source
trial (shq/health.py section "sources"): the site's values vs DARKO minutes vs shrunk (config.NBA_VALUE_SOURCE,
shq/nba_values.py) on the same mornings (those with a DARKO reading, state/nba_darko.json), finished weeks kept in
health.json; ready_sources() applies the rule to switch one on. Free reads only, no AI.

    py -m shq.nba_advice_backtest [--write]     prints the report; --write saves reviews/<date>-nba-swaps-backtest.md
    py -m shq.nba_advice_backtest --trial       prints the value-source trial"""
import datetime as dt
import re
import sys

from . import espn_fantasy as ef
from . import nba_swaps, radar
from .common import ROOT, now_utc
from .config import LEAGUES, TZ
from .espn_fantasy import NBA_STATS
from . import nba_values
from .nba_values import raw

LINEUPS, PLAYERS = "docs/data/lineups.json", "docs/data/players.json"
MORNING = 8            # the first data commit at or after 8am CT is "what the site advised this morning"
V = 1                  # version of a stored scored item; a change in how they're scored re-scores them
LOG_KEEP = 20          # game logs ESPN's pool keeps per player (radar.fetch_pool): older games roll off
CAT_ID = {name: cid for cid, name in NBA_STATS.items()}
NBA = {c["name"]: c for c in LEAGUES if c["sport"] == "nba"}
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


# ---------- what the site said ----------
def morning_versions(versions, hour=MORNING):
    """{date (CT): (unix time, sha)}: each day's first commit at or after `hour` CT."""
    out = {}
    for t, sha in versions:
        when = dt.datetime.fromtimestamp(t, TZ)
        if when.hour >= hour:
            out.setdefault(when.date(), (t, sha))
    return out


def parse_swap(text):
    """{"drop", "add", "dead", "est", "when", "add_games"} from a Waiver adds line, or None (not a swap)."""
    m = re.search(r"(?:^|; then )[Dd]rop (.+?) \((.*?), add (.+?) \(", text)
    gain = re.search(r"\): \+(\d+(?:\.\d+)?) (this|next) week", text)
    if not m or not gain:
        return None
    games = re.match(r"[^,]*, [^,]*, (\d+) games? (?:this|next) week", text[m.end():])
    return {"drop": m.group(1), "add": m.group(3), "dead": m.group(2).startswith("no NBA team"),
            "est": float(gain.group(1)), "when": f"{gain.group(2)} week", "add_games": int(games.group(1)) if games else None}


def parse_streamer(text):
    """{"name", "games", "est", "when"} from a streamer line, or None."""
    name = text.split(" (", 1)[0]
    games = re.search(r"\): (\d+) games? (this|next) week", text)
    est = re.search(r", ([+-]\d+(?:\.\d+)?) (?:this|next) week", text)
    if not games or not est:
        return None
    return {"name": name, "games": int(games.group(1)), "est": float(est.group(1)), "when": f"{games.group(2)} week"}


def span_dates(span, day):
    """(first, last) date of a "Thu Nov 12–Sun Nov 15" span shown on `day`, or None."""
    m = re.findall(r"([A-Z][a-z]{2}) (\d{1,2})", span or "")
    if len(m) < 2 or m[0][0] not in MONTHS or m[-1][0] not in MONTHS:
        return None
    out = []
    for mon, d in (m[0], m[-1]):
        year = day.year + (1 if MONTHS[mon] < day.month - 6 else 0)      # a Dec morning showing a Jan span
        out.append(dt.date(year, MONTHS[mon], int(d)))
    return tuple(out)


def windows(advice, day):
    """{"this week": (first, last), "next week": (first, last)} the advice meant, from its games grid; without one,
    this week runs from `day` to Sunday."""
    g = advice.get("games") or {}
    sunday = day + dt.timedelta(days=6 - day.weekday())
    now = span_dates((g.get("now") or {}).get("span"), day) or (day, sunday)
    nxt = span_dates((g.get("next") or {}).get("span"), day) or (now[1] + dt.timedelta(days=1), now[1] + dt.timedelta(days=7))
    return {"this week": (max(day, now[0]), now[1]), "next week": nxt}


def name_index(block):
    from .health import name_key
    out = {}
    for p in block.get("players") or []:
        out.setdefault(p["name"], p)
        out.setdefault(name_key(p["name"]), p)
    return out


def find(index, name):
    from .health import name_key
    return index.get(name) or index.get(name_key(name))


def history(lineup_versions=None, player_versions=None, load=None, skip=(), leagues=None):
    """Every morning's NBA advice as the site showed it: [{"day", "league", "block", "cats", "swaps", "streamers",
    "windows", "ir", "dynasty", "unmatched"}], oldest first. Mornings without a players.json yet (before Nov 6) and
    (league, day) pairs in `skip` are left out."""
    from . import health
    load = load or health.git_json
    lineup_versions = lineup_versions if lineup_versions is not None else health.git_versions(LINEUPS)
    player_versions = player_versions if player_versions is not None else health.git_versions(PLAYERS)
    leagues = leagues or list(NBA)
    out = []
    for day, (t, sha) in sorted(morning_versions(lineup_versions).items()):
        names = [n for n in leagues if (n, day.isoformat()) not in set(skip)]
        psha = health.last_before(player_versions, t + 1)
        if not names or not psha:
            continue
        lu, pl = load(sha, LINEUPS), load(psha, PLAYERS)
        for name in names:
            L, block = (lu.get("leagues") or {}).get(name), (pl.get("leagues") or {}).get(name)
            if not L or not block or not block.get("scale"):
                continue
            adv = L.get("advice") or {}
            idx, missing = name_index(block), []
            swaps, streamers = [], []
            for line in adv.get("adds") or []:
                s = parse_swap(line)
                if not s:
                    continue
                a, d = find(idx, s["add"]), None if s["dead"] else find(idx, s["drop"])
                if not a or (not s["dead"] and not d):
                    missing.append(s["add"] if not a else s["drop"])
                    continue
                swaps.append({**s, "add_id": a["id"], "drop_id": d["id"] if d else None})
            for line in (adv.get("games") or {}).get("streamers") or []:
                s = parse_streamer(line)
                p = find(idx, s["name"]) if s else None
                if s and not p:
                    missing.append(s["name"])
                if p:
                    streamers.append({**s, "id": p["id"]})
            ir = {x["name"] for x in (L.get("starters") or []) + (L.get("bench") or []) if x.get("slot") == "IR"}
            out.append({"day": day.isoformat(), "league": name, "block": block, "cats": adv.get("cats") or {},
                        "swaps": swaps, "streamers": streamers, "windows": windows(adv, day), "ir": ir,
                        "dynasty": bool(NBA.get(name, {}).get("dynasty")), "unmatched": missing})
    return out


# ---------- what happened ----------
def periods_in(dates, first, last):
    return {p for p, d in dates.items() if first <= d <= last}


def game_value(st, block, w):
    """One game's need-weighted value above a waiver-level player, on that morning's league scale."""
    v = 0.0
    for i, c in enumerate(block["cats"]):
        mean, sd, rate = block["scale"][c]
        z = (raw(CAT_ID[c], st, rate) - mean) / (sd or 1)
        v += w.get(c, 1.0) * z * (-1 if (block.get("rev") or [False] * len(block["cats"]))[i] else 1)
    return v - block["repl"]


def actual(pool, pid, periods, block, w):
    """(worth over these periods, games he played). A missed game adds nothing. (None, 0) when his logs have rolled
    past the start of these periods (LOG_KEEP games kept), so a missing game can't be told from one he missed."""
    logs = (pool.get(str(pid)) or {}).get("games") or []
    if periods and len(logs) >= LOG_KEEP and min(d for d, *_ in logs) > min(periods):
        return None, 0
    games = [st for d, _, st in logs if d in periods]
    return sum(game_value(st, block, w) for st in games), len(games)


def expected_pg(p, block, w):
    """The site's value per game for him that morning, need-weighted, above a waiver-level player."""
    return sum(w[c] * z for c, z in zip(block["cats"], p["z"])) - block["repl"]


def state(m, when, dates, last_period, today):
    """("done" / "partial" / "pending", periods so far) for a morning's window: done once the week is over and the
    logs reach its last game day."""
    first, last = m["windows"][when]
    periods = periods_in(dates, first, last)
    so_far = {p for p in periods if p <= last_period and dates[p] < today}
    if last < today and max(periods, default=0) <= last_period:
        return "done", periods
    return ("partial" if so_far else "pending"), so_far


def score(morning, pool, dates, last_period, today, partial=False):
    """Scored swaps and streamer pairs of one morning: ([swap items], [pair items], pending count, count lost to
    rolled-off logs). With partial,
    unfinished weeks are scored on the games so far (marked "partial"; never stored or judged)."""
    block, by_id = morning["block"], {p["id"]: p for p in morning["block"]["players"]}
    w = nba_swaps.weights(block, morning["cats"])
    hz = lambda when: 0 if when == "this week" else 1
    swaps, pairs, pending = [], [], 0
    lost = 0                                             # logs rolled past: never scorable
    base = {"v": V, "league": morning["league"], "day": morning["day"]}

    def ready(when):
        st, periods = state(morning, when, dates, last_period, today)
        return (periods, st) if st == "done" or (partial and st == "partial") else (None, st)

    def who(pid, periods, when):
        if not pid:
            return {"actual": 0.0, "played": 0, "exp_games": 0, "exp_pg": 0.0}
        p = by_id.get(pid) or {}
        a, n = actual(pool, pid, periods, block, w)
        if a is None:
            return None
        return {"actual": round(a, 2), "played": n, "exp_games": (p.get("g") or [0, 0])[hz(when)],
                "exp_pg": round(expected_pg(p, block, w), 2) if p else None}

    for s in morning["swaps"]:
        periods, st = ready(s["when"])
        if periods is None:
            pending += 1
            continue
        add, drop = who(s["add_id"], periods, s["when"]), who(s["drop_id"], periods, s["when"])
        if add is None or drop is None:
            lost += 1
            continue
        gain = add["actual"] - drop["actual"]
        games = s["add_games"] or add["exp_games"] or 1
        swaps.append({**base, "week": morning["windows"][s["when"]][1].isoformat(), "partial": st != "done",
                      "key": f"{morning['league']}|{morning['windows'][s['when']][1]}|{s['drop_id'] or s['drop']}|{s['add_id']}",
                      "drop": s["drop"], "add": s["add"], "dead": s["dead"], "when": s["when"], "est": s["est"],
                      "add_games": games, "add_stats": add, "drop_stats": drop, "gain": round(gain, 2),
                      "gain_pg": round(gain / games, 2), "hit": gain > 0, "err": round(gain - s["est"], 2)})
    st_list = morning["streamers"]
    for hi, lo in zip(st_list, st_list[1:]):
        periods, st = ready(hi["when"])
        if periods is None:
            pending += 1
            continue
        a, b = who(hi["id"], periods, hi["when"]), who(lo["id"], periods, lo["when"])
        if a is None or b is None:
            lost += 1
            continue
        edge = a["actual"] - b["actual"]
        pairs.append({**base, "week": morning["windows"][hi["when"]][1].isoformat(), "partial": st != "done",
                      "key": f"{morning['league']}|{morning['windows'][hi['when']][1]}|{hi['id']}|{lo['id']}",
                      "pick": hi["name"], "next": lo["name"], "rank": st_list.index(hi) + 1, "when": hi["when"],
                      "est_edge": round(hi["est"] - lo["est"], 2), "pick_stats": a, "next_stats": b,
                      "edge": round(edge, 2), "edge_pg": round(edge / max(hi["games"], 1), 2), "hit": edge > 0})
    return swaps, pairs, pending, lost


def run(hist, pool, dates, today, previous=None, partial=False):
    """Score every morning in `hist` (history()) whose week is over, keeping `previous` stored items (last night's
    health.json details) as they were. {"swaps", "streamers": [items, each once at its first morning],
    "partial": {...same, unfinished weeks} (only with partial), "pending", "done": ["league|day" fully scored],
    "unmatched": [names the players file didn't have]}."""
    last_period = max((d for p in pool.values() for d, *_ in p.get("games") or []), default=0)
    prev = previous or {}
    keep = lambda xs: [x for x in xs or [] if x.get("v") == V]
    out = {"swaps": keep(prev.get("swaps")), "streamers": keep(prev.get("streamers")), "pending": 0, "lost": 0,
           "done": list(prev.get("done") or []) if prev.get("v") == V else [], "unmatched": [],
           "partial": {"swaps": [], "streamers": []}}
    seen = {x["key"] for x in out["swaps"] + out["streamers"]}
    for m in hist:
        swaps, pairs, pending, lost = score(m, pool, dates, last_period, today, partial)
        out["pending"] += pending
        out["lost"] += lost
        out["unmatched"] += m["unmatched"]
        for kind, items in (("swaps", swaps), ("streamers", pairs)):
            for x in items:
                if x["key"] in seen:
                    continue
                seen.add(x["key"])
                (out["partial"][kind] if x["partial"] else out[kind]).append(x)
        if not pending and not any(x["partial"] for x in swaps + pairs):
            key = f"{m['league']}|{m['day']}"
            if key not in out["done"]:
                out["done"].append(key)
    out["v"] = V
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def r2(x):
    return round(x, 2) if x is not None else None


def per_game(stats):
    """(expected value per game, actual per game he played, games played / games expected) over a list of player stats."""
    stats = [x for x in stats if x and x.get("exp_pg") is not None]
    played, exp = sum(x["played"] for x in stats), sum(x["exp_games"] for x in stats)
    return (r2(mean([x["exp_pg"] for x in stats])), r2(sum(x["actual"] for x in stats) / played) if played else None,
            r2(played / exp) if exp else None)


def summarize(swaps, pairs):
    sw = {"n": len(swaps), "gain": r2(mean([x["gain_pg"] for x in swaps])), "gain_total": r2(mean([x["gain"] for x in swaps])),
          "hits": sum(x["hit"] for x in swaps), "hit_rate": r2(mean([float(x["hit"]) for x in swaps])),
          "est": r2(mean([x["est"] for x in swaps])), "est_err": r2(mean([abs(x["err"]) for x in swaps])),
          "est_bias": r2(mean([x["err"] for x in swaps])), "dead": sum(x["dead"] for x in swaps),
          # where the miss comes from: [expected per game, actual per game played, share of expected games played]
          "adds": per_game([x["add_stats"] for x in swaps]), "drops": per_game([x["drop_stats"] for x in swaps if not x["dead"]])}
    st = {"n": len(pairs), "edge": r2(mean([x["edge_pg"] for x in pairs])), "edge_total": r2(mean([x["edge"] for x in pairs])),
          "hits": sum(x["hit"] for x in pairs), "hit_rate": r2(mean([float(x["hit"]) for x in pairs])),
          "est_edge": r2(mean([x["est_edge"] for x in pairs])),
          "picks": per_game([x["pick_stats"] for x in pairs if x["rank"] == 1])}
    return {"swaps": sw, "streamers": st}


def summary(res):
    """The numbers model health tracks, overall and per fantasy week (by the week's last day)."""
    out = summarize(res["swaps"], res["streamers"])
    weeks = sorted({x["week"] for x in res["swaps"] + res["streamers"]})
    out["weeks"] = {w: summarize([x for x in res["swaps"] if x["week"] == w], [x for x in res["streamers"] if x["week"] == w])
                    for w in weeks}
    out["pending"], out["lost"] = res["pending"], res.get("lost", 0)
    out["unmatched"] = sorted(set(res["unmatched"]))
    return out


# ---------- another value source on the same history (the DARKO-minutes gate) ----------
def site_source(p, morning):
    """The site's own value: the category z-scores players.json showed that morning."""
    return p["z"]


def picks(morning, source):
    """The streamers and swaps the site's rules pick that morning when players are valued by `source(player, morning)`
    (per-category z-scores in the block's order). Same rules as shq/nba_games.py and shq/nba_swaps.py (need weights,
    MIN_GAIN, SEASON_SLACK, the dynasty keeps, no IR drop, no out add), except the two that need that morning's live
    state: the radar's protected risers and today's Lineup moves. {"streamers": [(id, when)], "swaps": [(drop id, add id, when)]}"""
    block = morning["block"]
    w = nba_swaps.weights(block, morning["cats"])
    val = {p["id"]: {**p, "z": list(source(p, morning))} for p in block["players"]}
    mine = [p for p in val.values() if p["own"] == "me" and p["name"] not in morning["ir"]]
    hz = 0 if any(p["g"][0] for p in mine) else 1
    when = "this week" if hz == 0 else "next week"
    worth = lambda p: nba_swaps.worth(p, block, w, hz)
    fas = [p for p in val.values() if not p["own"] and not p.get("out") and not nba_swaps.dead(p)]
    streamers = sorted((p for p in fas if p["g"][hz]), key=lambda p: -worth(p))[:3]
    ok = lambda p: not morning["dynasty"] or (p["pct"] < nba_swaps.DYNASTY_KEEP and (p.get("age") or 99) >= nba_swaps.DYNASTY_YOUNG)
    drops = [p for p in mine if nba_swaps.dead(p) or ok(p)]
    v = lambda p: sum(p["z"])
    pairs = []
    for d in drops:
        wd = 0.0 if nba_swaps.dead(d) else worth(d)
        for a in fas:
            gain = worth(a) - wd
            if not nba_swaps.dead(d) and (gain < nba_swaps.MIN_GAIN or v(a) < v(d) - nba_swaps.SEASON_SLACK):
                continue
            pairs.append((not nba_swaps.dead(d), -gain, d["id"], a["id"]))
    pairs.sort()
    swaps, used, est = [], set(), {}
    for _, g, d, a in pairs:
        if d in used or a in used:
            continue
        used |= {d, a}
        swaps.append((d, a, when))
        est[(d, a)] = -g
        if len(swaps) == nba_swaps.MAX_SWAPS:
            break
    return {"streamers": [(p["id"], when) for p in streamers], "swaps": swaps, "est": est}


def compare_sources(hist, pool, dates, today, sources):
    """Replay each finished morning's picks under every value source in `sources` ({name: fn(player, morning) -> z
    list}; the first is the reference, normally site_source) and score them on what happened, the same way as
    run(). Returns {"weeks": {week: {source: {"stream": actual worth per game of its top 3 streamers, "swap": actual gain
    per add game of its swaps, "n_stream", "n_swap"}}}, "overall": {...same over all weeks}, "diff": {week: {source:
    its stream/swap minus the reference's}}, "match" / "match_swaps": share of the reference's replayed streamers / swaps
    the site really showed (a check that the replay is faithful)}. Each source also has "err" / "bias": its swaps' own
    "+N" (the gain it estimated) vs what happened, average miss and average (actual - estimate).
    Each pick counts once a week, at its first morning, as in run()."""
    last_period = max((d for p in pool.values() for d, *_ in p.get("games") or []), default=0)
    names = list(sources)
    got = {n: {"stream": {}, "swap": {}, "err": {}, "bias": {}} for n in names}   # {source: {kind: {key: (week, value)}}}
    shown = matched = shown_sw = matched_sw = 0
    for m in hist:
        block = m["block"]
        w = nba_swaps.weights(block, m["cats"])
        g = {p["id"]: p for p in block["players"]}
        for n in names:
            pk = picks(m, sources[n])
            for pid, when in pk["streamers"]:
                st, periods = state(m, when, dates, last_period, today)
                if st != "done":
                    continue
                week = m["windows"][when][1].isoformat()
                games = g[pid]["g"][0 if when == "this week" else 1] or 1
                a = actual(pool, pid, periods, block, w)[0]
                if a is not None:
                    got[n]["stream"].setdefault(f"{m['league']}|{week}|{pid}", (week, a / games))
                if n == names[0]:
                    shown += 1
                    matched += pid in {s["id"] for s in m["streamers"]}
            for d, a, when in pk["swaps"]:
                st, periods = state(m, when, dates, last_period, today)
                if st != "done":
                    continue
                week = m["windows"][when][1].isoformat()
                if n == names[0]:
                    shown_sw += 1
                    matched_sw += (d, a) in {(s["drop_id"], s["add_id"]) for s in m["swaps"]}
                va = actual(pool, a, periods, block, w)[0]
                vd = 0.0 if nba_swaps.dead(g[d]) else actual(pool, d, periods, block, w)[0]
                if va is None or vd is None:
                    continue
                games = g[a]["g"][0 if when == "this week" else 1] or 1
                k = f"{m['league']}|{week}|{d}|{a}"
                if k not in got[n]["swap"]:
                    got[n]["swap"][k] = (week, (va - vd) / games)
                    miss = (va - vd) - pk["est"][(d, a)]
                    got[n]["err"][k], got[n]["bias"][k] = (week, abs(miss)), (week, miss)

    def agg(n, week=None):
        vals = {k: [v for w_, v in got[n][k].values() if week is None or w_ == week] for k in got[n]}
        return {"stream": r2(mean(vals["stream"])), "swap": r2(mean(vals["swap"])),
                "n_stream": len(vals["stream"]), "n_swap": len(vals["swap"]),
                "err": r2(mean(vals["err"])), "bias": r2(mean(vals["bias"]))}
    weeks = sorted({w_ for n in names for k in ("stream", "swap") for w_, _ in got[n][k].values()})
    out = {"weeks": {wk: {n: agg(n, wk) for n in names} for wk in weeks}, "overall": {n: agg(n) for n in names},
           "match": r2(matched / shown) if shown else None, "match_swaps": r2(matched_sw / shown_sw) if shown_sw else None}
    sub = lambda a, b: r2(a - b) if a is not None and b is not None else None
    out["diff"] = {wk: {n: {k: sub(out["weeks"][wk][n][k], out["weeks"][wk][names[0]][k]) for k in ("stream", "swap", "err")}
                        for n in names[1:]} for wk in weeks}
    return out


def compare(sources, today=None):
    """compare_sources() on the full history from free reads, e.g. compare({"site": site_source, "darko": darko_z})."""
    today = today or now_utc().astimezone(TZ).date()
    pool, dates = inputs()
    return compare_sources(history(), pool, dates, today, sources)


# ---------- the value-source trial (site vs DARKO minutes vs shrunk) ----------
TRIAL_V = 1            # version of the stored trial weeks; a change in how they're scored re-scores them
GATE_WEEKS, GATE_N = 2, 20     # the rule: 2+ complete weeks, 20+ of the source's swaps judged


def scale_rows(block):
    """[(mean, sd, sign)] per category on a morning's league scale (players.json "scale" and "rev")."""
    rev = block.get("rev") or [False] * len(block["cats"])
    return [(block["scale"][c][0], block["scale"][c][1], -1 if r else 1) for c, r in zip(block["cats"], rev)]


def darko_source(days):
    """Value source "darko_minutes" on a past morning: that morning's minutes factor (state/nba_darko.json "days")."""
    def fn(p, morning):
        f = ((days.get(morning["day"]) or {}).get("m") or {}).get(str(p["id"]))
        return p["z"] if f is None else nba_values.minutes_z(p["z"], scale_rows(morning["block"]), f)
    return fn


def shrunk_source(pool):
    """Value source "shrunk" on a past morning: a season-valued player's z pulled toward his ESPN projection's z on that
    morning's scale. The projection is the pool's (tonight's ESPN season projection, not that morning's)."""
    def fn(p, morning):
        proj = (pool.get(str(p["id"])) or {}).get("proj") or {}
        if p.get("src") != "season" or not proj:
            return p["z"]
        block = morning["block"]
        zp = [s * (raw(CAT_ID[c], proj, block["scale"][c][2]) - mean) / (sd or 1)
              for c, (mean, sd, s) in zip(block["cats"], scale_rows(block))]
        return nba_values.shrunk_z(p["z"], zp, p.get("gp") or 0)
    return fn


def pooled(rows, key):
    """A per-week number pooled over weeks, weighted by each week's swaps."""
    xs = [(r[key], r["n_swap"]) for r in rows if r.get(key) is not None and r.get("n_swap")]
    n = sum(w for _, w in xs)
    return r2(sum(x * w for x, w in xs) / n) if n else None


def ready_sources(weeks, ref="site"):
    """The rule, per trial source over the stored complete weeks: {source: {"weeks", "n", "gain", "err", "ref_gain",
    "ref_err", "ready"}}. Ready = GATE_WEEKS+ complete weeks with its swaps judged, GATE_N+ of them, and over those weeks
    a higher swap gain per add game AND a lower estimate miss than the site's (both pooled by swaps)."""
    out = {}
    names = sorted({s for wk in weeks.values() for s in wk if s != ref})
    for s in names:
        both = [wk for wk in sorted(weeks) if (weeks[wk].get(s) or {}).get("n_swap") and (weeks[wk].get(ref) or {}).get("n_swap")]
        mine, theirs = [weeks[wk][s] for wk in both], [weeks[wk][ref] for wk in both]
        g, e, rg, re_ = pooled(mine, "swap"), pooled(mine, "err"), pooled(theirs, "swap"), pooled(theirs, "err")
        n = sum(x["n_swap"] for x in mine)
        ok = (len(both) >= GATE_WEEKS and n >= GATE_N and None not in (g, e, rg, re_) and g > rg and e < re_)
        out[s] = {"weeks": len(both), "n": n, "gain": g, "err": e, "ref_gain": rg, "ref_err": re_, "ready": ok}
    return out


def trial(previous=None, hist=None, pool=None, dates=None, today=None, days=None):
    """The nightly value-source trial: the site's values, DARKO minutes and shrunk, replayed on the same mornings (every
    morning with a DARKO reading) and scored as compare_sources() does. Complete weeks are stored (`previous`: last
    night's result) and stand once stored. {"v", "weeks": {week: {source: ...}}, "diff", "gate", "ready", "mornings",
    "first", "match", "match_swaps", "lag"}."""
    from . import darko
    today = today or now_utc().astimezone(TZ).date()
    if pool is None or dates is None:
        pool, dates = inputs()
    days = days if days is not None else (darko.load().get("days") or {})
    if hist is None:                    # only the mornings with a DARKO reading are read from git
        from . import health
        on = lambda t: dt.datetime.fromtimestamp(t, TZ).date().isoformat() in days
        hist = history([(t, sha) for t, sha in health.git_versions(LINEUPS) if on(t)])
    hist = [m for m in hist if m["day"] in days]
    prev = previous if (previous or {}).get("v") == TRIAL_V else {}
    cmp = compare_sources(hist, pool, dates, today, {"site": site_source, "darko_minutes": darko_source(days),
                                                     "shrunk": shrunk_source(pool)})
    weeks = {**cmp["weeks"], **(prev.get("weeks") or {})}       # only finished weeks are ever scored; stored ones stand
    sub = lambda a, b: r2(a - b) if a is not None and b is not None else None
    diff = {wk: {s: {k: sub(x[s][k], x["site"][k]) for k in ("stream", "swap", "err")} for s in x if s != "site"}
            for wk, x in sorted(weeks.items())}
    gate = ready_sources(weeks)
    lag = [(dt.date.fromisoformat(d) - dt.date.fromisoformat(days[d]["asof"])).days for d in days
           if days[d].get("asof") and days[d].get("how") == "live"]
    return {"v": TRIAL_V, "weeks": dict(sorted(weeks.items())), "diff": diff, "gate": gate,
            "ready": [s for s, g in gate.items() if g["ready"]], "mornings": len(hist),
            "first": min(days) if days else None, "match": cmp["match"], "match_swaps": cmp["match_swaps"],
            "lag": r2(mean(lag)) if lag else None}


# ---------- runs ----------
def inputs():
    """(ESPN player pool with game logs, {scoring period: date}) from free reads."""
    pool = radar.fetch_pool()
    return pool, radar.period_dates(ef.pro_schedule("nba", radar.SOURCE["season"]))


def health(previous=None, hist=None, pool=None, dates=None, today=None):
    """The nightly check: score what's new since last night's stored items. Returns run()'s result plus "summary"."""
    previous = previous if (previous or {}).get("v") == V else None
    today = today or now_utc().astimezone(TZ).date()
    if pool is None or dates is None:
        pool, dates = inputs()
    skip = [tuple(k.split("|")) for k in (previous or {}).get("done") or []]
    hist = hist if hist is not None else history(skip=skip)
    res = run(hist, pool, dates, today, previous)
    res.pop("partial", None)
    return {**res, "summary": summary(res)}


def fmt(x, pct=False):
    if x is None:
        return "–"
    return f"{x:.0%}" if pct else f"{x:+.2f}"


def report(res, today):
    s = summary(res)
    sw, st = s["swaps"], s["streamers"]
    ps = summarize(res["partial"]["swaps"], res["partial"]["streamers"])
    lines = [
        f"# NBA swaps and streamers backtest ({today})", "",
        "What the site advised each morning (first data commit from 8am CT; docs/data/lineups.json history, both basketball "
        "leagues), judged over the rest of the fantasy week it was for on ESPN's game logs, in the league's own units "
        "(category z-scores on that morning's scale, need-weighted as the site weighted them, above a waiver-level player; "
        "a missed game adds 0). Same swap or streamer pair on several mornings of a week: counted once, at its first morning.", "",
        "## Finished weeks", "",
        f"- Swaps: n={sw['n']} ({sw['dead']} replacing a dead roster spot). Actual gain {fmt(sw['gain'])} per game of the add "
        f"({fmt(sw['gain_total'])} over the week); the add beat the drop in {sw['hits']} of {sw['n']} ({fmt(sw['hit_rate'], True)}).",
        f"- Swap estimates: shown {fmt(sw['est'])} on average; actual minus shown {fmt(sw['est_bias'])} "
        f"(average miss {sw['est_err'] if sw['est_err'] is not None else '–'}).",
        f"- Where the swap miss comes from: adds were valued {fmt(sw['adds'][0])} per game and produced {fmt(sw['adds'][1])} per game "
        f"played ({fmt(sw['adds'][2], True)} of their expected games played); drops (not dead spots) {fmt(sw['drops'][0])} → "
        f"{fmt(sw['drops'][1])} ({fmt(sw['drops'][2], True)}). Top-listed streamers {fmt(st['picks'][0])} → {fmt(st['picks'][1])} "
        f"({fmt(st['picks'][2], True)}).",
        f"- Streamers vs the next one listed: n={st['n']} pairs, edge {fmt(st['edge'])} per game of the higher-ranked "
        f"({fmt(st['edge_total'])} over the week, {fmt(st['est_edge'])} promised); the higher-ranked did better in "
        f"{st['hits']} of {st['n']} ({fmt(st['hit_rate'], True)}).",
    ]
    for wk, x in s["weeks"].items():
        lines.append(f"- Week ending {wk}: swaps n={x['swaps']['n']} gain {fmt(x['swaps']['gain'])}/g, hit "
                     f"{fmt(x['swaps']['hit_rate'], True)}, miss {x['swaps']['est_err']}; streamer pairs n={x['streamers']['n']} "
                     f"edge {fmt(x['streamers']['edge'])}/g.")
    if ps["swaps"]["n"] or ps["streamers"]["n"]:
        lines += ["", "## This week so far (provisional, games through last night)", "",
                  f"- Swaps n={ps['swaps']['n']}: gain {fmt(ps['swaps']['gain'])} per game of the add so far, add ahead in "
                  f"{ps['swaps']['hits']} of {ps['swaps']['n']}.",
                  f"- Streamer pairs n={ps['streamers']['n']}: edge {fmt(ps['streamers']['edge'])}/g, higher-ranked ahead in "
                  f"{ps['streamers']['hits']} of {ps['streamers']['n']}."]
    lines += ["", "## Swaps", "",
              "| Morning | League | Drop → add | Shown | Actual (add − drop) | Add: games, value/g expected → actual | Drop: games, value/g expected → actual |",
              "|---|---|---|---|---|---|---|"]
    pg = lambda x: f"{x['actual'] / x['played']:+.1f}" if x["played"] else "–"
    for x in sorted(res["swaps"] + res["partial"]["swaps"], key=lambda x: (x["day"], x["league"])):
        a, d = x["add_stats"], x["drop_stats"]
        lines.append(f"| {x['day']}{' (so far)' if x['partial'] else ''} | {x['league']} | {x['drop']} → {x['add']} | +{x['est']:.1f} | "
                     f"{x['gain']:+.1f} ({a['actual']:+.1f} − {d['actual']:+.1f}) | {a['played']} of {a['exp_games']}, "
                     f"{a['exp_pg']:+.1f} → {pg(a)} | "
                     + ("dead spot |" if x["dead"] else f"{d['played']} of {d['exp_games']}, {d['exp_pg']:+.1f} → {pg(d)} |"))
    lines += ["", "## Streamer pairs", "", "| Morning | League | #k vs #k+1 | Promised | Actual |", "|---|---|---|---|---|"]
    for x in sorted(res["streamers"] + res["partial"]["streamers"], key=lambda x: (x["day"], x["league"], x["rank"])):
        lines.append(f"| {x['day']}{' (so far)' if x['partial'] else ''} | {x['league']} | #{x['rank']} {x['pick']} vs {x['next']} | "
                     f"{x['est_edge']:+.1f} | {x['edge']:+.1f} |")
    lines += ["", "## Caveats", "",
              "- Small sample: swap advice started Nov 6 (before that the adds were the most-owned free agents, no drop).",
              "- A missed game counts 0 for the player (as the site's worth counts an out player), so availability is part "
              "of the result.",
              "- Judged on what the site showed, not on whether the move was made."]
    if s["unmatched"]:
        lines.append(f"- Not matched to the players file (left out): {', '.join(s['unmatched'])}.")
    return "\n".join(lines) + "\n"


def main(argv):
    today = now_utc().astimezone(TZ).date()
    pool, dates = inputs()
    hist = history()
    res = run(hist, pool, dates, today, partial=True)
    text = report(res, today)
    cmp = compare_sources(hist, pool, dates, today, {"site": site_source})
    text += (f"\nReplay check: the site's own values, replayed by compare_sources(), pick {fmt(cmp['match'], True)} of the "
             f"streamers and {fmt(cmp['match_swaps'], True)} of the swaps the site showed (the replay skips the radar's protected "
             f"risers and today's Lineup moves); their top 3 streamers {fmt(cmp['overall']['site']['stream'])} per game, swaps "
             f"{fmt(cmp['overall']['site']['swap'])} per add game (n={cmp['overall']['site']['n_stream']} / "
             f"{cmp['overall']['site']['n_swap']}).\n")
    if "--trial" in argv:
        from .health import trial_notes
        t = trial(pool=pool, dates=dates, today=today, hist=hist)
        print("\n".join(trial_notes(t)))
        return
    if "--write" in argv:
        path = ROOT / "reviews" / f"{today}-nba-swaps-backtest.md"
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path}")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
