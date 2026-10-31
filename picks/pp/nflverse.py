"""NFL efficiency from nflverse (free play-by-play with EPA, success rate and CPOE; the data behind rbsdm.com).

Files come from the nflverse-data GitHub releases (https://github.com/nflverse/nflverse-data): `pbp` for
play-by-play and `schedules` for games.csv (scores and closing lines). The current season is re-downloaded
at most once per 20 hours (nflverse refreshes it nightly in season); past seasons once a year. Raw files stay
in cache/nflverse/ (gitignored, ~7-19 MB each); each season is boiled down once to a small per-team-game
summary JSON beside them, so later runs never re-read the big file unless it changed.

Team ratings are opponent-adjusted per-game averages (ridge, as in pp.model), shrunk toward last season's
final rating. Ratings at week w use only games before week w, so the backtest is walk-forward.
Team codes are ESPN's (LAR, WSH), matching the BTO slates; nflverse's LA and WAS are mapped on read.
"""
import csv, gzip, json, os, time
from functools import lru_cache
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "cache" / "nflverse"
REL = "https://github.com/nflverse/nflverse-data/releases/download"
TO_ESPN = {"LA": "LAR", "WAS": "WSH"}
SUMMARY_VERSION = 1


def espn(code):
    return TO_ESPN.get(code, code)


def _fetch(tag, name, max_age_h):
    """Download a release asset unless the cached copy is fresh. Falls back to a stale copy offline."""
    p = DIR / name
    if p.exists() and (time.time() - p.stat().st_mtime) / 3600 < max_age_h:
        return p
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    try:
        with requests.get(f"{REL}/{tag}/{name}", stream=True, timeout=120, headers={"User-Agent": "pool-picks/1.0"}) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(tmp, p)
    except Exception as ex:
        if tmp.exists():
            tmp.unlink()
        if p.exists():
            print(f"nflverse {name}: download failed ({ex}); using the cached copy")
            return p
        raise
    return p


def _age(season, current):
    return 20 if season >= current else 24 * 365


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@lru_cache(None)
def schedule(current=2026):
    """{game_id: game} for every regular-season game in games.csv: ESPN team codes, scores (None if not
    played), home_spread in our convention (negative = home favored; nflverse's spread_line is the
    closing line with positive = home favored), total, roof, neutral."""
    p = _fetch("schedules", "games.csv.gz", 20)
    out = {}
    with gzip.open(p, "rt", encoding="utf-8", newline="") as fh:
        for g in csv.DictReader(fh):
            if g["game_type"] != "REG":
                continue
            sl = _f(g["spread_line"])
            out[g["game_id"]] = {
                "id": g["game_id"], "season": int(g["season"]), "week": int(g["week"]),
                "home": espn(g["home_team"]), "away": espn(g["away_team"]),
                "home_score": _f(g["home_score"]), "away_score": _f(g["away_score"]),
                "home_spread": -sl if sl is not None else None, "total": _f(g["total_line"]),
                "roof": g["roof"], "neutral": g["location"] == "Neutral", "espn_id": g["espn"],
            }
    return out


def _summarize(path):
    """One row per team-game offense from a play-by-play csv.gz. Plays: dropbacks and runs with an EPA
    (no-play penalties included, kneels and spikes excluded). 'Neutral' plays have a 10-90% win
    probability outside the last two minutes of each half; early-down pass rate uses those."""
    rows = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        rd = csv.reader(fh)
        h = next(rd)
        ix = {k: i for i, k in enumerate(h)}
        need = ("game_id", "season_type", "week", "home_team", "away_team", "posteam", "defteam", "epa", "success",
                "pass", "rush", "wp", "half_seconds_remaining", "down", "cpoe", "pass_oe", "play_type", "yards_gained",
                "interception", "fumble_lost", "sack", "location")
        I = {k: ix[k] for k in need}
        for r in rd:
            if r[I["season_type"]] != "REG" or r[I["play_type"]] in ("qb_kneel", "qb_spike"):
                continue
            ps, ru = r[I["pass"]] == "1", r[I["rush"]] == "1"
            epa = _f(r[I["epa"]])
            if not (ps or ru) or epa is None or not r[I["posteam"]]:
                continue
            gid, team = r[I["game_id"]], espn(r[I["posteam"]])
            row = rows.get((gid, team))
            if row is None:
                home = espn(r[I["home_team"]]) == team
                loc = 0 if r[I["location"]] == "Neutral" else (1 if home else -1)
                row = rows[(gid, team)] = {"game_id": gid, "week": int(r[I["week"]]), "team": team, "opp": espn(r[I["defteam"]]),
                                           "loc": loc, "n": 0, "epa": 0.0, "sr": 0.0, "p_n": 0, "p_epa": 0.0, "p_sr": 0.0,
                                           "r_n": 0, "r_epa": 0.0, "r_sr": 0.0, "nn": 0, "n_epa": 0.0, "n_sr": 0.0,
                                           "ed_n": 0, "ed_pass": 0, "cp_n": 0, "cpoe": 0.0, "oe_n": 0, "pass_oe": 0.0,
                                           "expl": 0, "to": 0, "sacks": 0}
            s = 1.0 if r[I["success"]] == "1" else 0.0
            row["n"] += 1; row["epa"] += epa; row["sr"] += s
            k = "p_" if ps else "r_"
            row[k + "n"] += 1; row[k + "epa"] += epa; row[k + "sr"] += s
            yds = _f(r[I["yards_gained"]]) or 0
            row["expl"] += int(yds >= (20 if ps else 10))
            row["to"] += int(r[I["interception"]] == "1") + int(r[I["fumble_lost"]] == "1")
            row["sacks"] += int(r[I["sack"]] == "1")
            wp, hs = _f(r[I["wp"]]), _f(r[I["half_seconds_remaining"]])
            if wp is not None and 0.1 <= wp <= 0.9 and (hs or 0) > 120:
                row["nn"] += 1; row["n_epa"] += epa; row["n_sr"] += s
                if r[I["down"]] in ("1", "2"):
                    row["ed_n"] += 1; row["ed_pass"] += int(ps)
            c = _f(r[I["cpoe"]])
            if c is not None:
                row["cp_n"] += 1; row["cpoe"] += c
            oe = _f(r[I["pass_oe"]])
            if oe is not None:
                row["oe_n"] += 1; row["pass_oe"] += oe
    return list(rows.values())


@lru_cache(None)
def team_games(season, current=2026):
    """Per team-game offense rows for `season`, with points scored from the schedule."""
    p = _fetch("pbp", f"play_by_play_{season}.csv.gz", _age(season, current))
    sp = DIR / f"team_games_{season}.json"
    src = int(p.stat().st_mtime)
    if sp.exists():
        d = json.loads(sp.read_text())
        if d.get("src") == src and d.get("v") == SUMMARY_VERSION:
            rows = d["rows"]
        else:
            rows = None
    else:
        rows = None
    if rows is None:
        rows = _summarize(p)
        sp.write_text(json.dumps({"src": src, "v": SUMMARY_VERSION, "rows": rows}))
    S = schedule(current)
    for r in rows:
        g = S.get(r["game_id"]) or {}
        r["pts"] = g.get("home_score") if g.get("home") == r["team"] else g.get("away_score")
    return rows


# Per-game values the ratings adjust. y(row) -> float or None (too few plays).
METRICS = {
    "epa": lambda r: r["epa"] / r["n"] if r["n"] else None,
    "sr": lambda r: r["sr"] / r["n"] if r["n"] else None,
    "pass": lambda r: r["p_epa"] / r["p_n"] if r["p_n"] >= 5 else None,
    "rush": lambda r: r["r_epa"] / r["r_n"] if r["r_n"] >= 5 else None,
    "pass_sr": lambda r: r["p_sr"] / r["p_n"] if r["p_n"] >= 5 else None,
    "rush_sr": lambda r: r["r_sr"] / r["r_n"] if r["r_n"] >= 5 else None,
    "expl": lambda r: r["expl"] / r["n"] if r["n"] else None,
    "pts": lambda r: r["pts"],
}
LAMBDA = 4.0       # the prior is worth ~4 games
CARRY = 0.5        # share of last season's final rating carried into the new season's prior


def _ridge(rows, teams, prior, lam):
    """y = mu + O[team] + D[opp] + h*loc, ridge toward prior {team: (o, d)} (deviations from mu)."""
    import numpy as np
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    if not rows:
        return None, 0.0, dict(prior)
    X = np.zeros((len(rows), 2 * n + 2))
    ri = np.arange(len(rows))
    X[ri, [ix[r[0]] for r in rows]] = 1
    X[ri, [n + ix[r[1]] for r in rows]] = 1
    X[:, 2 * n] = 1
    X[:, 2 * n + 1] = [r[2] for r in rows]
    A = X.T @ X
    b = X.T @ np.array([r[3] for r in rows], float)
    for t, i in ix.items():
        o0, d0 = prior.get(t, (0.0, 0.0))
        A[i, i] += lam; b[i] += lam * o0
        A[n + i, n + i] += lam; b[n + i] += lam * d0
    A[2 * n, 2 * n] += 1e-6
    A[2 * n + 1, 2 * n + 1] += 1e-6
    sol = np.linalg.solve(A, b)
    return float(sol[2 * n]), float(sol[2 * n + 1]), {t: (float(sol[ix[t]]), float(sol[n + ix[t]])) for t in teams}


def _rows(season, metric, week=None, current=2026):
    y = METRICS[metric]
    out = []
    for r in team_games(season, current):
        if week is not None and r["week"] >= week:
            continue
        v = y(r)
        if v is not None:
            out.append((r["team"], r["opp"], r["loc"], float(v)))
    return out


@lru_cache(None)
def ratings(season, week, metric="epa", current=2026, lam=LAMBDA, carry=CARRY):
    """{"mu", "hfa", "tab": {team: (offense, defense allowed)}} as deviations from the league average,
    from games before `week` (week 99 = the whole season). Prior: `carry` × last season's final rating."""
    rows = _rows(season, metric, week, current)
    teams = sorted({r[0] for r in rows} | {r[1] for r in rows} | {g["home"] for g in schedule(current).values() if g["season"] == season})
    prior = {}
    if season - 1 >= 2023 and carry:
        try:
            last = ratings(season - 1, 99, metric, current, lam, 0.0)
            prior = {t: (carry * o, carry * d) for t, (o, d) in last["tab"].items()}
        except Exception as ex:
            print(f"nflverse {season - 1} prior unavailable:", ex)
    mu, h, tab = _ridge(rows, teams, prior, lam)
    if mu is None:
        last_rows = _rows(season - 1, metric, None, current) if season - 1 >= 2023 else []
        mu = sum(r[3] for r in last_rows) / len(last_rows) if last_rows else 0.0
    return {"mu": mu, "hfa": h, "tab": tab, "games": sum(1 for r in rows)}


# Margin map, fit on 2023-2024 walk-forward (pp.backtest nfl_fit): home margin =
# a + k_epa * (expected home EPA/play - away) + k_sr * (expected SR edge). Written by `py -m pp.backtest --nfl-fit`.
MARGIN_FILE = ROOT / "cache" / "nfl_margin_model.json"


def margin_model():
    return json.loads(MARGIN_FILE.read_text())


def edges(season, week, home, away, neutral=False, current=2026):
    """Expected per-play EPA and success-rate edges for the home offense minus the away offense."""
    out = {}
    for m in ("epa", "sr"):
        R = ratings(season, week, m, current)
        T = R["tab"]
        ho, hd = T.get(home, (0.0, 0.0))
        ao, ad = T.get(away, (0.0, 0.0))
        out[m] = (ho + ad) - (ao + hd)
    return out


def predict(season, week, home, away, neutral=False, current=2026, mm=None):
    """Stats-only home margin from opponent-adjusted EPA and success rate (no spread input)."""
    mm = mm or margin_model()
    e = edges(season, week, home, away, neutral, current)
    return mm["a"] * (0 if neutral else 1) + mm["k_epa"] * e["epa"] + mm["k_sr"] * e["sr"]


def _rank(vals, higher_better):
    order = sorted((t for t in vals if vals[t] is not None), key=lambda t: vals[t], reverse=higher_better)
    return {t: i + 1 for i, t in enumerate(order)}


@lru_cache(None)
def profiles(season, week, current=2026):
    """{team: {facet: {o, d, ro, rd}}} for the Picks page breakdowns and the card data, plus style stats
    (early-down pass rate, pass rate over expected, CPOE; raw season averages) and games played.
    Facets are opponent-adjusted per-play values vs an average opponent; ranks 1-32, 1 = best."""
    P = {}
    for m, hb in (("epa", True), ("sr", True), ("pass", True), ("rush", True), ("expl", True)):
        R = ratings(season, week, m, current)
        vals = {t: (R["mu"] + o, R["mu"] + d) for t, (o, d) in R["tab"].items()}
        ro = _rank({t: v[0] for t, v in vals.items()}, hb)
        rd = _rank({t: v[1] for t, v in vals.items()}, not hb)
        for t, (o, d) in vals.items():
            P.setdefault(t, {})[m] = {"o": o, "d": d, "ro": ro.get(t), "rd": rd.get(t)}
    agg = {}
    for r in team_games(season, current):
        if r["week"] >= week:
            continue
        a = agg.setdefault(r["team"], {"g": 0, "ed_n": 0, "ed_pass": 0, "cp_n": 0, "cpoe": 0.0, "oe_n": 0, "pass_oe": 0.0, "to": 0})
        a["g"] += 1
        for k in ("ed_n", "ed_pass", "cp_n", "cpoe", "oe_n", "pass_oe", "to"):
            a[k] += r[k]
    style = {t: {"ed_pass": a["ed_pass"] / a["ed_n"] if a["ed_n"] else None,
                 "proe": a["pass_oe"] / a["oe_n"] if a["oe_n"] else None,
                 "cpoe": a["cpoe"] / a["cp_n"] if a["cp_n"] else None,
                 "to_pg": a["to"] / a["g"] if a["g"] else None, "g": a["g"]} for t, a in agg.items()}
    for k, hb in (("ed_pass", True), ("proe", True), ("cpoe", True), ("to_pg", False)):
        rk = _rank({t: s[k] for t, s in style.items()}, hb)
        for t, s in style.items():
            P.setdefault(t, {})[k] = {"o": s[k], "ro": rk.get(t)}
    for t, s in style.items():
        P[t]["g"] = s["g"]
    return P


def stats_dict(season, week, home, away, current=2026):
    """Compact per-game stats for the card data (`data/cards.json` game_stats) and the breakdown panels:
    {team: {facet: [value, rank]}} with offense (o_*) and defense-allowed (d_*) EPA/play, success rate,
    EPA/pass, EPA/rush, explosive-play rate, plus early-down pass rate, PROE, CPOE, turnovers/g."""
    P = profiles(season, week, current)
    out = {"source": "nflverse play-by-play", "through_week": week - 1, "teams": {}}
    for t in (away, home):
        T = P.get(t, {})
        d = {}
        for m in ("epa", "sr", "pass", "rush", "expl"):
            f = T.get(m) or {}
            d["o_" + m] = [_r(f.get("o")), f.get("ro")]
            d["d_" + m] = [_r(f.get("d")), f.get("rd")]
        for k in ("ed_pass", "proe", "cpoe", "to_pg"):
            f = T.get(k) or {}
            d[k] = [_r(f.get("o")), f.get("ro")]
        d["games"] = T.get("g", 0)
        out["teams"][t] = d
    return out


def _r(x):
    return None if x is None else round(float(x), 4)
