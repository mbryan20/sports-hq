"""Stats-only college ratings and game projections (no spread input).

Ratings: opponent-adjusted offensive/defensive EPA per play and success rate, from CFBD
game-level advanced stats (garbage time excluded), via ridge regression shrunk toward a
prior built from last season's SP+ scaled by returning production. Ratings at week w use
only games before week w, so the backtest is walk-forward with no leakage.
Points: OLS map from expected EPA/success/home field to points, fit on 2025 walk-forward.
"""
import json
from functools import lru_cache
import numpy as np
from .http import cfbd

STATS = (("ppa", 5), ("sr", 6), ("pts", 7))
LAMBDA = {"ppa": 3.0, "sr": 3.0, "pts": 3.0}  # prior worth ~3 games of data


@lru_cache(None)
def games(year):
    # current season refreshes about daily so ratings and grading see new results
    age = 20 if year >= 2026 else 24 * 365
    return [g for g in cfbd("/games", max_age_h=age, year=year, classification="fbs") if g.get("seasonType") == "regular" or g.get("seasonType") is None]


@lru_cache(None)
def adv(year):
    return cfbd("/stats/game/advanced", max_age_h=20 if year >= 2026 else 24 * 365, year=year, excludeGarbageTime="true")


@lru_cache(None)
def fbs_teams(year):
    return {t["school"] for t in cfbd("/teams/fbs", year=year)}


@lru_cache(None)
def _sp(year):
    return {r["team"]: r for r in cfbd("/ratings/sp", year=year)}


@lru_cache(None)
def _ret(year):
    return {r["team"]: r for r in cfbd("/player/returning", year=year)}


def _loc(g, team):
    if g.get("neutralSite"):
        return 0
    return 1 if g["homeTeam"] == team else -1


@lru_cache(None)
def offense_rows(year):
    """One row per team-game offense: (gameId, week, team, opp, loc, ppa, sr, points)."""
    gmap = {g["id"]: g for g in games(year)}
    rows = []
    for r in adv(year):
        g = gmap.get(r["gameId"])
        o = r.get("offense") or {}
        if not g or o.get("ppa") is None or o.get("successRate") is None:
            continue
        team = r["team"]
        pts = g["homePoints"] if g["homeTeam"] == team else g["awayPoints"]
        rows.append((r["gameId"], g["week"], team, r["opponent"], _loc(g, team), o["ppa"], o["successRate"], pts))
    return rows


# Scale from SP+ points to EPA/success units, fit once on 2025 (see calibrate_prior_scale).
PRIOR_SCALE_FILE = "cache/prior_scale.json"


def _prior(year, teams):
    """Prior O/D (offense +, defense allowed +) in ppa and sr units for `year` from year-1 SP+."""
    from pathlib import Path
    sc = json.loads((Path(__file__).resolve().parent.parent / PRIOR_SCALE_FILE).read_text())
    sp, ret = _sp(year - 1), _ret(year)
    offs = np.array([v["offense"]["rating"] for v in sp.values()])
    defs = np.array([v["defense"]["rating"] for v in sp.values()])
    mo, md = offs.mean(), defs.mean()
    pri = {}
    for t in teams:
        if t in sp:
            r = ret.get(t, {}).get("percentPPA")
            m = 0.5 + 0.5 * min(max(r if r is not None else 0.6, 0.0), 1.0)
            do = (sp[t]["offense"]["rating"] - mo) * m
            dd = (sp[t]["defense"]["rating"] - md) * m
            pri[t] = {k: (sc[k]["o"] * do, sc[k]["d"] * dd) for k in sc}
        else:  # FCS / unrated: league-wide FCS average learned from 2025
            pri[t] = {k: (sc[k]["fcs_o"], sc[k]["fcs_d"]) for k in sc}
    return pri


def _ridge(rows, teams, stat_idx, prior, lam):
    """Solve y = mu + O_t + D_o + h*loc with ridge toward prior. Returns mu, h, {team: (O, D)}."""
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    P = 2 * n + 2  # O..., D..., mu, h
    X = np.zeros((len(rows), P))
    ri = np.arange(len(rows))
    X[ri, [idx[r[2]] for r in rows]] = 1
    X[ri, [n + idx[r[3]] for r in rows]] = 1
    X[:, 2 * n] = 1
    X[:, 2 * n + 1] = [r[4] for r in rows]
    A = X.T @ X
    b = X.T @ np.array([r[stat_idx] for r in rows], float)
    key = {5: "ppa", 6: "sr", 7: "pts"}[stat_idx]
    for t, i in idx.items():
        o0, d0 = prior[t][key]
        A[i, i] += lam
        b[i] += lam * o0
        A[n + i, n + i] += lam
        b[n + i] += lam * d0
    A[2 * n, 2 * n] += 1e-6
    A[2 * n + 1, 2 * n + 1] += 1e-6
    if not rows:  # preseason: prior only, league mean from last season
        mu = {"ppa": 0.12, "sr": 0.41, "pts": 27.0}[key]
        return mu, 0.0, {t: prior[t][key] for t in teams}
    sol = np.linalg.solve(A, b)
    return sol[2 * n], sol[2 * n + 1], {t: (sol[idx[t]], sol[n + idx[t]]) for t in teams}


@lru_cache(None)
def ratings(year, week):
    """Ratings using games with week < `week`."""
    all_rows = offense_rows(year)
    teams = sorted({r[2] for r in all_rows} | {r[3] for r in all_rows} | {g["homeTeam"] for g in games(year)} | {g["awayTeam"] for g in games(year)})
    prior = _prior(year, teams)
    rows = [r for r in all_rows if r[1] < week]
    out = {}
    for key, si in STATS:
        out[key] = _ridge(rows, teams, si, prior, LAMBDA[key])
    out["n_games"] = {t: sum(1 for r in rows if r[2] == t) for t in teams}
    return out


def features(R, team, opp, loc):
    f = []
    for key, _ in STATS:
        mu, h, tab = R[key]
        f.append(mu + tab[team][0] + tab[opp][1] + h * loc)
    return f  # expected offensive ppa, success rate, points for `team`


POINTS_FILE = "cache/points_model.json"


def points_model():
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parent.parent / POINTS_FILE).read_text())


def project(year, week, home, away, neutral=False, adj=None):
    """Mean points for home and away. adj: {team: points} from research overrides + weather."""
    R = ratings(year, week)
    pm = points_model()
    lh, la = (0, 0) if neutral else (1, -1)
    out = []
    for t, o, l in ((home, away, lh), (away, home, la)):
        f = features(R, t, o, l)
        mu = pm["a"] + sum(pm["b_" + k] * v for (k, _), v in zip(STATS, f)) + pm["b_loc"] * l
        out.append(mu + (adj or {}).get(t, 0.0))
    return out[0], out[1]
