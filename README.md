# Sports HQ

Michael's all-in-one fantasy sports system: **https://mbryan20.github.io/sports-hq/**
(phone: Safari → Share → Add to Home Screen). Works where claude.ai is blocked.

## What's on the site

| Tab | What | Source |
|---|---|---|
| Today | daily 8am CT check: starters on bye/out/doubtful with the fix, today's locks, guillotine rank, Friday picks deadlines | cloud, daily |
| Kosmonauts | Yahoo, 0.5 PPR, no flex | roster read twice daily by the laptop (Yahoo API approval pending) |
| Domo Arigato | Sleeper "Sunday's Best", dynasty, superflex | Sleeper API (cloud) |
| Guillotine | Sleeper "Damon's Guillotine League" | Sleeper API (cloud) |
| 3-Ball FB / 3-Ball BB | ESPN 3-Ball Dynasty (football, basketball) | ESPN API, public league (cloud) |
| Stempak, Bro-vid19 | ESPN football, private | laptop snapshot with Michael's ESPN sign-in |
| Ball is Life | ESPN "We playin basketball", 8-cat, private | laptop snapshot |
| Weekly | start/sit + top 3 adds per league (basketball: games left, injuries) | Tuesday 7am CT |
| Picks | BTO, CFP, Yahoo pick'em cards (Pool Picks, in `picks/`) | laptop Claude runs Tue–Sat |
| War Room | Guillotine bid/elimination model (copy of the War Room artifact) | laptop sync, daily |

The footer shows the last cloud run and when each laptop job last delivered.

## Two engines

**Cloud (GitHub Actions, no AI, laptop not needed)** — `.github/workflows/run.yml` → `shq/run.py`
- Refreshes every league, builds the Lineup tabs, writes `docs/data/*.json`, commits each run.
- Injury watch: from 2h before each kickoff/tip-off until it locks, every 10 min. Starter OUT/IR/inactive →
  Yahoo: swap via API (when write access exists) and confirm; everyone else: push the exact swap. No healthy
  bench option → push the best free agent. Never adds or drops.
- GitHub drops many scheduled triggers, so a run keeps looping every 10 min while a watch window is open or
  opens within 3h (up to ~5h45m per run). Times come from real kickoffs, so DST doesn't matter.
- Daily digest (`shq/digest.py`): first run after 8am CT fills the Today tab; pushes once only if something
  needs fixing (dead starter or empty slot, NBA starter with no game while the bench can cover, guillotine
  bottom 3, Friday picks deadlines). Late runs (after 1pm) update the tab without pushing.
- Alerts if a laptop job's data goes stale (>30h) and on any failed run.
- `picks-backup.yml` posts a model-only picks card if a laptop picks run misses its slot (needs the
  `CFBD_API_KEY` secret). `test.yml` runs the tests on every push.

**Laptop (Claude scheduled tasks in the desktop app; they read sign-in sites in Michael's Chrome — see `ops/BROWSER.md`)**

| Task | When | Does |
|---|---|---|
| Sports HQ: daily laptop sync | 7:30am, 4:30pm (before the 8am digest) | Kosmonauts roster (Yahoo), private ESPN snapshots, War Room copy |
| Sports HQ: Picks Tue 8pm postmortem | Tue | grade last week's cards and entries |
| Sports HQ: Picks Wed 9pm drafts | Wed | draft cards for BTO, CFP, Yahoo |
| Sports HQ: Picks Thu 8pm BTO final | Thu | BTO final + Yahoo Friday/TB2 |
| Sports HQ: Picks Fri 9pm CFP + Yahoo final | Fri | CFP + Yahoo final |
| Sports HQ: Picks Sat 8am injury refresh | Sat | changed picks to the top in red |
| Sports HQ: sign-in check (manual) | on demand | are BTO, CFP, Yahoo, ESPN still signed in? |
| Sports HQ: Tue 10:30am guillotine bid check | Tue | War Room calls vs pending Sleeper bids → push the exact changes |
| Sports HQ: monthly review | 1st, 10am | audit + ranked improvements, pushes the top 3 |
| Sports HQ: add baseball (Feb reminder) | Feb 1 2027, once | baseball plan + reminder |

Copies of the review and baseball prompts are in `ops/tasks/`.
Rules for every laptop run: read-only on fantasy/pool sites, never type passwords, close opened tabs,
`git pull --no-rebase` (the repo has merge commits — never rebase). The ntfy topic is never committed: laptop
runs read it from `picks/.ntfy_topic` (gitignored); the cloud uses the `NTFY_TOPIC` secret.

## Adding a league
Add an entry to `LEAGUES` in `shq/config.py` (platform sleeper / espn). ESPN private leagues are picked up by
`py -m shq.save_espn --js` automatically. Baseball needs a small `mlb` addition (plan: `ops/tasks/baseball-kickoff.md`).

## Improving it
- `IDEAS.md`: drop ideas there anytime (phone: edit on github.com). Open decisions live there too.
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
