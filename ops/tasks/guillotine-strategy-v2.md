---
title: "Guillotine bid strategy (v2)"
kind: claude.ai cloud routine attached to the mbryan20/sports-hq repo (read-only)
routine_id: trig_01SSdrwq7mFaMPruMyzSxLJ9
cron: "CRON_TZ=America/Chicago 0 6 * * 2"   # Tue 6:00am CT only, no Monday-night run yet; reads the Mon 10:40pm/11:20pm CT War Room v2 build
model: Fable 5.1
connectors: Google Drive, Google Docs
status: CREATED 2026-10-31. Writes the Doc "Guillotine bid strategy (v2)" and sends no push; the 7:11am bid check sends the push.
---


Guillotine bid strategy (v2) for Michael (Sleeper "Damon's Guillotine League 2026", league 1385516543386845184; his team is "michaelbryan"). Each week the lowest score is cut and the cut team's players go to waivers. FAAB waivers run Wednesday about 2:15am CT. You run Tuesday 6:00am CT. At ~7:11am a separate laptop task reads YOUR Doc, compares it with Michael's actual pending Sleeper claims, and sends him the only push. Michael reads the Doc at work (Google Docs works there; claude.ai doesn't), so it must stand on its own and read well on a phone.

STRICTLY READ-ONLY on Sleeper and every fantasy site: never bid, claim, add, drop or trade. Don't edit or commit to the repo. Don't touch the older Doc "Guillotine bid strategy" (id 1zAMWjqX2n-y_s_S3RTfi6owMLCEeb2uLqtblW9cC7as). SEND NO PUSH OR NOTIFICATION. The laptop task is the only push.

1. MODEL OUTPUT. The sports-hq repo is checked out. Run `git pull -q` and read docs/war-room-v2/bids.json (the same file is at https://mbryan20.github.io/sports-hq/war-room-v2/bids.json):
   - data_as_of, last_sleeper_move, week (the coming week), cut (team, week, confirmed)
   - cut_risks (every surviving team's FAAB, boldness, cut risk, expected weeks left)
   - freed_players, my_roster (with next-week projections), my_faab, reserve
   - bids: per player sleeper_id, name, pos, team, est_price, your_max, call (Bid / Coin flip / Priced out / Skip / Add free), extra_weeks_alive, likely_rival_bids
   Freshness:
   - If data_as_of doesn't show the most recent week as final (Monday night included), put "Model not updated since <data_as_of>" at the top of the Doc and carry on.
   - If cut.confirmed is false, the cut and freed list are projected. Say so.
   - Sleeper's API is blocked in cloud runs. Don't try to re-pull league data; the JSON is the league data.

2. NEWS AND RANKINGS. For every player in bids with call Bid, Coin flip or Add free, every freed player, and Michael's likely starters, check current injury, role and transaction news with web search: team injury reports, beat reporters, FantasyPros rest-of-season and weekly 0.5 PPR rankings. Note anything the model can't know: a new starter, a return from IR, a trade, a suspension, a depth-chart change. The model only sees past points, byes and the injury report.

3. DECIDE. Start from the model's numbers. Change one only with a stated reason from step 2. For each player worth claiming:
   - bid = est_price + $1, capped at your_max; above your_max only with a stated reason
   - drop = from my_roster: lowest value, mind byes; never drop a player he needs to start this week
   - one line why
   If the bids he could win together exceed my_faab minus reserve, rank them and say which to skip. Flag any rival in cut_risks with a lot of FAAB and high boldness; they set the price.

4. GOOGLE DOC "Guillotine bid strategy (v2)". Find it in Google Drive by that exact title; create it if missing. Replace all its contents each run. Keep it short and phone-readable:
   - Line 1: "Updated <weekday> <date> <time> CT · data as of <data_as_of>"
   - Headline: this week's cut (confirmed or projected), Michael's cut risk and expected weeks left, FAAB left.
   - Bids for Wednesday's waivers: a table with Player | Pos/Team | Bid | Drop | Why. Mark any bid that differs from the model ("model said $X") and why.
   - Free adds now ($0): the top one or two, with the drop.
   - Rivals: the 3 most dangerous bidders (FAAB, boldness).
   - Watch list: news that could change a bid before Wednesday 2:15am.
   - Changes since the last run: compare with the Doc's previous contents.
   - Machine lines (used by the 7:11am laptop check; one per line, exactly this format, last section of the Doc):
       BID;<sleeper_id>;<name>;<amount>;<drop name>
       FREE;<sleeper_id>;<name>;0;<drop name>
       SKIP;<sleeper_id>;<name>;0;-
     (SKIP = players the model or you say not to claim, e.g. priced out.)
   - Footer: "Model: https://mbryan20.github.io/sports-hq/war-room-v2/"

5. Final message: the Doc link, the bid lines, and anything that failed.
