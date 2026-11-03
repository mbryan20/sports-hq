---
taskId: sports-hq-guillotine-bid-check
title: "Sports HQ: Tue 7:30am guillotine bid check"
cron: "10 7 * * 2"   # fires ~7:11am CT (the app adds about a minute of jitter)
status: CREATED 2026-10-28; moved to Tue 7:11am CT and War Room v2 first on 2026-10-31; reads the AI strategy Doc first since 2026-10-31 (scheduled task, Auto mode)
---


Tuesday guillotine bid check for Michael (Sleeper league "Damon's Guillotine League 2026"). Waivers process Wednesday about 2:15am CT. Goal: by 7:30am Tuesday (when he gets to work), push him the exact bid changes to make in the Sleeper app (he is at work; claude.ai is blocked there, so the push must stand on its own).

STRICTLY READ-ONLY: never place, edit or cancel a claim, never add/drop, never type a password or press a sign-in button. Use only Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). Close every tab you open.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

1. WAR ROOM CALLS. Source order: (0) the AI strategy Doc, (1) War Room v2 data, (2) the old War Room.
   0. AI STRATEGY DOC (preferred). With the Google Drive connector, find the Google Doc titled exactly "Guillotine bid strategy (v2)" and read it (Google Docs/Drive read tool). Use it if its first line ("Updated <weekday> <date> <time> CT · ...") is TODAY at or after 5:00am CT. Its last section, "Machine lines", holds the final calls, one per line: BID;<sleeper_id>;<name>;<amount>;<drop>, FREE;<sleeper_id>;<name>;0;<drop>, SKIP;<sleeper_id>;<name>;0;-. A BID amount is the final suggested bid: use it as is (don't add $1); FREE = add now at $0; SKIP = shouldn't be claimed. Also read bids.json (below) for my_faab and context. Line 1 of the push will start "AI strategy Doc (updated <time>)". If the Doc is missing, older than today 5:00am CT, or has no Machine lines, go to (a).
   a. Freshness: run `git log -1 --format=%cI -- docs/war-room-v2/bids.json`. It is FRESH if that time is after 6:00pm CT this Monday (the day before this run).
   b. If FRESH: read C:\Claude\sports-hq\docs\war-room-v2\bids.json (same file as https://mbryan20.github.io/sports-hq/war-room-v2/bids.json). Use: bids[] (name, pos, team, call = Bid / Coin flip / Priced out / Skip / Add free, est_price, your_max, extra_weeks_alive, likely_rival_bids), my_faab, cut (team, week, confirmed), data_as_of, and my_roster (the weakest player to drop = lowest next-week projection who isn't a starter you'd need). Line 1 of the push will start "War Room v2 (data: <data_as_of>)".
   c. If NOT fresh, or the file is missing or unreadable: FALL BACK to the old War Room. Open https://mbryan20.github.io/sports-hq/war-room/ and read the page text (get_page_text). Under "Who to bid on this week" each row has PLAYER, EST. PRICE, YOUR MAX and CALL. Note the header's "FAAB LEFT". Line 1 of the push will start "v2 data stale — used old War Room".
   d. Either way, if the data isn't from after this week's Monday night games, add "War Room not updated this week" to the push and use it anyway.

2. YOUR PENDING CLAIMS. Run `py -m shq.guillotine_bids --js`, open https://sleeper.com/leagues/1385516543386845184/team, wait ~5 seconds, and run the printed JavaScript with javascript_tool. If it returns {"error": ...} or the page redirected to a login screen, Sleeper is signed out in Chrome: skip to step 3 using only the War Room calls, and add "Sleeper signed out in Chrome — couldn't see your pending bids" to the push. Otherwise write the returned JSON text exactly to C:\Claude\sports-hq\.cache\guillotine_claims.json and run `py -m shq.guillotine_bids .cache\guillotine_claims.json` to get the claims with player names.

3. COMPARE and write the push (plain text, at most ~8 short lines, no tables):
   - CHECK WAIVERS YOURSELF FIRST (Nov 3 fix: the model wrongly said "cleared" while Sleeper still showed the cut team's players on waivers): fetch https://api.sleeper.app/v1/league/1385516543386845184/transactions/<week> for the current and previous week. If the latest "chopped" transaction has NO "waiver" transaction (status complete or failed) after it, waivers ARE OPEN: ignore waivers_open / freed_status "cleared", treat the cut team's players as on waivers until next_waiver_run, and give the BID lines normally. Only if a waiver transaction has completed after the chop does the rule below apply.
   - WAIVERS CLOSED: if bids.json has waivers_open = false (cut.freed_status "cleared") and the check above confirms a waiver run has completed since the chop, no FAAB bids are possible. Suggest no claims and no bid amounts. Say "No waiver bids possible until <next_waiver_run in CT>" and give only "Add free" lines (and "consider cancelling" for any pending claim). When cut.freed_status is "projected", label those bids "planning, cut not confirmed yet".
   - If you used the AI strategy Doc: each BID line is the suggested bid and each SKIP line counts like "Priced out"; ignore the model's Coin flips. Otherwise, for each "Bid" or "Coin flip" player: suggested bid = est. price + $1 if that is at or below your max, else your max. If he has a pending claim on that player, say "raise/lower X $A → $B" (or "OK at $A" if within $1); if not, say "add claim: X $B (drop <his weakest player>)".
   - "Add free" players: "add now, $0: X (drop <weakest>)" — only the top one or two.
   - For pending claims on players called "Priced out" or "Skip": say so ("X: priced out (est $P), consider cancelling").
   - If the suggested bids for players he'd both win add up to more than his FAAB left, say which to prioritise (higher extra weeks alive first).
   - End with: "Waivers run Wed ~2:15am CT."
   Send it (PowerShell; replace TEXT; click goes to the page you used):
   Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Guillotine bids: changes for tonight'; message='TEXT'; tags=@('moneybag'); priority=4; click='https://mbryan20.github.io/sports-hq/war-room-v2/'} | ConvertTo-Json)
   (If you fell back to the old War Room, use click='https://mbryan20.github.io/sports-hq/war-room/'.)

4. Report the push text as your final message, plus one line saying which source you used (v2 or fallback) and why.