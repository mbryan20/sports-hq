"""Fresh market lines from ESPN's public scoreboards, and the stale-line scanner for BTO and CFP.

BTO and CFP post fixed spreads early in the week; the market keeps moving. `scan` compares every open
pool line with ESPN's current line (DraftKings) and pushes once per game when the gap is 1.5+ points
or the pool line gains a key number (NFL 3/7, CFB 3/7/10/14). `overlay` puts the same fresh lines
under the cards so `fair_margins` centers on the market as it is now, not CFBD's line from hours ago.

Usage: py -m pp.lines [--week NN] [--if-due] [--no-push]
Runs inside Sports HQ's run.yml loop (requests only, no numpy, no CFBD calls).
"""
import argparse, glob, json, os, re
from datetime import datetime, timedelta, timezone
from math import erf, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo
from .http import get_json
from .names import norm

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "docs" / "data" / "pick_lines.json"  # read by the Picks page; committed by run.yml
SENT = ROOT.parent / "state" / "pick_lines_sent.json"     # once-per-game push dedup
CT = ZoneInfo("America/Chicago")
SB = {"CFB": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
      "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"}
KEYS = {"NFL": (3, 7), "CFB": (3, 7, 10, 14)}
GAP_ALERT = 1.5
EVERY_H = 2       # scan cadence Wed-Sat
EVERY_H_LOCK = 0.5  # Sat 6-11am CT, the run-up to CFP's 11am lock


def _ml_prob(s):
    try:
        ml = float(str(s).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def _names(team):
    return {norm(team.get(k) or "") for k in ("location", "shortDisplayName", "abbreviation", "displayName", "name")} - {""}


def parse_event(e, league):
    """One ESPN scoreboard event -> {id, kick, state, home/away names, home_spread, total, p_home, book}."""
    c = e["competitions"][0]
    t = {x["homeAway"]: x["team"] for x in c["competitors"]}
    o = (c.get("odds") or [{}])[0]
    sp = o.get("spread")
    rec = {"id": str(e["id"]), "league": league, "kick": e.get("date"), "state": c["status"]["type"]["state"],
           "home": t["home"].get("location") or t["home"].get("abbreviation"),
           "away": t["away"].get("location") or t["away"].get("abbreviation"),
           "home_abbr": t["home"].get("abbreviation"), "away_abbr": t["away"].get("abbreviation"),
           "home_names": _names(t["home"]), "away_names": _names(t["away"]),
           "home_spread": None if sp is None else float(sp), "total": o.get("overUnder"),
           "book": (o.get("provider") or {}).get("name") or "ESPN", "p_home": None}
    ml = o.get("moneyline") or {}
    ph = _ml_prob(((ml.get("home") or {}).get("close") or {}).get("odds") or (o.get("homeTeamOdds") or {}).get("moneyLine"))
    pa = _ml_prob(((ml.get("away") or {}).get("close") or {}).get("odds") or (o.get("awayTeamOdds") or {}).get("moneyLine"))
    if ph and pa:
        rec["p_home"] = ph / (ph + pa)
    elif sp is not None:
        rec["p_home"] = 0.5 * (1 + erf((-float(sp)) / (15.5 * sqrt(2))))
    return rec


def espn_odds(league, week, year=2026, max_age_h=0.25):
    """Current ESPN lines for a CFBD/ESPN week (CFB) or NFL week. Fresh by default (15-min cache)."""
    kw = {"seasontype": 2, "week": week, "dates": year}
    if league == "CFB":
        kw.update(groups=80, limit=300)  # all FBS games, not just the top 25
    d = get_json("espn", SB[league], max_age_h=max_age_h, **kw)
    return [parse_event(e, league) for e in d.get("events", [])]


def find(events, away, home):
    """Match a pool game to an ESPN event. Returns (event, flipped) where flipped means ESPN lists
    the pool's home team as away (neutral sites), so ESPN's home line must be negated."""
    a, h = norm(away), norm(home)
    for e in events:
        if h in e["home_names"] and a in e["away_names"]:
            return e, False
        if a in e["home_names"] and h in e["away_names"]:
            return e, True
    return None, False


def overlay(cfbd_lines, week, year=2026, games=()):
    """Cards: replace CFBD's (up to 6h old) spread/total/win prob with ESPN's current line where ESPN
    has one; keep CFBD's opening line. ESPN event ids are CFBD game ids; `games` (CFBD) guards against
    ESPN listing home/away the other way round. Never fails the card build."""
    out = dict(cfbd_lines)
    cfbd_games = {str(g["id"]): g for g in games}
    try:
        events = espn_odds("CFB", week, year)
    except Exception as ex:
        print("ESPN odds unavailable, using CFBD lines:", ex)
        return out
    at = datetime.now(CT).strftime("%a %I:%M %p CT")
    for e in events:
        if e["home_spread"] is None:
            continue
        gid = int(e["id"]) if e["id"].isdigit() else e["id"]
        old = out.get(gid) or {}
        hs, ph = e["home_spread"], e["p_home"]
        g = cfbd_games.get(e["id"])
        if g and norm(g["homeTeam"]) in e["away_names"] and norm(g["awayTeam"]) in e["home_names"]:
            hs, ph = -hs, None if ph is None else 1 - ph
        out[gid] = {**old, "home_spread": hs, "total": e["total"] if e["total"] is not None else old.get("total"),
                    "p_home": ph, "open_spread": old.get("open_spread"), "src": f"ESPN {e['book']} {at}",
                    "cfbd_spread": old.get("home_spread")}
    return out


def key_crossed(pool_s, mkt_s, keys):
    """Value side's pool spread vs its market spread (pool_s > mkt_s). Returns the key numbers the pool
    line gains: margins M (that side's margin) with -pool_s <= M <= -mkt_s, where the pool turns a loss
    into a push or win, or a push into a win."""
    return sorted({k for k in keys for m in (k, -k) if -pool_s <= m <= -mkt_s})


def gap_row(pool, sg, ev, flipped, league):
    """Compare one pool game with its market line. The value side is the team the pool gives more points."""
    mkt_home = -ev["home_spread"] if flipped else ev["home_spread"]
    pool_home = float(sg["home_spread"])
    gap = round(abs(pool_home - mkt_home), 2)
    home_value = pool_home > mkt_home  # pool's home line is more generous than the market's
    side = sg["home"] if home_value else sg["away"]
    pool_s, mkt_s = (pool_home, mkt_home) if home_value else (-pool_home, -mkt_home)
    keys = key_crossed(pool_s, mkt_s, KEYS[league]) if gap else []
    return {"pool": pool, "league": league, "game": f"{sg['away']} @ {sg['home']}", "side": side,
            "pool_line": pool_s, "market_line": mkt_s, "gap": gap, "keys": keys,
            "flag": gap >= GAP_ALERT or bool(keys), "book": ev["book"], "kick": ev["kick"], "espn_id": ev["id"]}


def deadlines(slate, events):
    """When each pool stops taking changes. CFP locks Sat 11am CT; BTO bets are due Fri 8pm CT (games lock
    at kickoff). A slate can override with bto.deadline / cfp.deadline (ISO)."""
    kicks = [datetime.fromisoformat(e["kick"].replace("Z", "+00:00")) for e in events if e.get("kick")]
    if not kicks:
        return {}
    first = min(kicks).astimezone(CT)
    sat = (first + timedelta(days=(5 - first.weekday()) % 7)).replace(hour=11, minute=0, second=0, microsecond=0)
    out = {"cfp": sat, "bto": (sat - timedelta(days=1)).replace(hour=20)}
    for p in out:
        if (slate.get(p) or {}).get("deadline"):
            out[p] = datetime.fromisoformat(slate[p]["deadline"])
    return out


def latest_slate(week=None):
    if week:
        f = ROOT / f"slates/2026-w{week:02d}.json"
    else:
        fs = sorted(glob.glob(str(ROOT / "slates/2026-w*.json")))
        if not fs:
            return None, None
        f = Path(fs[-1])
    if not f.exists():
        return None, None
    s = json.loads(f.read_text(encoding="utf-8"))
    return s, s.get("cfbd_week") or int(re.search(r"w(\d+)", f.name)[1])


def scan(week=None, now=None, fetch=espn_odds):
    """Gap rows for every open BTO/CFP game, biggest first."""
    now = now or datetime.now(timezone.utc)
    slate, week = latest_slate(week)
    if not slate:
        return week, []
    pools = [(p, g) for p in ("bto", "cfp") for g in (slate.get(p) or {}).get("games") or []]
    nfl_weeks = {g.get("nfl_week") for p, g in pools if g.get("league") == "NFL"} - {None}
    events = {"CFB": fetch("CFB", week)}
    events["NFL"] = [e for w in sorted(nfl_weeks) for e in fetch("NFL", w)]
    dl = deadlines(slate, events["CFB"] + events["NFL"])
    rows = []
    for pool, sg in pools:
        league = sg.get("league", "CFB")
        if sg.get("locked") or sg.get("home_spread") is None:
            continue
        ev, flipped = find(events[league], sg["away"], sg["home"])
        if not ev or ev["home_spread"] is None or ev["state"] != "pre":
            continue
        kick = datetime.fromisoformat(ev["kick"].replace("Z", "+00:00"))
        closes = min(kick, dl[pool]) if pool in dl else kick
        if closes <= now:
            continue
        r = gap_row(pool, sg, ev, flipped, league)
        r["closes"] = closes.astimezone(CT).isoformat()
        rows.append(r)
    rows.sort(key=lambda r: (-r["flag"], -r["gap"], r["pool"]))
    return week, rows


def _fmt(x):
    return f"{x:+g}" if x else "PK"


def describe(r):
    keys = f", gains {'/'.join(map(str, r['keys']))}" if r["keys"] else ""
    return f"{r['pool'].upper()} {r['side']} {_fmt(r['pool_line'])} vs market {_fmt(r['market_line'])} ({r['book']}): {r['gap']:g} pts{keys}"


def due(now=None):
    """run.yml calls this every pass; scan Wed-Sat CT every 2h (every 30 min Sat 6-11am CT)."""
    now = (now or datetime.now(timezone.utc)).astimezone(CT)
    if now.weekday() not in (2, 3, 4, 5):  # Wed..Sat
        return False
    try:
        last = datetime.fromisoformat(json.loads(OUT.read_text())["updated"])
    except Exception:
        return True
    every = EVERY_H_LOCK if now.weekday() == 5 and 6 <= now.hour < 11 else EVERY_H
    return (now - last).total_seconds() >= every * 3600 - 300


def run(week=None, push=True, now=None, fetch=espn_odds):
    from .publish import notify
    now = now or datetime.now(timezone.utc)
    week, rows = scan(week, now, fetch)
    sent = json.loads(SENT.read_text()) if SENT.exists() else {}
    new = [r for r in rows if r["flag"] and f"{week}:{r['pool']}:{r['game']}" not in sent]
    pushed = []
    if new and push and os.environ.get("DRY_RUN") != "1":
        title = f"Stale pool line: {new[0]['pool'].upper()} {new[0]['side']} {_fmt(new[0]['pool_line'])}" if len(new) == 1 \
            else f"{len(new)} stale pool lines"
        msg = "\n".join(describe(r) for r in new) + "\nPool lines are fixed; the market moved."
        if notify(title, msg, tags="chart_with_upwards_trend", priority=4):
            pushed = new
            for r in new:
                sent[f"{week}:{r['pool']}:{r['game']}"] = now.isoformat()
    cutoff = (now - timedelta(days=21)).isoformat()
    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps({k: v for k, v in sent.items() if v >= cutoff}, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": now.astimezone(CT).isoformat(), "week": week, "alert_gap": GAP_ALERT,
                               "rows": rows}, indent=1))
    return week, rows, pushed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--if-due", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    if a.if_due and not due():
        return
    week, rows, pushed = run(a.week, push=not a.no_push)
    print(f"week {week}: {len(rows)} open pool games, {sum(r['flag'] for r in rows)} flagged, {len(pushed)} pushed now")
    for r in rows[:12]:
        print(("* " if r["flag"] else "  ") + describe(r))


if __name__ == "__main__":
    main()
