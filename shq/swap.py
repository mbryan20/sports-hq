"""Pure lineup logic: who to swap during the injury watch, and weekly start/sit ideas.

A player here is a dict with at least:
  id, name, slot, positions, status, kickoff (datetime|None), started (bool), bye (bool), proj (float)
"""
import datetime as dt

from .status import OUTISH

FLEX_SLOTS = {
    "FLEX": {"RB", "WR", "TE"}, "W/R/T": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"}, "Q/W/R/T": {"QB", "RB", "WR", "TE"}, "OP": {"QB", "RB", "WR", "TE"},
    "WRRB_FLEX": {"WR", "RB"}, "W/R": {"WR", "RB"},
    "REC_FLEX": {"WR", "TE"}, "W/T": {"WR", "TE"},
}


def eligible(slot, positions):
    return slot in positions or bool(FLEX_SLOTS.get(slot, set()) & set(positions))


def playable(p, now):
    """Healthy, has a game this week, and that game hasn't locked."""
    return (p["status"] is None and not p["bye"] and p["kickoff"] is not None
            and not p["started"] and now < p["kickoff"])


def in_watch(p, now, lead_hours):
    k = p["kickoff"]
    return k is not None and not p["started"] and k - dt.timedelta(hours=lead_hours) <= now < k


def strength(p):
    """Points projection, or the category value per game in NBA category leagues (no points there; shq/nba_values.py)."""
    return (p.get("cv") or {}).get("v", p["proj"])


def strength_text(p):
    """'12.3 proj', or 'value +1.9/g, #33' for an NBA player with a category value."""
    v = p.get("cv")
    return f"value {v['v']:+.1f}/g, #{v['rk']}" if v else f"{p['proj']} proj"


MIN_FILL = 1.0   # a points-league fill-in projected under this is no fix (Nov 10: "start Carson Wentz", projected 0)
FA_EDGE = 5.0    # a free agent this many points better than the best bench fill-in is the real fix
Q_EDGE = 3.0     # a Questionable free agent this much better than the best healthy one is named instead, marked (Q)


def slot_fa(slot, free_agents, now, skip=()):
    """Best playable free agent who can legally fill `slot`, by this week's projection (flex and superflex slots
    take every position they allow, so a dead QB in SUPER_FLEX/OP can be covered by a QB).
    A Questionable free agent (not one whose Out is only unconfirmed: `conflict`) is named only when he projects
    Q_EDGE+ more than the best healthy one, and the caller shows "(Q)" (Nov 10: Drew Lock, Q but expected to play,
    18.7 vs Kyle McCord 12.4; ESPN tags many players a generic Q on Tuesdays)."""
    def ok(p, q):
        if p["id"] in skip or not p.get("positions") or not eligible(slot, p["positions"]):
            return False
        if not q:
            return playable(p, now)
        return (p["status"] == "Q" and not p.get("conflict") and not p["bye"] and p["kickoff"] is not None
                and not p["started"] and now < p["kickoff"])
    key = lambda p: (p["proj"], p.get("owned", 0))
    best = max((p for p in free_agents if ok(p, False)), key=key, default=None)
    q = max((p for p in free_agents if ok(p, True)), key=key, default=None)
    if q and (best is None or q["proj"] - best["proj"] >= Q_EDGE):
        return q
    return best


def q_tag(p):
    """" (Q)" for a Questionable player named in a fix, else ""."""
    return " (Q)" if p.get("status") == "Q" else ""


def fa_over_bench(bench_pick, fa):
    """Points leagues: True when adding `fa` is the better fix for a dead starter than `bench_pick` (None = no
    bench fit): the bench option projects under MIN_FILL, or the free agent beats him by FA_EDGE or more.
    Suggestion only: nothing here ever adds or drops."""
    if fa is None:
        return False
    if bench_pick is None:
        return True
    return fa["proj"] > bench_pick["proj"] and (bench_pick["proj"] < MIN_FILL or fa["proj"] - bench_pick["proj"] >= FA_EDGE)


def plan_injury_swaps(starters, bench, now, lead_hours=2):
    """For each OUT/IR/inactive starter inside its pre-kickoff window, pick the best healthy bench
    player who can legally fill that slot. Returns [{out, in (or None), slot}]."""
    used, plan = set(), []
    for s in starters:
        if s["status"] not in OUTISH or not in_watch(s, now, lead_hours):
            continue
        options = [b for b in bench
                   if b["id"] not in used and playable(b, now) and eligible(s["slot"], b["positions"])]
        pick = max(options, key=strength, default=None)
        if pick:
            used.add(pick["id"])
        plan.append({"out": s, "in": pick, "slot": s["slot"]})
    return plan


def start_sit(starters, bench, limit=3, min_gain=1.0):
    """Greedy best bench→starter upgrades for the week ahead. Dead slots (OUT/bye) count as 0.
    A bench player whose Out is unconfirmed (status.confirm shows him as Q with `conflict`, e.g. Sleeper says
    Out but ESPN's Out note is from last week) is never moved in: unconfirmed means don't act either way
    (Nov 10: "Start Garrett Wilson" while Sleeper listed him Out)."""
    def value(p):
        return 0.0 if (p["status"] in OUTISH or p["bye"] or p.get("empty")) else p["proj"]

    live_bench = [b for b in bench if b["status"] not in OUTISH and not b["bye"] and not b.get("conflict")]
    pairs = sorted(
        ((value(b) - value(s), s, b) for s in starters for b in live_bench
         if eligible(s["slot"], b["positions"]) and not s["started"] and not b["started"]),
        key=lambda t: -t[0])
    used, out = set(), []
    for gain, s, b in pairs:
        if gain < min_gain or s["id"] in used or b["id"] in used:
            continue
        used.update((s["id"], b["id"]))
        out.append((s, b, gain))
        if len(out) == limit:
            break
    return out


def fa_adds(roster, free_agents, limit=3):
    """Top free agents by projected gain over your weakest rostered player at that position."""
    worst = {}
    for p in roster:
        pos = p["positions"][0] if p["positions"] else None
        # byes and injuries say nothing about whether he's droppable (think dynasty stashes)
        if p["bye"] or p["status"] in OUTISH:
            continue
        v = p["proj"]
        if pos and (pos not in worst or v < worst[pos][0]):
            worst[pos] = (v, p)
    picks = []
    for fa in free_agents:
        if fa["status"] in OUTISH or fa["bye"] or not fa["positions"]:
            continue
        pos = fa["positions"][0]
        base, who = worst.get(pos, (0.0, None))
        picks.append((fa["proj"] - base, fa, who))
    picks.sort(key=lambda t: -t[0])
    return [t for t in picks if t[0] > 0][:limit]
