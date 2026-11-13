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
  Nov 11: Tue Nov 10's War Room builds started 6:58am and 7:37am CT, before this shipped that evening; the laptop's
  "Kick war room" task is registered Sun Nov 15, so Tue Nov 17 is the first Tuesday the Measure can count. Since Nov
  10 05:00Z, 18 `run.yml` runs (9 laptop dispatches, 9 scheduled), all succeeded, none cancelled; model health was
  kicked at 2:55am CT (08:55Z Nov 11).
  Nov 13: still waiting for Tue Nov 17. Since Nov 11 05:00Z, 40 `run.yml` runs (17 scheduled, 23 laptop dispatches),
  none cancelled; one dispatch failed (Thu Nov 12 1:02pm CT, run 43285972190; cause not checked tonight). War Room v2's
  last 10 runs (Nov 10-12) all succeeded; model health was kicked at 08:55Z Nov 12 and Nov 13.
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

### Q-043 · Traded players and new starters get zero or old-team rest-of-season numbers after the trade deadline
- **Status:** shipped (ce89445). Follow-up fix shipped the same evening (Tue Nov 10, see **Follow-up** below).
- **Follow-up (regressions found ~6:20pm):** (1) IR placement was read from ESPN's injury entry date, which is the latest
  blurb's (Etienne, on IR since Oct 1, read [0, 0, 0, 0] / ROS 0.0 after a Nov 4 / Nov 11 00:05Z blurb, and Kosmonauts
  said drop him for Geno Smith; Iosivas, Legette too). Now `state/ir_seen.json` records the first run that saw each IR
  tag (`ir_placed`; merged key by key like alerts.json); no record and no IR news in the last 7 days = minimum served;
  never zero weeks while Sleeper projects him > 0 this week. (2) The fill made up a this-week number for players
  status.confirm had softened to Q (Davante Adams, Sleeper IR: 13.8 in week 10, "Add Davante Adams (13.8/gm)" in
  Stempak; Mike Evans, Sleeper Out: 18.1) and for Doubtful players (Stevenson, Kyler Murray in the ESPN leagues). Now this
  week is never filled (no live projection = 0), and fill eligibility comes from the raw worst tag of every source
  (`raw_status`, `DEAD`: Doubtful/Out/IR/PUP/SUSP/NA). (3) A fill-in QB was filled through weeks his hurt starter is
  projected back (Drew Lock 18.7 in weeks 12-13 with Darnold back; Cousins 17.2 in weeks 11-13 with Murray back). Now a
  QB's stale or missing week is 0 when a teammate who is hurt now is projected there as the starter (≥ 100 pass yards and
  ≥ 60% of the fill); a healthy benched teammate's stale rows don't block a new starter (Mendoza case). (4) Not changed:
  `shq/status.py` `confirm` also reads ESPN's note date as the designation date (Cam Skattebo: ESPN Out, Tuesday
  21:38Z note says full practice, so OUT stands). Softening that would risk leaving a truly out player in a lineup and
  there is no designation date to use instead, so it stays as is. Code: `values.week_fills`, `live_points`,
  `raw_status`, `_qb_starter_back`, `ir_placed`/`load_ir_seen`/`save_ir_seen`, `.gitattributes`; tests: new classes in
  `tests/test_trade_deadline.py` (`IrPlacement`, `ReallyOut`, `QbRoom`; two IR tests updated to the new placement rule).
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
  Nov 13: the new `moved` health section (Q-057) can judge this from the week 10 run (Tue Nov 17, the first week after
  the deadline). Week 9 (before it): of 132 hurt, traded or new-starter players, 0 projected at 0 scored 5+
  (`moved.zeroed` 0) and 0 projected at 5+ sat (`moved.inactive` 0). Not checked tonight: `players_nfl.json` row by row.
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

### Q-047 · NBA league tabs contradicted themselves: radar "start him" vs "Drop him", a benched shrinking player "kept in the lineup"
- **Status:** shipped (b9ccfcd); follow-up shipped (f9159e2): a "may fade" riser the Waiver adds drop gets the swap on
  the radar ("rise may fade (no teammate's injury behind it); Waiver adds swaps him for X (+N this week)"), not a start
  verdict (Draymond Green, Ball is Life, Nov 10; Michael's call via Claude Ops: may-fade risers stay droppable);
  follow-up shipped (70976c8): Waiver adds swaps never drop a player today's Lineup moves start
- **Area:** `shq/radar.py` (`fades`, `block`'s `keep` and `shrink_ids`, `agree`, bench riser tag), `shq/nba_swaps.py` (drop
  filter, so also the weekly plan's adds), `shq/categories.py` (`build(skip)`, `_starting`), `shq/nba_lineup.py`
  (`start_key` on a move), `shq/advice.py` (chase rebuilt with the radar's shrinking ids; radar verdicts after Lineup moves)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (via Claude Ops)
- **Evidence:** live site Tue Nov 10 (data 23:27Z): Ball is Life's radar said "Obi Toppin … on your bench: start him" while
  Waiver adds #1 said "Drop Obi Toppin"; the weekly plan said "Drop Draymond Green" while the radar had him rising.
  3-Ball BB's chase said "FG% is close. Keep in the lineup: Jarrett Allen" with Allen on the bench and in the radar's
  shrinking list (minutes 28 → 18); the radar said "start him" for Dosunmu, Podziemski and Giddey with Lineup moves empty.
- **Expected impact:** one answer per player on an NBA tab. A rising player of mine isn't a drop unless the radar says his
  rise may fade; "Keep in the lineup" names only current starters who aren't shrinking; "start him today" only when Lineup
  moves starts him, otherwise "worth a start on his next game day (no game today)", "worth a start next game (today's game
  has started)", "consider starting him if he plays (Q today)" or "consider starting him (no lineup move today: his season
  value doesn't beat a starter who plays today by 1+ value/g)".
- **Effort:** S
- **Risk:** Low (advice text and drop candidates only; a protected riser can mean one fewer swap shown)
- **Measure:** — (one-off)
- **Design:** the rule is in `shq/radar.py`'s docstring. "May fade" for the drop filter is what the radar text says
  (`fades`: no injury behind a jump of under 4 straight games, or the injured teammate behind it is off the report).
  Tests: `tests/test_nba_one_answer.py` (one class per contradiction, plus the whole tab through `advice.build`);
  `tests/test_categories.py` no longer expects a bench player in "Keep in the lineup". The weekly plan's adds are frozen
  from Tuesday's build (`shq/run.py`, not touched here), so its Draymond line changes at the next weekly rebuild.
- **Decision:** bug fix requested by Michael via Claude Ops, Nov 10

### Q-048 · Weekly plan, Today check and league tiles disagreed with the live league page
- **Status:** shipped (be753c1)
- **Area:** `shq/run.py` (`start_sit_lines(fixes)`, `weekly_section(adv)`, `refresh_weekly`, `live_adds`, `add_key`,
  `refresh_digest`), `shq/leagues.py` (`view`'s `proj` sum only), `shq/guillotine.py` (`team_label`, `labels`, `v2_rows`
  names + `sid`), `shq/wrapup.py` / `shq/wrapup_render.py` (guillotine names, chart label width), `shq/health.py`
  (`rec_outcomes` reads `advice.guillotine.model`, `id_lookup`; `shown_cut_odds` knows the new labels), `docs/lib/core.js`
  (Weekly "Tuesday's plan had" note, Today "updated"), `tests/test_live_sync.py`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (via Claude Ops)
- **Evidence:** live site Tue Nov 10 ~5pm CT: the Weekly plan's adds were the 7:02am list (Domo Boswell vs the league
  page's Zvada; Guillotine Shough vs Jordan Love; Stempak Jordyn Tyson vs A.J. Brown/Davante Adams; 3-Ball BB Quenton
  Jackson vs Isaiah Stewart; Ball is Life drop Draymond vs drop Dunn) and its start/sit left out Domo's QB and K bye
  fixes and Stempak's Malik Willis IR fix. The 8am Today check was never updated (Elliott → "best FA Chris Boswell" vs
  Zvada; Stevenson "Questionable: unconfirmed" vs OUT; "start Carson Wentz (11.8 proj)" vs add a free agent): the
  README's "late runs update the tab" only meant a first build after 1pm. Stempak's tile said 172.7 vs a 156.7 headline
  (Willis on IR, proj 16, counted in `lg.proj`). Guillotine teams were "Off with his head" on the league page,
  "damonhawk1" in War Room v2's rival bids and wrap-up War Room lines, and the wrap-up chart cut names at 16 characters.
  Nov 11 nightly pass (partial check): weekly.json adds equal lineups.json `advice.adds` in all 8 leagues (06:50Z),
  and health.json scores the dashboard model's rows again (`dash_rows` n=16, `gd.dash_price_mae` $10.2). Not checked:
  digest items against league fixes, tile totals against the headline. Stays shipped until those are checked.
  Nov 13 (lineups.json 07:49Z): weekly.json adds still equal lineups.json `advice.adds` in all 8 leagues. Digest items
  and tile totals still not checked.
- **Expected impact:** the Weekly plan keeps its Tuesday framing, but every run its start/sit is the league page's fixes
  then healthy upgrades (up to 3 lines; fixes never cut) and its adds are the league page's adds; Tuesday's moves the live
  list no longer makes (by added and dropped player, not numbers) show as "Tuesday's plan had: …". After the 8am digest,
  each later run rebuilds today's items in place from the same `digest.league_items` the league pages use (title
  recount, "updated <time>"), never pushing; leagues a run couldn't read keep their items. Tile totals count OUT/IR/
  Doubtful/bye/empty starters as 0, like the headline. Guillotine teams read "Team name (username)" on the league page,
  rival bids, trade offers and the wrap-up (chart labels fit up to 32 characters). Model health scores the old model's
  bids again (they had been v2's own rows since Q-044), matched by Sleeper id, else by a Jr./III-blind name.
- **Effort:** S
- **Risk:** Low (display and plan text; no push added, the digest refresh never pushes)
- **Measure:** — (one-off: weekly.json adds = lineups.json advice.adds per league; digest items = league fixes; tile
  `proj` = headline). Health: `dash_rows` counts the model's rows again.
- **Design:** `run.main` passes this run's `league_views` advice to the Tuesday build and to `refresh_weekly` (stale or
  pending views are skipped, so that league keeps its last list); `plan_adds` is set once (`setdefault`). The digest
  refresh runs only when the digest isn't due and `generated` is today (CT), and only rewrites the file when an item
  changed. NBA weekly start/sit and the swap drop rules are unchanged (Q-047's area).
- **Decision:** bug fix requested by Michael via Claude Ops, Nov 10

### Q-049 · Duplicate phone pushes: one push per piece of news
- **Status:** shipped (1af7a32)
- **Area:** `shq/pushes.py` (new: Tuesday morning push, digest vs injury watch, laptop-outage push), `shq/notify.py`
  (`seen`/`mark`, origin/main read before a real push), `shq/statemerge.py` (new git merge driver) + `.gitattributes` +
  `.github/commit_data.sh`, `shq/radar.py` (`send_all`), `shq/run.py` (push calls only: radar queue, outage symptoms,
  `laptop_kicks` row flag, digest/plan/wrap-up push calls, morning push), `shq/wrapup.py` (`run(deliver=)`),
  `picks/pp/lines.py` (`held`, `origin_sent`), `tests/test_push_dedupe.py`, `tests/test_laptop_kick.py`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (via Claude Ops)
- **Evidence:** claude-audit `cleanup-2026-11-10/inv-outputs.md` section 2 (push log + run summaries, Nov 8-10): Tuesday
  reaches ~11-12 pushes. Nov 10: NBA radar x2 at 7:02am (one per league, same run; `state/alerts.json`
  `espn:nba:184031:radar:2026-11-10` and `espn:nba:190278:radar:2026-11-10` both 13:02:43Z), "Week 10 plan ready"
  7:02, digest 8:02 and wrap-up final 8:02 (the same pickups and start/sit moves three times). Stale pool lines: 6 pushes
  Wed Nov 4-Sat Nov 7, one at 1:29am (`state/pick_lines_sent.json` 2026-11-05T07:29Z). A laptop/Chrome outage could push
  "ESPN sync is stale" per league, "roster sync is stale" and "Laptop didn't start today's Sports HQ jobs" separately.
  Nov 11: nothing to measure yet; the Measure needs Tue Nov 17's `state/alerts.json`.
  Nov 13: the radar half holds so far: `state/alerts.json` has one `radar:2026-11-11` and one `radar:2026-11-12` key and
  no per-league `espn:nba:<id>:radar:<date>` key after Nov 10 (two a day Nov 3-10). The Tuesday half waits for Nov 17.
- **Expected impact:** Tuesday Sports HQ pushes 5 → 2 (radar 1, morning push 1); all sources ~11-12 → ~8-9. (1) NBA
  radar: one push a day for both basketball leagues (up to 2 risers each, 7am-9pm CT); a riser found after it waits for
  tomorrow's if still rising. (2) Tuesday: the plan (7am) waits; the first pass at or after 8am CT sends ONE push with
  today's urgent digest lines (or "Today: all clear."), "Week N plan: start/sit and FA adds are on the Weekly tab." and
  the wrap-up final's headline, tap = the wrap-up PDF (PDF / Web page buttons, 3-min delay for Pages). Each part's own
  key (`weekly-plan:`, `digest:`, `wrapup:`) is marked, so none pushes again by itself; a part that wasn't ready (the
  wrap-up crashed, the plan built late) pushes alone later. Other days: digest and wrap-up as before. Every day the
  digest push leaves out an urgent line about a starter the injury watch already pushed ("make this swap", "no healthy
  bench", "CHECK LINEUP"); nothing urgent left = no digest push. Injury-watch pushes themselves are unchanged. (3) Stale
  pool lines: never 10pm-6am CT, at most one push a CT day (`push-day:<date>`); held lines stay flagged on the Picks page
  and ride the next push while their pool is open. (4) One "Laptop/roster sync down" push per outage, listing every
  symptom (stale private-ESPN snapshot per league, stale Kosmonauts roster, no 2:55am kick by 4am); no second push until
  the laptop's kick (or, when the run list can't be read, any laptop job) lands after the push and every symptom has
  cleared (`laptop-down` / `laptop-up` in `state/alerts.json`). The guillotine chain (bid pushes, cut-risk push, War Room),
  the NBA pre-tip lineup push and the laptop tasks' own pushes are untouched.
- **Effort:** M
- **Risk:** Low (push routing only; every page and data file is written as before). Not covered: two runs passing the
  same new key within one pass of each other (each reads origin/main just before pushing, but the first commits at the
  end of its pass); the laptop guard tasks' "Chrome unreachable" / roster-sync-failed pushes (laptop side).
- **Measure:** — (one-off: next Tuesday `state/alerts.json` has `tuesday:<date>` and one `radar:<date>`, no per-league
  `radar:<date>` keys; `pick_lines_sent.json` has at most one `push-day:` per day, none sent 22:00-06:00 CT)
- **Design:** `shq/pushes.py` docstring. Dedupe across parallel runs (a laptop kick beside a cron loop): `notify.push_once`
  also reads origin/main's `state/alerts.json` right before a real push (only in Actions with a topic, never in tests;
  keys found there are kept locally), `pp.lines` does the same for `pick_lines_sent.json`, and both files merge key by
  key in `commit_data.sh`'s pull (`merge=pushstate` driver, `shq/statemerge.py`; works for Q-017's merge too) instead of
  `-X theirs` keeping one run's whole file. Tests: `tests/test_push_dedupe.py` (one class per item, a recorder in place
  of `notify.push`, ntfy and git origin reads patched to fail; a temp-repo rebase shows the driver keeps both runs' keys
  and that without it one is lost); `tests/test_laptop_kick.py` now checks the silent-kick symptom instead of a push.
  Undo: `git revert` the commit (the new state keys are harmless; the `.gitattributes` lines go with the revert).
- **Decision:** requested by Michael via Claude Ops, Nov 10

### Q-051 · NBA pass-3 review: IR fix first, questionable adds, radar protection, chase isn't a move
- **Status:** shipped (886bddc)
- **Area:** `shq/digest.py` (IR line first + urgent in every league, NBA day-to-day label), `shq/nba_swaps.py` (IR-first
  line + room drop, day-to-day discount + status, radar protection by value, "over keeping", whole-year ages),
  `shq/radar.py` (`keep` = shown bench risers, `agree()` verdicts and wording, % rostered wording), `shq/advice.py`
  (`ir_room`, `dedupe_cat_adds`), `shq/nba_values.py` (`play`, `word`), `shq/status.py` (`espn_word`, `play_chance`),
  `shq/nba_games.py` (streamer status), `shq/run.py` (`ADD_RE` reads the IR-first line), `docs/lib/core.js` (chase kind
  only), `tests/test_nba_pass3.py` (new), `tests/test_nba_one_answer.py`, `tests/test_radar.py`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (via Claude Ops), from the pass-3 review (Tue Nov 10 ~6:20pm)
- **Evidence:** live `docs/data/lineups.json` Nov 10 ~6:20pm. (1) Ball is Life: Austin Reaves (ESPN Active, played Nov 8)
  in an IR slot; Fix now said "Lineup is set, nothing to fix", the only mention was a collapsed note, and Waiver adds said
  "Drop John Collins, add Mo Bamba", which ESPN blocks until he moves; Stempak (football) listed an add/drop fix before
  "Move David Montgomery out of IR". (2) 3-Ball BB: Isaiah Stewart (ESPN 5:13p: questionable for Wednesday) shown as
  "+20.0 this week, 3 games" with no tag. (3) Ball is Life radar `keep` held Ryan Dunn (#230, -5.5/g, a starter whose rise
  the page never shows), LaMelo Ball and Ajay Mitchell, so the swaps dropped Collins/Draymond. (4) chase lines counted
  as moves: KPI "Lineup moves 6", layout B "Move 6", layout C "Do now 16", MOVE chip on "Keep in the lineup: Walker
  Kessler" (no game today). (5) Draymond's "may fade" said twice, "Waiver adds swaps him", "worth a start" for every
  bench riser on a no-game day, "1 straight game of it so far" after a 3-game rise, "+1.7 pts in 3 days" for % rostered.
  (6) Stewart "+20.0" in Waiver adds vs "+11.6" in Streamers; Category adds named Jerami Grant for BLK while Waiver adds
  named Mo Bamba. (7) "De'Andre Hunter is 29" (28.9). (8) Giannis "is Questionable" while ESPN's note said probable.
  Nov 11 nightly pass (lineups.json 06:50Z): Ball is Life's first Fix now line is "Move Austin Reaves out of IR …" and
  its add list starts "First move Austin Reaves out of IR (Fix now)". The 3-Ball BB half can't be checked: Isaiah
  Stewart is no longer in its adds. Stays shipped until both halves pass.
  Nov 13 (lineups.json 07:49Z): no NBA add or drop is day-to-day today (0 lines with "day-to-day (ESPN:"), so the
  status half still can't be checked.
- **Expected impact:** one answer per player and per action on the NBA tabs. (1) An IR slot ESPN won't allow is the first,
  urgent Fix now line in every league ("...; do this before any add or drop"), and the NBA add list starts "First move
  Austin Reaves out of IR (Fix now): ...; your roster is full, so that takes a drop too: X; then drop ..."; the Fix now
  line and the radar name the same room drop (the weakest bench player the swaps don't already drop). (2) A day-to-day
  add or drop shows "day-to-day (ESPN: questionable), next game counted at 50%" and his next game counts at ESPN's word:
  probable 0.9, questionable 0.5, doubtful 0.25, no word 0.5 (streamers too). (3) Only bench risers the radar shows, not
  "may fade", are protected, and only while their value isn't more than 1.0/g below the weakest other drop (Toppin
  -4.2 vs Dunn -5.5 stays protected; Dunn is a drop). (4) Chase lines are kind "keep": not in any move count; the NBA
  tile's top line is the fix, move or add. (5) "rise may fade (why); the add list below swaps him for X (+N this week over
  keeping him)" once; no-game verdict "worth a start on his next game day" only when his value beats the weakest
  starter's by 1+/g, else "keep him on the bench for now (...)"; "it hasn't lasted 4 straight games yet"; "rostered 2%
  (+1.7% in 3 days)". (6) "+20.0 this week over keeping De'Andre Hunter"; Category adds for a need a swap already helps
  are left out. (7) Whole years. (8) "day-to-day (ESPN: probable)".
- **Effort:** M
- **Risk:** Low (advice text and drop choice only; nothing is sent). Not confirmed: whether ESPN lets you drop a player
  while an IR slot is blocked (the line says the move "takes a drop", not which screen allows it). The play chances are
  set, not fitted.
- **Measure:** — (one-off: the next live Ball is Life tab shows the Reaves fix first and the IR-first add line; 3-Ball BB's
  Stewart line names his status)
- **Design:** see Area. Tests: `tests/test_nba_pass3.py` (one class per item, fixtures only; the core.js feed/tile check
  runs under Node, a source check runs everywhere). Undo: `git revert` the commit.
- **Decision:** requested by Michael via Claude Ops, Nov 10

### Q-052 · Expert consensus ranks on every football decision (instead of checking FantasyPros)
- **Status:** shipped (ffb2854)
- **Area:** `shq/experts.py` (new: fetch + 3h cache, consensus and "lately" ranks, cross-platform player match, league
  block, "where we disagree", pairs backtest), `shq/advice.py` (`expert_ranks`, `expert_block`, `advice["experts"]`),
  `shq/run.py` (guillotine bid names), `shq/leagues.py` (roster row `exp`), `shq/nfl_players.py` (`exp_wk`,
  `exp_lately`, `exp_range`), `shq/health.py` (section `experts`, checks `exp.*`), `docs/lib/core.js` (tags under each
  line, disagree section, roster rows, Today, Weekly), `docs/players/index.html` (Experts + Exp lately columns),
  `tests/test_experts.py`
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (via Claude Ops)
- **Evidence:** Michael, Nov 10 7pm: "I find myself going to FantasyPros regularly still because i trust it to be more
  reliable for certain things." FantasyPros checked first: robots.txt allows its ranking pages, but its Terms of Use
  (fantasypros.com/about/legal/) allow only "a single copy made for personal use" and forbid republishing; Sports HQ
  is a public repo and site. Its API (fantasypros.com/api-data/) needs a key: free tier "non-production use" only,
  personal use = $8.99/mo Premium or a HOF member's personal key; no account was created. ESPN's analysts' weekly PPR
  ranks (8 experts, ~330 players a week) come free from the public ESPN fantasy API the 3-Ball leagues already use.
  ESPN has no in-season NBA expert ranks and no rest-of-season football ranks in that feed.
  Nov 11 (health run 08:55Z): section `experts` ok; `exp.calls_right` 0.5 (n=2) and `exp.calls_vs_experts` 1.0 (n=1)
  still waiting; `exp.blend_edge` +0.0043 (n=15,973), under the 1% switch rule.
  Nov 13 (health run 08:55Z): unchanged; `exp.last_week_edge` +0.0026 (n=1,761).
- **Expected impact:** every football fix, lineup move, waiver add and guillotine bid shows "ESPN experts: <player>
  WR18 this week, WR22 lately"; roster rows, Today and Weekly too; the Players page gets sortable Experts / Exp lately
  columns (green/red where they differ from our week rank by 10+ spots, 6+ at QB/TE); each league page lists "Where we
  disagree with the experts" (both numbers). Backtest, weeks 1-9 2026, 15,973 start/sit pairs (same position, within 12
  expert ranks, both played, half PPR): Sleeper 57.5%, experts 56.8%, 50/50 blend 57.9%, blend better in 5 of 9 weeks.
  Not a clear win, so start/sit and adds still run on Sleeper's projections (display only).
- **Effort:** M
- **Risk:** Low (display + a nightly check; the lineup model is unchanged; an ESPN outage leaves the last cache or no
  tags, never a failed run). Players parked at the bottom of the experts' lists (bye, ruled out) show as "not ranked to
  play this week", and their "lately" skips those weeks.
- **Measure:** health.json section `experts`: `exp.blend_edge` and `exp.last_week_edge` (switch start/sit to the blend
  when it is 1%+ better and wins 70%+ of weeks; the section's note says so), `exp.calls_right` (our "Start X over Y"
  calls that outscored, baseline-tracked), `exp.calls_vs_experts`.
- **Design:** `shq/experts.py` docstring. Weekly ranks are read at most every 3h (`.cache/espn_experts.json`, generic
  User-Agent, nothing personal); this week's rank appears once ESPN publishes it (usually Tue-Wed).
- **Decision:** requested by Michael via Claude Ops, Nov 10 (FantasyPros itself not used: terms; paid key would be his call)

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
  Nov 11: still none.
  Nov 13: still none (the Inbox holds only the two Oct 31 lines).
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
  Nov 11 nightly pass: Tue Nov 10 had a data commit at 8:02am CT (14:02:36Z), so 2 of 10 weekdays pass; 9 laptop
  dispatches of `run.yml` since Nov 10 05:00Z, all succeeded, none cancelled; model health kicked at 08:55Z Nov 11.
  Nov 13 nightly pass: Wed Nov 11 and Thu Nov 12 had data commits at 8:02 and 8:03am CT (14:02:31Z, 14:03:51Z), so 4 of
  10 weekdays pass; 23 laptop dispatches of `run.yml` since Nov 11 05:00Z, none cancelled, one failed (Nov 12 19:02Z,
  run 43285972190, cause not checked); model health kicked at 08:55Z Nov 12 and Nov 13.
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
  Nov 13: none of the 17 scheduled `run.yml` runs since Nov 11 05:00Z was cancelled (weekday 8am commits: Q-029).
- **Expected impact:** the 8am digest and Tuesday Weekly tab on time; a "force" button press never vanishes.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: data-commit gaps 8am-1pm on weekdays, and dropped dispatches, in the next monthly review)
- **Design:** `ops/designs/Q-014.md`
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
  Nov 11: same; still no push log (Q-015).
  Nov 13: `state/alerts.json` shows the lineup push went out on 2 days (`nba-lineup:2026-11-08` 20:07Z,
  `nba-lineup:2026-11-11` 21:07Z); days a move was needed with no push still can't be counted without Q-015's log.
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

### Q-004 · No rival-specific bidding habits
- **Status:** shipped (4fef2c7, built as part of Q-062, Nov 12)
- **Area:** War Room v2 (`model.js` `threats`; since Q-062 `build.py` `rival_model`, `model.js` `bidsAtLeast`)
- **Rank:** — (built inside Q-062; no longer ranked)
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** A rival's predicted bid uses only his boldest past bid share (`MAXPCT`), his need and the player's quality; the
  ladder then corrects league-wide. Some teams win most big claims (CodyRust $150 McCaffrey and $50 Adams in week 1; Aniasin1
  once bid 93% of the FAAB he had left). The ladder holds 165 priced claims, about 10 per team.
  Nov 13: built inside Q-062 (4fef2c7, Nov 12): `build.py` `rival_model` fits each rival's own habit every build (his
  average bid share vs the league's, half-weighted = `scale`; his biggest share so far = `cap`; rivals with 3+ claims)
  and `model.js` `bidsAtLeast` applies them rival by rival. Its Measure scores the old raw estimate and ladder, not
  this, so it can be verified only once Q-064's check exists.
- **Expected impact:** better price estimates when a known big spender needs the player.
- **Effort:** M
- **Risk:** Med (about 10 claims per rival: easy to overfit)
- **Measure:** `wr.price_est_mae`, `wr.ladder_cov50`; for the model as built, Q-064's `wr.rival_cov50` / `wr.rival_brier`
- **Design:** as built in Q-062: warroom/README.md "Nov 12 revamp" (rival-by-rival prices)
- **Decision:** approved 2026-11-12 as part of Q-062 (Michael approved the War Room revamp plan parts 1-3 through Claude Ops)

### Q-020 · Laptop jobs that fail still show "succeeded"
- **Status:** designed
- **Area:** laptop task prompts (daily sync, picks, guillotine checks), `shq/run.py` `job_health`, `docs/lib/core.js` `footHTML`
- **Rank:** 1
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
  Nov 11: unchanged; the only `FAILED:` line in `ops/tasks/` is in `pool-picks-thu-bto-check.md`. Ranked 1 (was 3):
  Q-036 lost most of its evidence to Q-045's metric fix, and the daily sync and picks tasks are still the jobs that
  can fail without anyone hearing.
  Nov 13: unchanged (`FAILED:` still only in `pool-picks-thu-bto-check.md`). Stays 1.
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
- **Rank:** 2
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #4 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness): only `push_once` keys reach `state/alerts.json`, pruned after 21 days
  (`shq/notify.py:36`); digest, "lineup fixed" and weekly pushes use plain `push()` (`shq/run.py:120`, `:308`, `:321`) and leave
  no record, so the review couldn't say which injured starters were caught before lock in October. Still open Nov 4: no
  `state/pushes.json`, no "pushes" reference in `shq/` or `docs/`.
  Nov 11: still no `state/pushes.json`. Q-049 (1af7a32) added dedupe keys (`state/alerts.json`,
  `pick_lines_sent.json`), which keep a key per push, not its title or text. Q-032's and Q-049's Measures both need
  this log. Ranked 3 (was 4).
  Nov 13: still no `state/pushes.json`. `state/alerts.json` shows lineup pushes on Nov 8 and Nov 11 (Q-032) and one
  radar push a day since Nov 11 (Q-049), but not their text, and not the days nothing went out. Ranked 2 (was 3):
  Q-032's, Q-049's and Q-016's Measures all wait on it.
- **Expected impact:** "did we catch it before lock?" becomes answerable; a "Recent alerts" list on the site.
- **Effort:** S
- **Risk:** Low (the test must prove the ntfy topic never lands in the log; the repo is public)
- **Measure:** — (one-off: every `state/alerts.json` key from a week has a log entry)
- **Design:** `ops/designs/Q-015.md`
- **Decision:** —

### Q-064 · Model health still scores the old price ladder, not the rival-by-rival chances behind every bid since Nov 12
- **Status:** designed
- **Area:** `shq/health.py` (`ladder_backtest`, `warroom_prices`, checks `wr.*`), `warroom/build.py` (`rival_model`),
  `warroom/export.js` (a scoring mode), `warroom/model.js` (`rivalWin`, `priceFor`)
- **Rank:** 3
- **Added:** 2026-11-13 by the nightly pass (own finding from health.json `sections.warroom` and `sections.recs`, the
  code, and Q-062's replay numbers in warroom/README.md "Nov 12 revamp")
- **Evidence:** Since 4fef2c7 (Nov 12) War Room v2 prices every claim rival by rival (`winChance` uses `rivalWin`
  whenever `D.rival_model` is fitted); the old ladder is only a fallback. `shq/health.py` never mentions `rival_model`
  (last changed 5f6a437, before the revamp), so the nightly checks still score the ladder: `wr.ladder_cov50` 0.56 and
  `wr.ladder_cov80` 0.81 (n=212), both ok, while Q-062's own time-forward replay found that ladder's 10-30% chances won
  1 in 79 in weeks 6-9 (Nacua, Javonte Williams, Taylor, Pickens, Warren 0 for 5), and the new model's 20% bids won
  17-26%, a little cautious in the middle (said 60%, won about 70%). That replay was a one-off in the build session:
  nothing re-runs it as claims arrive or splits it by position (the ladder missed RBs: 33% at its 50% price, n=40). The
  one live check of stated chances, `rec.win_brier`, is on watch: 0.17 (n=9) vs 0.125; week 9's $1 "Bid" calls at
  57-66% lost Fannin (a $1 tie; Michael is last in waiver order) and Barkley ($2), both priced by the old ladder. It
  gets 2-5 bids a run, too few to judge a model soon. From Tue Nov 17's build every recommended bid uses the new chances.
- **Expected impact:** a nightly, out-of-sample answer to "when War Room says 50%, do we win half?" for the model that
  sets every Tuesday bid, claim order and backup, split by position and season stage, so a miscalibration shows within a
  week or two. FAAB is $10 ($5 spendable), so this season's stakes are mostly $0-5 claims and which backups fire.
- **Effort:** S-M
- **Risk:** Low (health job only; the old ladder checks stay as info)
- **Measure:** — (one-off: health.json has `wr.rival_cov25`, `wr.rival_cov50`, `wr.rival_cov80` and `wr.rival_brier`,
  scored time-forward with `by` splits; from then those checks are the measure for Q-004, Q-008 and the revamp)
- **Design:** `ops/designs/Q-064.md`
- **Decision:** —

### Q-024 · The picks health check scores Yahoo straight-up picks against a spread break-even
- **Status:** designed
- **Area:** `shq/health.py` `picks_health` and the `picks.card_ats` floor (line 71); `picks/data/postmortem/*.json`
- **Rank:** 4
- **Added:** 2026-11-05 by the nightly pass (own finding from health.json `sections.picks` and
  `picks/data/postmortem/2026-w09.json`)
- **Evidence:** `picks.card_ats` = 0.733 (22-8, n=30, baseline set Nov 4) is labelled "Posted card picks that won against the
  spread" and judged against a 52.4% floor (the -110 break-even). But 25 of the 30 graded picks are Yahoo pick'em winners,
  picked straight up (week 9: Yahoo 18-7, BTO 3-0, CFP 1-1; week 8's postmortem has no card picks). Straight-up winners are
  much easier to hit than spreads, so the check reads "ok" almost regardless of skill, and it is the Measure for Q-023. The
  same files grade the entries (32-27); in week 9 the entry differed from the card on 5 picks, card 5-0, entry 1-4
  (`differences` in the postmortem; the saved-picks check built Nov 4 now flags such differences before lock).
  Nov 10: unchanged (`graded_weeks` still 8 and 9); week 10's postmortem lands Tue Nov 10 8pm CT.
  Nov 11 (health run 08:55Z): `picks.card_ats` is now a flag: 0.678 (40-19, n=59) against its 0.733 baseline, watch
  (tolerance 0.08). Week 10's postmortem: Yahoo straight-up 16-9, BTO spreads 1-2, CFP 1-0. Over weeks 9-10 the card's
  spread picks (BTO + CFP) went 6-3 and its Yahoo straight-up picks 34-16; one number mixes the two, so the watch
  can't say which slipped. Entries 50-38 (0.568). Ranked 4 (was 9).
  Nov 13 (health run 08:55Z): unchanged: `picks.card_ats` 0.678 (n=59), on watch for the third night; `picks.brier_gap`
  0.028 and `picks.stale_cover` 0.616 still equal their baselines (the backtest file is still `2026_w1-8.json`). Stays 4.
- **Expected impact:** a picks score that means something: BTO and CFP spread picks against 52.4%, Yahoo against the
  market favourite's straight-up record on the same games. Feeds Q-013's scorecard and Q-023's decision.
- **Effort:** S
- **Risk:** Low (health job only; the `picks.card_ats` baseline resets)
- **Measure:** — (one-off: separate spread and straight-up checks, each with its own floor)
- **Design:** `ops/designs/Q-024.md`
- **Decision:** —

### Q-036 · NBA radar flags now trail the old suggestions (`radar.held` drift, `radar.edge` weak)
- **Status:** designed
- **Area:** `shq/radar.py` (`block`, `fit_score`, `send_alerts`), `shq/radar_backtest.py` (`run`, the comparison list),
  `shq/health.py` `radar_health`
- **Rank:** 5
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
  Nov 11: re-judged on Q-045's metric, as Q-045 asked: `radar.edge` +0.43 (n=30) and `radar.held` 0.70 (n=10), both
  ok, so the low-value flags this gate targets no longer measure as hurting. Ranked 14 (was 1); the design stays ready
  if the edge check turns weak again on the new metric.
  Nov 13 (health run 08:55Z): weak again, on Q-045's metric: `radar.edge` −0.27 z per game (n=42) vs baseline 0.34,
  floor 0.0 (it was +0.43 on n=30 Nov 11). Every flagged free agent: 34 of 51 held (0.67), value −4.23 vs −4.47 for the
  comparison list and −5.73 for every free agent (6 wire mornings). The flags the site shows look fine so far:
  `radar.held` 0.64 (7 of 11, ok vs 0.70) and a shown-only edge of +2.68 (n=5). So the drag is the flags beyond the 4 a
  morning the site lists, which is what this gate trims; 6 flags were added by someone later (was 5). Ranked 5 (was
  14), as the Nov 11 note planned if the edge turned weak again; the design's later-mornings test (edge ≥ 0.5 with ≥ 10
  flags) still decides.
- **Expected impact:** fewer, better radar lines and pushes in both basketball leagues: a rising free agent is shown only
  when his new role is worth a roster spot in this league's categories, and the check compares him with what the site
  actually suggests now.
- **Effort:** S
- **Risk:** Low (ideas and at most one push a day per league; a gate can hide a one-category specialist, see the design)
- **Measure:** `radar.edge` (≥ 0.5 z per game with ≥ 10 flags, out of sample), `radar.held` (≥ 0.75)
- **Design:** `ops/designs/Q-036.md`
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
  Nov 11: still n=0 for `wr.swing_k2`-`k4`; enough data for `k2` with the Nov 17 run, `k3` Nov 24, `k4` Dec 1. Keeps
  its place (6).
  Nov 13: still n=0 (Nov 13 run); same dates. Keeps its place (6).
- **Expected impact:** the right rest-of-season uncertainty, which drives win odds and so every value.
- **Effort:** S (change `SD_GROWTH` once measured)
- **Risk:** Low
- **Measure:** `wr.swing_k2`, `wr.swing_k3`, `wr.swing_k4` vs `wr.swing`
- **Design:** —
- **Decision:** —

### Q-018 · The What to do card contradicts itself
- **Status:** designed
- **Area:** `shq/waivers.py` (drop protection), `shq/advice.py` (What to do card), IR-slot lines
- **Rank:** 7
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
  Nov 11 (lineups.json 06:50Z): no football waiver drop is this week's start except same-position K/DEF upgrades (drop
  the starter, start the add), so the cause is dormant, not fixed: `waivers.py` still unchanged since Oct 31
  (46076da). Bro-vid19 still lists Waiver adds under two IR lines that say ESPN blocks adds and drops (Q-051 gave the
  NBA add lists an "IR first" line; football didn't get one), and Garrett Wilson's IR line cites a Nov 6 note. Several
  sibling contradictions were fixed Nov 10 (Q-047, Q-048, Q-050, Q-051). Ranked 5 (was 2).
  Nov 13: `waivers.py` still unchanged since Oct 31 (46076da); snapshots not replayed tonight. Ranked 7 (was 5): Q-064
  and Q-036 now have fresher, measured evidence.
- **Expected impact:** one consistent set of moves per league; no drop of a player the card says to start.
- **Effort:** S-M
- **Risk:** Low
- **Measure:** — (one-off: no league page where a waiver drop is also a lineup-move start)
- **Design:** `ops/designs/Q-018.md`
- **Decision:** —

### Q-065 · NBA waiver swaps promise about 5 more than they deliver ("+N this week")
- **Status:** measuring
- **Area:** `shq/nba_swaps.py` (the "+N this week" estimate), `shq/nba_values.py` (per-game values of fringe players);
  health.json sections `swaps` and `sources`
- **Rank:** 8
- **Added:** 2026-11-13 by the nightly pass (own finding from health.json `sections.swaps` and `sections.sources`, and
  `reviews/2026-11-12-nba-swaps-backtest.md` "Findings")
- **Evidence:** Week ending Nov 8, 8 swaps judged: the site showed +4.62 on average and the result came out 5.35 lower
  (`swap.est_bias` −5.35, `swap.est_err` 7.73); the add beat the drop in 4 of 8 (`swap.hit` 0.5) for +0.10 z per add
  game (`swap.gain`). The review: adds valued +1.80 a game produced −0.82 while playing every expected game; drops valued
  −2.74 produced −0.34. That is regression to the mean on fringe players, not missed games. Provisional week through
  Nov 11: −1.64 per add game, 5 of 11 ahead. Streamer order is fine (`stream.order` 0.83, n=12). Q-060's trial
  (`sections.sources`) tests the likeliest fix: DARKO minutes miss 5.87 vs the site's 7.73 (n=9), gain +3.06/g; shrunk
  values miss 9.19 (n=6). All info: one complete week, under 20 judged swaps. Enough data: 20 swaps about Nov 22-29
  (the health note); the trial's switch rule needs 2+ complete weeks. Related: ee072a4 (Nov 12) added rules after
  Michael rejected several swaps (Bey→Reed, Toppin→Goodwin).
- **Expected impact:** a "+N this week" that means what it says, so a swap shown as +5 is worth the roster move, and
  fewer churn moves between fringe players.
- **Effort:** S (if Q-060's switch closes the gap, one config line; otherwise shrink the shown estimate by the
  measured bias)
- **Risk:** Low
- **Measure:** `swap.est_bias` (toward 0), `swap.est_err`, `swap.gain`; `src.darko_err`, `src.shrunk_err`
- **Design:** —
- **Decision:** —

### Q-013 · Model health scorecard on the site
- **Status:** designed
- **Area:** site (`docs/lib/`, owned by the dashboard redesign session)
- **Rank:** 9
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
  Nov 11: the Nov 11 run (12 ok, 2 watch, 7 waiting, 9 info, 0 errors) put `rec.win_brier` and `picks.card_ats` on
  watch; `docs/lib/` and `docs/index.html` still never load health.json.
  Nov 13: the Nov 13 run (14 ok, 2 watch, 1 weak, 7 waiting, 21 info, 0 errors) turned `radar.edge` weak again
  (Q-036); `docs/lib/core.js` and `docs/index.html` still never load health.json. Ranked 9 (was 10).
- **Expected impact:** a glance at which models are trustworthy this week (ok / watch / drift / weak per model, tap for the checks).
- **Effort:** S
- **Risk:** Low
- **Measure:** —
- **Design:** `ops/designs/Q-013.md`
- **Decision:** —

### Q-019 · The picks backup has never worked for real
- **Status:** designed
- **Area:** `.github/workflows/picks-backup.yml`, `.github/workflows/run.yml`, `picks/pp/http.py`, GitHub secret `CFBD_API_KEY`
- **Rank:** 10
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
  Nov 11: `gh secret list` still shows 5 secrets and no `CFBD_API_KEY`; this week's first backup slot is tonight, Wed
  Nov 11 9:45pm CT. Ranked 9 (was 5): M effort plus a step for Michael.
  Nov 13: the first real backup build: the Wed Nov 11 9:45pm CT slot started Thu Nov 12 5:51am CT (8h late) and failed
  on the same `RuntimeError: CFBD /lines not cached and no key/budget` (run 43212798455, `CFBD_API_KEY` empty). Q-055
  (39dcb9e, 7:28am that morning) now builds the card without a key (saved CFBD lines plus ESPN's scoreboard); no backup
  run since, so not proven. Left here: the late crons (the backup still runs on its own schedule, 4-8h late) and the
  secret (`gh secret list`: 6 secrets, no `CFBD_API_KEY`). Ranked 10 (was 9).
- **Expected impact:** a real fallback card when a laptop picks run is missed.
- **Effort:** M (plus one manual step for Michael: add the secret)
- **Risk:** Low
- **Measure:** — (one-off: a forced backup run builds a card)
- **Design:** `ops/designs/Q-019.md`
- **Decision:** —

### Q-021 · Hygiene pass: line endings, public CFBD files, worktrees, browser rule
- **Status:** designed
- **Area:** `picks/pp/grade.py`, `picks/pp/model.py`, `picks/cache/cfbd/`, `.claude/worktrees/`, ROADMAP.md, laptop prompts
- **Rank:** 11
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
  Nov 11: still 2 `i/crlf` files and 17 tracked CFBD files. `git worktree list` now shows 17 extra worktrees (11
  `agent-*` from the Nov 10 build sessions, 6 of them locked), and tonight's `git pull` printed "failed to delete
  '.git/worktrees/nice-hamilton-b16e8b': Permission denied". Ranked 13 (was 16).
  Nov 13: still 2 `i/crlf` files and 17 tracked CFBD files; `git worktree list` shows 23 extra worktrees (was 17), and
  tonight's `git pull` printed the same "Permission denied" line twice. Ranked 11 (was 13).
- **Expected impact:** the repo follows its own rules; nothing raw from CFBD stays public; less clutter.
- **Effort:** S
- **Risk:** Low
- **Measure:** — (one-off: the four checks above come back clean)
- **Design:** `ops/designs/Q-021.md`
- **Decision:** —

### Q-017 · Four git steps still rebase (rule: merge, never rebase)
- **Status:** designed
- **Area:** `.github/commit_data.sh`, `.github/workflows/picks-backup.yml`, `war-room-v2.yml`, `yahoo-reauth.yml`
- **Rank:** 12
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Rule breaks" #1 and "Ranked improvements" #6
- **Evidence:** The review listed 5 rebase spots. On Nov 4 `git grep rebase` still finds 4: `commit_data.sh:8`
  (`git pull -q --rebase -X theirs`), `picks-backup.yml:67` (`git pull --rebase`), `war-room-v2.yml:48` (`--rebase -X theirs`),
  `yahoo-reauth.yml:41` (`--rebase`). `picks/pp/publish.py:72` is fixed (`--no-rebase --no-edit`). `feedback.yml` and
  `model-health.yml` already merge. Nov 5: same 4 lines. Note for the build: under a merge `-X theirs` means the remote, so
  the like-for-like swap is `-X ours` (see the design).
  Nov 10: the same 4 lines (`git grep -- --rebase .github`).
  Nov 11: the same 4 lines (`commit_data.sh:10`, `picks-backup.yml:67`, `war-room-v2.yml:50`, `yahoo-reauth.yml:41`);
  Q-049 added a merge driver for the state files but kept `--rebase -X theirs` in `commit_data.sh`. Ranked 15 (was 7).
  Nov 13: the same 4 lines (`commit_data.sh:10`, `picks-backup.yml:62`, `war-room-v2.yml:50`, `yahoo-reauth.yml:41`).
  Ranked 12 (was 15).
- **Expected impact:** the repo follows its own rule; no rewritten history when the data loop and a session push at once.
- **Effort:** S
- **Risk:** Low (the data loops keep this pass's data on a conflict, as today, via `-X ours`)
- **Measure:** — (one-off: `git grep -- --rebase .github` finds nothing)
- **Design:** `ops/designs/Q-017.md`
- **Decision:** —

### Q-009 · The 0.3-point win-odds noise floor is a guess
- **Status:** designed
- **Area:** War Room v2 (`model.js` `MIN_WIN`)
- **Rank:** 13
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Moves adding under 0.3 points of win odds are skipped as noise, but the real noise of `gains()` (10,000 seasons,
  same seed for both sides) has not been measured.
  Nov 8 nightly pass: with my win odds at 5% the calls now sit on the floor. bids.json (Nov 7 17:43Z): Pat Freiermuth and
  Tyler Higbee "Add free" at +0.003 (the floor itself, as stored), Dominic Zvada "Skip" at +0.002, three more at +0.001;
  9 of 14 rows are free adds. The page compares at 3,000 seasons, bids.json at 10,000 (`S.sims / 2`), so near the floor
  the two can differ (Q-006). Ranked 15, one above Q-007, whose replay needs this floor first.
  Nov 9: bids.json (Nov 8 17:53Z, 14 rows): Pat Freiermuth and Tyler Higbee "Add free" at +0.004, BAL DEF "Skip" at
  +0.003 (rounded), NE DEF, BUF DEF and Dominic Zvada "Skip" at +0.002: 6 calls within 0.002 of the floor.
  Nov 11: bids.json `d8b4c87`: IND DEF "Add free" at +0.003 (the floor itself), GB DEF at +0.004.
  Nov 13: `MIN_WIN` still 0.003 (`model.js:30`). Since Q-062, K, DEF and marginal adds go in at $0, so the floor now
  mostly decides Add free vs Skip and whether a claim is made at all. bids.json has no rows between runs (next waiver
  run Wed Nov 18). Ranked 13 (was 16).
- **Expected impact:** small free adds stop being dropped (or noise stops being recommended).
- **Effort:** S (rerun `gains` with several seeds, set the floor at about 2 standard errors)
- **Risk:** Low
- **Measure:** one-off (share of rows whose call flips across 20 seeds, under 5%); then fixed
- **Design:** `ops/designs/Q-009.md`
- **Decision:** —

### Q-022 · Old claude.ai helpers still give lineup and bid advice (and auto-swap) alongside Sports HQ
- **Status:** proposed
- **Area:** outside the repo: claude.ai routines "Fantasy football helper", "Fantasy basketball helper", "Guillotine strategy
  review", "Football pools picks"; Sports HQ rules (ROADMAP "Rules that must not break", `status.confirm`)
- **Rank:** 14
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
  Nov 11: ranked 17 (was 12): what is left is ROADMAP wording about the laptop guards' swaps.
  Nov 13: unchanged. Ranked 14 (was 17).
- **Expected impact:** one source of lineup and bid advice; no auto-swap that skips Sports HQ's injury confirmation; fewer pushes.
- **Effort:** S (a decision; the routine changes are a claude-audit batch)
- **Risk:** Med (turning off auto-swaps means Sports HQ's pushes are the only safety net for inactive starters; see Q-016)
- **Measure:** — (one-off: one owner per job in the claude-audit plan)
- **Design:** claude-audit `plan.md` Phase 2 (a decision, outside this repo)
- **Decision:** —

### Q-011 · One guillotine model: the dashboard and War Room v2 still give different numbers
- **Status:** designed
- **Area:** `shq/guillotine.py` (dashboard, Today tab, cut-risk push) vs `warroom/` (War Room v2, bids.json, Tuesday checks)
- **Rank:** 15
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
  Nov 11: the Guillotine league page's bids, fix and adds now follow v2 (Q-044 and Q-050, verified tonight); the
  cut-risk numbers (Today tab, cut-risk push) still come from the dashboard model. Prices: dashboard $10.2
  (`gd.dash_price_mae`, n=16) vs v2 $7.6 (`rec.est_mae`, n=7); cut odds still n=1-2. Ranked 18 (was 11).
  Nov 13: unchanged in the Nov 13 run (`gd.v2_skill` +0.507 n=1, `gd.dash_skill` −0.142 n=2; prices $10.2 vs $7.6).
  Ranked 15 (was 18).
- **Expected impact:** one answer everywhere (site, push, AI write-up); fixes found in one model reach every screen.
- **Effort:** M (dashboard reads bids.json for odds and bids; keeps its live Sunday locking until Q-002 lands)
- **Risk:** Med (the cut-risk push and Today tab change source)
- **Measure:** `gd.v2_skill` vs `gd.dash_skill` (which predicted cuts better as shown), `gd.dash_price_mae` vs `rec.est_mae`
- **Design:** `ops/designs/Q-011.md`
- **Decision:** —

### Q-007 · Free-agent candidates are capped (3 per position, 24 total)
- **Status:** designed
- **Area:** War Room v2 (`model.js` `candidates`)
- **Rank:** 16
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Only the top 60 free agents by projected points are tried, then at most 3 per position and 24 overall. The old
  cap of 2 per position hid Bo Nix (audit). A bye-week fill-in or a K/DEF stream can rank 4th at its position and vanish.
  Nov 8 nightly pass: bids.json (built Nov 7 17:43Z) has 14 rows, QB 3, DEF 3, TE 3, K 3, WR 2: the per-position cap
  binds at four positions (the 24 total doesn't). With $5 spendable, free adds (9 of 14 rows) are most of what v2 can
  still do for me, so the cap decides which ones I see. Not confirmed: whether a 4th-ranked player would have cleared
  the floor (Node isn't on the laptop; the design's replay runs in GitHub Actions).
  Nov 13: caps unchanged after the revamp (`model.js:252` top 60 by projection, `:266` at most 3 free agents per
  position, 24 total). Ranked 16 (was 19).
- **Expected impact:** no useful free add silently missing.
- **Effort:** S (raise the caps; check build time)
- **Risk:** Low (slower build)
- **Measure:** one-off: free agents beyond the cap that would add more than the noise floor
- **Design:** `ops/designs/Q-007.md`
- **Decision:** —

### Q-016 · "Likely out" news doesn't trigger a push while ESPN still says Questionable
- **Status:** designed
- **Area:** injury watch (`shq/run.py` swap pushes, `status.confirm`), ROADMAP injury rule
- **Rank:** 17
- **Added:** 2026-11-04 by the nightly pass, from `reviews/2026-11.md` "Ranked improvements" #5 and IDEAS.md "Proposed by monthly review"
- **Evidence:** `reviews/2026-11.md` (Usefulness, Sun Nov 1): Breece Hall (Guillotine FLEX) was still Questionable on ESPN while
  its 8:07am note said he "isn't expected to play"; the rule keeps him at Q, so no push. The site did show "Start J.K. Dobbins
  (7.7) over Breece Hall (0)" as a lineup move. Still open Nov 4: no "expected to play" / "likely out" handling in `shq/`.
  One case so far.
  Nov 11: still one case. Ranked 20 (was 10): Med risk and it needs Michael's call on the injury rule, while the S
  items above it have fresher evidence.
  Nov 13: still one case; still no "not expected to play" / "likely out" handling in `shq/`. Ranked 17 (was 20).
- **Expected impact:** in the guillotine league a likely zero is the alert that matters most; a labelled "likely out
  (unconfirmed)" swap push with the citation, when a starter's note says "not expected to play" / "won't play" or his
  projection drops to 0 within 90 minutes of lock.
- **Effort:** M
- **Risk:** Med (changes the injury rule; needs Michael's call; false alarms if the note is speculative)
- **Measure:** — (one-off, once Q-015's push log exists: likely-out pushes vs who actually played)
- **Design:** `ops/designs/Q-016.md`
- **Decision:** —

### Q-002 · Mid-week, War Room v2 ignores games already played
- **Status:** designed
- **Area:** War Room v2 (`model.py` / `model.js` `proj`)
- **Rank:** 18
- **Added:** 2026-11-03 (warroom/README.md "Known limits")
- **Evidence:** From Thursday night to Monday, the coming week's projections ignore games already played; only the dashboard
  (`shq/guillotine.py`) locks started games and uses real points. v2's cut risks on Fri-Mon are pre-kickoff numbers.
  Nov 7 nightly pass (code read for the design): nothing is partly built; `model.py` `build()` never fetches the current
  week's matchups. v2 barely rebuilds on game days: the only Thu-Mon slot (6:10am CT daily) ran 6-9.5h late Nov 1-6
  (started 11:54am-3:40pm CT; Sunday Nov 1's 6 minutes before kickoff). The dashboard's stored snapshots gave week 8's cut
  team 1.9% Thursday, 2.3% Sunday 11:57am CT, 96.1% Monday 7:07pm CT, so the gain shows Sunday night and Monday, not
  Sunday morning. No mid-game v2 history is stored (bids.json versions only since Oct 31).
  Nov 13: unchanged; warroom/README.md "Known limits" still lists it after the Nov 12 revamp. Ranked 18 (was 21).
- **Expected impact:** live cut risk on game days from the same model as the bids; a prerequisite for Q-011 (one model).
- **Effort:** M (lock started players at their real points, zero swing for finished games, like `guillotine.entry`)
- **Risk:** Low
- **Measure:** a Sunday-morning version of `gd.v2_skill` (add when built)
- **Design:** `ops/designs/Q-002.md`
- **Decision:** —

### Q-023 · College ATS cards still tilt 10% toward a stats model the backtest says to drop
- **Status:** designed
- **Area:** Pool Picks (`picks/pp/cards.py` `MODEL_W`, `fair_margins`)
- **Rank:** 19
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
  Nov 11: the backtest file is still `2026_w1-8.json`; `picks.brier_gap` 0.028 and `picks.stale_cover` 0.616 again
  equal their baselines.
  Nov 13: same file, same numbers; `picks.card_ats` still on watch (0.678, n=59; Q-024 splits it). Ranked 19 (was 23).
- **Expected impact:** small: college card centers move by a tenth of the model-market gap (a 5-pt gap = 0.5 pt), which
  only matters near a pool line's half point.
- **Effort:** S
- **Risk:** Low
- **Measure:** `picks.card_ats` (spread picks only, once Q-024 splits it) and the next backtest's walk-forward RMSE
- **Design:** `ops/designs/Q-023.md`
- **Decision:** —

### Q-012 · Cut odds are no better than a coin toss
- **Status:** designed
- **Area:** War Room v2 (`warroom/model.js` `simulate`), dashboard (`shq/guillotine.py`)
- **Rank:** 20
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
  Nov 11: unchanged in the Nov 11 run (`wr.cut_skill` +0.032, n=9; best swing 36, +5.4%, in-sample).
  Nov 13: unchanged in the Nov 13 run (`wr.cut_skill` +0.032, n=9; `wr.best_sd` 36). Week 10's cut adds a 10th case
  with the Nov 17 run. Ranked 20 (was 24).
- **Expected impact:** cut risk and win odds drive every bid value. If cuts are mostly upsets, both models are too sure who is
  safe, so win-odds gains (and bids) are spread too wide between players. Better-calibrated odds = better $ values.
- **Effort:** S to test, M to change
- **Risk:** Med (moves every bid value)
- **Measure:** `wr.cut_skill`, `gd.v2_skill`, `gd.dash_skill`, `wr.best_sd` in health.json
- **Design:** `ops/designs/Q-012.md`
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
  Nov 13 (health run 08:55Z): `rec.win_brier` is on watch: 0.17 (n=9) vs baseline 0.125, tolerance 0.05;
  `rec.would_win` 0.22 (2 of 9). Week 9's claims: Harold Fannin $1 "Bid" at 64.5% lost a $1 tie, Saquon Barkley $1 at
  57.2% lost to $2, Jaylen Warren $2 at 21.2% lost to $16, Spencer Shrader $1 won. Those misses came from the old
  ladder's chances (now Q-064), not this step. The step itself survived the revamp: `model.js:388` still sets Skip
  when a claim's bid doesn't fit ("your other bids use the budget") without trying a lower bid; `addBackups` can now
  pick such a claim up as a backup on a drop already in use. FAAB $10 ($5 spendable). Ranked 21 (was 25).
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
  Nov 11: bids.json `d8b4c87` (before the Wed run) set `dollars_per_win_point` 2.4 with $5 spendable.
  Nov 13: Q-062 now sets the rate at the 50% price (at the 80% price the honest prices inflated it and the replay spent
  $205); the one-crop assumption in `autoDpp` (`model.js:303`) is unchanged. Ranked 22 (was 26).
- **Expected impact:** steadier bid values week to week; less risk of overspending on a weak crop or hoarding before a strong one.
- **Effort:** M (estimate future crops from the remaining rosters: who is likely cut next and what they hold)
- **Risk:** Med (changes every value)
- **Measure:** `rec.would_win`, spending pace vs weeks survived (to add to health once bids have outcomes)
- **Design:** `ops/designs/Q-010.md`
- **Decision:** —

### Q-003 · Price ladder isn't split by position or season stage
- **Status:** designed
- **Area:** War Room v2 (`warroom/build.py` `ladder`, `model.js` `winChance`)
- **Rank:** 23
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
  Nov 11 (Nov 11 run, 212 claims, 22 more): RB 33% at the 50% price and 68% at the 80% (n=40, estimate miss $16.4); WR
  48% / 77% (n=69); QB 68% / 84% (n=25); TE 66% / 90% (n=29); K 91% / 95% (n=22); DEF 63% / 96% (n=27); overall
  `wr.ladder_cov50` 0.56, `wr.ladder_cov80` 0.82; estimate miss $12.2 for legs 1-4 vs $5.3 for 5-9.
  Nov 13 (Nov 13 run, same 212 claims): RB 33% / 68% (n=40, estimate miss $16.5), WR 48% / 74% (n=69), K 91% / 95%
  (n=22), DEF 63% / 96% (n=27). But since the War Room revamp (Q-062, 4fef2c7, Nov 12) the ladder prices a row only
  when no rival-by-rival model is fitted (`model.js` `winChance` uses `D.ladder` only as a fallback); every bid from
  Tue Nov 17 uses `rivalWin`. This design now targets a fallback: a candidate to reject. Ranked 23 (was 12). The
  question it raised (are the stated chances right by position?) moves to Q-064.
- **Expected impact:** RB claims (the most expensive position) won at the stated odds instead of lost; no overbidding on K/DEF.
- **Effort:** S
- **Risk:** Low-Med (splits get thin: keep the "at least 12 claims or merge" rule; test leave-one-run-out before shipping)
- **Measure:** `wr.ladder_cov50`, `wr.ladder_cov80` and their `by` splits (RB at 80% should reach about 0.8)
- **Design:** `ops/designs/Q-003.md`
- **Decision:** —

### Q-006 · The page runs 6,000 seasons, bids.json 20,000
- **Status:** designed
- **Area:** War Room v2 (`model.js` `S.sims`, `export.js`)
- **Rank:** 24
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The page uses 6,000 so the sliders respond quickly; bids.json, the Tuesday push and the AI write-up use 20,000.
  The audit measured ±0.3-0.7 pts of noise at 2,000. Near a call boundary (0.3-pt noise floor, Bid vs Coin flip at 50%)
  the page can show a different call than the push.
  Nov 9 nightly pass (code read for the design): the page compares each add at 3,000 seasons (`S.sims / 2` of 6,000,
  `model.js:166`, `:184`), bids.json at 10,000 (`export.js:12` sets 20,000); both use the same seed
  (`rng(20261027)`, `model.js:74`), so at equal sizes they would agree exactly. bids.json (Nov 8 17:53Z): 6 of 14 calls
  sit within 0.002 of the 0.003 floor (Q-009). Not confirmed: how many differ on the page today (needs Node).
  Nov 13: mostly delivered by Q-062 (4fef2c7): at default settings the page's "Your moves" box now shows bids.json's
  `claim_list` (the 20,000-season build) and says when it shows the page's own numbers. Left: the per-player rows and
  Try a move still compare at 3,000 seasons (`model.js:255`, `:283`, `:555`). Ranked 24 (was 22).
- **Expected impact:** the page always matches the push at default settings.
- **Effort:** S (inline bids.json's default-setting results in the page and recompute only when a slider moves)
- **Risk:** Low
- **Measure:** rows whose call differs page vs bids.json (one-off check)
- **Design:** `ops/designs/Q-006.md`
- **Decision:** —

### Q-008 · Rivals' adds ignore their drops
- **Status:** designed
- **Area:** War Room v2 (`model.js` `rivalGain`, `threats`, `rivalInputs`; `build.py` `rival_model`)
- **Rank:** 25
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** My adds are valued net of my best drop, but a rival's gain (which sets his predicted bid) assumes he adds without
  dropping anyone. Rosters are full, so a rival with no bench to spare gains less than modeled.
  Nov 13 (for the design): since Q-062 the same `rivalGain` (`model.js:125`, added without a drop) also sets the
  rival-by-rival model's need tiers (`rivalInputs`; `build.py` `need_tier`: under 1, 1-3, 3-6, 6+ lineup points a week),
  and the claim chances are fitted on those same inputs, so a bias that is the same every run is partly learned away.
  Size not measured; the design measures it first. Ranked 25 (was 27).
- **Expected impact:** small: slightly lower price estimates for players only thin-benched rivals need.
- **Effort:** S
- **Risk:** Low
- **Measure:** `wr.price_est_mae`; with Q-064, `wr.rival_brier`
- **Design:** `ops/designs/Q-008.md`
- **Decision:** —

### Q-001 · Simulation doesn't hand freed stars to rivals (denial value)
- **Status:** designed
- **Area:** War Room v2 (`model.js` `simulate`, `gains`)
- **Rank:** 26
- **Added:** 2026-11-03 (Nov 3 slider audit; warroom/README.md "Known limits")
- **Evidence:** The sim keeps current rosters, so a freed star you don't claim never strengthens a rival. In a winner-take-all
  league, a star going to the strongest rival lowers your win odds even if you survive. Not yet measured.
  Nov 13: still in warroom/README.md "Known limits" after the Nov 12 revamp. Designed tonight as measure-first (a
  one-off what-if on weeks 1-9's top freed players), build only if the drops clear the noise floor. Ranked 26 (was 29).
- **Expected impact:** higher values for stars the top rivals need; possibly worth bidding on players who add little to your
  own lineup. Size unknown: first step is to measure how much a rival's win odds move when he wins the top freed player.
- **Effort:** M-L (in each sim, give each unclaimed freed player to his likeliest winner at the estimated price)
- **Risk:** Med (can inflate bids; slower build)
- **Measure:** `rec.would_win`; a one-off what-if on past runs before building
- **Design:** `ops/designs/Q-001.md`
- **Decision:** —

## Done
(Items move here when verified, newest first, with the commit and the health.json numbers that confirmed them.)

### Q-030 · R2: a BTO bet on the Thursday game gets no final check before it locks
- **Status:** verified (fd1551f; first real run Thu Nov 12 4:07pm CT pushed a saved-bet difference)
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
  Nov 11: unchanged; first run Thu Nov 12, 4pm CT.
  Nov 13 (verified): the first real run, Thu Nov 12 4:07pm CT (local task `pool-picks-thu-bto-check`, succeeded in about
  1 minute), found the saved BTO bet didn't match the card and pushed, before the Thursday lock. The one-off passes.
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

### Q-063 · Clear a Fix now line; screenshots in Ask Claude
- **Status:** built Thu Nov 12 ~8:30pm CT at Michael's request (his Ask on issue #4: "Need the ability to clear items
  like this on fix now and also to send screenshots").
- **Clear:** each Fix now line has a Clear button: hidden on that device at once, and a pre-filled GitHub issue
  (label `clear`) that `clear.yml` records in docs/data/cleared.json, so builds leave it out of Fix now, Today and the
  texts everywhere for 7 days or until the problem changes (key = the problem part, letters only; shq/cleared.py).
  Cleared lines list under "N cleared" with Undo (this device).
- **Screenshots:** paste or drag them into the GitHub page the Ask box opens; ask.yml downloads them (GitHub's image
  hosts only, up to 4, no token sent) and Claude reads each one. The Ask button no longer overwrites the clipboard, so
  a copied screenshot survives.
- Not yet verified end to end: no real Clear or screenshot issue has been opened (that would post publicly as Michael).
- Tests: tests/test_cleared.py, tests/test_asks.py (Screenshots).

### Q-062 · War Room revamp: honest win chances, backup claims, Michael's rules as hard checks
- **Status:** built Thu Nov 12 for Tuesday Nov 17's bids (Michael approved plan parts 1-3 through Claude Ops). Details
  in warroom/README.md "Nov 12 revamp". Rival-by-rival prices fitted every build; calls Bid / Coin flip / Long shot /
  Backup by honest chance; backups on one drop (Sleeper's copy rule, worst case = top bid of each chain); rules.json
  (reserve, league-winners cap, marginal claims at $0, never drop this week's starter for an add who wouldn't start);
  bids.json claim_list in Sleeper order with a why per claim; the page shows that list at default settings.
- Replay of weeks 2-9 (prices fitted on earlier weeks only): +12.1 title-odds points for $26 vs +7.4 for the old
  prices and +13.6 for $182 actually bid. Time-forward calibration weeks 6-9: 20% bids won 17% (old ladder: 1%).
- Not done here (plan items 4-6, after Tuesday): phone-first page layout, market check vs Survive The Chop prices,
  post-waiver report card. The three Tuesday job prompts need the staged edits in
  claude-audit/cleanup-2026-11-10/staged-warroom-prompts.md (applied by Claude Ops in a turn Michael types).
- Tests: tests/test_warroom_revamp.py.

### Q-061 · Picks: keep a saved Yahoo pick the card's own season numbers favor; every push says what changed since the last card
- **Status:** shipped (Thu Nov 12 redraft). Found when Ops asked for a picks redraft: Wednesday's card told Michael
  "switch Kansas to West Virginia" while its own "value of taking the other side" note said Kansas raised his chance
  to win the group (0.8% -> 1.0%) and its stats gave Kansas 54%. `pp.cards.keep_saved_picks` now keeps any saved Yahoo
  pick whose season gain is at least 0.05 pts (`MIN_GAIN`; smaller gains are inside the sim's ~0.1-pt noise), with
  reason "Your pick kept: <team> wins N%, adds X pts season chance", drops it from Upset watch, and the CHANGE line no
  longer fires. Kept Kansas (+0.17) and Texas A&M; Cincinnati (+0.03) stayed a switch to Iowa St. (commits 272d470,
  0a2984a; the 0.05 floor, gain-based reason, kept-dog count in the underdog note and clearer note headers came from
  the second-opinion check).
- `pp.push` opens every card push with "Changed since <previous card time>:" and one line per pool change
  (old -> new, with the new card's reason), or "no pick, line or wager changed". The previous card comes from git.
- Tests: tests/test_yahoo_value.py KeepSavedPick, tests/test_pick_push.py ChangedSince.

### Q-060 · NBA values: try DARKO's projected minutes (and shrunk short-sample values) behind a switch, decided by the backtest
- **Status:** shipped (d7244b1, Thu Nov 12). Switch off (`NBA_VALUE_SOURCE = "site"`): nothing changes on the site. The
  nightly model health shows the trial from the next run; first numbers (one complete week, ending Nov 8): swaps per add
  game site +0.10 (n=8, "+N" miss 7.73), DARKO minutes +2.32 (n=10, miss 4.56), shrunk -1.90 (n=6, miss 9.19). Not
  ready (1 week, under 20 swaps). Not dispatched.
  Tightened (5f6a437, Claude Ops: the repo is public, don't republish DARKO's data): `state/nba_darko.json` keeps our
  factor only for my two basketball rosters, the players that morning's swaps and streamers named, and the 10 best free
  agents by value per league (`keep_ids`, TOP_FA); factors to the nearest 0.05; no DARKO as-of date (snapshot v2); the
  run takes the snapshot after the basketball tabs are built. Nov 6-12 rebuilt from the cached reads: 48-52 players a
  day (was 300-470). So DARKO minutes now moves only those players in the trial and on the switch; anyone else keeps
  the site's value. Re-run first numbers (week ending Nov 8): DARKO minutes +3.06/g (n=9, miss 5.87), site and shrunk
  unchanged.
- **Area:** `shq/darko.py` (new), `shq/nba_values.py` (`minutes_z`, `shrunk_z`, `alternative`, `build(source=)`),
  `shq/config.py` (`NBA_VALUE_SOURCE`), `shq/run.py` (daily `darko.track`), `shq/nba_advice_backtest.py` (`trial`,
  `ready_sources`, `darko_source`, `shrunk_source`; `compare_sources` now scores each source's own "+N" miss),
  `shq/health.py` (section `sources`, checks `src.*`), `state/nba_darko.json` (new), `tests/test_darko.py` (new), README
- **Rank:** —
- **Added:** 2026-11-12 by a Sports HQ build session (Michael via Claude Ops: "build DARKO minutes behind a switch, and
  turn it on only if the backtest shows a gain over at least 2 weeks of data"; never republish DARKO's tables, credit
  DARKO, read lightly)
- **Design:** DARKO source = the JSON darko.app's Projections page loads (`/projections/__data.json`, the rows behind its
  "Download CSV" button), always through its Time Machine (`?asof=<CT date>`): each player's pre-game minutes forecast
  for his latest game on or before that morning. Checked first: no robots.txt (404), no terms page; the FAQ says the
  data can be downloaded. The live board (no asof) is a different number (Nov 12: 2.6 min below season averages,
  4.4 min miss on Nov 11's games vs the Time Machine's +0.7 and 3.5; it looks like it counts the chance a player sits),
  so the Time Machine keeps the live switch and the backtest on one number with no peek at the game. One read a day
  from 7am CT (the committed snapshot says whether today is done; `.cache/darko/` keeps reads 14 days, a failed one
  too: no retry), generic User-Agent, never fails a run. Committed: only our minutes factor per ESPN id (DARKO
  minutes / the minutes in his value line), 60 days, one day per line; matched by name without accents (a name two
  ESPN players share is skipped); 470 of 528 matched today. Nov 6-11 backfilled once (6 reads).
  Sources (scale and waiver level stay the site's, as the backtest replays them): `darko_minutes` z' = s(m(mean + sd s
  z) - mean)/sd per category with m clamped to 0.5-1.75 (per-minute production kept, so a bad shooter with more
  minutes hurts FG% more); `shrunk` = a season-valued player's z pulled toward his ESPN season projection's z with
  weight gp / (gp + 10) (K not tuned on the backtest). When on, the basis says "minutes from DARKO (darko.app), as of
  <date>"; DARKO's minutes are never shown.
  Trial (`trial()`): the three sources replayed with the site's rules on the same mornings (those with a DARKO factor),
  scored like the swaps backtest; complete weeks are stored in health.json and stand. Rule
  (`ready_sources`): 2+ complete weeks, 20+ of the source's swaps, and over those weeks (pooled by swaps) a higher
  swap gain per add game AND a smaller miss on its own "+N" than the site's. The note then says "Ready to switch on:
  <source>"; switching is the one config line, made by a session after Michael is told. Caveat: shrunk uses tonight's
  ESPN projection for past mornings (ESPN's in-season projection updates are not confirmed).
- **Verify:** health.json section `sources` each night; when the note says ready, tell Michael, then set the line.
  Nov 13 nightly pass: the section shows (08:55Z): "Ready to switch on: none yet"; 1 complete week; DARKO minutes
  `src.darko_gain` +2.96, `src.darko_err` −1.86 (n=9); shrunk `src.shrunk_gain` −2.0, `src.shrunk_err` +1.46 (n=6).
  The problem it may fix is queued as Q-065 (measuring).

### Q-059 · Model health: did the NBA waiver swaps and streamers pay off?
- **Status:** verified (16eb792). Nov 13 nightly pass: health.json (08:55Z) has section `swaps` with the build's numbers:
  8 swaps judged, `swap.gain` +0.10, `swap.hit` 0.5, `swap.est_err` 7.73, `swap.est_bias` −5.35; 12 streamer pairs,
  `stream.edge` +1.56, `stream.order` 0.83; all info until 20 are judged. The optimistic "+N" it found is Q-065.
- **Area:** `shq/nba_advice_backtest.py` (new), `shq/health.py` (`swaps_health`, `swaps_checks`, `swaps_notes`; section
  `swaps`, checks `swap.*`, `stream.*`), `tests/test_nba_advice_backtest.py` (new), `reviews/2026-11-12-nba-swaps-backtest.md`,
  README
- **Rank:** —
- **Added:** 2026-11-12 by a Sports HQ build session (Michael via Claude Ops: measure the swaps and streamers first; it
  gates the DARKO-minutes change, "turn it on only if the backtest shows a gain over at least 2 weeks")
- **Design:** what the site advised = the first `docs/data/lineups.json` commit at or after 8am CT each day (both
  basketball leagues' `advice.adds` swaps and `advice.games.streamers`, parsed from the shown lines) with the
  `docs/data/players.json` committed with it (names to ESPN ids, category z-scores, that morning's league z scale and
  waiver level). Each item is judged once its fantasy week is over (the advice's own span; "next week" uses the next
  span), on the radar's ESPN pool game logs, in the "+N" units: each game's z on that morning's scale, weighted by that
  morning's need as `nba_swaps.weights` did, minus the waiver level, summed over games played (a missed game adds 0).
  Swap gain = add's actual worth − drop's (dead spot 0), per game of the add; hit = add out-produced the drop; estimate
  error = shown "+N" vs actual (MAE judged, bias shown). Streamers: each vs the next one listed, per game of the
  higher-ranked. A repeat on a later morning of the same week counts once. Scored items are stored in health.json's
  section details and carried forward (ESPN keeps 20 game logs per player; a window the logs rolled past is not scored).
  Tolerances are wide (1.5 z per game, 0.2 hit rate, 4 z miss) because single games are noisy; floors: gain 0, hit 50%,
  streamer edge 0. `compare_sources()` / `compare()` replay the picks under another value source (fn(player, morning) ->
  z list) on the same history and give per-week differences; the replay of the site's own values reproduces 100% of the
  streamers and 67% of the swaps shown (it skips the radar's protected risers and today's Lineup moves).
- **Checked:** 9 fixture tests (fake lineups/players git history and game logs: 8am selection, parsing incl. dead spot,
  IR head and nested day-to-day text, dedupe, partial weeks, carry-over, rolled-off logs, the compare hook, info-until-n
  and baseline); full suite 490 OK. Real history, week ending Nov 8 (Nov 6–8 mornings): 8 swaps, +0.10 z per add game,
  add beat the drop 4 of 8 (50%), shown +4.6 vs actual −0.7 (miss 7.7, bias −5.4: adds valued +1.8/g produced −0.8/g,
  drops −2.7/g produced −0.3/g); 12 streamer pairs, edge +1.56 z per game, higher-ranked better in 10 of 12.
- **Undo:** `git revert 16eb792` and this entry (the section disappears from the next health.json; its baselines, if any
  were set, stay unused in `state/health_baselines.json`).

### Q-058 · NBA rest days and late scratches arrived late: status came only from ESPN
- **Status:** shipped (e363165, Thu Nov 12; renumbered in ded7042). Live from the next cloud run. Not dispatched.
- **Area:** `shq/nba_status.py` (new), `shq/leagues.py` (`Context.nba_gameday`, `EspnLeague._player`/`gameday`, `view`
  `status_basis`), `shq/nba_lineup.py` (`_why`, `pushed_today`, `lines`, `send`), `shq/run.py` (`injury_watch`),
  `shq/digest.py` (`_problem`, `_q_label`), `shq/nba_values.py` (`gd`), `shq/nba_swaps.py` (`status_text`),
  `docs/lib/core.js` (Starters basis), `docs/players/index.html` ("Out today" chip, "Today:" line), `requirements.txt`
  (pypdf 5.1.0), `tests/test_nba_status.py` (new), README
- **Rank:** —
- **Added:** 2026-11-12 by a Sports HQ build session (Michael: add game-day NBA status from two allowed sources)
- **Design:** two free sources on top of ESPN's injury report, both cached in `.cache` and never allowed to fail a run.
  (1) The NBA's official injury report: the season index on official.nba.com (generic user agent; the default one gets
  403), newest PDF parsed by word positions (pypdf) into date, team, player, status, reason; "NOT YET SUBMITTED" =
  unknown. Re-read at most every 10 min on game days, hourly otherwise; the PDF is downloaded only when a newer one is
  listed. (2) Sleeper's public NBA players file (no ESPN ids for NBA, so name + team): injury_status, news_updated;
  every 45 min on game days, 6h otherwise. Precedence: for today's game the official row wins when it's newer than
  ESPN's note (or ESPN has none); an older row that disagrees with ESPN's newer note on whether he plays = unconfirmed
  (Q, nothing acts); no row → Sleeper fills gaps only when newer than ESPN and worse, through `status.confirm` (a Sleeper
  Out ESPN doesn't back is unconfirmed). "Injury Management" + Out = rest: OUT for that game only. Push: a starter newly
  out is a lineup move, so it rides in the one NBA lineup push if it hasn't gone out; after it, the move shows "(new
  since today's lineup push; not pushed)" and the injury watch skips starters whose Out the official report backs. No
  new notification. Display: our status and a short reason ("Out (rest) per NBA injury report, 5:30pm"), credited in a
  basis line on league pages and the Players page; the report itself is never republished or linked.
- **Checked:** 22 fixture tests (PDF words incl. a wrapped reason and a header-less page 2, index links, Sleeper JSON,
  caching and outages, every precedence rule, the push rules); full suite OK. Live, Nov 12 8:50am CT (8:45am report, 29
  players listed, 2 of today's 8 teams not yet submitted; Sleeper 98 tagged): none of the 9 rostered players who play today is on the
  report, so both leagues' statuses are unchanged (Ball is Life: Austin Reaves stays Q from ESPN, no game today).
  Not confirmed: that official.nba.com answers GitHub's runners (if not, ESPN + Sleeper carry on).
- **Undo:** `git revert ded7042 e363165` and this entry (pypdf leaves requirements with the revert).

### Q-057 · Model health: were traded, injured and newly starting players projected right?
- **Status:** verified (a1b34f8). Nov 13 nightly pass: health.json (08:55Z) has section `moved` with week 9 as built: 132
  players (127 injury tags, 0 new teams, 6 new starting QBs), `moved.zeroed` 0, `moved.inactive` 0, `moved.mae` 3.7 vs
  `moved.others_mae` 4.1 (n=293), `moved.mae_gap` −0.4. Week 10 joins with the Tue Nov 17 run.
- **Area:** `shq/health.py` (`moved_week`, `moved_health`, `moved_checks`, `moved_notes`, `scoring_getter`; section
  `moved`, checks `moved.*`), `tests/test_moved_players.py` (new)
- **Rank:** —
- **Added:** 2026-11-12 by a Sports HQ build session (Michael, Nov 12: "how do we test that traded and injured players are
  scored right?"; Q-043's rules had fixture tests only)
- **Design:** once per completed week from week 9 (the players file's git history starts Nov 6): every QB/RB/WR/TE in
  `docs/data/players_nfl.json` (all football leagues, one row per Sleeper id; ESPN ids via Sleeper's `espn_id`, else name
  and team) as committed before the week's first kickoff who had an injury tag (Q/D/OUT/IR/PUP/SUSP) or a
  `state/ir_seen.json` record, a team other than 14 days earlier (the file then, else Sleeper's projections two weeks
  back), or (QB) a projection after his last game week projected at 0 (Sleeper's projections, byes skipped). Projection =
  what the file showed just before his own game (a Thursday Q ruled out Friday showed 0 by Sunday; using the Thursday
  copy flagged 10 false "did not play" in week 9). Actual = Sleeper's weekly stats in that league's scoring (half-PPR if
  unreadable); played = Sleeper recorded a game. Checks (latest week): projected 0 but scored 5+, projected 5+ but did not
  play (both judged vs baseline, tolerance 2), their average miss, everyone else's, and the gap (tolerance 1.5 pts);
  under 10 players = info. Up to 10 flagged players named in the notes. A week counts 5 days 6 hours after its Thursday
  kickoff; scored weeks are kept from last night's health.json (`MOVED_V` bump recomputes).
- **Checked:** 11 fixture tests (fake git copies and Sleeper stats/projections); full suite 459 OK. Real data, week 9:
  132 players in the group (127 injury tags, 0 new teams, 6 new starting QBs), 0 projected 0 who scored 5+, 0 projected
  5+ who sat, average miss 3.7 pts vs 4.1 for the other 293.
- **Undo:** `git revert a1b34f8` and this entry (the section disappears from the next health.json; its baselines stay
  unused in `state/health_baselines.json`).

### Q-056 · Picks page: see what changed between card versions through the week, with line movement charts
- **Status:** shipped (855f18a, Thu Nov 12). The section and card charts show on the live page from the next card
  build that runs this `pp.cards` (the page's HTML carries the one `<script>` tag); the line files grow from the next
  cloud stale-line scan.
- **Area:** `picks/pp/history.py` (new), `picks/pp/cards.py` (`write` rebuilds the history; one `<script>` tag in
  `render`), `picks/pp/lines.py` (`run` appends each scan), `docs/picks/changes.js` (new), `docs/picks/changes.json`,
  `picks/data/card_versions.json`, `docs/data/pick_line_history/2026-wNN.json` (new), `tests/test_pick_history.py` (new)
- **Rank:** —
- **Added:** 2026-11-12 by a Sports HQ build session (Michael, Thu 7:25am: "see quickly and visually ... what has changed
  between iterations throughout the week ... line movements over time and public money information")
- **Design:** (1) **What changed this week** (section above "Pool lines vs market now", jump link under the alerts):
  every version of `picks/data/cards.json` in git (drafts, redrafts, finals, refresh, backup cards; identical rebuilds
  folded; restores marked) plus the uncommitted build, grouped by the card's "Week of" dates, last 4 weeks (week picker).
  Pool tabs (BTO, CFP, Yahoo, Survivor), one at a time: a timeline of versions, the change lines ("Kansas → West Virginia",
  "line -7.5 → -6.5", "cover 58% → 54%", wager, added/dropped, tiebreakers), and per game a small table (versions side by
  side: pick, line, market, cover/win %, wager) with changed cells in red. Win/cover moves under 3 points (Yahoo) or
  2 (BTO/CFP) don't count as changes; Yahoo shows only changed games until "Show all". A "Public %" row appears when cells
  carry a `pub` value (left for the public-betting plan). (2) **Line charts:** market spread (blue, DraftKings via ESPN)
  and pool line (orange dashed), from the picked team's side, step lines per scan, opening line as a hollow dot, D/F/R
  ticks when each card posted, tap for the value at that time; a sparkline under each BTO/CFP pick (Yahoo only when the
  market moved). Data: `pp.lines` (run.yml, Wed-Sat every 2h, 30 min Sat 6-11am) appends one point per game when its line
  changes, plus Yahoo games' market and ESPN openers; seeded from the 52 committed `pick_lines.json` snapshots (week 9 from
  Sat Oct 31, weeks 10-11 from Wednesday 12:45am). One JSON line per file so a data-commit conflict keeps one side whole.
  The cloud backup card (shallow checkout) adds its version via `card_versions.json`. Inline SVG, light and dark.
- **Checked:** 13 fixture tests (version diffs, week grouping, shallow rebuild, series building, the `pp.lines` hook);
  full suite passes. Browser at 375px and desktop, light and dark: no console errors, no sideways scroll.
- **Undo:** `git revert` the commit (removes the section, the charts and the hooks; the data files go with it).

### Q-055 · Picks backup card can't build without a CFBD key, and its failure push doesn't say why
- **Status:** shipped (39dcb9e, Thu Nov 12). Not yet seen in a real backup run (next slot: Thu 8pm BTO final, only if the
  laptop misses it). The workflow was not dispatched (it would overwrite the researched card).
  Nov 13 nightly pass: no `picks-backup.yml` run since 39dcb9e (the last, Thu 5:51am CT, failed before it shipped), so
  still unproven; stays shipped. `CFBD_API_KEY` is still not a secret (Q-019).
- **Area:** `picks/pp/http.py`, `picks/pp/market.py`, `picks/pp/model.py`, `picks/pp/weather.py`, `picks/pp/cards.py`,
  `picks/pp/backup.py` (new), `.github/workflows/picks-backup.yml`, `tests/test_picks_backup.py` (new)
- **Rank:** —
- **Added:** 2026-11-12 (run 43212798455: the Wed 9pm draft backup ran 8h late and failed on
  `RuntimeError: CFBD /lines not cached and no key/budget`; the `CFBD_API_KEY` secret is empty and this week's /lines
  call is gitignored, so the backup could never build a card)
- **Design:** (1) `pp.http.cfbd`: when CFBD can't be called (no key, monthly budget used up, HTTP/network error) the saved
  copy of that call is used at any age; nothing saved raises `CFBDUnavailable` with the reason in plain words.
  (2) `pp.market.lines(year, week)`: this week's saved CFBD lines at any age (card: "used saved CFBD lines as of <time>";
  "save time unknown" in Actions, whose checkout resets file times); else the saved season-wide CFBD /lines for the week,
  with ESPN's public college scoreboard (`groups=80&limit=300`, `competitions[0].odds[0]`) on top, in `consensus()` shape,
  matched by CFBD game id or `pp.names.norm` (as `pp.lines.find`), flipped when ESPN lists home/away the other way;
  nothing anywhere raises `LinesUnavailable` (plain words). The card's Model check names the source. (3) Other CFBD calls
  on the card path: `/games` and game stats use saved copies (tracked in git); `/teams/fbs` falls back to the schedule's
  FBS teams, `/ratings/sp` to a level prior, `/player/returning` to the usual 60%, `/venues` to no weather; `/talent`,
  season stats and current SP+ were already optional. NFL lines (BTO NFL games) never used CFBD: ESPN, then the slate's
  researched line. (4) Pushes: failure says "No picks card reached the site for the <slot> slot, and the backup couldn't
  build one: <reason>." (reason from the build log or the failed step); success text unchanged. A scheduled run whose slot
  already has the laptop's card (fresh=1) sends nothing, and before pushing a backup it re-checks origin/main and stands
  down if the laptop's card landed meanwhile.
- **Checked:** the backup build run locally the way Actions runs it (no key, only the git-tracked CFBD cache): card built
  for week 11 with "used older saved CFBD lines (save time unknown) for 7 games and ESPN's scoreboard for 61 games"
  (local outputs reverted, nothing posted). 18 new fixture tests (no network).
- **Undo:** `git revert 39dcb9e` (and this entry).

### Q-054 · A place to ask about a specific move, for every team (Try a move + Ask Claude)
- **Status:** shipped (5fe47f8, Wed Nov 11 ~9:10am CT). Ask Claude is live: Michael added the `CLAUDE_CODE_OAUTH_TOKEN`
  secret Thu Nov 12 ~7:40pm CT, and his Montgomery question (issue #4) got a real, sourced answer at 7:50pm. Same evening:
  the answer is recorded onto the newest asks.json (a re-run had hit a merge conflict) and a re-ask button (Run workflow
  with an issue number) was added. Try a move needs nothing.
- **Area:** `docs/lib/move.js` (new), `docs/lib/core.js` (box on each league page), `docs/move/` (new page), `docs/index.html`
  (bar under the totals), `warroom/model.js` (`tryMove`, `playerList`), `warroom/app.js` + template, `warroom/build.py`
  (publishes `data.json` + `model.js`; `--repage`), `warroom/trymove.js`, `shq/asks.py`, `.github/workflows/ask.yml`,
  `ops/tasks/ask-claude.md`, `shq/nfl_players.py` (`dynasty` flag)
- **Rank:** —
- **Added:** 2026-11-11 by the Sports HQ build session (Michael's request)
- **Evidence:** Michael, Wed Nov 11: "Where can I have a place where I can ask questions about particular moves? Is it possible
  to have a space in the sports HQ for each team to do this? ... should I put in a claim for KC Concepcion and drop Tre Tucker?
  Should I consider adding Caleb Williams this week while he is unowned and not wanted by the rest of the league?"
- **Design:** (1) **Try a move**, no AI, instant: search any player in the league's data, pick a drop (or let it pick the
  cheapest), up to two moves. Guillotine = War Room v2's own simulation (`tryMove`: win odds, expected weeks alive, this
  week's cut risk, lineup points per week, byes, injury, claim price + win chance when on waivers priced exactly like the
  bids table, "Better drop" hint). Verdict: win odds ±0.3 points decide; inside that noise, the next two weeks' lineup points,
  then the season's (a move that gains nothing and loses points is "Not worth it"). Other football = best lineup in the
  league's own slots this week and next 4 (K/DEF this week only; a K/DEF is never auto-dropped for a skill player),
  ±3 points decide, else depth (rest-of-season per game ±2); dynasty: losing 1,000+ FantasyCalc value turns "worth it" into
  a coin flip, gaining 1,000+ turns a coin flip into "worth it". Basketball = the Players page's trade-check math. Shown on
  every league page (lazy-loaded, state kept through the 5-minute refresh), on `/move/` (league chips), in War Room v2
  (above the bids table), a bar under the home page's totals and the ▦ menu. (2) **Ask Claude**: per-league box opens a
  pre-filled GitHub issue (label `ask`; works where claude.ai is blocked, like Feedback); `ask.yml` runs only for the
  owner's issues, Claude (Opus, claude-code-action) may only read, search the web, run `node warroom/trymove.js` and write
  `.ask/answer.md`; the workflow records it in `docs/data/asks.json` (newest 20 per league), comments and closes the issue.
  Rules in `ops/tasks/ask-claude.md`: verdict first, Sports HQ numbers + War Room model, news under 48h cited with date,
  Michael's guillotine rules. Folded nowhere else: Claude Ops was asked first whether to route through the Queue's
  Go-button runner (it can't be fired from a public site without claude.ai); no reply within 30 minutes, so Sports HQ
  owns it (one answerer per sports question, no schedule).
- **Checked:** this morning's data: Concepcion for Tucker −0.2 points of win odds ("Not worth it": no gain, −2 lineup points
  over the season; his bye is week 11); Caleb Williams for Goedert +0.7 ("Worth it"; "Better drop: Woody Marks", +1.0);
  Jacobs for Marks + Caleb for Goedert +3.4 (+3.7 in this morning's run; simulation noise). Phone 375px and desktop, light
  and dark, no console errors. Node tests emulated in the browser (13/13); full suite 417 OK locally.
- **Guardrails (Claude Ops, Nov 11 ~9:30am):** Ops chose this route over the Go-button runner (that runner has Michael's
  Gmail/Drive/Calendar; a public issue must never reach it). The job runs only for an issue opened by mbryan20 with
  author_association OWNER and the `ask` label (no title fallback, no comments/edits), permissions contents + issues only;
  the prompt answers private topics (job search, investments, health, family) with "Not here: this page is public".
- **Undo:** `git revert 5fe47f8` (and this entry, and the guardrail commit); delete the `ask` label and the secret if added.

### Q-053 · War Room v2 claims two players for one spot, and its plan isn't on the page or linked to the guide
- **Status:** shipped (c3bf006, landed Wed Nov 11 ~8:20am CT; planned for Tue 8pm, delayed because the build session stopped at ~7:30pm)
- **Area:** War Room v2 (`warroom/model.js` `decideAll`, `gainsOnTop`; `warroom/app.js` `planHtml`)
- **Rank:** —
- **Added:** 2026-11-10 by the Sports HQ build session
- **Evidence:** Nov 10 evening, the new model claimed both Harold Fannin and T.J. Hockenson at $0 for Goedert's bye week,
  dropping Breece Hall for Hockenson, with Strange and Freiermuth also free adds at TE: each claim was valued as if it were
  the only one. Michael (7pm): "where's my guillotine breakdown and guide? ... there should be a direct link in the sports
  HQ - no exceptions"; the Google Doc "Guillotine bid strategy (v2)" was not linked anywhere on the site.
- **Design:** (1) claims are settled best first; a later claim at the same position as earlier kept claims is re-valued as
  (chance none of those wins) x its own gain + (chance one wins) x what it adds on top of them (`gainsOnTop`, a simulation
  with both added), then re-priced; if it is no longer worth a bid it becomes Skip, "adds little if your X claim wins (57%)".
  Other positions are unchanged. (2) The War Room's top box now opens with "Your moves before waivers run": every claim
  (bid, win chance, drop), the best free add per position (two at most, with a warning when its drop is a claim's drop), the
  total vs what you can spend, how to place a claim in Sleeper, and a link to the written guide (the Doc).
- **Test:** `BidRules.test_second_claim_at_a_position_counts_what_it_adds_on_top` (Node, CI). Real Nov 10 data: Hockenson
  claim -> Skip, Breece Hall kept; Fannin, Barkley and Warren claims unchanged.
- **Decision:** Michael, Nov 10 7pm (quoted above) and 4:30pm: "I expect improvements to the site and the model."

### Q-041 · War Room v2 drops a usable RB to add a second DEF
- **Status:** shipped (c3bf006, landed Wed Nov 11 ~8:20am CT; planned for Tue 8pm, delayed because the build session stopped at ~7:30pm)
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
- **Design:** `bestDrop`: a K/DEF add skips RB/WR/TE drops worth 8+ (season average or the next 4 weeks' projection); after pricing, a paid K/DEF claim is Skip when a same-position free agent is Add free with at least its season gain.
- **Decision:** approved 2026-11-10 (Michael, 9:15am via Claude Ops: "Get to work ... Tired of delays.")

### Q-040 · An injured or IR player with no projection still gets "Add free"
- **Status:** shipped (c3bf006, landed Wed Nov 11 ~8:20am CT; planned for Tue 8pm, delayed because the build session stopped at ~7:30pm)
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
- **Design:** `outNow(s)`: injury Out or IR, projected 0 this week, not on a bye -> Skip with a why, for free agents and freed players.
- **Decision:** approved 2026-11-10 (Michael, 9:15am via Claude Ops: "Get to work ... Tired of delays.")

### Q-039 · Stated win chances don't match the same row's likely rival bids
- **Status:** shipped (c3bf006, landed Wed Nov 11 ~8:20am CT; planned for Tue 8pm, delayed because the build session stopped at ~7:30pm)
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
- **Design:** `rivalBids(r)` scales each rival guess by priceFor(.5)/estimate (`raw` kept); the page and bids.json use it. $0 ties left as they are: the ladder counts unclaimed players as $0, so most $0 cases had no rival claim at all.
- **Decision:** approved 2026-11-10 (Michael, 9:15am via Claude Ops: "Get to work ... Tired of delays.")

### Q-038 · War Room v2 never credits a $0 bid with its payoff, so it recommends $1 that buys nothing
- **Status:** shipped (c3bf006, landed Wed Nov 11 ~8:20am CT; planned for Tue 8pm, delayed because the build session stopped at ~7:30pm)
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
- **Design:** `decideAll` scores $0 at winChance(0) x value; a $0 pick is call Bid / Coin flip with bid 0 (needs a drop, counts in the budget loop, listed in `bid_options`); `shq/health.py` scores a $0 claim as a win when no rival claimed him.
- **Decision:** approved 2026-11-10 (Michael, 9:15am via Claude Ops: "Get to work ... Tired of delays.")

### Q-050 · Pass-3 review: Guillotine fix and adds contradicted War Room v2; wrong news; weak bench fill-in; small text fixes
- **Status:** verified (16f5558)
- **Area:** `shq/digest.py` (`v2_calls`, `fix_pool`, `_v2_room`, `_room(keep=)`), `shq/advice.py` (`v2_adds`),
  `shq/guillotine.py` (`v2_rows(teams=)`, `live_teams`, `waiting` in the analysis), `shq/run.py` (injury watch uses
  `fix_pool`; ESPN news by name), `shq/swap.py` (`WEAK_FILL`, `fa_over_bench`, `q_tag`), `shq/espn.py` (`pick_news`,
  feed read 5 deep), `shq/trades.py` (Surplus text), `shq/wrapup_render.py` (Next week "As of"), `picks/pp/cards.py`
  (old-card banner), `docs/index.html`, `docs/lib/core.js` (Weekly), tests in `tests/test_digest.py`
  (`PassThreeFixes`), `tests/test_guillotine.py`, `tests/test_espn_news_cache.py` (`OwnNews`)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (pass-3 review, Tue Nov 10 ~6:20pm CT)
- **Evidence:** lineups.json / digest.json Tue Nov 10 6:27pm CT. (1) Guillotine fix "add Harold Fannin Jr. ... drop
  Khalil Shakir ... and start him" for Goedert's bye, while `docs/war-room-v2/bids.json` had Fannin as a $1 waiver claim
  (drop Woody Marks; Shakir is v2's drop for the Barkley claim) and Pat Freiermuth as a free add; the adds said "Jaylen
  Warren for Woody Marks" and "Jordan Love for Braelon Allen" while v2 said Warren for Braelon Allen, Love for Woody
  Marks. (2) bids.json listed "Kirk Cousins, LV" after his trade to MIN. (3) 3-Ball FB "start Kenyon Sadiq (4.0 proj)"
  while Freiermuth (8.2) was a free agent (gap 4.2, under FA_EDGE 5). (4) "Fantasy buzz: Malik Willis placed on IR ..."
  cited for Rhamondre Stevenson and Garrett Wilson (`player_news` took the feed's first item, a roundup). (5) "add Drew
  Lock (Q) (SEA, 15.7 proj)". (6) Stempak "Surplus: Ollie Gordon II, 12.3/gm on your bench" while he starts. (7) Today
  tile showed the 8:02a build time after later refreshes; Weekly "Tuesday's plan had:" inline; wrap-up Next week had no
  as-of; the old picks card kept its "next lock" lines and a 2.85:1 grey chip in dark mode.
  Nov 11 nightly pass (verified, lineups.json 06:50Z against bids.json `d8b4c87`, the v2 build it read): the
  Guillotine fix names Pat Freiermuth, whom v2 calls Add free (not a claim), with v2's drop (Woody Marks); none of
  v2's four claims (Jaylen Warren, Harold Fannin, Saquon Barkley, Spencer Shrader) appears in any fix; all 10 fix
  citations across the 8 leagues quote the player's own note (no roundups); Domo's line reads "add Drew Lock (SEA, Q,
  15.7 proj)".
- **Expected impact:** (1) With v2 current, a guillotine fix names only a player you can add now (no pending claim),
  with v2's drop when v2 lists him, and never drops a player v2 uses as a recommended claim's drop; the league page's
  (and Weekly's) adds are v2's own calls and drops, in v2's order, Priced out skipped. Dashboard-model fallback unchanged.
  (2) v2 rows take SHQ's live team by Sleeper id. (3) A bench fill-in under 5 gives way to a free agent projecting at
  least double. (4) A citation is the player's own note (Rotowire first, else a headline/short story naming him), else
  none. (5) "add Drew Lock (SEA, Q, 15.7 proj)". (6) "beyond your rest-of-season starters". (7) Today tile shows the
  last refresh; Weekly "This morning's plan (replaced by the lines above):" as a list; wrap-up "As of <build>. League
  pages have current advice." (week 9 HTML re-rendered from its saved JSON; PDF fixed forward); the old card hides its
  lock lines and the chip is #666 under white (5.7:1).
- **Effort:** S
- **Risk:** Low (advice text only; nothing is ever added, dropped or bid)
- **Measure:** — (one-off: no guillotine fix names a player on v2's list as a claim; no roundup headline as a citation)
- **Design:** as above. War Room v2 itself (`warroom/`, bids.json) untouched.
- **Decision:** bug fixes requested by Michael via Claude Ops (pass-3 review), Nov 10

### Q-045 · NBA radar health warnings came mostly from the metric; fix the backtest, then two small model fixes
- **Status:** verified (74ba172)
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
  Nov 11 nightly pass (verified, health run 08:55Z): the radar section shows no warnings. `radar.edge` +0.43 z per
  game (n=30; +0.34 on n=25 at the re-set baseline, so the 5 flags scored since are out of sample and kept it
  positive), ok; `radar.held` 0.70 (n=10, no new shown flags scored yet), ok; `radar.held_all` 0.63 (n=41, was 38).
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

### Q-044 · The Guillotine league page said every TE was "priced out" while War Room v2 said free add or $1
- **Status:** verified (aac5193)
- **Area:** `shq/guillotine.py` (`load_v2`, `v2_current`, `v2_rows`, `on_waivers`, `RESERVE` 10 → 5), `docs/lib/core.js`
  (`bidText`, bid section, home tile and inbox lines), `tests/test_guillotine.py` (`WarRoomV2`)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (contradiction reported via Claude Ops)
- **Evidence:** lineups.json, Tue Nov 10 2026: every TE (Freiermuth, Fannin, Strange, Hockenson, Higbee) "priced out:
  rivals may go $4, worth $0 to you", shown on the tile/inbox as "Bid: Pat Freiermuth … priced out"; bids.json the same
  day: Freiermuth and Brenton Strange "Add free", Harold Fannin "Bid $1". Cause: `RESERVE = 10` (all of Michael's $10, so
  `my_max` was always $0) against v2's `reserve: 5`, and the model priced plain free agents as waiver bids.
  Nov 11 nightly pass (verified, lineups.json 06:50Z against bids.json `d8b4c87`): the Guillotine page's fix (Pat
  Freiermuth, add free, drop Woody Marks) and its three adds (Jaylen Warren coin flip $2, drop Braelon Allen; Kirk
  Cousins and Jordan Love add free, drop Woody Marks) match v2's call, bid and drop for each player; no "worth $0"
  line anywhere in lineups.json.
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

### Q-042 · A lineup fix says "start" a bench player projected 0 while a free agent projects 15+
- **Status:** verified (e508112; follow-ups 62b64be, 116fe5f: a Questionable free agent 3+ better than the best healthy one is named, marked "(Q)")
- **Area:** `shq/digest.py` (`_fix`, `_room`: Today digest, league-tab fixes, digest push), `shq/run.py` (`injury_watch`
  pushes), `shq/swap.py` (`slot_fa`, `fa_over_bench`, `MIN_FILL` 1.0, `FA_EDGE` 5.0), `shq/advice.py` (values loaded before
  the fixes so a fix can name the waivers drop)
- **Rank:** —
- **Added:** 2026-11-10 by a Sports HQ build session (bug on the Domo Arigato league card, reported via Claude Ops)
- **Evidence:** lineups.json, Tue Nov 10 4:37pm CT: Domo Arigato fix "Caleb Williams (QB) on BYE → start Carson Wentz", with
  no projection shown; Wentz projected 0 this week and the next 4 (a backup after Cousins' trade to MIN), while the same
  card's adds named Drew Lock (SEA, 15.7 this week). `_fix` took any playable bench player whatever his projection and
  printed the projection only when above 0; the injury watch had the same "any playable bench player" rule.
  Nov 11 nightly pass (verified, lineups.json 06:50Z): Domo Arigato's fix reads "Caleb Williams (QB) on BYE → add Drew
  Lock (SEA, Q, 15.7 proj) into your open roster spot and start him (Carson Wentz projects 0)"; no football fix in the
  6 leagues says start a 0-point player (the bench starts shown project 9.8 and 12.8; 3-Ball FB's fallback Kenyon
  Sadiq 4.0 sits behind a free-agent add).
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
