---
title: "Guillotine bid strategy (v2)"
kind: claude.ai cloud routine attached to the mbryan20/sports-hq repo (read-only)
routine_id: trig_01SSdrwq7mFaMPruMyzSxLJ9
cron: "CRON_TZ=America/Chicago 0 6 * * 2"   # Tue 6:00am CT only, no Monday-night run yet; reads the Tue 5:40am CT War Room v2 build
model: Fable 5.2
connectors: Google Drive, Google Docs
status: CREATED 2026-10-31; prompt updated 2026-11-03 (model bid/drop as given, Win % column, bid options), 2026-11-10 (stale-model rule, Doc folder), 2026-11-12 (step 1 reads ops/tasks/guillotine-tuesday-rules.md). Synced to the live routine 2026-11-12. Writes the Doc "Guillotine bid strategy (v2)" and sends no push; the 7:11am bid check sends the push.
---


Guillotine bid strategy (v2) for Michael (Sleeper "Damon's Guillotine League 2026", league 1385516543386845184; his team is "michaelbryan"). Each week the lowest score is cut and the cut team's players go to waivers. FAAB waivers run Wednesday about 2:15am CT. You run Tuesday 6:00am CT. At ~7:11am a separate laptop task reads YOUR Doc, compares it with Michael's actual pending Sleeper claims, and sends him the only push. Michael reads the Doc at work (Google Docs works there; claude.ai doesn't), so it must stand on its own and read well on a phone.

STRICTLY READ-ONLY on Sleeper and every fantasy site: never bid, claim, add, drop or trade. Don't edit or commit to the repo. Don't touch the older Doc "Guillotine bid strategy" (id 1zAMWjqX2n-y_s_S3RTfi6owMLCEeb2uLqtblW9cC7as). SEND NO PUSH OR NOTIFICATION. The laptop task is the only push.

1. MODEL OUTPUT. The sports-hq repo is checked out. Run `git pull -q`, then read ops/tasks/guillotine-tuesday-rules.md and follow it (where it differs from steps 3 and 4 below, it wins: claim_list order, backups, Long shot calls, his caps, ";backup" machine lines). Then read docs/war-room-v2/bids.json (the same file is at https://mbryan20.github.io/sports-hq/war-room-v2/bids.json) and the "How the model decides" and "bids.json fields" sections of warroom/README.md:
   - data_as_of, last_sleeper_move, week (the coming week), cut (team, week, confirmed)
   - cut_risks (every surviving team's FAAB, boldness, cut risk, expected weeks left)
   - freed_players, my_roster (with next-week projections), my_faab, reserve, budget (spendable, recommended_bids_total, dollars_per_win_point)
   - bids: per player sleeper_id, name, pos, team, call (Bid = worth it with at least 50% to win / Coin flip = worth it but under 50% / Priced out = likely price above his value / Skip / Add free), bid (the amount to claim; 0 = don't claim), win_chance (for that bid), bid_options (the bids worth comparing, each with win_chance, avg_payoff = chance x (value - bid), recommended, over_spendable), drop / drop_id (each claim's own drop), value (worth to him in $), est_price (the likely price: about half of comparable past claims won at or below it), price_80, your_max (= value, capped at spendable), why, bye_week, extra_weeks_alive
   Freshness:
   - If data_as_of doesn't show the most recent week as final (Monday night included), put "Model not updated since <data_as_of>" at the top of the Doc and carry on.
   - If cut.confirmed is false, the cut and freed list are projected. Say so.
   - Sleeper's API is blocked in cloud runs. Don't try to re-pull league data; the JSON is the league data.

2. NEWS AND RANKINGS. For every player in bids with call Bid, Coin flip or Add free, every freed player, and Michael's likely starters, check current injury, role and transaction news with web search: team injury reports, beat reporters, FantasyPros rest-of-season and weekly 0.5 PPR rankings. Note anything the model can't know: a new starter, a return from IR, a trade, a suspension, a depth-chart change. The model uses Sleeper's projections, past points, byes and the injury report.

3. DECIDE. Start from the model's numbers and keep them unless step 2 gives a stated reason. Michael's rule: "The goal is not to win every bid, its to spend money wisely... We should bid what we think is right and see what happens." So:
   - Claims = every Bid or Coin flip row with bid > 0, at the model's `bid` with the model's `drop`. The bid is chosen for best chance-to-win x (value - bid), so it is often below est_price. Do NOT use est_price + $1 and don't raise a bid just to win it.
   - Change a bid, value or drop only for news the model can't know (say why, and "model said $X"); never bid above value. Never drop a player he needs to start this week.
   - The model's bids already fit budget.spendable (FAAB minus reserve) with distinct drops. If your changes push the total over spendable, cut the lowest-value claim.
   - One line why per claim, with its win chance.
   Flag any rival in cut_risks with a lot of FAAB and high boldness; they set the price.

4. GOOGLE DOC "Guillotine bid strategy (v2)". Find it in Google Drive by that exact title (it lives in My Drive › Claude Home › For Michael); create it there if missing, never at the top of My Drive. Replace all its contents each run. Keep it short and phone-readable:
   - Line 1: "Updated <weekday> <date> <time> CT · data as of <data_as_of>"
   - Headline: this week's cut (confirmed or projected), Michael's cut risk and expected weeks left, FAAB left and spendable.
   - Bids for Wednesday's waivers: a table with Player | Pos/Team | Bid | Win % | Drop | Why. Mark any bid that differs from the model ("model said $X") and why. Total at the bottom vs spendable.
   - Bid options (Michael asked to see the trade-off, not just one number): under the table, one short line per claim from bid_options, e.g. "Nacua: $6 25% +$11 · $14 42% +$15 (pick) · $28 50% +$12". Skip options with over_spendable true or avg_payoff <= 0. Going higher is his judgment call, not an error.
   - Free adds now ($0): the top one or two, with the drop.
   - Rivals: the 3 most dangerous bidders (FAAB, boldness).
   - Watch list: news that could change a bid before Wednesday 2:15am.
   - Changes since the last run: compare with the Doc's previous contents.
   - Machine lines (used by the 7:11am laptop check; one per line, exactly this format, last section of the Doc):
       BID;<sleeper_id>;<name>;<amount>;<drop name>
       FREE;<sleeper_id>;<name>;0;<drop name>
       SKIP;<sleeper_id>;<name>;0;-
     (BID = every claim from step 3, Coin flips included. SKIP = players not to claim, e.g. Priced out or Skip.)
   - Footer: "Model: https://mbryan20.github.io/sports-hq/war-room-v2/"

5. Final message: the Doc link, the bid lines, and anything that failed.

ADDED Nov 10: If bids.json data_as_of does not name last week's cut as confirmed, the model is stale: write only the header, the stale warning, injury notes and the watch list, put NO BID lines in Machine lines, and say the 7:11am task will use the rebuilt model. Never price a player from name value; use this season's average and the model's est_price. Only list players who are in bids.json or freed_players.
