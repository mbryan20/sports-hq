"""NBA category value for every player in a category league. Pure logic on free reads, no AI.

Source: the trend radar's ESPN player pool (shq/radar.py fetch_pool: ~1,000 players, read once per run through the
public 3-Ball league), so rostered players and free agents in both basketball leagues are valued the same way.
Per-game stats are this season's averages once a player has MIN_GAMES games, ESPN's season projection before that
(each player says which).

Value per game: each of the league's own scoring categories as a z-score against the players a league this size
rosters (teams x roster spots), summed. Ratio categories (FG%, FT%, 3P%, A/TO) count made above that group's rate
times attempts, so a good shooter on many attempts helps more than one on few. Reversed categories (TO) count negative.
Rank is by that value across the whole pool.

This week: (value per game - a waiver-level player's) x games left this matchup that haven't tipped off, and 0 while
he's out on ESPN's injury report. A waiver-level player is the one ranked just past what the league rosters.

Value source (config.NBA_VALUE_SOURCE, a trial switch; "site" = all of the above, unchanged):
- "darko_minutes": each player's line rescaled to DARKO's projected minutes (shq/darko.py: his minutes factor, clamped
  to M_RANGE), per-minute production kept. On the z scale that is z' = s(m(mean + sd s z) - mean)/sd per category.
- "shrunk": a player valued on this season's games has each category's z pulled toward his ESPN season projection's z
  by games played: w = gp / (gp + SHRINK_K).
Either way the league's z scale and waiver level stay the site's (as the backtest replays them); only players' values
and so the order change. Model health compares the three nightly (shq/nba_advice_backtest.py trial())."""
import json
import traceback
from pathlib import Path

from . import categories, config, nba_ages, radar
from .common import load_json
from .config import TZ
from .espn_fantasy import NBA_STATS, RATIO, SLOT_NAMES
from .status import espn_word, play_chance

MIN_GAMES = 5          # games before this season's averages replace ESPN's projection
DEFAULT_CATS = [[0, False], [1, False], [2, False], [3, False], [6, False], [17, False], [19, False], [20, False]]
POS = ("PG", "SG", "SF", "PF", "C")
KEEP = 300             # players written per league besides the ones on a roster
SOURCES = ("site", "darko_minutes", "shrunk")
M_RANGE = (0.5, 1.75)  # DARKO minutes factor clamp: a 5-minute sample doesn't triple a player's value
SHRINK_K = 10          # games of ESPN's projection a season's average is shrunk toward (not tuned on the backtest)


def per_game(p):
    """(per-game stats, source, games played): this season's averages from MIN_GAMES games, else ESPN's projection."""
    season, proj, gp = p.get("season") or {}, p.get("proj") or {}, p.get("gp") or len(p.get("games") or [])
    if gp >= MIN_GAMES or (season and not proj):
        return season, "season", gp
    return proj, "proj", gp


def league_cats(league):
    """[(stat id, reversed)] the league scores, from the snapshot; the usual 8 categories if it has none."""
    data = league.data
    cats = (data.get("matchup") or {}).get("cats") or data.get("cats") or DEFAULT_CATS
    return [(int(c), bool(r)) for c, r in cats if int(c) in NBA_STATS]


def raw(cat, st, rate=None):
    """A category's per-game number on the z scale: counting stats as is, ratio cats as made above the rate."""
    if cat in RATIO:
        made, att = (st.get(str(x), 0) for x in RATIO[cat])
        return made - (rate or 0) * att
    return st.get(str(cat), 0)


def scales(stats, cats):
    """{cat: (mean, sd, rate)} over a group of per-game stat lines."""
    out = {}
    for cat, _ in cats:
        rate = None
        if cat in RATIO:
            m, a = (str(x) for x in RATIO[cat])
            rate = sum(s.get(m, 0) for s in stats) / max(sum(s.get(a, 0) for s in stats), 1e-9)
        vals = [raw(cat, s, rate) for s in stats]
        mean = sum(vals) / max(len(vals), 1)
        sd = (sum((v - mean) ** 2 for v in vals) / max(len(vals), 1)) ** 0.5 or 1
        out[cat] = (mean, sd, rate)
    return out


def zs(st, cats, sc):
    return [((raw(c, st, sc[c][2]) - sc[c][0]) / sc[c][1]) * (-1 if rev else 1) for c, rev in cats]


def value_pool(lines, cats, n):
    """{id: (value, [z per cat])}: z-scores against everyone first, then against the top n by that first pass."""
    ids = list(lines)
    first = scales([lines[i] for i in ids], cats)
    top = sorted(ids, key=lambda i: -sum(zs(lines[i], cats, first)))[:n]
    sc = scales([lines[i] for i in top], cats)
    out = {}
    for i in ids:
        z = zs(lines[i], cats, sc)
        out[i] = (sum(z), z)
    return out, sc


def minutes_z(z, rows, m):
    """A player's category z-scores with his line rescaled by minutes factor m (clamped to M_RANGE). rows: [(mean,
    sd, sign)] per category on the league's scale (sign -1 for a reversed category). Ratio categories scale too: made
    and attempts both move with minutes."""
    m = min(max(m, M_RANGE[0]), M_RANGE[1])
    return [s * (m * (mean + (sd or 1) * s * x) - mean) / (sd or 1) for x, (mean, sd, s) in zip(z, rows)]


def shrunk_z(z, zproj, gp, k=SHRINK_K):
    """z pulled toward his projection's z by games played."""
    w = gp / (gp + k) if gp + k else 1.0
    return [w * a + (1 - w) * b for a, b in zip(z, zproj)]


def alternative(source, vals, src, pool, cats, sc, factors):
    """{id: (value, [z])} under a trial value source; a player it has nothing for keeps his site value."""
    rows = [(sc[c][0], sc[c][1], -1 if rev else 1) for c, rev in cats]
    out = {}
    for pid, (v, z) in vals.items():
        if source == "darko_minutes" and pid in factors:
            z = minutes_z(z, rows, factors[pid])
        elif source == "shrunk" and src[pid][0] == "season" and (pool[pid].get("proj") or {}):
            z = shrunk_z(z, zs(pool[pid]["proj"], cats, sc), src[pid][1])
        out[pid] = (sum(z), z)
    return out


def source_basis(source, used, asof):
    if source == "darko_minutes":
        if not used:
            return " Value source: DARKO minutes is switched on but there is no recent DARKO reading, so these are the site's values."
        return (f" Value source: minutes from DARKO (darko.app), read {asof}: the per-game lines of {used} players (mine, "
                f"the waiver options) are rescaled to DARKO's projected minutes (factor kept within {M_RANGE[0]}–{M_RANGE[1]}).")
    if source == "shrunk":
        return (f" Value source: shrunk: a player valued on this season's games is pulled toward his ESPN projection by "
                f"games played (weight games / (games + {SHRINK_K})).")
    return ""


def roster_spots(league):
    slots = league.data.get("slot_counts") or {}
    per_team = sum(v for k, v in slots.items() if int(k) != 13) or 13      # IR spots don't count
    return league.team_count * per_team


def owners(league):
    """{espn id: "me" / other team's name}."""
    own = {str(p["id"]): "me" for p in league.data["roster"]}
    for t in league.data.get("teams") or []:
        for p in t["roster"]:
            own.setdefault(str(p["id"]), t["name"])
    return own


def position(eligible):
    names = {SLOT_NAMES["nba"].get(e) for e in eligible or []}
    return "/".join(x for x in POS if x in names)


def shown(cat, st):
    """The per-game number a player table shows: 18.4 points, .512 FG% (None with no attempts)."""
    if cat in RATIO:
        made, att = (st.get(str(x), 0) for x in RATIO[cat])
        return round(made / att, 3) if att else None
    return round(st.get(str(cat), 0), 1)


def build(league, sc=None, source=None):
    """{"cats", "players": [...best first], "repl", "n", "basis"} for one NBA category league, or None when the
    pool read failed. Each player: id, name, team, pos, own ("me" / team name / None = free agent), src ("season" /
    "proj"), gp, min, v (value per game), rk, wk (this week), g [games left this week, next week], b2b, z (per cat,
    in "cats" order), st (per-game stats in the same order), inj, play (chance he plays his next game), word (ESPN's
    probable/questionable/doubtful), dmin (minutes, last 3 games vs before), pct (% rostered),
    age (years, None when ESPN's rosters don't list him), and gd {"s": status or None, "t": "Out (rest) per NBA injury
    report, 5:30pm"} only when today's official report or Sleeper decided his status (shq/nba_status.py, Q-058)."""
    sc = sc or radar.scan_for(league)
    pool, roles = sc["pool"], sc.get("roles") or {}
    cats = league_cats(league)
    lines, src = {}, {}
    for pid, p in pool.items():
        st, s, gp = per_game(p)
        if st and (st.get("40") or s == "proj"):
            lines[pid], src[pid] = st, (s, gp)
    if not lines:
        return None
    n = roster_spots(league)
    vals, scale = value_pool(lines, cats, n)
    order = sorted(vals, key=lambda i: -vals[i][0])
    repl = vals[order[min(n, len(order) - 1)]][0]
    today = league.ctx.now.astimezone(TZ).date()
    source = source or getattr(config, "NBA_VALUE_SOURCE", "site")
    extra = ""
    if source in SOURCES and source != "site":      # the trial switch; the scale and waiver level stay the site's
        try:
            factors, asof = {}, None
            if source == "darko_minutes":
                from . import darko
                factors, asof = darko.today_factors(today.isoformat())
            vals = alternative(source, vals, src, pool, cats, scale, factors)
            order = sorted(vals, key=lambda i: -vals[i][0])
            extra = source_basis(source, sum(1 for i in vals if i in factors), asof)
        except Exception:
            traceback.print_exc()
    own = owners(league)
    try:
        born = nba_ages.birth_dates()
    except Exception:
        traceback.print_exc()
        born = {}
    out = []
    for rk, pid in enumerate(order, 1):
        if rk > KEEP and pid not in own:
            continue
        p, (v, z) = pool[pid], vals[pid]
        g_now, g_next, b2b = radar.schedule(league, p)
        healthy = categories._healthy(league, {"id": pid, "injury": p.get("injury")})
        entry = league.report.get(pid) or {}
        inj = entry.get("status") or (p.get("injury") if p.get("injury") not in (None, "ACTIVE") else None)
        rl = roles.get(pid)
        st = lines[pid]
        try:
            gd = league.gameday(pid, p["name"], p.get("team"), p.get("injury")) if hasattr(league, "gameday") else None
        except Exception:
            traceback.print_exc()
            gd = None
        out.append({
            "id": pid, "name": p["name"], "team": radar.team_abbrev(league.sched, p["team"]), "pos": position(p.get("eligible")),
            "own": own.get(pid), "src": src[pid][0], "gp": src[pid][1], "min": round(st.get("40", 0), 1),
            "v": round(v, 2), "rk": rk, "wk": round((v - repl) * g_now, 1) if healthy else 0.0,
            "g": [g_now, g_next], "b2b": len(b2b), "z": [round(x, 2) for x in z],
            "st": [shown(c, st) for c, _ in cats],
            "inj": inj,
            # day-to-day: the chance he plays his next game (ESPN's note: probable/questionable/doubtful), which
            # shq/nba_swaps.worth() counts that game at; 1 when healthy
            "play": play_chance(inj, entry.get("note")) if healthy else 1.0, "word": espn_word(entry.get("note")) if inj else None,
            "out": not healthy, "dmin": round(rl["dmin"], 1) if rl else None, "pct": p.get("owned", 0),
            "age": nba_ages.age(born.get(pid), today),
            **({"gd": {"s": gd[0], "t": gd[1]}} if gd else {}),
        })
    return {"cats": [NBA_STATS[c] for c, _ in cats], "rev": [r for _, r in cats], "players": out, "repl": round(repl, 2),
            "n": n, "scale": {NBA_STATS[c]: [round(x, 4) if x is not None else None for x in scale[c]] for c, _ in cats},
            "basis": f"Value per game = the league's {len(cats)} categories as z-scores against the top {n} players "
                     f"({league.team_count} teams' rosters); per-game stats from this season once a player has {MIN_GAMES} "
                     "games, ESPN's projection before that. This week = (value − a waiver-level player's) × games left, "
                     "0 while out. Injury tags are ESPN's; today's status line comes from the NBA injury report and "
                     "Sleeper (the official report wins when it's newer)." + extra,
            **({"source": source} if extra else {})}


def save(path, blocks, updated):
    """docs/data/players.json, one player per line so the run's data commits stay small diffs. A league missing
    this run keeps its last block."""
    old = (load_json(path, {}) or {}).get("leagues") or {}
    leagues = {**old, **{k: v for k, v in blocks.items() if v}}
    dump = lambda x: json.dumps(x, separators=(",", ":"), ensure_ascii=False)
    parts = []
    for name, b in leagues.items():
        head = dump({k: v for k, v in b.items() if k != "players"})[:-1]
        parts.append(f"{dump(name)}:{head},\"players\":[\n" + ",\n".join(dump(p) for p in b.get("players") or []) + "\n]}")
    Path(path).write_text(f"{{\"updated\":{dump(updated)},\"leagues\":{{\n" + ",\n".join(parts) + "\n}}\n",
                          encoding="utf-8", newline="\n")


def by_id(block):
    return {p["id"]: p for p in (block or {}).get("players") or []}


def label(p):
    """'#34 · +2.1/g' with the source, for roster rows."""
    if not p:
        return None
    src = f"{p['gp']} g" if p["src"] == "season" else "ESPN proj"
    return {"v": p["v"], "rk": p["rk"], "wk": p["wk"], "src": src}
