"""Trade finder and trade offers. Pure logic: no network, no AI.

Players are league player dicts (leagues.make_player) carrying, from values.annotate:
    val   FantasyCalc trade value for this league's settings (dynasty or redraft)
    ppg   projected points per game over the next few weeks

A lineup's strength is its best legal starting lineup by ppg over the skill slots (QB/RB/WR/TE and
the flexes); kickers and defenses aren't traded. An offer has to
    - be fair by value: the two sides within TOLERANCE, with the lesser player of a two-player side
      counted at PACKAGE_DISCOUNT (whoever takes two players has to cut someone)
    - raise my lineup by at least MIN_GAIN points per game
    - raise theirs by at least MIN_NEED: what they get starts for them, so it fills a real need"""
from itertools import combinations

from .swap import FLEX_SLOTS, eligible

SKILL = ("QB", "RB", "WR", "TE")
TOLERANCE = 0.10
PACKAGE_DISCOUNT = 0.8
MIN_GAIN = 0.5
MIN_NEED = 0.5
MIN_VALUE = 150          # below this FantasyCalc value a player is filler, not a trade piece


def primary(p):
    return next((x for x in p["positions"] if x in SKILL), None)


def skill_slots(slots):
    """The lineup slots a trade can change, narrowest first so a greedy fill is optimal."""
    keep = [s for s in slots if s in SKILL or FLEX_SLOTS.get(s, set()) & set(SKILL)]
    return sorted(keep, key=lambda s: len(FLEX_SLOTS.get(s, ())))


def lineup(slots, players):
    """Best skill lineup by ppg: (total ppg, [(slot, player)]). `slots` from skill_slots()."""
    pool = sorted((p for p in players if primary(p)), key=lambda p: -p["ppg"])
    used, picks = set(), []
    for slot in slots:
        p = next((p for p in pool if p["id"] not in used and eligible(slot, p["positions"])), None)
        if p:
            used.add(p["id"])
            picks.append((slot, p))
    return round(sum(p["ppg"] for _, p in picks), 1), picks


def package(vals):
    vals = sorted(vals, reverse=True)
    return vals[0] + PACKAGE_DISCOUNT * sum(vals[1:])


def fair(give, get):
    return abs(give - get) <= TOLERANCE * max(give, get)


def _tag(p):
    return f"{p['name']} ({primary(p)})"


def _starts(ps, who):
    names = " and ".join(p["name"] for p in ps)
    return f"{names} {'starts' if len(ps) == 1 else 'start'} for {who}" if ps else f"depth for {who}"


def _deals(mine, theirs):
    """(give, get, give_value, get_value) for every fair 1-for-1, 2-for-1 and 1-for-2."""
    for a in mine:
        for b in theirs:
            if fair(a["val"], b["val"]):
                yield (a,), (b,), a["val"], b["val"]
    for pair in combinations(mine, 2):
        g = package([p["val"] for p in pair])
        for b in theirs:
            if fair(g, b["val"]):
                yield pair, (b,), g, b["val"]
    for pair in combinations(theirs, 2):
        r = package([p["val"] for p in pair])
        for a in mine:
            if fair(a["val"], r):
                yield (a,), pair, a["val"], r


def offers(slots, mine, teams, limit=3):
    """Up to `limit` offers, best lineup gain for me first.
    teams: [{"name", "players"}] — every other roster in the league."""
    slots = skill_slots(slots)
    if not slots:
        return []
    base_me, _ = lineup(slots, mine)
    assets = lambda ps: [p for p in ps if primary(p) and p.get("val", 0) >= MIN_VALUE]
    my_assets = assets(mine)
    found = []
    for team in teams:
        theirs = team["players"]
        base_them, their_picks = lineup(slots, theirs)
        for give, get, gv, rv in _deals(my_assets, assets(theirs)):
            out, inn = {p["id"] for p in give}, {p["id"] for p in get}
            me_after, my_picks = lineup(slots, [p for p in mine if p["id"] not in out] + list(get))
            gain = round(me_after - base_me, 1)
            if gain < MIN_GAIN:
                continue
            them_after, their_new = lineup(slots, [p for p in theirs if p["id"] not in inn] + list(give))
            need = round(them_after - base_them, 1)
            if need < MIN_NEED:
                continue
            new_ids = {p["id"] for _, p in their_new}
            benched = [p for _, p in their_picks if p["id"] not in new_ids and p["id"] not in inn]
            starts_me = [p for _, p in my_picks if p["id"] in inn]
            starts_them = [p for p in give if p["id"] in new_ids]
            found.append({
                "team": " ".join(team["name"].split()),
                "give": [_tag(p) for p in give], "get": [_tag(p) for p in get],
                "give_value": round(gv), "get_value": round(rv),
                "my_gain": gain, "their_gain": need,
                "cut": len(get) > len(give),        # I take two players: someone on my bench has to go
                "why": _starts(starts_me, "you") + "; " + _starts(starts_them, "them")
                       + (f" over {benched[0]['name']} ({benched[0]['ppg']}/gm)" if benched else ""),
                "_ids": out | inn,
            })
    rank = lambda o: -(o["my_gain"] + 0.3 * o["their_gain"])
    found.sort(key=rank)
    # the best straight 1-for-1 always gets a place (simplest to propose), then the rest by gain;
    # no player appears in two offers
    one = next((o for o in found if len(o["give"]) == len(o["get"]) == 1), None)
    picked, used = ([one], set(one["_ids"])) if one else ([], set())
    for o in found:
        if len(picked) == limit:
            break
        if not o["_ids"] & used:
            picked.append(o)
            used |= o["_ids"]
    return [{k: v for k, v in o.items() if k != "_ids"} for o in sorted(picked, key=rank)]


def finder(slots, mine, teams):
    """Short lines on where I'm weak and what depth other teams would start."""
    slots = skill_slots(slots)
    if not slots or not teams:
        return []
    lines = []
    _, my_picks = lineup(slots, mine)
    rosters = [mine] + [t["players"] for t in teams]
    for pos in SKILL:
        if pos not in slots:
            continue
        weakest = []
        for ps in rosters:
            _, picks = lineup(slots, ps)
            at = [p["ppg"] for s, p in picks if s == pos]
            weakest.append(min(at) if at else 0.0)
        mine_w = weakest[0]
        rank = 1 + sum(w > mine_w for w in weakest[1:])
        if rank > len(rosters) * 2 / 3:
            who = min((p for s, p in my_picks if s == pos), key=lambda p: p["ppg"], default=None)
            lines.append(f"Weak spot: {pos}" + (f" ({who['name']} {who['ppg']}/gm" if who else " (") +
                         f", {_ordinal(rank)} of {len(rosters)})")
    starters = {p["id"] for _, p in my_picks}
    depth = sorted((p for p in mine if p["id"] not in starters and primary(p) and p.get("val", 0) >= MIN_VALUE),
                   key=lambda p: -p["ppg"])[:4]
    for p in depth:
        wanted = sum(lineup(slots, t["players"] + [p])[0] > lineup(slots, t["players"])[0] for t in teams)
        if wanted >= len(teams) / 2:
            lines.append(f"Surplus: {_tag(p)}, {p['ppg']}/gm on your bench, would start for {wanted} of {len(teams)} teams")
        if sum(l.startswith("Surplus") for l in lines) == 2:
            break
    return lines


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
