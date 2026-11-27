"""Pool strategy sims: Yahoo weekly pick'em, BTO wager sizing, CFP wager sizing."""
import itertools
import numpy as np

from .opponents import CFP_PAYOUTS, bto_payouts, bto_playoff_ev, payout_ev  # noqa: F401 (CFP_PAYOUTS re-exported)

N = 10_000

# Last regular-season week of each pool (docs/picks/method/pool-rules.md, read live Nov 26 2026): the CFP pool
# ends after week 14 (commissioner email Nov 24); BTO's regular season is 16 weeks (2025 rules doc, "rules are
# the same" in 2026). Before Nov 27 the sizing sims assumed 6 weeks left all season.
SEASON_END = {"cfp": 14, "bto": 16}
# Keep the posted size unless another is this much better in expected prize (my judgment, Nov 26: the rival
# bet-size model's error is about this size, so smaller gaps are noise and would flip cards on thin edges).
KEEP_MARGIN = 0.07


def weeks_left_for(pool, week):
    """Weeks still to play in the pool, this week included."""
    return max(1, SEASON_END[pool] - int(week) + 1)


def keep_or_best(table, best, keep, key, margin=KEEP_MARGIN):
    """The posted row (matched by key(row) == keep) if its expected prize is within margin of best
    (margin=float("inf") always keeps it: the pool has locked)."""
    if keep is None or "ev" not in best:
        return best
    k = next((r for r in table if key(r) == keep), None)
    return k if k is not None and k["ev"] * (1 + margin) >= best["ev"] else best


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


def cfp_opp_week_from(profile):
    """Rival week drawn from the pool's own history (data/opponent_profile.json "cfp", anonymous): wager share
    from its quantiles, number of sides around its mean. Falls back to cfp_opp_week without a profile."""
    if not profile or "wager_share_quantiles" not in profile:
        return cfp_opp_week
    q = profile["wager_share_quantiles"]
    xs, ys = [0.0, 0.1, 0.5, 0.9, 1.0], [0.5, q["p10"], q["p50"], q["p90"], 1.0]
    lam = max(0.0, float(profile.get("bets_per_week_mean", 3)) - 1)

    def week(opp, rng):
        f = np.interp(rng.random(opp.shape), xs, ys)
        k = np.clip(rng.poisson(lam, opp.shape) + 1, 1, 8)
        out = opp.copy()
        for nb in range(1, 9):
            m = k == nb
            if m.any():
                out[m] = _bets(opp[m], f[m], nb, 0.5, rng)
        return np.maximum(out, 0)
    return week


def cfp_plan(my_bal, field, edges, weeks_left=6, rebuy_ok=True, future_p=0.53, payouts=None, opp_profile=None):
    """edges: sorted list of cover probs for this week's best sides. Evaluates (#bets, fraction) for this
    week. Returns best plan and table. Without payouts later weeks repeat this week's size and the best row
    is the highest P(1st). With payouts (prize per finishing place) each row also gets "ev" (expected prize,
    ties split), "p_paid" and "later" (the best of: same size, all-in on 1 side, all-in on 2 sides in later
    weeks), and the best row is the highest expected prize. opp_profile: see cfp_opp_week_from."""
    opps = [b for b in field if b > 0]
    opp_week = cfp_opp_week_from(opp_profile)
    table = []
    for nb in (1, 2, 3, 4):
        if nb > len(edges):
            break
        p_now = float(np.mean(edges[:nb]))
        for frac in (0.5, 0.6, 0.75, 0.9, 1.0):
            laters = [(nb, frac)]
            if payouts and weeks_left > 1:
                laters += [x for x in ((1, 1.0), (2, 1.0)) if x != (nb, frac)]
            for rb in ((False, True) if rebuy_ok else (False,)):
                best_row = None
                for lnb, lfrac in laters:
                    rng = np.random.default_rng(3)
                    def my_week(w, me, leader, rng, nb=nb, frac=frac, p_now=p_now, lnb=lnb, lfrac=lfrac):
                        if w == 0:
                            return np.maximum(_bets(me, frac, nb, p_now, rng), 0)
                        return np.maximum(_bets(me, lfrac, lnb, future_p, rng), 0)
                    me, opp = _season(my_bal, opps, my_week, opp_week, weeks_left, rng, rebuy=10000 if rb else None)
                    p1 = float((me > opp.max(1)).mean())
                    row = {"bets": nb, "frac": frac, "rebuy": rb, "p_first": p1, "p_top3": float(((opp > me[:, None]).sum(1) < 3).mean())}
                    if payouts:
                        ev, above = payout_ev(me, opp, payouts)
                        row.update(ev=ev, p_paid=float((above < len(payouts)).mean()),
                                   later=f"{lfrac * 100:.0f}% on {lnb} side{'s' if lnb > 1 else ''}")
                    if best_row is None or row.get("ev", 0) > best_row.get("ev", 0):
                        best_row = row
                table.append(best_row)
    best = max(table, key=lambda r: (r.get("ev", 0), r["p_first"], r["p_top3"]))
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


def bto_plan(my_bal, field, cover_probs, mode, weeks_left=6, pot=None, keep=None):
    """cover_probs: per chosen bet after line points (Big Game included by caller).
    Chooses total fraction and split to maximize champion equity (top-4 bye vs 5-12 seeds). With pot (total
    buy-ins) it maximizes expected prize instead: regular-season places (bto_payouts) plus the playoff
    share, trying both a cautious and an all-in policy for later weeks; keep=(frac, split) of the posted
    card holds that size unless another is KEEP_MARGIN better."""
    n_b = len(cover_probs)
    min_frac = {"normal": 0.25, "three": 0.5, "one": 1.0}[mode]
    fracs = [f for f in (0.25, 0.35, 0.5, 0.65, 0.8, 1.0) if f >= min_frac]
    order = np.argsort(-np.array(cover_probs))
    splits = {"equal": [1] * n_b, "lean": [2 if i == order[0] else 1 for i in range(n_b)]}
    pay = bto_payouts(pot) if pot else None
    later_policies = ("cautious", "all-in") if pay and weeks_left > 1 else ("cautious",)
    table = []
    for frac in fracs:
        for sname, wts in splits.items():
            stakes = bto_split(my_bal * frac, n_b, wts)
            best_row = None
            for later in later_policies:
                rng = np.random.default_rng(9)
                def my_week(w, me, leader, rng, stakes=stakes, later=later):
                    if w == 0:
                        res = me.copy()
                        for s, p in zip(stakes, cover_probs):
                            res += np.where(rng.random(me.shape) < p, s, -s)
                        return np.maximum(res, 0)
                    if later == "all-in":
                        return np.maximum(_bets(me, 1.0, 3, 0.53, rng), 0)
                    st = np.where((me <= 500) | (me <= 0.25 * leader), 1.0, np.where((me <= 1000) | (me <= 0.5 * leader), 0.5, 0.3))
                    return np.maximum(_bets(me, st, 3, 0.53, rng), 0)
                me, opp = _season(my_bal, field, my_week, bto_opp_week, weeks_left, rng)
                rank = (opp > me[:, None]).sum(1)
                top4, top12 = float((rank < 4).mean()), float((rank < 12).mean())
                row = {"frac": frac, "split": sname, "stakes": stakes, "p_top4": top4, "p_top12": top12,
                       "champ": top4 / 8 + (top12 - top4) / 16}
                if pay:
                    reg, _ = payout_ev(me, opp, pay["regular"])
                    po = np.where(rank < 4, bto_playoff_ev(pay, True), np.where(rank < 12, bto_playoff_ev(pay, False), 0.0))
                    row.update(ev=reg + float(po.mean()), later=later)
                if best_row is None or row.get("ev", 0) > best_row.get("ev", 0):
                    best_row = row
            table.append(best_row)
    best = max(table, key=lambda r: (r.get("ev", 0), r["champ"]))
    return keep_or_best(table, best, keep, lambda r: (r["frac"], r["split"])), table
