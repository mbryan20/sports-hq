# Improvement queue

Every improvement that has evidence behind it, waiting for Michael's OK. Nothing here is built until its **Decision**
says approved. IDEAS.md stays the place for raw ideas; an idea moves here once someone has evidence for it.

- **Who adds items:** the nightly improvement pass (`ops/tasks/nightly-improvement-pass.md`) from `docs/data/health.json`
  (the nightly model-health job, `shq/health.py`), FEEDBACK.md, IDEAS.md and the monthly review; any session that finds
  something (one item, same format).
- **Who decides:** Michael. Until an approval channel is chosen (`ops/approvals.md`), say "approve Q-003" or "hold Q-005"
  in the Sports HQ intake chat, or edit the Decision line on github.com.
- **Who builds:** a session started for the item once it is approved. When it ships, set Status to `shipped` with the commit;
  the nightly pass sets `verified` once health.json shows the expected change (or `reopened` if it doesn't).

**Status:** `proposed` (evidence, no design yet) → `designed` (the nightly pass drafted a design) → `approved` / `held` /
`rejected` (Michael) → `building` → `shipped` → `verified` / `reopened`. `measuring` = the health job is collecting the
evidence; decide when it reports.

**Fields** (one block per item, keep the labels exactly; the nightly pass and the site parse them):
`### Q-NNN · title`, then Status, Area, Rank, Added, Evidence, Expected impact, Effort (S/M/L), Risk (Low/Med/High),
Measure (the health.json check that should move), Design, Decision.

## Open

### Q-026 · B1: NBA players had no value (every one showed "proj 0.0")
- **Status:** shipped (70ff3ff)
- **Area:** `shq/nba_values.py` (new), `shq/radar.py` `fetch_pool`/`compact` (adds ESPN's season projection and games played),
  `shq/advice.py` `player_values`, `shq/run.py` (writes `docs/data/players.json`), `docs/lib/core.js` `prow`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal `sports-hq-improvements-2026-11-05.md` (item B1)
- **Evidence:** Nov 5 6am: every NBA player showed "proj 0.0" (category leagues have no points); ROADMAP listed "NBA trade
  values and ROS waiver ranking: not covered"; pickups were ranked by % owned.
- **Expected impact:** a real number and rank on every NBA player, rostered or free agent, in each league's own categories,
  per game and for this week.
- **Effort:** M
- **Risk:** Low
- **Measure:** — (one-off; later: does the value rank of players added beat the old % owned picks, like the radar backtest)
- **Design:** value per game = the league's own scoring categories (read from the snapshot; both leagues are 8-cat today) as
  z-scores against the top N players, N = teams × non-IR roster spots (170 in 3-Ball, 168 in Ball is Life); two passes (all
  players, then the top N of pass one). Ratio cats count made above that group's rate times attempts; reversed cats (TO)
  count negative. This week = (value − the value of player N, a waiver-level player) × games left this matchup not yet
  tipped, 0 while out on ESPN's injury report. Stats: this season's per-game averages once a player has 5 games, ESPN's
  season projection before that; each player carries `src` and games played, and the roster rows say "8 g" or "ESPN proj".
  One ESPN read covers both leagues (the radar's ~1,000-player pool, now also asking for `10<season>`); Ball is Life's
  owners come from its laptop snapshot. Choices: no blend of projection and season stats (the brief said 5 games); early in
  the season that makes slow starters rank low (Mikal Bridges #261 on 6.2 pts, 33% FG through 8 games). If that looks
  wrong in a few weeks, blend toward the projection by games played. `players.json` is written one player per line so the
  10-minute data commits stay small diffs (~185 KB, top 300 per league plus everyone rostered).
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-027 · B2: no way to sift NBA players inside HQ (still done on FantasyPros)
- **Status:** shipped (02451dc)
- **Area:** `docs/players/index.html` (new), `docs/lib/core.js` (`SHQ.loadFile`, Players links in the ▦ menu and on NBA league
  pages), header links in `docs/index.html` and `docs/lab/b|c|d/`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B2)
- **Evidence:** Nov 5: Michael still sifts players on FantasyPros; HQ had no player list to sort or filter.
- **Expected impact:** the FantasyPros sift inside HQ for both basketball leagues.
- **Effort:** M
- **Risk:** Low
- **Measure:** — (one-off; Michael's feedback on the page)
- **Design:** one static page over `docs/data/players.json` (Q-026), loaded only on this page through `SHQ.loadFile` so the
  dashboard stays light. League tabs; filters: available / mine / other teams, position, health (healthy / injured), minutes
  rising or falling (last 3 games vs before, ±5, the radar's threshold), games this week ≥ and next week ≥, and "Helps in"
  category buttons. Choices: "Helps in" keeps players whose summed value in the chosen categories is above zero and sorts by
  that (a "Fit" column); requiring +0.3 in every chosen category left 0 free agents for AST + 3PM in Ball is Life. Every
  column sorts. Desktop shows each category's per-game number shaded by its value; on a phone (≤760px) the table drops to
  rank, name (with a category heat strip and the minutes arrow), value, this week and games, and a tap opens the full line
  with an ESPN game-log link. The header "Players" pill is hidden at phone width (it wrapped the header to two rows); phones
  reach the page from the ▦ menu or the league page's Players button. Filters are kept per device (localStorage).
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-028 · B3: NBA pickups were ranked by % owned, not by what they do for my categories
- **Status:** shipped (168a299)
- **Area:** `shq/nba_swaps.py` (new), `shq/nba_ages.py` (new), `shq/nba_values.py` (age), `shq/advice.py` `adds`, `shq/run.py`
  `nba_weekly_section`, `docs/players/index.html` (age in the detail row)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B3)
- **Evidence:** Nov 5: "Collin Gillespie (PG, PHX): 2 games left this week, 38% owned" style lines, sorted by games then
  % owned; Kevin Porter Jr. (no NBA team) sat on the 3-Ball bench unflagged.
- **Expected impact:** 1-3 exact moves per basketball league that help this week's categories without hurting the season.
- **Effort:** S
- **Risk:** Low (ideas only)
- **Measure:** — (one-off; could join the radar backtest later: did the suggested adds out-produce the drops?)
- **Design:** a player's this-week worth = (need-weighted value per game − the waiver-level value) × games left, the same
  "Wk" as the Players page with each category weighted by this week's outlook (close 1.5, lose 0.5, win 0.5, rescaled to
  average 1; all 1 with no live matchup). Gain = add's worth − drop's. Choices: minimum gain +3 (at +2 Ball is Life got
  near-even churn swaps, Draymond Green for Robert Williams III); the add may give up at most 1 value per game for the
  rest of the season; no drops from IR slots (they free no spot) and no out adds; greedy pairing, each player once. A
  player with no NBA team is a dead spot: listed first and always droppable. Dynasty (3-Ball): never drops anyone 40%+
  rostered ESPN-wide or under 24. ESPN's fantasy pool has no ages, so `shq/nba_ages.py` reads the 30 public ESPN team
  rosters (same player ids) once a day. On live data Nov 5: 3-Ball "Drop Kevin Porter Jr. (no NBA team, a dead roster
  spot), add De'Anthony Melton: +3.4 this week (helps STL, 3PM)" and "Drop De'Andre Hunter, add Collin Gillespie: +10.1";
  Kingston Flemings (rookie) is no longer offered as a drop. The Weekly tab uses the same lines.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-029 · R1: the laptop starts the GitHub jobs on time (builds Q-014)
- **Status:** shipped (d2bfcb7)
- **Area:** `ops/kick.ps1` (new), Windows Task Scheduler `\SportsHQ\Kick run` and `\SportsHQ\Kick model health` (user level),
  `.github/workflows/run.yml` (concurrency, one-pass rule, `actions: read`), `shq/run.py` (`origin_digest`, `digest_due`,
  digest `push_once`), `ops/designs/Q-014.md` ("As built", exact commands and removal)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item R1); evidence in Q-014
- **Evidence:** Q-014: the 8am digest built at 11:06am Nov 4; model health ran 7.5 hours late; manual dispatches dropped.
  Nov 5 evening, while building this: a dispatch made at 5:48pm CT sat "pending" behind a game-day loop that started at
  2:29pm (the old single concurrency group).
- **Expected impact:** the digest out by about 8:05am CT and data at most about an hour old whenever the laptop is on.
- **Effort:** S
- **Risk:** Low (two loops at once could double a swap push in the same minute; a run only loops when no other run has
  been going 10+ minutes)
- **Measure:** — (one-off: every weekday a data commit 8:00-8:15am CT for two weeks; zero cancelled `workflow_dispatch` runs;
  `%LOCALAPPDATA%\sports-hq-kick.log` shows the kicks)
- **Design:** `ops/designs/Q-014.md`, "As built". Choices against the draft: Task Scheduler instead of a line in the Claude
  sync prompt (the proposal said "no Claude usage", and it works when a Claude task fails); kicks at 7:02 (Tuesday's 7am
  Weekly) and hourly from 8:02 (the digest needs 8:00 or later, so the draft's 7:35 would not have built it), skipped when
  `status.json` was committed in the last 20 minutes; a dispatched run still loops when no other run is looping, so a
  laptop kick covers a game night GitHub skipped; health kicked at 2:55am.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-030 · R2: a BTO bet on the Thursday game gets no final check before it locks
- **Status:** shipped (fd1551f); the scheduled task itself is created by the Claude Ops session from the prompt
- **Area:** `picks/pp/thu_check.py` (new), `ops/tasks/pool-picks-thu-bto-check.md` (new task prompt), `tests/test_thu_check.py`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item R2)
- **Evidence:** the BTO "final" card runs Thu 8pm, after the Thursday NFL game kicks off (7:15pm); BTO locks each game at
  kickoff (Nov 4: Michael's saved JAX bet locked Thu 7:15pm, `pp/push.py` `early_lock`). Nov 5 dry run on real data: saved
  bets (read Wed 9:20pm) differ from the draft card on all 5 games, JAX @ BAL locking 7:15pm.
- **Expected impact:** a push before the Thursday lock whenever the saved bets and the card disagree; silence otherwise.
- **Effort:** S
- **Risk:** Low (read-only; pushes only on a difference or an unreadable site)
- **Measure:** — (one-off)
- **Design:** the task runs Thu 4pm CT. `py -m pp.thu_check --needed` exits 3 when this week's BTO slate has no Thursday game
  still to play, so most weeks it stops before opening Chrome. Otherwise it reads the saved bets read-only (RUNBOOK
  "Every card run" A), writes them to a temp file outside the repo (no commit, so the main checkout stays clean for the
  8pm run), and `--saved <file> --push` compares them with `picks/data/published/<year>-wNN-bto.json` (the latest posted
  card: Wednesday's draft at 4pm). Choices: one "yours → card" line per game rather than `push.compare_ats`'s single
  package line (the brief asked for exact lines); the Thursday game's line first; wagers compared as numbers ("$1,660" =
  1660) and picks by team and line; an unreadable site still pushes a "check before <lock>" line.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-031 · B4: no games grid or streaming plan for the basketball leagues
- **Status:** shipped (c3b56e7)
- **Area:** `shq/nba_games.py` (new), `shq/advice.py` (`games` block), `docs/lib/core.js` (`gamesHTML`, "Games & streamers")
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B4)
- **Evidence:** the tabs showed games left only per player and in the category table; no team schedule view, no next week,
  no streaming plan (FantasyPros / Hashtag-style grids done by hand).
- **Expected impact:** a Monday plan (next week's 4-game teams and back-to-backs) and mid-week streamer picks in one place.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off)
- **Design:** from ESPN's pro schedule (`league.sched`): per team, games still to tip off for the rest of this matchup week
  and all of next week, grouped by count ("3 games: …"), back-to-backs marked ². My games left vs my opponent's come from
  the category table (best lineup each day); next week counts my roster's games capped by starting spots each day.
  Streamers: the 3 free agents with the highest need-weighted "Wk" (`nba_swaps.worth`, Q-028) this week (next week once
  this one has no games left), with their game days and the categories they help. Choices: grouped team lists instead
  of a 30-row × 14-day grid (fits a phone, reads in seconds); the section is collapsed by default with the streamer count
  on it. Nov 5 live: 3-Ball 29 games left vs 29, next week 52; 14 teams play 4 next week.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-032 · B5: no NBA lineup push before tip-off when a move is needed
- **Status:** shipped (3ae3a74)
- **Area:** `shq/nba_lineup.py` (new), `shq/run.py` (send before the injury watch), `shq/advice.py` `_moves` (NBA "Lineup
  moves"), `shq/digest.py` (`_fix` ranks by value; NBA lineup items no longer urgent)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B5)
- **Evidence:** the 8am digest flagged "no game today → start X" for NBA, but nothing pushed later in the day when injury
  news lands; the NBA tabs had no lineup moves at all (`_moves` returned [] for NBA); bench picks were by points (0.0).
- **Expected impact:** one phone push on days a basketball lineup change is needed, before it locks; nothing on other days.
- **Effort:** S
- **Risk:** Low (read-only; at most one push a day)
- **Measure:** — (one-off: pushes per week, and days a move was needed with no push)
- **Design:** moves for today: (1) a starter with no game, out (ESPN-confirmed status) or an empty slot, filled by the best
  bench player who plays today and fits the slot (`swap.eligible`), by category value; (2) a playing bench player who beats
  a playing starter by 1+ value per game. Push: one a day for both leagues (`push_once("nba-lineup:<date>")`), on the first
  run within 3 hours of the earliest affected tip-off (the hourly laptop kick and the 2h watch loop both land there), and
  only with a move. Choices: the 8am digest still lists NBA lineup fixes but no longer pushes them (one lineup push a day, and
  the pre-tip one sees the latest injury news); an out starter in the push is marked as sent for the injury watch, so it
  isn't pushed twice. Nov 5 live: no moves (no bench player had a game that night).
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-022 · Old claude.ai helpers still give lineup and bid advice (and auto-swap) alongside Sports HQ
- **Status:** proposed
- **Area:** outside the repo: claude.ai routines "Fantasy football helper", "Fantasy basketball helper", "Guillotine strategy
  review", "Football pools picks"; Sports HQ rules (ROADMAP "Rules that must not break", `status.confirm`)
- **Rank:** 1
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #2 and IDEAS.md "Open decisions"
- **Evidence:** `reviews/2026-11.md` (Coverage vs goals): the football helper (Sun/Mon/Tue/Thu/Sat, 4×/day) and basketball
  helper (9am/5pm) still auto-swap lineups through Chrome, outside `status.confirm`; "Guillotine strategy review" (daily
  6:19am) runs alongside War Room v2; "Football pools picks" runs alongside Sports HQ Picks. Two systems give lineup and bid
  advice, with possible duplicate pushes. Open in IDEAS.md since Oct 28. ROADMAP "Where things stand" (Nov 4): the cloud pools
  task retires after the Nov 4-7 side-by-side; the rest is "Michael to decide". The claude-audit plan (`plan.md` Phase 2
  "One owner per job") holds the proposed owners; not yet executed per its `changes.md`. Nov 5: still no Decision.
- **Expected impact:** one source of lineup and bid advice; no auto-swap that skips Sports HQ's injury confirmation; fewer pushes.
- **Effort:** S (a decision; the routine changes are a claude-audit batch)
- **Risk:** Med (turning off auto-swaps means Sports HQ's pushes are the only safety net for inactive starters; see Q-016)
- **Measure:** — (one-off: one owner per job in the claude-audit plan)
- **Design:** claude-audit `plan.md` Phase 2 (a decision, outside this repo)
- **Decision:** —

### Q-003 · Price ladder isn't split by position or season stage
- **Status:** designed
- **Area:** War Room v2 (`warroom/build.py` `ladder`, `model.js` `winChance`)
- **Rank:** 2
- **Added:** 2026-11-03 (Nov 3 slider audit); evidence from the first model-health run the same day
- **Evidence:** The ladder splits past claims only by estimate size ($10+ vs under). Overall it is well calibrated
  (leave one waiver run out, 165 claims: a bid at its 50% price would have won 55%, at its 80% price 82%), but not by position:
  RBs won only 37% at the 50% price and 67% at the 80% price (n=30; raw estimate missed by $20.4), while kickers won 94% and
  100% (n=16: we'd overpay) and DEF 95% at the 80% price (n=22). Weeks 1-3 vs 4-7: 77% vs 86% at the 80% price; estimate miss
  $13.1 vs $6.6. Source: health.json `sections.warroom.details.prices.by`. Per-position samples are 16-54 claims.
  Nov 4 health run (week 8 added, n=187): RB got worse, 34% at the 50% price and 63% at the 80% price (n=35, estimate miss
  $19.1); K 90% at the 50% price (n=20); DEF 96% at the 80% price (n=24); WR 75% at the 80% price (n=61). Legs 1-4 vs 5-8:
  80% vs 81% at the 80% price, estimate miss $12.5 vs $5.6, so the season-stage gap is now in the estimate, not the coverage.
  Overall still on target (`wr.ladder_cov50` 0.56, `wr.ladder_cov80` 0.81).
- **Expected impact:** RB claims (the most expensive position) won at the stated odds instead of lost; no overbidding on K/DEF.
- **Effort:** S
- **Risk:** Low-Med (splits get thin: keep the "at least 12 claims or merge" rule; test leave-one-run-out before shipping)
- **Measure:** `wr.ladder_cov50`, `wr.ladder_cov80` and their `by` splits (RB at 80% should reach about 0.8)
- **Design:** `ops/designs/Q-003.md`
- **Decision:** —

### Q-020 · Laptop jobs that fail still show "succeeded"
- **Status:** designed
- **Area:** laptop task prompts (daily sync, picks, guillotine checks), `shq/run.py` `job_health`, `docs/lib/core.js` `footHTML`
- **Rank:** 3
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #9 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Freshness): 4 of 17 laptop daily syncs did nothing but are marked "succeeded" (Oct 25 and
  Oct 30: Chrome not connected; Oct 26 and Oct 28 7:30am: signed out of the built-in browser). The site only sees the last
  delivery (`job_health`, `shq/run.py:201`) and greys a job after 30 hours (`core.js:283`), with no reason. Still open Nov 4:
  no `FAILED:` line in any `ops/tasks/*.md` and no laptop result file in `state/`. The claude-audit plan (`plan.md` Phase 3 #3)
  covers the prompt half.
- **Expected impact:** a failed morning sync is visible (and pushed) within one cloud pass, with its reason, instead of a stale
  roster being used for lineups until the next day's alert.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off: 2 weeks with no "succeeded" run that delivered nothing)
- **Design:** `ops/designs/Q-020.md`
- **Decision:** —

### Q-015 · No record of which pushes went out
- **Status:** designed
- **Area:** `shq/notify.py` `push`, `picks/pp/publish.py`, `shq/run.py` (status.json), `docs/lib/core.js` (footer)
- **Rank:** 4
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #4 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness): only `push_once` keys reach `state/alerts.json`, pruned after 21 days
  (`shq/notify.py:36`); digest, "lineup fixed" and weekly pushes use plain `push()` (`shq/run.py:120`, `:308`, `:321`) and leave
  no record, so the review couldn't say which injured starters were caught before lock in October. Still open Nov 4: no
  `state/pushes.json`, no "pushes" reference in `shq/` or `docs/`.
- **Expected impact:** "did we catch it before lock?" becomes answerable; a "Recent alerts" list on the site.
- **Effort:** S
- **Risk:** Low (the test must prove the ntfy topic never lands in the log; the repo is public)
- **Measure:** — (one-off: every `state/alerts.json` key from a week has a log entry)
- **Design:** `ops/designs/Q-015.md`
- **Decision:** —

### Q-014 · Morning runs depend on GitHub's late crons, and manual dispatches get dropped
- **Status:** shipped (d2bfcb7, built as Q-029)
- **Area:** `.github/workflows/run.yml` (concurrency, lines 46-48), the 7:30am laptop daily sync prompt
- **Rank:** 5
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #3 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Reliability): 26 "cancelled" Sports HQ runs never started because `concurrency:
  cancel-in-progress: false` keeps one waiting run, and 7 manual dispatches were dropped (Oct 25, 28, 30). On 3 of 8 weekday
  mornings no run fired between 8am and late morning; Mon Oct 26's 6h22m gap meant no 8am digest. Still open Nov 4: run.yml
  has the same single concurrency group, and no `ops/tasks/*.md` ends with `gh workflow run run.yml`. Same pattern tonight:
  `model-health.yml`'s 2:50am CT cron (`50 8 * * *`) had not run by 3:53am CT; its only run ever is the Nov 3 manual dispatch.
  Nov 5: it happened again on Wed Nov 4. No Sports HQ run between 2:59am and 11:06am CT (data commits 08:59Z, then 17:06Z:
  8h07m), so the 8am digest was about 3 hours late; Nov 3 00:00Z - Nov 5 10:00Z, 17 runs started (2 more cancelled) in 58
  hours. `model-health.yml`'s two slots (2:50am, 4:50am CT) ran at 10:37am and 12:15pm CT (7h47m and 7h25m late), and
  tonight's 2:50am slot again had not run by 3:53am CT.
- **Expected impact:** the 8am digest and Tuesday Weekly tab on time; a "force" button press never vanishes.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: data-commit gaps 8am-1pm on weekdays, and dropped dispatches, in the next monthly review)
- **Design:** `ops/designs/Q-014.md`
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-017 · Four git steps still rebase (rule: merge, never rebase)
- **Status:** designed
- **Area:** `.github/commit_data.sh`, `.github/workflows/picks-backup.yml`, `war-room-v2.yml`, `yahoo-reauth.yml`
- **Rank:** 6
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Rule breaks" #1 and "Ranked improvements" #6
- **Evidence:** The review listed 5 rebase spots. On Nov 4 `git grep rebase` still finds 4: `commit_data.sh:8`
  (`git pull -q --rebase -X theirs`), `picks-backup.yml:67` (`git pull --rebase`), `war-room-v2.yml:48` (`--rebase -X theirs`),
  `yahoo-reauth.yml:41` (`--rebase`). `picks/pp/publish.py:72` is fixed (`--no-rebase --no-edit`). `feedback.yml` and
  `model-health.yml` already merge. Nov 5: same 4 lines. Note for the build: under a merge `-X theirs` means the remote, so
  the like-for-like swap is `-X ours` (see the design).
- **Expected impact:** the repo follows its own rule; no rewritten history when the data loop and a session push at once.
- **Effort:** S
- **Risk:** Low (the data loops keep this pass's data on a conflict, as today, via `-X ours`)
- **Measure:** — (one-off: `git grep -- --rebase .github` finds nothing)
- **Design:** `ops/designs/Q-017.md`
- **Decision:** —

### Q-005 · Far-week Sleeper projections aren't backtested yet
- **Status:** measuring
- **Area:** War Room v2 (`model.py` `SD_GROWTH`, `model.js` `swing`)
- **Rank:** 7
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The 1.25-pt-per-week swing growth was measured on the old blend (misses 23 → 27 from 1 to 4 weeks ahead);
  Sleeper's stored past projections are its latest, not what it showed weeks earlier. The page has carried Sleeper's projection
  for every remaining week since Nov 3, so the health job now scores what the page showed 2, 3 and 4 weeks before each week.
  First numbers after week 10 (2 weeks ahead), week 11 (3), week 12 (4). Nov 4: `wr.swing_k2`-`k4` still waiting (n=0).
  Nov 5: still n=0; the first 2-weeks-ahead number arrives with the health run after week 10 ends (Tue Nov 17).
- **Expected impact:** the right rest-of-season uncertainty, which drives win odds and so every value.
- **Effort:** S (change `SD_GROWTH` once measured)
- **Risk:** Low
- **Measure:** `wr.swing_k2`, `wr.swing_k3`, `wr.swing_k4` vs `wr.swing`
- **Design:** —
- **Decision:** —

### Q-013 · Model health scorecard on the site
- **Status:** designed
- **Area:** site (`docs/lib/`, owned by the dashboard redesign session)
- **Rank:** 8
- **Added:** 2026-11-03
- **Evidence:** health.json is published at `/data/health.json` but nothing shows it. Michael only learned about the Nov 3
  War Room findings because he asked. Nov 5: `docs/lib/core.js` still loads only lineups, weekly, status, digest and
  pick_lines (`FILES`, line 9); the Nov 4 health run (13 ok, 1 weak, 5 waiting, 4 info) is visible nowhere on the site.
- **Expected impact:** a glance at which models are trustworthy this week (ok / watch / drift / weak per model, tap for the checks).
- **Effort:** S
- **Risk:** Low
- **Measure:** —
- **Design:** `ops/designs/Q-013.md`
- **Decision:** —

### Q-024 · The picks health check scores Yahoo straight-up picks against a spread break-even
- **Status:** proposed
- **Area:** `shq/health.py` `picks_health` and the `picks.card_ats` floor (line 71); `picks/data/postmortem/*.json`
- **Rank:** 9
- **Added:** 2026-11-05 by the nightly pass (own finding from health.json `sections.picks` and
  `picks/data/postmortem/2026-w09.json`)
- **Evidence:** `picks.card_ats` = 0.733 (22-8, n=30, baseline set Nov 4) is labelled "Posted card picks that won against the
  spread" and judged against a 52.4% floor (the -110 break-even). But 25 of the 30 graded picks are Yahoo pick'em winners,
  picked straight up (week 9: Yahoo 18-7, BTO 3-0, CFP 1-1; week 8's postmortem has no card picks). Straight-up winners are
  much easier to hit than spreads, so the check reads "ok" almost regardless of skill, and it is the Measure for Q-023. The
  same files grade the entries (32-27); in week 9 the entry differed from the card on 5 picks, card 5-0, entry 1-4
  (`differences` in the postmortem; the saved-picks check built Nov 4 now flags such differences before lock).
- **Expected impact:** a picks score that means something: BTO and CFP spread picks against 52.4%, Yahoo against the
  market favourite's straight-up record on the same games. Feeds Q-013's scorecard and Q-023's decision.
- **Effort:** S
- **Risk:** Low (health job only; the `picks.card_ats` baseline resets)
- **Measure:** — (one-off: separate spread and straight-up checks, each with its own floor)
- **Design:** —
- **Decision:** —

### Q-016 · "Likely out" news doesn't trigger a push while ESPN still says Questionable
- **Status:** proposed
- **Area:** injury watch (`shq/run.py` swap pushes, `status.confirm`), ROADMAP injury rule
- **Rank:** 10
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #5 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness, Sun Nov 1): Breece Hall (Guillotine FLEX) was still Questionable on ESPN while
  its 8:07am note said he "isn't expected to play"; the rule keeps him at Q, so no push. The site did show "Start J.K. Dobbins
  (7.7) over Breece Hall (0)" as a lineup move. Still open Nov 4: no "expected to play" / "likely out" handling in `shq/`.
  One case so far.
- **Expected impact:** in the guillotine league a likely zero is the alert that matters most; a labelled "likely out
  (unconfirmed)" swap push with the citation, when a starter's note says "not expected to play" / "won't play" or his
  projection drops to 0 within 90 minutes of lock.
- **Effort:** M
- **Risk:** Med (changes the injury rule; needs Michael's call; false alarms if the note is speculative)
- **Measure:** — (one-off, once Q-015's push log exists: likely-out pushes vs who actually played)
- **Design:** —
- **Decision:** —

### Q-012 · Cut odds are no better than a coin toss
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `simulate`), dashboard (`shq/guillotine.py`)
- **Rank:** 11
- **Added:** 2026-11-03 by the first model-health run
- **Evidence:** Rebuilding each of the 8 past weeks from Sleeper's projections, the team actually cut ranked 14th, 11th, 9th,
  1st, 1st, 11th, 1st and 10th by predicted risk (average 7th). At the measured 22-pt swing the cut odds score a log-loss of
  2.71 vs 2.66 for treating every team as equally likely (skill −1.7%); wider swings score better (27: +0.7%, 36: +2.3%), and
  the measured swing can't fix the ordering. The dashboard gave week 8's cut team 1.9% before kickoff (10th of 11). 8 cuts is
  a small sample, and the 22-pt swing is measured on the same weeks (in-sample). Nov 4: still the only health flag
  (`wr.cut_skill` −0.017, floor 0.0, n=8, status weak); week 9's cut (after Mon Nov 9's game) adds a 9th case.
  Nov 5: unchanged (same run); `gd.v2_skill` still waiting (n=0), `gd.dash_skill` −0.653 (n=1).
- **Expected impact:** cut risk and win odds drive every bid value. If cuts are mostly upsets, both models are too sure who is
  safe, so win-odds gains (and bids) are spread too wide between players. Better-calibrated odds = better $ values.
- **Effort:** S to test, M to change
- **Risk:** Med (moves every bid value)
- **Measure:** `wr.cut_skill`, `gd.v2_skill`, `gd.dash_skill`, `wr.best_sd` in health.json
- **Design:** —
- **Decision:** —

### Q-002 · Mid-week, War Room v2 ignores games already played
- **Status:** proposed
- **Area:** War Room v2 (`model.py` / `model.js` `proj`)
- **Rank:** 12
- **Added:** 2026-11-03 (warroom/README.md "Known limits")
- **Evidence:** From Thursday night to Monday, the coming week's projections ignore games already played; only the dashboard
  (`shq/guillotine.py`) locks started games and uses real points. v2's cut risks on Fri-Mon are pre-kickoff numbers.
- **Expected impact:** live cut risk on game days from the same model as the bids; a prerequisite for Q-011 (one model).
- **Effort:** M (lock started players at their real points, zero swing for finished games, like `guillotine.entry`)
- **Risk:** Low
- **Measure:** a Sunday-morning version of `gd.v2_skill` (add when built)
- **Design:** —
- **Decision:** —

### Q-018 · The What to do card contradicts itself
- **Status:** proposed
- **Area:** `shq/waivers.py` (drop protection), `shq/advice.py` (What to do card), IR-slot lines
- **Rank:** 13
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #7 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness, Nov 1, Guillotine page at 375px): Bids said "No free agent adds a point to your
  lineup" while Waiver adds said "Add Bryce Young … lineup +2.0/gm"; that add dropped J.K. Dobbins, whom Lineup moves said to
  start this week. Stempak and Bro-vid19 both cited a 9-day-old "ruled out" note (Oct 23) on an IR-slot line. Likely cause
  (not confirmed): `waivers.py:116` protects the best lineup on rest-of-season points, not this week's starters. No commits to
  `waivers.py` or `advice.py` since Nov 3 08:38 CT.
- **Expected impact:** one consistent set of moves per league; no drop of a player the card says to start.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: no league page where a waiver drop is also a lineup-move start)
- **Design:** —
- **Decision:** —

### Q-025 · War Room v2's budget step drops a claim instead of fitting it
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `decideAll`, lines 222-233; `bidOptions`)
- **Rank:** 14
- **Added:** 2026-11-05 by the nightly pass (own finding from health.json `sections.recs` and bids.json as committed
  before the Nov 4 waiver run, `dd398c1`)
- **Evidence:** health.json `recs.notes`: "Week 8: Parker Washington went for $21 (JHED1979) although his value to you was $31
  and the call was Skip." The committed bids.json gives the reason: "your other bids use the budget". Spendable $54 ($59 FAAB
  − $5 reserve); claims took money in order of expected surplus: Puka Nacua $14 (stated win chance 42%), Javonte Williams $15
  (40%), Jonathan Taylor $15 (40%) = $44, so Washington's best bid no longer fit the $10 left and the claim was dropped outright
  (`model.js:231` sets Skip when `used + r.bid > spend`, without trying a smaller bid or swapping out a weaker claim); then
  George Pickens $2 and AJ Barner $1. All three coin flips would have lost (winners paid $57, $34, $27); `rec.would_win` 0.2
  (1 of 5, the uncontested Barner), `rec.win_brier` 0.125. Michael bid $34, $34, $34 and $30 himself and won Javonte Williams.
  One waiver run (n=5 bids): a pattern to test, not a proven loss; a $10 bid would not have won Washington either.
- **Expected impact:** the claims that share the budget are chosen together for the best total expected surplus, instead of
  first-come; fewer budgets spread thin over 40% coin flips.
- **Effort:** S (a small knapsack over each claim's bid options, which `bidOptions` already lists)
- **Risk:** Med (changes which claims get money each week)
- **Measure:** `rec.would_win`, `rec.win_brier`, and `bargains_skipped` in `sections.recs.details`
- **Design:** —
- **Decision:** —

### Q-006 · The page runs 6,000 seasons, bids.json 20,000
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `S.sims`, `export.js`)
- **Rank:** 15
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The page uses 6,000 so the sliders respond quickly; bids.json, the Tuesday push and the AI write-up use 20,000.
  The audit measured ±0.3-0.7 pts of noise at 2,000. Near a call boundary (0.3-pt noise floor, Bid vs Coin flip at 50%)
  the page can show a different call than the push.
- **Expected impact:** the page always matches the push at default settings.
- **Effort:** S (inline bids.json's default-setting results in the page and recompute only when a slider moves)
- **Risk:** Low
- **Measure:** rows whose call differs page vs bids.json (one-off check)
- **Design:** —
- **Decision:** —

### Q-023 · College ATS cards still tilt 10% toward a stats model the backtest says to drop
- **Status:** proposed
- **Area:** Pool Picks (`picks/pp/cards.py` `MODEL_W`, `fair_margins`)
- **Rank:** 16
- **Added:** 2026-11-04 by the nightly pass (own finding from health.json `sections.picks` and `picks/backtest/2026_w1-8.json`)
- **Evidence:** health.json `picks.brier_gap` = 0.028 (model Brier 0.195 vs market 0.168, n=444 college games). In the backtest
  file's `model_weight` report, the walk-forward choice was weight 0 in all 6 weeks scored (3-8): total RMSE 14.059 at 0
  (= market only) vs 14.099 at the fixed 0.1. Over weeks 1-8, ATS picks where the model disagrees with the market by 3+ pts
  hit 48.9% (n=274). Against: weeks 6-8 alone lean slightly the other way (best weight 0.087 ± 0.236; disagreements hit 54.5%,
  n=77). NFL already went to 0 (`picks/pp/nfl.py:76`); college stays at 0.1 (`cards.py:105`, ROADMAP "MODEL_W stays 0.1").
  Nov 5: `picks.card_ats` now reports 0.733 (n=30), but 25 of those 30 are Yahoo straight-up picks (Q-024), so it can't
  judge this yet.
- **Expected impact:** small: college card centers move by a tenth of the model-market gap (a 5-pt gap = 0.5 pt), which
  only matters near a pool line's half point.
- **Effort:** S
- **Risk:** Low
- **Measure:** `picks.card_ats` (spread picks only, once Q-024 splits it) and the next backtest's walk-forward RMSE
- **Design:** —
- **Decision:** —

### Q-011 · One guillotine model: the dashboard and War Room v2 still give different numbers
- **Status:** proposed
- **Area:** `shq/guillotine.py` (dashboard, Today tab, cut-risk push) vs `warroom/` (War Room v2, bids.json, Tuesday checks)
- **Rank:** 17
- **Added:** 2026-11-03 (claude-audit item 1, option 4)
- **Evidence:** On Nov 3 the two models disagree for the same week 9: MoneyManChas cut risk 17.0% (dashboard) vs 21.5% (v2),
  robert8063 14.3% vs 12.6%, my projection 119.1 vs 118.8. They use different swings (dashboard per-player position SDs,
  about 27 per team; v2 measured 22), different price models (dashboard: boldest past bid share, $10 reserve per bid; v2:
  calibrated ladder, $5 reserve across all bids) and different values (dashboard: points gained; v2: win odds). The site shows
  the dashboard's bids, the Tuesday push uses v2's. Audit item 1 ("three models give three sets of numbers") recommended folding
  them into one after the redesign. Nov 4 health run, first scored waiver run (week 8): the dashboard's likely prices missed
  by $12.4 (`gd.dash_price_mae`, n=8) vs v2's $8.3 (`rec.est_mae`, n=6); the dashboard put Puka Nacua, Javonte Williams and
  Jonathan Taylor all at $43 (winners paid $57, $34, $27), v2 at $27, $33, $33.
- **Expected impact:** one answer everywhere (site, push, AI write-up); fixes found in one model reach every screen.
- **Effort:** M (dashboard reads bids.json for odds and bids; keeps its live Sunday locking until Q-002 lands)
- **Risk:** Med (the cut-risk push and Today tab change source)
- **Measure:** `gd.v2_skill` vs `gd.dash_skill` (which predicted cuts better as shown), `gd.dash_price_mae` vs `rec.est_mae`
- **Design:** —
- **Decision:** —

### Q-021 · Hygiene pass: line endings, public CFBD files, worktrees, browser rule
- **Status:** proposed
- **Area:** `picks/pp/grade.py`, `picks/pp/model.py`, `picks/cache/cfbd/`, `.claude/worktrees/`, ROADMAP.md, laptop prompts
- **Rank:** 18
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Rule breaks" #2-4 and "Ranked improvements" #10, and
  IDEAS.md "Proposed by monthly review" (last two lines)
- **Evidence:** Still true Nov 4: `git ls-files --eol` shows `i/crlf` for `picks/pp/grade.py` and `picks/pp/model.py`; 17 files
  under `picks/cache/cfbd/` are tracked (raw CFBD responses in a public repo, against `.gitignore:13-16`); `.claude/worktrees/`
  holds 5 folders (analytics-sources, friendly-tu-4f1575, nice-hamilton-b16e8b, sweet-euler-ce89af, vigilant-dewdney-33aa4d;
  not confirmed which are merged); ROADMAP.md:207 still says "use Chrome" with no exception for the public-site 375px check
  that needs the built-in browser's viewport emulation. The review also found the daily-sync prompt hard-codes the ntfy
  topic and that laptop prompts lack copies in `ops/tasks/`; not re-checked tonight. Nov 5: the first three checks are
  unchanged (2 CRLF files, 17 tracked CFBD files, the same 5 worktrees); `ops/tasks/` still has no daily-sync copy.
- **Expected impact:** the repo follows its own rules; nothing raw from CFBD stays public; less clutter.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off: the four checks above come back clean)
- **Design:** —
- **Decision:** —

### Q-009 · The 0.3-point win-odds noise floor is a guess
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `MIN_WIN`)
- **Rank:** 19
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Moves adding under 0.3 points of win odds are skipped as noise, but the real noise of `gains()` (10,000 seasons,
  same seed for both sides) has not been measured.
- **Expected impact:** small free adds stop being dropped (or noise stops being recommended).
- **Effort:** S (rerun `gains` with several seeds, set the floor at about 2 standard errors)
- **Risk:** Low
- **Measure:** one-off; then fixed
- **Design:** —
- **Decision:** —

### Q-007 · Free-agent candidates are capped (3 per position, 24 total)
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `candidates`)
- **Rank:** 20
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Only the top 60 free agents by projected points are tried, then at most 3 per position and 24 overall. The old
  cap of 2 per position hid Bo Nix (audit). A bye-week fill-in or a K/DEF stream can rank 4th at its position and vanish.
- **Expected impact:** no useful free add silently missing.
- **Effort:** S (raise the caps; check build time)
- **Risk:** Low (slower build)
- **Measure:** one-off: free agents beyond the cap that would add more than the noise floor
- **Design:** —
- **Decision:** —

### Q-019 · The picks backup has never worked for real
- **Status:** proposed
- **Area:** `.github/workflows/picks-backup.yml`, `.github/workflows/run.yml`, `picks/pp/http.py`, GitHub secret `CFBD_API_KEY`
- **Rank:** 21
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #8 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Reliability): the backup's crons ran 4-7h late every time (Wed 9:45pm slot at 5:25am Thu;
  Sat 8:45am at 1:45pm, after CFP's 11am lock), and `pp/http.py:48` raises on any uncached CFBD call without a key. Nov 4:
  `gh secret list` still has no `CFBD_API_KEY` (NTFY_TOPIC, TOKEN_KEY and 3 Yahoo secrets only). Not confirmed: whether it
  could build a card at all. Nov 5: secret still absent.
- **Expected impact:** a real fallback card when a laptop picks run is missed.
- **Effort:** M (plus one manual step for Michael: add the secret)
- **Risk:** Low
- **Measure:** — (one-off: a forced backup run builds a card)
- **Design:** —
- **Decision:** —

### Q-010 · Automatic $ per win-point assumes every future crop looks like this week's
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `autoDpp`)
- **Rank:** 22
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** `autoDpp` lines up this week's freed players by win odds per $, assumes a similar crop at every waiver run you're
  expected to see, and takes the rate where FAAB runs out. Crops vary a lot: the top winning bids per run were $150 (wk 1),
  $156 (wk 2), $80 (wk 3) (health.json `recs.details.winners_paid`). The audit called $ per extra week "the biggest lever, and
  a guess"; this replaced the guess with one week's sample.
- **Expected impact:** steadier bid values week to week; less risk of overspending on a weak crop or hoarding before a strong one.
- **Effort:** M (estimate future crops from the remaining rosters: who is likely cut next and what they hold)
- **Risk:** Med (changes every value)
- **Measure:** `rec.would_win`, spending pace vs weeks survived (to add to health once bids have outcomes)
- **Design:** —
- **Decision:** —

### Q-008 · Rivals' adds ignore their drops
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `rivalGain`, `threats`)
- **Rank:** 23
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** My adds are valued net of my best drop, but a rival's gain (which sets his predicted bid) assumes he adds without
  dropping anyone. Rosters are full, so a rival with no bench to spare gains less than modeled.
- **Expected impact:** small: slightly lower price estimates for players only thin-benched rivals need.
- **Effort:** S
- **Risk:** Low
- **Measure:** `wr.price_est_mae`
- **Design:** —
- **Decision:** —

### Q-001 · Simulation doesn't hand freed stars to rivals (denial value)
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `simulate`, `gains`)
- **Rank:** 24
- **Added:** 2026-11-03 (Nov 3 slider audit; warroom/README.md "Known limits")
- **Evidence:** The sim keeps current rosters, so a freed star you don't claim never strengthens a rival. In a winner-take-all
  league, a star going to the strongest rival lowers your win odds even if you survive. Not yet measured.
- **Expected impact:** higher values for stars the top rivals need; possibly worth bidding on players who add little to your
  own lineup. Size unknown: first step is to measure how much a rival's win odds move when he wins the top freed player.
- **Effort:** M-L (in each sim, give each unclaimed freed player to his likeliest winner at the estimated price)
- **Risk:** Med (can inflate bids; slower build)
- **Measure:** `rec.would_win`; a one-off what-if on past runs before building
- **Design:** —
- **Decision:** —

### Q-004 · No rival-specific bidding habits
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `threats`)
- **Rank:** 25
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** A rival's predicted bid uses only his boldest past bid share (`MAXPCT`), his need and the player's quality; the
  ladder then corrects league-wide. Some teams win most big claims (CodyRust $150 McCaffrey and $50 Adams in week 1; Aniasin1
  once bid 93% of the FAAB he had left). The ladder holds 165 priced claims, about 10 per team.
- **Expected impact:** better price estimates when a known big spender needs the player.
- **Effort:** M
- **Risk:** Med (about 10 claims per rival: easy to overfit)
- **Measure:** `wr.price_est_mae`, `wr.ladder_cov50`
- **Design:** —
- **Decision:** —

## Done
(Items move here when verified, newest first, with the commit and the health.json numbers that confirmed them.)
