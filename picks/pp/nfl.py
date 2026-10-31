"""Stats-only NFL margins for BTO's NFL games: ridge power ratings from this season's results
(ESPN public scoreboard), Monte Carlo margins with NFL key-number weighting (3, 7, 10, 14)."""
from functools import lru_cache
import numpy as np
from .http import get_json

SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
KEY_W = {0: 0.1, 1: 1.0, 2: 0.9, 3: 2.2, 4: 1.15, 6: 1.2, 7: 1.7, 8: 1.05, 10: 1.3, 14: 1.3, 17: 1.1}


@lru_cache(None)
def results(year=2026, through_week=18):
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


MODEL_W = 0.1  # backtest: stats margins add ~nothing beyond the market line; small weight only


def nfl_sim(sg, rng, n=10_000, sd=13.5):
    """Fair margin = current market + small stats tilt + research adjustment; samples with key numbers."""
    R, hfa = ratings()
    h, a = _team(sg["home"], R), _team(sg["away"], R)
    stats = R[h] - R[a] + (0 if sg.get("neutral") else hfa)
    mk = market_home_spread(h, a, sg.get("nfl_week"))
    if mk is None:
        mk = sg.get("market_home_spread")  # the laptop run's researched line
    base_mu = stats if mk is None else -mk + MODEL_W * (stats - (-mk))
    mu = base_mu + sg.get("adj_home_pts", 0)
    support = np.arange(-60, 61)
    base = np.exp(-((support - mu) ** 2) / (2 * sd * sd)) * np.array([KEY_W.get(abs(int(s)), 1.0) for s in support])
    m = rng.choice(support, size=n, p=base / base.sum())
    return m, f"https://www.espn.com/nfl/scoreboard/_/week/{sg.get('nfl_week', '')}", sg.get("why", [])
