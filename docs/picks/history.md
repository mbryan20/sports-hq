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

## Per-game breakdowns — Sat Oct 31, 2026
- **Shipped:** tap any game on the Picks page (a card row or the new "All pool games" table) to see what the model saw: lines and movement, model vs market, cover % at the pool line, a stats matchup with national ranks, strengths and weaknesses, dated injury/news items, weather and each pool's context. Built from the numbers by templates (`picks/pp/explain.py`); no AI.
- **Picks unchanged:** the Sat 8am refresh card was re-rendered around the posted picks (`--render-only`); every pick, wager and changed flag matched before and after.
- **Rule 4 in the text:** a weakness is labeled "exploitable" only when the opponent's matching unit ranks top 50 and leans on that play type; otherwise it reads "probably won't matter" with the reason. Example: Georgia's big-play defense (#113) vs Florida's big-play offense (#89).
- **Limits:** stats cover games before this week; havoc, plays and run rate are raw (not opponent-adjusted). NFL panels have no Open-Meteo pull (EPA splits from nflverse were added later the same day, commit 4e5d702). Research-run notes show the run date and log link rather than a per-note source; injury items keep their own dated source.

## New data sources and backtest — Sat Oct 31, 2026
Michael asked for sources beyond Yahoo and ESPN (rbsdm-style EPA, success rate, CPOE). The ranked list, terms and limits are in `method/sources.md`.

- **Built:** nflverse play-by-play (free, CC BY 4.0, the data behind rbsdm.com) now gives every NFL BTO game opponent-adjusted offense and defense EPA/play, success rate, EPA per dropback and per rush, explosive-play rate, plus early-down pass rate, pass rate over expected, CPOE and giveaways, each ranked 1-32 (`picks/pp/nflverse.py`). The NFL panels show it with rule-4 strengths/weaknesses and key matchups. nflverse's schedule file supplies closing lines back to 1999, which made a multi-season NFL backtest possible. College panels add current SP+ and the 247 talent composite (CFBD), plus line yards and standard-down success rows.
- **NFL backtest** (`py -m pp.backtest --nfl`, 2023-2026 weeks 2+, n=860, vs nflverse's closing line; `picks/backtest/nfl_2023-2026.json`):
  - The EPA model beats our old scores-only ratings as a standalone forecast: margin RMSE 13.27 vs 13.63, straight-up 61.4% vs 61.0%. Both trail the market: RMSE 12.58, straight-up 67.5%.
  - Leaning toward the stats hurt. The least-squares weight on (stats − market) was negative in all four seasons for the EPA model (pooled −0.26 ± 0.12; 2025-26 out of sample −0.44 ± 0.19). Walk-forward picked a weight of 0 in all 50 weeks for both models. At 3+ points of disagreement, the stats side covered 45.6% (n=294), which isn't significant.
  - **Change:** the NFL MODEL_W goes from 0.1 to 0. NFL BTO picks now center on the current market plus research. The EPA numbers stay on the panels as context. (Picks barely move: 0.1 × a few points.)
- **College extra stats** (`py -m pp.backtest --cfb-features`; fit on 2025, tested on 2026 weeks 1-8, n=444): adding standard/passing-down success rates or run/pass EPA moved the stats-only model from 70.0% to about 71.4% straight-up (margin RMSE 16.9 → 16.6). That's within noise (±2.2%), and the weight vs the market stayed negative (−0.10 to −0.14). **The college model is unchanged** and MODEL_W stays 0.1. The stats show on the panels instead.
- **Takeaway:** public efficiency stats are already in the closing line, in both NFL and college. The edges worth chasing are the ones the market gives away: stale pool lines (61% at 1.5+ points), line points across key numbers, and news that breaks after the pool posts. The new stats help explain each game and flag which weaknesses an opponent can actually exploit. On their own they don't beat the line.
- **Data on the page:** `picks/data/cards.json` now has `game_stats`, keyed by breakdown id (the `bd` on each card row): per-team `[value, rank]` pairs for the panels.

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

## Week 9 (CFBD 9, Oct 29-Nov 2) — graded Tue Nov 3, 2026
Entries were read read-only from all three sites in Michael's Chrome; all were signed in. Cards graded are the last posted before each pool locked (BTO final Thu Oct 29; CFP and Yahoo Sat 8am refresh).

**Records (card vs entered)**
- BTO: card 3-0, net +$2,620 (MIN +7.5 LP 4 $1,300 ★; Georgia -11.5 $660; Oregon -3.5 $660). Entered 2-1, net +$700: DET -2 (LP 1.5, $500 ★) won 19-15; Northwestern +4.5 (LP 1, $800) lost 26-34; Wake Forest -11 (LP 1.5, $1,000) won 51-7. He wagered $2,300 of $2,620.
- CFP: card 1-1, net 0; entered the same (Utah -6.5 for 5,952 won 49-25; Auburn +13.5 for 5,952 lost).
- Yahoo: card 18-7; entered 15-10. TB1: Ohio St. 31-24 USC (actual 18-30), Wisconsin 16-20 Iowa (actual 0-30). TB2: most Notre Dame, fewest Rutgers (both wrong).

**Standings**
- BTO: $3,320, #20 of 49, Three Bet (min $1,660 in week 10). Playoff line (#12) $4,250; leader $10,700. The card's picks would have made $5,240, above the line.
- CFP: 11,904 pts, #25 of 55 with points. Money line (#12) 22,000; leader 122,500. Rebuy window closes 11am Nov 7.
- Yahoo: 135 pts, 8th of 14 (tied with 7th). Leader 144, 3rd 141.

**Differences (judged on pre-kickoff information)**
- BTO MIN@DET, card MIN +7.5 (LP 4) vs entered DET -2 (LP 1.5): both won. Opposite sides of the Big Game, each buying through 3 against a market of DET -3. The card's was the stronger ticket: it also crossed 7, so it lost only to DET by 8+, while DET -2 needed a 3+ point win. Card better on process; same result.
- BTO Northwestern@Oregon, card Oregon -3.5 vs entered Northwestern +4.5: Michael's call was better. The market moved about 2 points toward Northwestern after the pool posted, so +3.5 (+4.5 with LP) was the stale-number side, the edge that covered about 61% in the backtest. The card's own Saturday CFP note dropped Oregon for that reason ("its edge was stats only"). Oregon won by 8, so the better call lost. Not confirmed: whether the move had happened before BTO's Friday 8pm lock.
- BTO, card only Georgia -11.5 (won 27-8) and entry only Wake Forest -11 (won 51-7): both reasonable. The card listed Wake Forest -12.5 as "also worth a look" at 53%; Michael's 1.5 LP improved that number.
- Yahoo Northwestern@Oregon, card Oregon vs entered Northwestern: the card was better. Straight-up the market had Oregon about 62%, and 7 of the 10 active group members also took Northwestern, so the pick was less likely to win and gave no separation from the group. The BTO spread edge on Northwestern +4.5 doesn't make Northwestern the straight-up winner.
- Yahoo Illinois@Maryland, card Illinois vs entered Maryland, and Washington St.@SDSU, card SDSU vs entered Washington St.: a wash. The card listed both under "Value of taking the other side": each was about a 47% winner, worth a combined +0.2 points of season win chance (4.0% → 4.3% with both). Michael was the only member on Maryland. Both lost by 6 or fewer (20-17, 26-20).

**Process vs outcome**
- Good decision that lost: Northwestern +4.5 in BTO was on the stale-number side of a 2-point move and lost when Oregon won by 8. Auburn +13.5 in CFP (2 points better than market) also lost. Neither result says the stale-line read was wrong.
- Card vs entries: the card would have been 3 Yahoo points and $1,920 better. Most of the gap is Northwestern in Yahoo plus the two card-endorsed contrarian picks (Maryland, Washington St.), which are legitimate season-win plays that lost close games. The repeatable value Michael added was the Northwestern spread read. No evidence yet that his Yahoo straight-up departures add value.
- Lesson: one game in two pools needs two separate decisions, a spread side and a straight-up winner. For the second week running (Ole Miss in week 8, Northwestern in week 9), his BTO side became his Yahoo pick, so one game cost him in both pools.
