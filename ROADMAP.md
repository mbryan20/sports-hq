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
| Waiver adds on rest-of-season value, with who to drop + FAAB bid range (NFL) | live 2026-10-28 (`shq/waivers.py`) |
| Trade finder + up to 3 offers per football league (FantasyCalc values) | live 2026-10-28 (`shq/trades.py`); Stempak/Bro-vid19 fill in after the next laptop ESPN sync |
| NBA trade values and ROS waiver ranking | not covered: no free value API (adds stay games-left + ownership) |
| Guillotine survival odds + FAAB bid guidance on the tab | not started (War Room has the model) |
| NBA category matchup view | not started |
| 3-Ball dynasty assets (picks, minors) + Command Center "Moves to make" | not started |
| Kosmonauts FA adds | blocked: Yahoo API approval (or read FAs in the laptop sync) |
| Baseball | Feb 2027 (task `sports-hq-baseball-kickoff`) |
| Older claude.ai routines (auto-swaps, bids, helpers) | Michael to decide: keep, merge or retire (IDEAS.md) |

## Next up, in order
1. Guillotine tab: survival odds and bid guidance (the waiver bid ranges on the tab are generic; the
   War Room has the guillotine model).
2. NBA category matchup.
3. Dynasty assets (3-Ball picks and minors; FantasyCalc also values draft picks).
4. NBA trade ideas from ESPN ranks/projections, if wanted (no free value API).
5. Kosmonauts trades and FA adds once the Yahoo API is approved (needs every team's roster).

## How trades and waiver adds work (`shq/values.py`, `shq/trades.py`, `shq/waivers.py`)
- **Values:** FantasyCalc's public API, matched per league (dynasty or redraft, 1QB or superflex, PPR,
  team count); cached in `.cache` for 6h like the Sleeper players dump. ESPN players map to Sleeper ids
  through FantasyCalc's espnId (Sleeper's DB lacks many), then by name/team.
- **Points per game:** Sleeper weekly projections for the next 4 weeks, scored with the league's
  settings (ESPN scoring is read from the league's scoringItems). Byes aren't counted as games.
- **Offers:** fair within 10% by value (in a two-player side the lesser player counts at 80%), my best
  lineup +0.5/gm or more, theirs +0.5/gm or more. Up to 3, the best straight 1-for-1 always included,
  no player in two offers. After the trade deadline the card says so.
- **Adds:** score = 70% ROS points per game + 30% this week + FantasyCalc value nudge. Drops come from the
  bench, never a starter-level player or (dynasty) anyone worth 750+. A non-starter only replaces his
  own position. K/DEF stream one of each, $0–1. FAAB range scales with the lineup gain.
- **Private ESPN leagues:** `LAPTOP_SNAPSHOT_JS` now saves every team's roster, scoring, trade deadline and
  FAAB. Old snapshots still work; trade ideas appear after the next laptop sync.

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
- **FantasyCalc:** the redraft list only has ~200 players; the dynasty list (same settings) carries a
  `redraftValue` for ~420, so `values.py` always fetches the dynasty list and picks the field.
- **Sleeper projections** for a week skip players on bye, so the Sleeper free-agent pool also takes anyone
  projected in the next 4 weeks.
