"""Per-league "what to do" block for the league tabs, rebuilt every run. Pure logic, no AI.

    matchup  one line: projected score vs opponent, or guillotine standing
    fixes    starters who can't play (bye/out/doubtful/empty) with the fix — same rules as the digest
    moves    healthy start/sit upgrades by projection
    adds     top free agents on rest-of-season value, who to drop, FAAB bid (shq/waivers.py)
    trades   trade finder lines + up to 3 fair offers that help both lineups (shq/trades.py)
    assets   3-Ball dynasty picks and minor leaguers from the league sheet (shq/dynasty.py)
    radar    NBA: rising free agents and bench players, my shrinking roles, injured starters' minutes (shq/radar.py)
    notes    informational lines (questionable today, games tonight, FAAB left, data age)"""
import traceback

from . import categories, digest, dynasty, nba_swaps, nba_values, radar, trades, values, waivers
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


def valued(league):
    """FantasyCalc values + multi-week projections on every player; False where there are none (NBA,
    Kosmonauts, test leagues) or the free sources are down."""
    try:
        return values.annotate(league)
    except Exception:
        traceback.print_exc()
        return False


def adds(league):
    if valued(league):
        dynasty = bool(getattr(league, "dynasty", False))
        # guillotine bids come from the survival model (shq/guillotine.py), not the generic ranges
        budget = 0 if getattr(league, "format", None) == "guillotine" else getattr(league, "faab_budget", 0)
        found = waivers.adds(league.starters, league.bench, league.free_agents, league.slots, dynasty=dynasty,
                             open_spots=getattr(league, "open_spots", 0), faab=getattr(league, "faab", None),
                             budget=budget)
        return [waivers.line(a) for a in found] or ["No free agent improves your lineup, or beats a backup at his position, right now."]
    if getattr(league, "sport", "nfl") == "nba" and getattr(league, "values", None):
        league.swaps = nba_swaps.build(league, getattr(league, "cats", None))
        return league.swaps["lines"] or ["No free agent beats anyone on your roster by enough this week."]
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


def trade_block(league):
    """{"lines": [...], "offers": [...]} or None where trades aren't covered."""
    if getattr(league, "sport", "nfl") != "nfl":
        return None
    if getattr(league, "platform", None) == "yahoo":
        return {"lines": ["Trade ideas need every team's roster: waiting on Yahoo API access."], "offers": []}
    if not getattr(league, "others", None) or not valued(league):
        return None
    if "_trades" not in league.__dict__:
        deadline = getattr(league, "trade_deadline", None)
        if not getattr(league, "trades_open", True):
            league._trades = {"lines": [f"Trade deadline has passed ({deadline})." if deadline else "Trades are closed."],
                              "offers": []}
        else:
            mine = league.starters + league.bench
            found = trades.offers(league.slots, mine, league.others)
            lines = trades.finder(league.slots, mine, league.others)
            if not found:
                lines.append("No fair 1-for-1 or 2-for-1 that helps both lineups right now.")
            if deadline:
                lines.append(f"Trade deadline: {deadline}.")
            league._trades = {"lines": lines, "offers": found,
                              "basis": "FantasyCalc " + ("dynasty" if league.fc_settings["dynasty"] else "redraft")
                                       + " values; lineup gain in projected points per game"}
    return league._trades


def trend_radar(league, cats):
    """Best-effort like the rest of the advice: a failed ESPN pool read leaves the tab without the radar."""
    try:
        return radar.block(league, cats)
    except Exception:
        traceback.print_exc()
        return None


def player_values(league):
    """NBA category value for every player (shq/nba_values.py), also put on my roster rows. Best-effort: without it
    the tab keeps the category table and radar."""
    try:
        league.values = nba_values.build(league)
    except Exception:
        traceback.print_exc()
        league.values = None
    ids = nba_values.by_id(league.values)
    for p in league.starters + league.bench + getattr(league, "ir_blocked", []):
        p["val"] = nba_values.label(ids.get(str(p.get("key"))))
    return league.values


def build(league, now):
    standing = digest.standing_item(league)
    items = [i for i in digest.league_items(league, now) if not (standing and i["text"] == standing["text"])]
    notes = [i["text"] for i in items if not i["urgent"]]
    faab = getattr(league, "faab", None)
    if faab is not None:
        notes.append(f"FAAB left: ${faab}")
    nba = getattr(league, "sport", "nfl") == "nba"
    cats = league.cats = categories.build(league) if nba else None
    league.radar = trend_radar(league, cats) if nba else None
    if nba:
        player_values(league)
    return {
        "matchup": _matchup(league),
        "danger": bool(standing and standing["urgent"]),
        "fixes": [i["text"] for i in items if i["urgent"]],
        "moves": _moves(league)[:3],
        "adds": adds(league)[:3],
        "trades": trade_block(league),
        "notes": notes,
        "cats": cats,
        "radar": league.radar,
        "assets": dynasty.block(league.sport, now) if getattr(league, "assets", False) else None,
        "built": ct_label(now),
    }
