---
taskId: sports-hq-guillotine-bid-check
title: "Sports HQ: Tue 10:30am guillotine bid check"
cron: "30 10 * * 2"
status: CREATED 2026-10-28 (scheduled task, Auto mode)
---


Tuesday guillotine bid check for Michael (Sleeper league "Damon's Guillotine League 2026"). Waivers process Wednesday about 2:15am CT. Goal: by late morning Tuesday, push him the exact bid changes to make in the Sleeper app (he is at work; claude.ai is blocked there, so the push must stand on its own).

STRICTLY READ-ONLY: never place, edit or cancel a claim, never add/drop, never type a password or press a sign-in button. Use only the built-in browser tools (mcp__Claude_Browser__*). Close every tab you open.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

1. WAR ROOM CALLS. Open https://mbryan20.github.io/sports-hq/war-room/ and read the page text (get_page_text). Under "Who to bid on this week" each row has PLAYER, EST. PRICE, YOUR MAX and CALL (Bid / Coin flip / Priced out / Skip / Add free). Note the header's "FAAB LEFT" and the date on the second line. If that date is not from this week (Monday night final or later), say "War Room not updated this week" in the push and use it anyway with that caveat.

2. YOUR PENDING CLAIMS. Run `py -m shq.guillotine_bids --js`, open https://sleeper.com/leagues/1385516543386845184/team, wait ~5 seconds, and run the printed JavaScript with javascript_tool. If it returns {"error": ...} or the page redirected to a login screen, Sleeper is signed out in the Claude app browser: skip to step 3 using only the War Room calls, and add "Sleeper signed out in the Claude app browser — couldn't see your pending bids" to the push. Otherwise write the returned JSON text exactly to C:\Claude\sports-hq\.cache\guillotine_claims.json and run `py -m shq.guillotine_bids .cache\guillotine_claims.json` to get the claims with player names.

3. COMPARE and write the push (plain text, at most ~8 short lines, no tables):
   - For each War Room "Bid" or "Coin flip" player: suggested bid = EST. PRICE + $1 if that is at or below YOUR MAX, else YOUR MAX. If he has a pending claim on that player, say "raise/lower X $A → $B" (or "OK at $A" if within $1); if not, say "add claim: X $B (drop <his weakest player, from the War Room if shown>)".
   - For pending claims on players the War Room calls "Priced out" or "Skip": say so ("X: priced out (est $P), consider cancelling").
   - If the suggested bids for players he'd both win add up to more than his FAAB left, say which to prioritise (higher +WEEKS ALIVE first).
   - End with: "Waivers run Wed ~2:15am CT."
   Send it (PowerShell; replace TEXT):
   Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Guillotine bids: changes for tonight'; message='TEXT'; tags=@('moneybag'); priority=4; click='https://mbryan20.github.io/sports-hq/war-room/'} | ConvertTo-Json)

4. Report the push text as your final message.