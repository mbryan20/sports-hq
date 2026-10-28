"""Waiver adds ranked on rest-of-season value, each with who to drop and, in FAAB leagues, a bid range.
Pure logic: players carry "val" and "ppg" from values.annotate.

Score = 70% points per game over the next few weeks (ROS) + 30% this week's projection + a nudge for
FantasyCalc value (twice as strong in dynasty). The bid range follows how much the add lifts my best lineup. Kickers and defenses are streamed: this week only,
and they only replace each other. An add that wouldn't make my best lineup only replaces a player at
his own position (a depth upgrade), so a backup QB never costs a starting-calibre RB. Never suggested
as drops: anyone in my best lineup, and in dynasty any bench player worth STASH_VALUE or more in trade."""
from .status import OUTISH
from .trades import lineup, primary, skill_slots

STASH_VALUE = 750
MIN_EDGE = 1.0
SCAN = 60                 # free agents considered, best score first
# FAAB range by how much the add lifts my best lineup (points per game): (gain below, % of season budget)
BID_TIERS = ((1, .01, .03), (2.5, .03, .08), (4, .08, .15), (float("inf"), .15, .25))


def score(p, dynasty=False, rostered=False):
    """Kickers/defenses: this week's projection. A rostered player's bye week doesn't make him droppable."""
    if not primary(p):
        return p["proj"]
    week = p.get("ppg", 0) if rostered and p["bye"] else p["proj"]
    return round(0.7 * p.get("ppg", 0) + 0.3 * week + p.get("val", 0) / (500 if dynasty else 1000), 1)


def bid(gain, budget, left, stream=False):
    """FAAB range as a share of the season budget, capped by what's left. Streamed K/DEF: $0-1."""
    if stream:
        return 0, min(1, left)
    lo, hi = next((lo, hi) for cut, lo, hi in BID_TIERS if gain < cut)
    lo, hi = max(1, round(budget * lo)), max(1, round(budget * hi))
    return min(lo, left), min(hi, left)


def adds(starters, bench, free_agents, slots, *, dynasty=False, open_spots=0, faab=None, budget=0, limit=3):
    """[{"fa", "drop" (None = open roster spot), "edge", "gain" (lineup ppg), "bid" (lo, hi) or None}]"""
    slots = skill_slots(slots)
    roster = [p for p in starters + bench if not p.get("empty")]
    mine = {id(p) for p in roster}
    sc = lambda p: score(p, dynasty, id(p) in mine)
    protected = {p["id"] for _, p in lineup(slots, roster)[1]}
    droppable = [b for b in bench if b["id"] not in protected and not b.get("empty")
                 and not (dynasty and b.get("val", 0) >= STASH_VALUE)]
    pool = sorted((fa for fa in free_agents if fa["status"] not in OUTISH and fa["positions"] and fa["team"]),
                  key=lambda p: -sc(p))[:SCAN]
    out, used = [], set()
    for fa in pool:
        if len(out) == limit:
            break
        pos = primary(fa)
        if open_spots > 0 and pos:
            drop, edge = None, sc(fa)
        else:
            if pos:
                starts = any(p["id"] == fa["id"] for _, p in lineup(slots, roster + [fa])[1])
                cands = [b for b in droppable if primary(b) and (starts or primary(b) == pos)]
            else:  # streaming a kicker/defense (one of each): swap with the one you have, starter or not
                kind = fa["positions"][0]
                if kind in used:
                    continue
                cands = [b for b in roster if kind in b["positions"] and not b["started"] and b["id"] not in used]
            drop = min(cands, key=sc, default=None)
            if drop is None:
                continue
            edge = round(sc(fa) - sc(drop), 1)
        if edge < MIN_EDGE:
            continue
        after = [p for p in roster if p is not drop] + [fa]
        gain = round(lineup(slots, after)[0] - lineup(slots, roster)[0], 1) if pos else edge
        roster = after
        if drop is None:
            open_spots -= 1
        else:
            used |= {drop["id"]} | (set() if pos else {fa["positions"][0]})
            droppable = [b for b in droppable if b is not drop]
        out.append({"fa": fa, "drop": drop, "edge": edge, "gain": gain,
                    "bid": bid(gain, budget, faab, stream=not pos) if faab is not None and budget else None})
    return out


def line(a):
    fa, drop = a["fa"], a["drop"]
    pos = (primary(fa) or fa["positions"][0])
    how = (f"{fa['ppg']}/gm ROS" if primary(fa) else f"{fa['proj']} proj this week")
    text = f"Add {fa['name']} ({pos}, {fa['team']}, {how}" + (f", value {fa['val']:,}" if fa.get("val") else "") + ")"
    if drop is None:
        text += " into your open roster spot"
    else:
        dhow = f"{drop['ppg']}/gm" if primary(drop) else f"{drop['proj']} proj"
        text += f", drop {drop['name']} ({dhow})"
    if a["gain"] > 0 and primary(fa):
        text += f", lineup +{a['gain']}/gm"
    if a["bid"]:
        lo, hi = a["bid"]
        text += f". Bid ${lo}" + (f"–{hi}" if hi != lo else "")
    return text
