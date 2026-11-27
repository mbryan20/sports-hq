"""Yahoo pick'em: what taking the other side of a game is worth for winning Michael's GROUP this season.

Picking an underdog only gains ground when it wins and the people ahead of you didn't take it. So the value
of a flip depends on how likely the dog is, how many members are on each side, and where Michael stands.
This simulates the rest of the season (common random numbers, so the base and each flip see the same games):
- This week's open games: outcome from our blended win chance (stats + betting odds). Each other member picks
  the dog with a chance built from this week's Yahoo-wide pick split and the group's own history by spread
  (data/pool_profile.json), scaled by that member's own lean toward dogs.
- Later weeks: games drawn from the season's spread mix; everyone, Michael included, picks by habit.
- Win = most points at the end (a tie for first counts as a share).
Value = chance to finish 1st with the flip minus without it, in percentage points."""
import json
from math import erf, sqrt

import numpy as np

from .cards import ROOT

PROFILE = ROOT / "data/pool_profile.json"
SPREAD_SD = 14.5          # college margin spread around the line (same as the ATS cards)
WEEKS_LEFT = 1            # weeks AFTER the current one: season ends Dec 5 (week 14; Yahoo group page, read Nov 26).
                          # Was 5 (stale since late October). The group drops each member's worst week (Settings:
                          # "Drop 1 score"), which this sim ignores; pp.opponents' Yahoo notes model it.
GAMES_PER_WEEK = 25
N = 20000


def load_profile():
    return json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else None


def bucket_rate(prof, spread):
    return next(r for lo, hi, r in prof["dog_rate_by_spread"] if lo <= spread < hi)


def p_fav_from_spread(s):
    return 0.5 * (1 + erf(s / SPREAD_SD / sqrt(2)))


def season_values(games, prof, weeks_left=WEEKS_LEFT, n=N, seed=7):
    """games: [{"p_fav", "spread" (abs), "pub_dog" (0-1, Yahoo-wide share on the dog), "my_dog" (bool)}] for
    this week's open games. Returns (P(1st) with the card's picks, [value of flipping each game, pts],
    value of flipping every game with a positive value together, pts)."""
    rng = np.random.default_rng(seed)
    lean = np.array([o["lean"] for o in prof["others"]])
    opp = np.tile(np.array([o["points"] for o in prof["others"]], float), (n, 1))
    me = np.full(n, float(prof["me"]["points"]))
    flip_delta = np.zeros((n, len(games)))
    if games:
        pf = np.array([g["p_fav"] for g in games])
        q = np.clip(np.array([0.5 * g["pub_dog"] + 0.5 * bucket_rate(prof, g["spread"]) for g in games])[:, None]
                    * lean[None, :], 0, 0.95)                               # (games, members)
        fav_won = rng.random((n, len(games))) < pf
        opp_dog = rng.random((n, len(games), len(lean))) < q[None]
        opp += (opp_dog != fav_won[:, :, None]).sum(1)
        my_dog = np.array([bool(g["my_dog"]) for g in games])
        right = my_dog[None, :] != fav_won                                   # my pick was correct
        me += right.sum(1)
        flip_delta = np.where(right, -1.0, 1.0)                              # flipping that game's pick
    spreads = np.array(prof["spreads"])
    my_lean = prof["me"]["lean"]
    for _ in range(weeks_left):
        s = rng.choice(spreads, GAMES_PER_WEEK)
        pf = np.array([p_fav_from_spread(x) for x in s])
        rate = np.array([bucket_rate(prof, x) for x in s])
        fav_won = rng.random((n, GAMES_PER_WEEK)) < pf
        opp_dog = rng.random((n, GAMES_PER_WEEK, len(lean))) < np.clip(rate[:, None] * lean[None, :], 0, 0.95)[None]
        opp += (opp_dog != fav_won[:, :, None]).sum(1)
        my_dog = rng.random((n, GAMES_PER_WEEK)) < np.clip(rate * my_lean, 0, 0.95)[None]
        me += (my_dog != fav_won).sum(1)

    def p_first(mine):
        best = opp.max(1)
        ties = (opp == mine[:, None]).sum(1)
        return float(np.where(mine > best, 1.0, np.where(mine == best, 1.0 / (1 + ties), 0.0)).mean())

    base = p_first(me)
    vals = [round((p_first(me + flip_delta[:, i]) - base) * 100, 2) for i in range(len(games))]
    pos = [i for i, v in enumerate(vals) if v > 0]
    combo = round((p_first(me + flip_delta[:, pos].sum(1)) - base) * 100, 2) if pos else 0.0
    return base, vals, combo


# ---------------------------------------------------------------- finishing place (Nov 27)
# The group has no prize (docs/picks/method/pool-rules.md), so what matters is Michael's finishing place, not P(1st)
# (about 0% when 9 back with a week and a half left). This version also models two facts season_values ignores:
# - Yahoo's pick % is ALL Yahoo players (pickdistribution page and the group page's side panel, checked live Nov 27),
#   never the group's split; the group's own picks show only after each game locks. It is still the best predictor
#   of the group: walk-forward on weeks 10-12 (747 picks), P(member takes the dog) = sigmoid(logit(Yahoo %) +
#   0.5 x ln(member lean)) scored Brier 0.078 vs 0.082 for the old sim formula (0.5 x Yahoo % + 0.5 x bucket rate x
#   lean) and 0.079 for 0.5 x Yahoo % + 0.5 x member bucket rate; it missed the group's dog count by 0.85 vs 0.94-0.95
#   per game ("always the favorite": 0.131 / 1.31). Independent checker re-run, Nov 27.
# - "Drop 1 score": each member's worst week doesn't count (Settings page). Needs "dropped" in the profile.
PUB_LEAN_W = 0.5
FUTURE_GAMES = 12         # week 14 is conference championship weekend; Yahoo posts it Mon Nov 30. Not confirmed: 12.
                          # It matters: with ~12 games week 14 is most members' dropped week; a 20-25 game week
                          # makes it count (checker, Nov 27: UCF's +3.1 flip turns about -0.6 at 25 games). That
                          # weekend has only ~10-11 FBS title games (not confirmed what Yahoo includes); set the
                          # real count here once Yahoo posts the slate.


def _logit(p):
    p = np.clip(p, 0.005, 0.995)
    return np.log(p / (1 - p))


def member_dog_probs(pub_dog, leans):
    """(games, members) chance each member takes the underdog: Yahoo-wide share shifted by the member's lean."""
    z = _logit(np.asarray(pub_dog, float))[:, None] + PUB_LEAN_W * np.log(np.clip(np.asarray(leans, float), 0.2, 5))[None, :]
    return 1 / (1 + np.exp(-z))


def season_place(games, prof, weeks_left=WEEKS_LEFT, future_games=FUTURE_GAMES, n=N, seed=7):
    """Like season_values, scored by finishing place. Returns {"place": expected place, "hold": P(finish at the
    current rank or better), "first": P(1st), "rank": current rank, "flips": [same three for flipping each game],
    "drop_rule": bool}. Ties share places."""
    rng = np.random.default_rng(seed)
    others = prof["others"]
    lean = np.array([o["lean"] for o in others])
    pts_o = np.array([o["points"] for o in others], float)
    pts_me = float(prof["me"]["points"])
    drops = [o.get("dropped") for o in others] + [prof["me"].get("dropped")]
    drop_rule = all(d is not None for d in drops)
    weeks_o = []            # per week: (n, members) scores
    weeks_me = []
    flip_delta = np.zeros((n, len(games)))
    if games:
        pf = np.array([g["p_fav"] for g in games])
        q = member_dog_probs([g["pub_dog"] for g in games], lean)                      # (games, members)
        fav_won = rng.random((n, len(games))) < pf
        opp_dog = rng.random((n, len(games), len(lean))) < q[None]
        weeks_o.append((opp_dog != fav_won[:, :, None]).sum(1).astype(float))
        my_dog = np.array([bool(g["my_dog"]) for g in games])
        right = my_dog[None, :] != fav_won
        weeks_me.append(right.sum(1).astype(float))
        flip_delta = np.where(right, -1.0, 1.0)
    spreads = np.array(prof["spreads"])
    for _ in range(weeks_left):
        s = rng.choice(spreads, future_games)
        pf = np.array([p_fav_from_spread(x) for x in s])
        rate = np.array([bucket_rate(prof, x) for x in s])
        fav_won = rng.random((n, future_games)) < pf
        opp_dog = rng.random((n, future_games, len(lean))) < np.clip(rate[:, None] * lean[None, :], 0, 0.95)[None]
        weeks_o.append((opp_dog != fav_won[:, :, None]).sum(1).astype(float))
        my_dog = rng.random((n, future_games)) < np.clip(rate * prof["me"]["lean"], 0, 0.95)[None]
        weeks_me.append((my_dog != fav_won).sum(1).astype(float))
    if drop_rule:
        d_o = np.array([o["dropped"] for o in others], float)
        worst_o = np.minimum.reduce([np.broadcast_to(d_o, (n, len(lean)))] + weeks_o) if weeks_o else d_o
        opp = pts_o + d_o + sum(weeks_o) - worst_o
    else:
        opp = pts_o + (sum(weeks_o) if weeks_o else 0)
    opp = np.broadcast_to(np.asarray(opp, float), (n, len(lean)))
    rank = 1 + int((pts_o > pts_me).sum())

    def score(extra):
        wk = list(weeks_me)
        if wk:
            wk[0] = wk[0] + extra
        if drop_rule:
            d = float(prof["me"]["dropped"])
            worst = np.minimum.reduce([np.full(n, d)] + wk) if wk else d
            me = pts_me + d + sum(wk) - worst
        else:
            me = pts_me + (sum(wk) if wk else 0)
        me = np.broadcast_to(np.asarray(me, float), (n,))
        above = (opp > me[:, None]).sum(1)
        ties = (opp == me[:, None]).sum(1)
        place = 1 + above + ties / 2.0
        hold = np.clip((rank - above) / (ties + 1.0), 0, 1)
        first = np.where(above == 0, 1.0 / (ties + 1.0), 0.0)
        return {"place": float(place.mean()), "hold": float(hold.mean()), "first": float(first.mean())}

    out = score(0.0)
    out.update(rank=rank, drop_rule=drop_rule, flips=[score(flip_delta[:, i]) for i in range(len(games))])
    return out
