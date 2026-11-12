"""DARKO's free next-game NBA projections (darko.app): each player's projected minutes, for the trial value source
"darko_minutes" (config.NBA_VALUE_SOURCE, shq/nba_values.py) and its nightly comparison (shq/health.py, section
"sources", via shq/nba_advice_backtest.py trial()). Free read, no AI, no sign-in.

Source: the JSON darko.app's Projections page loads (https://www.darko.app/projections/__data.json: the page's own
SvelteKit data, the rows its "Download CSV" button turns into a CSV in the browser), always through its Time Machine
(?asof=YYYY-MM-DD): each player's minutes forecast for his latest game on or before that day, made before that game.
x_minutes = DARKO's forecast of a player's minutes a game when he plays (darko.app/about). darko.app has no robots.txt
(404) and no terms page (checked Nov 12, 2026); its FAQ says the data can be downloaded.
Why the Time Machine, also for today: the live board (no asof) is a different number. On Nov 12 its minutes ran 2.6
below players' season averages (median) and missed the Nov 11 games by 4.4 minutes (median), while the Time Machine's
ran 0.7 above and missed by 3.5 (it looks like the live board counts the chance a player sits). The same Time Machine
read as of each morning keeps the live switch and the backtest on one number, and it never sees the game it forecasts.

Read lightly: at most once a day (state/nba_darko.json says whether today is done; .cache/darko/ keeps each day's read,
a failed one too), one try, a generic User-Agent, never fails a run.

Never republished: DARKO's numbers stay in .cache (not committed, never on the site). What is committed
(state/nba_darko.json, this repo is public) is only our own derived number for the players the advice and the backtest
need: his minutes factor = DARKO's projected minutes / the minutes in the line his value is built on (this season's
average, or ESPN's projection before 5 games), rounded to STEP, for the players on my two basketball rosters, the ones
that morning's swaps and streamers named, and the TOP_FA best free agents by value in each league (keep_ids). No DARKO
dates, minutes or names. One entry a day, KEEP_DAYS days. The site credits "minutes from DARKO (darko.app)" whenever
the switch uses it.

    py -m shq.darko               today's read (once a day); prints what it got, not DARKO's table (the run keeps
                                  the snapshot, after the basketball tabs are built)
    py -m shq.darko --backfill    also each backtest morning without a snapshot (one read per day, ever)"""
import datetime as dt
import json
import sys
import traceback
import unicodedata

import requests

from .common import CACHE, STATE, load_json, now_utc
from .config import TZ

URL = "https://www.darko.app/projections/__data.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; data-reader/1.0)", "Accept": "application/json"}
SNAP = STATE / "nba_darko.json"
CACHE_DIR = CACHE / "darko"
KEEP_DAYS = 60          # snapshot days kept (the comparison stores finished weeks in health.json, so older ones can go)
SNAP_HOUR = 7           # the day's reading is taken from the first run at or after 7am CT (before the 8am advice)
STALE_DAYS = 3          # with the switch on, an older snapshot than this is not used (site values instead)
STEP = 0.05             # factors are kept to the nearest 0.05
TOP_FA = 10             # free agents kept per league besides the ones the advice named (the next-ranked options)
V = 2                   # 2: only the players the advice and backtest need, factors to 0.05, no DARKO as-of date


# ---------- the read ----------
def decode(payload):
    """[{"name", "team", "min", "date"}] from the page's SvelteKit data (devalue: one flat array of values, objects
    and lists holding indexes into it; players either a list of objects or {"keys", "values"} columns), or [].
    Also returns DARKO's as-of date: (rows, asof)."""
    node = next((n for n in (payload or {}).get("nodes") or [] if isinstance(n, dict) and n.get("type") == "data"), None)
    arr = (node or {}).get("data")
    if not isinstance(arr, list) or not arr:
        return [], None
    memo = {}

    def h(i, depth=0):
        if not isinstance(i, int) or i < 0 or i >= len(arr) or depth > 50:
            return None
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, dict):
            out = {k: h(x, depth + 1) for k, x in v.items()}
        elif isinstance(v, list):
            out = None if v and isinstance(v[0], str) else [h(x, depth + 1) for x in v]   # typed values (Date, Map...)
        else:
            out = v
        memo[i] = out
        return out
    root = h(0)
    if not isinstance(root, dict):
        return [], None
    players = root.get("players")
    if isinstance(players, dict) and players.get("keys") and players.get("values"):
        players = [dict(zip(players["keys"], r)) for r in zip(*players["values"])]
    rows = []
    for p in players or []:
        if not isinstance(p, dict) or not p.get("player_name"):
            continue
        try:
            m = float(p.get("x_minutes"))
        except (TypeError, ValueError):
            continue
        rows.append({"name": p["player_name"], "team": p.get("team_name"), "min": m, "date": p.get("date")})
    asof = root.get("asOf") or root.get("ratingsThrough")
    return rows, asof if isinstance(asof, str) else None


def fetch(day, get=None):
    """(rows, DARKO's as-of date) from the Time Machine as of `day`, or (None, None). One read per day, ever: the
    day's cached read is reused, a failed one too (no retry). Never raises."""
    path = CACHE_DIR / f"asof-{day}.json"
    hit = load_json(path)
    if hit:
        return hit.get("rows"), hit.get("asof")
    rows, got, err = None, None, None
    try:
        r = (get or requests.get)(URL, params={"asof": day}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        rows, got = decode(r.json())
        rows = rows or None
        if not rows:
            err = "no players in the page data (the page may have changed)"
    except Exception as e:
        traceback.print_exc()
        err = f"{type(e).__name__}: {e}"[:200]
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"day": day, "asof": got, "rows": rows, "error": err}), encoding="utf-8")
    except Exception:
        traceback.print_exc()
    return rows, got


# ---------- our derived numbers ----------
def key(name):
    """health.name_key without accents: "Nikola Jokić" and "Nikola Jokic" meet."""
    from .health import name_key
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return name_key(plain)


def step(x):
    """A factor rounded to STEP (0.05): coarse on purpose, it is ours, not DARKO's number."""
    return round(round(x / STEP) * STEP, 2)


def factors(rows, lines, names, keep=None):
    """{ESPN id: DARKO's projected minutes / the minutes in his value line, to the nearest STEP} for the ids in `keep`
    (all when None). lines: {id: minutes}; names: {id: name}. Matched by name; a name two ESPN players share is skipped,
    and so is a line under 1 minute."""
    by_key = {}
    for pid, n in names.items():
        by_key.setdefault(key(n), []).append(pid)
    out = {}
    for r in rows or []:
        ids = by_key.get(key(r["name"])) or []
        if len(ids) != 1 or (keep is not None and ids[0] not in keep):
            continue
        lm = lines.get(ids[0]) or 0
        if lm >= 1 and r["min"] > 0:
            out[ids[0]] = step(r["min"] / lm)
    return out


def named(block, adv):
    """ESPN ids a morning's Waiver adds swaps (add and drop) and streamers named, from the shown lines."""
    from . import nba_advice_backtest as ab
    idx, out = ab.name_index(block), set()
    for line in (adv or {}).get("adds") or []:
        s = ab.parse_swap(line)
        for n in ((s["add"], s["drop"]) if s else ()):
            p = ab.find(idx, n)
            if p:
                out.add(str(p["id"]))
    for line in ((adv or {}).get("games") or {}).get("streamers") or []:
        s = ab.parse_streamer(line)
        p = ab.find(idx, s["name"]) if s else None
        if p:
            out.add(str(p["id"]))
    return out


def keep_ids(blocks):
    """Who the snapshot keeps: [(players.json league block, ids its advice named)] -> my roster in that league (the drops),
    the players named, and the TOP_FA best free agents by value (the next-ranked options)."""
    out = set()
    for block, names_ in blocks:
        players = (block or {}).get("players") or []
        out |= {str(p["id"]) for p in players if p.get("own") == "me"} | set(names_ or ())
        fas = sorted((p for p in players if not p.get("own")), key=lambda p: -(p.get("v") or 0))
        out |= {str(p["id"]) for p in fas[:TOP_FA]}
    return out


def load():
    return load_json(SNAP, {}) or {}


def save(snap):
    """One day per line, so a day's data commit is a one-line diff."""
    days = snap.get("days") or {}
    keep = sorted(days)[-KEEP_DAYS:]
    dump = lambda x: json.dumps(x, separators=(",", ":"))
    body = ",\n".join(f"{dump(d)}:{dump(days[d])}" for d in keep)
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(f"{{\"v\":{V},\"days\":{{\n{body}\n}}}}\n", encoding="utf-8", newline="\n")


def record(day, rows, lines, names, keep, how="daily"):
    """Store one day's factors for the `keep` ids (an existing day is kept). Returns the day's entry or None. Only our
    factor and how it was read ("daily" / "backfill") are stored: no DARKO date, minutes or names."""
    f = factors(rows, lines, names, keep)
    if not f:
        return None
    snap = load()
    days = snap.setdefault("days", {})
    if day not in days:
        days[day] = {"how": how, "m": dict(sorted(f.items()))}
        save(snap)
    return days[day]


def pool_lines(pool):
    """({id: minutes in his value line}, {id: name}) from the radar's ESPN pool, as shq/nba_values.py builds lines."""
    from .nba_values import per_game
    lines, names = {}, {}
    for pid, p in pool.items():
        st = per_game(p)[0]
        if st and st.get("40"):
            lines[pid], names[pid] = st["40"], p["name"]
    return lines, names


def track(now=None, blocks=(), pool=None, get=None):
    """The run's daily reading, after the basketball tabs are built: from SNAP_HOUR CT, once a day, read DARKO and
    keep today's factors for keep_ids(blocks) (blocks: [(league values block, ids its advice named)]). Returns a
    one-line status for the run notes. Never raises."""
    try:
        now = now or now_utc()
        local = now.astimezone(TZ)
        day = local.date().isoformat()
        if day in (load().get("days") or {}) or local.hour < SNAP_HOUR:
            return None
        keep = keep_ids(blocks)
        if not keep:
            return None
        rows, _ = fetch(day, get=get)
        if not rows:
            return f"darko: no reading today ({error(day) or 'read failed'})"
        if pool is None:
            from . import radar
            pool = radar.fetch_pool()
        lines, names = pool_lines(pool)
        e = record(day, rows, lines, names, keep)
        prune(local.date())
        return f"darko: {len(e['m']) if e else 0} players' minutes factors for {day}"
    except Exception:
        traceback.print_exc()
        return None


def run_blocks(leagues, views):
    """track()'s blocks from a run: each basketball league's values block and the players its advice names."""
    out = []
    for lg in leagues:
        block = getattr(lg, "values", None)
        if getattr(lg, "sport", "nfl") == "nba" and block:
            out.append((block, named(block, (views.get(lg.name) or {}).get("advice"))))
    return out


def prune(today, keep=14):
    """Drop cached reads older than `keep` days (their factors are in the snapshot), so .cache stays small."""
    cut = (today - dt.timedelta(days=keep)).isoformat()
    for f in CACHE_DIR.glob("asof-*.json"):
        if f.stem[5:] < cut:
            f.unlink(missing_ok=True)


def error(day):
    return (load_json(CACHE_DIR / f"asof-{day}.json") or {}).get("error")


def today_factors(day, stale=STALE_DAYS):
    """(factors, snapshot day) for the live switch: the newest snapshot on or before `day` within `stale` days, else
    ({}, None). Reads only the committed snapshot, never the network."""
    days = load().get("days") or {}
    d = dt.date.fromisoformat(day)
    for k in sorted(days, reverse=True):
        kd = dt.date.fromisoformat(k)
        if kd <= d and (d - kd).days <= stale:
            return days[k].get("m") or {}, k
    return {}, None


def morning_blocks(hist):
    """{day: (lines, names, keep)} from backtest mornings (history()): that morning's players.json minutes, and who the
    snapshot keeps (my roster, named by that morning's swaps and streamers, the next-ranked free agents)."""
    by_day = {}
    for m in hist:
        lines, names, blocks = by_day.setdefault(m["day"], ({}, {}, []))
        for p in m["block"].get("players") or []:
            if p.get("min"):
                lines[str(p["id"])], names[str(p["id"])] = p["min"], p["name"]
        ids = {str(s["add_id"]) for s in m["swaps"]} | {str(s["drop_id"]) for s in m["swaps"] if s["drop_id"]}
        blocks.append((m["block"], ids | {str(s["id"]) for s in m["streamers"]}))
    return {d: (lines, names, keep_ids(blocks)) for d, (lines, names, blocks) in by_day.items()}


def backfill(hist, get=None):
    """For backtest mornings without a snapshot: DARKO's Time Machine as of that morning (one read per day, cached),
    factors against the minutes in that morning's players.json for the players it keeps. Returns the days added."""
    have = load().get("days") or {}
    added = []
    for day, (lines, names, keep) in sorted(morning_blocks(hist).items()):
        if day in have:
            continue
        rows, _ = fetch(day, get=get)
        if rows and record(day, rows, lines, names, keep, how="backfill"):
            added.append(day)
    return added


def main(argv):
    now = now_utc()
    day = now.astimezone(TZ).date().isoformat()
    rows, asof = fetch(day)
    if not rows:
        print(f"DARKO read for {day}: none ({error(day) or 'no rows'})")
    else:
        mins = sorted(r["min"] for r in rows)
        print(f"DARKO read for {day}: {len(rows)} players, DARKO as of {asof}; projected minutes median "
              f"{mins[len(mins) // 2]:.1f}")
        from . import radar
        lines, names = pool_lines(radar.fetch_pool())
        f = factors(rows, lines, names)
        if f:
            v = sorted(f.values())
            print(f"Matched to the ESPN pool: {len(f)} of {len(rows)}; minutes factor median {v[len(v) // 2]:.2f}, "
                  f"{sum(x >= 1.15 for x in v)} at 1.15+ (more minutes), {sum(x <= 0.85 for x in v)} at 0.85 or less")
    if "--backfill" in argv:
        from . import nba_advice_backtest as ab
        print("backfilled:", backfill(ab.history()) or "nothing missing")
    snap = load().get("days") or {}
    print("snapshot days:", ", ".join(f"{d} ({snap[d].get('how')}, {len(snap[d]['m'])} players)" for d in sorted(snap)) or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
