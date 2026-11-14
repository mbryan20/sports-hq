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
- Kickers and defenses are streamed: this week only, and they only replace each other.
- A handcuff (rule 14, fantasy-rules.md) is dropped only when the add clearly beats his injury insurance, and the
  step then spells out the trade-off (cuff_check)."""
from collections import Counter

from .status import DEAD, OUTISH
from .swap import FLEX_SLOTS, handcuff_of
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
# Rule 14 (fantasy-rules.md, Nov 14: "Braelon Allen is probably the only reason I survived this long"): handcuffs
MISS_WEEK = 0.12          # Claude's estimate of a typical RB's weekly chance to miss a game
MISS_TAG = {"D": 0.75, "Q": 0.25}   # this week's chance he misses, by his tag (Out/IR: already in the projections)
CUFF_SHARE = 0.85         # backup's points as the starter, as a share of the starter's projection (no history)
CUFF_HIST_MIN = 2         # weeks the starter sat that the backup's own average needs
CUFF_MARGIN = 2.0         # the add's window gain must beat this many times the insurance
CUFF_BLOCK = DEAD | {"Q"}  # starter tagged Q/D/Out/IR: his handcuff is never dropped


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


def _pts(p, w):
    """His projection for week w (None on a bye); per game when there are no week-by-week numbers."""
    if w is None or not p.get("wk"):
        return p.get("ppg", 0)
    return dict(p["wk"]).get(w)


def _as_starter(cuff, starter, w):
    """(points, from history) the handcuff scores in a week his starter sits: his own average over past weeks the
    starter didn't play ("hist": {week: points} for games each played, CUFF_HIST_MIN+ such weeks), else
    CUFF_SHARE of the starter's projection that week."""
    mine, his = cuff.get("hist") or {}, starter.get("hist") or {}
    if mine and his:
        played = {str(k) for k, x in his.items() if x is not None}
        sat = [x for k, x in mine.items() if x is not None and str(k) not in played]
        if len(sat) >= CUFF_HIST_MIN:
            return sum(sat) / len(sat), True
    return CUFF_SHARE * (_pts(starter, w) or 0), False


def cuff_check(drop, roster, after, slots, weeks, guillotine=False):
    """Rule 14: None when `drop` isn't a handcuff, else the side-by-side and whether the drop may go ahead ("ok").
    Each week: the add's lineup gain, and the insurance the handcuff gives = chance his starter misses that week x
    (my lineup with the handcuff starting − my lineup with whoever would start instead, from the roster after the
    move). The drop goes ahead only when the add's gain over the window beats CUFF_MARGIN x the insurance, in the
    guillotine also this week (surviving this week's cut beats upside), and never while the starter is tagged."""
    starter = handcuff_of(drop, roster)
    if starter is None:
        return None
    tag = starter.get("status")
    rest = [q for q in after if q is not starter and q is not drop]
    rows = []
    for i, w in enumerate(weeks or [None]):
        span = [w] if w is not None else []
        gain = round(window_total(slots, after, span) - window_total(slots, roster, span), 1)
        # this week's tag sets this week's chance; Out/IR is already in the projections
        miss = (0.0 if tag in OUTISH else MISS_TAG.get(tag, MISS_WEEK)) if i == 0 else MISS_WEEK
        est, from_hist = _as_starter(drop, starter, w)
        row = {"week": w, "gain": gain, "miss": miss, "est": est, "hist": from_hist, "ins": 0.0, "instead": None}
        if _pts(starter, w) is not None:   # their bye: nothing to cover
            at = lambda qs: [{**q, "ppg": _pts(q, w) or 0} for q in qs if primary(q)]
            without, wo_picks = lineup(slots, at(rest))
            with_cuff, w_picks = lineup(slots, at(rest) + [{**drop, "ppg": est}])
            row["ins"] = round(miss * max(0.0, with_cuff - without), 2)
            ids = {q["id"] for _, q in w_picks}
            row["instead"] = next((q for _, q in wo_picks if q["id"] not in ids), None)
            row["starts"] = any(q["id"] == drop["id"] for _, q in w_picks)
        rows.append(row)
    gain, ins = sum(r["gain"] for r in rows), sum(r["ins"] for r in rows)
    blocked = tag in CUFF_BLOCK or bool(starter.get("conflict"))
    ok = (not blocked and gain > CUFF_MARGIN * ins
          and (not guillotine or rows[0]["gain"] >= rows[0]["ins"]))
    return {"ok": ok, "starter": starter, "cuff": drop, "rows": rows, "gain": round(gain, 1), "ins": round(ins, 1),
            "blocked": blocked, "guillotine": guillotine}


def cuff_text(c, fa):
    """The rule 14 side-by-side in plain words, for a handcuff drop that passed cuff_check."""
    cuff, st, rows = c["cuff"]["name"], c["starter"]["name"], c["rows"]
    live = [r for r in rows if r.get("instead") is not None or r["ins"] > 0] or rows
    est = sum(r["est"] for r in live) / len(live)
    hist = f", his own average when {st} sat" if live[0]["hist"] else ""
    risk = f"{rows[0]['miss']:.0%}/wk" if all(r["miss"] == MISS_WEEK for r in rows) else \
        f"{c['starter'].get('status')} this week ({rows[0]['miss']:.0%}), then {MISS_WEEK:.0%}/wk"
    risk += " risk, Claude's estimate of a typical RB's weekly chance to miss a game"
    text = f"Drops a handcuff: {cuff} ~{est:.0f} pts/wk if {st} sits{hist} ({st}: {risk}); "
    swap = next((r for r in rows if r.get("instead") is not None and r.get("starts")), None)
    if swap:
        who = swap["instead"]
        text += f"without {cuff}, {who['name']} ({primary(who)}) starts ({who['ppg']:.1f})"
    elif any(r.get("starts") for r in rows):
        text += f"without {cuff}, nobody else is left to start in his place"
    else:
        text += f"{cuff} wouldn't crack your lineup even then"
    n = len(rows)
    when = f"over the next {n} weeks" if rows[0]["week"] is not None else "per game"
    text += (f"; {fa['name']} adds " + ", ".join(f"{r['gain']:+.1f}" for r in rows) + f" {when}"
             f" vs {c['ins']:.1f} pts of insurance from {cuff}; worth it because ")
    ins = sum(r["ins"] for r in rows)   # unrounded: a tiny insurance is still "times", not "none"
    if ins > 0:
        text += (f"{fa['name']} gains about {c['gain'] / ins:.0f} times what {cuff} is worth as insurance "
                 f"(the bar is {CUFF_MARGIN:.0f} times)")
    else:
        text += f"{cuff} gives no insurance: he wouldn't start for you even if {st} sat"
    if c["guillotine"]:
        r = rows[0]
        text += f", and he helps more this week ({r['gain']:+.1f} vs {r['ins']:.1f}), which counts most for surviving the cut"
    return text


def adds(starters, bench, free_agents, slots, *, dynasty=False, open_spots=0, faab=None, budget=0, limit=3,
         guillotine=False):
    """[{"fa", "drop" (None = open roster spot), "edge", "gain" (lineup ppg), "window" (lineup pts over the
    window), "weeks", "role", "depth", "cuff" (rule 14 side-by-side when the drop is a handcuff, else None),
    "bid" (lo, hi) or None}], best first. guillotine: a handcuff drop must also win this week (cuff_check)."""
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
                    cuff = cuff_check(drop, roster, after, slots, weeks, guillotine) if drop is not None else None
                    if cuff and not cuff["ok"]:
                        continue   # rule 14: keep the handcuff; the next-best drop wins, or no step
                    gain = round(lineup(slots, after)[0] - lineup(slots, roster)[0], 1)
                    best = {"fa": fa, "drop": drop, "edge": edge, "gain": gain, "window": window, "rank": rank,
                            "role": _role(slots, roster, after, fa, weeks),
                            "depth": _depth(drop, roster) if drop else None, "cuff": cuff}
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
        if a.get("cuff"):   # rule 14: a handcuff drop always shows its trade-off
            text += ". " + cuff_text(a["cuff"], fa)
    if a["bid"]:
        lo, hi = a["bid"]
        text += f". Bid ${lo}" + (f"–{hi}" if hi != lo else "")
    return text


def _or(depth):
    return depth or "bench"
