"""NFL margins for BTO's NFL games: the market line plus research, sampled with NFL key-number weighting
(3, 7, 10, 14). Stats margin: opponent-adjusted EPA/play and success rate from nflverse play-by-play
(pp.nflverse); if nflverse is unavailable, ridge power ratings from this season's ESPN scores."""
from functools import lru_cache
import numpy as np
from .http import get_json

SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
KEY_W = {0: 0.1, 1: 1.0, 2: 0.9, 3: 2.2, 4: 1.15, 6: 1.2, 7: 1.7, 8: 1.05, 10: 1.3, 14: 1.3, 17: 1.1}


@lru_cache(None)
def results(year=2026, through_week=18):
    """[(home, away, home margin, neutral)] for completed games: nflverse's schedule file (one 0.5 MB download
    per 6h), with ESPN's scoreboards as the backup when nflverse is down or behind."""
    from . import nflverse
    try:
        return [(r["home"], r["away"], r["home_score"] - r["away_score"], r["neutral"])
                for r in nflverse.results(year, current=year) if r["week"] <= through_week]
    except Exception as ex:
        print("nflverse results unavailable, using ESPN:", ex)
    return espn_results(year, through_week)


def espn_results(year=2026, through_week=18):
    out = []
    for w in range(1, through_week + 1):
        d = get_json("espn", SB, max_age_h=12, seasontype=2, week=w, dates=year)
        for e in d.get("events", []):
            c = e["competitions"][0]
            if not c["status"]["type"]["completed"]:
                continue
            t = {x["homeAway"]: x for x in c["competitors"]}
            out.append((t["home"]["team"]["abbreviation"], t["away"]["team"]["abbreviation"],
                        int(t["home"]["score"]) - int(t["away"]["score"]), c.get("neutralSite", False)))
    return out


@lru_cache(None)
def ratings(year=2026):
    rs = results(year)
    teams = sorted({r[0] for r in rs} | {r[1] for r in rs})
    ix = {t: i for i, t in enumerate(teams)}
    X = np.zeros((len(rs), len(teams) + 1)); y = np.zeros(len(rs))
    for k, (h, a, m, neu) in enumerate(rs):
        X[k, ix[h]] = 1; X[k, ix[a]] = -1; X[k, -1] = 0 if neu else 1; y[k] = m
    lam = np.eye(len(teams) + 1) * 2.0; lam[-1, -1] = 1e-6
    sol = np.linalg.solve(X.T @ X + lam, X.T @ y)
    return {t: sol[ix[t]] for t in teams}, float(sol[-1])


def _team(name, R):
    n = name.upper().strip()
    if n in R:
        return n
    raise KeyError(f"NFL team {name}: use ESPN abbreviations like KC, SEA")


def market_home_spread(home, away, week, year=2026):
    """ESPN's current line (15-min cache), so the sim centers on the market at build time."""
    from .lines import espn_odds
    try:
        events = espn_odds("NFL", week, year)
    except Exception as ex:
        print("ESPN NFL odds unavailable:", ex)
        return None
    for e in events:
        if {e["home_abbr"], e["away_abbr"]} == {home, away} and e["home_spread"] is not None:
            return e["home_spread"] if e["home_abbr"] == home else -e["home_spread"]
    return None


# Backtest (pp.backtest --nfl, 2023-2026 vs the closing line, n=860): the least-squares weight on
# (stats - market) was negative for both stats models and walk-forward picked 0 every week, so the cards
# use the market + research only. Stats stay on the breakdown panels as context.
MODEL_W = 0.0


def stats_margin(home, away, week, neutral=False, year=2026):
    """(home margin, source): nflverse EPA/SR model, else ESPN-scores ridge ratings."""
    from . import nflverse
    try:
        return nflverse.predict(year, week or 99, home, away, neutral, current=year), "nflverse EPA/success"
    except Exception as ex:
        print("nflverse unavailable, using score ratings:", ex)
    R, hfa = ratings(year)
    return R[_team(home, R)] - R[_team(away, R)] + (0 if neutral else hfa), "ESPN scores"


def nfl_sim(sg, rng, n=10_000, sd=13.5):
    """Fair margin = current market + MODEL_W x (stats - market) + research adjustment; samples with key numbers."""
    R, hfa = ratings()
    h, a = _team(sg["home"], R), _team(sg["away"], R)
    stats, _ = stats_margin(h, a, sg.get("nfl_week"), sg.get("neutral"))
    mk = market_home_spread(h, a, sg.get("nfl_week"))
    if mk is None:
        mk = sg.get("market_home_spread")  # the laptop run's researched line
    base_mu = stats if mk is None else -mk + MODEL_W * (stats - (-mk))
    mu = base_mu + sg.get("adj_home_pts", 0)
    support = np.arange(-60, 61)
    base = np.exp(-((support - mu) ** 2) / (2 * sd * sd)) * np.array([KEY_W.get(abs(int(s)), 1.0) for s in support])
    m = rng.choice(support, size=n, p=base / base.sum())
    return m, f"https://www.espn.com/nfl/scoreboard/_/week/{sg.get('nfl_week', '')}", sg.get("why", [])
