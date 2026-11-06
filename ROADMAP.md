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
that need a sign-in. It is an ongoing project, improved through the nightly model-health job and improvement pass
(IMPROVEMENTS.md, approved by Michael), the monthly review and ideas he adds.

## Where things stand (update this table when something ships)
| Area | Status |
|---|---|
| Lineup tabs, 8 leagues (NFL + NBA) | live |
| Injury watch + exact-swap pushes (2h before lock) | live |
| Weekly tab (Tue 7am): start/sit + top FA adds | live |
| Today tab + 8am digest push | live 2026-10-28 |
| Weekend wrap-up: phone-sized PDF + web page per week, ntfy push opens the PDF (`/wrapups/`, header link) | live 2026-10-31 (`shq/wrapup.py` builds, `shq/wrapup_render.py` draws with reportlab). Sunday edition once every Sunday game is final (Monday players listed as still to play), final from Tue 8am CT, redrawn quietly when the Tue 8pm picks postmortem lands. Per league: result, standing and movement, bench points left, boom/bust vs projection, cited injuries, next week from the What to do card; pools card graded on ESPN scores (entries after the postmortem), War Room v2 bid picture, model and stale-line hits. First issue: NFL week 7 (private ESPN leagues had no scores yet; the laptop snapshot carries `results` + `box` from Oct 31) |
| Picks (BTO, CFP, Yahoo pick'em) | live (laptop, Tue–Sat) |
| Picks as the only pool picker: saved-picks check, Decisions log, second opinion, standalone push | live for the Wed Nov 4 draft (`picks/pp/push.py`, `picks/pp/checks.py`, RUNBOOK "Every card run"); the cloud "Football pools picks" task retires after the Nov 4–7 side-by-side |
| Yahoo: season value of taking the other side, upset watch, rebuilt-roster flag | live 2026-10-31 (`picks/pp/yahoo_value.py`, `pool_profile.py`; profile refreshed at the Tue postmortem) |
| Picks stale-line scanner + fresh market lines | live 2026-10-31 (`picks/pp/lines.py`): run.yml compares open BTO/CFP pool lines with ESPN's current line Wed–Sat every 2h (30 min Sat 6–11am CT), pushes once per game at 1.5+ pts or a key number, gap table on the Picks page; cards center on ESPN's line at build time. Backtest: stale 1.5+ openers covered 61% (CFB n=194, NFL n=64); MODEL_W stays 0.1 (walk-forward picks 0) |
| Picks per-game breakdowns (tap any game) | live 2026-10-31 (`picks/pp/explain.py`): every BTO/CFP/Yahoo card row and a new "All pool games" table open a panel with kickoff/TV, pool line vs market vs opener (movement, stale gap), stats model vs market and the ATS card center, cover % at each pool line, an opponent-adjusted matchup table with FBS ranks, strengths/weaknesses (rule 4: a weakness counts only if the opponent can exploit it), key edges, dated and sourced injuries/news, weather and pool context. NFL: power ratings, scores, ESPN injury report. Templates only, no AI; one extra cached CFBD call (havoc). `py -m pp.cards --render-only` redraws them around the posted cards |
| Picks analytics sources (nflverse EPA, SP+) | live 2026-10-31 (`picks/pp/nflverse.py`, `docs/picks/method/sources.md`): NFL panels show opponent-adjusted EPA/play, success rate, pass/rush EPA, explosive plays, early-down pass rate, PROE, CPOE and giveaways (ranks of 32) from nflverse play-by-play; college panels add current SP+, talent, line yards and standard-down SR; `data/cards.json` carries a `game_stats` dict per game. Backtest 2023-26 (n=860): stats lost to the closing line every season, so NFL MODEL_W 0.1 → 0 (cards = market + research); college model unchanged |
| War Room copy + pinned header links | live |
| War Room v2 in the repo (`warroom/`, `/war-room-v2/` + `bids.json`, own workflow) | live 2026-10-31, side-by-side with the old copy; cloud write-up drafted (`ops/tasks/guillotine-strategy-v2.md`) |
| League tabs as action pages (matchup, fixes, moves, adds, guillotine standing, FAAB) | live 2026-10-28 (`shq/advice.py`) |
| Waiver adds on rest-of-season value, with who to drop + FAAB bid range (NFL) | live 2026-10-28 (`shq/waivers.py`) |
| Trade finder + up to 3 offers per football league (FantasyCalc values) | live 2026-10-28 (`shq/trades.py`); Stempak/Bro-vid19 fill in after the next laptop ESPN sync |
| NBA player values (both basketball leagues) | live 2026-11-05 (`shq/nba_values.py`, Q-026): every player in the ESPN pool, rostered or free agent, gets a value per game in the league's own categories (z-scores against the top teams × roster spots; ratio cats weighted by attempts), a rank, and a this-week value (above a waiver-level player × games left, 0 while out). This season's averages from 5 games, ESPN's projection before. On every NBA roster row and in `docs/data/players.json` |
| Players page for both NBA leagues (`/players/`) | live 2026-11-05 (`docs/players/index.html`, Q-027): sortable, filterable table of `docs/data/players.json` (value, this week, games this week and next with back-to-backs, minutes and the radar's last-3-games change, each category's per-game number shaded by its value, % rostered, owner). Filters: available/mine/other teams, position, health, rising/falling minutes (±5, the radar's threshold), games this week/next, "Helps in" categories (keeps players who help the chosen categories on balance, sorted by that fit). Phone: rank, name with a category heat strip, value, this week, games; tap a row for the full line. Filters are kept per device |
| NBA pickups as swaps | live 2026-11-05 (`shq/nba_swaps.py`, Q-028): up to 3 "Drop X, add Y: +N this week (helps …)" lines per basketball league in What to do and the Weekly tab, replacing the % owned list. Gain = (need-weighted value per game − a waiver-level player's) × games this week (next week once the week is over); close categories weigh 1.5, safe or lost ones 0.5, rescaled to average 1. Guards: +3 minimum gain, the add may give up at most 1 value per game for the season, no IR-slot drops, no out adds; dynasty keeps players 40%+ rostered on ESPN or under 24 (`shq/nba_ages.py`, ESPN team rosters, cached a day). A player with no NBA team is flagged as a dead spot and goes first |
| Laptop starts the GitHub jobs on time (Q-014 / Q-029) | live 2026-11-05: Windows Task Scheduler (user level, `\SportsHQ\`) runs `ops/kick.ps1` → `gh workflow run run.yml` 7:02am-11:02pm CT hourly (skipped when `status.json` was committed in the last 20 min) and `model-health.yml` 2:55am; log `%LOCALAPPDATA%\sports-hq-kick.log`. `run.yml`: own concurrency group per dispatch; a run that finds another going 10+ min does one pass; digest built once (`run.digest_due` reads origin/main) and pushed once a day. Commands and removal: `ops/designs/Q-014.md` |
| NBA games grid and streaming plan | live 2026-11-05 (`shq/nba_games.py`, Q-031): "Games & streamers" on both basketball tabs: games per NBA team for the rest of this week and all of next week, grouped by count, back-to-backs marked ²; my games left vs my opponent's (best lineup each day) and my games next week (capped by starting spots); top 3 streamers = free agents with the highest need-weighted value × games this week (next week once it's over), with their game days |
| NBA daily lineup push | live 2026-11-05 (`shq/nba_lineup.py`, Q-032): today's moves on both basketball tabs ("Lineup moves") and one push a day for both leagues, sent on the first run from 3h before the earliest affected tip-off, only when a starter has no game / is out / the slot is empty and a bench player who plays today fits the slot, or a playing bench player beats a playing starter by 1+ value per game. Out starters in it aren't pushed again by the injury watch; the 8am digest lists NBA lineup fixes without pushing them; the digest's bench pick uses category value |
| No "proj 0.0" in the category leagues | live 2026-11-05 (Q-033): NBA roster rows show the value rank (`#33`, value per game, this week, source) instead of points; the tile and league page show the category outlook ("cats now · on course"), or "Category outlook fills in with this week's matchup data" before the table exists, never "0.0 projected"; `view()` writes no team projection for NBA; injury-watch swaps, the digest's bench pick and the best free agent rank NBA players by category value and say "value +1.9/g, #33" instead of "0.0 proj" (`swap.strength`, `swap.strength_text`); Game day (layout D) shows the rank |
| NBA trade checker | live 2026-11-05 (`shq/nba_trade.py` + the Players page's "⇄ Trade check", Q-034): pick players to give and get; verdict on value per game above a waiver-level player (a player below that counts 0, so 3-for-1s are fair), fit (extra weight on my bottom-third categories by team profile, less on my top third), per-category change with my rank; 3-Ball adds a rough age curve (×1.5 at 20 down to ×0.4 at 34+, prospect bonus under 23) and decides the verdict on it. The page's JavaScript mirrors `nba_trade.trade()`, which is tested |
| Guillotine survival odds + FAAB bid guidance on the tab | live 2026-10-28 (`shq/guillotine.py`; push when cut risk > 20%) |
| NBA category matchup (per-category totals, win/lose/close, what to chase, category FA adds) | live 2026-10-28 (`shq/categories.py`; Ball is Life fills in from the next laptop sync) |
| NBA trend radar (Trend radar section on both basketball tabs, Today digest lines, ntfy push) | live 2026-11-03 (`shq/radar.py`): one ESPN fantasy read gives every player's last 20 game logs. It flags free agents and my bench whose last-3-game minutes, usage % (computed from ESPN box scores) or starts jumped against their earlier games, ties each jump to a key teammate's cited ESPN injury, lists my players losing minutes, and shows who absorbs each injured starter's minutes (with/without splits). Free agents are ranked by fit in the categories I'm losing or that are close (`categories.build`) times games left, with back-to-backs and next week's games. Push: at most one a day per league (7am–9pm CT) for a riser under 30% owned whose role jumped and who helps a losing/close category, each player once per matchup week. `state/nba_owned.json` keeps a daily % rostered reading. Backtest (`py -m shq.radar_backtest --write`, `reviews/2026-11-03-nba-radar-backtest.md`): roles held 5 of 5 flagged free agents (11 of 15 players overall), and flagged players out-produced the site's old suggestions (−1.15 vs −2.47 z per game). No 3-Ball team added any of them, so there was no waiver race to win yet; small sample |
| 3-Ball dynasty assets (picks, minors) on both 3-Ball tabs | live 2026-10-31 (`shq/dynasty.py`): only my holdings are public (`state/dynasty_assets.json`, from `py -m shq.dynasty --export`); the full league sheet copy stays on the laptop |
| ESPN IR-slot check (a non-Out player in IR blocks adds/drops) | live 2026-10-30 (urgent in football) |
| Fantasy Command Center (older claude.ai dashboard) | folded in 2026-10-30; retired |
| Kosmonauts FA adds | live 2026-10-28 (laptop sync reads Yahoo's top 15 available per position; `shq/save_roster.py`) |
| Dashboard main page = layout A (Scoreboard tiles) + ▦ layout menu to switch to B Command center, C Deck, D Game day | live 2026-10-31 (Michael picked A). `docs/index.html` is A; B/C/D in `docs/lab/<letter>/`; shared `docs/lib/core.js` + `core.css`; old list view (`app.js`, `style.css`) removed |
| Feedback buttons (👍/👎 per tile, 💬 Feedback) → FEEDBACK.md | live 2026-10-31: a pre-filled GitHub issue, logged by `.github/workflows/feedback.yml` (`shq/feedback.py`), works without claude.ai |
| Continuous improvement: nightly model health (`model-health.yml`, `shq/health.py` → `docs/data/health.json`), improvement queue (`IMPROVEMENTS.md`), nightly AI pass | health job live 2026-11-03; queue seeded (13 items); nightly pass task created 2026-11-03 by Claude Ops, first run Wed Nov 4 (prompt `ops/tasks/nightly-improvement-pass.md`); approval channel waits on Michael (`ops/approvals.md`); site scorecard is Q-013 |
| Baseball | Feb 2027 (task `sports-hq-baseball-kickoff`) |
| Older claude.ai routines (auto-swaps, bids, helpers) | Michael to decide: keep, merge or retire (IDEAS.md) |

## Next up, in order
1. Value 3-Ball draft picks in trade ideas (FantasyCalc values picks too).
2. NBA trade ideas (offers to other teams) on top of the trade checker's values (Q-034), if wanted.
3. Kosmonauts trade ideas once the Yahoo API is approved (needs every team's roster).

## Site layout (`docs/lib/`, `docs/lab/`)
- **Shared core:** `docs/lib/core.js` loads the data (`SHQ.load`, the only place that fetches `docs/data/*.json`, so the
  planned passphrase lock only has to decrypt there), builds per-league summaries (`SHQ.leagues`), one ranked action list
  across leagues and pools (`SHQ.feed`), the full league page (`SHQ.detail`), the drawer, the theme toggle and the feedback
  sheet. `docs/lib/core.css` holds the look (dark default, light by system setting or the ◐ toggle, saved per device).
- **Main page = layout A (Scoreboard)**, `docs/index.html` (picked by Michael 2026-10-31). B Command center, C Deck and
  D Game day live in `docs/lab/b|c|d/index.html`; `docs/lab/a/` just forwards to `/`. Every page has the ▦ layout menu
  (`SHQ.LAYOUTS` in core.js: name, path, one-line description; the footer of the menu links War Room, Wrap-up and the lab).
  The menu only navigates; it does not change which page `/` opens.
- **Each layout** is its own CSS plus a small render function on top of the core, with `data-view="<letter>"` on `<body>`
  and `<div data-picker></div>` in the header. Keep header links to `picks/`, `war-room/` and `wrapups/`, and check
  375px (no sideways scroll) and 1440px in dark and light after any change. A feature added to `SHQ.detail` or `SHQ.feed`
  shows up in all four layouts at once.
- **New variant:** copy a lab layout to `docs/lab/<next letter>/`, set `data-layout`/`data-view`, add it to `SHQ.LAYOUTS` and
  a card on `docs/lab/index.html`. To make a different layout the main page, swap its page into `docs/index.html`
  (paths `../../` → `./`, keep the manifest and home-screen meta tags) and move A into `docs/lab/a/`.
- **Picks page and War Room** keep their own pages; restyle them into the shared shell only after the Picks per-game
  breakdown work (`picks/pp/cards.py` `render()`) has landed.
- **Data contract:** the lab only reads what the cloud job already writes. New fields go through `shq/` and its tests.

### Next layout ideas (continuous improvement; FEEDBACK.md and the monthly review re-rank these)
- Blend the winner with the best piece of another (e.g. A's tiles with B's inbox on the left).
- Live scores during games: actual points vs projection per league (needs a new cloud field from ESPN/Sleeper box scores).
- "Since you last looked": highlight new or changed actions (kept per device).
- Mark an action done / snooze it (kept per device) so the inbox empties as he works.
- Density toggle (comfortable / compact) and a bigger-text option.
- Team logos and player headshots (ESPN CDN), only if they stay fast on a phone.
- Projected-margin sparkline across the week per league.
- Picks page and War Room restyled into the shared shell and theme (after the Picks breakdown work lands).
- Passphrase lock (planned) plugs into `SHQ.load`.

## How trades and waiver adds work (`shq/values.py`, `shq/trades.py`, `shq/waivers.py`)
- **Values:** FantasyCalc's public API, matched per league (dynasty or redraft, 1QB or superflex, PPR,
  team count); cached in `.cache` for 6h like the Sleeper players dump. ESPN players map to Sleeper ids
  through FantasyCalc's espnId (Sleeper's DB lacks many), then by name/team.
- **Points per game:** Sleeper weekly projections for the next 4 weeks, scored with the league's
  settings (ESPN scoring is read from the league's scoringItems). Byes aren't counted as games.
- **Offers:** fair within 10% by value (in a two-player side the lesser player counts at 80%), my best
  lineup +0.5/gm or more, theirs +0.5/gm or more. Up to 3, the best straight 1-for-1 always included,
  no player in two offers. After the trade deadline the card says so.
- **Adds (position-aware since 2026-10-31):** an add is judged by my best lineup summed over the next 4 weeks,
  each week on that week's Sleeper projections (byes score 0), plus insurance for the top backups at each
  position (`waivers.INSURANCE`). A same-position swap needs a better score (70% ROS ppg + 30% this week +
  FantasyCalc nudge). A cross-position swap needs +2 lineup points over the window and can't leave RB/WR (or QB
  in superflex) without a backup (`waivers.floor`). Every line says what the move does: "starts at QB over X",
  "fills in at QB in week 11", or "better backup RB", and which depth spot the drop is ("your RB6"). Never
  dropped: lineup players, (dynasty) anyone worth 750+, or an add suggested above. K/DEF stream one of
  each, $0–1. FAAB range scales with the lineup gain.
- **Private ESPN leagues:** `LAPTOP_SNAPSHOT_JS` now saves every team's roster, scoring, trade deadline and
  FAAB. Old snapshots still work; trade ideas appear after the next laptop sync.

## Rules that must not break
- **The repo is public.** Never commit the ntfy topic, cookies, tokens or passwords.
  - Secrets live only in GitHub Secrets.
  - Laptop runs read the topic from `picks/.ntfy_topic` (gitignored).
- **Read-only on fantasy sites.** Never add, drop, trade or bid automatically. The only automatic action is
  a Yahoo lineup swap via the API, if write access ever exists. Everything else is a push saying exactly
  what to do.
- **Guillotine claims:** entered only from a list Michael approves in chat, then read back.
- **Git:** always merge, never rebase (`git pull --no-rebase --no-edit`); the repo has subtree merges.
- **Laptop tasks:** use Michael's Chrome through Claude in Chrome (`ops/BROWSER.md`), never the built-in
  browser. Never type passwords.
- **Manual steps for Michael:** follow the hard rule in his global CLAUDE.md. Give exact window, URL, labels,
  values and the expected result, and close any tabs you opened.
- **No paid APIs and no AI calls in GitHub Actions.**
- **Every injury call is cited.** A status that would bench someone (Out, Doubtful, IR…) only counts when
  ESPN's public injury report agrees, and for a one-game Out/Doubtful its dated note is from this NFL week
  (Tuesday on). Otherwise the player shows as Q, "unconfirmed", and nothing is benched, swapped or pushed on
  it (`status.confirm`). The ESPN note, its time and the player-card link go with every status line.
- **Tests:** run `py -m unittest discover -s tests` before every push. Verify the site at phone width
  (375px, no horizontal scroll) and desktop width (1440px), in dark and light.
- **Windows quirks:** run Python as `py`. Set `PYTHONIOENCODING=utf-8` for console output. Keep LF line
  endings.

## Hand-off practice
- **One intake chat.** Michael drops ideas, tips and requests, one or many at a time, into the Sports HQ intake chat.
  In the same turn, the intake chat routes each item and ends with a short "where each went" list:
  - **Quick** (a fix or answer a few tool calls settle): done right there.
  - **Belongs to a feature session that exists:** sent to that session by message.
  - **A new feature:** shown as a session card he starts with one click. If he says "start it", it starts right away.
  - **Later / someday:** appended to IDEAS.md (the monthly review ranks it).
  - **Needs his call:** one question at the end, never one per item.
  The intake chat reads IDEAS.md for anything he added from his phone (github.com, this repo, IDEAS.md, pencil icon).
- **Feedback from the site.** Every layout has 👍/👎 on its tiles and sections plus a 💬 Feedback button. Each opens a
  pre-filled GitHub issue (works on his phone at work; no claude.ai needed); `.github/workflows/feedback.yml` logs it as one
  line in FEEDBACK.md "Inbox" and closes the issue. The intake chat reads that Inbox at the start of each session and when
  he says "check feedback", routes each line like any other item, then moves it to "Handled" with where it went. The
  monthly review reads the whole file for patterns and recommends how to re-rank "Next layout ideas".
- **Starting a fresh intake chat:** when the current one has been summarized more than once or gets slow, open a new
  Code chat in C:\Claude\sports-hq and say: "This is the Sports HQ intake chat. Read ROADMAP.md, IDEAS.md,
  FEEDBACK.md and README.md, then route what I send." Sessions started from the old chat still report there; check them with the
  sessions list.
- **Parallel sessions:** each works in its own worktree and branch, then merges `main` in and pushes to `main`.
- Start a **new session per big feature** (e.g. "build trade tools"). Open it in C:\Claude\sports-hq and say:
  "read ROADMAP.md and build item N". The repo, README, this file and IDEAS.md carry everything needed. A
  long chat isn't needed and gets summarized anyway.
- At the end of each feature: update the status table and "Next up", commit, and note anything
  non-obvious under "Lessons" below.

## Lessons (non-obvious things learned the hard way)
- **GitHub drops many scheduled runs,** so one run loops through game-day windows (run.yml). Daily jobs
  use "first run after X o'clock" anchors, not exact crons. Since Nov 5 the laptop also starts runs on time (Q-029);
  a dispatch needs its own concurrency group, or a queued cron silently replaces it.
- **Bash cache key:** hours 08 and 09 need `10#` or bash reads them as octal and crashes.
- **Yahoo:** blocked unapproved apps in July 2026. Read-only access is pending; the roster comes from the
  laptop sync until then.
- **ESPN NBA:** scoring periods are days, and matchups run Monday to Sunday.
- **ESPN private leagues:** return 401 without cookies. The laptop snapshot (`shq/save_espn.py`) covers them.
- **Sleeper's injury_status lags.** It kept Jeremiyah Love "Out" Oct 26–28 from the prior week while
  ESPN had moved on, and the Tuesday Weekly tab froze that. ESPN's injury report
  (`site.api.espn.com/.../nfl/injuries`) lists ~800 players with a status, a dated Rotowire note and a
  player-card link; Sleeper's DB lacks ESPN ids for many rookies, so players are also matched by name + team.
  The Weekly tab's start/sit is now rebuilt every run.
- **3-Ball league sheet** isn't public (gviz CSV returns 401), so the cloud can't read it. The monthly review
  re-reads "Updated Draft Picks" (A1:J41) and "Minor League Spots & Transaction Log" (A1:J7) with the Sheets
  connector into `state/dynasty_sheet.json`, updates `picks_updated`/`minors_updated`/`read`, then runs
  `py -m shq.dynasty --export` and commits `state/dynasty_assets.json` (my holdings only). A pick cell
  is "<n> Rd" while its owner holds it, else the holder's name. **The copy is gitignored**: the sheet is the
  league's private data and this repo is public, so it lives only on the laptop.
- **ESPN injury-report notes are sometimes bare** ("questionable"); `run.better_news` swaps in the player's
  latest ESPN news headline for my players. Citations show the date, not a weekday.
- **Waiver adds were position-blind until Oct 31:** a QB was weighed against a WR by raw points ("add Jayden
  Daniels, drop Carnell Tate"). Counting every bench player as insurance then made spare QBs look valuable
  because QBs score more; only the top backups per position count now.
- **ESPN per-position scoring:** some leagues (Stempak) set a stat's `points` to 0 and put the value in
  `pointsOverrides` by position id (1 QB, 2 RB, 3 WR, 4 TE). Reading only `points` made Stempak's passing,
  receiving and TD stats worth 0. `values.espn_scoring` and the laptop snapshot JS now use the override.
- **Claude in Chrome cuts `javascript_tool` results at ~1,000 characters.** Yahoo reads go one position per
  call. The ESPN snapshot (~109 KB) is gzipped + base64'd in the page, read back with `get_page_text` in
  15,000-character pieces, and joined with hash checks by `py -m shq.save_espn --parts` (since 2026-10-30).
- **Pool lines aren't openers.** Week 9's BTO/CFP spreads sat ~0.35 pts from Saturday's line but ~1 pt from the opener, so
  the pools post after early movement and big stale gaps are rarer than open-vs-close history suggests. ESPN event ids are
  CFBD game ids, so ESPN odds drop straight into the cards' line table (`lines.overlay`).
- **Efficiency stats are already in the line.** nflverse EPA/success beat our scores-only NFL ratings as a forecast (RMSE 13.3 vs 13.6) but tilting toward either one lost to the closing line in every season 2023-26, and extra CFBD stats didn't help the college cards either. Use stats to explain games and apply rule 4; look for edges in stale pool lines, key numbers and late news. nflverse's `games.csv` has closing lines back to 1999 (free), so NFL ideas can be backtested over many seasons, not 7 weeks.
- **Source terms (checked 2026-10-31, `docs/picks/method/sources.md`):** ESPN's (Disney) terms bar automated access, and CFBD's bar republishing raw responses. `pp/publish.py` runs `git add -A` on `picks/`, which is how raw CFBD cache files reached this public repo; new ones are gitignored now, and the 17 already tracked still need untracking. On Windows, open files as UTF-8 explicitly: `Path.read_text()` defaults to cp1252 and a failed `write_text` truncates the file.
- **nflverse kickoff times lag schedule changes.** On Oct 31 it still had LV @ SF at 4:05 ET after the game moved to 4:25 on FOX. Final scores matched ESPN on every 2026 game, so Picks reads NFL results from nflverse with ESPN as the backup. Kickoffs, live state and injuries stay on ESPN (`docs/picks/method/sources.md`, "Less ESPN").
- **NBA stat sources (tested from GitHub Actions 2026-11-03):** stats.nba.com times out (from the laptop too), cdn.nba.com and
  Basketball-Reference return 403, and pbpstats' stat endpoints are slow or 502 (only `get-games`/`get-totals` answered). official.nba.com's
  firewall turns away non-browser clients, and posing as a browser was refused by the safety check, so the official injury PDFs aren't
  read; ESPN's dated injury report is the citation. ESPN fantasy's `kona_player_info` with
  `filterStatsForTopScoringPeriodIds: {value: 20}` returns each player's last 20 game logs (`statSplitTypeId` 5, any season, so filter
  `seasonId`; stat 40 = minutes, 41 = started), season averages and `ownership.percentChange` for ~1,000 players in one ~8 MB call
  (0.3 s from Actions). That is enough to compute usage % and with/without-teammate splits. ESPN-wide ownership history isn't available
  anywhere free, so the radar records its own daily reading.
- **Laptop sync timing:** runs at 7:30am so the 8am digest reads that morning's rosters.
- **Wrap-up and the laptop-read leagues:** the Sunday edition reads Stempak, Bro-vid19 and Ball is Life from the 4:30pm
  snapshot, so their late games count as still to play (a game is over 3h30m after kickoff, `wrapup.GAME_LENGTH`); the
  Tuesday final has them complete from the 7:30am read (the snapshot keeps last week's box score as well as this week's).
  Kosmonauts has no score feed until Yahoo approves the API: the wrap-up scores my saved lineup with Sleeper's stats and
  league scoring, and shows no W/L.
- **Browsers:** the Claude app's built-in browser loses sign-ins when the app restarts; use Chrome.
- **FantasyCalc:** the redraft list only has ~200 players; the dynasty list (same settings) carries a
  `redraftValue` for ~420, so `values.py` always fetches the dynasty list and picks the field.
- **Sleeper projections** for a week skip players on bye, so the Sleeper free-agent pool also takes anyone
  projected in the next 4 weeks.
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
