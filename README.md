# Sports HQ

Michael's all-in-one fantasy sports system: **https://mbryan20.github.io/sports-hq/**
(phone: Safari → Share → Add to Home Screen). Works where claude.ai is blocked.

## What's on the site

The main page is a dashboard (layout A, Scoreboard): totals across the top (fixes, moves, pick edges, guillotine
odds, next lock), then a tile per league with its projected score, what needs fixing and the top move; tap a tile for the
full league page. The ▦ menu at the top switches to the other layouts: B Command center (one ranked to-do list across
all leagues and pools), C Deck (a card per league, swipe on a phone) and D Game day (starters by kickoff). Code:
`docs/index.html`, `docs/lab/`, shared `docs/lib/core.js` + `core.css`.

| Tile / page | What | Source |
|---|---|---|
| Today | daily 8am CT check: starters on bye/out/doubtful with the fix, today's locks, guillotine rank, Friday picks deadlines | cloud, daily |
| Kosmonauts | Yahoo, 0.5 PPR, no flex | roster + top free agents read twice daily by the laptop (Yahoo API approval pending) |
| Domo Arigato | Sleeper "Sunday's Best", dynasty, superflex | Sleeper API (cloud) |
| Guillotine | Sleeper "Damon's Guillotine League" | Sleeper API (cloud) |
| 3-Ball FB / 3-Ball BB | ESPN 3-Ball Dynasty (football, basketball) | ESPN API, public league (cloud) |
| Stempak, Bro-vid19 | ESPN football, private | laptop snapshot with Michael's ESPN sign-in |
| Ball is Life | ESPN "We playin basketball", 8-cat, private | laptop snapshot |
| Weekly | start/sit + top 3 adds per league (basketball: drop/add swaps on category value) | Tuesday 7am CT |
| Wrap-up (`/wrapups/`, header link) | weekend wrap-up: every league's result, bench points, booms/busts, cited injuries, next week's moves, pools, War Room bids; a phone-sized PDF plus a web page, archived per week; push opens the PDF | cloud, Sunday night after the late games + final Tuesday 8am CT |
| Picks | BTO, CFP, Yahoo pick'em cards (Pool Picks, in `picks/`) | laptop Claude runs Tue–Sat |
| War Room | Guillotine bid/elimination model (copy of the War Room artifact) | laptop sync, daily |
| War Room v2 (`/war-room-v2/`) | Same model, rebuilt from Sleeper's API in git (`warroom/`), plus `bids.json` for the AI write-up and bid check | GitHub, `war-room-v2.yml` (daily 6:10am, Mon night, Tue morning, Wed after waivers) |
| Players (`/players/`, header link, ▦ menu, "Players" on each NBA league page) | every NBA player in each basketball league: sort by value, this week, games, minutes or any category; filter available / mine, position, health, rising or falling minutes, games this week and next, and the categories he should help in (ranked by fit); tap a row for his full line. Phone: key columns plus a category heat strip. **⇄ Trade check**: tap + on players to give and get, and the tray gives a verdict (value per game above waiver level, fit to your weakest categories, and for 3-Ball an age curve; `shq/nba_trade.py`) | `docs/data/players.json` (cloud, every run) |
| Layouts lab (`/lab/`) | where new layout ideas are tried; 👍/👎 and 💬 Feedback on every page | same data files |

Each league page (tap its tile) opens with a **What to do** section (`shq/advice.py`, rebuilt every run): matchup outlook or
guillotine survival odds and FAAB bid ranges (`shq/guillotine.py`), fixes for starters who can't play, start/sit
moves, waiver adds on rest-of-season value with who to drop and a FAAB bid range (`shq/waivers.py`), trade ideas
for the football leagues (weak spots, surplus, up to 3 fair offers that help both lineups, from FantasyCalc
values; `shq/trades.py`), FAAB left. NBA category leagues also get a category table (my total, the opponent's,
win/lose/close by the rest-of-week projection), which close categories to chase and with whom, and free agents
strong in them (`shq/categories.py`), plus a **Trend radar** (`shq/radar.py`): free agents and bench players whose minutes, usage or starts just jumped (tied to the cited injury behind it and ranked by the categories I need), my players losing minutes, and who absorbs each injured starter's minutes, from ESPN game logs. Every NBA player also has a **category value** (`shq/nba_values.py`): value per game in that
league's own categories, rank, and this week's value (games left), from this season's averages after 5 games and ESPN's
projection before; it shows on each roster row and is written to `docs/data/players.json`. Basketball **waiver adds are
swaps** (`shq/nba_swaps.py`): "Drop X, add Y: +N this week (helps AST, 3PM)", up to 3, need-weighted by this week's
categories, dead roster spots (no NBA team) first; dynasty never drops anyone 40%+ rostered or under 24 (ages from ESPN's
team rosters, `shq/nba_ages.py`). **Games & streamers** (`shq/nba_games.py`): games per NBA team for the rest of this week
and next week with back-to-backs, my games left vs my opponent's and next week's, and the top 3 streamers. The radar's top lines also go in the Today digest, and a rising free agent under 30% owned in a category I need gets one push. Ideas only: nothing is ever sent to a fantasy site.
What's next and the hand-off rules live in **ROADMAP.md**.

The footer shows the last cloud run and when each laptop job last delivered.

## Two engines

**Cloud (GitHub Actions, no AI, laptop not needed)** — `.github/workflows/run.yml` → `shq/run.py`
- Refreshes every league, builds the Lineup tabs, writes `docs/data/*.json`, commits each run.
- Injury watch: from 2h before each kickoff/tip-off until it locks, every 10 min. Starter OUT/IR/inactive →
  Yahoo: swap via API (when write access exists) and confirm; everyone else: push the exact swap. No healthy
  bench option → push the best free agent. Never adds or drops.
- GitHub drops many scheduled triggers, so a run keeps looping every 10 min while a watch window is open or
  opens within 3h (up to ~5h45m per run). Times come from real kickoffs, so DST doesn't matter.
- Weekend wrap-up (`shq/wrapup.py`, `shq/wrapup_render.py`): Sunday edition on the first run after every Sunday game
  is final, final edition from Tuesday 8am CT; writes `docs/wrapups/<season>-wNN.{pdf,html,json}` and the archive, pushes
  the PDF link (3-min ntfy delay so Pages has published it). Run one by hand: Actions → Sports HQ run → `force_wrapup`, or
  locally `py -m shq.wrapup --week N --edition final [--push]`.
- Daily digest (`shq/digest.py`): first run after 8am CT fills the Today tab; pushes once only if something
  needs fixing (dead starter or empty slot, guillotine bottom 3, Friday picks deadlines). Late runs (after 1pm) update the
  tab without pushing. NBA lineup fixes are listed there but pushed by the **NBA lineup push** (`shq/nba_lineup.py`): at
  most one a day for both basketball leagues, from 3h before the first affected tip-off, only when a starter has no game,
  is out or the slot is empty and a bench player who plays today can fill it, or a bench player who plays today is worth
  1+ value per game more than a playing starter. The same moves show as "Lineup moves" on the tabs.
- **Laptop kick** (Windows Task Scheduler, `ops/kick.ps1`, no AI): GitHub runs scheduled jobs hours late, so the laptop
  starts `run.yml` at 7:02am CT and hourly to 11:02pm (skipped when data was committed in the last 20 min) and
  `model-health.yml` at 2:55am. A dispatched run gets its own concurrency group, so it is never dropped; a run that finds
  another one looping does one pass and stops; the digest checks `origin/main` so it is built and pushed once. Tasks and how
  to remove them: `ops/designs/Q-014.md` "As built".
- Alerts if a laptop job's data goes stale (>30h) and on any failed run.
- `picks-backup.yml` posts a model-only picks card if a laptop picks run misses its slot (needs the
  `CFBD_API_KEY` secret). `test.yml` runs the tests on every push. `feedback.yml` logs site feedback issues to FEEDBACK.md.
- Model health (`model-health.yml` → `shq/health.py`, nightly 2:50am CT, backup 4:50am): re-tests every model against what
  happened and writes `docs/data/health.json`: War Room v2's projection error (Sleeper vs the old blend), score swing (and
  2-4 weeks ahead, from the page's git history), cut-prediction log-loss vs a coin toss, price-ladder coverage (leave one
  waiver run out, by position and season stage); our bids vs the waiver results (would they have won, what winners paid);
  the cut odds the dashboard and v2 showed before kickoff; the NBA radar backtest; Pool Picks' stored backtest and graded
  cards. Each check is compared with `state/health_baselines.json` (set from its first measurement): ok / watch / drift,
  or weak when it doesn't beat the simple alternative. No push; the nightly improvement pass reads it.

**Laptop (Claude scheduled tasks in the desktop app; they read sign-in sites in Michael's Chrome — see `ops/BROWSER.md`)**

| Task | When | Does |
|---|---|---|
| Sports HQ: daily laptop sync | 7:30am, 4:30pm (before the 8am digest) | Kosmonauts roster + free agents (Yahoo), private ESPN snapshots, War Room copy |
| Sports HQ: Picks Tue 8pm postmortem | Tue | grade last week's cards and entries |
| Sports HQ: Picks Wed 9pm drafts | Wed | draft cards for BTO, CFP, Yahoo |
| Sports HQ: Picks Thu 4pm BTO check (`ops/tasks/pool-picks-thu-bto-check.md`; prompt ready, task created by Claude Ops) | Thu 4pm | only in weeks with a Thursday BTO game: saved BTO bets vs the published card (`py -m pp.thu_check`), push only if they differ, with "yours → card" lines and the lock time |
| Sports HQ: Picks Thu 8pm BTO final | Thu | BTO final + Yahoo Friday/TB2 |
| Sports HQ: Picks Fri 9pm CFP + Yahoo final | Fri | CFP + Yahoo final |
| Sports HQ: Picks Sat 8am injury refresh | Sat | changed picks to the top in red |
| Sports HQ: sign-in check (manual) | on demand | are BTO, CFP, Yahoo, ESPN still signed in? |
| Sports HQ: Tue 7:30am guillotine bid check | Tue 7:11am | The AI strategy Doc's bids when it was updated today after 5am CT (else War Room v2's `bids.json`, else the old War Room) vs pending Sleeper bids → push the exact changes by ~7:30am |
| Sports HQ: Tue 7:30pm guillotine bid safety net | Tue ~7:35pm | Same sources and check against your pending claims and roster; pushes only if a "Bid" player is unclaimed or underbid, a claim is on a Priced out/Skip player, the top free add is missing, or claims exceed FAAB (coin flips never count) |
| Sports HQ: monthly review | 1st, 10am | audit + ranked improvements, pushes the top 3 |
| Sports HQ: nightly improvement pass (`ops/tasks/nightly-improvement-pass.md`) | daily 3:40am | reads health.json, FEEDBACK.md, reviews and the queue; adds and ranks IMPROVEMENTS.md items with evidence, drafts designs for the top 3 (`ops/designs/`); never changes code |
| Sports HQ: add baseball (Feb reminder) | Feb 1 2027, once | baseball plan + reminder |

**Cloud (claude.ai routine, read-only on the repo):** "Guillotine bid strategy (v2)", Tue 6:00am CT, Fable 5.1
(`ops/tasks/guillotine-strategy-v2.md`). It reads War Room v2's `bids.json` plus news and rankings and rewrites the
Google Doc "Guillotine bid strategy (v2)", ending with machine-readable BID/FREE/SKIP lines. It sends no push; the
7:11am bid check turns the Doc into the Tuesday push.

Copies of the review and baseball prompts are in `ops/tasks/`.
Rules for every laptop run: read-only on fantasy/pool sites, never type passwords, close opened tabs,
`git pull --no-rebase` (the repo has merge commits — never rebase). The ntfy topic is never committed: laptop
runs read it from `picks/.ntfy_topic` (gitignored); the cloud uses the `NTFY_TOPIC` secret.

## Adding a league
Add an entry to `LEAGUES` in `shq/config.py` (platform sleeper / espn). ESPN private leagues are picked up by
`py -m shq.save_espn --js` automatically. Baseball needs a small `mlb` addition (plan: `ops/tasks/baseball-kickoff.md`).

## Improving it
- `IDEAS.md`: drop ideas there anytime (phone: edit on github.com). Open decisions live there too.
- `FEEDBACK.md`: what the site's 👍 / 👎 / 💬 Feedback buttons send (a pre-filled GitHub issue, logged by `feedback.yml`).
- `IMPROVEMENTS.md`: the improvement queue. Every item has evidence, expected impact, effort, risk, the health check that
  should move, a design and Michael's decision. Filled nightly from `docs/data/health.json`; how he approves: `ops/approvals.md`.
- Monthly review (1st of each month): audits reliability, freshness and usefulness, writes
  `reviews/YYYY-MM.md`, pushes the top 3 improvements. Nothing changes without Michael's OK.

## Open items
- Yahoo Fantasy API: applied 2026-10-24, pending. When approved, Kosmonauts switches to the API on its own and
  pushes "Yahoo access is live". Yahoo grants read-only access, so Kosmonauts swaps stay "make this swap" pushes.
- Secrets: `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN`, `TOKEN_KEY`, `NTFY_TOPIC`, and
  `CFBD_API_KEY` (still to add, for the picks backup).

## Local
```
pip install -r requirements.txt
python -m unittest discover -s tests      # includes the Yahoo swap dry-run
DRY_RUN=1 python -m shq.run
```
