---
taskId: sports-hq-guillotine-safety-net
title: "Sports HQ: Tue 7:30pm guillotine bid safety net"
cron: "30 19 * * 2"   # fires ~7:35pm CT (the app adds a few minutes of jitter)
status: CREATED 2026-10-31 (scheduled task, Auto mode)
---


Tuesday evening guillotine bid SAFETY NET for Michael (Sleeper league "Damon's Guillotine League 2026", league 1385516543386845184, his team michaelbryan). Waivers process Wednesday about 2:15am CT. This morning at ~7:11am a separate task pushed him the bid advice. Your job: check whether his actual Sleeper bids now match that advice, and push ONLY if something is still missing. If everything is set, send NO push.

STRICTLY READ-ONLY: never place, edit or cancel a claim, never add/drop, never type a password or press a sign-in button. Use only Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). Close every tab you open.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

1. THE ADVICE.
   a. Run `git log -1 --format=%cI -- docs/war-room-v2/bids.json`. FRESH if that time is after 6:00pm CT yesterday (Monday).
   b. If FRESH: read C:\Claude\sports-hq\docs\war-room-v2\bids.json: bids[] (sleeper_id, name, pos, team, call = Bid / Coin flip / Priced out / Skip / Add free, est_price, your_max, extra_weeks_alive), my_faab, my_roster.
   c. If NOT fresh or unreadable: use the old War Room instead — open https://mbryan20.github.io/sports-hq/war-room/ with get_page_text, rows under "Who to bid on this week" (PLAYER, EST. PRICE, YOUR MAX, CALL), and say "v2 data stale — used old War Room" in any push.
   d. Changed since this morning? Get the version that existed at 7:11am today: `git log -1 --before="<today> 07:11 -0600" --format=%H -- docs/war-room-v2/bids.json`, then `git show <hash>:docs/war-room-v2/bids.json`. If any player's call or your_max differs from now, note it as "changed since this morning: <player> <old> → <new>".
   Suggested bid for a "Bid" player = est_price + $1 if that is at or below your_max, else your_max.

2. HIS ACTUAL BIDS AND ROSTER.
   - Pending claims: run `py -m shq.guillotine_bids --js`, open https://sleeper.com/leagues/1385516543386845184/team, wait ~5 seconds, run the printed JavaScript with javascript_tool. Write the returned JSON exactly to C:\Claude\sports-hq\.cache\guillotine_claims.json and run `py -m shq.guillotine_bids .cache\guillotine_claims.json`.
   - If it returns {"error": ...} or a login page: Sleeper is signed out. Skip to step 4 and push: "Couldn't check your guillotine bids (Sleeper signed out in Chrome). This morning's advice: <the Bid and Add free lines>. Waivers run Wed ~2:15am CT."
   - Roster: fetch https://api.sleeper.app/v1/league/1385516543386845184/rosters (PowerShell Invoke-RestMethod is fine here) and take the players list of the roster whose owner is Michael (roster_id 14; confirm via owner_id 605584791680663552).

3. WHAT'S STILL MISSING (only these count; "Coin flip" players never count):
   - A "Bid" player with no pending claim, or a claim more than $1 below the suggested bid → "add claim: X $B (drop <weakest>)" or "raise X $A → $B".
   - A pending claim on a player called "Priced out" or "Skip" → "X: priced out (est $P), consider cancelling".
   - The top "Add free" player (highest extra_weeks_alive) not on his roster → "add now, $0: X (drop <weakest>)".
   - Pending claims that add up to more than his FAAB left → "your claims total $T but you have $F".
   Weakest player = lowest next-week projection in my_roster who isn't needed as a starter.

4. PUSH, only if step 3 found anything (or Sleeper was signed out). Plain text, at most ~6 short lines: first line "<N> guillotine bid item(s) not set — waivers Wed ~2:15am CT", then one line per item, then any "changed since this morning" lines.
   Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Guillotine: bids not set yet'; message='TEXT'; tags=@('warning','moneybag'); priority=4; click='https://mbryan20.github.io/sports-hq/war-room-v2/'} | ConvertTo-Json)
   If nothing is missing: send nothing.

5. Final message: one line, "Pushed: <the text>" or "All set, no push (<N> claims match the advice)", plus which data source you used and its time.