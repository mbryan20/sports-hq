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
                          "text": f"{label} ({s['slot']}) {why} → {fix}"})
        elif s["status"] == "Q" and _today(s["kickoff"], now):
            items.append({"league": league.name, "urgent": False,
                          "text": f"{s['name']} ({s['slot']}) is Questionable, plays {ct_label(s['kickoff'])}"})
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
    """Guillotine: projected rank among teams still alive; bottom 3 is urgent."""
    standing = getattr(league, "standing", None)
    if not standing:
        return None
    rank, n, gap = standing["rank"], standing["n"], standing["gap"]
    danger = rank > n - 3
    return {"league": league.name, "urgent": danger,
            "text": (f"projected {rank} of {n} this week" +
                     (f", {gap:+.1f} pts vs the lowest other team" if gap is not None else "") +
                     (" — DANGER ZONE, check the War Room" if danger else ""))}


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
