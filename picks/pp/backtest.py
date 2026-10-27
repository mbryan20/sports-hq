"""Walk-forward backtest of the stats-only model on 2026 weeks 1-8: calibration, accuracy, ATS."""
import json
from pathlib import Path
import numpy as np
from . import model as M
from .market import lines
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


if __name__ == "__main__":
    rows = run()
    rep = report(rows)
    (ROOT / "backtest").mkdir(exist_ok=True)
    (ROOT / "backtest/2026_w1-8.json").write_text(json.dumps({"report": rep, "games": rows}, indent=1))
    print(json.dumps(rep, indent=1))
