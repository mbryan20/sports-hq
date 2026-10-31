# Pool Picks

Phone-first weekly pick cards for Michael's football pools: **https://mbryan20.github.io/sports-hq/picks/**

- `pp/` holds the stats-only college model (CFBD data, ridge ratings, 10,000-run Monte Carlo per game), the pool strategy sims (Yahoo 14-person pick'em, BTO and CFP wager sizing) and the card builder.
- `RUNBOOK.md` is what each scheduled run follows.
- `../docs/picks/method/` has the pool method and rules.
- `slates/` stores each week's games as read from the pool sites. `research/` stores each run's sourced injury and QB notes.
- `backtest/` holds the walk-forward check (`py -m pp.backtest --through N`, N = last graded week): calibration, the MODEL_W weight study, and stale-line covers.
- `pp/lines.py` is the stale-line scanner (run.yml, Wed–Sat) and the fresh ESPN lines the cards use.

Run it locally:

    py -m pp.fit         # preseason only: refit prior scale + points model on last season
    py -m pp.backtest    # walk-forward calibration
    py -m pp.cards --stage draft
    py -m pp.publish --stage draft
