"""Daily 8am CT digest: what needs a look today across every league. Pure logic, no AI.

Each item is {"league", "text", "urgent"}. The digest pushes only when at least one item is urgent
(a starter who can't play, an empty slot, a guillotine danger zone, Friday picks deadlines);
otherwise it just updates the Today tab."""
import datetime as dt

from .common import ct_label
from .config import DIGEST_HOUR, DIGEST_PUSH_UNTIL, TZ
from .status import OUTISH
from .swap import eligible, playable

DEAD = OUTISH | {"D"}
DANGER_CUT = 0.20   # guillotine elimination chance that counts as urgent


def due(now, last_generated):
    """True once per day, on the first run at or after DIGEST_HOUR CT."""
    local = now.astimezone(TZ)
    anchor = local.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    return local >= anchor and (last_generated is None or last_generated < anchor)


def push_window(now):
    """A digest that only got its run late in the day goes to the Today tab without a push."""
    return now.astimezone(TZ).hour < DIGEST_PUSH_UNTIL


def _today(k, now):
    return k is not None and k.astimezone(TZ).date() == now.astimezone(TZ).date()


def _problem(p, nba):
    if p.get("empty"):
        return "empty slot"
    if p["bye"]:
        return "no game today" if nba else "on BYE"
    if p["status"] in DEAD:
        return p["status"] + (f" ({p['why']})" if p.get("why") else "")
    return None


def cite(p, limit=160):
    """The dated ESPN injury-report note behind a status, so every status call names its source."""
    n = p.get("news")
    if not n:
        return ""
    note = n["note"] if len(n["note"]) <= limit else n["note"][:limit].rsplit(" ", 1)[0] + "…"
    return f" [ESPN{', ' + ct_label(n['at']) if n.get('at') else ''}: {note}]"


def _fix(league, starter, used, now):
    bench = [b for b in league.bench if b["id"] not in used and playable(b, now)
             and eligible(starter["slot"], b["positions"])]
    pick = max(bench, key=lambda b: (b["proj"], b.get("owned", 0)), default=None)
    if pick:
        used.add(pick["id"])
        return f"start {pick['name']}" + (f" ({pick['proj']} proj)" if pick["proj"] else ""), True
    fa = league.best_fa(starter["positions"] or [starter["slot"]], now) if league.free_agents else None
    if fa:
        return f"no bench fit; best FA {fa['name']} ({fa['team']})", False
    return "no healthy bench fit", False


def league_items(league, now):
    nba = getattr(league, "sport", "nfl") == "nba"
    items, used = [], set()
    for s in league.starters:
        if s["started"]:
            continue
        why = _problem(s, nba)
        if why:
            fix, from_bench = _fix(league, s, used, now)
            # NBA lineups reset daily and off nights are routine: push only when the bench can cover it
            if nba and s["bye"] and not from_bench:
                continue
            label = s["name"] if not s.get("empty") else s["slot"]
            items.append({"league": league.name, "urgent": from_bench or not nba,
                          "text": f"{label} ({s['slot']}) {why} → {fix}" + cite(s)})
        elif s.get("conflict"):
            # sources disagree on whether he plays: say so, never bench him on it
            items.append({"league": league.name, "urgent": False,
                          "text": f"{s['name']} ({s['slot']}): {s['why']}. Check before benching" + cite(s)})
        elif s["status"] == "Q" and _today(s["kickoff"], now):
            items.append({"league": league.name, "urgent": False,
                          "text": f"{s['name']} ({s['slot']}) is Questionable, plays {ct_label(s['kickoff'])}" + cite(s)})
    if nba:
        playing = sum(1 for s in league.starters if playable(s, now))
        if playing:
            items.append({"league": league.name, "urgent": False,
                          "text": f"{playing} of {len(league.starters)} starters play tonight"})
    else:
        today = sorted(s["kickoff"] for s in league.starters if _today(s["kickoff"], now) and not s["started"])
        if today:
            items.append({"league": league.name, "urgent": False,
                          "text": f"{len(today)} starters play today, first locks {ct_label(today[0])}"})
    standing = standing_item(league)
    if standing:
        items.append(standing)
    captured = getattr(league, "captured", None)  # laptop-read leagues (Kosmonauts, private ESPN)
    if captured and any(i["urgent"] for i in items):
        items.append({"league": league.name, "urgent": False,
                      "text": f"(roster as of the laptop read {ct_label(captured)}; check it's still current)"})
    return items


def standing_item(league):
    """Guillotine: projected rank among teams still alive; bottom 3, or an elimination chance over
    DANGER_CUT (from shq/guillotine.py), is urgent."""
    standing = getattr(league, "standing", None)
    if not standing:
        return None
    rank, n, gap, cut = standing["rank"], standing["n"], standing["gap"], standing.get("cut")
    danger = rank > n - 3 or (cut or 0) > DANGER_CUT
    return {"league": league.name, "urgent": danger,
            "text": (f"projected {rank} of {n} this week" +
                     (f", {gap:+.1f} pts vs the lowest other team" if gap is not None else "") +
                     (f", {_pct(cut)} chance of being cut" if cut is not None else "") +
                     (" — DANGER ZONE, check the War Room" if danger else ""))}


def danger_push(league):
    """Guillotine: (key, title, message) for a once-a-week push when my elimination chance tops
    DANGER_CUT, whenever in the week that happens (the 8am digest also lists it as urgent)."""
    g = (getattr(league, "standing", None) or {})
    if (g.get("cut") or 0) <= DANGER_CUT:
        return None
    return (f"{league.key}:w{league.week}:cut-danger", f"{league.name}: {_pct(g['cut'])} elimination risk",
            f"Projected {g['rank']} of {g['n']} ({g['gap']:+.1f} pts vs the lowest other team). "
            "Check the lineup and the What to do card.")


def _pct(x):
    return "<1%" if 0 < x < 0.005 else f"{round(x * 100)}%"


def picks_items(cards, now):
    """Friday: the week's pick'em deadlines."""
    if now.astimezone(TZ).weekday() != 4:
        return []
    return [{"league": "Picks", "urgent": True, "text": f"{c['title']}: {c['deadline']}"}
            for c in (cards or {}).get("cards", []) if c.get("deadline")]


def build(leagues, now, cards=None):
    items = []
    for lg in leagues:
        items += league_items(lg, now)
    return items + picks_items(cards, now)


def message(items):
    urgent = [i for i in items if i["urgent"]]
    title = (f"Today: {len(urgent)} thing{'s' if len(urgent) != 1 else ''} to fix" if urgent
             else "Today: all clear")
    lines = [f"{'⚠ ' if i['urgent'] else ''}{i['league']}: {i['text']}" for i in items]
    return title, "\n".join(lines)[:3800] or "Every lineup looks set."
