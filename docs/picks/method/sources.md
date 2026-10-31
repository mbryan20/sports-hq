# Data sources for Pool Picks and Sports HQ

Checked Oct 31, 2026 on the live pages, release files and API specs. The rules: free only, machine-readable only,
respect each source's terms and rate limits, cache downloads, and never commit secrets or bulk raw data to this
public repo.

## What we use today
| Source | Used for | Access | Notes |
|---|---|---|---|
| CollegeFootballData (CFBD) | college games, advanced stats, lines (incl. openers), SP+, talent, returning production | API, free key, 1,000 calls/month | capped at 900 in `picks/pp/http.py` |
| ESPN public JSON | scores, current and opening odds (DraftKings), injuries, news, records | unofficial, no key | see the ESPN terms flag below |
| Sleeper | NFL projections, players, guillotine data | public API | |
| FantasyCalc | trade values | public API | |
| Open-Meteo | kickoff weather | free API, no key | free tier is for non-commercial use only; Sports HQ is personal, so it fits |
| **nflverse** (new) | NFL play-by-play EPA, success rate, CPOE, early-down pass rate; closing lines 2023+ | GitHub release files | built in `picks/pp/nflverse.py` (Oct 31) |

## Ranked shortlist
"Built" means it's in the pipeline now. Ranked by how much it can improve the picks for the effort, given the
rules above.

| # | Source | What it offers | Access, terms, limits | Fresh | Helps | Status |
|---|---|---|---|---|---|---|
| 1 | **nflverse play-by-play** (`pbp` release) | Every NFL play with EPA, success, win prob, CPOE, pass rate over expected. rbsdm.com is built on it. | Free files at `github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_<year>.csv.gz` (2026 so far: 7 MB; a full season: 19 MB). License **CC BY 4.0** (credit nflverse). No key. | Nightly in season, plus game-day runs | NFL BTO games: opponent-adjusted offense/defense EPA, success, pass/rush splits, explosive plays, style; strengths/weaknesses on the panels | **Built** |
| 2 | **nflverse schedules** (`schedules/games.csv.gz`) | Every game since 1999 with scores, closing spread, total and moneylines, rest days, starting QBs, roof, temp, wind | Same release terms, 0.5 MB | Every 5 minutes in season | The NFL backtest's market line (2023-25 had no free line history before) | **Built** (backtest) |
| 3 | **CFBD endpoints we hadn't used** | `/ratings/sp` (Bill Connelly's SP+, current season), `/talent` (247 composite). Already used: game advanced stats (EPA, success, explosiveness, line yards, down splits, stuff rate), `/stats/season/advanced` (havoc), `/player/returning`, `/lines` (with `spreadOpen`). | Same key and budget. SP+ costs ~1 call/day, talent ~1/month. **Terms:** CFBD data may not be republished "as a standalone dataset or bulk download" (see flags). | SP+ updates in season; SP+ has no week-by-week history | College panels: SP+ second opinion, talent rank; line yards and standard-down success rows | **Built** (context) |
| 4 | **nflverse injuries / depth charts / snap counts / FTN charting** | Official-style injury report fields (report status, practice status), weekly depth charts, snap shares; FTN charting is CC BY-SA 4.0 | Same release pattern, e.g. `injuries/injuries_2026.parquet` (also csv) | Injuries and depth charts daily 7am UTC; snaps and FTN every 6h | Second injury source next to ESPN for the injury-confirm rule; snap-share trends for waivers | Next (not built) |
| 5 | **CFBD `/ratings/elo` and `/metrics/wp/pregame`** | Elo by week (has a `week` parameter, so it can be backtested) | Same key and budget | Weekly | A second college rating that can be tested walk-forward | Next (not built) |
| 6 | **sportsdataverse cfbfastR pbp** | College play-by-play (CFBD-based), `releases/download/cfbfastR_cfb_pbp/play_by_play_2026.parquet` (79 MB) | Free, MIT repo; data comes from CFBD, so CFBD's terms apply | Sat/Sun/Mon in season | Play-level college splits (e.g. early-down pass rate) without spending CFBD calls | Later; parquet would need pyarrow |
| 7 | **hoopR NBA box scores** (sportsdataverse) | Player and team box scores, play-by-play for 2026-27 (`espn_nba_player_boxscores/player_box_2027.parquet`) | Free files, MIT repo, **ESPN-derived** (ESPN terms flag applies) | Daily 7am UTC | NBA category leagues: recent per-game form for FA adds | Later; only free NBA option |

Pass-through and context only:
- **rbsdm.com**: a web app on nflverse data with no public API or terms page. We compute the same numbers from nflverse, so nothing is lost.
- **ESPN FPI** (`site.api.espn.com/apis/fitt/v3/sports/football/nfl/powerindex?season=2026`, also college): returns FPI and unit efficiencies, NFL updated today. It is ESPN JSON, so the ESPN flag applies; not built. Not confirmed: whether college FPI is current (its run date reads Sep 26).
- **The Odds API**: free tier is 500 credits/month with a key; **historical odds are paid only**. We already get current and opening lines from ESPN (NFL) and CFBD (college), so skip it.

## Avoid: paid, or terms that forbid automated use
| Source | Why |
|---|---|
| FTN (DVOA) | Paid subscription; the site blocks automated fetches |
| PFF | Paid API; terms ban scraping and AI/ML use |
| sumersports.com | Free team tables, but terms ban robots/scraping and commercial use; no API |
| Sports Reference (basketball-reference, pro-football-reference) | Data-use page bars automated access; bot limit 20 requests/min or a 1-day block |
| stats.nba.com / nba_api / nbastatR | NBA terms bar use "in connection with any fantasy game"; blocks cloud IPs (GitHub Actions) |
| nfl.com injury pages | Terms ban robots that harvest for commercial purposes; nflverse's injuries file covers the same report |
| sportsbookreviewsonline line archives | No reuse without written consent; archives stopped in 2021-23 |
| gameonpaper.com | Web page only; robots.txt blocks AI crawlers; use the sportsdataverse files it is built on |

## Flags for Michael (existing setup, not changed here)
- **ESPN's terms ban automated access.** ESPN.com's terms point to Disney's, which bar copying "using a robot, spider, script, or other automated means". That covers the JSON endpoints Sports HQ already relies on (scores, odds, injuries, news, league data). Usage is light, personal and cached, but it is against the written terms. Michael's call (Oct 31): switch to another source only where it's a verified true replacement, keep ESPN as the backup, and ping ESPN as little as possible. See "Less ESPN" below.
- **CFBD raw responses are committed to this public repo** (`picks/cache/cfbd/*.json`, 17 files added with the Oct 31 breakdowns change; the reason isn't written down, and the cloud backup has its own CFBD key). CFBD's terms bar republishing its data "as a standalone dataset or bulk download" or a "public database mirror". The fix is to stop committing raw responses (gitignore them, keep only derived files such as `points_model.json`) and let the backup build fetch within the budget. The two new cache files this change created (SP+ and talent) were not committed.

## Less ESPN (Oct 31, 2026)
Each ESPN data point was checked against nflverse for 2026 weeks 1-18 (272 games) before deciding.

| Data | Verdict | Now |
|---|---|---|
| NFL final scores, home/away, neutral site | **Same**: all 108 finals matched ESPN exactly | Picks ratings, panels and grading read nflverse's `games.csv` (one 0.5 MB download per 6h). ESPN is the backup if nflverse is down, or if a game that kicked off 6+ hours ago has no score there yet. Saves ~18 ESPN scoreboard calls per card build. |
| NFL kickoff times and live game state | **Not the same**: nflverse still had LV @ SF (week 9) at 4:05 ET after it moved to 4:25 on FOX (ESPN and FOX's game page agree on 4:25). The other 24 differences are unscheduled weeks 16-18 placeholders. nflverse also has no live in-game state. | Stays on ESPN. Lock-time swap alerts depend on it. |
| NFL injury report | **Not the same**: nflverse updates once a day (7am UTC), and the injury rule needs ESPN's dated note and player-card link | Stays on ESPN |
| Current and opening odds, player news, fantasy league data, NBA | No free replacement | Stays on ESPN. Player news headlines are now cached an hour per player, so the 10-minute game-day loop asks once an hour instead of six times. |

## Rate limits and caching in the pipeline
- nflverse: the current season's play-by-play is re-downloaded at most every 20 hours, past seasons once a year, into `picks/cache/nflverse/` (gitignored). Each season is boiled down once to a ~0.2 MB per-team-game summary beside it.
- CFBD: every call goes through `pp/http.py` (cache + 900/month cap). This change adds ~1 call/day (SP+) and ~1/month (talent).
- No new keys, no paid APIs, no AI calls in GitHub Actions. The NFL stats only run in the laptop card builds.
