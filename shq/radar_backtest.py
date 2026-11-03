"""Backtest for the NBA trend radar (shq/radar.py): would its flags have beaten the waiver wire?

Replays each morning of the last two weeks with only the games played before it, using the same rules the
radar uses (injuries are inferred from the logs: the ESPN report of that morning isn't kept). For every
free agent it flagged in 3-Ball BB (rosters rebuilt from the league's public transactions), it checks:
- role held: minutes per game in the games after the flag vs his earlier baseline;
- value: per-game category value after the flag (3-Ball's categories, in rotation-player z units) against what
  the site suggested that morning (the most-owned free agents with a game, as shq/advice.py ranks NBA adds)
  and against the average free agent who played;
- market: whether a 3-Ball team added him later, and his ESPN-wide % rostered now with ESPN's +/-.
Free reads only, no AI. Run: py -m shq.radar_backtest [--write] (--write saves reviews/<date>-nba-radar-backtest.md)."""
import sys

from . import espn_fantasy as ef
from . import radar
from .common import ROOT, get_json, now_utc
from .config import TZ

LEAGUE = radar.SOURCE
FIRST, MIN_AFTER = 7, 2     # first morning replayed (needs 6 periods of games before it); games needed after a flag


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


def run(pool, now_ids, txns, cats, last):
    flags, wire, every, anyone = [], [], [], {}
    z = radar.z_scales(pool, radar.team_games(pool))
    for day in range(FIRST, last + 1 - MIN_AFTER + 1):
        past = before(pool, day)
        tg = radar.team_games(past)
        taken = rostered_at(now_ids, txns, day)
        sc = {"z": z}
        after = lambda pid: [x for x in pool[pid]["games"] if x[0] >= day and x[1] == pool[pid]["team"]]
        team_last = {t: max(d for tt, d in tg if tt == t) for t, _ in tg}
        fas = [pid for pid in pool if pid not in taken and past[pid]["games"]
               and past[pid]["games"][-1][0] == team_last.get(past[pid]["team"])]      # played his team's last game
        for pid in pool:   # the signal itself, rostered or not: does a flagged role hold?
            rl = radar.role(past[pid], tg, day)
            later = after(pid)
            if pid not in anyone and radar.rising(rl) and len(later) >= MIN_AFTER:
                anyone[pid] = (rl["base"]["min"], sum(st.get("40", 0) for *_, st in later) / len(later))
        for pid in fas:
            rl = radar.role(past[pid], tg, day)
            later = after(pid)
            v = value(sc, cats, later)
            if v is not None:
                every.append(v)
            if radar.rising(rl) and len(later) >= MIN_AFTER:
                adds = [sp for sp, kind, x in txns if x == pid and kind == "ADD" and sp >= day]
                flags.append({"day": day, "id": pid, "name": pool[pid]["name"], "base": rl["base"]["min"], "flag": rl["recent"]["min"],
                              "after": sum(st.get("40", 0) for *_, st in later) / len(later), "n_after": len(later),
                              "value": v, "added": adds[0] if adds else None, "owned": pool[pid]["owned"], "change": pool[pid]["change"]})
        top = sorted(fas, key=lambda pid: -pool[pid]["owned"])[:3]
        wire += [v for pid in top if (v := value(sc, cats, after(pid))) is not None]
    return flags, wire, every, anyone


def report(pool, flags, wire, every, anyone, dates, cats, last):
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    first = {}
    for f in flags:   # count each player once, from his first flag
        first.setdefault(f["id"], f)
    uniq = list(first.values())
    held = [f for f in uniq if f["after"] >= f["base"] + 3]
    added = [f for f in uniq if f["added"]]
    day = lambda d: radar._day(dates.get(d))
    lines = [
        f"# NBA trend radar backtest ({now_utc().astimezone(TZ).date()})", "",
        f"Mornings replayed: {day(FIRST)} to {day(max(f['day'] for f in flags) if flags else FIRST)}, each with only the games "
        f"before it (ESPN game logs through {day(last)}). League: 3-Ball BB, categories "
        + ", ".join(ef.NBA_STATS[c] for c, _ in cats) + ".", "",
        "## Result", "",
        "Verdict: " + ("the flagged free agents kept their bigger roles and out-produced the site's current suggestions"
                       if flags and mean([f['value'] for f in flags]) > mean(wire) else "the flags did not beat the site's current suggestions")
        + ("; no 3-Ball team picked any of them up afterward, so there was no waiver race to win yet." if not added
           else f"; {len(added)} were later picked up by a 3-Ball team.")
        + f" Small sample ({len(uniq)} free agents), so treat this as a first read.", "",
        f"- Free agents flagged: {len(uniq)} players ({len(flags)} player-mornings).",
        f"- Role held (minutes after the flag at least 3 above his old baseline): {len(held)} of {len(uniq)}.",
        f"- Minutes per game: baseline {mean([f['base'] for f in uniq]):.1f}, at the flag {mean([f['flag'] for f in uniq]):.1f}, "
        f"after the flag {mean([f['after'] for f in uniq]):.1f}.",
        f"- Category value per game after the flag (z units, 0 = average rotation player): radar flags {mean([f['value'] for f in flags]):+.2f}, "
        f"the site's current suggestion (3 most-owned free agents) {mean(wire):+.2f}, average free agent who played {mean(every):+.2f}.",
        f"- Every player the radar would have flagged, rostered or not: {len(anyone)}; role held for "
        f"{sum(a >= b + 3 for b, a in anyone.values())} (minutes {mean([b for b, _ in anyone.values()]):.1f} before, "
        f"{mean([a for _, a in anyone.values()]):.1f} after).",
        f"- Added later by a 3-Ball team: {len(added)} of {len(uniq)}"
        + (f" (median {sorted(f['added'] - f['day'] for f in added)[len(added) // 2]} days after our flag)" if added else "") + ".",
        "", "## Players (first flag)", "",
        "| Flagged | Player | Min before → at flag → after (games) | Value/g after | Added in 3-Ball | % rostered now (ESPN +/-) |",
        "|---|---|---|---|---|---|",
    ]
    for f in sorted(uniq, key=lambda f: (f["day"], -f["after"])):
        lines.append(f"| {day(f['day'])} | {f['name']} | {f['base']:.0f} → {f['flag']:.0f} → {f['after']:.0f} ({f['n_after']}) | "
                     f"{f['value']:+.2f} | {day(f['added']) if f['added'] else '–'} | {f['owned']:.1f} ({f['change']:+.1f}) |")
    lines += ["", "## Caveats", "",
              "- Small sample: two weeks of a new season. Run it again in December.",
              "- Ownership at the time of each flag isn't recorded anywhere free, so the market check uses 3-Ball's own adds; "
              "`state/nba_owned.json` now keeps a daily % rostered reading, so later backtests can measure the ESPN-wide rise.",
              "- The comparison list uses today's % rostered to rank that morning's free agents (a small look-ahead in its favor).",
              "- Injuries come from the logs only (a key teammate missing games), not that morning's ESPN report."]
    return "\n".join(lines) + "\n"


def main(argv):
    pool = radar.fetch_pool()
    tg = radar.team_games(pool)
    last = max(d for _, d in tg)
    raw = get_json(ef._url("nba", LEAGUE["season"], LEAGUE["league_id"]), [("view", "mRoster"), ("view", "mSettings")])
    now_ids = {str(e["playerId"]) for t in raw["teams"] for e in (t.get("roster") or {}).get("entries", [])}
    cats = [(i["statId"], bool(i.get("isReverseItem"))) for i in raw["settings"]["scoringSettings"]["scoringItems"]]
    sched = ef.pro_schedule("nba", LEAGUE["season"])
    flags, wire, every, anyone = run(pool, now_ids, transactions(last + 1), cats, last)
    text = report(pool, flags, wire, every, anyone, radar.period_dates(sched), cats, last)
    if "--write" in argv:
        path = ROOT / "reviews" / f"{now_utc().astimezone(TZ).date()}-nba-radar-backtest.md"
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path}")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
