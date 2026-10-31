"""Waiver adds ranked on what they do for my lineup, each with who to drop and, in FAAB leagues, a bid range.
Pure logic: players carry "val", "ppg" and "wk" (week-by-week projections) from values.annotate.

Positions matter. An add is judged by my best lineup summed over the next few weeks, each week picked on that
week's projections, so a starter upgrade, bye-week cover and the cost of the player dropped all count; a raw
points gap between a QB and a WR never does.
- Same position (a depth swap): allowed when the add scores better (70% points per game over the next few
  weeks + 30% this week + a FantasyCalc value nudge, twice as strong in dynasty).
- Different position: only when my lineup gains at least MIN_WINDOW_GAIN points over the window, and never
  if the drop leaves that position without a backup (POSITION_FLOOR).
- Never dropped: anyone in my best lineup, and in dynasty any bench player worth STASH_VALUE or more.
- Kickers and defenses are streamed: this week only, and they only replace each other."""
from collections import Counter

from .status import OUTISH
from .swap import FLEX_SLOTS
from .trades import lineup, primary, skill_slots

STASH_VALUE = 750
MIN_EDGE = 1.0            # same-position swap: score edge needed
MIN_WINDOW_GAIN = 2.0     # cross-position swap: lineup points needed over the window
# Depth as insurance: share of a backup's points counted each week, by position and depth order. Only the top
# backup counts at QB/TE (the 2nd at QB in superflex); the top two at RB/WR, which have more starters to cover.
INSURANCE = {"QB": (0.06,), "RB": (0.15, 0.07), "WR": (0.12, 0.06), "TE": (0.06,)}
INSURANCE_SF_QB = (0.12, 0.05)
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


def weeks_of(players):
    return sorted({w for p in players for w, _ in p.get("wk") or []})


def window_total(slots, players, weeks):
    """Best lineup summed over the window, each week on that week's projections (a bye scores 0), plus the
    insurance value of the top backups at each position (INSURANCE). Without weekly projections, per-game."""
    sf = any("QB" in FLEX_SLOTS.get(s, ()) for s in slots) or slots.count("QB") > 1
    total = 0.0
    for w in weeks or [None]:
        week_pts = [{**p, "ppg": (dict(p.get("wk") or []).get(w) or 0) if w is not None else p.get("ppg", 0)}
                    for p in players if primary(p)]
        best, picks = lineup(slots, week_pts)
        starting = {p["id"] for _, p in picks}
        total += best
        for pos, weights in INSURANCE.items():
            backups = sorted((p["ppg"] for p in week_pts if primary(p) == pos and p["id"] not in starting), reverse=True)
            total += sum(wt * x for wt, x in zip(INSURANCE_SF_QB if pos == "QB" and sf else weights, backups))
    return round(total, 1)


def floor(slots):
    """Fewest players to keep at each position: its dedicated starters, plus one backup at RB and WR (and at QB
    in superflex/2QB leagues), so a cross-position drop never leaves a position with nobody behind the starters.
    A 1QB league needs no backup QB: bye weeks are already priced by window_total."""
    need = Counter(s for s in slots if s in ("QB", "RB", "WR", "TE"))
    for pos in ("RB", "WR"):
        need[pos] += 1
    if need["QB"] > 1 or any("QB" in FLEX_SLOTS.get(s, ()) for s in slots):
        need["QB"] += 1
    return need


def _role(slots, roster, after, fa, weeks):
    """Plain words for what the add does: who he starts over, or which weeks he fills in."""
    before = dict((p["id"], s) for s, p in lineup(slots, roster)[1])
    now = lineup(slots, after)[1]
    slot = next((s for s, p in now if p["id"] == fa["id"]), None)
    if slot:
        out = [p for p in roster if p["id"] in before and p["id"] not in {q["id"] for _, q in now}]
        over = f" over {out[0]['name']}" if out else ""
        return f"starts at {slot}{over}"
    covers = [w for w in weeks if any(p["id"] == fa["id"] for _, p in
              lineup(slots, [{**q, "ppg": dict(q.get("wk") or []).get(w) or 0} for q in after if primary(q)])[1])]
    if covers:   # a starter's bye, or a week he isn't projected (injury)
        return f"fills in at {primary(fa)} in week{'s' if len(covers) > 1 else ''} " + ", ".join(map(str, covers))
    return f"better backup {primary(fa)}"


def _depth(drop, roster):
    """'your RB6': where the drop sits at his position."""
    pos = primary(drop)
    same = sorted((p for p in roster if primary(p) == pos), key=lambda p: -p.get("ppg", 0))
    return f"your {pos}{next(i for i, p in enumerate(same, 1) if p is drop)}"


def adds(starters, bench, free_agents, slots, *, dynasty=False, open_spots=0, faab=None, budget=0, limit=3):
    """[{"fa", "drop" (None = open roster spot), "edge", "gain" (lineup ppg), "window" (lineup pts over the
    window), "weeks", "role", "depth", "bid" (lo, hi) or None}], best first."""
    slots = skill_slots(slots)
    roster = [p for p in starters + bench if not p.get("empty")]
    mine = {id(p) for p in roster}
    sc = lambda p: score(p, dynasty, id(p) in mine)
    need = floor(slots)
    pool = sorted((fa for fa in free_agents if fa["status"] not in OUTISH and fa["positions"] and fa["team"]),
                  key=lambda p: -sc(p))[:SCAN]
    out, used_fa, used_kind = [], set(), set()
    while len(out) < limit:
        protected = {p["id"] for _, p in lineup(slots, roster)[1]}
        droppable = [b for b in bench if b["id"] not in protected and not b.get("empty")
                     and not (dynasty and b.get("val", 0) >= STASH_VALUE)]
        weeks = weeks_of(roster + pool)
        base = window_total(slots, roster, weeks)
        best = None
        for fa in pool:
            if fa["id"] in used_fa:
                continue
            pos = primary(fa)
            if not pos:   # streaming a kicker/defense (one of each): swap with the one you have, starter or not
                kind = fa["positions"][0]
                if kind in used_kind:
                    continue
                cands = [b for b in roster if kind in b["positions"] and not b["started"]]
                drop = min(cands, key=sc, default=None)
                if drop is None:
                    continue
                edge = round(sc(fa) - sc(drop), 1)
                if edge >= MIN_EDGE and (best is None or edge > best["rank"]):
                    best = {"fa": fa, "drop": drop, "edge": edge, "gain": edge, "window": None, "rank": edge,
                            "role": None, "depth": None}
                continue
            counts = Counter(primary(p) for p in roster)
            options = [None] if open_spots > 0 else [
                b for b in droppable if primary(b) and
                (primary(b) == pos or counts[primary(b)] - 1 >= need.get(primary(b), 0))]
            for drop in options:
                after = [p for p in roster if p is not drop] + [fa]
                window = round(window_total(slots, after, weeks) - base, 1)
                edge = round(sc(fa) - (sc(drop) if drop else 0), 1)
                if drop is not None and primary(drop) == pos:
                    ok = edge >= MIN_EDGE          # depth swap at the same position
                else:
                    ok = window >= MIN_WINDOW_GAIN  # cross-position (or open spot): must lift the lineup
                if not ok:
                    continue
                # lineup points first; FantasyCalc value breaks ties and counts more in dynasty
                rank = window + (fa.get("val", 0) - (drop.get("val", 0) if drop else 0)) / (250 if dynasty else 1000)
                if best is None or rank > best["rank"]:
                    gain = round(lineup(slots, after)[0] - lineup(slots, roster)[0], 1)
                    best = {"fa": fa, "drop": drop, "edge": edge, "gain": gain, "window": window, "rank": rank,
                            "role": _role(slots, roster, after, fa, weeks),
                            "depth": _depth(drop, roster) if drop else None}
        if best is None:
            break
        fa, drop = best["fa"], best["drop"]
        used_fa.add(fa["id"])
        if not primary(fa):
            used_kind.add(fa["positions"][0])
        roster = [p for p in roster if p is not drop] + [fa]
        bench = [b for b in bench if b is not drop]   # a suggested add is never a later suggestion's drop
        if drop is None:
            open_spots -= 1
        best["weeks"] = len(weeks) if primary(fa) else None
        best["bid"] = (bid(best["gain"], budget, faab, stream=not primary(fa))
                       if faab is not None and budget else None)
        out.append(best)
    return out


def line(a):
    fa, drop = a["fa"], a["drop"]
    pos = (primary(fa) or fa["positions"][0])
    if not primary(fa):   # streamed kicker/defense
        text = f"Add {fa['name']} ({pos}, {fa['team']}, {fa['proj']} proj this week), drop {drop['name']} ({drop['proj']} proj)"
    else:
        text = f"Add {fa['name']} ({pos}, {fa['team']}, {fa['ppg']}/gm"
        text += f", value {fa['val']:,})" if fa.get("val") else ")"
        if drop is None:
            text += " into your open roster spot"
        else:
            text += f" for {drop['name']} ({primary(drop)}, {_or(a['depth'])}, {drop['ppg']}/gm)"
        bits = [a["role"]] if a.get("role") else []
        if a["gain"] > 0:
            bits.append(f"lineup +{a['gain']}/gm")
        if a.get("window") and a["window"] > 0 and a.get("weeks"):
            bits.append(f"+{a['window']:g} pts over the next {a['weeks']} weeks")
        if bits:
            text += ": " + ", ".join(bits)
    if a["bid"]:
        lo, hi = a["bid"]
        text += f". Bid ${lo}" + (f"–{hi}" if hi != lo else "")
    return text


def _or(depth):
    return depth or "bench"
