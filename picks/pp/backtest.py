"""Walk-forward backtest of the stats-only model: calibration, accuracy, ATS, the market-vs-model
weight used by the ATS cards (MODEL_W), and whether stale lines (open vs close) cover.

Usage: py -m pp.backtest [--through N]   (writes backtest/2026_w1-N.json; N = last graded week)
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", type=int, default=8, help="last graded CFBD week")
    a = ap.parse_args()
    rows = run(weeks=range(1, a.through + 1))
    rep = report(rows)
    rep["model_weight"] = weight_study(rows)
    nfl = nfl_open_close(weeks=range(1, a.through))  # CFBD week N = NFL week N-1
    rep["stale_lines"] = stale_study(rows + nfl)
    rep["stale_lines"]["note"] = "Pool line stand-in = opener (CFBD consensus open for CFB, ESPN/DraftKings open for NFL), graded at that number."
    (ROOT / "backtest").mkdir(exist_ok=True)
    (ROOT / f"backtest/2026_w1-{a.through}.json").write_text(json.dumps({"report": rep, "games": rows, "nfl_lines": nfl}, indent=1), newline="\n")
    print(json.dumps({k: rep[k] for k in ("n", "su_accuracy", "brier", "model_weight", "stale_lines")}, indent=1))
