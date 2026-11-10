"""NBA trend radar: role and usage changes, caught before the waiver wire. Pure logic on free reads, no AI.

Sources (each tested from GitHub Actions on 2026-11-03):
- ESPN fantasy's player pool, read once per run through the public 3-Ball league: every player's last 20 game
  logs (minutes, start, box score), season averages, and ESPN-wide % rostered with ESPN's +/-.
- ESPN's NBA injury report (already read for the lineups): status plus a dated note, the citation for every
  injury line here.
stats.nba.com timed out from Actions and from the laptop, cdn.nba.com and Basketball-Reference returned 403,
pbpstats' stat endpoints were slow or 502, and official.nba.com's firewall turns away non-browser clients (its
injury PDFs aren't read), so usage % and with/without-teammate splits are computed here
from ESPN's box scores. Usage is the player's share of his team's shots, free throws and turnovers while he's on
the floor (Basketball-Reference's formula, over the same games).

scan() is league-free: who is rising, whose role is shrinking, who absorbs an injured starter's minutes.
block() turns it into one league's lines: free agents and my bench rising, ranked by the categories I'm losing
or that are close (shq/categories.py), my players losing minutes, and the cited injuries behind them.

One answer per player across the league tab (Q-047). The radar, Lineup moves, Waiver adds and the category chase used to
disagree ("start him" here, "Drop him" two sections down). The rule:
- A player of mine the radar has rising, and not "may fade", is never a drop: block()'s "keep" ids, which
  shq/nba_swaps.py skips (and so the weekly plan, built from the same swaps).
- My shrinking players ("shrink_ids") and anyone on my bench are never "Keep in the lineup" in the chase (shq/categories.py).
- "Start him" for a rising bench player only when today's Lineup moves start him (agree(), after shq/nba_lineup.py has
  run); otherwise "worth a start" / "consider starting him" with the reason there's no move today."""
import json
import time

from . import categories, notify
from . import espn_fantasy as ef
from .common import CACHE, STATE, get_json, iso, load_json, save_json
from .config import LEAGUES, TZ
from .espn_fantasy import NBA_STATS, RATIO
from .status import OUTISH, norm

SOURCE = next(c for c in LEAGUES if c["sport"] == "nba" and not c.get("private"))   # public 3-Ball BB
POOL_FILE, POOL_MAX_AGE = CACHE / "nba_pool.json", 3000         # the pool only changes when games finish
POOL_VERSION = 2                                                # 2: adds ESPN's season projection (shq/nba_values.py)
OWNED = STATE / "nba_owned.json"                                # daily % rostered, for the market signal
KEEP = [str(k) for k in (0, 1, 2, 3, 4, 5, 6, 11, 13, 14, 15, 16, 17, 18, 37, 38, 40, 41)]   # 40 MIN, 41 started

RECENT = 3            # the new-role window: his last 3 games
STALE_DAYS = 10       # a run of games older than this isn't a current role
MIN_JUMP, USG_JUMP = 5, 4
KEY_MIN = 24          # an injured player this big frees minutes worth tracking
BACK_SHARE = 0.5      # played under half his team's earlier games: back from an absence, not a riser
LASTED = 4            # a jump with no injury behind it needs this many straight games, or it "may fade"
PUSH_OWNED = 30       # push a rising free agent in a category I need while he's under this % rostered
PUSH_STRENGTH = 8     # ...and his role jumped this much (strength())
PUSH_HOURS = range(7, 22)
POS = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}
GAMELOG = "https://www.espn.com/nba/player/gamelog/_/id/{}"


# ---------- reads ----------
def fetch_pool(season=SOURCE["season"], league_id=SOURCE["league_id"]):
    """{espn id: compact player} for every NBA player ESPN carries, cached ~50 min."""
    hit = load_json(POOL_FILE)
    if hit and hit.get("season") == season and hit.get("v") == POOL_VERSION and time.time() - hit["t"] < POOL_MAX_AGE:
        return hit["players"]
    filt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]}, "limit": 1000,
                        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                        "filterStatsForTopScoringPeriodIds": {"value": 20, "additionalValue": [f"00{season}", f"10{season}"]}}}
    raw = get_json(ef._url("nba", season, league_id), {"view": "kona_player_info"},
                   headers={"X-Fantasy-Filter": json.dumps(filt)})
    players = {str(e["player"]["id"]): compact(e["player"], season) for e in raw.get("players") or []}
    CACHE.mkdir(exist_ok=True)
    POOL_FILE.write_text(json.dumps({"t": time.time(), "v": POOL_VERSION, "season": season, "players": players}), encoding="utf-8")
    return players


def compact(p, season):
    """Name, team, ownership, season averages, games played, ESPN's season projection (per game) and this season's
    game logs [period, pro team, stats]."""
    pick = lambda st: {k: round(v, 2) for k, v in (st or {}).items() if k in KEEP and v}
    avg = lambda sid: next((s.get("averageStats") for s in p.get("stats") or [] if s.get("id") == sid), None)
    season_avg = avg(f"00{season}")
    games = sorted([s["scoringPeriodId"], s.get("proTeamId"), pick(s.get("stats"))] for s in p.get("stats") or []
                   if s.get("statSplitTypeId") == 5 and s.get("seasonId") == season and (s.get("stats") or {}).get("40"))
    own = p.get("ownership") or {}
    return {"name": p["fullName"], "team": p.get("proTeamId"), "pos": p.get("defaultPositionId"),
            "eligible": p.get("eligibleSlots") or [], "injury": p.get("injuryStatus"),
            "owned": round(own.get("percentOwned") or 0, 1), "change": round(own.get("percentChange") or 0, 1),
            "season": pick(season_avg), "gp": int((season_avg or {}).get("42") or 0),
            "proj": pick(avg(f"10{season}")), "games": games}


def track_ownership(pool, now):
    """Keep one % rostered reading per day (players 0.5–70% owned, 30 days) so the market signal is our own
    measured change, not just ESPN's +/-."""
    hist = load_json(OWNED, {}) or {}
    day = now.astimezone(TZ).date().isoformat()
    if day not in hist:
        hist[day] = {pid: p["owned"] for pid, p in pool.items() if 0.5 <= p["owned"] <= 70}
        keep = sorted(hist)[-30:]
        save_json(OWNED, {d: hist[d] for d in keep})
    return hist


# ---------- league-free scan ----------
def plays(st):
    return st.get("14", 0) + 0.44 * st.get("16", 0) + st.get("11", 0)


def team_games(pool):
    """{(pro team, period): [minutes, plays]} summed over everyone who played: the usage denominators."""
    out = {}
    for p in pool.values():
        for period, team, st in p["games"]:
            t = out.setdefault((team, period), [0.0, 0.0])
            t[0] += st.get("40", 0)
            t[1] += plays(st)
    return out


def window(games, tg, team_count=None):
    """Minutes, usage %, start share over a run of game logs. team_count counts the team's games in the same
    stretch, so games he didn't play count as 0 minutes."""
    n = team_count or len(games)
    mins = sum(st.get("40", 0) for *_, st in games)
    tm = [tg.get((t, d), (0, 0)) for d, t, _ in games]
    tm_min, tm_plays = sum(x[0] for x in tm), sum(x[1] for x in tm)
    usg = 100 * sum(plays(st) for *_, st in games) / mins / (tm_plays / (tm_min / 5)) if mins and tm_plays and tm_min else None
    return {"n": n, "played": len(games), "min": mins / n if n else 0, "usg": usg,
            "gs": sum(st.get("41", 0) for *_, st in games) / n if n else 0}


def role(p, tg, period):
    """His last RECENT games against the games before them this season (same team, a missed game = 0 min).
    None when there's too little to compare or the recent run is stale."""
    games = [g for g in p["games"] if g[1] == p["team"]]
    if len(games) < RECENT or period - games[-1][0] > STALE_DAYS:
        return None
    recent, before = games[-RECENT:], games[:-RECENT]
    moved = max((d for d, t, _ in p["games"] if t != p["team"]), default=0)   # traded: count from his first game here
    team_before = sorted(d for t, d in tg if t == p["team"] and moved < d < recent[0][0])
    if len(team_before) < 3:
        return None
    r, b = window(recent, tg), window(before, tg, len(team_before))
    if b["played"] < 2:
        b["usg"] = None   # one game is no usage baseline
    streak = 0            # his latest games in a row at 3+ minutes over the baseline
    for *_, st in reversed(games):
        if st.get("40", 0) < b["min"] + 3:
            break
        streak += 1
    return {"recent": r, "base": b, "games": recent, "base_days": team_before, "last": games[-1][0],
            "back": b["played"] < BACK_SHARE * b["n"], "streak": streak,
            "dmin": r["min"] - b["min"], "dusg": (r["usg"] - b["usg"]) if r["usg"] is not None and b["usg"] is not None else None,
            "started": r["gs"] >= 2 / 3 and b["gs"] <= 1 / 3, "benched": b["gs"] >= 2 / 3 and r["gs"] <= 1 / 3,
            "up": sum(st.get("40", 0) >= b["min"] + 3 for *_, st in recent),
            "down": sum(st.get("40", 0) <= b["min"] - 3 for *_, st in recent)}


def rising(rl):
    """A bigger role in his last 3 games. Not one when he missed most of the earlier games: that's a player back from
    an absence, whose low baseline is the games he sat (Q-045: those flags held only on paper, at -7 to -11 z a game)."""
    if not rl or rl["back"] or rl["recent"]["min"] < 18:
        return False
    usage = (rl["dusg"] or 0) >= USG_JUMP and rl["dmin"] >= -2
    return (rl["up"] >= 2 and (rl["dmin"] >= MIN_JUMP or rl["started"]) and rl["recent"]["min"] >= 20) or usage


def may_fade(rl, gone):
    """No key teammate's absence behind the jump and fewer than LASTED straight games of it (Q-045 backtest: those
    held 9 of 16, the rest 18 of 26)."""
    return not gone and rl["streak"] < LASTED


def fades(rl, gone, out):
    """The radar text's "may fade": may_fade(), or the teammate whose absence explains the jump is back off
    ESPN's injury report. A rising player of mine who fades can be a drop; one who doesn't is kept (shq/nba_swaps.py)."""
    return may_fade(rl, gone) or bool(gone and gone[0] not in out)


def rank_key(rl, gone, out, fit, games=1):
    """block()'s order for rising players, ascending: a jump caused by a key teammate who is out now (on ESPN's
    injury report) first, then category fit times games left, then the size of the jump."""
    return (0 if set(gone) & set(out) else 1, -fit * max(games, 1), -strength(rl))


def shrinking(rl):
    return bool(rl) and rl["base"]["min"] >= 20 and ((rl["dmin"] <= -MIN_JUMP and rl["down"] >= 2) or rl["benched"])


def strength(rl):
    return rl["dmin"] + 0.8 * max(rl["dusg"] or 0, 0) + 6 * rl["started"]


def key_player(p):
    return (p["season"].get("40") or 0) >= KEY_MIN or (p["season"].get("41") or 0) >= 0.5


def absences(pool, team, periods):
    """Key teammates who played for the team before `periods` and missed every one of them."""
    out = []
    for pid, x in pool.items():
        if x["team"] != team or not key_player(x):
            continue
        played = {d for d, t, _ in x["games"] if t == team}
        if played and min(played) < min(periods) and not played & set(periods):
            out.append(pid)
    return out


def with_without(pool, tg, xid):
    """Teammates' minutes and usage in the team's games without the injured player vs with him (DNP = 0 min).
    [(gain in minutes, teammate id, with-window, without-window)], biggest gains first; [] before he has missed
    a game."""
    x = pool[xid]
    team = x["team"]
    team_days = sorted(d for t, d in tg if t == team)
    played = {d for d, t, _ in x["games"] if t == team}
    without, with_ = [d for d in team_days if d not in played], [d for d in team_days if d in played]
    if not without or len(with_) < 2:
        return []
    last = team_days[-1]
    gains = []
    for pid, y in pool.items():
        if pid == xid or y["team"] != team:
            continue
        mine = [g for g in y["games"] if g[1] == team]
        if not mine or mine[-1][0] != last:   # hurt or out of the rotation now: not the one absorbing it
            continue
        w = window([g for g in mine if g[0] in with_], tg, len(with_))
        wo = window([g for g in mine if g[0] in without], tg, len(without))
        gains.append((wo["min"] - w["min"], pid, w, wo))
    return sorted((g for g in gains if g[0] >= 3 or ((g[3]["usg"] or 0) - (g[2]["usg"] or 0)) >= USG_JUMP),
                  key=lambda g: -g[0])


def scan(pool, report, period, sched):
    """League-free radar: roles for everyone, the injured key players and who absorbs their minutes."""
    tg = team_games(pool)
    roles = {pid: role(p, tg, period) for pid, p in pool.items()}
    out_now = {pid for pid in pool if norm((report.get(pid) or {}).get("status")) in OUTISH}
    injured = [{"id": pid, "gains": with_without(pool, tg, pid)[:3]}
               for pid in sorted(out_now, key=lambda x: -(pool[x]["season"].get("40") or 0))
               if key_player(pool[pid]) and pool[pid]["games"]]
    return {"pool": pool, "tg": tg, "roles": roles, "out": out_now, "injured": injured, "report": report,
            "period": period, "dates": period_dates(sched), "z": z_scales(pool, tg)}


def period_dates(sched):
    days = {}
    for t in sched.values():
        for d, gs in t["games"].items():
            for k, *_ in gs:
                days[d] = min(days.get(d, k), k)
    return {d: k.astimezone(TZ).date() for d, k in days.items()}


def z_scales(pool, tg):
    """Mean and spread per category over rotation players' per-game numbers this season (ratio cats as made
    above the league rate), so category fit is in comparable units."""
    rot = [p["season"] for p in pool.values() if (p["season"].get("40") or 0) >= 20]
    out = {}
    for cat in NBA_STATS:
        if cat in RATIO:
            m, a = (str(x) for x in RATIO[cat])
            rate = sum(s.get(m, 0) for s in rot) / max(sum(s.get(a, 0) for s in rot), 1)
            vals = [s.get(m, 0) - rate * s.get(a, 0) for s in rot]
        else:
            rate, vals = None, [s.get(str(cat), 0) for s in rot]
        if len(vals) > 1:
            mean = sum(vals) / len(vals)
            sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
            out[cat] = (mean, sd, rate)
    return out


def projected(p, rl):
    """Per-game stats at his new minutes: this season's per-minute rates times his recent minutes."""
    mins = sum(st.get("40", 0) for *_, st in p["games"])
    if not mins:
        return {}
    scale = rl["recent"]["min"] / mins
    return {k: sum(st.get(k, 0) for *_, st in p["games"]) * scale for k in KEEP}


def cat_z(sc, cat, per_game):
    mean, sd, rate = sc["z"][cat]
    if cat in RATIO:
        m, a = (str(x) for x in RATIO[cat])
        v = per_game.get(m, 0) - rate * per_game.get(a, 0)
    else:
        v = per_game.get(str(cat), 0)
    return (v - mean) / sd


# ---------- one league ----------
def scan_for(league):
    """The run's scan, shared by both basketball leagues; the ownership history is written once a day."""
    ctx = league.ctx
    if "_radar" not in ctx.__dict__:
        pool = fetch_pool()
        track_ownership(pool, ctx.now)
        ctx._radar = scan(pool, ctx.injury_report("nba"), league.period, league.sched)
    return ctx._radar


def block(league, cats=None):
    """{"rising", "shrinking", "injuries", "basis"} for an NBA league tab; each item {"text", "links", "push"}."""
    if getattr(league, "sport", "nfl") != "nba":
        return None
    sc = scan_for(league)
    pool, roles = sc["pool"], sc["roles"]
    mine = {str(p["id"]): p for p in league.data["roster"]}
    taken = set(mine) | {str(p["id"]) for t in league.data.get("teams") or [] for p in t["roster"]}
    need = needed(league, cats)
    hist = load_json(OWNED, {}) or {}
    rising_items = []
    for pid, rl in roles.items():
        p = pool[pid]
        if not rising(rl) or pid in sc["out"]:
            continue
        where = "fa" if pid not in taken else "bench" if pid in mine and mine[pid]["slot"] == ef.BENCH["nba"][0] else None
        if not where:
            continue
        fit, helps = fit_score(sc, p, rl, need)
        g_now, g_next, b2b = schedule(league, p)
        gone = absences(pool, p["team"], [d for d, *_ in rl["games"]])
        rising_items.append((rank_key(rl, gone, sc["out"], fit, g_now),
                             riser_item(league, sc, pid, rl, where, helps, need, (g_now, g_next, b2b), hist, gone)))
    rising_items.sort(key=lambda t: t[0])
    fas = [i for _, i in rising_items if i["where"] == "fa"][:4]
    bench = [i for _, i in rising_items if i["where"] == "bench"]
    shrink_ids = [pid for pid in mine if pid in pool and shrinking(roles.get(pid)) and pid not in sc["out"]]
    shrink = [shrink_item(league, sc, pid, roles[pid]) for pid in shrink_ids]
    ir = {str(p["id"]) for p in league.data["roster"] if p.get("slot") == ef.BENCH["nba"][1]}
    keep = sorted(pid for pid in mine if pid in pool and pid not in ir and rising(roles.get(pid)) and pid not in sc["out"]
                  and not fades(roles[pid], absences(pool, pool[pid]["team"], [d for d, *_ in roles[pid]["games"]]), sc["out"]))
    injuries = injury_items(league, sc, taken, mine)
    last = max((rl["last"] for rl in roles.values() if rl), default=None)
    return {
        "rising": bench + fas, "shrinking": shrink, "injuries": injuries, "keep": keep, "shrink_ids": shrink_ids,
        "need": [NBA_STATS[c] + f" ({o})" for c, o in need.items()],
        "basis": "ESPN game logs" + (f" through {_day(sc['dates'].get(last))}" if last in sc["dates"] else "")
                 + "; last 3 games vs his earlier games this season (a missed game counts as 0 min); usage % from ESPN box scores"
                 + "; injuries from ESPN's injury report. Ideas only: nothing is sent.",
    }


def needed(league, cats):
    """{stat id: "losing"/"close"} this week from the category table; every category when the week is done."""
    ids = {v: k for k, v in NBA_STATS.items()}
    league_cats = [c for c, rev in (league.data.get("matchup") or {}).get("cats") or [] if not rev and c in NBA_STATS]
    rows = (cats or {}).get("rows") or []
    if not rows or not any(cats.get("games_left") or [0]):
        return {c: "all" for c in league_cats}
    word = {"lose": "losing", "close": "close"}
    return {ids[r["cat"]]: word[r["outlook"]] for r in rows if r["outlook"] in word and ids.get(r["cat"]) in league_cats}


def fit_score(sc, p, rl, need):
    per_game = projected(p, rl)
    zs = {c: cat_z(sc, c, per_game) for c in need if c in sc["z"]}
    helps = [(c, z) for c, z in sorted(zs.items(), key=lambda t: -t[1]) if z >= 0.3]
    return sum(max(z, 0) for z in zs.values()), helps


def schedule(league, p):
    """Games left this matchup, games next week, and back-to-back day pairs across both."""
    team = league.sched.get(p["team"], {}).get("games", {})
    days = list(categories._days_left(league))
    nxt = range(days[-1] + 1, days[-1] + 8) if days else range(0)
    now_games = len(categories._game_days(league, {"pro_team": p["team"]}))
    next_games = sum(len(team.get(d, [])) for d in nxt)
    played = [d for d in list(days) + list(nxt) if team.get(d) and team[d][0][0] > league.ctx.now]
    b2b = [(a, b) for a, b in zip(played, played[1:]) if b == a + 1]
    return now_games, next_games, b2b


def _day(d):
    return f"{d.strftime('%b')} {d.day}" if d else "?"


def team_abbrev(sched, team):
    return (sched.get(team) or {}).get("abbrev") or "FA"


def change_text(pid, p, hist):
    days = sorted(hist)
    old = next((hist[d].get(pid) for d in days[-4:-3]), None) if len(days) >= 4 else None
    if old is not None:
        return f", {p['owned'] - old:+.1f} pts in 3 days"
    return f", ESPN +/- {p['change']:+.1f}" if p.get("change") else ""


def window_text(rl, dates):
    r, b = rl["recent"], rl["base"]
    span = f"{_day(dates.get(rl['games'][0][0]))}–{_day(dates.get(rl['games'][-1][0]))}"
    bits = [f"minutes {b['min']:.0f} → {r['min']:.0f} in his last {r['n']} games ({span}) vs {b['n']} before"
            + (f", played {b['played']} of them" if b["played"] < b["n"] else "")]
    if rl["dusg"] is not None and abs(rl["dusg"]) >= 2:
        bits.append(f"usage {b['usg']:.0f}% → {r['usg']:.0f}%")
    if rl["started"] or rl["benched"]:
        bits.append(f"started {round(r['gs'] * r['n'])} of {r['n']} ({round(b['gs'] * b['n'])} of {b['n']} before)")
    return ", ".join(bits)


def injury_cite(sc, pid):
    """' [ESPN Nov 1: Out, note]' and its link, from ESPN's injury report entry; ('', []) when he isn't on it."""
    e = sc["report"].get(pid)
    if not e:
        return "", []
    when = _day(e["date"].astimezone(TZ)) if e.get("date") else ""
    note = e["note"] if len(e["note"]) <= 90 else e["note"][:90].rsplit(" ", 1)[0] + "…"
    return f" [ESPN {when}: {e['status']}" + (f", {note}" if note else "") + "]", [[f"ESPN {when or 'injury report'}", e["url"]]]


def riser_item(league, sc, pid, rl, where, helps, need, games, hist, gone):
    p, dates = sc["pool"][pid], sc["dates"]
    g_now, g_next, b2b = games
    pos = POS.get(p["pos"], "?")
    tag = "on your bench" if where == "bench" else f"free agent, {p['owned']:.0f}% owned{change_text(pid, p, hist)}"   # agree() adds the verdict
    text = f"{p['name']} ({pos}, {team_abbrev(league.sched, p['team'])}), {tag}: {window_text(rl, dates)}"
    links = [[f"ESPN game log through {_day(dates.get(rl['last']))}", GAMELOG.format(pid)]]
    fade = fades(rl, gone, sc["out"])
    if may_fade(rl, gone):
        run = f" and {rl['streak']} straight game{'s' if rl['streak'] != 1 else ''} of it so far" if rl["streak"] else ""
        text += f"; no teammate's injury behind it{run}, so this may fade"
    if gone:
        x = gone[0]
        cite, more = injury_cite(sc, x)
        if x in sc["out"]:
            text += f", since {sc['pool'][x]['name']} went out{cite}"
            links += more
        else:
            text += f"; {sc['pool'][x]['name']} sat those games but isn't on ESPN's injury report now, so this may fade"
    if helps:
        text += ". Fits " + ", ".join(f"{NBA_STATS[c]}" + (f" ({need[c]})" if need.get(c) not in (None, "all") else "") for c, _ in helps[:3])
    else:
        text += ". Doesn't add much in the categories you need this week"
    sched = f"{g_now} game{'s' if g_now != 1 else ''} left this week, {g_next} next week"
    if b2b:
        a, b = b2b[0]
        sched += f" (back-to-back {dates[a].strftime('%a')}–{dates[b].strftime('%a')})" if a in dates and b in dates else ""
    text += f". {sched}."
    push = (where == "fa" and p["owned"] < PUSH_OWNED and strength(rl) >= PUSH_STRENGTH and g_now > 0
            and any(need.get(c) in ("losing", "close") and z >= 0.5 for c, z in helps))
    who = "your bench" if where == "bench" else f"FA {p['owned']:.0f}%"
    short = (f"{p['name']} ({team_abbrev(league.sched, p['team'])}, {who}): minutes {rl['base']['min']:.0f} → {rl['recent']['min']:.0f}"
             + (f", usage {rl['base']['usg']:.0f}% → {rl['recent']['usg']:.0f}%" if (rl["dusg"] or 0) >= 2 else "")
             + (", now starting" if rl["started"] else "")
             + (f"; fits {', '.join(NBA_STATS[c] for c, _ in helps[:2])}" if helps else "")
             + ("; may fade" if fade else "")
             + f" (ESPN game logs through {_day(dates.get(rl['last']))})")
    return {"text": text, "short": short, "links": links, "where": where, "push": push, "id": pid, "name": p["name"], "fade": fade}


def agree(r, moves, bench, now):
    """Give each rising bench player the same verdict as today's Lineup moves (the ones shown, shq/nba_lineup.py):
    "start him today" only when a move starts him; otherwise why there's no move: no game today, his game has started,
    he's questionable, or his season value doesn't beat a starter who plays today by nba_lineup.MIN_EDGE."""
    if not r:
        return r
    from . import nba_lineup
    from .swap import playable
    starts = {str(m.get("start_key")) for m in moves}
    rows = {str(b.get("key")): b for b in bench}
    for i in r.get("rising") or []:
        if i["where"] != "bench":
            continue
        b = rows.get(i["id"])
        if i["id"] in starts:
            verdict = "start him today (it's in Lineup moves)"
        elif not b:
            verdict = "consider starting him"
        elif not nba_lineup._today(b, now):
            verdict = "worth a start on his next game day (no game today)"
        elif b["started"] or now >= b["kickoff"]:
            verdict = "worth a start next game (today's game has started)"
        elif not playable(b, now):
            verdict = f"consider starting him if he plays ({b['status']} today)"
        else:
            verdict = (f"consider starting him (no lineup move today: his season value doesn't beat a starter who plays "
                       f"today by {nba_lineup.MIN_EDGE:g}+ value/g)")
        i["text"] = i["text"].replace(", on your bench:", f", on your bench, {verdict}:", 1)
        i["verdict"] = verdict
    return r


def shrink_item(league, sc, pid, rl):
    p = sc["pool"][pid]
    text = f"{p['name']} ({POS.get(p['pos'], '?')}, {team_abbrev(league.sched, p['team'])}): {window_text(rl, sc['dates'])}"
    links = [[f"ESPN game log through {_day(sc['dates'].get(rl['last']))}", GAMELOG.format(pid)]]
    back = [y["name"] for x, y in sc["pool"].items() if y["team"] == p["team"] and x != pid and key_player(y) and returned(y, rl)]
    if back:
        text += f", since {back[0]} came back"
    cite, more = injury_cite(sc, pid)
    if cite:   # hurt, not demoted: say so with ESPN's dated note
        text += f"; he's on ESPN's injury report{cite}"
        links += more
    short = (f"{p['name']} ({team_abbrev(league.sched, p['team'])}, yours): minutes {rl['base']['min']:.0f} → {rl['recent']['min']:.0f}"
             + (", lost his starting spot" if rl["benched"] else "") + (f"{cite}" if cite else "")
             + f" (ESPN game logs through {_day(sc['dates'].get(rl['last']))})")
    return {"text": text + ". Check his minutes before you start him over a rising free agent.", "short": short, "links": links}


def returned(y, rl):
    """A key teammate who missed 2+ of the team's earlier games and played every recent one."""
    played = {d for d, t, _ in y["games"] if t == y["team"]}
    return {d for d, *_ in rl["games"]} <= played and len(set(rl["base_days"]) - played) >= 2


def injury_items(league, sc, taken, mine):
    """Injured key players whose minutes go to a free agent or one of my players in this league."""
    out = []
    for inj in sc["injured"]:
        x = sc["pool"][inj["id"]]
        cite, links = injury_cite(sc, inj["id"])
        gains = [g for g in inj["gains"] if g[1] not in taken or g[1] in mine]
        if not gains:
            continue
        who = "; ".join(f"{sc['pool'][pid]['name']} ({'yours' if pid in mine else 'FA'}) {w['min']:.0f} → {wo['min']:.0f} min"
                        + (f", usage {w['usg']:.0f}% → {wo['usg']:.0f}%" if w["usg"] and wo["usg"] else "")
                        for _, pid, w, wo in gains[:2])
        n = gains[0][3]["n"]
        out.append({"text": f"{x['name']} ({team_abbrev(league.sched, x['team'])}) is out{cite}. In {n} game{'s' if n != 1 else ''} "
                            f"without him: {who}.", "links": links})
    return out[:4]


def send_alerts(league, advice):
    """One push per league per day at most, 7am–9pm CT: rising free agents under PUSH_OWNED% whose role jumped and
    who help a category I'm losing or that's close. A player is pushed once per matchup week."""
    if league.ctx.now.astimezone(TZ).hour not in PUSH_HOURS:
        return None
    seen = load_json(notify.ALERTS, {}) or {}
    key = lambda i: f"{league.key}:radar:w{league.week}:{i['id']}"
    new = [i for i in ((advice or {}).get("radar") or {}).get("rising", []) if i.get("push") and key(i) not in seen][:2]
    day = f"{league.key}:radar:{league.ctx.now.astimezone(TZ).date()}"
    if not new or day in seen:
        return None
    title = f"{league.name}: rising free agent{'s' if len(new) > 1 else ''} " + " + ".join(i["name"] for i in new)
    notify.push_once(day, title, "\n\n".join(i["text"] for i in new), priority=3, tags=["chart_with_upwards_trend"])
    seen = load_json(notify.ALERTS, {}) or {}
    save_json(notify.ALERTS, {**seen, **{key(i): iso(league.ctx.now) for i in new}})
    return title


def digest_items(league):
    """Today tab lines: the top two risers and any shrinking role of mine, never urgent."""
    r = getattr(league, "radar", None) or {}
    picks = [i["short"] for i in r.get("rising", [])[:2]] + [i["short"] for i in r.get("shrinking", [])[:1]]
    return [{"league": league.name, "urgent": False, "text": "Radar: " + t} for t in picks]
