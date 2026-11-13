# Baseball plan: Sports HQ's fantasy baseball edge

Written Nov 12, 2026 (replaces the Feb 1, 2027 kickoff plan). Code so far: `shq/mlb_data.py` (free reads, cached),
`shq/mlb_backtest.py` (in-season signals), `shq/mlb_prospects.py` (prospect model and watch list),
`docs/baseball/` (site page). Everything here is free data, no AI in GitHub Actions, read-only on ESPN.

**The short version**
- 3-Ball (dynasty) is where the edge is. Rosters are deep, the waiver market is slow (useful free agents mostly went
  unclaimed in 2026), and prospects come through the league's own 4-round MLB draft and 5 minor-league spots a team.
- First deliverable is live: a ranked prospect watch list on the site (public facts) plus a private Doc with who holds
  each prospect in the league sheet: "3-Ball baseball prospect watch list" (Drive > Claude Home > For Michael).
- Backtests kept 4 signals and dropped 5 (table below). The prospect model ties MLB Pipeline for hitters, beats it for
  pitchers on small samples, and finds a few useful players each year that Pipeline's Top 100 missed.

## 1. League facts (read Nov 12, 2026)

| | 3-Ball Dynasty League | Hardball |
|---|---|---|
| ESPN league / my team | 142878, team 6 "Ragonk Force" | 143598, team 2 "Ippei You Later" |
| Readable | public API (cloud reads it) | private: 401 without sign-in, read through Michael's Chrome (laptop snapshot, like Stempak) |
| Teams, format | 10, head-to-head categories, 19 weeks, 6-team playoffs (2-week rounds) | 12, same format |
| Categories (confirmed from team totals) | R, HR, RBI, SB, OPS / K, QS, SV, ERA, WHIP | same 10 |
| Lineup | C, 1B, 2B, 3B, SS, 5 OF, MI, CI, 2 UTIL, 9 P | same but 1 UTIL |
| Bench / IL / roster | 8 / 4 / 35 | 5 / 3 / 30 |
| Keepers | 31 a team on ESPN; plus 5 minor-league spots and a 4-round MLB draft each year in the league sheet | none (redraft) |
| Draft | the 2026 ESPN "draft" was 309 keepers + 1 pick, entered by Mar 24; first free-agent adds Mar 19 (87 in March) | snake, Mar 23, 2026 evening CT |
| Waivers | no FAAB, 24h, processed Sunday 11pm; 398 adds in 2026 | no FAAB, 48h, daily |
| 2026 finish | 80-98, 8th of 10 | 106-73, 3rd of 12 |
| My 3-Ball MLB picks (league sheet) | 2027: rounds 1, 2 (from Chan), 3, 4 (my own 2nd went to Chan); 2028: all four | |
| My 3-Ball minors (league sheet) | Carlos Lagrange, Angel Genoa, Jarlin Susana, Edward Florentino, Joshua Baez | |

Not confirmed: the 2027 leagues don't exist on ESPN yet (404); the 2026 3-Ball league was renewed Jan 28, 2026.
Not confirmed: the 3-Ball MLB draft date (2026 picks were updated in the sheet Mar 19, the day adds started).
Not confirmed: weekly add limits (ESPN shows 1.0 and 0.57 "per scoring period"; likely 7 and 4 a week).

## 2. Free data sources and their terms

| Source | What we use | Terms / limits | Use |
|---|---|---|---|
| MLB Stats API (statsapi.mlb.com) | MLB + every minor level (sport 11-14, 16), Arizona Fall League (sport 17, league 119), ages, draft year, 40-man rosters, transactions, schedules with probable pitchers, injuries via transactions | MLBAM notice: "individual, non-commercial, non-bulk use" only. No published rate limit; no key | yes, season aggregates, a few calls a day, cached |
| Baseball Savant search CSV | per-player Statcast aggregates for any date range (`group_by=name`): wOBA, xwOBA, barrels, K%, velocity, spin | MLB terms (personal, non-commercial). robots.txt allows all. No published limit; pitch-level export caps at 25,000 rows | yes, aggregates only, 2s between calls, never pitch-level in git |
| MLB Pipeline (mlb.com/milb/prospects/<year>/top100) | Top 100 ranks 2011-2026, keyed by MLB player id | MLB terms; robots.txt allows /milb/ | rank numbers only, no scouting text |
| ESPN fantasy API | rosters, % rostered (today only: no history), transactions, ESPN projections | unofficial, public leagues readable | yes (public 3-Ball); Hardball through Chrome, read-only |
| FanGraphs | projections, leaderboards | site answers scripts with a bot check (403); written terms couldn't be read for the same reason | no automated use; by hand only |
| 3-Ball league sheet (Google Sheet) | minor-league spots, draft picks | private league data | laptop only (`state/dynasty_sheet.json`, gitignored); only my own holdings are public |

No paid APIs. ESPN keeps no ownership history, so from spring 2027 Sports HQ saves a daily % rostered reading itself.

## 3. Data design: keep the public repo small

- Raw reads go to `.cache/mlb/` (gitignored), keyed by URL. Finished seasons and closed date ranges never refetch;
  live data refetches after a set age. GitHub Actions runs start empty and refetch what they need (a few MB a day).
- Committed: only summaries the site shows, each under ~200 KB: `docs/data/mlb_prospects.json` (now),
  `docs/data/mlb_backtest.json` (now), later `docs/data/mlb_players.json` (values per league) and
  `state/mlb_owned.json` (daily % rostered, rolling 60 days, one small integer per player per day).
- Never committed: pitch-level Statcast, full game logs, the league sheet, other teams' minor-league holdings.
  The private Doc is regenerated on the laptop (`py -m shq.mlb_prospects --write` writes `.cache/mlb/watch-private.md`).
- Stable ordering and rounding in every JSON so each commit's diff stays small.

## 4. Signals and their backtests

### In-season signals (`py -m shq.mlb_backtest --write`)
Method: checkpoints May 15 and Jun 30 of 2025 and 2026. Each signal sees only games before the checkpoint and is
judged on the rest of that season (ROS). Each is compared with the baseline a manager already has: the player's
results so far. Hitters need 60+ PA by May 15 (120 by Jun 30) and 100+ PA after.

| Signal | Rule | Result | Baseline | Verdict |
|---|---|---|---|---|
| xwOBA vs results (hitters) | which predicts ROS wOBA better | correlation .31 (n=1,123) | wOBA so far: .22 | **keep**: value hitters on xwOBA |
| Buy-low hitter | wOBA .310 or lower and xwOBA 30+ pts higher | ROS wOBA up 20+ pts: 117/157 (75%); ROS .330+: 59/157 (38%) | same bracket, not flagged: 175/328 (53%); 98/328 (30%) | **keep** (both seasons) |
| Sell-high hitter | wOBA .350+ and 30+ pts over xwOBA | ROS down 20+ pts: 51/61 (84%); stayed .340+: 20/61 (33%) | same bracket, not flagged: 140/221 (63%); 111/221 (50%) | **keep** |
| Pitcher K% jump confirmed by xwOBA | K% up 4+ pts vs last season and xwOBA-against no worse | ROS xwOBA 15+ pts better than last season: 48/94 (51%) | K% jump alone 53/123 (43%); all pitchers 218/753 (29%) | **keep** |
| Barrel-rate jump | barrels/PA up 2.5+ vs last season | ROS wOBA 20+ over last season: 58/137 (42%) | wOBA jump alone 114/231 (49%) | **drop**: worse than results |
| xwOBA confirming a wOBA jump | jump with wOBA within 30 pts of xwOBA | 86/174 (49%) | wOBA jump alone 114/231 (49%) | **drop**: adds nothing |
| Velocity jump (pitchers) | fastball 1+ mph faster than last season | 19/50 (38%) | K% jump 49/119 (41%) | **drop** |
| Velocity drop | 1+ mph slower | got 15+ pts worse: 44/120 (37%) | all pitchers 241/723 (33%) | **drop** |
| Unlucky pitcher | wOBA-against .330+ and 25+ over xwOBA | ROS .300 or better: 30/90 (33%) | same bracket 64/187 (34%) | **drop** |
| Playing-time jump | 40+ PA in last 14 days after under 25 | stayed a regular: 12/25 (48%) | too few to test | **drop** for now; retest with lineup cards |

Also: for pitchers, K% so far predicts ROS wOBA-against (r = -.33) better than results or xwOBA (.27).

Market test (2026, 3-Ball's own adds as the clock, since ESPN keeps no ownership history): flagged players who were
free agents in 3-Ball at the checkpoint and then turned useful (hitters ROS wOBA .340+ on 150+ PA; pitchers ROS
xwOBA-against .290 or better on 150+ batters):

| Flag | Free agents flagged | Turned useful | Added later by a 3-Ball team | Median days after the flag |
|---|---|---|---|---|
| Buy-low hitter | 34 | 8 (24%) | 2 | 46 |
| Low wOBA, not flagged (baseline) | 82 | 17 (21%) | 6 | 64 |
| wOBA jump vs last season | 32 | 11 (34%) | 4 | 80 |
| Pitcher K% jump | 23 | 8 (35%) | 2 | 60 |

Read: the 3-Ball waiver market is slow (most useful free agents were never added), so speed matters less than
attention. Among free agents, buy-low barely beats its baseline (24% vs 21%); results jumps (wOBA, K%) find more
useful players. So: the free-agent radar ranks on results jumps, and buy-low / sell-high drive trade ideas between
rostered players, where they beat the baseline clearly.

### Prospect model (`py -m shq.mlb_prospects --write`)
A prospect's season at his highest full level: performance vs that level (OPS and K% for hitters; K-BB% and ERA for
pitchers, as z-scores), years younger than the level's average player, the level, and Pipeline's rank (0 when
unranked). Fit on the 2021-22 prospect classes, tested on 2023 and 2024 without refitting. "Useful" = a 350+ PA
season with .750+ OPS or 20+ SB within two seasons (pitchers: 100+ IP at ERA 4.00 or better, or 20+ saves+holds at 3.50).

| Test class | Useful | Pipeline Top 100 only: hits in its top 25 / 50 | Stats + age model | Stats + age + Pipeline | Useful players Pipeline missed / model had in its top 50 |
|---|---|---|---|---|---|
| Hitters 2023 | 28 of 1,200 | 7 / 11 | 5 / 13 | 8 / 14 | 17 / 4 |
| Hitters 2024 | 25 of 1,178 | 6 / 10 | 4 / 9 | 5 / 9 | 15 / 2 |
| Pitchers 2023 | 13 of 1,182 | 1 / 2 | 2 / 3 | 3 / 3 | 12 / 2 |
| Pitchers 2024 | 26 of 1,158 | 1 / 1 | 4 / 8 | 4 / 7 | 25 / 8 |

Honest read: for hitters the combined model ties Pipeline (better in 2023, slightly worse in 2024); the numbers
alone are worse at the very top. Age adds a little over performance + level (more hits in the top 50, fewer in the
top 25). For pitchers the model beats Pipeline, on small samples. The cheap edge is the tail: 2 to 8 useful players a
class that Pipeline's Top 100 left out sat in the model's top 50 (2024 pitchers: Didier Fuentes, Justin Wrobleski,
Noah Cameron, Christian Scott, Ronny Henriquez, Jack Leiter, Mason Fluharty, Michael McGreevy). Use: Pipeline-ranked
players with good numbers early, numbers-only names with late picks.

Call-up timing (2021-24 classes, debuted the next season): hitters in AAA 1.5+ years young 253/415 (61%), AAA about
average age 93/245 (38%), AA young 103/351 (29%), A+ young 24/279 (9%). Pitchers in AAA young 304/602 (50%), AA young 74/279 (27%).

### Category values (to build; reuses `shq/nba_values.py`)
`nba_values.scales()` / `zs()` already do league-specific z-scores with ratio categories weighted by volume. Baseball
plugs in: counting cats R, HR, RBI, SB, K, QS, SV as is; OPS as (OPS - pool rate) x PA; ERA and WHIP reversed as
(pool rate - ERA) x IP. Pool = the top teams x roster spots for each league (350 for 3-Ball, 360 for Hardball).
Hitters and pitchers are scored in separate pools, then put on one scale by replacement level. In-season the rate
inputs use xwOBA-based expected stats for hitters (that backtest beat results) and K% for pitchers.

### Ownership gap (to build)
Our value rank against ESPN % rostered: "ours top 150, rostered under 30%" = add target (Hardball) or long-term
add (3-Ball, only if better long-term than the drop, rule 2); "ESPN 80%+, ours outside the top 250" plus sell-high = trade
away. For 3-Ball trades, reuse `shq/nba_trade.py`'s age curve. Every flag is checked against `fantasy-rules.md`
(rule 1: no streaming in 3-Ball; rule 5: one named drop).

## 5. Where it shows, what is pushed

- **Baseball page** (`/baseball/`, home-page tile and the ▦ menu): prospect watch list now; in season adds a trend
  radar per league in the NBA radar's pattern (risers among free agents, my players slipping, buy-low and sell-high
  trade ideas), each line with the number behind it.
- **League pages**: "3-Ball MLB" and "Hardball" tiles with What to do (lineup fixes, adds with one named drop,
  trade ideas), category table, Players page tabs (same page as NBA, categories swapped).
- **Weekly tab**: two-start pitchers and the week's matchups (Hardball streamers only; 3-Ball never streams).
- **Today digest**: a starter not in the lineup or scratched, probable-pitcher changes.
- **Pushes** (at most one a day for both leagues): a watch-list prospect called up who is on no 3-Ball roster; a
  lineup hole that can be filled. Never a 3-Ball streamer.
- **Private Doc**: who holds which prospect (league sheet), refreshed when the list is.

## 6. Build order and dates

| # | When | What | Effort |
|---|---|---|---|
| 1 | done Nov 12 | data reads + cache, signal backtest, prospect model, watch list page + private Doc | done |
| 2 | Jan 25, 2027 (staged job, replaces Feb 1) | rerun the watch list with Pipeline's 2027 Top 100 and the latest league sheet; check whether ESPN has the 2027 leagues; refresh the Doc | 1 session |
| 3 | by Feb 15 | `LEAGUES` entries (sport "mlb"), ESPN baseball slot and stat maps, rosters on the site; Hardball through the laptop snapshot (`save_espn` for flb); daily % rostered snapshots start | 1-2 sessions |
| 4 | by Mar 1 | category values (`mlb_values.py`), Players page tabs, ownership-gap list, Hardball draft board from ESPN projections + values | 1-2 sessions |
| 5 | by Mar 10 (before 3-Ball's draft, ~mid-March) | 3-Ball draft board: watch list + MLB-ready rookies, my picks and roster needs; refresh the Doc | short |
| 6 | by Mar 20 (before Hardball's draft, ~Mar 22) | Hardball draft sheet on the site | short |
| 7 | Opening Day (~Mar 25) | daily lineups, probable pitchers, two-start pitchers on the Weekly tab, injury watch from MLB transactions | 1 session |
| 8 | from Apr 15 | trend radar with the kept signals; one push a day max | 1 session |
| 9 | May 15 and monthly | rerun the backtest in the nightly model health with real ESPN ownership history; drop what stops working | small |
| 10 | July (MLB draft) | draftee list for the 3-Ball race (Pipeline draft ranks + college/HS stats where free) | short |

## 7. Rules this follows
Public repo: no secrets, no ntfy topic, no other teams' sheet holdings. No paid APIs, no AI in Actions except `ask.yml`.
Read-only on every fantasy site. Merge, never rebase. Estimates are labeled. Each signal stays only while it beats its
baseline. Scheduled jobs are staged for Claude Ops, never edited here.
