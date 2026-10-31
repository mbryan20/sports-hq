"""Walk-forward backtest of the stats-only model: calibration, accuracy, ATS, the market-vs-model
weight used by the ATS cards (MODEL_W), and whether stale lines (open vs close) cover.

Usage: py -m pp.backtest [--through N] [--nfl] [--cfb-features]
  writes backtest/2026_w1-N.json (N = last graded week); --nfl adds backtest/nfl_2023-2026.json (nflverse EPA
  model and score ratings vs the closing line) and refits cache/nfl_margin_model.json; --cfb-features adds
  backtest/cfb_features_w1-N.json (extra CFBD stats as model features).
"""
import argparse, json
from pathlib import Path
import numpy as np
from . import model as M
from .http import get_json
from .lines import GAP_ALERT, KEYS, key_crossed
from .market import lines
from .nfl import SB as NFL_SB
from .sim import sim_game

ROOT = Path(__file__).resolve().parent.parent


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def run(year=2026, weeks=range(1, 9)):
    rng = np.random.default_rng(7)
    L = lines(year)
    fbs = M.fbs_teams(year)
    out = []
    for w in weeks:
        for g in M.games(year):
            if g["week"] != w or not g.get("completed") or g["homeTeam"] not in fbs or g["awayTeam"] not in fbs:
                continue
            mh, ma = M.project(year, w, g["homeTeam"], g["awayTeam"], g.get("neutralSite"))
            h, a = sim_game(mh, ma, rng)
            mk = L.get(g["id"])
            out.append({
                "week": w, "home": g["homeTeam"], "away": g["awayTeam"],
                "p_model": float((h > a).mean()), "p_mkt": mk["p_home"] if mk else None,
                "model_margin": float(np.mean(h - a)), "home_spread": mk["home_spread"] if mk else None,
                "open_spread": mk["open_spread"] if mk else None,
                "home_won": int(g["homePoints"] > g["awayPoints"]), "margin": g["homePoints"] - g["awayPoints"],
            })
    return out


def report(rows):
    p = np.array([r["p_model"] for r in rows]); y = np.array([r["home_won"] for r in rows])
    pick_p = np.where(p >= 0.5, p, 1 - p); hit = np.where(p >= 0.5, y, 1 - y)
    bins = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    cal = []
    for lo, hi in bins:
        m = (pick_p >= lo) & (pick_p < hi)
        if m.sum():
            cal.append({"bin": f"{int(lo*100)}-{min(int(hi*100),100)}%", "n": int(m.sum()), "pred": float(pick_p[m].mean()), "hit": float(hit[m].mean())})
    wm = [r for r in rows if r["p_mkt"] is not None]
    pm = np.array([r["p_model"] for r in wm]); pk = np.array([r["p_mkt"] for r in wm]); yk = np.array([r["home_won"] for r in wm])
    pb = 1 / (1 + np.exp(-(0.5 * logit(pm) + 0.5 * logit(pk))))
    brier = {k: float(np.mean((v - yk) ** 2)) for k, v in (("model", pm), ("market", pk), ("blend", pb))}
    acc = {k: float(np.mean((v >= 0.5) == yk)) for k, v in (("model", pm), ("market", pk))}
    # ATS: model disagrees with spread by 3+ points
    ats = []
    for r in wm:
        edge = r["model_margin"] + r["home_spread"]  # >0: model likes home vs line
        res = r["margin"] + r["home_spread"]
        if abs(edge) >= 3 and res != 0:
            ats.append(int((edge > 0) == (res > 0)))
    return {"n": len(rows), "calibration": cal, "brier": brier, "su_accuracy": acc, "n_market": len(wm),
            "ats_edge3": {"n": len(ats), "hit": float(np.mean(ats)) if ats else None}}


def _rmse(x):
    return float(np.sqrt(np.mean(np.square(x))))


def weight_study(rows, grid=(0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)):
    """ATS cards center on market + w * (stats - market). For each week group: margin RMSE per w, the
    least-squares w (actual - market on stats - market) and, walk-forward, a w picked on prior weeks only."""
    wm = [r for r in rows if r["home_spread"] is not None]

    def de(rs):  # d = stats - market, e = actual - market (home margins)
        mkt = -np.array([r["home_spread"] for r in rs], float)
        return np.array([r["model_margin"] for r in rs]) - mkt, np.array([r["margin"] for r in rs], float) - mkt
    out = {"groups": {}, "walk_forward": []}
    weeks = sorted({r["week"] for r in wm})
    last = max(weeks)
    for name, lo, hi in (("early", 1, 4), ("mid", 5, last - 3), ("late", last - 2, last), ("all", 1, last)):
        rs = [r for r in wm if lo <= r["week"] <= hi]
        if not rs:
            continue
        d, e = de(rs)
        w_ls = float(d @ e / (d @ d))
        se = float(np.sqrt(np.mean((e - w_ls * d) ** 2) / (d @ d)))
        big = (np.abs(d) >= 3) & (e != 0)
        ats = np.sign(d[big]) == np.sign(e[big])
        out["groups"][name] = {"weeks": f"{lo}-{hi}", "n": len(rs), "rmse": {str(w): round(_rmse(e - w * d), 3) for w in grid},
                               "w_ls": round(w_ls, 3), "w_ls_se": round(se, 3),
                               "ats_model_disagrees_3plus": {"n": int(ats.size), "hit": round(float(ats.mean()), 3) if ats.size else None}}
    fine = np.round(np.arange(0, 1.001, 0.05), 2)
    tot = {"walk_forward": [], "fixed_0.1": [], "market_only": []}
    for k in weeks[2:]:
        d0, e0 = de([r for r in wm if r["week"] < k])
        w = float(fine[np.argmin([np.mean((e0 - f * d0) ** 2) for f in fine])])
        d1, e1 = de([r for r in wm if r["week"] == k])
        out["walk_forward"].append({"week": k, "w_chosen": w, "rmse": round(_rmse(e1 - w * d1), 3),
                                    "rmse_w0.1": round(_rmse(e1 - 0.1 * d1), 3), "rmse_market": round(_rmse(e1), 3)})
        tot["walk_forward"] += list(e1 - w * d1); tot["fixed_0.1"] += list(e1 - 0.1 * d1); tot["market_only"] += list(e1)
    out["walk_forward_total_rmse"] = {k: round(_rmse(v), 3) for k, v in tot.items()}
    return out


def nfl_open_close(year=2026, weeks=range(1, 19)):
    """Completed NFL games with ESPN's (DraftKings) opening and closing home spread from the game summary."""
    out = []
    for w in weeks:
        d = get_json("espn", NFL_SB, max_age_h=24 * 30, seasontype=2, week=w, dates=year)
        for e in d.get("events", []):
            c = e["competitions"][0]
            if not c["status"]["type"]["completed"]:
                continue
            t = {x["homeAway"]: x for x in c["competitors"]}
            s = get_json("espn", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary", max_age_h=24 * 365, event=e["id"])
            ps = ((s.get("pickcenter") or [{}])[0].get("pointSpread") or {}).get("home") or {}
            try:
                op, cl = float(ps["open"]["line"]), float(ps["close"]["line"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append({"league": "NFL", "week": w, "home": t["home"]["team"]["abbreviation"], "away": t["away"]["team"]["abbreviation"],
                        "open_spread": op, "home_spread": cl, "margin": int(t["home"]["score"]) - int(t["away"]["score"])})
    return out


def stale_study(rows):
    """Stand-in for a pool's early-week line: the opener. Take the side the market moved away from at the
    opening number and grade it (win 1, push 0.5, loss 0). Buckets follow the scanner's push rule
    (1.5+ points or a key number)."""
    res = {}
    for league in ("CFB", "NFL"):
        b = {"gap_1.5_plus": [], "key_only_under_1.5": [], "flagged_any": [], "gap_under_1.5_no_key": [], "flagged_same_side_vs_close": []}
        for r in rows:
            if r.get("league", "CFB") != league or r.get("open_spread") is None or r.get("home_spread") is None:
                continue
            op, cl = r["open_spread"], r["home_spread"]
            gap = abs(op - cl)
            if gap < 0.5:
                continue
            home_value = op > cl  # the opener gave the home side more points than the close
            s_pool, s_mkt = (op, cl) if home_value else (-op, -cl)
            m = r["margin"] if home_value else -r["margin"]
            keys = key_crossed(s_pool, s_mkt, KEYS[league])
            x = m + s_pool
            hit = 1.0 if x > 0 else 0.5 if x == 0 else 0.0  # a push counts half, as in p_cover
            flagged = gap >= GAP_ALERT or bool(keys)
            b["gap_1.5_plus" if gap >= GAP_ALERT else "key_only_under_1.5" if keys else "gap_under_1.5_no_key"].append(hit)
            if flagged:
                b["flagged_any"].append(hit)
                xc = m + s_mkt
                b["flagged_same_side_vs_close"].append(1.0 if xc > 0 else 0.5 if xc == 0 else 0.0)
        res[league] = {k: {"n": len(v), "cover": round(float(np.mean(v)), 3) if v else None,
                           "se": round(float(np.sqrt(np.mean(v) * (1 - np.mean(v)) / len(v))), 3) if v else None} for k, v in b.items()}
    return res


def nfl_study(seasons=(2023, 2024, 2025, 2026), fit=(2023, 2024)):
    """NFL vs the closing line (nflverse schedules), walk-forward from week 2. Two stats models:
    'epa' = opponent-adjusted EPA/play and success rate from nflverse play-by-play (margin map fit on `fit`
    seasons and written to cache/nfl_margin_model.json), 'scores' = the cards' ridge on this season's scores.
    For each: per-season least-squares weight on (model - market), ATS when the model differs by 3+,
    straight-up accuracy, margin RMSE at w = 0 / 0.1, and a walk-forward w (picked on prior games only)."""
    from . import nflverse as N
    rows = []
    for g in N.schedule().values():
        if g["season"] not in seasons or g["week"] < 2 or g["home_score"] is None or g["home_spread"] is None:
            continue
        s, w = g["season"], g["week"]
        e = N.edges(s, w, g["home"], g["away"], g["neutral"])
        R = N.ratings(s, w, "pts", lam=2.0, carry=0.0)  # same shape as pp.nfl.ratings: this season's scores only
        ho, hd = R["tab"].get(g["home"], (0, 0)); ao, ad = R["tab"].get(g["away"], (0, 0))
        rows.append({"season": s, "week": w, "home": g["home"], "away": g["away"], "neutral": g["neutral"],
                     "e_epa": e["epa"], "e_sr": e["sr"], "scores": (ho + ad) - (ao + hd) + (0 if g["neutral"] else R["hfa"]),
                     "mkt": -g["home_spread"], "margin": g["home_score"] - g["away_score"]})
    tr = [r for r in rows if r["season"] in fit]
    X = np.array([[0 if r["neutral"] else 1, r["e_epa"], r["e_sr"]] for r in tr])
    b, *_ = np.linalg.lstsq(X, np.array([r["margin"] for r in tr], float), rcond=None)
    mm = {"a": float(b[0]), "k_epa": float(b[1]), "k_sr": float(b[2]), "fit": f"{min(fit)}-{max(fit)} weeks 2-18, walk-forward ratings", "n": len(tr)}
    N.MARGIN_FILE.write_text(json.dumps(mm, indent=1), newline="\n")
    for r in rows:
        r["epa"] = mm["a"] * (0 if r["neutral"] else 1) + mm["k_epa"] * r["e_epa"] + mm["k_sr"] * r["e_sr"]

    def stats(rs, key):
        p = np.array([r[key] for r in rs]); mk = np.array([r["mkt"] for r in rs]); y = np.array([r["margin"] for r in rs], float)
        d, e = p - mk, y - mk
        w = float(d @ e / (d @ d))
        se = float(np.sqrt(np.mean((e - w * d) ** 2) / (d @ d)))
        big = (np.abs(d) >= 3) & (e != 0)
        nz = y != 0
        return {"n": len(rs), "w_ls": round(w, 3), "w_ls_se": round(se, 3),
                "ats_model_differs_3plus": {"n": int(big.sum()), "hit": round(float(np.mean(np.sign(d[big]) == np.sign(e[big]))), 3) if big.any() else None},
                "su": {"model": round(float(np.mean((p[nz] > 0) == (y[nz] > 0))), 3), "market": round(float(np.mean((mk[nz] > 0) == (y[nz] > 0))), 3)},
                "rmse": {"model": round(_rmse(y - p), 3), "w0": round(_rmse(e), 3), "w0.1": round(_rmse(e - 0.1 * d), 3)}}
    out = {"margin_model": mm, "note": "Market = nflverse closing spread_line. 'epa' margin map fit on " + mm["fit"] + "; its 2023-24 rows are in-sample for the map, not the ratings."}
    fine = np.round(np.arange(0, 1.001, 0.05), 2)
    for key in ("epa", "scores"):
        res = {str(s): stats([r for r in rows if r["season"] == s], key) for s in seasons}
        res["all"] = stats(rows, key)
        res["out_of_sample"] = stats([r for r in rows if r["season"] not in fit], key)
        wf, tot, base = [], [], []
        order = sorted({(r["season"], r["week"]) for r in rows})
        for sw in order[8:]:
            prior = [r for r in rows if (r["season"], r["week"]) < sw]
            d0 = np.array([r[key] - r["mkt"] for r in prior]); e0 = np.array([r["margin"] - r["mkt"] for r in prior], float)
            w = float(fine[np.argmin([np.mean((e0 - f * d0) ** 2) for f in fine])])
            cur = [r for r in rows if (r["season"], r["week"]) == sw]
            wf.append(w)
            tot += [r["margin"] - r["mkt"] - w * (r[key] - r["mkt"]) for r in cur]
            base += [r["margin"] - r["mkt"] for r in cur]
        res["walk_forward"] = {"weeks": len(wf), "w_chosen_share_zero": round(float(np.mean(np.array(wf) == 0)), 3),
                               "w_chosen_max": float(max(wf)), "rmse": round(_rmse(tot), 3), "rmse_market": round(_rmse(base), 3)}
        out[key] = res
    return out, rows


# Extra CFBD game-level stats tried as points-model features (pp.backtest --cfb-features).
CFB_EXTRA = {"expl": lambda o: o["explosiveness"], "line": lambda o: o["lineYards"],
             "pdsr": lambda o: o["passingDowns"]["successRate"], "sdsr": lambda o: o["standardDowns"]["successRate"],
             "stuff": lambda o: o["stuffRate"], "rush": lambda o: o["rushingPlays"]["ppa"], "pass": lambda o: o["passingPlays"]["ppa"]}
CFB_SETS = ((), ("expl",), ("line",), ("pdsr", "sdsr"), ("rush", "pass"), ("expl", "line", "pdsr", "stuff", "rush", "pass"))


def cfb_feature_study(fit_year=2025, test_year=2026, test_weeks=range(1, 9)):
    """Does adding explosiveness, line yards, down splits, stuff rate or run/pass PPA (each opponent-adjusted
    like EPA, ridge toward average) to the points model help? Fit on `fit_year` weeks 2-14 walk-forward, test
    on `test_year`: margin RMSE, straight-up accuracy and the least-squares weight vs the CFBD consensus line."""
    from functools import lru_cache
    L = lines(test_year)
    fbs = M.fbs_teams(test_year)

    @lru_cache(None)
    def xrows(year, key):
        gmap = {g["id"]: g for g in M.games(year)}
        out = []
        for r in M.adv(year):
            g = gmap.get(r["gameId"])
            try:
                v = CFB_EXTRA[key](r["offense"]) if g else None
            except (KeyError, TypeError):
                v = None
            if v is not None:
                out.append((r["gameId"], g["week"], r["team"], r["opponent"], M._loc(g, r["team"]), float(v)))
        return out

    @lru_cache(None)
    def xrat(year, week, key):
        rows = [r for r in xrows(year, key) if r[1] < week]
        teams = sorted({r[2] for r in xrows(year, key)} | {r[3] for r in xrows(year, key)})
        return M._ridge(rows, teams, 5, {t: {"ppa": (0, 0)} for t in teams}, 3.0) if rows else None

    def data(year, weeks, keys):
        X, y, ids = [], [], []
        for w in weeks:
            R = M.ratings(year, w)
            for r in M.offense_rows(year):
                if r[1] != w:
                    continue
                f = M.features(R, r[2], r[3], r[4])
                for k in keys:
                    x = xrat(year, w, k)
                    f.append(0.0 if x is None else x[0] + x[2].get(r[2], (0, 0))[0] + x[2].get(r[3], (0, 0))[1] + x[1] * r[4])
                X.append([1, *f, r[4]]); y.append(r[7]); ids.append((r[0], r[2]))
        return np.array(X), np.array(y, float), ids

    out = {}
    for keys in CFB_SETS:
        X, y, _ = data(fit_year, range(2, 15), keys)
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        Xt, _, ids = data(test_year, test_weeks, keys)
        pred = dict(zip(ids, Xt @ b))
        d, e, su = [], [], []
        for g in M.games(test_year):
            mk = L.get(g["id"])
            if g["week"] not in test_weeks or not g.get("completed") or g["homeTeam"] not in fbs or g["awayTeam"] not in fbs or not mk:
                continue
            ph, pa = pred.get((g["id"], g["homeTeam"])), pred.get((g["id"], g["awayTeam"]))
            if ph is None or pa is None:
                continue
            act, mkt = g["homePoints"] - g["awayPoints"], -mk["home_spread"]
            d.append(ph - pa - mkt); e.append(act - mkt); su.append((ph > pa) == (act > 0))
        d, e = np.array(d), np.array(e)
        w = float(d @ e / (d @ d))
        out["+".join(keys) or "base (EPA, SR, points)"] = {
            "n": len(d), "rmse_model": round(_rmse(e - d), 3), "rmse_market": round(_rmse(e), 3), "su_model": round(float(np.mean(su)), 3),
            "w_ls": round(w, 3), "w_ls_se": round(float(np.sqrt(np.mean((e - w * d) ** 2) / (d @ d))), 3)}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", type=int, default=8, help="last graded CFBD week")
    ap.add_argument("--nfl", action="store_true", help="also run the NFL study (nflverse; downloads ~60 MB once)")
    ap.add_argument("--cfb-features", action="store_true", help="also test extra CFBD stats as model features (cached data only)")
    a = ap.parse_args()
    if a.cfb_features:
        crep = cfb_feature_study(test_weeks=range(1, a.through + 1))
        (ROOT / "backtest").mkdir(exist_ok=True)
        (ROOT / f"backtest/cfb_features_w1-{a.through}.json").write_text(json.dumps(crep, indent=1), newline="\n")
        print(json.dumps(crep, indent=1))
    if a.nfl:
        nrep, nrows = nfl_study()
        (ROOT / "backtest").mkdir(exist_ok=True)
        (ROOT / "backtest/nfl_2023-2026.json").write_text(json.dumps({"report": nrep}, indent=1), newline="\n")
        print(json.dumps(nrep, indent=1))
    rows = run(weeks=range(1, a.through + 1))
    rep = report(rows)
    rep["model_weight"] = weight_study(rows)
    nfl = nfl_open_close(weeks=range(1, a.through))  # CFBD week N = NFL week N-1
    rep["stale_lines"] = stale_study(rows + nfl)
    rep["stale_lines"]["note"] = "Pool line stand-in = opener (CFBD consensus open for CFB, ESPN/DraftKings open for NFL), graded at that number."
    (ROOT / "backtest").mkdir(exist_ok=True)
    (ROOT / f"backtest/2026_w1-{a.through}.json").write_text(json.dumps({"report": rep, "games": rows, "nfl_lines": nfl}, indent=1), newline="\n")
    print(json.dumps({k: rep[k] for k in ("n", "su_accuracy", "brier", "model_weight", "stale_lines")}, indent=1))
