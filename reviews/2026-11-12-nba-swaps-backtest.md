# NBA swaps and streamers backtest (2026-11-12)

## Findings (first numbers: one finished week, Nov 6–8 mornings)

- Swaps about broke even: 8 judged, the add out-produced the drop in 4 (50%), +0.10 z per game of the add. The page
  promised +4.6 on average; the week came out −0.7 (average miss 7.7, all on the optimistic side: −5.4).
- The miss is regression to the mean on both sides, not missed games: adds valued +1.8 a game produced −0.8 (they played
  every game expected); drops valued −2.7 produced −0.3. The fringe players' per-game values are too confident. A better
  minutes/role source (the DARKO-minutes change) or shrinking short-sample averages toward a projection is the obvious
  fix to test; `compare_sources()` in shq/nba_advice_backtest.py replays the picks under another value source on this
  same history for that.
- The streamer order held: the higher-ranked streamer beat the next one in 10 of 12 pairs, +1.56 z per game.
- This week so far (not final, games through Nov 11) looks worse: swaps −1.64 per add game, 5 of 11 ahead.
- One week is far too few to act on. Model health shows these as info until 20 swaps and 20 streamer pairs are judged
  (about two more weeks); the first baseline is set then.

The generated report follows (`py -m shq.nba_advice_backtest --write`).

What the site advised each morning (first data commit from 8am CT; docs/data/lineups.json history, both basketball leagues), judged over the rest of the fantasy week it was for on ESPN's game logs, in the league's own units (category z-scores on that morning's scale, need-weighted as the site weighted them, above a waiver-level player; a missed game adds 0). Same swap or streamer pair on several mornings of a week: counted once, at its first morning.

## Finished weeks

- Swaps: n=8 (2 replacing a dead roster spot). Actual gain +0.10 per game of the add (-0.72 over the week); the add beat the drop in 4 of 8 (50%).
- Swap estimates: shown +4.62 on average; actual minus shown -5.35 (average miss 7.73).
- Where the swap miss comes from: adds were valued +1.80 per game and produced -0.82 per game played (100% of their expected games played); drops (not dead spots) -2.74 → -0.34 (88%). Top-listed streamers +1.90 → +0.94 (100%).
- Streamers vs the next one listed: n=12 pairs, edge +1.56 per game of the higher-ranked (+1.78 over the week, +0.38 promised); the higher-ranked did better in 10 of 12 (83%).
- Week ending 2026-11-08: swaps n=8 gain +0.10/g, hit 50%, miss 7.73; streamer pairs n=12 edge +1.56/g.

## This week so far (provisional, games through last night)

- Swaps n=11: gain -1.64 per game of the add so far, add ahead in 5 of 11.
- Streamer pairs n=12: edge -0.54/g, higher-ranked ahead in 4 of 12.

## Swaps

| Morning | League | Drop → add | Shown | Actual (add − drop) | Add: games, value/g expected → actual | Drop: games, value/g expected → actual |
|---|---|---|---|---|---|---|
| 2026-11-06 | 3-Ball BB | Kevin Porter Jr. → Alex Caruso | +1.2 | -5.8 (-5.8 − +0.0) | 2 of 2, +0.6 → -2.9 | dead spot |
| 2026-11-06 | 3-Ball BB | De'Andre Hunter → Derrick Jones Jr. | +7.1 | -8.2 (-7.2 − +1.1) | 1 of 1, +1.2 → -7.2 | 1 of 2, -3.0 → +1.1 |
| 2026-11-06 | Ball is Life | Day'Ron Sharpe → Ziaire Williams | +5.0 | -7.4 (+0.6 − +8.0) | 2 of 2, +0.3 → +0.3 | 2 of 2, -2.1 → +4.0 |
| 2026-11-07 | 3-Ball BB | Kevin Porter Jr. → Matisse Thybulle | +2.6 | +4.7 (+4.7 − +0.0) | 1 of 1, +2.6 → +4.7 | dead spot |
| 2026-11-07 | 3-Ball BB | De'Andre Hunter → De'Anthony Melton | +6.8 | -6.6 (-7.7 − -1.1) | 1 of 1, +2.2 → -7.7 | 1 of 1, -4.7 → -1.1 |
| 2026-11-07 | Ball is Life | John Collins → Ziaire Williams | +3.4 | +1.2 (+0.4 − -0.8) | 1 of 1, +1.4 → +0.4 | 1 of 1, -1.9 → -0.8 |
| 2026-11-08 | 3-Ball BB | De'Andre Hunter → Jaxson Hayes | +6.8 | +4.8 (+3.8 − -1.0) | 1 of 1, +2.3 → +3.8 | 1 of 1, -4.5 → -1.0 |
| 2026-11-08 | Ball is Life | Bobby Portis → Mo Bamba | +4.1 | +11.6 (+3.1 − -8.5) | 1 of 1, +3.8 → +3.1 | 1 of 1, -0.3 → -8.5 |
| 2026-11-09 (so far) | 3-Ball BB | Kevin Porter Jr. → Spencer Jones | +10.8 | -15.3 (-15.3 − +0.0) | 2 of 3, +3.6 → -7.7 | dead spot |
| 2026-11-09 (so far) | 3-Ball BB | De'Andre Hunter → Quenton Jackson | +19.3 | +0.1 (+0.1 − +0.0) | 2 of 4, +2.0 → +0.1 | 1 of 3, -3.8 → +0.0 |
| 2026-11-09 (so far) | Ball is Life | Obi Toppin → Robert Williams III | +16.4 | +4.0 (-3.0 − -7.0) | 2 of 3, +3.2 → -1.5 | 2 of 4, -1.7 → -3.5 |
| 2026-11-09 (so far) | Ball is Life | John Collins → Mo Bamba | +13.3 | -12.5 (+2.4 − +14.9) | 2 of 4, +2.2 → +1.2 | 1 of 3, -1.5 → +14.9 |
| 2026-11-09 (so far) | Ball is Life | Day'Ron Sharpe → Spencer Jones | +3.3 | -29.1 (-12.4 − +16.7) | 2 of 3, +2.8 → -6.2 | 1 of 2, +2.6 → +16.7 |
| 2026-11-10 (so far) | 3-Ball BB | Matisse Thybulle → Isaiah Stewart | +3.4 | -9.4 (-4.3 − +5.1) | 1 of 3, +2.4 → -4.3 | 1 of 2, +1.9 → +5.1 |
| 2026-11-10 (so far) | Ball is Life | Obi Toppin → Mo Bamba | +18.5 | +13.8 (+9.3 − -4.5) | 2 of 4, +3.7 → +4.6 | 1 of 3, -1.2 → -4.5 |
| 2026-11-10 (so far) | Ball is Life | Ryan Dunn → Robert Williams III | +12.2 | +0.7 (-1.5 − -2.2) | 2 of 3, +3.6 → -0.8 | 1 of 3, -0.5 → -2.2 |
| 2026-11-10 (so far) | Ball is Life | John Collins → Jalen Smith | +7.1 | +6.0 (+6.0 − +0.0) | 1 of 3, +3.4 → +6.0 | 0 of 2, +1.6 → – |
| 2026-11-11 (so far) | 3-Ball BB | Matisse Thybulle → Paul Reed | +4.0 | -6.6 (+0.0 − +6.6) | 0 of 2, +3.2 → – | 1 of 2, +1.2 → +6.6 |
| 2026-11-11 (so far) | Ball is Life | Obi Toppin → Quenton Jackson | +5.4 | -1.9 (-6.0 − -4.1) | 1 of 3, +0.9 → -6.0 | 1 of 3, -0.8 → -4.1 |

## Streamer pairs

| Morning | League | #k vs #k+1 | Promised | Actual |
|---|---|---|---|---|
| 2026-11-06 | 3-Ball BB | #1 Alex Caruso vs Derrick Jones Jr. | +0.0 | +1.4 |
| 2026-11-06 | 3-Ball BB | #2 Derrick Jones Jr. vs Danny Wolf | +0.0 | +3.3 |
| 2026-11-06 | Ball is Life | #1 Ziaire Williams vs Obi Toppin | +0.7 | +3.9 |
| 2026-11-06 | Ball is Life | #2 Obi Toppin vs Cam Spencer | +0.2 | +1.3 |
| 2026-11-07 | 3-Ball BB | #1 Matisse Thybulle vs De'Anthony Melton | +0.4 | +12.4 |
| 2026-11-07 | 3-Ball BB | #2 De'Anthony Melton vs Jaxson Hayes | +0.1 | -11.2 |
| 2026-11-07 | Ball is Life | #1 Ziaire Williams vs Robert Williams III | +0.2 | +0.4 |
| 2026-11-07 | Ball is Life | #2 Robert Williams III vs Danny Wolf | +0.5 | +10.6 |
| 2026-11-08 | 3-Ball BB | #1 Matisse Thybulle vs Jaxson Hayes | +0.3 | +0.8 |
| 2026-11-08 | 3-Ball BB | #2 Jaxson Hayes vs Derrick Jones Jr. | +0.2 | +12.3 |
| 2026-11-08 | Ball is Life | #1 Mo Bamba vs Matisse Thybulle | +1.9 | +4.1 |
| 2026-11-08 | Ball is Life | #2 Matisse Thybulle vs Jalen Smith | +0.1 | -17.9 |
| 2026-11-09 (so far) | 3-Ball BB | #1 Spencer Jones vs Quenton Jackson | +2.9 | -15.4 |
| 2026-11-09 (so far) | 3-Ball BB | #2 Quenton Jackson vs Jaxson Hayes | +0.7 | -3.4 |
| 2026-11-09 (so far) | Ball is Life | #1 Robert Williams III vs Mo Bamba | +1.0 | -5.4 |
| 2026-11-09 (so far) | Ball is Life | #2 Mo Bamba vs Spencer Jones | +0.1 | +14.8 |
| 2026-11-10 (so far) | 3-Ball BB | #1 Quenton Jackson vs Isaiah Stewart | +0.2 | -2.3 |
| 2026-11-10 (so far) | 3-Ball BB | #2 Isaiah Stewart vs Jamal Shead | +0.8 | +2.3 |
| 2026-11-10 (so far) | Ball is Life | #1 Mo Bamba vs Robert Williams III | +4.0 | +10.8 |
| 2026-11-10 (so far) | Ball is Life | #2 Robert Williams III vs Jalen Smith | +0.6 | -7.5 |
| 2026-11-11 (so far) | 3-Ball BB | #1 Paul Reed vs Quenton Jackson | +0.9 | +6.6 |
| 2026-11-11 (so far) | 3-Ball BB | #2 Quenton Jackson vs Jordan Goodwin | +2.1 | -6.6 |
| 2026-11-11 (so far) | Ball is Life | #1 Quenton Jackson vs Ziaire Williams | +0.1 | -9.1 |
| 2026-11-11 (so far) | Ball is Life | #2 Ziaire Williams vs Cam Spencer | +0.2 | -1.4 |

## Caveats

- Small sample: swap advice started Nov 6 (before that the adds were the most-owned free agents, no drop).
- A missed game counts 0 for the player (as the site's worth counts an out player), so availability is part of the result.
- Judged on what the site showed, not on whether the move was made.

Replay check: the site's own values, replayed by compare_sources(), pick 100% of the streamers and 67% of the swaps the site showed (the replay skips the radar's protected risers and today's Lineup moves); their top 3 streamers -0.62 per game, swaps +0.10 per add game (n=14 / 8).
