---
taskId: sports-hq-guillotine-safety-net
title: "Sports HQ: Tue 7:30pm guillotine bid safety net"
cron: "30 19 * * 2"   # fires ~7:35pm CT (the app adds a few minutes of jitter)
status: CREATED 2026-10-31; reads the AI strategy Doc first ; uses War Room v2 `bid`/`drop` as given since 2026-11-03 (scheduled task, Auto mode)
---


Tuesday evening guillotine bid SAFETY NET for Michael (Sleeper league "Damon's Guillotine League 2026", league 1385516543386845184, his team michaelbryan). Waivers process Wednesday about 2:15am CT. This morning at ~7:11am a separate task pushed him the bid advice. Your job: check whether his actual Sleeper bids now match that advice, and push ONLY if something is still missing. If everything is set, send NO push.

STRICTLY READ-ONLY: never place, edit or cancel a claim, never add/drop, never type a password or press a sign-in button. Use only Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). Close every tab you open.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

1. THE ADVICE. Source order: the AI strategy Doc first, then War Room v2 data, then the old War Room.
   0. AI STRATEGY DOC (preferred). With the Google Drive connector, find the Google Doc titled exactly "Guillotine bid strategy (v2)" and read it. Use it only if BOTH: its first line ("Updated <weekday> <date> <time> CT · ...") is TODAY at or after 5:00am CT, AND that time is after the last model change (`git log -1 --format=%cI -- warroom/model.py`). If the model changed after the Doc was written, the Doc's amounts are outdated: skip it, use (a)–(b), and say "Model rebuilt <time> — new bids replace this morning's" in any push. Its last section, "Machine lines", holds the final calls: BID;<sleeper_id>;<name>;<amount>;<drop> (amount = the suggested bid, used as is), FREE;<sleeper_id>;<name>;0;<drop> (add now at $0), SKIP;<sleeper_id>;<name>;0;- (shouldn't be claimed; counts like "Priced out"). Still read bids.json (below) for my_faab, budget and my_roster.
   a. Run `git log -1 --format=%cI -- docs/war-room-v2/bids.json`. FRESH if that time is after 6:00pm CT yesterday (Monday).
   b. If FRESH: read C:\Claude\sports-hq\docs\war-room-v2\bids.json: bids[] (sleeper_id, name, pos, team, call = Bid / Coin flip / Priced out / Skip / Add free, bid = the amount to claim (0 = don't claim), win_chance, drop / drop_id = that claim's own drop, value = worth to him in $, est_price = the likely price, price_80, why), budget (spendable, recommended_bids_total), my_faab, my_roster. (Since Nov 3 the model picks `bid` for best chance-to-win × (value − bid), so it is often below est_price. Use it as given; never compute est_price + $1.)
   c. If NOT fresh or unreadable: use the old War Room instead — open https://mbryan20.github.io/sports-hq/war-room/ with get_page_text, rows under "Who to bid on this week" (PLAYER, EST. PRICE, YOUR MAX, CALL), and say "v2 data stale — used old War Room" in any push. Only here: suggested bid = est price + $1, capped at your max.
   d. Changed since this morning? This morning's push used today's Doc if it existed (its BID amounts), else bids.json as of 7:11am (`git log -1 --before="<today> 07:11 -0600" --format=%H -- docs/war-room-v2/bids.json`, then `git show <hash>:docs/war-room-v2/bids.json`). If any player's suggested bid, call or drop differs from what you're using now, note it as "changed since this morning: <player> $<old> → $<new>".
   Claims to suggest: from the Doc's BID lines if you used the Doc; otherwise every "Bid" or "Coin flip" row with bid > 0, at that bid with that drop. Step 3's checks use the Doc's BID, SKIP and FREE lines when the Doc is the source.

2. HIS ACTUAL BIDS AND ROSTER.
   - Pending claims: run `py -m shq.guillotine_bids --js`, open https://sleeper.com/leagues/1385516543386845184/team, wait ~5 seconds, run the printed JavaScript with javascript_tool. Write the returned JSON exactly to C:\Claude\sports-hq\.cache\guillotine_claims.json and run `py -m shq.guillotine_bids .cache\guillotine_claims.json`.
   - If it returns {"error": ...} or a login page: Sleeper is signed out. Skip to step 4 and push: "Couldn't check your guillotine bids (Sleeper signed out in Chrome). This morning's advice: <the Bid and Add free lines>. Waivers run Wed ~2:15am CT."
   - Roster: fetch https://api.sleeper.app/v1/league/1385516543386845184/rosters (PowerShell Invoke-RestMethod is fine here) and take the players list of the roster whose owner is Michael (roster_id 14; confirm via owner_id 605584791680663552).

3. WHAT'S STILL MISSING (only these count):
   - CHECK WAIVERS YOURSELF FIRST (Nov 3 fix: the model wrongly said "cleared" while Sleeper still showed the cut team's players on waivers): fetch https://api.sleeper.app/v1/league/1385516543386845184/transactions/<week> for the current and previous week. If the latest "chopped" transaction has NO "waiver" transaction (status complete or failed) after it, waivers ARE OPEN: ignore waivers_open / freed_status "cleared" and check his bids normally. Only if a waiver transaction has completed after the chop does the rule below apply.
   - WAIVERS CLOSED: if bids.json has waivers_open = false and the check above confirms a waiver run has completed since the chop, there are no bids to place. Only the "Add free" check and the "consider cancelling" check apply. Never ask for a claim.
   - A suggested claim (step 1) with no pending claim, or a claim more than $1 below the suggested bid → "add claim: X $B, <win_chance>% to win (drop <drop>)" or "raise X $A → $B".
   - A pending claim more than $2 ABOVE the suggested bid → "lower X $A → $B? ($B: <win>% to win, +$<avg_payoff> avg; $A: <win>%, +$<avg_payoff>)", using the row's bid_options (nearest option to $A). Going higher is his judgment call, not an error, so word it as a choice. Michael's rule: spend wisely, don't overpay to win every bid.
   - A pending claim whose drop differs from the suggested drop → "X: change drop <old> → <new>" (each claim needs its own drop).
   - A pending claim on a player called "Priced out" or "Skip" → "X: <call> (likely $<est_price>, worth $<value>), consider cancelling".
   - The top "Add free" player (highest extra_weeks_alive) not on his roster → "add now, $0: X (drop <its drop>)".
   - Pending claims that add up to more than budget.spendable (or his FAAB left if there is no budget block) → "your claims total $T but only $S is spendable".
   For rows without a drop field (old War Room), drop = lowest next-week projection in my_roster who isn't needed as a starter.

4. PUSH, only if step 3 found anything (or Sleeper was signed out). Plain text, at most ~6 short lines: first line "<N> guillotine bid item(s) not set — waivers Wed ~2:15am CT", then one line per item, then any "changed since this morning" lines.
   Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Guillotine: bids not set yet'; message='TEXT'; tags=@('warning','moneybag'); priority=4; click='https://mbryan20.github.io/sports-hq/war-room-v2/'} | ConvertTo-Json)
   If nothing is missing: send nothing.

5. Final message: one line, "Pushed: <the text>" or "All set, no push (<N> claims match the advice)", plus which data source you used and its time.