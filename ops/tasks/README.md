# Laptop task prompts

Every Sports HQ laptop task's prompt, kept in the repo so it can be reviewed and recreated.
`monthly-review.md` (1st of each month, 10am CT) and `baseball-kickoff.md` (once, Feb 1 2027) are created
as scheduled tasks. `nightly-improvement-pass.md` (daily 3:40am CT) is proposed, not yet created (Claude Ops creates tasks). If you edit a prompt here, update the task too (Scheduled in the Claude app sidebar).
The `pool-picks-*.md` files are the Pool Picks tasks (Tue postmortem, Wed draft, Thu BTO final, Fri final, Sat refresh,
manual sign-in check); since 2026-11-02 the card runs also read saved picks and the Decisions log, run a second opinion and
send the standalone push (picks/RUNBOOK.md "Every card run").

The daily laptop sync runs `py -m shq.save_espn --js` and executes whatever JavaScript it prints, so changes to
the snapshot (`LAPTOP_SNAPSHOT_JS` in `shq/espn_fantasy.py`) need no prompt change. Since 2026-10-28 NBA snapshots
also carry a `matchup` block (this week's category totals, per-game averages by player id for both rosters and
20 free agents) for the category table; the players themselves come from `roster`, `teams` and `free_agents`
(trimmed 2026-10-30, about 7 KB). `save_espn` rejects a snapshot whose `matchup` block is incomplete.
Since 2026-10-31 every snapshot also carries `results` (every matchup's score) and football snapshots a `box` for this
week and last (my players' points and projections) for the weekend wrap-up; about 6 KB more per football league.
