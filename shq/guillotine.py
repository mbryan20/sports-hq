"""Guillotine survival odds and FAAB bid guidance (Sleeper guillotine league). Pure math, no AI.

Survival: every surviving team plays its best lineup. Starters whose games have started stay put (a
final game counts its real points); open slots take the best healthy players left on the roster. Each
starter's score is normal around his Sleeper projection with a position-based SD, so a team's total is
normal too. Several thousand draws give each team's chance of finishing lowest (the lowest is cut).

Bids: for the free agents who most improve my lineup, the points and survival they add, a likely price
(each rival who would start the player is assumed to bid a share of the FAAB they have left, scaled by
how much he helps them and how good he is) and the most he is worth to me. Waivers run Wednesday about
2:15am CT; the cut team's players hit the pool after Monday night, so the likely cut team's best players
are previewed too. Read-only: this only recommends, it never bids."""
import datetime as dt
import random

from .common import ct_label
from .config import TZ
from .status import OUTISH
from .swap import FLEX_SLOTS, eligible

SIMS = 5000
POS_SD = {"QB": 7.0, "RB": 7.0, "WR": 7.5, "TE": 5.5, "K": 4.0, "DEF": 5.0}
BOLD = 0.25          # share of their FAAB left a rival spends on a player he badly needs (War Room floor is 20%)
RESERVE = 10         # FAAB I keep back for emergencies (War Room default)
KDEF_CAP = 3         # nobody pays real money for a kicker or defense
WAIVER_WEEKDAY, WAIVER_HOUR, WAIVER_MINUTE = 2, 2, 15   # Wednesday 2:15am CT
MIN_GAIN = 1.0       # points a week a player must add to my lineup to be worth a bid


def entry(p, ctx, points):
    """{id, positions, mean, sd, locked} for one rostered player this week."""
    pos = (p["positions"] or ["?"])[0]
    sd = POS_SD.get(pos, 6.0)
    if p["started"]:
        game = ctx.games.get(p["team"]) or {}
        actual = points.get(p["id"], 0.0) or 0.0
        if game.get("state") == "post":
            return {"id": p["id"], "positions": p["positions"], "mean": actual, "sd": 0.0, "locked": True}
        return {"id": p["id"], "positions": p["positions"], "mean": max(actual, p["proj"]), "sd": sd / 2, "locked": True}
    dead = p.get("empty") or p["bye"] or p["status"] in OUTISH or p["proj"] <= 0
    mean = 0.0 if dead else p["proj"]
    # a low projection means a small role, and a small role swings less
    return {"id": p["id"], "positions": p["positions"], "mean": mean,
            "sd": 0.0 if dead else sd * min(1.0, mean / 5), "locked": False}


def lineup(slots, starters, pool):
    """(mean, sd) of the best lineup: locked starters keep their slot, open slots take the best unlocked
    players left, most specific slots first."""
    taken, mean, var, open_slots = set(), 0.0, 0.0, []
    for slot, pid in zip(slots, list(starters) + [None] * len(slots)):
        p = pool.get(pid)
        if p and p["locked"]:
            taken.add(pid)
            mean, var = mean + p["mean"], var + p["sd"] ** 2
        else:
            open_slots.append(slot)
    for slot in sorted(open_slots, key=lambda s: len(FLEX_SLOTS.get(s, ()))):
        best = max((p for pid, p in pool.items() if pid not in taken and not p["locked"]
                    and eligible(slot, p["positions"])), key=lambda p: p["mean"], default=None)
        if best:
            taken.add(best["id"])
            mean, var = mean + best["mean"], var + best["sd"] ** 2
    return mean, var ** 0.5


def draws(n_teams, sims, seed):
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n_teams)] for _ in range(sims)]


def cut_odds(stats, z):
    """Share of draws in which each team (mean, sd) scores lowest."""
    counts = [0] * len(stats)
    for row in z:
        scores = [m + s * x for (m, s), x in zip(stats, row)]
        counts[scores.index(min(scores))] += 1
    return [c / len(z) for c in counts]


def others_low(stats, z, i):
    """Per draw, the lowest score among everyone but team i (to re-test team i with a new lineup)."""
    return [min(m + s * x for j, ((m, s), x) in enumerate(zip(stats, row)) if j != i) for row in z]


def my_cut(mean, sd, z, i, low):
    return sum(1 for row, lo in zip(z, low) if mean + sd * row[i] < lo) / len(z)


def quality(pos, proj):
    """0 = replacement level, 1 = a stud (War Room scale)."""
    q = (proj - 14) / 12 if pos == "QB" else (proj - 6) / 10
    return max(0.1, min(1.0, q))


def rival_bid(faab, gain, pos, proj):
    if faab <= 0 or gain < 1:
        return 0
    bid = round(faab * BOLD * min(1.0, gain / 6) * quality(pos, proj))
    return min(faab, KDEF_CAP if pos in ("K", "DEF") else faab, bid)


def my_max(faab, gain, cut):
    """Value-based ceiling: a bigger share of spendable FAAB the more he adds, more when I'm in danger."""
    spend = max(0, faab - min(RESERVE, faab))
    return min(spend, round(spend * min(0.6, gain / 15) * (1 + 2 * cut)))


def next_waivers(now):
    local = now.astimezone(TZ)
    run = local.replace(hour=WAIVER_HOUR, minute=WAIVER_MINUTE, second=0, microsecond=0)
    run += dt.timedelta(days=(WAIVER_WEEKDAY - local.weekday()) % 7)
    return run if run > local else run + dt.timedelta(days=7)


class Team:
    def __init__(self, rid, name, faab, slots, starters, pool):
        self.rid, self.name, self.faab, self.slots, self.starters, self.pool = rid, name, faab, slots, starters, pool
        self.mean, self.sd = lineup(slots, starters, pool)

    def gain(self, p):
        """Projected points a player adds to this team's best lineup this week."""
        if p["id"] in self.pool:
            return 0.0
        m, _ = lineup(self.slots, self.starters, {**self.pool, p["id"]: p})
        return m - self.mean


def analyze(league, ctx, now, sims=SIMS):
    """Survival odds for every surviving team plus bid guidance for me. None if the league is down to one."""
    from .leagues import make_player
    points = {}
    for m in league.matchups or []:
        points.update(m.get("players_points") or {})
    names = {u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name") or "?" for u in league.users}
    budget = league.faab_budget or 0
    teams = []
    for r in league.rosters:
        if not r.get("players"):
            continue
        pool = {}
        for pid in r["players"]:
            e = entry(make_player(ctx, league.scoring, pid, "BN"), ctx, points)
            pool[e["id"]] = e
        used = (r.get("settings") or {}).get("waiver_budget_used") or 0
        teams.append(Team(r["roster_id"], names.get(r["owner_id"], f"Team {r['roster_id']}"),
                          max(0, budget - used), league.roster_slots, r.get("starters") or [], pool))
    if len(teams) < 2:
        return None
    me = next(i for i, t in enumerate(teams) if t.rid == league.my_roster_id)
    stats = [(t.mean, t.sd) for t in teams]
    z = draws(len(teams), sims, f"{league.key}:{ctx.week}")
    odds = cut_odds(stats, z)
    low = others_low(stats, z, me)
    mine = teams[me]
    rank = 1 + sum(1 for t in teams if t.mean > mine.mean)
    gap = mine.mean - min(t.mean for i, t in enumerate(teams) if i != me)
    order = sorted(range(len(teams)), key=lambda i: -odds[i])

    def bid(p, source=None):
        e = entry(p, ctx, points)
        gain = mine.gain(e)
        if gain < MIN_GAIN:
            return None
        m, s = lineup(mine.slots, mine.starters, {**mine.pool, e["id"]: e})
        cut_with = my_cut(m, s, z, me, low)
        pos = (p["positions"] or ["?"])[0]
        rivals = sorted(({"name": t.name, "bid": rival_bid(t.faab, t.gain(e), pos, p["proj"])}
                         for i, t in enumerate(teams) if i != me and t is not source), key=lambda r: -r["bid"])
        rivals = [r for r in rivals if r["bid"] > 0]
        price = rivals[0]["bid"] + 1 if rivals else 0
        top = my_max(mine.faab, gain, odds[me])
        call = ("bid" if price <= top else "coin flip" if price * 0.7 <= top else "priced out")
        return {"name": p["name"], "pos": pos, "team": p["team"], "proj": p["proj"], "gain": round(gain, 1),
                "cut_with": round(cut_with, 3), "price": price, "max": top, "call": call,
                "rivals": rivals[:3], "freed_from": source.name if source else None}

    fas = [p for p in league.free_agents[:80] if not p["started"] and p["status"] not in OUTISH and not p["bye"]]
    bids = sorted(filter(None, (bid(p) for p in fas)), key=lambda b: -b["gain"])[:5]

    # the likeliest cut rival's best players flood the pool after Monday night
    freed = None
    risky = next((i for i in order if i != me), None)
    if risky is not None:
        t = teams[risky]
        players = [make_player(ctx, league.scoring, pid, "BN") for pid in t.pool]
        rows = sorted(filter(None, (bid(p, source=t) for p in players
                                    if not p["started"] and p["status"] not in OUTISH and not p["bye"])),
                      key=lambda b: -b["gain"])[:3]
        freed = {"team": t.name, "cut": round(odds[risky], 3), "players": rows}

    return {
        "week": ctx.week, "sims": sims, "n": len(teams), "rank": rank, "gap": round(gap, 1),
        "proj": round(mine.mean, 1), "cut": round(odds[me], 3), "survive": round(1 - odds[me], 3),
        "faab": mine.faab, "waivers": ct_label(next_waivers(now)),
        "teams": [{"name": teams[i].name, "proj": round(teams[i].mean, 1), "cut": round(odds[i], 3),
                   "faab": teams[i].faab, "me": i == me} for i in order],
        "rich": [{"name": t.name, "faab": t.faab} for t in sorted(teams, key=lambda t: -t.faab) if t is not mine][:3],
        "bids": bids, "freed": freed,
    }

