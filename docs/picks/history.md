# Pool Picks history

Weekly postmortems. Process is graded separately from outcome (method rule 9).

## Setup — Mon Oct 26, 2026
- Started mid-season. Survivor: eliminated in Week 7 (NYJ). BTO: $2,820 after Week 7 (Three Bet status). CFP: 11,904 points (#29). Yahoo Kosmos: 120 points, 4th of 14.
- Backtest of the stats-only college model on 2026 weeks 1–8 is on the main page (Model check).

## Backtest refresh and stale-line scanner — Sat Oct 31, 2026
Re-ran the walk-forward backtest through week 8, the last graded week (`picks/backtest/2026_w1-8.json`, 444 FBS games).

- **Straight-up:** model 70% vs market 75%. The gap narrows late (weeks 6–8: model 63% vs market 66%; week 5 the model was ahead 77–71) but never closes.
- **Model weight (MODEL_W):** the ATS cards center on market + w × (stats − market). Margin RMSE at w = 0 / 0.1 / 0.3 / 0.5: weeks 1–4 14.02 / 14.17 / 14.69 / 15.47; weeks 6–8 13.68 / 13.68 / 13.71 / 13.80. Least-squares w for weeks 6–8 is 0.09 ± 0.24, and walk-forward (w picked on prior weeks only) chose 0 every week (total RMSE 14.06 vs 14.10 at 0.1). A larger weight doesn't help late season, so **MODEL_W stays 0.1** (the cost vs 0 is negligible). When the model disagrees with the closing line by 3+ points, weeks 6–8 went 54.5% ATS (n=77, ±5.7), which is not significant.
- **Stale lines:** there's no pool-line history for weeks 1–8, so the opener stands in for an early-week pool line (CFBD consensus open for CFB; ESPN/DraftKings open for NFL weeks 1–7), graded at that number (push = ½). The side the market moved away from, at a gap of 1.5+ points, covered **61.6% in CFB (n=194, ±3.5)** and **60.9% in NFL (n=64, ±6.1)**. A key number gained with a gap under 1.5 did not cover more (CFB 51.7%, n=58; NFL 37%, n=19). The same sides at the closing number went 52% / 46%, so the edge is the stale number, not following the move.
- **Caveat:** week 9's pool lines sat ~0.35 pts from Saturday's market but ~1 pt from the opener, so the pools post after early movement and 1.5+ gaps will be rarer than in this test. This morning's scan flagged 5 of 18 open CFP games, led by Auburn +13.5 vs market +11.5.
- **Shipped:** the scanner (`pp/lines.py`, run.yml Wed–Sat) pushes once per game at 1.5+ points or a key number and shows the gap table on the Picks page. Card builds now pull ESPN's current line, so `fair_margins` and the NFL sim center on the market at build time, not CFBD's line from up to 6h earlier.

## Week 8 (CFBD 8, Oct 22-26) — graded Tue Oct 27, 2026
No cards were posted for this week (Pool Picks started Mon Oct 26), so there is no card record and no card-vs-entry differences. Entries were read read-only from all three sites; all were signed in.

**Records (card vs entered)**
- BTO: card none; entered 1-2, net -$200. Ole Miss +4.5 ($400, 1 LP) lost 27-34; CIN +3.5 ($800, 1 LP) won 35-13; KC +4.5 ($600, 2 LP) lost 3-20.
- CFP: card none; entered 1-0, net +5,952. Boise State -13.5 for 5,952 (100% of balance) won 31-10.
- Yahoo: card none; entered 12-13 (12 pts). TB1: Ole Miss 31-24 Texas (actual 27-34), NDSU 18-23 New Mexico (actual 16-21). TB2: most Texas St., fewest Pittsburgh. He took Yahoo's listed favorite in 24 of 25 games; the exception was Ole Miss over Texas (lost).

**Standings**
- BTO: $2,620, #20 of 49, Three Bet. Playoff line (#12) $3,500; leader $9,000.
- CFP: 11,904 pts, #29 of 63 alive. Money line (#12) 23,000; leader 105,000.
- Yahoo: 120 pts, 4th of 14. Leader 126, 3rd 123.

**Differences:** none to judge (no card posted).

**Process vs outcome**
- CFP all-in on Boise State -13.5 won, but the call was good for standings reasons, not because it won: at 5,952 vs a 23,000 money line, max variance was the only path, so it would have been right even as a loss.
- Card vs entries: no card yet, so no read on where Michael's judgment adds value. One process flag: Ole Miss was his side in both BTO and Yahoo (against the Yahoo favorite), so one game drove two losses; that's correlated exposure, worth sizing as one bet.
- Lesson: check whose page you're reading. Yahoo's `/college/3659/9/` is Michael's team ID, not a week number (other numbers show other members' picks), and Yahoo week = CFBD week. Runbook, grader label and slate file corrected; the grader also now grades all-caps college teams (LSU, BYU, USC) instead of treating them as NFL.
