---
title: "Guillotine bid strategy (v2)"
kind: claude.ai cloud scheduled task, attached to the mbryan20/sports-hq GitHub repo
schedule: "Mon 11:45pm CT and Tue 7:00am CT"   # War Room v2 rebuilds Mon 10:40pm and 11:20pm CT, Tue 6:10am CT
model: Opus 5.5 (trial Fable 5.1 if the task picker offers it)
status: DRAFT 2026-10-31, not created. Claude Ops creates it after Michael connects GitHub to claude.ai.
---

Guillotine bid strategy for Michael (Sleeper "Damon's Guillotine League 2026", league 1385516543386845184; his team is
"michaelbryan"). Each week the lowest score is cut, and the cut team's players go to waivers. FAAB waivers run
Wednesday about 2:15am CT. Michael reads the result at work, where claude.ai is blocked: the Google Doc and the
push must stand on their own.

STRICTLY READ-ONLY on Sleeper and every fantasy site: never bid, claim, add, drop or trade. Don't edit the repo
(no commits), and don't touch the older Doc "Guillotine bid strategy" (id 1zAMWjqX2n-y_s_S3RTfi6owMLCEeb2uLqtblW9cC7as).
It stays during the side-by-side.

1. MODEL OUTPUT. Pull the repo and read `docs/war-room-v2/bids.json` (the same file is at
   https://mbryan20.github.io/sports-hq/war-room-v2/bids.json). It holds:
   - `data_as_of` and `last_sleeper_move`
   - `week` (the coming week), and `cut` (team, week, confirmed true/false)
   - `cut_risks` (every surviving team's FAAB, boldest past bid as % of budget, cut risk, expected weeks left)
   - `freed_players`, `my_roster` (with next-week projections) and `my_faab`
   - `bids`: per player `est_price`, `your_max`, `call` (Bid / Coin flip / Priced out / Skip / Add free),
     `extra_weeks_alive` and `likely_rival_bids`

   Freshness check:
   - If `data_as_of` doesn't say the most recent week is final, say "model not updated since <data_as_of>"
     at the top of the Doc and in the push, then carry on.
   - If `cut.confirmed` is false, the cut and the freed list are projected. Say so.
   - Sleeper's API is blocked in cloud runs, so don't try to re-pull league data. The JSON is the league
     data.

2. NEWS AND RANKINGS. For every player in `bids` with call Bid or Coin flip, every freed player, and Michael's
   starters, check current injury and role news. Use web search: team injury reports, beat reporters, and
   FantasyPros rest-of-season and weekly rankings (0.5 PPR). Note anything the model can't know: a new
   starter, a return from IR, a trade, a suspension, or a role change. The model only sees past points,
   byes and the injury report.

3. DECIDE. Start from the model's numbers and adjust only with a stated reason from step 2. For each player
   worth claiming, give:
   - the bid: normally `est_price` + $1, capped at `your_max`; above `your_max` only with a reason
   - whom to drop, from `my_roster` (lowest value, mind byes)
   - one line why

   Two more checks:
   - If the bids he could win together exceed `my_faab` minus a $10 reserve, rank them.
   - Flag any rival in `cut_risks` with a lot of FAAB and high boldness; they set the price.

4. GOOGLE DOC "Guillotine bid strategy (v2)". Create it on the first run; afterwards find it by that exact title
   and replace its contents. Keep it short and readable on a phone:
   - **Headline:** this week's cut (confirmed or projected), Michael's cut risk and expected weeks left, FAAB.
   - **Bids for Wednesday's waivers:** a table with player, pos/team, bid, drop, why. Mark any bid that
     differs from the model and say why.
   - **Rivals:** the 3 most dangerous bidders (FAAB, boldness).
   - **Watch list:** news that could change a bid before Wednesday 2:15am.
   - **Changes since the last run:** compare with the Doc's previous contents.
   - Footer: "Model: https://mbryan20.github.io/sports-hq/war-room-v2/ · data as of <data_as_of>".

5. ONE PUSH. Use the Claude app notification (and ntfy if the environment provides an NTFY_TOPIC variable;
   never write the topic anywhere). Title: "Guillotine bids (v2)". Body: at most 6 short lines with each
   bid as "Bid $N on X (drop Y)", and the Doc link last.

6. Final message: the push text and the Doc link.
