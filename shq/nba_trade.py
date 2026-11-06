"""NBA trade checker data: what the Players page's Trade mode needs to judge a trade in a category league. Pure logic.

- Value above waiver level per player: max(value per game - the waiver-level value, 0). Swapping three bench players
  for one star frees two roster spots, which waiver-level players fill, so each side counts what it has above that level.
- Category fit: each team's category profile (z-scores summed over its top ROSTER_TOP players by value) and where I
  rank in each category; the page weights my weakest categories most.
- Dynasty (3-Ball): an age curve. Value above waiver level times AGE_MULT (young players grow, players past 29 fade)
  plus a prospect bonus for players under PROSPECT_AGE, so a 20-year-old below waiver level still has trade value.
  A rough curve, not fitted to data; the page says so.

trade() is the same verdict the page computes in JavaScript, kept here so it is tested."""
from .nba_swaps import dead
from .nba_values import by_id

ROSTER_TOP = 10           # players per team that count toward its category profile (about the starters)
AGE_MULT = [(20, 1.5), (21, 1.4), (22, 1.3), (23, 1.2), (24, 1.1), (28, 1.0), (29, 0.9), (30, 0.8), (31, 0.7), (32, 0.6),
            (33, 0.5)]
OLD_MULT = 0.4            # 34 and up
PROSPECT_AGE, PROSPECT_STEP = 23, 0.6
CLOSE = 0.5               # value per game within which a trade is a coin flip
WEAK, STRONG = 1.5, 0.5   # weights for my bottom-third / top-third categories


def above(p, repl):
    """0 for a player with no NBA team: he plays for nobody, whatever his projection says."""
    return 0.0 if dead(p) else max(p["v"] - repl, 0.0)


def age_mult(age):
    if age is None:
        return 1.0
    for top, m in AGE_MULT:
        if age < top + 1:
            return m
    return OLD_MULT


def dynasty_value(p, repl):
    """Value above waiver level on the age curve, plus the prospect bonus (None age = no adjustment)."""
    age = p.get("age")
    bonus = PROSPECT_STEP * max(0.0, PROSPECT_AGE - age) if age is not None else 0.0
    return round(above(p, repl) * age_mult(age) + bonus, 2)


def profiles(block):
    """{team: [z sum per category over its top ROSTER_TOP players]}; my team is "me"."""
    teams = {}
    for p in block["players"]:
        if p["own"]:
            teams.setdefault(p["own"], []).append(p)
    out = {}
    for t, ps in teams.items():
        top = sorted(ps, key=lambda p: -p["v"])[:ROSTER_TOP]
        out[t] = [round(sum(p["z"][i] for p in top), 2) for i in range(len(block["cats"]))]
    return out


def my_ranks(prof):
    """My rank (1 = best) in each category among the teams."""
    me = prof.get("me")
    if not me:
        return []
    return [1 + sum(1 for t, z in prof.items() if t != "me" and z[i] > me[i]) for i in range(len(me))]


def fit_weights(ranks, n_teams):
    """Category weights for a trade: my bottom third WEAK, top third STRONG, else 1; rescaled to average 1."""
    if not ranks:
        return []
    raw = [WEAK if r > n_teams * 2 / 3 else STRONG if r <= n_teams / 3 else 1.0 for r in ranks]
    mean = sum(raw) / len(raw)
    return [round(w / mean, 3) for w in raw]


def annotate(block, dynasty):
    """Add the trade fields to a league's values block (players.json): per player "above" (and "dyn" in dynasty),
    and "trade": {"profiles", "ranks", "weights", "dynasty"}."""
    if not block:
        return block
    for p in block["players"]:
        p["above"] = round(above(p, block["repl"]), 2)
        if dynasty:
            p["dyn"] = dynasty_value(p, block["repl"])
    prof = profiles(block)
    ranks = my_ranks(prof)
    block["trade"] = {"profiles": prof, "ranks": ranks, "weights": fit_weights(ranks, len(prof)), "dynasty": dynasty}
    return block


def trade(block, give_ids, get_ids):
    """Verdict for giving `give_ids` for `get_ids`: {"now", "fit", "dyn", "cats", "verdict"}. now = value per game above
    waiver level gained; fit = now adjusted toward my weak categories; dyn = dynasty value gained (dynasty leagues), which
    decides the verdict there; elsewhere fit does."""
    ids = by_id(block)
    give, get = [ids[i] for i in give_ids], [ids[i] for i in get_ids]
    t = block["trade"]
    now = sum(p["above"] for p in get) - sum(p["above"] for p in give)
    # per category, counting only players above waiver level (one below it would be dropped for a waiver player anyway)
    counts = lambda p: p["above"] > 0
    cats = [sum(p["z"][i] for p in get if counts(p)) - sum(p["z"][i] for p in give if counts(p)) for i in range(len(block["cats"]))]
    w = t["weights"] or [1.0] * len(cats)
    # fit: the value gained, plus extra for gains in my weak categories and less for ones I already win (weights average 1)
    fit = now + sum((x - 1) * c for c, x in zip(cats, w))
    dyn = (sum(p.get("dyn", 0) for p in get) - sum(p.get("dyn", 0) for p in give)) if t["dynasty"] else None
    score = dyn if dyn is not None else fit
    verdict = "close" if abs(score) < CLOSE else "accept" if score > 0 else "decline"
    return {"now": round(now, 2), "fit": round(fit, 2), "dyn": round(dyn, 2) if dyn is not None else None,
            "cats": [round(c, 2) for c in cats], "verdict": verdict}
