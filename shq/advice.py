"""Per-league "what to do" block for the league tabs, rebuilt every run. Pure logic, no AI.

    matchup  one line: projected score vs opponent, or guillotine standing
    fixes    starters who can't play (bye/out/doubtful/empty) with the fix — same rules as the digest
    moves    healthy start/sit upgrades by projection
    adds     top free agents and who they'd replace
    notes    informational lines (questionable today, games tonight, FAAB left, data age)"""
from . import digest
from .common import ct_label
from .status import OUTISH
from .swap import fa_adds, start_sit


NBA_POS = ("PG", "SG", "SF", "PF", "C")


def _matchup(league):
    standing = digest.standing_item(league)
    if standing:
        return standing["text"][0].upper() + standing["text"][1:]
    # starters who can't play count as zero, so the margin shows what the lineup is really worth
    mine = round(sum(p["proj"] for p in league.starters if not _dead(p)), 1)
    opp = " ".join((league.opponent or "").split())
    if getattr(league, "sport", "nfl") == "nba":
        return f"vs {opp}" if opp else None
    if opp and league.opp_proj is not None:
        diff = round(mine - league.opp_proj, 1)
        verdict = f"projected to win by {diff}" if diff > 0 else f"projected to lose by {-diff}" if diff < 0 else "dead even"
        return f"{mine} vs {league.opp_proj} ({opp}): {verdict}"
    return f"{mine} projected" + (f" vs {opp}" if opp else "")


def _dead(p):
    return bool(p.get("empty") or p["bye"] or p["status"] in digest.DEAD)


def _moves(league):
    if getattr(league, "sport", "nfl") == "nba":
        return []
    return [f"Start {b['name']} ({b['proj']}) over {s['name']} ({s['proj']}) at {s['slot']}, +{round(gain, 1)}"
            for s, b, gain in start_sit(league.starters, league.bench) if not _dead(s)]


def _adds(league):
    if getattr(league, "sport", "nfl") == "nba":
        fas = sorted(((league.games_in_matchup(p), p["owned"], p) for p in league.free_agents if p["status"] not in OUTISH),
                     key=lambda t: (-t[0], -t[1]))[:3]
        return [f"{p['name']} ({'/'.join(x for x in NBA_POS if x in p['positions'])}, {p['team']}): {g} games left this week, {o}% owned"
                for g, o, p in fas]
    roster = league.starters + league.bench
    # dynasty benches hold stashes that project 0 this week, so name the comparison, not a drop
    dynasty = getattr(league, "dynasty", False)
    return [f"{fa['name']} ({fa['positions'][0]}, {fa['team']}, {fa['proj']} proj)"
            + ((f", beats your weakest {fa['positions'][0]} {who['name']} ({who['proj']}) this week" if dynasty
                else f" for {who['name']} ({who['proj']})") if who else "")
            for _, fa, who in fa_adds(roster, league.free_agents[:300])]


def build(league, now):
    standing = digest.standing_item(league)
    items = [i for i in digest.league_items(league, now) if not (standing and i["text"] == standing["text"])]
    notes = [i["text"] for i in items if not i["urgent"]]
    faab = getattr(league, "faab", None)
    if faab is not None:
        notes.append(f"FAAB left: ${faab}")
    return {
        "matchup": _matchup(league),
        "danger": bool(standing and standing["urgent"]),
        "fixes": [i["text"] for i in items if i["urgent"]],
        "moves": _moves(league)[:3],
        "adds": _adds(league)[:3],
        "notes": notes,
        "built": ct_label(now),
    }
