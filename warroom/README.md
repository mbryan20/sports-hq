# Guillotine War Room v2

The War Room (bid adviser for Damon's Guillotine League, Sleeper league 1385516543386845184), now saved in
git and rebuilt by GitHub Actions straight from Sleeper's public API. Before this, a claude.ai cloud task
rebuilt it from code kept in a Drive zip (`guillotine_warroom_code_v1.tgz`), reading Sleeper through
WebFetch summaries that dropped data, and fixes made during a run were lost.

- Page: https://mbryan20.github.io/sports-hq/war-room-v2/ (noindex, back link to Sports HQ)
- JSON: https://mbryan20.github.io/sports-hq/war-room-v2/bids.json (bids table, cut risks, freed players,
  my roster, FAAB, data as of). The AI strategy routine (Tue 6:00am CT, `ops/tasks/guillotine-strategy-v2.md`)
  reads it and writes the Google Doc "Guillotine bid strategy (v2)". The Tuesday 7:11am bid check and 7:30pm safety
  net use that Doc when it was updated today after 5am CT, and fall back to this JSON, then the old War Room.
- Workflow: `.github/workflows/war-room-v2.yml`: daily 6:10am CT, Mon 10:40pm and 11:20pm CT (after
  Monday night), Tue 5:40am CT (fresh for the 6:00am AI strategy task), Tue 6:50am CT (fresh for the
  7:11am bid check), Tue 8:10, 9:10 and 9:50am CT (a fresh page during the morning), Wed 2:40am CT
  (after waivers). It commits only when the page or JSON changed. A failed build sends an ntfy push.
  GitHub runs these crons hours late, so from Sun Nov 15 the laptop starts the workflow at the same times (Windows task
  `\SportsHQ\Kick war room`, `ops/designs/Q-014.md` "The laptop is the clock"); a kick has its own concurrency group, so
  a late cron run can't replace it (Q-037).

## Files
| File | Does |
|---|---|
| `nfl.py` | Downloads nflverse weekly stats, rosters, injuries and schedule, plus dynastyprocess's id map (to `.cache/warroom`, not committed). Scores 0.5 PPR with the league's -1 INT, plus K and DEF. |
| `model.py` | Reads Sleeper directly (league, rosters, users, matchups, every transaction) and builds the page data. |
| `model.js` | The model: projections, 5,000-season elimination sim, rival price model, bid candidates, and `exportBids()`. No DOM. |
| `app.js`, `app_template.html` | The page (tabs, sliders, tables). |
| `export.js` | Runs `model.js` under Node to write `bids.json`, so the page and the JSON always agree. |
| `build.py` | `py -m warroom.build`: builds both files into `docs/war-room-v2/`. Needs `node` (or `NODE=<path>`). |

## Rules the old builder had to re-learn each run (now in `model.py`, tested in `tests/test_warroom.py`)
- **Last finished week:** Sleeper's `last_scored_leg`, or the next week once all its games are final
  (ESPN live scoreboard or nflverse schedule). So Monday night counts as soon as it ends.
- **Week scores:** Sleeper's matchup points. Exception: Sleeper hasn't finished scoring the week and
  nflverse's recompute of the same starters differs by more than 2 points. Sleeper's Tuesday-morning
  points can miss Monday night.
- **The cut:**
  - A cut counts as confirmed only when Sleeper marks the roster `eliminated` for that week; that
    roster is then empty.
  - Before that, the lowest score is a projected cut, labeled as one on the page and in the JSON.
- **Freed players** come from Sleeper's `chopped` transaction, or the team's last matchup. The page
  works when the cut roster is already empty.
- **Freed players stop being bid targets once the waiver run after the cut has processed.** That is any claim
  processed after the chop, or Wednesday ~2:15am CT plus an hour. After it, they are ordinary free agents ("Add
  free" or Skip, no price) until the next cut. `bids.json` says so in `cut.freed_status` (projected / on waivers /
  cleared), `waivers_open` and `next_waiver_run`, so the Tuesday checks can say "no FAAB bids possible yet".
- **Claims** keep Sleeper's own `leg`: claims processed after week N's cut carry leg N.
- **Budget check:** each build compares bids won against Sleeper's `waiver_budget_used` and prints any
  mismatch.

## How the model decides (rebuilt Nov 3 2026 after testing every slider on this league's history)
The test: rebuild each past week as it stood, then compare with what happened. That covered 81 team-weeks, 6 cuts and
64 contested claims; the write-up is in Claude Home/claude-audit/war-room-v2-sliders.md.

- **Projections:** Sleeper's weekly projections for every remaining week (`model.py` `sleeper_projections`).
  - They missed real team scores by about 16 points a week, against about 20 for any mix of season and last-3
    averages. The old "projection basis" slider changed answers a lot without making them more accurate, so it's gone.
  - Byes and players ruled out are 0 in Sleeper's numbers, so a player's upcoming bye (or one already taken)
    is in every gain, win-odds and value figure. The page shows each player's bye week.
  - A player with no Sleeper projection falls back to the old recent-points blend.
- **Score swing:** measured each build (`measure_sd`) as the spread of real team scores around their projected
  best lineup, after removing each week's league-wide shift. It was 22 points in early November.
  - It grows about 1.25 points per week further out (misses measured 23 → 27 from 1 to 4 weeks ahead).
  - Before, a fixed 21 made the rest-of-season odds too sure.
- **Prices:** the model's raw guess of the top rival bid is checked against every past claim, rebuilt as of
  that waiver run (`calibration_cases` in `model.py`, the `--calibrate` mode of `export.js`, `ladder` in `build.py`).
  - The ratios of what claims really went for to that guess become a win chance for any bid. Freed players
    nobody claimed count as $0. Guesses of $10 or more get their own ladder.
  - A single estimate missed by about $15, and stars went for about 1.65× it.
- **Value:** the league is winner-take-all, so a player is worth the win odds he adds, after dropping your least
  useful player (rosters are full).
  - Dollars per point of win odds is set automatically: line up this week's freed players by win odds per $
    (at their 80% price), assume a similar crop at each waiver run you're expected to see, and take the rate
    where your money runs out. The slider overrides it.
- **Bid:** the amount with the best chance × (value − bid), so it's often below the likely price.
  - The aim is to spend well, not win every claim.
  - "Coin flip" means worth bidding but under 50% to win.
  - All bids together stay under FAAB minus the reserve, and no two claims share a drop (a claim moved to its
    next-best drop is re-valued).
  - Moves adding under 0.3 points of win odds are skipped as noise.
- **Reserve:** $5, held back from all bids together; $0 in the last 3 weeks.
- **Simulations:** the page runs 6,000 seasons so the controls respond quickly; `bids.json` uses 20,000.

### bids.json fields the Tuesday checks and the AI write-up use
- **Per-row amounts:**
  - `bid`: the amount to claim; 0 means don't claim.
  - `win_chance`: the chance that bid wins.
  - `drop` / `drop_id`: who to drop for it.
  - `value`: the player's worth to you in $.
- **Prices:** `est_price` (likely price, wins about half of comparable claims) and `price_80`. `your_max` = value, capped at what you can spend.
- **Labels:** `call` (Bid / Coin flip / Priced out / Skip / Add free) and `why`, plus `bye_week`.
- **Budget block:** `budget.spendable`, `budget.recommended_bids_total` and `budget.dollars_per_win_point`.

## Known limits
- The sim keeps current rosters: freed players aren't handed to rivals, so it misses the value of keeping a star
  away from them.
- Mid-week, the coming week's projections ignore games already played. The dashboard's model (`shq/guillotine.py`)
  is the live one.
- The price ladder comes from one season's claims (~180 so far). With only 2 past claims of good players on bye the
  week after their cut, it can't yet say whether the market discounts them; the bye still lowers what they're
  worth to you.
- Sleeper's stored projections for past weeks were used to test them. Not confirmed: whether those are exactly what
  showed before kickoff.
