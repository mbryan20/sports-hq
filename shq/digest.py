"""Daily 8am CT digest: what needs a look today across every league. Pure logic, no AI.

Each item is {"league", "text", "urgent"}. The digest pushes only when at least one item is urgent
(a starter who can't play, an empty slot, a guillotine danger zone, Friday picks deadlines);
otherwise it just updates the Today tab."""
import datetime as dt
import traceback

from . import radar, waivers
from .common import ct_label
from .config import DIGEST_HOUR, DIGEST_PUSH_UNTIL, TZ
from .status import OUTISH, espn_word
from .swap import eligible, fa_over_bench, playable, q_tag, slot_fa, strength, strength_text

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
    # dated, not just a weekday: a last-week note must not read as today's
    when = f"{n['at'].astimezone(TZ).strftime('%b')} {n['at'].astimezone(TZ).day} {ct_label(n['at']).split(' ')[1]}" if n.get("at") else ""
    return f" [ESPN{', ' + when if when else ''}: {note}]"


def free_agents(league):
    """The league's free agents, or [] when they can't be read (a failed read never blocks the lineup fixes)."""
    try:
        return list(league.free_agents or [])
    except Exception:
        traceback.print_exc()
        return []


def _key(name):
    """Jr./III-blind name: War Room v2 says "Harold Fannin", Sleeper "Harold Fannin Jr."."""
    words = "".join(c if c.isalnum() or c.isspace() else " " for c in (name or "").lower()).split()
    while len(words) > 1 and words[-1] in ("jr", "sr", "ii", "iii", "iv", "v"):
        words.pop()
    return " ".join(words)


def v2_calls(league):
    """Guillotine with War Room v2 as the bid source (its bids.json is this week's, shq/guillotine.py): {"rows":
    {sleeper id: v2 row}, "claims": ids that need a waiver claim, "keep": name keys of players v2 drops for a
    claim it recommends}. None otherwise (other leagues, or v2 stale and the dashboard model's bids in charge)."""
    g = getattr(league, "guillotine", None) or {}
    if (g.get("bid_source") or {}).get("name") != "War Room v2":
        return None
    rows = {str(b["sid"]): b for b in g.get("bids") or [] if b.get("v2") and b.get("sid") is not None}
    claims = {sid for sid, b in rows.items() if not b.get("free")} | {str(i) for i in g.get("waiting") or []}
    keep = {_key(b["drop"]) for b in rows.values()
            if not b.get("free") and b.get("drop") and b.get("call") in ("bid", "coin flip")}
    return {"rows": rows, "claims": claims, "keep": keep}


def fix_pool(league, v2=None):
    """Free agents a lineup fix may name. Guillotine with War Room v2 current: only players you can add now (no waiver
    claim: they can't be added before the Wednesday run), so a fix never contradicts v2's bid list (Nov 10: "add
    Harold Fannin Jr. ... and start him" while v2 had him as a $1 claim and Pat Freiermuth was a free add)."""
    fas = free_agents(league)
    v2 = v2_calls(league) if v2 is None else v2
    return [p for p in fas if str(p["id"]) not in v2["claims"]] if v2 else fas


def _fix(league, starter, used, now, spots):
    """(fix text, from_bench). `used` holds bench and free-agent ids already named for another slot; `spots` is
    [open roster spots left], spent by each free-agent suggestion. Football: a bench fill-in projected under
    MIN_FILL, or one a free agent beats by FA_EDGE+, becomes "add <FA> and start him" (Nov 10: "start Carson
    Wentz" while he projected 0 and Drew Lock 15.7). Suggestions only: nothing is ever added or dropped."""
    bench = [b for b in league.bench if b["id"] not in used and playable(b, now)
             and eligible(starter["slot"], b["positions"])]
    # NBA category leagues have no points: rank by category value (shq/nba_values.py) when the run has it
    pick = max(bench, key=lambda b: (strength(b), b.get("owned", 0)), default=None)
    if getattr(league, "sport", "nfl") == "nba":   # category leagues: no points to compare, so no FA threshold
        if pick:
            used.add(pick["id"])
            return f"start {pick['name']}" + (f" ({strength_text(pick)})" if pick["proj"] or pick.get("cv") else ""), True
        fa = league.best_fa(starter["positions"] or [starter["slot"]], now) if league.free_agents else None
        if fa:
            return f"no bench fit; best FA {fa['name']} ({fa['team']})", False
        return "no healthy bench fit", False
    v2 = v2_calls(league)
    fa = slot_fa(starter["slot"], fix_pool(league, v2), now, skip=used)
    if not fa_over_bench(pick, fa):
        if pick:
            used.add(pick["id"])
            return f"start {pick['name']} ({strength_text(pick)})", True
        return "no healthy bench fit", False
    used.add(fa["id"])
    row = (v2 or {}).get("rows", {}).get(str(fa["id"]))
    room = (_v2_room(league, row, used) if row else None) or _room(league, fa, used, spots, (v2 or {}).get("keep"))
    text = f"add {fa['name']} ({fa.get('team') or 'FA'}{q_tag(fa)}, {fa['proj']} proj){room or ''} and start him"
    if pick and pick["proj"] > 0:
        text += f" (or start {pick['name']}, {strength_text(pick)})"
    elif pick:
        text += f" ({pick['name']} projects {pick['proj']})"
    if room is None:
        text += "; needs a roster spot"
    return ("" if pick else "no bench fit: ") + text, False


def _v2_room(league, row, used):
    """War Room v2's own drop for the player it lists (its "Add free" call), so the fix makes v2's move; None when v2
    names no drop (an open spot) or its drop is already spent on another fix."""
    name = row.get("drop")
    mine = next((p for p in league.bench + league.starters if _key(p["name"]) == _key(name)), None) if name else None
    if not mine or mine["id"] in used:
        return None
    used.add(mine["id"])
    return f", drop {mine['name']} ({mine['proj']} proj) as War Room v2 says,"


def _room(league, fa, used, spots, keep=None):
    """Where the add goes: an open roster spot, else the drop shq/waivers.py would pick for him (needs the
    FantasyCalc values), else None (no drop named). `keep`: name keys never named as the drop (guillotine: players
    War Room v2 drops for a waiver claim it recommends)."""
    if spots[0] > 0:
        spots[0] -= 1
        return " into your open roster spot"
    drop = None
    if getattr(league, "_valued", False) and "ppg" in fa and getattr(league, "slots", None):
        try:
            bench = [b for b in league.bench if b["id"] not in used and _key(b["name"]) not in (keep or ())]
            found = waivers.adds(league.starters, bench, [fa], league.slots,
                                 dynasty=bool(getattr(league, "dynasty", False)), limit=1)
            drop = found[0]["drop"] if found else None
        except Exception:
            traceback.print_exc()
    if drop:
        used.add(drop["id"])
        return f", drop {drop['name']} ({drop['proj']} proj),"
    return None


def league_items(league, now):
    nba = getattr(league, "sport", "nfl") == "nba"
    items, used, spots = [], set(), [getattr(league, "open_spots", 0) or 0]
    for p in getattr(league, "ir_blocked", []):
        # first and urgent in every league: it blocks every add and drop, including the fixes below (Stempak and
        # Ball is Life, Nov 10); in football he may also be a missed starter
        items.append({"league": league.name, "urgent": True,
                      "text": f"Move {p['name']} out of IR: ESPN lists him {_ir_label(p, nba)}, "
                              f"so ESPN blocks adds and drops until he's on your bench; do this before any add or drop"
                              + cite(p)})
    for s in league.starters:
        if s["started"]:
            continue
        why = _problem(s, nba)
        if why:
            fix, from_bench = _fix(league, s, used, now, spots)
            # NBA lineups reset daily and off nights are routine: list it only when the bench can cover it. NBA lineup
            # fixes aren't urgent here: shq/nba_lineup.py pushes them once a day before the first tip-off
            if nba and s["bye"] and not from_bench:
                continue
            label = s["name"] if not s.get("empty") else s["slot"]
            items.append({"league": league.name, "urgent": not nba,
                          "text": f"{label} ({s['slot']}) {why} → {fix}" + cite(s)})
        elif s.get("conflict"):
            # sources disagree on whether he plays: say so, never bench him on it
            items.append({"league": league.name, "urgent": False,
                          "text": f"{s['name']} ({s['slot']}): {s['why']}. Check before benching" + cite(s)})
        elif s["status"] == "Q" and _today(s["kickoff"], now):
            items.append({"league": league.name, "urgent": False,
                          "text": f"{s['name']} ({s['slot']}) is {_q_label(s, nba)}, plays {ct_label(s['kickoff'])}" + cite(s)})
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


def _ir_label(p, nba):
    return {None: "as active", "Q": _q_label(p, nba), "D": "Doubtful"}.get(p["status"], p["status"])


def _q_label(p, nba):
    """NBA's Q is ESPN's day-to-day, which runs from probable to doubtful: say which when ESPN's note does (Giannis,
    Nov 10: "Questionable" while the note said probable)."""
    if not nba:
        return "Questionable"
    word = espn_word((p.get("news") or {}).get("note"))
    return "day-to-day" + (f" (ESPN: {word})" if word else "")


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
        items += league_items(lg, now) + radar.digest_items(lg)   # NBA: rising players, shrinking roles (shq/radar.py)
    return items + picks_items(cards, now)


def message(items):
    urgent = [i for i in items if i["urgent"]]
    title = (f"Today: {len(urgent)} thing{'s' if len(urgent) != 1 else ''} to fix" if urgent
             else "Today: all clear")
    lines = [f"{'⚠ ' if i['urgent'] else ''}{i['league']}: {i['text']}" for i in items]
    return title, "\n".join(lines)[:3800] or "Every lineup looks set."
