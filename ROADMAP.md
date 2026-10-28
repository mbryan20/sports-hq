# Sports HQ roadmap and hand-off notes

**Read this first in any new session.** It holds the goal, where things stand, what's next, and the rules
that keep the system working. README.md explains how the system runs; IDEAS.md collects ideas.

## The goal
Michael wants **one all-in-one fantasy hub** for every league and pool. It should work from his phone,
including at work, where claude.ai is blocked. For each league it should tell him *what to do*:
- lineup fixes
- waiver adds, with who to drop
- trade targets and trade offers
- guillotine survival and bids
- matchup outlook
- pick'em cards

It runs on its own (GitHub Actions, no AI in scheduled jobs). The laptop's Claude tasks only read sites
that need a sign-in. It is an ongoing project, improved through the monthly review and ideas he adds.

## Where things stand (update this table when something ships)
| Area | Status |
|---|---|
| Lineup tabs, 8 leagues (NFL + NBA) | live |
| Injury watch + exact-swap pushes (2h before lock) | live |
| Weekly tab (Tue 7am): start/sit + top FA adds | live |
| Today tab + 8am digest push | live 2026-10-28 |
| Picks (BTO, CFP, Yahoo pick'em) | live (laptop, Tue–Sat) |
| War Room copy + pinned header links | live |
| League tabs as action pages (matchup, fixes, moves, adds, guillotine standing, FAAB) | live 2026-10-28 (`shq/advice.py`) |
| Waiver adds ranked on rest-of-season value, not one week's projection | not started |
| Trade finder + trade offers | not started |
| Guillotine survival odds + FAAB bid guidance on the tab | live 2026-10-28 (`shq/guillotine.py`; push when cut risk > 20%) |
| NBA category matchup (per-category totals, win/lose/close, what to chase, category FA adds) | live 2026-10-28 (`shq/categories.py`; Ball is Life fills in from the next laptop sync) |
| 3-Ball dynasty assets (picks, minors) + Command Center "Moves to make" | not started |
| Kosmonauts FA adds | live 2026-10-28 (laptop sync reads Yahoo's top 15 available per position; `shq/save_roster.py`) |
| Baseball | Feb 2027 (task `sports-hq-baseball-kickoff`) |
| Older claude.ai routines (auto-swaps, bids, helpers) | Michael to decide: keep, merge or retire (IDEAS.md) |

## Next up, in order
1. **Trade tools.**
   - Value source: FantasyCalc's free public values API (dynasty and redraft, superflex and PPR settings).
     Sleeper and public ESPN leagues expose every roster. Private ESPN leagues need the laptop snapshot to
     include all teams.
   - Trade finder: other teams' needs vs my surplus.
   - Offers: 1-for-1 and 2-for-1 deals that are fair by value and help both lineups.
   - NBA has no free value API; use ESPN ranks and projections.
2. **Better waiver adds:** rank free agents by rest-of-season value, not one week, using the same value
   source plus projections. For each add, say who to drop. FAAB guidance where the league uses FAAB.
3. Dynasty assets.

## Rules that must not break
- **The repo is public.** Never commit the ntfy topic, cookies, tokens or passwords.
  - Secrets live only in GitHub Secrets.
  - Laptop runs read the topic from `picks/.ntfy_topic` (gitignored).
- **Read-only on fantasy sites.** Never add, drop, trade or bid automatically. The only automatic action is
  a Yahoo lineup swap via the API, if write access ever exists. Everything else is a push saying exactly
  what to do.
- **Git:** always merge, never rebase (`git pull --no-rebase --no-edit`); the repo has subtree merges.
- **Laptop tasks:** use Michael's Chrome through Claude in Chrome (`ops/BROWSER.md`), never the built-in
  browser. Never type passwords.
- **Manual steps for Michael:** follow the hard rule in his global CLAUDE.md. Give exact window, URL, labels,
  values and the expected result, and close any tabs you opened.
- **No paid APIs and no AI calls in GitHub Actions.**
- **Tests:** run `py -m unittest discover -s tests` before every push. Verify the site at phone width
  (375px, no horizontal scroll).
- **Windows quirks:** run Python as `py`. Set `PYTHONIOENCODING=utf-8` for console output. Keep LF line
  endings.

## Hand-off practice
- **One intake chat.** Michael drops ideas, tips and requests into the main Sports HQ chat. That chat routes each one:
  - to the feature session that owns it, by message;
  - into IDEAS.md or ROADMAP.md;
  - or into a proposed new session.
  Away from the laptop, he can add to IDEAS.md from his phone.
- **Parallel sessions:** each works in its own worktree and branch, then merges `main` in and pushes to `main`.
- Start a **new session per big feature** (e.g. "build trade tools"). Open it in C:\Claude\sports-hq and say:
  "read ROADMAP.md and build item N". The repo, README, this file and IDEAS.md carry everything needed. A
  long chat isn't needed and gets summarized anyway.
- At the end of each feature: update the status table and "Next up", commit, and note anything
  non-obvious under "Lessons" below.

## Lessons (non-obvious things learned the hard way)
- **GitHub drops many scheduled runs,** so one run loops through game-day windows (run.yml). Daily jobs
  use "first run after X o'clock" anchors, not exact crons.
- **Bash cache key:** hours 08 and 09 need `10#` or bash reads them as octal and crashes.
- **Yahoo:** blocked unapproved apps in July 2026. Read-only access is pending; the roster comes from the
  laptop sync until then.
- **ESPN NBA:** scoring periods are days, and matchups run Monday to Sunday.
- **ESPN private leagues:** return 401 without cookies. The laptop snapshot (`shq/save_espn.py`) covers them.
- **Laptop sync timing:** runs at 7:30am so the 8am digest reads that morning's rosters.
- **Browsers:** the Claude app's built-in browser loses sign-ins when the app restarts; use Chrome.
- **ESPN NBA categories:** `mMatchup` already carries each side's `cumulativeScore.scoreByStat` (no extra view
  needed), including FGM/FGA/FTM/FTA for the percentage cats. `settings.scheduleSettings.matchupPeriods` maps
  matchup periods to matchup periods, not to scoring days. Player `stats` ids: `00<season>` = this season's
  actuals, `10<season>` = ESPN's season projection, each with per-game `averageStats` (stat 42 = games played).
- **Guillotine model** (`shq/guillotine.py`) assumes every team plays its best lineup; started games are locked
  in place and final games use real points, so odds move live on Sundays. Rival prices use each rival's boldest
  past bid share (floor 25%), scaled by need and player quality.
- **Sleeper beta Chop menu** (checked 2026-10-28): `https://sleeper.com/beta/leagues/<league_id>/matchup` (the old
  `sleeper.com/leagues/<id>` URL redirects there when signed in). It shows per-team "% safe" and chop rank, a
  Graveyard of eliminated teams (week, FAAB left, points), and in the chat each waiver run's winning bids with
  the number of bids. **No chop endpoint:** "% safe" is computed in the browser from public rosters and matchups
  (team score normal with variance (points − proj)² / (1 + 10·(1 − points/proj)), so about 30% of the projection
  before kickoff), so the cloud already has everything. Its odds are flatter than ours (team SD ~36 vs ~27).
  Public `GET /v1/league/<id>/transactions/<week>` lists every processed claim, won or lost, with its
  `waiver_bid`, which is what the bid model learns from. Only pending claims need the signed-in browser
  (`shq/guillotine_bids.py`).
