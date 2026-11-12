"""Market consensus from CFBD /lines: home spread, total, devigged home win probability.

When CFBD can't be called (no key in GitHub Actions, budget used up, HTTP error), `lines` falls back (Q-055):
the saved copy of that week's CFBD /lines, any age (pp.http); else the saved season-wide CFBD /lines filtered to
the week plus ESPN's public scoreboard lines, in the same shape. NOTE says on the card which was used."""
import statistics
from datetime import datetime
from math import erf, sqrt
from zoneinfo import ZoneInfo
from .http import cfbd, cfbd_cached, CFBDUnavailable, STALE, when
from .names import norm

CT = ZoneInfo("America/Chicago")

NOTE = []  # plain-English line(s) for the card when this build's lines didn't come from a fresh CFBD call


class LinesUnavailable(CFBDUnavailable):
    """No betting lines at all for the week (CFBD down, nothing saved, ESPN empty). Plain words."""


def _ml_prob(ml):
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def _p_from_spread(spread):
    return 0.5 * (1 + erf((-spread) / (15.5 * sqrt(2))))


def consensus(line_rec):
    ls = line_rec.get("lines") or []
    spreads = [l["spread"] for l in ls if l.get("spread") is not None]
    opens = [l["spreadOpen"] for l in ls if l.get("spreadOpen") is not None]
    totals = [l["overUnder"] for l in ls if l.get("overUnder") is not None]
    probs = []
    for l in ls:
        h, a = l.get("homeMoneyline"), l.get("awayMoneyline")
        if h and a:
            ph, pa = _ml_prob(h), _ml_prob(a)
            probs.append(ph / (ph + pa))
    if not spreads:
        return None
    spread = statistics.median(spreads)
    p_home = statistics.median(probs) if probs else _p_from_spread(spread)
    return {
        "home_spread": spread,  # home line: negative = home favored
        "open_spread": statistics.median(opens) if opens else None,
        "total": statistics.median(totals) if totals else None,
        "p_home": p_home,
    }


def _saved(at):
    """'saved CFBD lines as of Tue Nov 10, 03:10 PM CT' (or 'older saved CFBD lines (save time unknown)')."""
    return f"saved CFBD lines as of {when(at)}" if at else "older saved CFBD lines (save time unknown)"


def _same_game(g, e):
    """CFBD game g is ESPN event e, either way round (the matching pp.lines.find uses for pool games)."""
    a, h = norm(g["awayTeam"]), norm(g["homeTeam"])
    return (h in e["home_names"] and a in e["away_names"]) or (a in e["home_names"] and h in e["away_names"])


def espn_lines(year, week, games=(), fetch=None):
    """ESPN's current college lines for a CFBD week, in consensus() shape, keyed by CFBD game id. ESPN event ids
    are CFBD game ids; otherwise teams are matched by name (pp.names.norm, as pp.lines.find does). ESPN listing
    home/away the other way round (neutral sites) flips the line. {} when ESPN is unreachable."""
    from . import lines as espn  # the ESPN scoreboard module (no cycle: it imports only http and names)
    try:
        events = (fetch or espn.espn_odds)("CFB", week, year)
    except Exception as ex:
        print("ESPN odds unavailable:", ex)
        return {}
    by_id = {str(g["id"]): g for g in games}
    at = datetime.now(CT).strftime("%a %I:%M %p CT")
    out = {}
    for e in events:
        if e.get("home_spread") is None:
            continue
        g = by_id.get(str(e["id"]))
        if g is None and games:
            g = next((x for x in games if _same_game(x, e)), None)
            if g is None:
                continue  # not a game on this CFBD week
        hs, ph, op = float(e["home_spread"]), e.get("p_home"), e.get("open_home_spread")
        if g and norm(g["homeTeam"]) in e["away_names"] and norm(g["awayTeam"]) in e["home_names"]:
            hs, ph, op = -hs, None if ph is None else 1 - ph, None if op is None else -op
        gid = g["id"] if g else (int(e["id"]) if str(e["id"]).isdigit() else e["id"])
        out[gid] = {"home_spread": hs, "open_spread": op, "total": e.get("total"),
                    "p_home": ph if ph is not None else _p_from_spread(hs), "src": f"ESPN {e.get('book') or 'ESPN'} {at}"}
    return out


def fallback(year, week, games=(), why="CFBD unavailable", fetch=None):
    """Lines when CFBD /lines can't be fetched and no copy of this week's call is saved: the saved season-wide
    CFBD /lines (any age) for this week's games, with ESPN's scoreboard on top (fresher) and filling the rest."""
    out, parts = {}, []
    saved = cfbd_cached("/lines", year=year)
    if saved:
        data, at = saved
        got = {r["id"]: c for r in data if r.get("week") == week for c in [consensus(r)] if c}
        if got:
            out.update(got)
            parts.append(f"{_saved(at)} for {len(got)} games")
    esp = espn_lines(year, week, games, fetch)
    for gid, e in esp.items():
        old = out.get(gid) or {}
        out[gid] = {**e, "open_spread": e["open_spread"] if e["open_spread"] is not None else old.get("open_spread"),
                    "total": e["total"] if e["total"] is not None else old.get("total")}
    if esp:
        parts.append(f"ESPN's scoreboard for {len(esp)} games")
    if not out:
        raise LinesUnavailable(f"no betting lines for week {week} ({why}, no saved CFBD lines, "
                               "and ESPN's scoreboard had none)")
    NOTE.append(f"CFBD lines unavailable at build ({why}); used " + " and ".join(parts) + ".")
    return out


def lines(year, week=None, max_age_h=24 * 365, games=(), fetch=None):
    """{CFBD game id: consensus}. Never fails for want of CFBD when a week is given: see the module note."""
    kw = {"year": year}
    if week is not None:
        kw["week"] = week
    n = len(STALE)
    try:
        data = cfbd("/lines", max_age_h=max_age_h, **kw)
    except CFBDUnavailable as ex:
        if week is None:
            raise
        return fallback(year, week, games, getattr(ex, "why", None) or str(ex), fetch)
    if len(STALE) > n:  # CFBD couldn't be called; pp.http served this week's saved copy
        _, why, at = STALE[-1]
        NOTE.append(f"CFBD lines unavailable at build ({why}); used {_saved(at)}, "
                    "with ESPN's current line on top where it has one.")
    return {r["id"]: consensus(r) for r in data}
