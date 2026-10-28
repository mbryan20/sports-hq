# Laptop task prompts

Every Sports HQ laptop task's prompt, kept in the repo so it can be reviewed and recreated.
`monthly-review.md` (1st of each month, 10am CT) and `baseball-kickoff.md` (once, Feb 1 2027) are created
as scheduled tasks. If you edit a prompt here, update the task too (Scheduled in the Claude app sidebar).

The daily laptop sync runs `py -m shq.save_espn --js` and executes whatever JavaScript it prints, so changes to
the snapshot (`LAPTOP_SNAPSHOT_JS` in `shq/espn_fantasy.py`) need no prompt change. Since 2026-10-28 NBA snapshots
also carry a `matchup` block (this week's category totals, both rosters' per-game averages, 40 free agents) for
the category table; `save_espn` rejects a snapshot whose `matchup` block is incomplete.
