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

## Known limits
- Projections blend the season average with the last 3 games. They are not expert rankings; the AI
  write-up adds news and rankings on top.
- The sim keeps current rosters: freed players aren't reassigned.
- In-progress weeks aren't modeled live: mid-week, the coming week's projections ignore games already
  played. The dashboard's model (`shq/guillotine.py`) is the live one.
