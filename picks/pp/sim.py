"""Monte Carlo game sims: 10,000 draws of correlated team scores, snapped to real football scores."""
import json
from pathlib import Path
import numpy as np
from .model import points_model

ROOT = Path(__file__).resolve().parent.parent
N_SIMS = 10_000
_freq = None


def _snap_cdf():
    """For each rounded raw score -20..110, a CDF over real scores 0..90 (frequency x closeness)."""
    global _freq
    if _freq is None:
        f = np.array(json.loads((ROOT / "cache/score_freq.json").read_text()))
        s = np.arange(91)
        raw = np.arange(-20, 111)[:, None]
        w = f[None, :] * np.exp(-((s[None, :] - raw) ** 2) / (2 * 3.0 ** 2))
        _freq = np.cumsum(w / w.sum(1, keepdims=True), 1)
    return _freq


def sim_game(mu_home, mu_away, rng, n=N_SIMS):
    pm = points_model()
    sd, rho = pm["sd"], pm["rho"]
    cov = [[sd * sd, rho * sd * sd], [rho * sd * sd, sd * sd]]
    raw = rng.multivariate_normal([mu_home, mu_away], cov, size=n)
    cdf = _snap_cdf()
    ri = np.clip(np.rint(raw).astype(int), -20, 110) + 20
    u = rng.random(raw.shape)
    pts = np.empty_like(ri)
    for j in range(2):
        pts[:, j] = (u[:, j][:, None] > cdf[ri[:, j]]).sum(1)
    h, a = pts[:, 0], pts[:, 1]
    tie = h == a  # overtime: coin flip weighted slightly to the better team, +3/+7
    ot = rng.random(n) < (0.5 + np.clip((mu_home - mu_away) / 60, -0.2, 0.2))
    h = np.where(tie & ot, h + np.where(rng.random(n) < 0.5, 3, 7), h)
    a = np.where(tie & ~ot, a + np.where(rng.random(n) < 0.5, 3, 7), a)
    return h, a


def summarize(h, a):
    m = h - a
    vals, counts = np.unique(np.stack([h, a], 1), axis=0, return_counts=True)
    order = np.argsort(-counts)
    return {
        "p_home": float((m > 0).mean()),
        "mean_home": float(h.mean()), "mean_away": float(a.mean()),
        "median_margin": float(np.median(m)),
        "top_scores": [(int(vals[i][0]), int(vals[i][1]), float(counts[i] / len(h))) for i in order[:5]],
    }


def exact_score_pick(h, a):
    """Exact-score tiebreaker: the realistic score pair nearest the sims' center of mass,
    weighted by how often each pair occurs. Returns best and an alternate."""
    vals, counts = np.unique(np.stack([h, a], 1), axis=0, return_counts=True)
    mh, ma = np.median(h), np.median(a)
    winner_home = (h > a).mean() >= 0.5
    ok = (vals[:, 0] > vals[:, 1]) == winner_home
    d = np.hypot(vals[:, 0] - mh, vals[:, 1] - ma)
    score = np.where(ok, counts / (1 + d), -1)
    o = np.argsort(-score)
    return tuple(map(int, vals[o[0]])), tuple(map(int, vals[o[1]]))


def p_cover(margin, line):
    """P(side covers) where margin is that side's margin and line is its spread (e.g. -3.5). Push = half."""
    x = margin + line
    return float((x > 0).mean() + 0.5 * (x == 0).mean())
