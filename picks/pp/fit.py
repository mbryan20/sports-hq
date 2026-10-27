"""One-time fits on the 2025 season (re-run each preseason): prior scale and points map."""
import json
from pathlib import Path
import numpy as np
from . import model as M

ROOT = Path(__file__).resolve().parent.parent


def prior_scale():
    rows = M.offense_rows(2025)
    teams = sorted({r[2] for r in rows} | {r[3] for r in rows})
    zero = {t: {k: (0, 0) for k, _ in M.STATS} for t in teams}
    sp = M._sp(2025)
    fbs = [t for t in teams if t in sp]
    so = np.array([sp[t]["offense"]["rating"] for t in fbs]); so -= so.mean()
    sd = np.array([sp[t]["defense"]["rating"] for t in fbs]); sd -= sd.mean()
    out = {}
    for key, si in M.STATS:
        mu, h, tab = M._ridge(rows, teams, si, zero, 0.5)
        O = np.array([tab[t][0] for t in fbs]); D = np.array([tab[t][1] for t in fbs])
        fcs = [t for t in teams if t not in sp]
        out[key] = {
            "o": float(np.dot(so, O - O.mean()) / np.dot(so, so)),
            "d": float(np.dot(sd, D - D.mean()) / np.dot(sd, sd)),
            "fcs_o": float(np.mean([tab[t][0] for t in fcs]) - O.mean()),
            "fcs_d": float(np.mean([tab[t][1] for t in fcs]) - D.mean()),
        }
    (ROOT / M.PRIOR_SCALE_FILE).write_text(json.dumps(out, indent=1))
    return out


def points_fit(year=2025, weeks=range(2, 15)):
    X, y, pairs = [], [], {}
    for w in weeks:
        R = M.ratings(year, w)
        for r in M.offense_rows(year):
            if r[1] != w:
                continue
            X.append([1, *M.features(R, r[2], r[3], r[4]), r[4]]); y.append(r[7])
            pairs.setdefault(r[0], []).append(len(y) - 1)
    X, y = np.array(X), np.array(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    pr = [(res[a], res[b]) for a, b in (v for v in pairs.values() if len(v) == 2)]
    rho = float(np.corrcoef(np.array(pr).T)[0, 1])
    out = {"a": beta[0], **{"b_" + k: beta[i + 1] for i, (k, _) in enumerate(M.STATS)}, "b_loc": beta[-1],
           "sd": float(res.std()), "rho": rho, "n": len(y)}
    out = {k: float(v) if not isinstance(v, int) else v for k, v in out.items()}
    (ROOT / M.POINTS_FILE).write_text(json.dumps(out, indent=1))
    return out


def score_freq():
    """Empirical team-score frequencies (0..90) for snapping sims to real football scores."""
    c = np.ones(91)  # Laplace smoothing
    for yr in (2025, 2026):
        for g in M.games(yr):
            for k in ("homePoints", "awayPoints"):
                p = g.get(k)
                if p is not None and 0 <= p <= 90:
                    c[p] += 1
    (ROOT / "cache/score_freq.json").write_text(json.dumps((c / c.sum()).tolist()))


if __name__ == "__main__":
    print(prior_scale())
    M.ratings.cache_clear()
    print(points_fit())
    score_freq()
