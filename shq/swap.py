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


def plan_injury_swaps(starters, bench, now, lead_hours=2):
    """For each OUT/IR/inactive starter inside its pre-kickoff window, pick the best healthy bench
    player who can legally fill that slot. Returns [{out, in (or None), slot}]."""
    used, plan = set(), []
    for s in starters:
        if s["status"] not in OUTISH or not in_watch(s, now, lead_hours):
            continue
        options = [b for b in bench
                   if b["id"] not in used and playable(b, now) and eligible(s["slot"], b["positions"])]
        pick = max(options, key=lambda b: b["proj"], default=None)
        if pick:
            used.add(pick["id"])
        plan.append({"out": s, "in": pick, "slot": s["slot"]})
    return plan


def start_sit(starters, bench, limit=3, min_gain=1.0):
    """Greedy best bench→starter upgrades for the week ahead. Dead slots (OUT/bye) count as 0."""
    def value(p):
        return 0.0 if (p["status"] in OUTISH or p["bye"] or p.get("empty")) else p["proj"]

    live_bench = [b for b in bench if b["status"] not in OUTISH and not b["bye"]]
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
