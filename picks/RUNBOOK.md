# Pool Picks weekly runbook

The scheduled tasks call this file with a STAGE. Work in `C:\Claude\sports-hq\picks` (Pool Picks is part of Sports HQ). Python is `py`. The CFBD key is in `.env` (never print it). The ntfy topic is in `.ntfy_topic`.

The page is https://mbryan20.github.io/sports-hq/picks/ and is built from `../docs/picks/` (the Sports HQ repo's `docs/picks/`) on `main`.

## Hard rules
- **Read-only on pool sites.** Never submit, save or change picks. Never sign in, sign out or type a password. If a site shows a sign-in page, record "slate not confirmed (signed out)" in the slate file. Send a push saying which site needs Michael to sign in to in his Chrome, then continue with what you have.
- Follow `../docs/picks/method/pool-method.md`. Research fresh every run: prior opinions and old research files are not evidence. Use sources published in the last 7 days.
- Every pick's reason is 12 words or fewer and has a source link. Tiebreakers show one alternate.
- Survivor: Michael was eliminated in Week 7 (his NYJ pick lost; the Option 2 split paid $1,000 on Oct 23). Don't make survivor picks. If a newer email from shaunguhy@gmail.com says otherwise (still alive, or the remaining entries chopped), report it in one line: put it in the slate as `"survivor_note": "<one line>"` and it goes in the push.
- **Sports HQ Picks is Michael's only pool picker** (the cloud "Football pools picks" task is being retired). Every card run (draft, bto_final, final, refresh) does the four steps in "Every card run" below: saved picks, decisions log, second opinion, standalone push.
- Stay under 1,000 CFBD calls/month. `pp/http.py` caches and caps at 900, so don't bypass it.

## Weeks
- CFBD week N = Yahoo week N = BTO week N. For example, CFBD 9 is the Oct 31 slate, Yahoo week 9 and BTO week 9 (NFL week 8). (Checked 10/27 on the Yahoo week selector; the old "N+1" was wrong.)
- `py -c "from pp.cards import current_week; print(current_week())"` prints the CFBD week of the next games.
- Slate file: `slates/2026-wNN.json` (NN = CFBD week). `slates/2026-w09.json` is the schema example.

## Steps for STAGE = draft (Wed 9pm), bto_final (Thu 8pm), final (Fri 9pm), refresh (Sat 8am)
1. `git pull`.
2. **Read the slates** in Michael's Chrome via Claude in Chrome (follow `../ops/BROWSER.md`; never the Claude app's built-in browser, which loses sign-ins).
   - Yahoo: `https://football.fantasysports.yahoo.com/college/3659/9/picks?week=<week>` (9 is Michael's team ID, not a week; other numbers show other members' picks) has the 25 games, kick times, TB1 games, TB2 deadline and pick distribution. The group page `https://football.fantasysports.yahoo.com/college/3659` has the standings.
   - BTO: `https://beattheoddspickem.com/player/picks/current` has the 16 games, visitor spreads, Big Game and lock state. `/player/dashboard` has the balance, `/player/leaderboard` has every balance and Michael's status (normal / Three Bet / One Bet). Use ESPN abbreviations for NFL teams.
   - CFP: `https://ncaa-pool-two.vercel.app/player/picks` has the games and spreads; `/player/leaderboard` has all balances.
   - Write or update the slate file:
     - `bto.games`: `[{league: "CFB"|"NFL", away, home, home_spread, big: bool, kick, locked: bool}]`, plus `bto.field` (other players' balances), `bto.mode` ("normal"/"three"/"one"), `bto.balance`, `bto.weeks_left`.
     - `cfp.games`: `[{away, home, home_spread, kick}]`, plus `cfp.field`, `cfp.balance`, `cfp.weeks_left`, `cfp.rebuy_window` (false after 11am Nov 7).
     - `home_spread` is the HOME team's line (negative = home favored). Convert from the visitor spread the site shows.
     - Skip over/under games and games already locked.
3. **Research** (fresh). For every slate game, check QB status, key injuries and suspensions, line movement (open vs now; investigate moves of 2+ points or through 3/7), and weather.
   - College: write `research/2026-wNN-<stage>.json` in the schema of `research/2026-w09-injuries.json`: `{team, off_pts, def_pts, status, reason, source, published}`.
   - **Weigh injuries by position value, then size the points.** Rough guide for one starter missing (backup quality moves it):
     QB 2–7 (depends on the drop to the backup); elite edge rusher, LT or CB1 0.5–1; RB1, WR1 or TE1 0.3–0.75; safety, LB,
     interior OL (center, guard) or DT 0.1–0.3. Several starters out in one unit add up (three OL out matters more than one).
   - **Keep `reason` in step with `status`.** When a re-check changes a status (doubtful → questionable, or a starter named),
     rewrite the reason and update `source`/`published` to the newest report. Oct 31: Illinois' status said "questionable"
     while its reason still said "starter out".
   - **Only cite an injury as a pick's reason if it's worth 0.5+ points, or it's part of a unit that is.** Smaller items stay in
     the research file and the breakdown, not in the card's one-line reason.
   - NFL games: put `adj_home_pts` (net research adjustment to the home margin) and `why: [{reason, source}]` on the BTO slate entry.
   - Later runs in the same week must re-verify earlier items: carry an item forward only after you re-confirm it this run.
4. **Build:** `py -m pp.cards --stage <draft|final|refresh>`. bto_final uses `--stage final --pools bto,yahoo`.
   - The build pulls ESPN's current line (DraftKings, 15-min cache) on top of CFBD's consensus, so ATS cards center on the market at build time; the card's Model check names the line source and time. On the Sat refresh a pick that moved to a different game is flagged red too.
   - Stale lines: `py -m pp.lines --no-push` prints today's pool-vs-market gaps (the cloud scan in run.yml pushes them Wed–Sat).
   - Breakdowns: every game on the page gets a tap-to-open panel, built automatically by the same command. NFL panels use nflverse play-by-play (downloaded at most once per 20h into `cache/nflverse/`, ~7-19 MB per season, gitignored); if the download fails they fall back to scores. NFL BTO picks center on the market + research (`pp/nfl.py` MODEL_W = 0, from `py -m pp.backtest --nfl`). `py -m pp.cards --render-only` redraws them around the posted `data/cards.json` without changing any pick.
   - Read `data/cards.json`. Sanity-check every row: no pick on a locked game, reasons ≤ 12 words, links work.
   - Check that any underdog shows its signals. Check that the BTO picks obey the mode rules (count, Big Game, 2× rule, $10 multiples).
5. **Publish:** after the second opinion (C below), `py -m pp.publish --stage <stage>`. This commits, merges (never rebases), pushes, waits for Pages, then sends the standalone ntfy push (D below).
6. Open https://mbryan20.github.io/sports-hq/picks/ in the browser and confirm the new timestamp shows.

### Every card run: saved picks, decisions log, second opinion, push
These are part of steps 2, 4 and 5 for every card stage. The schemas are in the docstring of `pp/push.py`.

**A. Saved picks (step 2, read-only).** In the same Chrome tabs, read what Michael has already saved on each site. Never click Save, Submit or any pick.
- BTO `https://beattheoddspickem.com/player/picks/current`: his saved bets (pick, adjusted line incl. line points, wager). `get_page_text` can return nothing there; read it with `javascript_tool` → `document.body.innerText` (in pieces if long).
- CFP `https://ncaa-pool-two.vercel.app/player/picks`: his saved sides, wagers and "Total wagered".
- Yahoo `https://football.fantasysports.yahoo.com/college/3659/9/picks?week=<week>`: his saved winners, both TB1 score pairs and TB2 most/fewest. An empty TB box counts as unsaved.
- Write them to the slate file:
  - `bto.saved` / `cfp.saved` = `{"read": "<ISO time>", "bets": [{"key": "<Away>@<Home>", "pick": "<Team> <line incl. LP>", "wager": 1300}]}`. Use an empty `bets` list when nothing is saved.
  - `yahoo.saved` = `{"read": ..., "picks": {"<Away>@<Home>": "<Team>"}, "tb1": {"<Away>@<Home>": "<Away> 17, <Home> 20"}, "tb2": {"most": "<Team>", "fewest": "<Team>"}}`.
  - Keys and team spellings must match the slate games (NFL uses ESPN abbreviations).
  - If a site is signed out: `{"unread": "signed out"}`.
- The build compares them with the card. Each difference becomes a line at the top of the page and the push: `CHANGE: <pool>: yours <X> → card <Y> (<reason>)`.
  - BTO and CFP bets are one package, so any difference is one line.
  - Yahoo gets one line per game or tiebreaker. Games already kicked off are skipped.
  - On Thu, Fri and Sat runs, anything still unsaved is a CHANGE too. (Oct 31: an unsaved TB1, Wisconsin @ Iowa, was caught before the 11am lock.)

**B. Decisions log (step 2).** Read the Google Doc "Decisions log (agreed with Michael)" with the Google Docs connector (`read_doc`, id `1sQYBSQdJ7nrzLzBYx5y9UUAVg38dVgPSAqTEpPiKSfY`).
- Its entries are Michael's decisions. Newest first; format `date | area | decision | where it lives`.
- After the build (step 4), compare the card with every football-pools entry that still applies: a pick, a sizing strategy, a format rule, survivor status.
- Where the card departs from one, add it to the slate: `"decisions": {"read": "<ISO>", "differs": [{"date": "Oct 23", "old": "<decision>", "new": "<card>", "because": "<new evidence>"}]}`. The page and push lead with `Differs from your decision on <date>: <old> → <new>, because <evidence>`.
  - Never change course silently.
  - Re-run `py -m pp.cards --render-only` (picks unchanged) so the page shows it.
- Don't copy the doc's other entries into the repo. It's Michael's private log, and the repo is public.
- When Michael confirms a new pool choice in the conversation that started this run, insert a line at the top of the entries (right after the "Newest first" line) with `update_doc`: `YYYY-MM-DD | Football pools: <pool> (week N) | <decision> | <site> (saved)`.
- If the connector or a permission check blocks the read, don't work around it. Set `"decisions": {"unread": "<what blocked it>"}`; the push then says the log wasn't read.

**C. Second opinion (after step 4, before publishing).**
1. Run `py -m pp.checks`. It prints the automatic checks:
   - format per pool;
   - BTO mode count, Big Game, total vs minimum, $10 multiples, 2× rule, line points, lines = pool line + LP, no locked game;
   - CFP 50–100% and posted spreads;
   - Yahoo 25 picks, TB1 and TB2 set;
   - no conditional picks.

   It also prints the push's CHANGE / Differs lines.
2. Spawn one subagent (Agent tool) that did not build the card. Give it:
   - `data/cards.json` and the slate file;
   - `../docs/picks/method/pool-rules.md`;
   - the Decisions log text;
   - the `pp.checks` output.

   Have it check:
   - each pool's format (BTO/CFP against the spread, Yahoo straight-up);
   - lock times, wager rules and minimums;
   - that nothing contradicts a decision or a saved pick without its CHANGE / Differs line;
   - no "if X then Y" hedging anywhere on the card;
   - that the numbers add up.
3. Fix everything it finds (rebuild if a pick or wager changes), then re-run `py -m pp.checks`.
4. Record the verdict: `py -m pp.checks --record "Checked: <what passed>"`. Add `; not fixed: <item>` for anything you couldn't fix. This puts "Checked: …" on the page (redrawn, picks unchanged).
5. A fresh build resets it to "pending", so record after the last build.

**D. Standalone push (step 5).** `py -m pp.publish` builds the push from the card and slate, so don't pass `--msg` for card stages. Preview it first with `py -m pp.push`. Order:
1. `CHANGE:` and `Differs from your decision` lines.
2. Picks that moved since the last post.
3. One line per pool due before the next run:
   - Wed: BTO, CFP and Yahoo. Thu: BTO and Yahoo. Fri and Sat: CFP and Yahoo. Override with `--due bto,yahoo`.
   - Formats: `BTO (locks Fri 8pm): <bet> <line> $<amt>; …`, `CFP (locks Sat 11am): <team> <spread> <pts>`, `Yahoo: <N> set; close calls …; TB1 …; TB2 …`.
   - A pool whose saved picks match the card says `<pool>: your saved picks match`.
4. The page link.

### Stage specifics
- **draft** (Wed 9pm): all pools. Cards are labeled DRAFT. Also search Gmail (connector, read-only) for emails from shaunguhy@gmail.com newer than the last survivor entry in the Decisions log; only if one says Michael is still alive or the pool chopped, set `survivor_note`.
- **bto_final** (Thu 8pm): BTO FINAL. Also finalize Yahoo's Friday games and TB2, since TB2 locks before Friday's first game. Thursday NFL games may already be locked; never pick a locked game.
- **final** (Fri 9pm): CFP and Yahoo FINAL. Friday Yahoo games and TB2 are already locked; leave them as posted Thursday.
- **refresh** (Sat 8am): re-check injuries and QB news only. `--stage refresh` moves any changed pick to the top in red, and the push lists the changes. CFP locks at 11am, so flag any CFP change clearly.

## STAGE = postmortem (Tue 8pm; Wednesday catch-up)
Grade last week. Last week = the CFBD week whose games just finished, which is `current_week() - 1` on Tue/Wed.
1. `git pull`. If `data/postmortem/2026-wNN.json` already exists for last week, it was already graded: skip steps 2–4 and go to step 5.
2. **Read what Michael actually entered.** In Michael's Chrome (`../ops/BROWSER.md`), read-only, never change anything:
   - BTO: `/player/history` has last week's picks, lines incl. line points, and wagers. The dashboard and `/player/leaderboard` have the balance and rank.
   - CFP: `https://ncaa-pool-two.vercel.app/player/history` (or Individual Picks) has his picks and wagers. `/player/leaderboard` has the balance and rank.
   - Yahoo: `https://football.fantasysports.yahoo.com/college/3659/9/picks?week=<week>` (9 is Michael's team ID, not a week; other numbers show other members' picks) has his picks and tiebreakers. The group page has the standings.
   - Write `data/entries/2026-wNN.json`:
     ```
     {"yahoo": {"<Away>@<Home>": {"pick": "<Team>"}},
      "bto": {"<Away>@<Home>": {"pick": "<Team> <line incl. LP, e.g. +4.5>", "wager": "$400", "game": "<Away> @ <Home>"}},
      "cfp": {...same as bto...},
      "standings": {"bto": "...", "cfp": "...", "yahoo": "..."}}
     ```
     - Keys must match the card keys in `data/published/2026-wNN-<pool>.json`. Use the same team spellings; NFL uses ESPN abbreviations.
     - Include entries on games the card didn't pick, using game keys in the same format.
   - If a site is signed out, skip that pool's entries, say so in the history, and keep going.
3. **Grade:** `py -m pp.grade --week NN`. This grades the card picks and the entries against final scores, lists every place the entry differs from the card, and writes `data/postmortem/2026-wNN.json` (which marks the week as graded).
4. **Append** to `../docs/picks/history.md` a dated section for the week:
   - Each pool's record: card vs entered, plus net for BTO/CFP.
   - Current standings.
   - For each difference between the card and the entry: which call was better and why, judged on the information available before kickoff, not just the result.
   - Exactly 3 bullets that separate process from outcome: (1) a good decision that lost or a bad one that won; (2) card vs entries, where Michael's judgment added or cost value and whether that's repeatable; (3) one generalizable lesson, or "no change".
   - No team-specific permanent rules.
4b. **Refresh the Yahoo group profile** (feeds the card's "value of taking the other side"). Both pages are read-only:
   - Standings: `https://football.fantasysports.yahoo.com/college/3659` → write `.private/standings.json` as
     `{"me": "Michael B.", "read": "<date>", "points": {member: total}}` (Rank / Pick Set Name / Total table).
   - Group picks for the graded week: in that tab, fetch `/college/3659/grouppicks?week=NN` and `...&pg=2` (games 14-25)
     and parse each `table tr` (rows "Favored", "Spread", "Underdog", then one row per member). Add the week to
     `.private/grouppicks_2026.json` as `{"g": "FAV,spread,DOG;...", "p": {member: "F"/"D"/"-" per game}}`. Keep results
     short (Claude in Chrome cuts JS results at ~1,000 chars): put the JSON in a `<pre>` and read it with get_page_text.
   - Run `py -m pp.pool_profile`. It writes the anonymous `data/pool_profile.json`; publish commits it.
   - `.private/` is gitignored: member names and their picks are the group's private data and never go in the repo.
5. Also check whether this week's BTO, CFP and Yahoo slates are posted. If they are, write them into the next slate file so Wednesday's draft is ready.
6. `py -m pp.publish --stage postmortem --title "Pool Picks postmortem posted" --msg "Week NN graded: <one-line summary>. Tap for history."`

### Wednesday catch-up
At the start of every Wed 9pm draft run, check whether `data/postmortem/2026-wNN.json` exists for last week. If it doesn't (the Tuesday run was missed), run the whole postmortem above first, including its publish and push, and then do the draft.

## If something fails
Publish what you have. Never leave the page stale without saying so. Send a push that names the failure in one line.
