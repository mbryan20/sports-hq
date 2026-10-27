"""Market consensus from CFBD /lines: home spread, total, devigged home win probability."""
import statistics
from math import erf, sqrt
from .http import cfbd


def _ml_prob(ml):
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


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
    p_home = statistics.median(probs) if probs else 0.5 * (1 + erf((-spread) / (15.5 * sqrt(2))))
    return {
        "home_spread": spread,  # home line: negative = home favored
        "open_spread": statistics.median(opens) if opens else None,
        "total": statistics.median(totals) if totals else None,
        "p_home": p_home,
    }


def lines(year, week=None, max_age_h=24 * 365):
    kw = {"year": year}
    if week is not None:
        kw["week"] = week
    return {r["id"]: consensus(r) for r in cfbd("/lines", max_age_h=max_age_h, **kw)}
