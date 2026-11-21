"""Value calls on the dynasty league tabs (Sunday's Best, 3-Ball FB): 3 buys, 3 sells and his rookie picks, from our
values vs the FantasyCalc market (shq/pv_model.py). Only positions whose signal is live (it beat the market on past
seasons and hasn't been paused) make a call; rookie trials never do. Ideas only: nothing is sent."""
import math

from . import pv_model, values
from .common import STATE, get_json, load_json
from .config import SEASON

MIN_EDGE = 0.10          # 10%+ off the market by ours to list
N = 3
ROUNDS = ("1st", "2nd", "3rd", "4th")
ASSETS = STATE / "dynasty_assets.json"     # 3-Ball: my picks from the league sheet (shq/dynasty.py)
CLASSES = STATE / "pv_classes.json"        # early read of each rookie class (label only; written at the Feb review)


def _pct(edge):
    return round(100 * (math.exp(edge) - 1))


def line(kind, p, owner=None):
    pv = p["pv"]
    who = f" ({owner})" if owner else ""
    return (f"{kind}: {p['name']}{who}: market {p.get('val', 0):,}, ours {pv['ours']:,} ({_pct(pv['edge']):+d}%). "
            f"{pv['why'][0].upper()}{pv['why'][1:]}. Track record: {pv['record']}.")


def _live(p):
    pv = p.get("pv")
    return pv if pv and pv.get("live") else None


def calls(league):
    """(buys, sells): [(player, owner)] best first."""
    mine = [p for p in list(league.starters) + list(league.bench) if not p.get("empty")]
    buys = [(p, t["name"]) for t in getattr(league, "others", None) or [] for p in t["players"]
            if _live(p) and p["pv"]["edge"] >= MIN_EDGE]
    sells = [(p, None) for p in mine if _live(p) and p["pv"]["edge"] <= -MIN_EDGE]
    buys.sort(key=lambda x: -x[0]["pv"]["edge"])
    sells.sort(key=lambda x: x[0]["pv"]["edge"])
    return buys[:N], sells[:N]


# ---- rookie picks ----
def sleeper_picks(league, traded=None, seasons=None, rounds=None):
    """My picks in a Sleeper dynasty league: [(season, round, from_team or None)]; every team holds its own picks
    unless Sleeper's traded-picks list says otherwise."""
    seasons = seasons or [SEASON + 1, SEASON + 2, SEASON + 3]
    rounds = rounds or int((league.settings or {}).get("draft_rounds") or 3)
    if traded is None:
        traded = get_json(f"https://api.sleeper.app/v1/league/{league.key.split(':', 1)[1]}/traded_picks")
    holder = {}
    for t in traded:
        holder[(int(t["season"]), int(t["round"]), t["roster_id"])] = t["owner_id"]
    me = league.my_roster_id
    names = getattr(league, "team_names", {}) or {}
    out = []
    for s in seasons:
        for r in range(1, rounds + 1):
            for rid in [x["roster_id"] for x in league.rosters]:
                if holder.get((s, r, rid), rid) == me:
                    out.append((s, r, None if rid == me else (names.get(rid) or f"team {rid}")))
    return out


def sheet_picks(assets=None):
    """3-Ball FB: my NFL picks from the league sheet export."""
    assets = assets or load_json(ASSETS) or {}
    out = []
    for p in assets.get("picks") or []:
        if p.get("sport") == "NFL":
            out += [(p["year"], r, via) for r, via in p.get("mine") or []]
    return out


def picks_line(league, picks, fc_picks):
    if not picks:
        return None
    race = getattr(league, "race", None) or {}
    n = getattr(league, "team_count", 12) or 12
    parts, total = [], 0
    for s, r, via in sorted(picks, key=lambda x: (x[0], x[1], x[2] or "")):
        tier = None
        if s == SEASON + 1 and via is None and race.get("pick"):    # my own next pick: where I'd draft if it ended now
            k = race["pick"]
            tier = "Early" if k <= n / 3 else "Mid" if k <= 2 * n / 3 else "Late"
        v = (fc_picks.get(f"{s} {ROUNDS[r - 1]} ({tier})") if tier else None) or fc_picks.get(f"{s} {ROUNDS[r - 1]}")
        total += v or 0
        parts.append(f"{s} {ROUNDS[r - 1]}{f' ({tier.lower()})' if tier else ''}{f' via {via}' if via else ''} "
                     + (f"{v:,}" if v else "no value"))
    labels = (load_json(CLASSES) or {}).get("labels") or {}
    seen = sorted({str(s) for s, _, _ in picks if str(s) in labels})
    cls = (" Class read (label only, not proven): " + "; ".join(f"{y} {labels[y]}" for y in seen) + ".") if seen else ""
    return f"Your picks (FantasyCalc market, {total:,} in all): " + " · ".join(parts) + "." + cls


def block(league):
    """League-tab section, or None outside dynasty football leagues."""
    if not getattr(league, "dynasty", False) or getattr(league, "sport", "nfl") != "nfl":
        return None
    try:
        if not values.annotate(league):
            return None
    except Exception:
        return None
    fc = league.fc_settings
    buys, sells = calls(league)
    lines = [line("Buy", p, o) for p, o in buys] + [line("Sell", p) for p, _ in sells]
    if not lines:
        lines.append("No player is 10%+ off the market by ours right now.")
    try:
        picks = sleeper_picks(league) if league.platform == "sleeper" else sheet_picks()
        pl = picks_line(league, picks, values.fc_picks(fc["qbs"], fc["teams"], fc["ppr"]))
        if pl:
            lines.append(pl)
    except Exception:
        pass
    model = pv_model.load_model()
    live = [f"{'in-season' if v == 'in' else 'offseason'} {pos}" for v in ("in", "off")
            for pos, e in ((model.get("versions") or {}).get(v) or {}).items() if (e.get("gate") or {}).get("pass")]
    return {"lines": lines,
            "basis": "Ours = FantasyCalc's value moved by signals that beat it on past seasons the model never saw; one call "
                     "moves it 35% at most. Live now: " + (", ".join(live) or "none") + ". Other positions show the market. "
                     "Trade offers stay fair by the market, since that's what the other owner sees. Rookie picks: market "
                     "values; early class reads haven't passed a test yet, so they're labels and picks aren't adjusted."}
