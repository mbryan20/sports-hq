"""How the other players in Michael's three pools pick and bet, from their own history; and what that means
for his best play (expected prize money, or finishing place where there is no prize).

    py -m pp.opponents        rebuild data/opponent_profile.json (anonymous) + the private per-player report

PRIVATE inputs (rivals' names and picks) live only in POOL_OPP_DIR, never in this public repo:
  cfp_allpicks_*.txt            ncaa-pool-two "All Picks" pages, compact format (see parse_cfp)
  yahoo_grouppicks_2026.json    Yahoo group picks, same format as picks/.private/grouppicks_2026.json
  cfp_balances.json             {"read": date, "balances": {player: balance}} from the CFP leaderboard
  cfb_context_2026_w01-12.json  CFBD lines (open/close), scores, AP ranks, team abbreviations
Outputs: data/opponent_profile.json (anonymous field-level numbers only, committed) and
POOL_OPP_DIR/opponent_report.json (named, private).

Fair test: every model here is scored by predicting each past week from earlier weeks only, against the
baseline "everyone takes the market favorite and bets the minimum". A model is used only where it wins."""
import json
import os
import re
from datetime import date
from pathlib import Path

POOL_OPP_DIR = Path(os.environ.get("POOL_OPP_DIR", r"G:\My Drive\Claude Home\System - ignore\pool-opponents"))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/opponent_profile.json"

# Prize tables, read live Nov 26 2026 (sources in docs/picks/method/pool-rules.md).
CFP_PAYOUTS = [1059, 454, 303, 242, 212, 182, 151, 121, 106, 91, 61, 45]   # leaderboard "$" column, pot $3,025


def bto_payouts(pot):
    """BTO 2025 rules doc ("rules are the same" in 2026): regular season 4th = buy-in back, then of the rest
    1st 40%, 2nd 20%, 3rd 10%; playoffs 1st 15%, 2nd 10%, 3rd 5%."""
    rest = pot - 75
    return {"regular": [0.40 * rest, 0.20 * rest, 0.10 * rest, 75.0], "playoff": [0.15 * rest, 0.10 * rest, 0.05 * rest]}


def bto_playoff_ev(payouts, bye):
    """Expected playoff prize for a qualifier: best-of-5 ATS series are near coin flips, so a bye seed (3 wins
    to the title) reaches each of 1st, 2nd and 3rd 1/8 of the time; seeds 5-12 (4 wins) 1/16."""
    return sum(payouts["playoff"]) * (1 / 8 if bye else 1 / 16)


BUCKETS = ((0, 7), (7, 14), (14, 99))


def bucket(spread):
    s = abs(float(spread))
    return next(i for i, (lo, hi) in enumerate(BUCKETS) if lo <= s < hi)


# ---------------------------------------------------------------- CFP points pool

def parse_cfp(text):
    """Compact All Picks dump -> {"players": [...], "games": [{week, fav, line, dog, cov}], "picks": [(g, p, side, amt)]}.
    Format: '#PLAYERS' then one comma line of names; '#GAMES' then 'wk;fav;line;dog;covered(F/D)' lines;
    '#PICKS' then space/newline-separated 'game,<playerIdx><F|D><wager>' tokens."""
    sec, players, games, picks = None, [], [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or (s.startswith("#") and not s.split()[0] in ("#PLAYERS", "#GAMES", "#PICKS")):
            continue
        tag = s.split()[0]
        if tag in ("#PLAYERS", "#GAMES", "#PICKS"):
            sec = tag
            continue
        if sec == "#PLAYERS":
            players += [p for p in s.split(",") if p]
        elif sec == "#GAMES":
            wk, fav, ln, dog, cov = s.split(";")
            games.append({"week": int(wk), "fav": fav, "line": float(ln), "dog": dog, "cov": cov})
        elif sec == "#PICKS":
            for tok in s.split():
                m = re.fullmatch(r"(\d+),(\d+)([FD])(\d+)", tok)
                if m:
                    picks.append((int(m[1]), int(m[2]), m[3], int(m[4])))
    return {"players": players, "games": games, "picks": picks}


def cfp_weekly(parsed):
    """{player: {week: {n, wager, net, dog, big}}}; big = largest single wager. Lines are half points: no pushes."""
    out = {}
    for g, p, side, amt in parsed["picks"]:
        game = parsed["games"][g]
        w = out.setdefault(parsed["players"][p], {}).setdefault(game["week"], {"n": 0, "wager": 0, "net": 0, "dog": 0, "big": 0})
        w["n"] += 1
        w["wager"] += amt
        w["dog"] += side == "D"
        w["big"] = max(w["big"], amt)
        w["net"] += amt if side == game["cov"] else -amt
    return out


REBUY = 10000   # CFP rebuy resets a busted balance to 10,000 (rules page)


def reconstruct_starts(weekly, end_balances, last_week):
    """Each player's balance at the start of each week, worked backward from today's leaderboard
    (end of last_week): start = end - net. A week with no picks cost 50% (start = 2 x end). Weeks that come
    out at or below 0 (a rebuy happened) and everything before them are dropped."""
    starts = {}
    for name, end in end_balances.items():
        wk = weekly.get(name, {})
        if not wk:
            continue
        first = min(wk)
        bal, s = float(end), {}
        for w in range(last_week, first - 1, -1):
            start = bal - wk[w]["net"] if w in wk else bal * 2
            # All-in, lost everything, then rebought to 10,000: working back gives start = 2 x wager (share 0.5).
            # The real start was the wager (share 1.0). Only certain in a player's first week, since everyone
            # starts at 10,000 (later, a real 50% loss looks the same). Checker, Nov 27.
            if (w == first and w in wk and wk[w]["net"] == -wk[w]["wager"] and abs(bal - REBUY) < 1
                    and abs(start - 2 * wk[w]["wager"]) < 1):
                s[w] = float(wk[w]["wager"])
                break
            # A rebuy (bust to 0, reset to 10,000) makes the week before it come out ~10,000 too high, so its
            # wager share falls under the 50% minimum the site enforces: stop there (checker, Nov 26).
            if start <= 0 or (w in wk and wk[w]["wager"] / start < 0.49):
                break
            s[w] = start
            bal = start
        starts[name] = s
    return starts


def _fracs(weekly, starts, name):
    return {w: v["wager"] / starts[name][w] for w, v in weekly.get(name, {}).items()
            if w in starts.get(name, {}) and starts[name][w] > 0}


def risk_label(frac_mean, big_mean):
    """risky: bets nearly everything or a big share on one game; risk-averse: near the 50% minimum and spread out."""
    if frac_mean >= 0.85 or big_mean >= 0.6:
        return "risky"
    if frac_mean <= 0.62 and big_mean <= 0.35:
        return "risk-averse"
    return "balanced"


def cfp_profiles(parsed, end_balances, last_week):
    weekly = cfp_weekly(parsed)
    starts = reconstruct_starts(weekly, end_balances, last_week)
    # the paid line each week: 12th-highest start balance among known players
    by_week = {}
    for n, s in starts.items():
        for w, b in s.items():
            by_week.setdefault(w, []).append(b)
    line12 = {w: sorted(v, reverse=True)[min(11, len(v) - 1)] for w, v in by_week.items()}
    prof = {}
    for name in end_balances:
        fr = _fracs(weekly, starts, name)
        if not fr:
            continue
        wk = weekly[name]
        big = [wk[w]["big"] / starts[name][w] for w in fr]
        dogs_by_b = [[0, 0] for _ in BUCKETS]
        wins = losses = 0
        for g, p, side, amt in parsed["picks"]:
            if parsed["players"][p] != name:
                continue
            game = parsed["games"][g]
            b = dogs_by_b[bucket(game["line"])]
            b[0] += side == "D"
            b[1] += 1
            wins += side == game["cov"]
            losses += side != game["cov"]
        ahead = [fr[w] for w in fr if starts[name][w] >= line12.get(w, 0)]
        behind = [fr[w] for w in fr if starts[name][w] < line12.get(w, 0)]
        late = [fr[w] for w in fr if w >= 9]
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
        fm, bm = mean(list(fr.values())), mean(big)
        prof[name] = {"balance": end_balances[name], "weeks": len(fr), "frac_mean": fm, "fracs": [round(x, 3) for x in fr.values()],
                      "bets_mean": mean([wk[w]["n"] for w in fr]), "big_mean": bm,
                      "dog_rate": [round(a / b, 3) if b else None for a, b in dogs_by_b], "picks_by_bucket": [b for _, b in dogs_by_b],
                      "ats": [wins, losses], "frac_ahead": mean(ahead), "frac_behind": mean(behind), "frac_late": mean(late),
                      "label": risk_label(fm, bm)}
    return prof, weekly, starts


def cfp_fair_test(parsed, weekly, starts, min_hist=2):
    """Predict each player's week-w wager share from their earlier weeks only, vs the baseline 'bets the 50%
    minimum'; and their underdog picks from earlier dog rates (shrunk to the field) vs 'always the favorite'.
    Returns mean absolute error (share) and Brier scores (lower is better)."""
    err_m = err_b = 0.0
    n = 0
    for name, s in starts.items():
        fr = _fracs(weekly, starts, name)
        ws = sorted(fr)
        for i, w in enumerate(ws):
            if i < min_hist:
                continue
            pred = sum(fr[x] for x in ws[:i]) / i
            err_m += abs(pred - fr[w])
            err_b += abs(0.5 - fr[w])
            n += 1
    side_m = side_b = 0.0
    k = 0
    hist = {}
    field = [[1, 2] for _ in BUCKETS]           # weak prior: dogs, picks
    order = sorted(range(len(parsed["picks"])), key=lambda i: parsed["games"][parsed["picks"][i][0]]["week"])
    cur_week, pending = None, []
    for i in order:
        g, p, side, amt = parsed["picks"][i]
        game = parsed["games"][g]
        if game["week"] != cur_week:                  # fold the finished week into history before predicting the next
            for (nm, b, d) in pending:
                h = hist.setdefault(nm, [[0, 0] for _ in BUCKETS])
                h[b][0] += d
                h[b][1] += 1
                field[b][0] += d
                field[b][1] += 1
            pending, cur_week = [], game["week"]
        b = bucket(game["line"])
        name = parsed["players"][p]
        h = hist.get(name, [[0, 0] for _ in BUCKETS])[b]
        prior = field[b][0] / field[b][1]
        pred = (h[0] + 5 * prior) / (h[1] + 5)
        y = 1.0 if side == "D" else 0.0
        side_m += (pred - y) ** 2
        side_b += (0.0 - y) ** 2
        k += 1
        pending.append((name, b, int(y)))
    avg = lambda s, c: round(s / c, 3) if c else None      # too little history: no score rather than a crash
    return {"wager_share_mae": {"model": avg(err_m, n), "baseline_min": avg(err_b, n), "n": n},
            "side_brier": {"model": avg(side_m, k), "baseline_fav": avg(side_b, k), "n": k}}


# ---------------------------------------------------------------- Yahoo group

SKIP = {"HG"}
# Yahoo group-picks abbreviations that CFBD's abbreviation list maps wrongly or not at all (checker, Nov 26)
YAHOO_ABBR = {"UMD": "Maryland", "BSU": "Boise State", "AFA": "Air Force", "IND": "Indiana", "NW": "Northwestern",
              "UW": "Washington", "MIZZ": "Missouri", "TAMU": "Texas A&M", "NCST": "NC State"}
# Yahoo display names (pick-distribution page) -> CFBD school names
YAHOO_NAMES = {"mississippi": "ole miss", "miami (fl)": "miami", "n. carolina": "north carolina", "boston coll.": "boston college",
               "connecticut": "uconn", "san jose st.": "san josé state", "sdsu": "san diego state", "nc state": "nc state"}


def _yname(name):
    from .names import norm
    s = (name or "").strip().lower()
    s = YAHOO_NAMES.get(s, s)
    if s.endswith(" st."):
        s = s[:-4] + " state"
    return norm(s)


def pub_share(week_pub, school, yahoo_name=None):
    """Yahoo-wide pick share for a team, matching Yahoo's display names ("Mississippi St.") to CFBD schools."""
    pw = {_yname(k): v for k, v in week_pub.items()}
    for cand in (school, yahoo_name):
        if cand and _yname(cand) in pw:
            return pw[_yname(cand)]
    return None


def yahoo_games(week_rec):
    return [g.split(",") for g in week_rec["g"].split(";")]


def yahoo_profiles(picks):
    """{member: {"dog_rate": [by bucket], "picks": n}} from the group's own picks (F/D per game)."""
    out = {}
    for v in picks.values():
        gs = yahoo_games(v)
        for name, s in v["p"].items():
            if name in SKIP:
                continue
            o = out.setdefault(name, {"d": [[0, 0] for _ in BUCKETS]})
            for (fav, spread, dog), c in zip(gs, s):
                if c == "-":
                    continue
                b = o["d"][bucket(spread)]
                b[0] += c == "D"
                b[1] += 1
    return {n: {"dog_rate": [round(a / b, 3) if b else None for a, b in o["d"]], "picks": sum(b for _, b in o["d"]),
                "dogs": sum(a for a, _ in o["d"])} for n, o in out.items()}


def yahoo_fair_test(picks):
    """Predict each member's pick on each game of week w from weeks < w (their bucket dog rate, shrunk to the
    group's) vs the baseline 'always the favorite'. Brier score; also the per-game group dog count error."""
    weeks = sorted(picks, key=int)
    hist, grp = {}, [[1, 4] for _ in BUCKETS]
    sm = sb = 0.0
    k = 0
    cnt_m = cnt_b = 0.0
    ng = 0
    for w in weeks:
        v = picks[w]
        gs = yahoo_games(v)
        for gi, (fav, spread, dog) in enumerate(gs):
            b = bucket(spread)
            exp = obs = 0.0
            for name, s in v["p"].items():
                if name in SKIP or gi >= len(s) or s[gi] == "-":
                    continue
                h = hist.get(name, [[0, 0] for _ in BUCKETS])[b]
                pred = (h[0] + 5 * grp[b][0] / grp[b][1]) / (h[1] + 5)
                y = 1.0 if s[gi] == "D" else 0.0
                sm += (pred - y) ** 2
                sb += y
                k += 1
                exp += pred
                obs += y
            cnt_m += abs(exp - obs)
            cnt_b += obs
            ng += 1
        for gi, (fav, spread, dog) in enumerate(gs):
            b = bucket(spread)
            for name, s in v["p"].items():
                if name in SKIP or gi >= len(s) or s[gi] == "-":
                    continue
                h = hist.setdefault(name, [[0, 0] for _ in BUCKETS])
                h[b][0] += s[gi] == "D"
                h[b][1] += 1
                grp[b][0] += s[gi] == "D"
                grp[b][1] += 1
    cm, cb = round(cnt_m / ng, 3), round(cnt_b / ng, 3)
    return {"pick_brier": {"model": round(sm / k, 4), "baseline_fav": round(sb / k, 4), "n": k},
            "group_dog_count_mae": {"model": cm, "baseline_fav": cb, "games": ng,
                                    "verdict": "model wins" if cm < cb else "model loses: not used alone"}}


def yahoo_pub_fair_test(picks, ctx, pub, w_pub=0.5):
    """Weeks with Yahoo-wide pick shares: P(member takes the dog) = w_pub x public share + (1 - w_pub) x their
    earlier bucket rate, vs the member rate alone and vs 'always the favorite'. Brier and group-count error."""
    abbr = {k.upper(): v for k, v in ctx["abbr"].items()}
    abbr.update(YAHOO_ABBR)
    hist, grp = {}, [[1, 4] for _ in BUCKETS]
    acc = {"blend": [0.0, 0], "member": [0.0, 0], "baseline_fav": [0.0, 0]}
    cnt = {"blend": 0.0, "member": 0.0, "baseline_fav": 0.0}
    ng = unmatched = 0
    for w in sorted(picks, key=int):
        v = picks[w]
        gs = yahoo_games(v)
        for gi, (fav, spread, dog) in enumerate(gs):
            b = bucket(spread)
            pd = pub_share(pub[w], abbr.get(dog.upper()), dog) if w in pub else None
            if w in pub and pd is None:
                unmatched += 1
            exp = {k: 0.0 for k in cnt}
            obs = 0.0
            for name, s in v["p"].items():
                if name in SKIP or gi >= len(s) or s[gi] == "-":
                    continue
                h = hist.get(name, [[0, 0] for _ in BUCKETS])[b]
                pm = (h[0] + 5 * grp[b][0] / grp[b][1]) / (h[1] + 5)
                y = 1.0 if s[gi] == "D" else 0.0
                if pd is not None:
                    for key, p in (("blend", w_pub * pd + (1 - w_pub) * pm), ("member", pm), ("baseline_fav", 0.0)):
                        acc[key][0] += (p - y) ** 2
                        acc[key][1] += 1
                        exp[key] += p
                    obs += y
            if pd is not None:
                for key in cnt:
                    cnt[key] += abs(exp[key] - obs)
                ng += 1
        for gi, (fav, spread, dog) in enumerate(gs):
            b = bucket(spread)
            for name, s in v["p"].items():
                if name in SKIP or gi >= len(s) or s[gi] == "-":
                    continue
                h = hist.setdefault(name, [[0, 0] for _ in BUCKETS])
                h[b][0] += s[gi] == "D"
                h[b][1] += 1
                grp[b][0] += s[gi] == "D"
                grp[b][1] += 1
    if not ng:
        return None
    return {"weeks": sorted(pub, key=int), "games": ng, "unmatched_games": unmatched,
            "pick_brier": {k: round(a / n, 4) for k, (a, n) in acc.items()},
            "group_dog_count_mae": {k: round(c / ng, 3) for k, c in cnt.items()}}


def herding(picks, ctx, pub=None, min_share=0.5):
    """Games where at least min_share of active members took the same Yahoo underdog, and which explanations
    the data supports. ctx: cfb context (abbr map, AP ranks, CFBD games with open/close lines); pub: optional
    {week: {dog_team_abbr_or_name: Yahoo-wide share}}. Returns counts for herd games vs other close games."""
    abbr = {k.upper(): v for k, v in ctx["abbr"].items()}
    abbr.update(YAHOO_ABBR)
    by_week = {}
    for g in ctx["games"]:
        by_week.setdefault(g["week"], []).append(g)
    def find(w, a, b):
        ta, tb = abbr.get(a.upper()), abbr.get(b.upper())
        for g in by_week.get(w, []):
            if {g["home"], g["away"]} == {ta, tb}:
                return g, ta, tb
        return None, ta, tb
    rows = []
    for w, v in picks.items():
        w = int(w)
        for gi, (fav, spread, dog) in enumerate(yahoo_games(v)):
            col = [s[gi] for n, s in v["p"].items() if n not in SKIP and gi < len(s) and s[gi] != "-"]
            if not col:
                continue
            share = sum(c == "D" for c in col) / len(col)
            g, tf, td = find(w, fav, dog)
            r = {"week": w, "fav": fav, "dog": dog, "spread": float(spread), "dog_share": round(share, 3), "matched": g is not None}
            if g:
                home_fav = g["home"] == tf
                def fav_side(x):                         # CFBD spread is the home line: <0 = home favored
                    return None if x is None else (x < 0) == home_fav
                r["dog_home"] = g["home"] == td
                r["open_fav_was_dog"] = fav_side(g["open"]) is False
                r["close_fav_was_dog"] = fav_side(g["close"]) is False
                r["moved"] = None if g["open"] is None or g["close"] is None else round(abs(g["close"] - g["open"]), 1)
                rk = ctx["ap"].get(str(w)) or ctx["ap"].get(w) or {}
                rf, rd = rk.get(tf, 99), rk.get(td, 99)
                r["dog_ranked_higher"] = rd < rf
                r["both_ranked"] = rd < 99 and rf < 99
                if g["hs"] is not None and g["as"] is not None:
                    fav_pts, dog_pts = (g["hs"], g["as"]) if home_fav else (g["as"], g["hs"])
                    r["dog_won"] = dog_pts > fav_pts
            if pub and str(w) in pub:
                r["pub_dog"] = pub_share(pub[str(w)], td, dog)
            rows.append(r)
    herd = [r for r in rows if r["dog_share"] >= min_share]
    close = [r for r in rows if r["dog_share"] < min_share and r["spread"] <= 7]
    def rate(rs, k):
        xs = [r[k] for r in rs if r.get(k) is not None]
        return [sum(1 for x in xs if x), len(xs)]
    factors = ["open_fav_was_dog", "close_fav_was_dog", "dog_ranked_higher", "dog_home", "both_ranked", "dog_won"]
    summary = {"herd_games": len(herd), "close_non_herd_games": len(close),
               "herd": {f: rate(herd, f) for f in factors}, "close_non_herd": {f: rate(close, f) for f in factors},
               "herd_spread_mean": round(sum(r["spread"] for r in herd) / len(herd), 2) if herd else None,
               "matched": [sum(r["matched"] for r in rows), len(rows)]}
    pubs = [(r["pub_dog"], r["dog_share"]) for r in rows if r.get("pub_dog") is not None]
    if pubs:
        hi = [s for p, s in pubs if p >= 0.5]
        lo = [s for p, s in pubs if p < 0.5]
        summary["pub_effect"] = {"group_dog_share_when_yahoo_majority_on_dog": round(sum(hi) / len(hi), 3) if hi else None,
                                 "games_hi": len(hi), "group_dog_share_otherwise": round(sum(lo) / len(lo), 3) if lo else None,
                                 "games_lo": len(lo)}
    return summary, herd


# ---------------------------------------------------------------- prize-money sims

def payout_ev(me, opp, payouts):
    """Mean prize for Michael over simulations. me (n,), opp (n, k); ties split the tied places' prizes."""
    import numpy as np
    pay = np.array(list(payouts) + [0.0] * (opp.shape[1] + 1))
    above = (opp > me[:, None]).sum(1)
    tie = (opp == me[:, None]).sum(1)
    out = pay[above].astype(float)
    for i in np.nonzero(tie)[0]:
        a, t = above[i], tie[i]
        out[i] = pay[a:a + t + 1].mean()
    return float(out.mean()), above


def cfp_season(my_bal, week_bets, later_frac, later_bets, field, opp_fracs, weeks_left, rng, n=10000,
               p_later=0.53, opp_bets=None):
    """CFP balances at season end. week_bets: this week's [(wager, cover prob)]; later weeks Michael bets
    later_frac of his balance over later_bets sides at p_later. Each rival re-draws a wager share each week
    from their own history (opp_fracs[i], list) and splits it over opp_bets[i] even bets at 50%."""
    import numpy as np
    me = np.full(n, float(my_bal))
    for amt, p in week_bets:
        me += np.where(rng.random(n) < p, amt, -amt)
    me = np.maximum(me, 0)
    k = len(field)
    opp = np.tile(np.asarray(field, float), (n, 1))
    nb = np.array([max(1, round(b)) for b in (opp_bets or [2] * k)])
    for w in range(weeks_left):
        fr = np.stack([rng.choice(np.asarray(opp_fracs[i] or [0.75]), n) for i in range(k)], 1)
        fr = np.clip(fr, 0.5, 1.0)
        res = np.zeros_like(opp)
        for j in range(nb.max()):
            act = nb > j
            win = rng.random(opp.shape) < 0.5
            res += np.where(act[None, :], np.where(win, 1, -1) * opp * fr / nb[None, :], 0)
        opp = np.maximum(opp + res, 0)
        if w > 0:
            stake = me * later_frac / later_bets
            wins = (rng.random((n, later_bets)) < p_later).sum(1)
            me = np.maximum(me + stake * (2 * wins - later_bets), 0)
    return me, opp


def build(cfp_text=None, cfp_bal=None, cfp_last_week=12, yahoo=None, ctx=None, pub=None):
    """Anonymous field profile + named private report."""
    prof = {"updated": date.today().isoformat(), "note": "Anonymous field-level numbers; names stay in the private Drive folder."}
    report = {"updated": prof["updated"]}
    if cfp_text and cfp_bal:
        parsed = parse_cfp(cfp_text)
        p, weekly, starts = cfp_profiles(parsed, cfp_bal, cfp_last_week)
        ft = cfp_fair_test(parsed, weekly, starts)
        fr = sorted(x for v in p.values() for x in v["fracs"])
        q = lambda a: round(fr[min(len(fr) - 1, int(a * len(fr)))], 3) if fr else None
        labels = [v["label"] for v in p.values()]
        prof["cfp"] = {"players_profiled": len(p), "weeks": sorted({g["week"] for g in parsed["games"]}),
                       "wager_share_quantiles": {"p10": q(0.1), "p50": q(0.5), "p90": q(0.9)},
                       "bets_per_week_mean": round(sum(v["bets_mean"] for v in p.values()) / len(p), 2),
                       "dog_rate_by_spread": [[lo, hi, round(sum(v["picks_by_bucket"][i] * (v["dog_rate"][i] or 0) for v in p.values()) /
                                               max(1, sum(v["picks_by_bucket"][i] for v in p.values())), 3)] for i, (lo, hi) in enumerate(BUCKETS)],
                       "labels": {l: labels.count(l) for l in ("risk-averse", "balanced", "risky")},
                       "fair_test": ft}
        report["cfp"] = p
    if yahoo:
        yp = yahoo_profiles(yahoo)
        prof["yahoo"] = {"members_profiled": len(yp), "fair_test": yahoo_fair_test(yahoo)}
        if ctx:
            summ, herd = herding(yahoo, ctx, pub)
            prof["yahoo"]["herding"] = summ
            if pub:
                prof["yahoo"]["fair_test_with_public_share"] = yahoo_pub_fair_test(yahoo, ctx, pub)
            report["yahoo_herd_games"] = herd
        report["yahoo"] = yp
    return prof, report


def main():
    d = POOL_OPP_DIR
    cfp_files = sorted(d.glob("cfp_allpicks_*.txt"))
    cfp_text = cfp_files[-1].read_text(encoding="utf-8") if cfp_files else None
    bal = json.loads((d / "cfp_balances.json").read_text(encoding="utf-8")) if (d / "cfp_balances.json").exists() else {}
    yahoo = json.loads((d / "yahoo_grouppicks_2026.json").read_text(encoding="utf-8")) if (d / "yahoo_grouppicks_2026.json").exists() else None
    ctxf = sorted(d.glob("cfb_context_*.json"))
    ctx = json.loads(ctxf[-1].read_text(encoding="utf-8")) if ctxf else None
    pubf = d / "yahoo_pub.json"
    pub = json.loads(pubf.read_text(encoding="utf-8")) if pubf.exists() else None
    prof, report = build(cfp_text, bal.get("balances"), bal.get("last_week", 12), yahoo, ctx, pub)
    OUT.write_text(json.dumps(prof, indent=1) + "\n", encoding="utf-8")
    (d / "opponent_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {OUT.name} and the private report ({', '.join(k for k in prof if k not in ('updated', 'note'))})")


if __name__ == "__main__":
    main()
