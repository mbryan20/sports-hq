# Pool Picks weekly runbook

The scheduled tasks call this file with a STAGE. Work in `C:\Claude\sports-hq\picks` (Pool Picks is part of Sports HQ). Python is `py`. The CFBD key is in `.env` (never print it). The ntfy topic is in `.ntfy_topic`.

The page is https://mbryan20.github.io/sports-hq/picks/ and is built from `../docs/picks/` (the Sports HQ repo's `docs/picks/`) on `main`.

## Hard rules
- **Read-only on pool sites.** Never submit, save or change picks. Never sign in, sign out or type a password. If a site shows a sign-in page, record "slate not confirmed (signed out)" in the slate file. Send a push saying which site needs Michael to sign in to in his Chrome, then continue with what you have.
- Follow `../docs/picks/method/pool-method.md`. Research fresh every run: prior opinions and old research files are not evidence. Use sources published in the last 7 days.
- Every pick's reason is 12 words or fewer and has a source link. Tiebreakers show one alternate.
- Survivor: Michael was eliminated in Week 7. Don't make survivor picks.
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
   - NFL games: put `adj_home_pts` (net research adjustment to the home margin) and `why: [{reason, source}]` on the BTO slate entry.
   - Later runs in the same week must re-verify earlier items: carry an item forward only after you re-confirm it this run.
4. **Build:** `py -m pp.cards --stage <draft|final|refresh>`. bto_final uses `--stage final --pools bto,yahoo`.
   - The build pulls ESPN's current line (DraftKings, 15-min cache) on top of CFBD's consensus, so ATS cards center on the market at build time; the card's Model check names the line source and time. On the Sat refresh a pick that moved to a different game is flagged red too.
   - Stale lines: `py -m pp.lines --no-push` prints today's pool-vs-market gaps (the cloud scan in run.yml pushes them Wed–Sat).
   - Read `data/cards.json`. Sanity-check every row: no pick on a locked game, reasons ≤ 12 words, links work.
   - Check that any underdog shows its signals. Check that the BTO picks obey the mode rules (count, Big Game, 2× rule, $10 multiples).
5. **Publish:** `py -m pp.publish --stage <stage>`. This commits, pushes, waits for Pages, then sends the ntfy push.
6. Open https://mbryan20.github.io/sports-hq/picks/ in the browser and confirm the new timestamp shows.

### Stage specifics
- **draft** (Wed 9pm): all pools. Cards are labeled DRAFT.
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
5. Also check whether this week's BTO, CFP and Yahoo slates are posted. If they are, write them into the next slate file so Wednesday's draft is ready.
6. `py -m pp.publish --stage postmortem --title "Pool Picks postmortem posted" --msg "Week NN graded: <one-line summary>. Tap for history."`

### Wednesday catch-up
At the start of every Wed 9pm draft run, check whether `data/postmortem/2026-wNN.json` exists for last week. If it doesn't (the Tuesday run was missed), run the whole postmortem above first, including its publish and push, and then do the draft.

## If something fails
Publish what you have. Never leave the page stale without saying so. Send a push that names the failure in one line.
