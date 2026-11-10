"""Guillotine survival odds and FAAB bid guidance (Sleeper guillotine league). Pure math, no AI.

Survival: every surviving team plays its best lineup. Starters whose games have started stay put (a
final game counts its real points); open slots take the best healthy players left on the roster. Each
starter's score is normal around his Sleeper projection with a position-based SD, so a team's total is
normal too. Several thousand draws give each team's chance of finishing lowest (the lowest is cut).

Bids: for the free agents who most improve my lineup, the points and survival they add, a likely price
(each rival who would start the player bids up to his boldest past share of FAAB, from the league's
public waiver history, scaled by how much the player helps him and how good he is) and the most he is
worth to me. Waivers run Wednesday about
2:15am CT; the cut team's players hit the pool after Monday night, so the likely cut team's best players
are previewed too. Read-only: this only recommends, it never bids.

War Room v2 (warroom/, docs/war-room-v2/bids.json) is the source of truth for bids: when its bids.json is
for this week and its waiver run hasn't passed, the bid list shows its calls (call, bid, drop, why, win
chance) instead of this model's pricing. This model's own bids are only the fallback, and use the same
reserve; plain free agents (not on waivers) are free adds there, not bids."""
import datetime as dt
import json
import random

from . import sleeper
from .common import ROOT, ct_label
from .config import TZ
from .status import OUTISH
from .swap import FLEX_SLOTS, eligible

SIMS = 5000
# a ~120-point lineup swings about 27 points; Sleeper's own Chop page uses ~30% of the projection (~36)
POS_SD = {"QB": 8.5, "RB": 8.5, "WR": 9.0, "TE": 7.0, "K": 5.0, "DEF": 6.5}
BOLD = 0.25          # least share of FAAB left a rival spends on a player he badly needs (War Room floor is 20%)
RESERVE = 5          # FAAB I keep back: War Room v2's default (warroom/model.js); bids.json's own "reserve" wins
KDEF_CAP = 3         # nobody pays real money for a kicker or defense
WAIVER_WEEKDAY, WAIVER_HOUR, WAIVER_MINUTE = 2, 2, 15   # Wednesday 2:15am CT
MIN_GAIN = 1.0       # points a week a player must add to my lineup to be worth a bid
BIDS_V2 = ROOT / "docs" / "war-room-v2" / "bids.json"
V2_GRACE = dt.timedelta(hours=1)   # after its waiver run, bids.json is stale until War Room v2 rebuilds


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


def boldness(history, budget):
    """{roster_id: boldest bid as a share of the FAAB that roster had going into that week}, from every
    processed claim, won or lost. Spending inside a week isn't tracked, so shares lean a little low."""
    spent, bold = {}, {}
    for t in sorted(history, key=lambda t: (t.get("leg") or 0, t.get("created") or 0)):
        if t.get("type") != "waiver" or t.get("status") not in ("complete", "failed"):
            continue
        bid, rid, leg = (t.get("settings") or {}).get("waiver_bid") or 0, (t.get("roster_ids") or [None])[0], t.get("leg") or 0
        before = budget - sum(b for l, b in spent.get(rid, []) if l < leg)
        if bid > 0 and before > 0:
            bold[rid] = max(bold.get(rid, 0.0), min(1.0, bid / before))
        if t["status"] == "complete":
            spent.setdefault(rid, []).append((leg, bid))
    return bold


def rival_bid(faab, gain, pos, proj, bold=BOLD):
    if faab <= 0 or gain < 1:
        return 0
    bid = round(faab * max(BOLD, bold) * min(1.0, gain / 6) * quality(pos, proj))
    return min(faab, KDEF_CAP if pos in ("K", "DEF") else faab, bid)


def my_max(faab, gain, cut, reserve=RESERVE):
    """Value-based ceiling: a bigger share of spendable FAAB the more he adds, more when I'm in danger."""
    spend = max(0, faab - min(reserve, faab))
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


def on_waivers(past, now):
    """Players a cut freed whose waiver run hasn't happened yet: those need a FAAB claim. Every other unrostered
    player is a plain free agent (a free add). Same rule as War Room v2's freed_status."""
    held = set()
    for c in past or []:
        if c.get("type") != "chopped":
            continue
        at = c.get("status_updated") or c.get("created") or 0
        ran = any(t.get("type") == "waiver" and t.get("status") in ("complete", "failed")
                  and (t.get("status_updated") or 0) > at for t in past)
        if ran or (at and now > next_waivers(dt.datetime.fromtimestamp(at / 1000, dt.timezone.utc)) + V2_GRACE):
            continue
        held |= set(c.get("drops") or {})
    return held


def load_v2(path=None):
    """War Room v2's bids.json, or None when it's missing or unreadable."""
    try:
        b = json.loads((path or BIDS_V2).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return b if isinstance(b, dict) else None


def reserve_of(v2):
    r = (v2 or {}).get("reserve")
    return r if isinstance(r, int) and not isinstance(r, bool) and r >= 0 else RESERVE


def v2_current(v2, week, now):
    """bids.json is for this week and its waiver run hasn't passed (it rebuilds after each run)."""
    if not v2 or v2.get("week") != week or not isinstance(v2.get("bids"), list):
        return False
    try:
        run = dt.datetime.fromisoformat(str(v2.get("next_waiver_run")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return now <= (run if run.tzinfo else run.replace(tzinfo=dt.timezone.utc)) + V2_GRACE


def v2_rows(v2):
    """War Room v2's calls in its own order (most added win odds first), Skips left out. `price` is the bid
    to place (health.py scores the dashboard's "bid" rows by it); a Bid of $0 is a $0 claim."""
    rows = []
    for x in v2.get("bids") or []:
        call = str(x.get("call") or "").strip().lower()
        if not call or call == "skip":
            continue
        bid = int(x.get("bid") or 0)
        rows.append({
            "name": x.get("name"), "pos": x.get("pos"), "team": x.get("team"), "proj": x.get("proj_next_week"),
            "gain": round(x.get("gain_next_week") or 0, 1), "gain_ros": round(x.get("gain_rest_of_season") or 0, 1),
            "call": call, "bid": bid, "price": bid, "max": x.get("your_max") or 0, "est_price": x.get("est_price"),
            "drop": x.get("drop"), "why": x.get("why"), "win_chance": x.get("win_chance"),
            "free": x.get("source") == "free agent", "source": x.get("source"), "injury": x.get("injury"),
            "rivals": [{"name": r.get("team"), "bid": r.get("bid")} for r in (x.get("likely_rival_bids") or [])[:3]],
            "v2": True})
    return rows


def history(league, week):
    lid = league.key.split(":", 1)[1]
    return [t for w in range(1, week + 1) for t in sleeper.transactions(lid, w) or []]


def analyze(league, ctx, now, sims=SIMS, past=None, v2=None):
    """Survival odds for every surviving team plus bid guidance for me. None if the league is down to one.
    `past` is the league's transactions so far (fetched when None); `v2` is War Room v2's bids.json (read
    from docs/war-room-v2/ when None; pass {} for none)."""
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
    past = history(league, ctx.week) if past is None else past
    bold = boldness(past, budget)
    v2 = load_v2() if v2 is None else v2
    reserve, waiting = reserve_of(v2), on_waivers(past, now)
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
        row = {"name": p["name"], "pos": pos, "team": p["team"], "proj": p["proj"], "gain": round(gain, 1),
               "cut_with": round(cut_with, 3), "freed_from": source.name if source else None}
        if source is None and p["id"] not in waiting:
            # a plain free agent: no waiver claim, so no bid and no rivals to outbid
            return {**row, "price": 0, "max": 0, "call": "add free", "free": True, "rivals": []}
        rivals = sorted(({"name": t.name, "bid": rival_bid(t.faab, t.gain(e), pos, p["proj"], bold.get(t.rid, BOLD))}
                         for i, t in enumerate(teams) if i != me and t is not source), key=lambda r: -r["bid"])
        rivals = [r for r in rivals if r["bid"] > 0]
        price = rivals[0]["bid"] + 1 if rivals else 0
        top = my_max(mine.faab, gain, odds[me], reserve)
        call = ("bid" if price <= top else "coin flip" if price * 0.7 <= top else "priced out")
        return {**row, "price": price, "max": top, "call": call, "rivals": rivals[:3]}

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

    source, model = {"name": "dashboard model"}, None
    try:
        rows = v2_rows(v2) if v2_current(v2, ctx.week, now) else None
    except (TypeError, ValueError, AttributeError):   # a malformed bids.json: keep the model's own bids
        rows = None
    if rows is not None:
        # War Room v2 decides the bids; this model's own list stays alongside for comparison
        source = {"name": "War Room v2", "url": "war-room-v2/", "as_of": v2.get("data_as_of"),
                  "spendable": (v2.get("budget") or {}).get("spendable")}
        model = {"bids": bids, "freed": freed}
        bids, freed = rows, None
    return {
        "week": ctx.week, "sims": sims, "n": len(teams), "rank": rank, "gap": round(gap, 1),
        "proj": round(mine.mean, 1), "cut": round(odds[me], 3), "survive": round(1 - odds[me], 3),
        "faab": mine.faab, "reserve": reserve, "waivers": ct_label(next_waivers(now)),
        "bid_source": source, "model": model,
        "teams": [{"name": teams[i].name, "proj": round(teams[i].mean, 1), "cut": round(odds[i], 3),
                   "faab": teams[i].faab, "bold": round(bold.get(teams[i].rid, 0), 2), "me": i == me} for i in order],
        "rich": [{"name": t.name, "faab": t.faab} for t in sorted(teams, key=lambda t: -t.faab) if t is not mine][:3],
        "bids": bids, "freed": freed,
    }

