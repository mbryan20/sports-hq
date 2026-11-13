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
  - $0 counts with its own payoff (Q-038): when $1 wins no more past claims than $0, the call is a $0 claim
    (`call` Bid or Coin flip with `bid` 0). Before Nov 10 the $0 option was scored as worth nothing, so $1 always won.
  - A player who is Out or on IR and projected 0 this week (not on a bye) is Skip, never Add free (Q-040).
  - A K or DEF add never drops an RB, WR or TE worth 8+ points a week (season average or the next weeks'
    projection), and a paid K or DEF claim is skipped when a free agent at that position helps as much (Q-041).
- **Reserve:** from `warroom/rules.json`, held back from all bids together while Michael is likely to survive. Rule 13
  (Nov 12, his words: "as long as we have a decent chance at surviving having a little bit of money is better than
  having none"): when his chance of being cut this week reaches `release_reserve_at_cut_risk` (25%, about twice an
  average team's with 9 left), a claim that lowers that chance by `release_min_survival_gain` (2 points) or more may
  spend it. bids.json: `budget.reserve_released`, `budget.my_cut_risk`, per row `cut_risk_drop` and `uses_reserve`,
  `rules.reserve_rule`. The 25% isn't fitted: only 2 weeks of past cut forecasts exist, and his own risk never passed
  8% in them.

## Nov 12 revamp (Michael approved plan parts 1-3; `tests/test_warroom_revamp.py`)
Replayed on every past waiver run (weeks 2-9, Michael's real roster and FAAB each time, prices fitted only on earlier
weeks, scored against the bids that really happened): +12.1 points of title odds for $26 spent, against +7.4 for the
old prices with the same rules and +13.6 for $182 for what Michael actually bid.
- **Rival-by-rival prices** (`rivalWin`, fitted in `build.py` `rival_model` every build from every past waiver run):
  each surviving rival's chance to claim a player (by the player's rank among that run's targets and the lineup points
  he'd add for that rival) and his bid as a share of HIS OWN money, with his habits and biggest share so far. A bid wins
  only if it beats every rival; ties lose (Michael is last in waiver order), so any rival claim beats a $0 claim and a
  rival with $0 left can only beat $0. The old one-ladder estimate was right on average but its 10-30% chances won 1 in
  79 in weeks 6-9 (Nacua, Javonte, Taylor, Pickens and Warren went 0 for 5); this model's 20% bids won 17-26%. It runs a
  little cautious in the middle (says 60%, won ~70%). The $ per point of win odds is now set at the 50% price (at the
  80% price the honest prices inflated it and the replay spent $205).
- **Calls by honest chance:** Bid 50%+, Coin flip 25-50%, Long shot 10-25% (worth a try, expect to lose), Skip under
  10% at every bid worth making.
- **Backups** (`addBackups`): with a full roster a claim that shares a drop with one that already won fails, so a
  lower claim on the same drop only runs if every claim above it on that drop lost (no team in this league ever won two
  claims with one drop; 84 such claims failed). Backups go strictly below the claims they back up and never raise the
  most you can spend: `worst_case_spend` = the top bid of each drop's chain.
- **His rules** (`warroom/rules.json`): `reserve`; `league_winners` (only these can go above `big_bid_share` of his FAAB,
  at least `big_bid_min`); K, DEF and any add worth under `marginal_pts_per_week` lineup points a week go in at $0;
  never drop a player in this week's lineup unless the add starts in his place (Try a move falls back to the cheapest
  drop when nothing else is left, and its verdict says if that's bad).
- **One answer:** the page's "Your moves" box shows `bids.json`'s `claim_list` (the 20,000-season build the guide and
  the 7:11am push read) while the controls are at their defaults, and says when it's showing the page's own numbers.
  Every claim and free add has a one-line `why_line` with anything to check first (an injury tag: news from the last
  48 hours; projected 0 with no tag; a bye).
- **Simulations:** the page runs 6,000 seasons so the controls respond quickly; `bids.json` uses 20,000.

### bids.json fields the Tuesday checks and the AI write-up use
- **Per-row amounts:**
  - `bid`: the amount to claim. With `call` Bid, Coin flip, Long shot or Backup, 0 means a $0 claim (since Nov 10);
    with any other call, don't claim.
  - `win_chance`: the chance that bid wins.
  - `drop` / `drop_id`: who to drop for it.
  - `value`: the player's worth to you in $.
- **Prices:** `est_price` (likely price, wins about half of comparable claims) and `price_80`. `your_max` = value, capped at what you can spend.
- **Rivals:** `likely_rival_bids` (top 3) are on the same scale as `win_chance` since Nov 10 (Q-039): each rival's
  guessed bid × (est_price / raw estimate), because past claims went for less than the raw guesses (often $0:
  nobody claimed him). `raw` keeps the unscaled guess.
- **Labels:** `call` (Bid / Coin flip / Long shot / Backup / Priced out / Skip / Add free), `why`, `why_line`, plus `bye_week`.
- **Backups:** `chain_drop`, `chain_order`, `fires_if` on each row.
- **The list to enter, in order:** `claim_list` (order, name, bid, drop, win_chance, kind claim/backup, fires_if, why);
  `worst_case_spend`; `can_outbid` per row (rivals with the money to beat that bid and their chance to claim);
  `rules` (reserve, league_winners, big_bid_cap, marginal, starters).
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
