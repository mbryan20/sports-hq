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
WEEKS_LEFT = 5            # regular season ends Dec 5 (week 14)
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
