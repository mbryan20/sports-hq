"""NBA daily lineup: today's start/sit moves for the basketball leagues and one push a day before the first tip-off.
Pure logic, no AI; ESPN is read-only, so every move is "make this change" for Michael.

A move is needed only when a starter can't help today (no game, out, or an empty slot) and a bench player who plays
today can fill that slot, or when a bench player who plays today is worth clearly more than a starter who plays today
(MIN_EDGE value per game, shq/nba_values.py). The same rule as the 8am digest's "no game today → start X", ranked by
category value instead of points (category leagues have none). The trend radar's "start him" for a rising bench player
follows these moves (radar.agree(), Q-047), so the two never disagree.

The push: at most one a day for both leagues together, sent on the first run inside LEAD before the earliest tip-off
among the moves, and only when there is a move. An out starter in it isn't pushed again by the injury watch.

Game-day status (Q-057, shq/nba_status.py): a starter the official NBA injury report lists Out today (a rest day too) is a
move like any other out starter, so it rides in that one push if it hasn't gone out yet. Once today's push is out, a
change after it shows only on the site (the move is marked "new since today's lineup push"), and the injury watch doesn't
push a starter whose Out the official report backs (run.injury_watch): never a second NBA lineup push in a day."""
import datetime as dt

from . import notify
from .common import ct_label, iso, load_json, save_json
from .config import TZ
from .status import OUTISH
from .swap import eligible, playable

MIN_EDGE = 1.0                  # value per game a bench player must beat a playing starter by
LEAD = dt.timedelta(hours=3)    # send from 3h before the first affected tip-off (the watch loop runs from 2h; the hourly run before)


def value(p):
    return (p.get("cv") or {}).get("v", -99.0)


def _today(p, now):
    k = p.get("kickoff")
    return k is not None and k.astimezone(TZ).date() == now.astimezone(TZ).date()


def _why(s):
    if s.get("empty"):
        return "empty slot"
    if s["bye"]:
        return "no game today"
    if s["status"] in OUTISH:
        # the game-day reason when the NBA injury report or Sleeper decided it: "Out (rest) per NBA injury report, 5:30pm"
        return s["why"] if s.get("gd") and s.get("why") else s["status"]
    return None


def moves(league, now):
    """[{"start", "sit", "slot", "why", "lock", "text"}] for today, best first."""
    if getattr(league, "sport", "nfl") != "nba":
        return []
    bench = sorted((b for b in league.bench if playable(b, now) and _today(b, now)), key=lambda b: -value(b))
    used, out = set(), []

    def take(s, cands):
        pick = next((b for b in cands if b["id"] not in used and eligible(s["slot"], b["positions"])), None)
        if pick:
            used.add(pick["id"])
        return pick

    for s in league.starters:                        # starters who can't help today
        if s["started"]:
            continue
        why = _why(s)
        if why:
            b = take(s, bench)
            if b:
                out.append(_move(b, s, why, b["kickoff"]))
    playing = [s for s in league.starters if playable(s, now) and _today(s, now) and not s.get("empty")]
    for s in sorted(playing, key=value):              # weakest playing starters first
        b = take(s, [b for b in bench if value(b) >= value(s) + MIN_EDGE])
        if b:
            out.append(_move(b, s, f"{value(b) - value(s):+.1f} value/g", min(b["kickoff"], s["kickoff"])))
    return out


def _move(b, s, why, lock):
    sit = s["slot"] if s.get("empty") else s["name"]
    return {"start": b["name"], "start_key": b.get("key"), "sit": sit, "sit_id": s["id"], "slot": s["slot"], "why": why, "lock": lock,
            "out": s["status"] in OUTISH and not s.get("empty"),
            "text": f"Start {b['name']} ({b['team']} {b['opp'] or ''}, {ct_label(b['kickoff'])}) over {sit} at {s['slot']}: {why}"}


def _day(now):
    return now.astimezone(TZ).date().isoformat()


def _key(league, m, now):
    return f"nba-lineup:{_day(now)}:{league.key}:{m['sit_id']}:{m['start_key'] or m['start']}"


def pushed_today(now):
    """True once today's one NBA lineup push has gone out (this checkout's alert state)."""
    return f"nba-lineup:{_day(now)}" in (notify.seen() or {})


def lines(league, now):
    """The league tab's "Lineup moves" for NBA. After today's push, a move that wasn't in it says so: it's on the site
    only (no second push)."""
    ms = moves(league, now)
    if not ms or not pushed_today(now):
        return [m["text"] for m in ms]
    seen = notify.seen() or {}
    return [m["text"] + ("" if _key(league, m, now) in seen else " (new since today's lineup push; not pushed)")
            for m in ms]


def send(leagues, now):
    """One push a day for every NBA league's moves; returns the title when it sent one."""
    found = [(lg, m) for lg in leagues for m in moves(lg, now)]
    if not found:
        return None
    first = min(m["lock"] for _, m in found)
    if not (first - LEAD <= now < first):
        return None
    day = _day(now)
    n = len(found)
    title = f"NBA lineup: {n} change{'s' if n != 1 else ''} before {ct_label(first).split(' ')[1]} tip"
    body = "\n".join(f"{lg.name}: {m['text']}" for lg, m in found) + "\nESPN lineups lock at each player's tip-off."
    if not notify.push_once(f"nba-lineup:{day}", title, body, priority=4, tags=["basketball"]):
        return None
    # the injury watch would push an out starter's swap again 2h before his tip: it's in this push already. Each move
    # in it is recorded too, so a later move shows on the site as "new since today's lineup push" (lines()).
    seen = load_json(notify.ALERTS, {}) or {}
    for lg, m in found:
        if m["out"]:
            seen.setdefault(f"{lg.key}:w{lg.week}:{m['sit_id']}:swap", iso(now))
        seen.setdefault(_key(lg, m, now), iso(now))
    save_json(notify.ALERTS, seen)
    return title
