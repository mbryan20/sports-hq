"""Backtest for the NBA trend radar (shq/radar.py): would its flags have beaten the waiver wire?

Replays each of the last 14 mornings that had games, with only the games played before it, using the same rules the
radar uses (injuries are inferred from the logs: the ESPN report of that morning isn't kept, so a key teammate who
missed every one of the riser's last 3 games stands in for "on ESPN's injury report"). Every free agent it flags in
3-Ball BB (rosters rebuilt from the league's public transactions) is scored once, at his first flag, on his team's
next 3 games (the same window `radar.role()` flags on; a game he missed counts as 0 minutes, as in his baseline):
- role held: minutes over those 3 games at least 3 above his earlier baseline;
- shown: the same for the 4 free agents a morning the site would have listed (`radar.block()`'s order), the number
  that matters, since the rest never reach the page;
- value: per-game category value in those games (3-Ball's categories, in rotation-player z units) against what the
  site suggested that morning (the 3 most-owned free agents with a game, ranked by that morning's % rostered from
  `state/nba_owned.json`, so only mornings from Nov 3 on) and against the average free agent who played;
- market: whether a 3-Ball team added him later, and his ESPN-wide % rostered now with ESPN's +/-.
Free reads only, no AI. Run: py -m shq.radar_backtest [--write] (--write saves reviews/<date>-nba-radar-backtest.md)."""
import datetime as dt
import sys

from . import espn_fantasy as ef
from . import radar
from .common import ROOT, get_json, load_json, now_utc
from .config import TZ

LEAGUE = radar.SOURCE
FIRST = 7          # first morning that can be replayed (needs 6 periods of games before it)
MORNINGS = 14      # mornings replayed: the last two weeks
HORIZON = 3        # judged on his team's next 3 games, the window radar.role() flags on
SHOWN = 4          # free agents a basketball tab lists (radar.block)
WIRE = 3           # the old suggestion: the 3 most-owned free agents


def transactions(last_period):
    """[(period, "ADD"/"DROP", player id)] executed in 3-Ball BB, from its public transaction log."""
    url = ef._url("nba", LEAGUE["season"], LEAGUE["league_id"])
    out = []
    for sp in range(1, last_period + 1):
        for t in get_json(url, {"view": "mTransactions2", "scoringPeriodId": sp}).get("transactions") or []:
            if t.get("status") == "EXECUTED":
                out += [(sp, it["type"], str(it["playerId"])) for it in t.get("items") or [] if it["type"] in ("ADD", "DROP")]
    return out


def rostered_at(now_ids, txns, day):
    """3-Ball rosters the morning of `day`: undo every add and drop since."""
    ids = set(now_ids)
    for sp, kind, pid in sorted(txns, reverse=True):
        if sp >= day:
            (ids.discard if kind == "ADD" else ids.add)(pid)
    return ids


def before(pool, day):
    return {pid: {**p, "games": [x for x in p["games"] if x[0] < day]} for pid, p in pool.items()}


def value(sc, cats, games):
    """Mean per-game category value over these games (z units summed over the league's categories)."""
    if not games:
        return None
    per = [sum(radar.cat_z(sc, c, st) * (-1 if rev else 1) for c, rev in cats if c in sc["z"]) for *_, st in games]
    return sum(per) / len(per)


def day_date(dates, day):
    """The date of scoring period `day`; a period with no NBA games (absent from radar.period_dates) follows the one before."""
    known = [d for d in dates if d <= day]
    return dates[max(known)] + dt.timedelta(days=day - max(known)) if known else None


def run(pool, now_ids, txns, cats, last, dates=None, owned=None, mornings=MORNINGS):
    """Replay the last `mornings` mornings that had games, through period `last`. Returns {"log": every scored
    flag-morning, "wire": [(day, value)], "every": [value], "mornings": [days replayed]}. Each flag: day, id, name,
    base/flag/after minutes (after = per team game over his team's next HORIZON games), played, held, value, cause,
    fade, shown (among the SHOWN the site would list that morning), added, owned/change now. Flags too recent for
    HORIZON team games after them aren't scored. dates: {period: date} (radar.period_dates), owned: the
    state/nba_owned.json history; both only for the old-suggestion comparison."""
    dates, owned = dates or {}, owned or {}
    tg_all = radar.team_games(pool)
    sc = {"z": radar.z_scales(pool, tg_all)}
    need = {c: "all" for c, rev in cats if not rev and c in sc["z"]}
    ahead = lambda team, day: sorted(d for t, d in tg_all if t == team and d >= day)[:HORIZON]
    log, wire, every = [], [], []
    days = sorted({d for _, d in tg_all if FIRST <= d <= last})[-mornings:]   # a day without games repeats the one before
    for day in days:
        past = before(pool, day)
        tg = radar.team_games(past)
        taken = rostered_at(now_ids, txns, day)
        team_last = {}
        for t, d in tg:
            team_last[t] = max(d, team_last.get(t, d))
        fas = [pid for pid in pool if pid not in taken and past[pid]["games"]
               and past[pid]["games"][-1][0] == team_last.get(past[pid]["team"])]      # played his team's last game

        def outcome(pid):
            """(minutes per team game, games played, value per game played) over his team's next HORIZON games."""
            team = pool[pid]["team"]
            nxt = ahead(team, day)
            if len(nxt) < HORIZON:
                return None
            games = [g for g in pool[pid]["games"] if g[1] == team and g[0] in nxt]
            return sum(st.get("40", 0) for *_, st in games) / HORIZON, len(games), value(sc, cats, games)

        ranked = []
        for pid in fas:
            res = outcome(pid)
            if res and res[2] is not None:
                every.append(res[2])
            rl = radar.role(past[pid], tg, day)
            if not rl:
                continue
            if not radar.rising(rl):
                continue
            gone = radar.absences(past, past[pid]["team"], [d for d, *_ in rl["games"]])
            fit, _ = radar.fit_score(sc, past[pid], rl, need)
            ranked.append((radar.rank_key(rl, gone, gone, fit), pid, rl, gone, res))   # absent = out (no old report)
        ranked.sort(key=lambda t: t[0])
        for i, (_, pid, rl, gone, res) in enumerate(ranked):
            if not res:
                continue
            adds = [sp for sp, kind, x in txns if x == pid and kind == "ADD" and sp >= day]
            log.append({"day": day, "id": pid, "name": pool[pid]["name"], "base": rl["base"]["min"], "flag": rl["recent"]["min"],
                        "after": res[0], "played": res[1], "held": res[0] >= rl["base"]["min"] + 3, "value": res[2],
                        "cause": pool[gone[0]]["name"] if gone else None, "fade": radar.may_fade(rl, gone),
                        "shown": i < SHOWN, "added": adds[0] if adds else None, "owned": pool[pid]["owned"],
                        "change": pool[pid]["change"]})
        when = day_date(dates, day)
        hist = owned.get(when.isoformat()) if when else None
        if hist:   # ESPN-wide % rostered that morning; players over 70% aren't kept, so they fall back to today's
            pct = lambda pid: hist.get(pid, pool[pid]["owned"] if pool[pid]["owned"] > 70 else 0)
            for pid in sorted(fas, key=lambda pid: -pct(pid))[:WIRE]:
                res = outcome(pid)
                if res and res[2] is not None:
                    wire.append((day, res[2]))
    return {"log": log, "wire": wire, "every": every, "mornings": days}


def firsts(log, keep=lambda f: True):
    """Each player once, at his first flag-morning that passes `keep`."""
    out = {}
    for f in log:
        if keep(f):
            out.setdefault(f["id"], f)
    return list(out.values())


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def r2(x):
    return round(x, 2) if x is not None else None


def summary(res):
    """The numbers model health tracks: hit rates (shown and all flags, each player once at his first flag) and the
    value edge over the old suggestion on the mornings that have an ownership reading (each player once, at his first
    flag among those mornings)."""
    wire_days = {d for d, _ in res["wire"]}
    wv = mean([v for _, v in res["wire"]])
    out = {"mornings": len(res["mornings"]), "wire_mornings": len(wire_days), "wire_value": r2(wv)}
    for key, keep in (("shown", lambda f: f["shown"]), ("flags", lambda f: True)):
        fl = firsts(res["log"], keep)
        held = sum(f["held"] for f in fl)
        on_wire = [f["value"] for f in firsts(res["log"], lambda f: keep(f) and f["day"] in wire_days) if f["value"] is not None]
        fv = mean(on_wire)
        out[key] = {"n": len(fl), "held": held, "held_rate": r2(held / len(fl)) if fl else None,
                    "value": r2(mean([f["value"] for f in fl])), "edge_n": len(on_wire),
                    "edge": r2(fv - wv) if fv is not None and wv is not None else None,
                    "added_later": sum(1 for f in fl if f["added"])}
    out["every_value"] = r2(mean(res["every"]))
    return out


def report(res, dates, cats, last):
    s = summary(res)
    sh, fl = s["shown"], s["flags"]
    day = lambda d: radar._day(day_date(dates, d))
    fmt = lambda x: f"{x:+.2f}" if x is not None else "–"
    pct = lambda k: f"{k['held']} of {k['n']}" + (f" ({k['held_rate']:.0%})" if k["n"] else "")
    lines = [
        f"# NBA trend radar backtest ({now_utc().astimezone(TZ).date()})", "",
        f"Mornings replayed: {day(res['mornings'][0])} to {day(res['mornings'][-1])} (the last {len(res['mornings'])} with games), "
        f"each with only the games before it (ESPN game logs through {day(last)}); a flag is judged on his team's next "
        f"{HORIZON} games, so the last few mornings aren't scored yet. League: 3-Ball BB, categories "
        + ", ".join(ef.NBA_STATS[c] for c, _ in cats) + ".", "",
        "## Result", "",
        f"- Shown on the site (top {SHOWN} free agents a morning, the tab's order): role held for {pct(sh)}; "
        f"value {fmt(sh['value'])} per game.",
        f"- Every flagged free agent: role held for {pct(fl)}; value {fmt(fl['value'])} per game.",
        f"- Against the site's old suggestion ({WIRE} most-owned free agents by that morning's % rostered, {s['wire_mornings']} "
        f"mornings): shown flags {fmt(sh['edge'])} z per game (n={sh['edge_n']}), every flag {fmt(fl['edge'])} "
        f"(n={fl['edge_n']}); the old suggestion itself {fmt(s['wire_value'])}, the average free agent who played "
        f"{fmt(s['every_value'])}.",
        f"- Added later by a 3-Ball team: {fl['added_later']} of {fl['n']}.",
        "", "## Players (first flag; * = was among the shown)", "",
        f"| Flagged | Player | Min before → at flag → next {HORIZON} team games (played) | Held | Value/g | Cause | Added in 3-Ball | % rostered now (ESPN +/-) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    shown_ids = {f["id"] for f in res["log"] if f["shown"]}
    for f in sorted(firsts(res["log"]), key=lambda f: (f["day"], -f["after"])):
        lines.append(f"| {day(f['day'])} | {f['name']}{' *' if f['id'] in shown_ids else ''} | {f['base']:.0f} → {f['flag']:.0f} → "
                     f"{f['after']:.0f} ({f['played']}) | {'yes' if f['held'] else 'no'} | {fmt(f['value'])} | "
                     f"{f['cause'] or ('none, may fade' if f['fade'] else 'none')} | {day(f['added']) if f['added'] else '–'} | "
                     f"{f['owned']:.1f} ({f['change']:+.1f}) |")
    lines += ["", "## Caveats", "",
              "- Small sample: a few weeks of a new season. A flag counts once, at his first flag.",
              "- Injuries come from the logs only (a key teammate missing games), not that morning's ESPN report.",
              "- The site's order also weighs games left this week; the replay ranks by category fit over every 3-Ball category."]
    return "\n".join(lines) + "\n"


def inputs():
    """Everything run() needs, from free reads: (pool, rostered ids now, transactions, categories, last period, dates, owned)."""
    pool = radar.fetch_pool()
    last = max(d for _, d in radar.team_games(pool))
    raw = get_json(ef._url("nba", LEAGUE["season"], LEAGUE["league_id"]), [("view", "mRoster"), ("view", "mSettings")])
    now_ids = {str(e["playerId"]) for t in raw["teams"] for e in (t.get("roster") or {}).get("entries", [])}
    cats = [(i["statId"], bool(i.get("isReverseItem"))) for i in raw["settings"]["scoringSettings"]["scoringItems"]]
    dates = radar.period_dates(ef.pro_schedule("nba", LEAGUE["season"]))
    return pool, now_ids, transactions(last + 1), cats, last, dates, load_json(radar.OWNED, {}) or {}


def main(argv):
    pool, now_ids, txns, cats, last, dates, owned = inputs()
    text = report(run(pool, now_ids, txns, cats, last, dates, owned), dates, cats, last)
    if "--write" in argv:
        path = ROOT / "reviews" / f"{now_utc().astimezone(TZ).date()}-nba-radar-backtest.md"
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path}")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
