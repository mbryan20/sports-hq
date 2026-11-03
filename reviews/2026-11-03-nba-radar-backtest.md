# NBA trend radar backtest (2026-11-03)

Mornings replayed: Oct 26 to Nov 1, each with only the games before it (ESPN game logs through Nov 2). League: 3-Ball BB, categories FT%, REB, PTS, BLK, 3PM, STL, AST, FG%.

## Result

Verdict: the flagged free agents kept their bigger roles and out-produced the site's current suggestions; no 3-Ball team picked any of them up afterward, so there was no waiver race to win yet. Small sample (5 free agents), so treat this as a first read.

- Free agents flagged: 5 players (9 player-mornings).
- Role held (minutes after the flag at least 3 above his old baseline): 5 of 5.
- Minutes per game: baseline 16.9, at the flag 25.5, after the flag 28.1.
- Category value per game after the flag (z units, 0 = average rotation player): radar flags -1.15, the site's current suggestion (3 most-owned free agents) -2.47, average free agent who played -5.15.
- Every player the radar would have flagged, rostered or not: 15; role held for 11 (minutes 21.6 before, 28.9 after).
- Added later by a 3-Ball team: 0 of 5.

## Players (first flag)

| Flagged | Player | Min before → at flag → after (games) | Value/g after | Added in 3-Ball | % rostered now (ESPN +/-) |
|---|---|---|---|---|---|
| Oct 30 | Luguentz Dort | 23 → 22 → 30 (2) | -2.59 | – | 2.6 (-0.0) |
| Oct 31 | Jarace Walker | 18 → 26 → 32 (2) | -1.27 | – | 2.1 (+0.1) |
| Oct 31 | Dean Wade | 9 → 27 → 26 (2) | +1.50 | – | 1.2 (+0.1) |
| Oct 31 | Sandro Mamukelashvili | 22 → 25 → 26 (2) | -2.35 | – | 5.9 (-0.4) |
| Oct 31 | Jake LaRavia | 11 → 27 → 26 (2) | +0.29 | – | 7.9 (-0.2) |

## Caveats

- Small sample: two weeks of a new season. Run it again in December.
- Ownership at the time of each flag isn't recorded anywhere free, so the market check uses 3-Ball's own adds; `state/nba_owned.json` now keeps a daily % rostered reading, so later backtests can measure the ESPN-wide rise.
- The comparison list uses today's % rostered to rank that morning's free agents (a small look-ahead in its favor).
- Injuries come from the logs only (a key teammate missing games), not that morning's ESPN report.
