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

### Q-037 · GitHub jobs still run hours late: make the laptop the clock for every time-critical one
- **Status:** shipped (d5d5bf7, landed Tue Nov 10 after Michael lifted the Sunday hold)
- **Area:** `ops/kick.ps1` (one push per outage), `.github/workflows/war-room-v2.yml` (own concurrency group for kicks),
  `shq/run.py` (`laptop_kicks`: a push when the 2:55am kick didn't happen; "Laptop kick" footer row),
  `.github/workflows/run.yml` (game-day handoff), `.github/workflows/model-health.yml` (4:50am cron removed),
  `ops/designs/Q-014.md` "The laptop is the clock"
- **Rank:** —
- **Added:** 2026-11-09 by Claude Ops (Michael called the late GitHub jobs "clunky" and asked for a step-back review)
- **Evidence:** claude-audit `overhaul/github-reliability.md` (independent review, Nov 9): GitHub documents scheduled runs as
  best effort; War Room v2's daily 6:10am build ran 5.6-10.1 hours late on all 6 days Nov 2-9 (Tue Nov 3's first run 6:21am);
  every laptop `workflow_dispatch` since Nov 8 started within seconds (Q-029). Gaps it found: no War Room kick; a failed kick
  only writes a log line no session can read; a dispatched War Room run can be replaced by a late cron run in the shared
  concurrency group; a game-day loop that hits its 5h45m limit leaves the injury watch idle up to about 80 minutes.
  Tue Nov 10 (Claude Ops' morning review, checked against `gh run list --workflow war-room-v2.yml`): GitHub never ran the
  Mon 10:40pm, Mon 11:20pm or Tue 5:40am CT War Room builds; the first runs were 6:58am and 7:37am CT. The 6:03am strategy
  Doc was written on a week-old bids.json (`ada4348`, Mon 4:15pm CT, before the week 9 cut was confirmed).
- **Expected impact:** every time-critical build on time while the laptop is on; one push when the laptop can't start jobs,
  and one a day when it has gone quiet; no injury-watch gap between game-day loops.
- **Effort:** S-M
- **Risk:** Low (two new push types, each at most once per outage or day; the handoff only fires when a loop hits its time
  limit while a watch window is still open)
- **Measure:** — (one-off: Tuesday War Room builds within 5 minutes of 5:40am and 6:50am CT for two weeks; no cancelled
  dispatches; no gap over 15 minutes between `data:` commits inside game windows)
- **Design:** claude-audit `overhaul/github-reliability.md` §3 (option B); as built in `ops/designs/Q-014.md` "The laptop is
  the clock". The Windows task "Kick war room" is not part of this item's commits: it is staged in claude-audit
  `overhaul/staged/github-kicks.ps1` and registered Sun Nov 15 9:00am by the "Overhaul: apply staged edits" task.
- **Decision:** approved 2026-11-09 (Michael's Nov 9 instruction, via Claude Ops; extends the approved R1 / Q-029)

### Q-038 · War Room v2 never credits a $0 bid with its payoff, so it recommends $1 that buys nothing
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `decideAll`, the line `let best = { b: 0, ev: 0, p: winChance(0, r.est) }`)
- **Rank:** —
- **Added:** 2026-11-10 by the Sports HQ build session (from Claude Ops' review of the Nov 10 bids.json)
- **Evidence:** bids.json `f53bf00` (Tue Nov 10 7:37am CT): Saquon Barkley "Bid $1", `win_chance` 0.572, and `win_curve`
  gives 0.57 at both $0 and $1, so the dollar buys nothing (he is on bye in week 10; value $3). Cause: the search starts
  the $0 option with `ev: 0` instead of `winChance(0) x value`, so any bid of $1+ with a positive payoff beats it. For
  Barkley $0 is worth 0.57 x $3 = $1.71 against $1.14 at $1 (`bid_options` avg_payoff 1.1). MIN DEF has the same pattern
  ($1 at 0.77 vs $0 at 0.57; there the $1 is worth it).
- **Expected impact:** no wasted dollars on claims a $0 bid wins as often; with $5 spendable, $1 is 20% of the budget.
- **Effort:** S (one line, plus a test that a flat curve between $0 and $1 gives a $0 call)
- **Risk:** Low (also needs a call name for a $0 waiver claim, e.g. "Claim at $0"; today $0 means "Add free" or nothing)
- **Measure:** — (one-off: no row whose recommended bid has the same `win_curve` value as $0)
- **Design:** —
- **Decision:** —

### Q-039 · Stated win chances don't match the same row's likely rival bids
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `winChance`, `threats` (the `likely_rival_bids` list); `warroom/build.py` `ladder`)
- **Rank:** —
- **Added:** 2026-11-10 by the Sports HQ build session (from Claude Ops' review of the Nov 10 bids.json)
- **Evidence:** bids.json `f53bf00`: Jaylen Warren 21% at $2 while the row lists rivals at $18, $13 and $11; Barkley 57% at
  $0 with three rivals at $4 each. The two numbers come from different places: `likely_rival_bids` is the raw guess per
  rival, while `winChance` uses only the ladder (how past winning bids compared with the raw estimate), which is well
  calibrated league-wide (`wr.ladder_cov50` about 0.55, Q-003). So the rival list may be what's too high, not the chance.
  Also, at $0 `winChance` counts every past $0 winning bid as a win for me, but a $0 tie goes by waiver order.
  Not confirmed: which number is wrong; the Wed Nov 11 waiver run is the first test.
- **Expected impact:** one believable number per row; the bid check (and the Nov 15 chain addendum, which calls a >50% chance
  below every rival bid "not believable") stops having to second-guess the model.
- **Effort:** M (show calibrated rival bids, or scale the rival list by the ladder; treat $0 ties by waiver order)
- **Risk:** Med (changes every stated win chance)
- **Measure:** `rec.win_brier`, `wr.ladder_cov50` (by estimate size), share of rows where the stated chance is above 50% while
  the bid is below every listed rival bid (should be 0)
- **Design:** —
- **Decision:** —

### Q-040 · An injured or IR player with no projection still gets "Add free"
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `decideAll`, the free-agent branch; `proj`)
- **Rank:** —
- **Added:** 2026-11-10 by the Sports HQ build session (from Claude Ops' review of the Nov 10 bids.json)
- **Evidence:** bids.json `539613e` and `f53bf00`: Lamar Jackson (QB, injury "Out", `ir` true, `proj_next_week` 0) is
  "Add free", dropping Woody Marks (8.2 projected). Free agents get "Add free" whenever their rest-of-season win odds clear
  `MIN_WIN`, with no check on whether he can play soon or whether the drop is worth more now. Not confirmed: how many weeks
  Sleeper projects him out.
- **Expected impact:** no free add that costs a usable player for someone who can't play; an IR stash only when an IR slot is
  open or the gain is large and labelled "stash".
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off: no "Add free" row with injury Out/IR and `proj_next_week` 0 unless its call says stash)
- **Design:** —
- **Decision:** —

### Q-041 · War Room v2 drops a usable RB to add a second DEF
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `bestDrop`, `decideAll`)
- **Rank:** —
- **Added:** 2026-11-10 by the Sports HQ build session (from Claude Ops' review of the Nov 10 bids.json)
- **Evidence:** bids.json `f53bf00`: MIN DEF "Bid $1" (77%), drop Breece Hall (RB, 8.1 projected, 11.9 season average).
  I already start CIN DEF (6.6 projected); MIN DEF projects 6.1, and BAL DEF (8.5) and GB DEF (8.2) are free adds in the
  same file. `bestDrop` picks the drop that costs the least projected starting lineup over the coming weeks, so a bench RB
  counts as nearly free (no value for injury cover), and each row is valued alone, so it can pay for one DEF while a
  better one is free.
- **Expected impact:** no starting-calibre RB or WR dropped for a backup DEF or K; when a better DEF is free, the paid DEF
  claim is skipped.
- **Effort:** S-M (protect RB/WR above a projection floor from K/DEF swaps; compare paid claims with free adds at the same
  position)
- **Risk:** Low
- **Measure:** — (one-off: no claim whose add is K/DEF and whose drop is an RB/WR projected above about 8 points)
- **Design:** —
- **Decision:** —

### Q-042 · A lineup fix says "start" a bench player projected 0 while a free agent projects 15+
- **Status:** shipped (e508112)
- **Area:** `shq/digest.py` (`_fix`, `_room`: Today digest, league-tab fixes, digest push), `shq/run.py` (`injury_watch`
  pushes), `shq/swap.py` (`slot_fa`, `fa_over_bench`, `MIN_FILL` 1.0, `FA_EDGE` 5.0), `shq/advice.py` (values loaded before
  the fixes so a fix can name the waivers drop)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (bug on the Domo Arigato league card, reported via Claude Ops)
- **Evidence:** lineups.json, Tue Nov 10 4:37pm CT: Domo Arigato fix "Caleb Williams (QB) on BYE → start Carson Wentz", with
  no projection shown; Wentz projected 0 this week and the next 4 (a backup after Cousins' trade to MIN), while the same
  card's adds named Drew Lock (SEA, 15.7 this week). `_fix` took any playable bench player whatever his projection and
  printed the projection only when above 0; the injury watch had the same "any playable bench player" rule.
- **Expected impact:** a football fix never tells Michael to start a 0-point player when a usable free agent exists: it
  says "add <FA> (proj) into your open roster spot / drop <X> and start him", keeps the bench option as a fallback only
  above 0, and always shows the projection. Superflex/OP slots look at every eligible position (QBs included); a QB slot
  only at QBs. NBA category leagues unchanged. Suggestions only: nothing is ever added or dropped.
- **Effort:** S
- **Risk:** Low (text only, plus the injury watch no longer swaps in a sub-1-point player when a free agent is available)
- **Measure:** — (one-off: no urgent fix line "start <name> (0 proj)" while a free agent projected 1+ fits that slot)
- **Design:** a bench fill-in under 1 point, or one a playable, slot-eligible free agent beats by 5+ points, gives way to
  "add <FA> and start him"; the room comes from an open roster spot, else the drop `shq/waivers.py` picks for that free
  agent (needs FantasyCalc values), else "needs a roster spot". Tests: `tests/test_digest.py` `FreeAgentFix`.
- **Decision:** bug fix requested by Michael via Claude Ops, Nov 10

### Q-043 · Traded players and new starters get zero or old-team rest-of-season numbers after the trade deadline
- **Status:** shipped (ce89445)
- **Area:** `shq/values.py` (`_slim` keeps each projection's team, `ros_weeks`/`ros_ppg` fill, `per_game`, `ir_games_left`,
  `live_team`, `annotate`; ROS cache format 2), `shq/leagues.py` (`make_player`, `EspnLeague._live_team`/`_player`),
  `shq/nfl_players.py` (basis text), `tests/test_trade_deadline.py`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (audit of the Tue Nov 10 NFL trade deadline: Downs IND→KC, Allen IND→SF,
  Cousins LV→MIN, Mendoza LV's starter, Malik Willis to IR)
- **Evidence:** `docs/data/players_nfl.json` 22:47Z: Sleeper's weeks 11-12 projections still carried the old teams and week 13
  (IND/LV bye) had no row for the new teams, so Allen read [6.0, 9.4, 9.3, 0.0] = 6.2/gm (Domo), Cousins [13.8, 16.4, 16.7, 0.0],
  Mendoza [10.9, 0.0, 0.0, None] = 3.6/gm (3-Ball), Downs (shown KC) got IND's week-13 bye from the 6h players file, and
  Willis (IR) was projected 14-19 a week. Kosmonauts advised "Add Carnell Tate … for Keenan Allen (4.9/gm): fills in at WR in
  week 13". Stempak/Bro-vid19 (ESPN snapshot) still showed Cousins "LV vs SEA" at 21:05Z (really MIN @ GB, 18:00Z).
- **Expected impact:** rest-of-season, next-4-weeks, waiver and trade numbers follow a player's current team and role on the
  day of a move, not when Sleeper next rebuilds its later weeks; lineups lock on the right kickoff after a trade.
- **Effort:** M
- **Risk:** Low (a healthy player Sleeper deliberately stopped projecting would now get his live number; out/IR players don't)
- **Measure:** — (one-off: no healthy skill player with a live projection shows a 0 in `next` on a week his team plays)
- **Design:** a week whose projection is missing or was made for another team takes the player's live per-game number (this
  week's Sleeper projection when it's for his current team, else the average of his up-to-date weeks, else 0 as before),
  never for OUT/IR/PUP/SUSP players. Team and bye come from Sleeper's live projections, then the players file, then the
  platform; a Yahoo or ESPN snapshot team that differs from Sleeper's live team gives way for opponent, kickoff and bye. A
  confirmed IR tag (status.confirm) scores 0 for the games left on the 4-game minimum, placement estimated from ESPN's
  injury entry date (unknown date: all 4). Tests: `tests/test_trade_deadline.py`.

### Q-044 · The Guillotine league page said every TE was "priced out" while War Room v2 said free add or $1
- **Status:** shipped (aac5193)
- **Area:** `shq/guillotine.py` (`load_v2`, `v2_current`, `v2_rows`, `on_waivers`, `RESERVE` 10 → 5), `docs/lib/core.js`
  (`bidText`, bid section, home tile and inbox lines), `tests/test_guillotine.py` (`WarRoomV2`)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (contradiction reported via Claude Ops)
- **Evidence:** lineups.json, Tue Nov 10 2026: every TE (Freiermuth, Fannin, Strange, Hockenson, Higbee) "priced out:
  rivals may go $4, worth $0 to you", shown on the tile/inbox as "Bid: Pat Freiermuth … priced out"; bids.json the same
  day: Freiermuth and Brenton Strange "Add free", Harold Fannin "Bid $1". Cause: `RESERVE = 10` (all of Michael's $10, so
  `my_max` was always $0) against v2's `reserve: 5`, and the model priced plain free agents as waiver bids.
- **Expected impact:** one set of bid calls everywhere: the league page, home tile and inbox show War Room v2's call, bid,
  drop, why and win chance (link to /war-room-v2/) whenever bids.json is for this week and its waiver run hasn't passed.
  The old model is only the fallback: v2's reserve (from bids.json, else 5), plain free agents are "Add free" (only a
  fresh cut's players, before their Wednesday run, need a claim), and a priced-out line says "over your reserve" instead
  of "worth $0". A $0 Bid reads "Claim at $0". Priced-out rows stay on the league page only; with v2 current the generic
  guillotine add ideas stay off the inbox.
- **Effort:** S
- **Risk:** Low (display and fallback only; War Room v2 untouched)
- **Measure:** — (one-off: no Guillotine bid line in lineups.json contradicts bids.json's call for the same player).
  Note for `shq/health.py`: from this week the dashboard's `bids` mirror v2 (`bid_source` says which); the model's own
  rows are kept under `advice.guillotine.model` if the dashboard-vs-v2 comparison should keep scoring them.
- **Design:** `analyze()` reads `docs/war-room-v2/bids.json`; current = same `week` and `now` ≤ `next_waiver_run` + 1h.
  Rows keep v2's order, drop Skips, and keep `call` (lowercase), `bid` (= `price`), `drop`, `why`, `win_chance`,
  `your_max` (as `max`). A malformed file falls back. Free agent vs waivers in the fallback follows v2's `freed_status`
  (players in a `chopped` transaction, until a waiver run after it or an hour past that Wednesday's run).
- **Decision:** bug fix requested by Michael via Claude Ops, Nov 10

### Q-046 · Site polish: wrap-up cuts mid-word and margins off by 0.1, stale picks card unlabeled, small phone taps
- **Status:** shipped (ae9cd9f)
- **Area:** `shq/wrapup_render.py` (`short`), `shq/wrapup.py` (`margin`, `h2h_line`), `docs/wrapups/` (index, weeks 8-9
  re-rendered from saved JSON), `picks/pp/cards.py` (`card_over`, `old_card_html`), `docs/picks/index.html` (banner added
  to the live page), `docs/lib/core.js` (`SHQ.picksStale`), `docs/lib/core.css` (`.pill`, `.fb button`),
  `docs/index.html` (Players tile)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (site review via Claude Ops)
- **Evidence:** wrap-up archive rows ended "…Most left" / "…Yahoo en" (`[:220]`); week 9 read "182.8-7.0 … by 175.7"
  and "166.5-141.5 … by 25.1" (margin from raw 182.76-7.04); /picks/ on Tue Nov 10 still showed Saturday's "SAT REFRESH"
  card with "next lock Sat 10:55am CT" and no label; footer "Picks cards: 3d ago" amber every Tue/Wed (30-hour rule on a
  Wed-Sat job); 👍/👎 22px and header pills 28px tall; Players/War Room/Wrap-up header links hidden under 420px.
- **Expected impact:** archive short versions end on a whole sentence; margins match the scores shown; an old picks card
  says so ("Last week's card … New drafts post Wednesday 9pm CT") from the Tuesday after it was built; the footer is amber
  only when a Wed 9pm / Thu 8pm / Fri 9pm / Sat 8am CT build was missed (3h grace, fresh from 2h before the slot, like
  picks-backup.yml); tap targets at least 36px; Players one tap from the home page (War Room and Wrap-up tiles already were).
- **Effort:** S
- **Risk:** Low (display only; week 8 margins also corrected: 79.2, 13.9, 24.5)
- **Measure:** — (one-off)
- **Design:** tests: `tests/test_wrapup.py` (short version, margins), `tests/test_pick_breakdowns.py` (`card_over`, banner),
  `tests/test_core_js.py` (`SHQ.picksStale`, Node; skipped without Node). Checked at 375px and desktop, light and dark.
- **Decision:** bug fixes requested by Michael via Claude Ops, Nov 10

### Q-027 · B2: no way to sift NBA players inside HQ (still done on FantasyPros)
- **Status:** shipped (02451dc)
- **Area:** `docs/players/index.html` (new), `docs/lib/core.js` (`SHQ.loadFile`, Players links in the ▦ menu and on NBA league
  pages), header links in `docs/index.html` and `docs/lab/b|c|d/`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B2)
- **Evidence:** Nov 5: Michael still sifts players on FantasyPros; HQ had no player list to sort or filter.
  Nov 6 nightly pass: still shipped; its data is in place (see Q-026), the Measure is Michael's feedback and FEEDBACK.md has
  none on the Players page yet. Nov 7: still none (FEEDBACK.md holds only the two Oct 31 layout lines). Nov 8: still none.
  Nov 9: still none.
  Nov 10: still none.
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


### Q-029 · R1: the laptop starts the GitHub jobs on time (builds Q-014)
- **Status:** shipped (d2bfcb7; logging d5482ef, c590724). Working since Nov 8: Michael saved a one-repo, Actions-only token
  (option A) in his own PowerShell window; test kicks started `model-health.yml` from the laptop at 8:21am and 8:29am CT. The
  first token was replaced the same morning (it showed in a chat screenshot, and the link's 366-day expiry hadn't applied);
  the current one **expires Nov 8, 2027**, after which the kick log says "GitHub rejected the saved token". The cause of the
  earlier silence (the Claude app's private copy of AppData) and the sign-in options stay in `ops/designs/Q-014.md`.
- **Area:** `ops/kick.ps1` (new), Windows Task Scheduler `\SportsHQ\Kick run` and `\SportsHQ\Kick model health` (user level),
  `.github/workflows/run.yml` (concurrency, one-pass rule, `actions: read`), `shq/run.py` (`origin_digest`, `digest_due`,
  digest `push_once`), `ops/designs/Q-014.md` ("As built", exact commands and removal)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item R1); evidence in Q-014
- **Evidence:** Q-014: the 8am digest built at 11:06am Nov 4; model health ran 7.5 hours late; manual dispatches dropped.
  Nov 5 evening, while building this: a dispatch made at 5:48pm CT sat "pending" behind a game-day loop that started at
  2:29pm (the old single concurrency group). Nov 6 nightly pass: on Thu Nov 5 (before this was built) no Sports HQ data
  commit landed between 6:11am and 2:30pm CT (12:11Z, then 20:30Z: 8h19m, so no 8am digest on time); model health's 2:50am
  and 4:50am CT slots ran at 10:53am and 12:19pm CT (8h03m and 7h29m late); tonight's 2:50am slot had not run by 3:45am CT,
  so the 2:55am laptop kick still starts nothing (gh not signed in outside the app). The first real test is the first
  weekday 8am after Michael signs gh in outside the app.
  Nov 7 nightly pass: same on Fri Nov 6: data commits at 6:00am, then 11:25am CT (12:00Z, 17:25Z: 5h25m over 8am, so no
  8am digest on time); model health's 2:50am and 4:50am slots ran at 10:20am and 11:42am CT (7h30m and 6h52m late); tonight's
  2:50am slot had not run by 3:52am CT. So the kicks still start nothing. Not confirmed: the kick log (it can only be read
  from outside the Claude app).
  Nov 8 nightly pass: same on Sat Nov 7: data commits at 5:19am, then 10:19am CT (11:19Z, 16:19Z); model health's 2:50am
  and 4:50am slots ran at 9:13am and 10:39am CT (6h23m and 5h49m late); `gh run list --workflow run.yml` shows no
  `workflow_dispatch` run since Nov 6 00:23Z (the Nov 5 build's manual runs), so no laptop kick has started a run; tonight's
  2:50am health slot had not run by 3:52am CT. Still waiting on Michael's gh sign-in outside the app.
  Nov 9 nightly pass: the kicks now start runs. `model-health.yml` ran as a `workflow_dispatch` at 08:55Z (2:55am CT,
  the kick slot; health.json generated 08:55Z, the first nightly health on time); `run.yml` had laptop dispatches at
  04:02Z and 05:02Z (Sun 10:02pm and 11:02pm CT). Sunday's game-day loop committed data every 10 min from 10:07Z, so
  the daytime kicks skipped as designed. The Measure (weekday data commit 8:00-8:15am CT for two weeks) starts today.
  Nov 10 nightly pass: the first weekday of the Measure passed. Mon Nov 9 had a data commit at 8:02am CT (14:02:27Z)
  from the 8:02 kick. 12 laptop dispatches of `run.yml` from Nov 9 04:02Z to Nov 10 05:02Z, all succeeded, none
  cancelled; `model-health.yml` was kicked at 2:55am CT again (08:55Z Nov 10). 1 of 10 weekdays; the two weeks end
  Fri Nov 20.
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


### Q-014 · Morning runs depend on GitHub's late crons, and manual dispatches get dropped
- **Status:** shipped (d2bfcb7, built as Q-029; working since Nov 8)
- **Area:** `.github/workflows/run.yml` (concurrency, lines 46-48), the 7:30am laptop daily sync prompt
- **Rank:** — (approved and being built as Q-029; no longer ranked)
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #3 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Reliability): 26 "cancelled" Sports HQ runs never started because `concurrency:
  cancel-in-progress: false` keeps one waiting run, and 7 manual dispatches were dropped (Oct 25, 28, 30). On 3 of 8 weekday
  mornings no run fired between 8am and late morning; Mon Oct 26's 6h22m gap meant no 8am digest. Still open Nov 4: run.yml
  has the same single concurrency group, and no `ops/tasks/*.md` ends with `gh workflow run run.yml`. Same pattern tonight:
  `model-health.yml`'s 2:50am CT cron (`50 8 * * *`) had not run by 3:53am CT; its only run ever is the Nov 3 manual dispatch.
  Nov 5: it happened again on Wed Nov 4. No Sports HQ run between 2:59am and 11:06am CT (data commits 08:59Z, then 17:06Z:
  8h07m), so the 8am digest was about 3 hours late; Nov 3 00:00Z - Nov 5 10:00Z, 17 runs started (2 more cancelled) in 58
  hours. `model-health.yml`'s two slots (2:50am, 4:50am CT) ran at 10:37am and 12:15pm CT (7h47m and 7h25m late), and
  tonight's 2:50am slot again had not run by 3:53am CT. Nov 6: same again on Thu Nov 5 (see Q-029: 8h19m data gap over 8am;
  model health 8h03m and 7h29m late). Nov 7: same on Fri Nov 6 (Q-029: 5h25m data gap over 8am; model health 7h30m and
  6h52m late). Nov 8: same on Sat Nov 7 (Q-029: no data commit 5:19am-10:19am CT; model health 6h23m and 5h49m late;
  run.yml had 3 cancelled scheduled runs of 13 on Nov 7 UTC, the single concurrency group).
  Nov 9: built as Q-029 and working (see there). Scheduled `run.yml` runs still share one concurrency group: 7 of
  20 scheduled runs since Nov 8 00:00Z were cancelled; dispatches have their own group, and none were dropped.
  Nov 10: none of the 12 scheduled `run.yml` runs since Nov 9 00:00Z was cancelled (7 of 20 the day before). War Room
  v2 is still on GitHub's crons: Mon Nov 9's 6:10am CT slot started at 4:15pm CT (22:15Z), and the Mon 10:40pm and
  11:20pm CT slots had not started by 3:55am CT Tue, so bids.json still showed week 9 (before MoneyManChas was cut)
  while the dashboard was on week 10. That gap is Q-037, built on branch `claude/improvements-nov5-6ed372` and not on
  main yet (claude-audit `changes.md`, "Overhaul 16"); it is not repeated here as a new item.
- **Expected impact:** the 8am digest and Tuesday Weekly tab on time; a "force" button press never vanishes.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: data-commit gaps 8am-1pm on weekdays, and dropped dispatches, in the next monthly review)
- **Design:** `ops/designs/Q-014.md`
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)


### Q-030 · R2: a BTO bet on the Thursday game gets no final check before it locks
- **Status:** shipped (fd1551f); the scheduled task itself is created by the Claude Ops session from the prompt
- **Area:** `picks/pp/thu_check.py` (new), `ops/tasks/pool-picks-thu-bto-check.md` (new task prompt), `tests/test_thu_check.py`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item R2)
- **Evidence:** the BTO "final" card runs Thu 8pm, after the Thursday NFL game kicks off (7:15pm); BTO locks each game at
  kickoff (Nov 4: Michael's saved JAX bet locked Thu 7:15pm, `pp/push.py` `early_lock`). Nov 5 dry run on real data: saved
  bets (read Wed 9:20pm) differ from the draft card on all 5 games, JAX @ BAL locking 7:15pm.
  Nov 6 nightly pass: still shipped; it shipped Thu 6:06pm CT, after that week's 4pm slot, so the first real run is Thu
  Nov 12 (not checked tonight: that the Claude Ops task exists).
  Nov 7: claude-audit `changes.md` (Nov 5 ~6:35pm) records that Claude Ops created the local task
  `pool-picks-thu-bto-check` (Thu 4pm, next Nov 12), saved in the Default permission mode rather than Auto and due to be
  re-saved in Auto. Not confirmed: that it has been re-saved.
  Nov 8: the task list shows `pool-picks-thu-bto-check` enabled, Thursdays 4:07pm, next run Thu Nov 12 (never run yet).
  Not confirmed: its permission mode (the list doesn't show it).
  Nov 9: claude-audit `changes.md` (Nov 8) records the task re-created in Auto mode (same prompt, Thu 4pm); first run
  Thu Nov 12.
  Nov 10: unchanged; first run Thu Nov 12.
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


### Q-032 · B5: no NBA lineup push before tip-off when a move is needed
- **Status:** shipped (3ae3a74)
- **Area:** `shq/nba_lineup.py` (new), `shq/run.py` (send before the injury watch), `shq/advice.py` `_moves` (NBA "Lineup
  moves"), `shq/digest.py` (`_fix` ranks by value; NBA lineup items no longer urgent)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B5)
- **Evidence:** the 8am digest flagged "no game today → start X" for NBA, but nothing pushed later in the day when injury
  news lands; the NBA tabs had no lineup moves at all (`_moves` returned [] for NBA); bench picks were by points (0.0).
  Nov 6 nightly pass: still shipped. Today's data has the moves (3-Ball 3 "Start X over Y: no game today", Ball is Life 2),
  but whether the push went out can't be checked: no push log yet (Q-015). Nov 7: same; still no push log. Nov 8: same.
  Nov 9: same; still no push log (Q-015).
  Nov 10: same; still no push log (Q-015), so the push count can't be measured.
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


### Q-036 · NBA radar flags now trail the old suggestions (`radar.held` drift, `radar.edge` weak)
- **Status:** designed
- **Area:** `shq/radar.py` (`block`, `fit_score`, `send_alerts`), `shq/radar_backtest.py` (`run`, the comparison list),
  `shq/health.py` `radar_health`
- **Rank:** 1
- **Added:** 2026-11-06 by the nightly pass, from health.json flags `radar.held` and `radar.edge` (both drift since the
  Nov 5 16:53Z run) plus a read-only replay of `radar_backtest.run` tonight
- **Evidence:** health.json (Nov 5 18:19Z): `radar.held` 0.77 (17 of 22 flagged free agents kept the bigger role) vs
  baseline 1.0 (n=5, set Nov 3), tolerance 0.15; `radar.edge` 0.15 z per game (flags −2.51 vs the old suggestions −2.66)
  vs baseline 1.32 (n=5), tolerance 0.5, floor 0.0 (still above the floor, so drift, not weak). The Nov 4 runs had 1.0 and
  1.44 on 5 flags; the jump to 22 flags is new mornings with games after them. Tonight's replay (games through period 17):
  25 free agents flagged on 47 mornings, flags −2.53, the old suggestion −3.62, average free agent −5.43, so the edge
  already swung to +0.91 in a day: at this n the check is noisy. The pattern underneath: the flag is minutes only, and 16
  of the 25 projected under −3 z per game in the league's categories even at their new minutes (Larry Nance Jr. −3.62,
  then −8.78 after); that projected value correlates 0.31 with value after. On the later mornings (periods 13-14), the 14
  flag-mornings projected at −3 or better averaged −0.04 after, the 23 below −3 averaged −3.62 (all 37: −2.27). In-sample:
  the earlier mornings (periods 11-12) had only 2 such flags, too few to pick a cutoff. Two more gaps: the comparison list is still "the 3 most-owned free agents"
  (`radar_backtest.run`), which Q-028 (168a299) replaced on the site with value-ranked swaps; and only 3-Ball is checked.
  Nov 7 (Nov 6 17:43Z run): `radar.held` 0.76 (19 of 25) still drift; `radar.edge` back to ok at 1.16 (flags −2.53 vs the
  comparison list −3.69, n=25), as the Nov 6 replay suggested: the edge check is noisy at this n. The low-value flags
  the design gates are unchanged; ranked one place lower (6) because the headline edge recovered.
  Nov 8 (Nov 7 16:39Z run): `radar.edge` is weak for the first time: −0.98 z per game (flags −3.12 vs the comparison list
  −2.14, n=29), below its 0.0 floor, so the flagged free agents did worse than the site's old suggestions; `radar.held`
  0.79 (23 of 29) still drift; across all flagged player-mornings 59 of 84 held (`any_held`), 1 flag added by someone later.
  The edge has gone +0.15, +1.16, −0.98 over three runs: noisy, but now negative at the largest n so far. Ranked 3 (was 6).
  Nov 9 (Nov 8 16:48Z run): worse again. `radar.edge` −2.98 z per game (flags −4.25 vs the comparison list −1.28,
  n=42), weak for the second run and the lowest yet; `radar.held` 0.71 (30 of 42), the lowest yet; across all flagged
  player-mornings 73 of 115 held; 1 flag added by someone later. Edge by run: +0.15, +1.16, −0.98, −2.98 as n went
  22 → 25 → 29 → 42, so the larger the sample, the worse the flags look. Ranked 2 (was 3): radar flags push to the phone.
  Nov 10 (Nov 10 08:55Z run): no better. `radar.edge` −2.96 z per game (flags −4.48 vs the comparison list −1.52,
  n=48), weak for the third run; `radar.held` 0.71 (34 of 48); across all flagged player-mornings 76 of 126 held; 5
  flags were added by someone later (was 1). Edge by run: +0.15, +1.16, −0.98, −2.98, −2.96 as n went 22 → 25 → 29 →
  42 → 48: it has settled near −3 rather than bounced back. Ranked 1 (was 2).
  Nov 10 (Q-045): most of that was the metric (today's ownership in the comparison list, open-ended "after", every
  player-morning counted). On the fixed metric, before Q-045's model fixes: every flag held 0.64 (n=42), edge −0.29
  (n=29); after: shown 0.70 (n=10), every flag 0.63 (n=38), edge +0.34 (n=25). This item's value gate is still unbuilt.
- **Expected impact:** fewer, better radar lines and pushes in both basketball leagues: a rising free agent is shown only
  when his new role is worth a roster spot in this league's categories, and the check compares him with what the site
  actually suggests now.
- **Effort:** S
- **Risk:** Low (ideas and at most one push a day per league; a gate can hide a one-category specialist, see the design)
- **Measure:** `radar.edge` (≥ 0.5 z per game with ≥ 10 flags, out of sample), `radar.held` (≥ 0.75)
- **Design:** `ops/designs/Q-036.md`
- **Decision:** —


### Q-045 · NBA radar health warnings came mostly from the metric; fix the backtest, then two small model fixes
- **Status:** shipped (74ba172)
- **Area:** `shq/radar_backtest.py` (`run`, `summary`, `report`, `inputs`), `shq/health.py` (`judge`, `MIN_N`, `radar_health`,
  new info check `radar.held_all`), `shq/radar.py` (`role`, `rising`, `may_fade`, `rank_key`, `block`, `riser_item`),
  `state/health_baselines.json` (`radar.held`, `radar.edge` re-set), `reviews/2026-11-10-nba-radar-backtest.md`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (from Claude Ops' diagnosis of the Q-036 warnings)
- **Evidence:** health.json Nov 10: `radar.held` 0.71 (drift) and `radar.edge` −2.96 (weak), both against baselines set Nov 3
  on n=5; the radar code hadn't changed since. The metric had three faults: (1) the "old suggestion" it compared with was
  ranked by today's % rostered, so later breakouts leaked into it; (2) "held" used every game after the flag (DNPs
  dropped) and counted each player-morning (178 for 48 players); (3) it scored every flag, while the site shows 4 a
  morning. Re-scored on the same data (logs through Nov 9, last 14 mornings with games, each free agent once at his first
  flag, his team's next 3 games, a missed game = 0 min, old suggestion by that morning's `state/nba_owned.json` reading):
  every flag held 27 of 42 (0.64), the 4 shown a morning 7 of 11 (0.64), edge −0.29 z per game (n=29, Nov 4-6 mornings).
  Model fixes tried on that backtest (before → after): (6) a "riser" who played under half his team's earlier games is
  back from an absence, not a riser: removes Marcus Smart, Oso Ighodaro, Caleb Martin, Kobe Brown (−7 to −11 z a game;
  three "held" only because their baseline was the games they sat): every flag 27/42 → 24/38, edge −0.29 → +0.34 (n=25),
  value −4.24 → −3.86. Shipped. (5) rank flags caused by an injured key teammate first, and label a jump with no cause
  and under 4 straight games "may fade" (those held 9 of 16, the rest 18 of 26): shown 7/11 → 7/10 (0.64 → 0.70), shown
  value −3.63 → −2.75. Shipped. (7) usage-only flags need 24+ recent minutes or a teammate's absence: removed 4 flags
  (2 held), edge −0.29 → −0.43, with 6: held 0.62 and edge +0.23, both worse than 6 alone. Not shipped. A
  "may fade last" order changed nothing in this sample, so may-fade is a label only.
  Not confirmed: the replay stands in "on ESPN's injury report" with "missed all 3 of his recent games" (old reports
  aren't kept), and ranks by fit over all 3-Ball categories without games left. Samples are small (10 shown, 25 for edge).
- **Expected impact:** the radar checks stop warning about a measuring error and track what the site shows; slightly
  fewer, better-ordered rising lines on both basketball tabs (no players just back from an absence; injury-driven jumps
  on top; unexplained short jumps say "may fade").
- **Effort:** S-M
- **Risk:** Low (ideas and at most one push a day per league; push rules unchanged)
- **Measure:** `radar.held` (shown, baseline 0.70, n=10, MIN_N 10), `radar.edge` (every flag, baseline +0.34, n=25, MIN_N 20,
  floor 0), `radar.held_all` (info, 0.63, n=38). `judge` now re-sets any stored baseline with n under the check's MIN_N.
- **Design:** as above. The window is the last 14 mornings with games (a period with no NBA games, e.g. Nov 3, repeats
  the morning before). MIN_N for the shown check is 10, not 20: the site shows ~10 different free agents per 14 mornings,
  so 20 would leave it waiting for good. Edge is judged on every flag (n=25); the shown-only edge (+2.22 on n=4) is in the
  notes. Q-036's value gate is not built; re-judge it on the new metric. Undo: `git revert` the commit (restores the old
  `state/health_baselines.json` radar rows too).
- **Decision:** built 2026-11-10 on Claude Ops' build request (the session that ran the diagnosis)

### Q-018 · The What to do card contradicts itself
- **Status:** designed
- **Area:** `shq/waivers.py` (drop protection), `shq/advice.py` (What to do card), IR-slot lines
- **Rank:** 2
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #7 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness, Nov 1, Guillotine page at 375px): Bids said "No free agent adds a point to your
  lineup" while Waiver adds said "Add Bryce Young … lineup +2.0/gm"; that add dropped J.K. Dobbins, whom Lineup moves said to
  start this week. Stempak and Bro-vid19 both cited a 9-day-old "ruled out" note (Oct 23) on an IR-slot line. Likely cause
  (not confirmed): `waivers.py:116` protects the best lineup on rest-of-season points, not this week's starters. No commits to
  `waivers.py` or `advice.py` since Nov 3 08:38 CT.
  Nov 7 nightly pass (replay of all 327 committed `lineups.json` snapshots, Oct 31-Nov 7 04:38Z, football leagues): a waiver
  drop was this week's start in 114 snapshots, 4 players: Kimani Vidal, Bro-vid19 (92, Nov 4-6: "Montgomery OUT → start
  Kimani Vidal" next to "Add Bryce Young … for Kimani Vidal"), J.K. Dobbins (11, Nov 1), Tre Tucker (6) and Zach Charbonnet
  (5), Guillotine, Nov 3-4. Cause confirmed: `waivers.adds()` protects the best lineup on rest-of-season ppg only
  (`waivers.py:116`). Guillotine add lines claiming "lineup +X/gm" that Bids didn't list: Bryce Young 208, Juwan Johnson 85,
  Brenton Strange 15, Jayden Daniels 4 (two horizons, neither labelled). IR lines citing a 3+ day old note: Montgomery
  (Oct 23 note, Stempak and Bro-vid19, 104 each, to Nov 1), Shaheed (2, Nov 3); `run.better_news()` (`run.py:68`) only
  refreshes notes under 30 characters. Also: Bro-vid19 lists Waiver adds while its IR line says ESPN blocks adds and drops
  (233 snapshots, incl. today). Today's snapshot has 0 cases, but `waivers.py` is unchanged since Oct 31: dormant, not
  fixed. Ranked 2 (was 13): it touches lineup decisions every week, with exact cases.
  Nov 9: ranked 3 (Q-036 moved above it); `waivers.py` still unchanged since Oct 31 (46076da), so the drop-protection
  cause stands; snapshots not replayed tonight.
  Nov 10: no change (no commit to `shq/` in 36 hours; `waivers.py` last changed Oct 31, 46076da). Ranked 2.
- **Expected impact:** one consistent set of moves per league; no drop of a player the card says to start.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: no league page where a waiver drop is also a lineup-move start)
- **Design:** `ops/designs/Q-018.md`
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
  Nov 9: worth more now. The cloud "Football pools picks" task was turned off Nov 8 (claude-audit `changes.md`), so a
  laptop picks run that fails but shows "succeeded" has no cloud twin behind it, and the backup can't build a card (Q-019).
  Nov 10: three more laptop tasks went live Nov 9 (the fantasy guards that replaced the cloud helpers, claude-audit
  `changes.md` "Overhaul 17"). Those push on a failure themselves; the daily sync and the picks tasks still don't.
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


### Q-019 · The picks backup has never worked for real
- **Status:** designed
- **Area:** `.github/workflows/picks-backup.yml`, `.github/workflows/run.yml`, `picks/pp/http.py`, GitHub secret `CFBD_API_KEY`
- **Rank:** 5
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #8 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Reliability): the backup's crons ran 4-7h late every time (Wed 9:45pm slot at 5:25am Thu;
  Sat 8:45am at 1:45pm, after CFP's 11am lock), and `pp/http.py:48` raises on any uncached CFBD call without a key. Nov 4:
  `gh secret list` still has no `CFBD_API_KEY` (NTFY_TOPIC, TOKEN_KEY and 3 Yahoo secrets only). Not confirmed: whether it
  could build a card at all. Nov 5: secret still absent.
  Nov 9 nightly pass: worth more, and confirmed broken. (1) Since Nov 8 the laptop is the only pool picker: the cloud
  "Football pools picks" task is off (claude-audit `changes.md`, "Pools cutover check (Nov 8)"). (2) In a clean clone
  with no key, `BACKUP=1 python -m pp.cards --stage draft` failed in 6 seconds: `RuntimeError: CFBD /lines not cached
  and no key/budget` (`pp/market.py:38` → `pp/http.py:48`); `gh secret list` still has no `CFBD_API_KEY`. (3) Its
  last 4 runs started 4-8h after the slot: Wed 9:45pm slot at Thu 5:31am CT (Nov 5), Thu 8:45pm at Fri 3:52am,
  Fri 9:45pm at Sat 4:40am, Sat 8:45am at 1:02pm (Nov 7, after CFP's 11am lock). All 8 runs "succeeded" only because
  the laptop had posted and the build was skipped. Ranked 6 (was 19).
  Nov 10: no backup run since Sat Nov 7; `gh secret list` still shows 5 secrets and no `CFBD_API_KEY`. This week's
  first slot is Wed Nov 11 9:45pm CT.
- **Expected impact:** a real fallback card when a laptop picks run is missed.
- **Effort:** M (plus one manual step for Michael: add the secret)
- **Risk:** Low
- **Measure:** — (one-off: a forced backup run builds a card)
- **Design:** `ops/designs/Q-019.md`
- **Decision:** —


### Q-005 · Far-week Sleeper projections aren't backtested yet
- **Status:** measuring
- **Area:** War Room v2 (`model.py` `SD_GROWTH`, `model.js` `swing`)
- **Rank:** 6
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The 1.25-pt-per-week swing growth was measured on the old blend (misses 23 → 27 from 1 to 4 weeks ahead);
  Sleeper's stored past projections are its latest, not what it showed weeks earlier. The page has carried Sleeper's projection
  for every remaining week since Nov 3, so the health job now scores what the page showed 2, 3 and 4 weeks before each week.
  First numbers after week 10 (2 weeks ahead), week 11 (3), week 12 (4). Nov 4: `wr.swing_k2`-`k4` still waiting (n=0).
  Nov 5: still n=0; the first 2-weeks-ahead number arrives with the health run after week 10 ends (Tue Nov 17).
  Nov 6: still n=0 (Nov 5 run); enough data for `wr.swing_k2` Nov 17, `k3` Nov 24, `k4` Dec 1.
  Nov 7: still n=0 (Nov 6 run); same dates. Nov 8: still n=0 (Nov 7 run); same dates.
  Nov 9: still n=0 (Nov 8 run); same dates.
  Nov 10: still n=0 for `wr.swing_k2`-`k4` (Nov 10 run); same dates. The section now also notes the 1-week-ahead miss
  as shown on the page: 13.4 pts (n=10).
- **Expected impact:** the right rest-of-season uncertainty, which drives win odds and so every value.
- **Effort:** S (change `SD_GROWTH` once measured)
- **Risk:** Low
- **Measure:** `wr.swing_k2`, `wr.swing_k3`, `wr.swing_k4` vs `wr.swing`
- **Design:** —
- **Decision:** —


### Q-017 · Four git steps still rebase (rule: merge, never rebase)
- **Status:** designed
- **Area:** `.github/commit_data.sh`, `.github/workflows/picks-backup.yml`, `war-room-v2.yml`, `yahoo-reauth.yml`
- **Rank:** 7
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Rule breaks" #1 and "Ranked improvements" #6
- **Evidence:** The review listed 5 rebase spots. On Nov 4 `git grep rebase` still finds 4: `commit_data.sh:8`
  (`git pull -q --rebase -X theirs`), `picks-backup.yml:67` (`git pull --rebase`), `war-room-v2.yml:48` (`--rebase -X theirs`),
  `yahoo-reauth.yml:41` (`--rebase`). `picks/pp/publish.py:72` is fixed (`--no-rebase --no-edit`). `feedback.yml` and
  `model-health.yml` already merge. Nov 5: same 4 lines. Note for the build: under a merge `-X theirs` means the remote, so
  the like-for-like swap is `-X ours` (see the design).
  Nov 10: the same 4 lines (`git grep -- --rebase .github`).
- **Expected impact:** the repo follows its own rule; no rewritten history when the data loop and a session push at once.
- **Effort:** S
- **Risk:** Low (the data loops keep this pass's data on a conflict, as today, via `-X ours`)
- **Measure:** — (one-off: `git grep -- --rebase .github` finds nothing)
- **Design:** `ops/designs/Q-017.md`
- **Decision:** —


### Q-013 · Model health scorecard on the site
- **Status:** designed
- **Area:** site (`docs/lib/`, owned by the dashboard redesign session)
- **Rank:** 8
- **Added:** 2026-11-03
- **Evidence:** health.json is published at `/data/health.json` but nothing shows it. Michael only learned about the Nov 3
  War Room findings because he asked. Nov 5: `docs/lib/core.js` still loads only lineups, weekly, status, digest and
  pick_lines (`FILES`, line 9); the Nov 4 health run (13 ok, 1 weak, 5 waiting, 4 info) is visible nowhere on the site.
  Nov 6: the Nov 5 run turned two NBA radar checks to drift (11 ok, 2 drift, 1 weak, 5 waiting, 4 info; Q-036), and
  nothing on the site or in a push says so; the new Players page (Q-027) is loaded through `SHQ.loadFile`, which this
  card could reuse for `health.json`. Nov 7: the Nov 6 run (12 ok, 1 drift, 1 weak, 5 waiting, 4 info) is still shown
  nowhere on the site. Nov 8: the Nov 7 run (11 ok, 1 drift, 2 weak, 5 waiting, 4 info) turned `radar.edge` weak
  (Q-036), and the site still shows none of it.
  Nov 9: the Nov 8 run (11 ok, 1 drift, 2 weak, 5 waiting, 4 info) is still shown nowhere on the site.
  Nov 10: the Nov 10 run (12 ok, 1 drift, 1 weak, 5 waiting, 4 info) cleared the cut-odds flag (`wr.cut_skill` ok,
  Q-012) and kept both radar flags (Q-036); the site shows none of it.
- **Expected impact:** a glance at which models are trustworthy this week (ok / watch / drift / weak per model, tap for the checks).
- **Effort:** S
- **Risk:** Low
- **Measure:** —
- **Design:** `ops/designs/Q-013.md`
- **Decision:** —


### Q-024 · The picks health check scores Yahoo straight-up picks against a spread break-even
- **Status:** designed
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
  Nov 10: unchanged (`graded_weeks` still 8 and 9); week 10's postmortem lands Tue Nov 10 8pm CT.
- **Expected impact:** a picks score that means something: BTO and CFP spread picks against 52.4%, Yahoo against the
  market favourite's straight-up record on the same games. Feeds Q-013's scorecard and Q-023's decision.
- **Effort:** S
- **Risk:** Low (health job only; the `picks.card_ats` baseline resets)
- **Measure:** — (one-off: separate spread and straight-up checks, each with its own floor)
- **Design:** `ops/designs/Q-024.md`
- **Decision:** —


### Q-016 · "Likely out" news doesn't trigger a push while ESPN still says Questionable
- **Status:** designed
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
- **Design:** `ops/designs/Q-016.md`
- **Decision:** —


### Q-011 · One guillotine model: the dashboard and War Room v2 still give different numbers
- **Status:** designed
- **Area:** `shq/guillotine.py` (dashboard, Today tab, cut-risk push) vs `warroom/` (War Room v2, bids.json, Tuesday checks)
- **Rank:** 11
- **Added:** 2026-11-03 (claude-audit item 1, option 4)
- **Evidence:** On Nov 3 the two models disagree for the same week 9: MoneyManChas cut risk 17.0% (dashboard) vs 21.5% (v2),
  robert8063 14.3% vs 12.6%, my projection 119.1 vs 118.8. They use different swings (dashboard per-player position SDs,
  about 27 per team; v2 measured 22), different price models (dashboard: boldest past bid share, $10 reserve per bid; v2:
  calibrated ladder, $5 reserve across all bids) and different values (dashboard: points gained; v2: win odds). The site shows
  the dashboard's bids, the Tuesday push uses v2's. Audit item 1 ("three models give three sets of numbers") recommended folding
  them into one after the redesign. Nov 4 health run, first scored waiver run (week 8): the dashboard's likely prices missed
  by $12.4 (`gd.dash_price_mae`, n=8) vs v2's $8.3 (`rec.est_mae`, n=6); the dashboard put Puka Nacua, Javonte Williams and
  Jonathan Taylor all at $43 (winners paid $57, $34, $27), v2 at $27, $33, $33.
  Nov 10 (health run of 08:55Z): the first same-week score as shown before kickoff. Week 9 (MoneyManChas cut): v2 gave
  him 32.1% and ranked him 1st (`gd.v2_skill` +0.507, n=1); the dashboard ranked him 2nd (`gd.dash_skill` −0.142 over
  weeks 8-9, n=2). Log-loss 1.136 vs 2.683, coin toss 2.35. Prices unchanged ($12.4 vs $8.3, one run). Tonight they
  also disagree on what I can do: the tab's week 10 Bids list Harold Fannin Jr., Pat Freiermuth, Brenton Strange and
  T.J. Hockenson as "priced out" (rivals $3-4, my max $0), while bids.json calls Strange, Freiermuth and Tyler Higbee
  "Add free" (waivers closed until Wed Nov 11). And v2 was still on week 9 at 3:55am CT Tue while the dashboard was on
  week 10 (late build, Q-037). Samples are 1-2 weeks. Ranked 11 (was 20).
- **Expected impact:** one answer everywhere (site, push, AI write-up); fixes found in one model reach every screen.
- **Effort:** M (dashboard reads bids.json for odds and bids; keeps its live Sunday locking until Q-002 lands)
- **Risk:** Med (the cut-risk push and Today tab change source)
- **Measure:** `gd.v2_skill` vs `gd.dash_skill` (which predicted cuts better as shown), `gd.dash_price_mae` vs `rec.est_mae`
- **Design:** `ops/designs/Q-011.md`
- **Decision:** —


### Q-022 · Old claude.ai helpers still give lineup and bid advice (and auto-swap) alongside Sports HQ
- **Status:** proposed
- **Area:** outside the repo: claude.ai routines "Fantasy football helper", "Fantasy basketball helper", "Guillotine strategy
  review", "Football pools picks"; Sports HQ rules (ROADMAP "Rules that must not break", `status.confirm`)
- **Rank:** 12
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #2 and IDEAS.md "Open decisions"
- **Evidence:** `reviews/2026-11.md` (Coverage vs goals): the football helper (Sun/Mon/Tue/Thu/Sat, 4×/day) and basketball
  helper (9am/5pm) still auto-swap lineups through Chrome, outside `status.confirm`; "Guillotine strategy review" (daily
  6:19am) runs alongside War Room v2; "Football pools picks" runs alongside Sports HQ Picks. Two systems give lineup and bid
  advice, with possible duplicate pushes. Open in IDEAS.md since Oct 28. ROADMAP "Where things stand" (Nov 4): the cloud pools
  task retires after the Nov 4-7 side-by-side; the rest is "Michael to decide". The claude-audit plan (`plan.md` Phase 2
  "One owner per job") holds the proposed owners; not yet executed per its `changes.md`. Nov 5: still no Decision.
  Nov 7: one of the four is settled: claude-audit `changes.md` (Nov 5) records the old cloud "Guillotine strategy review"
  turned OFF with Michael's approval (it had failed Nov 3-4 and pushed errors; War Room v2 replaces it). Still running:
  the football helper and basketball helper (auto-swaps outside `status.confirm`), and the "Football pools picks" task, whose
  side-by-side with Sports HQ Picks ends today (Nov 7). Still no Decision on the rest.
  Nov 8: the pools side-by-side is over; the one-time Claude Ops task `claude-ops-pools-cutover-auto` runs today 9:00am CT
  and turns the cloud "Football pools picks" task off only if Sports HQ covered everything. claude-audit `changes.md` has
  no entry since Nov 5, so both helpers (and their auto-swaps) still run.
  Nov 9: two of four settled. claude-audit `changes.md` "Pools cutover check (Nov 8)": the cloud "Football pools
  picks" task is OFF (confirmed `enabled=false`; Sports HQ covered every item, the cloud-only calls were judgment calls).
  Still running: the football and basketball helpers with their Chrome auto-swaps. `changes.md` also records that
  editing those laptop-bound routines is blocked for Claude ("Only Michael can make those edits"), so this needs his
  decision and his hands.
  Nov 10: all four are now off. claude-audit `changes.md` "Overhaul 17" (Nov 9, 8:40pm): Michael said "Cut over
  helpers"; the cloud football and basketball helpers were turned OFF and replaced by three laptop tasks ("Fantasy
  football: Sunday guard", "Fantasy football: prep + night guard", "Fantasy basketball guard"). Tuesday's pickups run
  no longer carries a guillotine bid plan, so Sports HQ is the only source of bid advice. What is left of this item:
  the guards keep the "same lineup-only zero-score swap rules as before", so lineup swaps through Chrome still happen
  outside `status.confirm`, and ROADMAP's "Rules that must not break" and its "Older claude.ai routines" row don't say
  so. The decision was made in claude-audit, not on this Decision line. Ranked 12 (was 1).
- **Expected impact:** one source of lineup and bid advice; no auto-swap that skips Sports HQ's injury confirmation; fewer pushes.
- **Effort:** S (a decision; the routine changes are a claude-audit batch)
- **Risk:** Med (turning off auto-swaps means Sports HQ's pushes are the only safety net for inactive starters; see Q-016)
- **Measure:** — (one-off: one owner per job in the claude-audit plan)
- **Design:** claude-audit `plan.md` Phase 2 (a decision, outside this repo)
- **Decision:** —


### Q-003 · Price ladder isn't split by position or season stage
- **Status:** designed
- **Area:** War Room v2 (`warroom/build.py` `ladder`, `model.js` `winChance`)
- **Rank:** 13
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
  Nov 5 health run (same 187 claims, no new waiver run): RB 34% at the 50% price and 66% at the 80% price (n=35, estimate
  miss $18.9); WR 48% / 75% (n=61); K 90% / 95% (n=20); DEF 58% / 96% (n=24); legs 5-8 estimate miss $5.5 vs $12.5 for 1-4.
  The week 9 waiver run (after Mon Nov 9's game) adds the next claims.
  Nov 6 health run (17:43Z, same 187 claims): RB 37% / 69% (n=35, estimate miss $18.8); WR 49% / 75% (n=61); QB 70% / 87%
  (n=23); K 90% / 95% (n=20); DEF 58% / 96% (n=24). The miss sits in the big claims: estimate $10+ won 51% at the 50% price
  (n=55, miss $18.4) vs 59% under $10 (n=132, miss $5.0); overall `wr.ladder_cov50` 0.57, `wr.ladder_cov80` 0.82.
  Nov 7: worth less for the rest of this season: bids.json (Fri 8:51am CT) shows my FAAB at $10 ($5 spendable), waivers
  closed until Wed Nov 11, week 9 rows 9 Add free and 5 Skip. The ladder now matters mostly for reading rivals' prices and
  for next season. Ranked 11 (was 2).
  Nov 8 (Nov 7 run): same 187 claims and the same splits (RB 37% / 69%, n=35); next claims after the Wed Nov 11 run.
  Nov 9 (Nov 8 run): same 187 claims; RB 34% at the 50% price, 69% at the 80% (n=35, estimate miss $18.7); next
  claims after the Wed Nov 11 run.
  Nov 10 (Nov 10 run, 190 claims, 3 more): RB 31% at the 50% price and 67% at the 80% (n=36, estimate miss $18.1);
  WR 48% / 73% (n=63); QB 70% / 87% (n=23); K 90% / 95% (n=20); DEF 58% / 96% (n=24); overall `wr.ladder_cov50` 0.55,
  `wr.ladder_cov80` 0.81. Next claims after the Wed Nov 11 run.
- **Expected impact:** RB claims (the most expensive position) won at the stated odds instead of lost; no overbidding on K/DEF.
- **Effort:** S
- **Risk:** Low-Med (splits get thin: keep the "at least 12 claims or merge" rule; test leave-one-run-out before shipping)
- **Measure:** `wr.ladder_cov50`, `wr.ladder_cov80` and their `by` splits (RB at 80% should reach about 0.8)
- **Design:** `ops/designs/Q-003.md`
- **Decision:** —


### Q-002 · Mid-week, War Room v2 ignores games already played
- **Status:** designed
- **Area:** War Room v2 (`model.py` / `model.js` `proj`)
- **Rank:** 14
- **Added:** 2026-11-03 (warroom/README.md "Known limits")
- **Evidence:** From Thursday night to Monday, the coming week's projections ignore games already played; only the dashboard
  (`shq/guillotine.py`) locks started games and uses real points. v2's cut risks on Fri-Mon are pre-kickoff numbers.
  Nov 7 nightly pass (code read for the design): nothing is partly built; `model.py` `build()` never fetches the current
  week's matchups. v2 barely rebuilds on game days: the only Thu-Mon slot (6:10am CT daily) ran 6-9.5h late Nov 1-6
  (started 11:54am-3:40pm CT; Sunday Nov 1's 6 minutes before kickoff). The dashboard's stored snapshots gave week 8's cut
  team 1.9% Thursday, 2.3% Sunday 11:57am CT, 96.1% Monday 7:07pm CT, so the gain shows Sunday night and Monday, not
  Sunday morning. No mid-game v2 history is stored (bids.json versions only since Oct 31).
- **Expected impact:** live cut risk on game days from the same model as the bids; a prerequisite for Q-011 (one model).
- **Effort:** M (lock started players at their real points, zero swing for finished games, like `guillotine.entry`)
- **Risk:** Low
- **Measure:** a Sunday-morning version of `gd.v2_skill` (add when built)
- **Design:** `ops/designs/Q-002.md`
- **Decision:** —


### Q-012 · Cut odds are no better than a coin toss
- **Status:** designed
- **Area:** War Room v2 (`warroom/model.js` `simulate`), dashboard (`shq/guillotine.py`)
- **Rank:** 15
- **Added:** 2026-11-03 by the first model-health run
- **Evidence:** Rebuilding each of the 8 past weeks from Sleeper's projections, the team actually cut ranked 14th, 11th, 9th,
  1st, 1st, 11th, 1st and 10th by predicted risk (average 7th). At the measured 22-pt swing the cut odds score a log-loss of
  2.71 vs 2.66 for treating every team as equally likely (skill −1.7%); wider swings score better (27: +0.7%, 36: +2.3%), and
  the measured swing can't fix the ordering. The dashboard gave week 8's cut team 1.9% before kickoff (10th of 11). 8 cuts is
  a small sample, and the 22-pt swing is measured on the same weeks (in-sample). Nov 4: still the only health flag
  (`wr.cut_skill` −0.017, floor 0.0, n=8, status weak); week 9's cut (after Mon Nov 9's game) adds a 9th case.
  Nov 5: unchanged (same run); `gd.v2_skill` still waiting (n=0), `gd.dash_skill` −0.653 (n=1).
  Nov 6: unchanged in the Nov 5 run (−0.017, n=8, best swing 36); the 9th cut lands after Mon Nov 9's game.
  Nov 7 nightly pass (read-only replay of weeks 1-8 for the design): 36 is only the edge of the health grid (14-36); in
  sample, skill keeps rising to +2.7% at a 45-55 swing. Chosen out of sample (leave one week out), every fix loses to a coin
  toss: one wider swing −5.8%, odds shrunk toward equal −3.6%, heavier tails −2.9%, per-team swing −5.7%; the chosen swing
  jumps between 27 and 120 by left-out week. If the 22-pt model were right, a log-loss of 2.71 or worse over 8 cuts happens
  about 9% of the time. Week 9's two models agree on order (bottom two 29.5%/29.5% v2 vs 26.6%/23.0% dashboard). And my FAAB
  is $10 ($5 spendable, bids.json Fri 8:51am CT: 9 Add free, 5 Skip), so the bid impact is small now. Ranked 12 (was 11).
  Nov 8: unchanged in the Nov 7 run (−0.017, n=8, best swing 36).
  Nov 9: unchanged in the Nov 8 run (−0.017, n=8, best swing 36); the 9th cut lands after Mon Nov 9's game.
  Nov 10 (Nov 10 run): week 9's cut is in (n=9) and the flag cleared. The cut team was ranked 1st by predicted risk
  (ranks now 14, 11, 9, 1, 1, 11, 1, 10, 1; average 6.6); `wr.cut_skill` +0.032 at the 22-pt swing (was −0.017), ok
  against its baseline; a 36-pt swing still scores best (+5.4%), all in-sample. As shown before kickoff, v2 gave the
  week 9 cut team 32.1% (`gd.v2_skill` +0.507, n=1; `gd.dash_skill` −0.142, n=2). One good week doesn't settle it:
  the Nov 7 replay found every fix lost out of sample. Ranked 15 (was 13).
- **Expected impact:** cut risk and win odds drive every bid value. If cuts are mostly upsets, both models are too sure who is
  safe, so win-odds gains (and bids) are spread too wide between players. Better-calibrated odds = better $ values.
- **Effort:** S to test, M to change
- **Risk:** Med (moves every bid value)
- **Measure:** `wr.cut_skill`, `gd.v2_skill`, `gd.dash_skill`, `wr.best_sd` in health.json
- **Design:** `ops/designs/Q-012.md`
- **Decision:** —


### Q-021 · Hygiene pass: line endings, public CFBD files, worktrees, browser rule
- **Status:** designed
- **Area:** `picks/pp/grade.py`, `picks/pp/model.py`, `picks/cache/cfbd/`, `.claude/worktrees/`, ROADMAP.md, laptop prompts
- **Rank:** 16
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Rule breaks" #2-4 and "Ranked improvements" #10, and
  IDEAS.md "Proposed by monthly review" (last two lines)
- **Evidence:** Still true Nov 4: `git ls-files --eol` shows `i/crlf` for `picks/pp/grade.py` and `picks/pp/model.py`; 17 files
  under `picks/cache/cfbd/` are tracked (raw CFBD responses in a public repo, against `.gitignore:13-16`); `.claude/worktrees/`
  holds 5 folders (analytics-sources, friendly-tu-4f1575, nice-hamilton-b16e8b, sweet-euler-ce89af, vigilant-dewdney-33aa4d;
  not confirmed which are merged); ROADMAP.md:207 still says "use Chrome" with no exception for the public-site 375px check
  that needs the built-in browser's viewport emulation. The review also found the daily-sync prompt hard-codes the ntfy
  topic and that laptop prompts lack copies in `ops/tasks/`; not re-checked tonight. Nov 5: the first three checks are
  unchanged (2 CRLF files, 17 tracked CFBD files, the same 5 worktrees); `ops/tasks/` still has no daily-sync copy.
  Nov 8 nightly pass (for the design): still 2 `i/crlf` files and 17 tracked CFBD files; 6 extra worktrees now (adds
  improvements-nov5-6ed372), all 6 clean and every HEAD already in `main`; ROADMAP's rule is at lines 126 and 220; the live
  daily-sync prompt still writes the ntfy topic inline (0 references to `picks/.ntfy_topic`) and has no `ops/tasks/` copy.
- **Expected impact:** the repo follows its own rules; nothing raw from CFBD stays public; less clutter.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off: the four checks above come back clean)
- **Design:** `ops/designs/Q-021.md`
- **Decision:** —


### Q-009 · The 0.3-point win-odds noise floor is a guess
- **Status:** designed
- **Area:** War Room v2 (`model.js` `MIN_WIN`)
- **Rank:** 17
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Moves adding under 0.3 points of win odds are skipped as noise, but the real noise of `gains()` (10,000 seasons,
  same seed for both sides) has not been measured.
  Nov 8 nightly pass: with my win odds at 5% the calls now sit on the floor. bids.json (Nov 7 17:43Z): Pat Freiermuth and
  Tyler Higbee "Add free" at +0.003 (the floor itself, as stored), Dominic Zvada "Skip" at +0.002, three more at +0.001;
  9 of 14 rows are free adds. The page compares at 3,000 seasons, bids.json at 10,000 (`S.sims / 2`), so near the floor
  the two can differ (Q-006). Ranked 15, one above Q-007, whose replay needs this floor first.
  Nov 9: bids.json (Nov 8 17:53Z, 14 rows): Pat Freiermuth and Tyler Higbee "Add free" at +0.004, BAL DEF "Skip" at
  +0.003 (rounded), NE DEF, BUF DEF and Dominic Zvada "Skip" at +0.002: 6 calls within 0.002 of the floor.
- **Expected impact:** small free adds stop being dropped (or noise stops being recommended).
- **Effort:** S (rerun `gains` with several seeds, set the floor at about 2 standard errors)
- **Risk:** Low
- **Measure:** one-off (share of rows whose call flips across 20 seeds, under 5%); then fixed
- **Design:** `ops/designs/Q-009.md`
- **Decision:** —


### Q-007 · Free-agent candidates are capped (3 per position, 24 total)
- **Status:** designed
- **Area:** War Room v2 (`model.js` `candidates`)
- **Rank:** 18
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Only the top 60 free agents by projected points are tried, then at most 3 per position and 24 overall. The old
  cap of 2 per position hid Bo Nix (audit). A bye-week fill-in or a K/DEF stream can rank 4th at its position and vanish.
  Nov 8 nightly pass: bids.json (built Nov 7 17:43Z) has 14 rows, QB 3, DEF 3, TE 3, K 3, WR 2: the per-position cap
  binds at four positions (the 24 total doesn't). With $5 spendable, free adds (9 of 14 rows) are most of what v2 can
  still do for me, so the cap decides which ones I see. Not confirmed: whether a 4th-ranked player would have cleared
  the floor (Node isn't on the laptop; the design's replay runs in GitHub Actions).
- **Expected impact:** no useful free add silently missing.
- **Effort:** S (raise the caps; check build time)
- **Risk:** Low (slower build)
- **Measure:** one-off: free agents beyond the cap that would add more than the noise floor
- **Design:** `ops/designs/Q-007.md`
- **Decision:** —


### Q-006 · The page runs 6,000 seasons, bids.json 20,000
- **Status:** designed
- **Area:** War Room v2 (`model.js` `S.sims`, `export.js`)
- **Rank:** 19
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The page uses 6,000 so the sliders respond quickly; bids.json, the Tuesday push and the AI write-up use 20,000.
  The audit measured ±0.3-0.7 pts of noise at 2,000. Near a call boundary (0.3-pt noise floor, Bid vs Coin flip at 50%)
  the page can show a different call than the push.
  Nov 9 nightly pass (code read for the design): the page compares each add at 3,000 seasons (`S.sims / 2` of 6,000,
  `model.js:166`, `:184`), bids.json at 10,000 (`export.js:12` sets 20,000); both use the same seed
  (`rng(20261027)`, `model.js:74`), so at equal sizes they would agree exactly. bids.json (Nov 8 17:53Z): 6 of 14 calls
  sit within 0.002 of the 0.003 floor (Q-009). Not confirmed: how many differ on the page today (needs Node).
- **Expected impact:** the page always matches the push at default settings.
- **Effort:** S (inline bids.json's default-setting results in the page and recompute only when a slider moves)
- **Risk:** Low
- **Measure:** rows whose call differs page vs bids.json (one-off check)
- **Design:** `ops/designs/Q-006.md`
- **Decision:** —


### Q-023 · College ATS cards still tilt 10% toward a stats model the backtest says to drop
- **Status:** designed
- **Area:** Pool Picks (`picks/pp/cards.py` `MODEL_W`, `fair_margins`)
- **Rank:** 20
- **Added:** 2026-11-04 by the nightly pass (own finding from health.json `sections.picks` and `picks/backtest/2026_w1-8.json`)
- **Evidence:** health.json `picks.brier_gap` = 0.028 (model Brier 0.195 vs market 0.168, n=444 college games). In the backtest
  file's `model_weight` report, the walk-forward choice was weight 0 in all 6 weeks scored (3-8): total RMSE 14.059 at 0
  (= market only) vs 14.099 at the fixed 0.1. Over weeks 1-8, ATS picks where the model disagrees with the market by 3+ pts
  hit 48.9% (n=274). Against: weeks 6-8 alone lean slightly the other way (best weight 0.087 ± 0.236; disagreements hit 54.5%,
  n=77). NFL already went to 0 (`picks/pp/nfl.py:76`); college stays at 0.1 (`cards.py:105`, ROADMAP "MODEL_W stays 0.1").
  Nov 5: `picks.card_ats` now reports 0.733 (n=30), but 25 of those 30 are Yahoo straight-up picks (Q-024), so it can't
  judge this yet. Nov 6: unchanged (Nov 5 run). Nov 7: unchanged (Nov 6 run: `picks.brier_gap` 0.028, n=444). Nov 8: same.
  Nov 9 (for the design): weeks 9 and 10 have been played since the backtest (weeks 1-8), so they can serve as the
  out-of-sample test; in the walk-forward, 0.1 beat the market in weeks 6 and 7 (14.330 vs 14.378, 13.345 vs 13.361)
  and lost in 3-5. `pp.backtest --through N` writes `2026_w1-N.json`; `cards.py:763` and `health.py:532` read
  `2026_w1-8.json` by name.
  Nov 10: unchanged, and it can't change: the backtest file is still `2026_w1-8.json` (written Oct 31), so
  `picks.brier_gap` (0.028) and `picks.stale_cover` (0.616) have matched their baselines exactly since Nov 3. Weeks 9
  and 10 are played; the design's first step (re-run through week 10 on the laptop) would refresh both.
- **Expected impact:** small: college card centers move by a tenth of the model-market gap (a 5-pt gap = 0.5 pt), which
  only matters near a pool line's half point.
- **Effort:** S
- **Risk:** Low
- **Measure:** `picks.card_ats` (spread picks only, once Q-024 splits it) and the next backtest's walk-forward RMSE
- **Design:** `ops/designs/Q-023.md`
- **Decision:** —


### Q-025 · War Room v2's budget step drops a claim instead of fitting it
- **Status:** designed
- **Area:** War Room v2 (`warroom/model.js` `decideAll`, lines 222-233; `bidOptions`)
- **Rank:** 21
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
  Nov 7: worth little for the rest of this season: my FAAB is $10 ($5 spendable, bids.json Fri 8:51am CT), so there is
  no budget left to share between claims. Ranked 21 (was 14).
  Nov 10: unchanged (still the one run; the next is Wed Nov 11 with $5 spendable). Designed tonight: the fix is
  small, and the lost coin flips came from low price estimates (Q-003, Q-004), not from this step.
- **Expected impact:** the claims that share the budget are chosen together for the best total expected surplus, instead of
  first-come; fewer budgets spread thin over 40% coin flips.
- **Effort:** S (a small knapsack over each claim's bid options, which `bidOptions` already lists)
- **Risk:** Med (changes which claims get money each week)
- **Measure:** `rec.would_win`, `rec.win_brier`, and `bargains_skipped` in `sections.recs.details`
- **Design:** `ops/designs/Q-025.md`
- **Decision:** —


### Q-010 · Automatic $ per win-point assumes every future crop looks like this week's
- **Status:** designed
- **Area:** War Room v2 (`model.js` `autoDpp`)
- **Rank:** 22
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** `autoDpp` lines up this week's freed players by win odds per $, assumes a similar crop at every waiver run you're
  expected to see, and takes the rate where FAAB runs out. Crops vary a lot: the top winning bids per run were $150 (wk 1),
  $156 (wk 2), $80 (wk 3) (health.json `recs.details.winners_paid`). The audit called $ per extra week "the biggest lever, and
  a guess"; this replaced the guess with one week's sample.
  Nov 10 (for the design): crops also shrink as the league's money drains. The six biggest winning bids per run
  added up to $342, $310, $301, $248, $154, $223, $167, $174 over weeks 1-8 (same source); top bid per run $150, $156,
  $80, $65, $57, $103, $56, $57. Between runs the rate is empty: bids.json (Nov 9 22:15Z) has
  `dollars_per_win_point: null`.
- **Expected impact:** steadier bid values week to week; less risk of overspending on a weak crop or hoarding before a strong one.
- **Effort:** M (estimate future crops from the remaining rosters: who is likely cut next and what they hold)
- **Risk:** Med (changes every value)
- **Measure:** `rec.would_win`, spending pace vs weeks survived (to add to health once bids have outcomes)
- **Design:** `ops/designs/Q-010.md`
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

### Q-035 · F1: no player list for the football leagues either
- **Status:** verified (ea3c058)
- **Area:** `shq/nfl_players.py` (new), `shq/advice.py` (`football_players`), `shq/run.py` (writes `docs/data/players_nfl.json`),
  `shq/espn_fantasy.py` (public football leagues read 50 free agents, was 12), `docs/players/index.html` (football view),
  `docs/lib/core.js` (Players button on football league pages)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item F1)
- **Evidence:** football rankings by position still came from FantasyPros; HQ had only waiver adds and trade ideas.
  Verified 2026-11-06 (nightly pass, `docs/data/players_nfl.json` of 09:17Z): all 6 football leagues, each player with
  `ros_rk` and `proj_rk`: Domo Arigato 509 players, Guillotine 301, 3-Ball FB 278, Bro-vid19 250, Stempak 195, Kosmonauts 97
  (marked partial, as designed).
- **Expected impact:** rest-of-season and weekly ranks by position for every football league without leaving HQ.
- **Effort:** M
- **Risk:** Low
- **Measure:** — (one-off)
- **Design:** per league, every rostered player (mine, each other team) plus the best FA_KEEP (150) free agents. ROS = Sleeper's
  projections for the next 4 weeks scored with the league's settings, per game played (`values.ros_ppg`, the same numbers
  the waiver adds and trade finder use; QB/RB/WR/TE). This week = the league's own projection (ESPN for ESPN leagues,
  Sleeper for Sleeper leagues and Kosmonauts), as on the lineup tab. Ranks are by position among those players; K/DEF rank
  on this week only. FantasyCalc dynasty or redraft value and the next 4 weeks are shown too. Choices: a separate data
  file (`players_nfl.json`, ~350 KB before Pages' gzip) so the basketball view stays light; the same page with football
  tabs after the basketball ones and football-specific columns (no category filters or trade tray; football trades
  already have the trade finder); Kosmonauts is marked partial (other rosters need the Yahoo API); 3-Ball FB's public
  read now asks ESPN for 50 free agents like the laptop snapshot, so its free-agent ranks aren't 12 players deep.
  Also fixed while building this: the NBA row label had been stored as "val", which football rows use for FantasyCalc
  (football league pages' roster rows broke for about an hour on Nov 5); it is "cv" now (commit 5821d51).
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-034 · B6: no way to check an NBA trade in category terms
- **Status:** verified (90dd05c)
- **Area:** `shq/nba_trade.py` (new), `shq/advice.py` (`player_values` adds the trade fields), `docs/players/index.html` ("⇄ Trade
  check" mode and tray), `docs/data/players.json` (`above`, `dyn`, `trade`)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B6)
- **Evidence:** ROADMAP: "NBA trade values … not covered: no free value API"; trades were judged by hand or on FantasyPros.
  Verified 2026-11-06 (nightly pass, `players.json` of 09:17Z): both leagues carry the `trade` block and every player has
  `above` (value over waiver level); 3-Ball players also carry `dyn` (dynasty value with age). Not checked: the tray on a
  phone screen.
- **Expected impact:** pick players, get a verdict in each league's own categories, with dynasty age built in for 3-Ball.
- **Effort:** M
- **Risk:** Low (ideas only; the age curve is a rule of thumb and says so)
- **Measure:** — (one-off)
- **Design:** each player's value per game above a waiver-level player, floored at 0 (someone below that level would be dropped
  for a waiver player, so an n-for-1 is judged fairly; a player with no NBA team counts 0). Fit = that gain plus (weight − 1) ×
  the per-category change, weights from where my top 10 rank among the teams' top 10 by category (bottom third 1.5, top third
  0.5, else 1, rescaled to average 1). 3-Ball (dynasty): value above waiver level × an age multiplier (1.5 at 20, 1.3 at 22,
  1.1 at 24, 1.0 at 25-28, then 0.9, 0.8 … 0.4 at 34+) plus 0.6 per year under 23, and the verdict uses it; ages from ESPN's
  team rosters (`shq/nba_ages.py`). Verdict: accept / decline, "coin flip" within 0.5. Choices: built into the Players page
  (tap + on any rostered player, a tray at the bottom) rather than a separate page, so the filters help find targets; the
  JavaScript verdict mirrors `nba_trade.trade()`, which carries the tests (live check Nov 5: SGA for Wembanyama in 3-Ball,
  both gave +11.7 dynasty, +7.3 now, +6.9 fit). The age curve isn't fitted to data; the tray says so.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-033 · B7: "proj 0.0" everywhere in the category leagues
- **Status:** verified (83fdf01)
- **Area:** `docs/lib/core.js` (`S.leagues` pending outlook, `scoreHTML`; roster rows since Q-026), `docs/lab/b`, `docs/lab/d`,
  `shq/leagues.py` (`view` proj, `EspnLeague.best_fa`), `shq/swap.py` (`strength`, `strength_text`), `shq/run.py` (injury-watch
  push text), `shq/digest.py` (`_fix`), `shq/advice.py` (free agents get values too)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B7)
- **Evidence:** Nov 5: every NBA player showed "proj 0.0"; the injury watch's NBA swap push read "start X (0.0 proj)" and
  picked the bench player by a projection that is always 0 (in practice the first one listed); a tile without this week's
  category table showed "0.0 projected".
  Verified 2026-11-06 (nightly pass, data of 09:17Z): no "proj 0.0" / "0.0 proj" text in any basketball line of
  `lineups.json`, `weekly.json` or `digest.json` (the only two hits are football: "170.0 projected" and a K drop, Chris
  Boswell 0.0 proj). NBA roster rows still carry `proj: 0.0` in the data, but `core.js` `prow` shows the value rank when a
  row has `cv` and a blank for 0, and NBA tiles take the category branch (`core.js:78-80`). Not checked on a phone screen.
- **Expected impact:** less noise; every number on a basketball page means something.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off)
- **Design:** roster rows show the value rank and "Value #33 · +1.9/g · this week +10.6 · 6 g" (Q-026). Tiles and league pages
  show the category outlook, or "Category outlook fills in with this week's matchup data · vs <opponent>" until the table
  exists; `view()` writes `proj: null` for NBA. Every NBA ranking that used points now uses category value (`swap.strength`:
  value per game when a player has one, else points): the injury watch's bench pick, the digest's "start X", the best free
  agent; their text says "value +1.9/g, #33". Layout D shows "#33". Choice: the Players page and the category table are the
  outlook; no new per-player outlook number was added. Fix the same evening: the NBA label was first stored as "val", which football rows already use for the
  FantasyCalc value, so football league pages' roster rows could not render and `swap.strength` failed on football rows; it is
  "cv" now, with a test.
- **Decision:** approved 2026-11-05 (Michael, via Claude Ops)

### Q-031 · B4: no games grid or streaming plan for the basketball leagues
- **Status:** verified (c3b56e7)
- **Area:** `shq/nba_games.py` (new), `shq/advice.py` (`games` block), `docs/lib/core.js` (`gamesHTML`, "Games & streamers")
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B4)
- **Evidence:** the tabs showed games left only per player and in the category table; no team schedule view, no next week,
  no streaming plan (FantasyPros / Hashtag-style grids done by hand).
  Verified 2026-11-06 (nightly pass, `lineups.json` of 09:17Z): both basketball leagues carry the `games` block: this
  week Fri Nov 6-Sun Nov 8 (16 teams with 2 games, 7 back-to-backs), next week Mon Nov 9-Sun Nov 15 (14 teams with 4);
  3-Ball 25 games left vs 26, 52 next week; Ball is Life 21 vs 18, 42 next week; 3 streamers each.
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

### Q-028 · B3: NBA pickups were ranked by % owned, not by what they do for my categories
- **Status:** verified (168a299)
- **Area:** `shq/nba_swaps.py` (new), `shq/nba_ages.py` (new), `shq/nba_values.py` (age), `shq/advice.py` `adds`, `shq/run.py`
  `nba_weekly_section`, `docs/players/index.html` (age in the detail row)
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal (item B3)
- **Evidence:** Nov 5: "Collin Gillespie (PG, PHX): 2 games left this week, 38% owned" style lines, sorted by games then
  % owned; Kevin Porter Jr. (no NBA team) sat on the 3-Ball bench unflagged.
  Verified 2026-11-06 (nightly pass, `docs/data/lineups.json` of 09:17Z): 3-Ball has 2 exact swaps ("Drop Kevin Porter Jr.
  (no NBA team, a dead roster spot), add Alex Caruso … +1.2 this week (helps FG%)"; "Drop De'Andre Hunter …, add Derrick
  Jones Jr. … +7.1 this week (helps FT%, STL, BLK). Dynasty: De'Andre Hunter is 29."); Ball is Life says "No free agent beats
  anyone on your roster by enough this week." (the +3 minimum). Whether the adds out-produce the drops isn't measured yet.
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

### Q-026 · B1: NBA players had no value (every one showed "proj 0.0")
- **Status:** verified (70ff3ff)
- **Area:** `shq/nba_values.py` (new), `shq/radar.py` `fetch_pool`/`compact` (adds ESPN's season projection and games played),
  `shq/advice.py` `player_values`, `shq/run.py` (writes `docs/data/players.json`), `docs/lib/core.js` `prow`
- **Rank:** —
- **Added:** 2026-11-05 from the claude-audit proposal `sports-hq-improvements-2026-11-05.md` (item B1)
- **Evidence:** Nov 5 6am: every NBA player showed "proj 0.0" (category leagues have no points); ROADMAP listed "NBA trade
  values and ROS waiver ranking: not covered"; pickups were ranked by % owned.
  Verified 2026-11-06 (nightly pass, `docs/data/players.json` of 09:17Z): 3-Ball BB 310 players and Ball is Life 303, every
  one with a value (0 missing, 0 at exactly 0); 251 / 244 on this season's stats, 59 / 59 on ESPN's projection; my rosters
  20 and 17 players.
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
