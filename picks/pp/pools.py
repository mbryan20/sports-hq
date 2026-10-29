"""Pool strategy sims: Yahoo weekly pick'em, BTO wager sizing, CFP wager sizing."""
import itertools
import numpy as np

N = 10_000


# ---------- Yahoo: 14-person straight-up pick'em, maximize P(win the week) ----------

def yahoo_win_prob(p_home, my_home, pub_home, n_opp=13, rng=None, n=N):
    """p_home: true home-win probs (G,); my_home: bool picks (G,); pub_home: opponents' P(pick home)."""
    rng = rng or np.random.default_rng(1)
    G = len(p_home)
    out = rng.random((n, G)) < p_home
    mine = (out == my_home).sum(1)
    opp_picks = rng.random((n, n_opp, G)) < pub_home
    opp = (opp_picks == out[:, None, :]).sum(2)
    best = opp.max(1)
    ties = (opp == best[:, None]).sum(1)
    win = np.where(mine > best, 1.0, np.where(mine == best, 1.0 / (ties + 1), 0.0))
    return float(win.mean())


def yahoo_optimize(p_true, fav_home, eligible, pub_home, n_opp=13):
    """Start from market favorites; add eligible underdog flips (ordered by leverage) while they
    raise P(win week). Returns picks (bool home), chosen flips, curve of P(win) by #underdogs."""
    rng = np.random.default_rng(11)
    base = fav_home.copy()
    order = sorted(eligible, key=lambda g: -((p_true[g] if not fav_home[g] else 1 - p_true[g]) * (pub_home[g] if fav_home[g] else 1 - pub_home[g])))
    curve = [yahoo_win_prob(p_true, base, pub_home, n_opp, np.random.default_rng(5))]
    picks, chosen = base.copy(), []
    for g in order:
        trial = picks.copy(); trial[g] = not trial[g]
        pw = yahoo_win_prob(p_true, trial, pub_home, n_opp, np.random.default_rng(5))
        curve.append(pw)
        if pw > max(curve[:-1]):
            picks, chosen = trial, chosen + [g]
    return picks, chosen, curve


def extremes(sims):
    """sims: list of (team_home, team_away, h_pts, a_pts). Most- and fewest-points team frequencies."""
    teams, cols = [], []
    for th, ta, h, a in sims:
        teams += [th, ta]; cols += [h, a]
    M = np.stack(cols, 1)
    most = np.bincount(M.argmax(1), minlength=len(teams)) / len(M)
    fewest = np.bincount(M.argmin(1), minlength=len(teams)) / len(M)
    om, of = np.argsort(-most), np.argsort(-fewest)
    return ([(teams[i], float(most[i])) for i in om[:3]], [(teams[i], float(fewest[i])) for i in of[:3]])


# ---------- Shared: season simulation against a field ----------

def _season(my_bal, opp_bal, my_week_fn, opp_week_fn, weeks_left, rng, n=N, rebuy=None):
    """Simulate balances to season end. Returns my final (n,) and opps final (n, k)."""
    me = np.full(n, float(my_bal))
    opp = np.tile(np.asarray(opp_bal, float), (n, 1))
    for w in range(weeks_left):
        leader = np.maximum(opp.max(1), me)
        me = my_week_fn(w, me, leader, rng)
        if rebuy is not None and w == 0:
            me = np.where(me <= 0, rebuy, me)
        opp = opp_week_fn(opp, rng)
    return me, opp


def _bets(bal, frac, n_bets, p, rng):
    """Even-money bets: total frac*bal split equally over n_bets, each won w.p. p."""
    stake = bal * frac / n_bets
    wins = (rng.random(bal.shape + (n_bets,)) < p).sum(-1)
    return bal + stake * (2 * wins - n_bets)


# ---------- CFP: ATS, even money, wager 50-100% of balance, maximize P(1st) ----------

def cfp_opp_week(opp, rng):
    f = rng.uniform(0.5, 1.0, opp.shape)
    k = rng.integers(1, 6, opp.shape)
    out = opp.copy()
    for nb in range(1, 6):
        m = k == nb
        if m.any():
            out[m] = _bets(opp[m], f[m], nb, 0.5, rng)
    return np.maximum(out, 0)


def cfp_plan(my_bal, field, edges, weeks_left=6, rebuy_ok=True, future_p=0.53):
    """edges: sorted list of cover probs for this week's best sides. Evaluates (#bets, fraction)
    with the same policy in future weeks. Returns best plan and table."""
    opps = [b for b in field if b > 0]
    table = []
    for nb in (1, 2, 3, 4):
        if nb > len(edges):
            break
        p_now = float(np.mean(edges[:nb]))
        for frac in (0.5, 0.6, 0.75, 0.9, 1.0):
            for rb in ((False, True) if rebuy_ok else (False,)):
                rng = np.random.default_rng(3)
                def my_week(w, me, leader, rng, nb=nb, frac=frac, p_now=p_now):
                    return np.maximum(_bets(me, frac, nb, p_now if w == 0 else future_p, rng), 0)
                me, opp = _season(my_bal, opps, my_week, cfp_opp_week, weeks_left, rng, rebuy=10000 if rb else None)
                p1 = float((me > opp.max(1)).mean())
                table.append({"bets": nb, "frac": frac, "rebuy": rb, "p_first": p1, "p_top3": float(((opp > me[:, None]).sum(1) < 3).mean())})
    best = max(table, key=lambda r: (r["p_first"], r["p_top3"]))
    return best, table


# ---------- BTO: ATS fake money, status rules, top-12 playoff, 4 line points ----------

def bto_status(bal, leader):
    if bal <= 0:
        return "out"
    if bal <= 500 or bal <= 0.25 * leader:
        return "one"
    if bal <= 1000 or bal <= 0.5 * leader:
        return "three"
    return "normal"


def bto_opp_week(opp, rng):
    leader = opp.max(1, keepdims=True)
    out = opp.copy()
    one = (opp <= 500) | (opp <= 0.25 * leader)
    three = ~one & ((opp <= 1000) | (opp <= 0.5 * leader))
    norm = ~one & ~three & (opp > 0)
    if norm.any():
        out[norm] = _bets(opp[norm], rng.uniform(0.25, 0.6, norm.sum()), 5, 0.52, rng)
    if three.any():
        out[three] = _bets(opp[three], rng.uniform(0.5, 0.8, three.sum()), 3, 0.52, rng)
    m = one & (opp > 0)
    if m.any():
        out[m] = _bets(opp[m], 1.0, 1, 0.52, rng)
    return np.maximum(out, 0)


def allocate_line_points(margins, lines, total=4.0, step=0.5):
    """Greedy: give each half point to the bet whose cover prob rises most (key numbers win)."""
    lp = [0.0] * len(lines)
    def pc(i, extra):
        x = margins[i] + lines[i] + extra
        return float((x > 0).mean() + 0.5 * (x == 0).mean())
    for _ in range(int(total / step)):
        gains = [pc(i, lp[i] + step) - pc(i, lp[i]) for i in range(len(lines))]
        j = int(np.argmax(gains)); lp[j] += step
    return lp, [pc(i, lp[i]) for i in range(len(lines))]


def bto_split(total, n, weights):
    """$10 multiples, max <= 2x min."""
    w = np.array(weights, float); w = w / w.sum()
    s = np.maximum(np.round(total * w / 10) * 10, 10)
    lo = s.min()
    s = np.minimum(s, 2 * lo)
    while s.sum() > total + 1e-9:  # rounding up can overshoot the balance; trim the largest bet
        s[int(np.argmax(s))] -= 10
    return [int(x) for x in s]


def bto_plan(my_bal, field, cover_probs, mode, weeks_left=6):
    """cover_probs: per chosen bet after line points (Big Game included by caller).
    Chooses total fraction and split to maximize champion equity (top-4 bye vs 5-12 seeds)."""
    n_b = len(cover_probs)
    min_frac = {"normal": 0.25, "three": 0.5, "one": 1.0}[mode]
    fracs = [f for f in (0.25, 0.35, 0.5, 0.65, 0.8, 1.0) if f >= min_frac]
    order = np.argsort(-np.array(cover_probs))
    splits = {"equal": [1] * n_b, "lean": [2 if i == order[0] else 1 for i in range(n_b)]}
    table = []
    for frac in fracs:
        for sname, wts in splits.items():
            stakes = bto_split(my_bal * frac, n_b, wts)
            rng = np.random.default_rng(9)
            def my_week(w, me, leader, rng, stakes=stakes):
                if w == 0:
                    res = me.copy()
                    for s, p in zip(stakes, cover_probs):
                        res += np.where(rng.random(me.shape) < p, s, -s)
                    return np.maximum(res, 0)
                st = np.where((me <= 500) | (me <= 0.25 * leader), 1.0, np.where((me <= 1000) | (me <= 0.5 * leader), 0.5, 0.3))
                return np.maximum(_bets(me, st, 3, 0.53, rng), 0)
            me, opp = _season(my_bal, field, my_week, bto_opp_week, weeks_left, rng)
            rank = (opp > me[:, None]).sum(1)
            top4, top12 = float((rank < 4).mean()), float((rank < 12).mean())
            table.append({"frac": frac, "split": sname, "stakes": stakes, "p_top4": top4, "p_top12": top12,
                          "champ": top4 / 8 + (top12 - top4) / 16})
    return max(table, key=lambda r: r["champ"]), table
