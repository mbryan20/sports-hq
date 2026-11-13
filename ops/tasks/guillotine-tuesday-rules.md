# Guillotine Tuesday rules (War Room revamp, Nov 12 2026)

Read by the three Tuesday bid jobs: the 6:00am "Guillotine bid strategy (v2)" routine, the 7:11am bid check and the
7:30pm safety net. Where these rules and a job's own prompt differ, these rules win. Michael approved this plan on
Nov 12 (warroom/README.md "Nov 12 revamp", IMPROVEMENTS Q-062).

1. **The list is `claim_list` in bids.json, in its order.** Each item: order, name, sleeper_id, bid, drop, drop_id,
   win_chance, kind (`claim` or `backup`), fires_if, why. Use the bid and drop as given (never est_price + $1). Add or
   remove a claim only for news (rule 5), and say "model said $X" when you do.
2. **Calls.** Bid = 50%+ to win. Coin flip = 25-50%. Long shot = 10-25%: worth a try, expect to lose; say "long shot".
   Backup = runs only if the claim(s) in `fires_if` lost. All four are claims, and bid 0 means a $0 claim. Priced out
   and Skip are not claims.
3. **Backups share a drop on purpose.** With a full roster, once one claim on a drop wins, Sleeper fails the rest on
   that drop, so he never pays twice. Never flag claims that share a drop when one of them is a backup, and never tell
   him to change a backup's drop. Compare `worst_case_spend` (the top bid of each drop's chain), not the sum of all
   bids, with budget.spendable. A backup must stay strictly below the claims it backs up: if his backup is at or above
   one of them, say so.
4. **Order in Sleeper.** Enter claims in `claim_list` order on the classic site. Sleeper runs the highest bids first;
   equal bids (usually the $0 claims) run in his drag order, so drag them into list order.
5. **News.** Injury and role status come only from news less than 48 hours old, never from Sleeper's tag alone. Check
   every item whose `why` says "check news". If a player is ruled out for the coming week and isn't worth holding, drop
   his claim and say why.
6. **His rules (bids.json `rules`).**
   - The reserve depends on survival (his rule, Nov 12): keep `reserve` ($5) while his cut risk this week is under
     `release_reserve_at_cut_risk` (25%). At 25% or more, only a claim that lowers that risk (bids `uses_reserve`,
     `cut_risk_drop`) may spend it; budget `reserve_released` says which applies. Never suggest spending it on any
     other claim, and never leave him at $0 while he is under 25%.
   - Anyone not on `league_winners` is capped at `big_bid_cap`. Never suggest going above it; if a player looks worth
     more, say so and ask Michael whether he is a league-winner.
   - K, DEF and marginal adds stay at $0. Don't suggest $1, even if it raises the chance.
   - Never drop a player in this week's lineup for an add who wouldn't start in his place.
7. **One line why per claim:** use its `why` (shorten it if needed). "can be outbid by" names the rivals with enough
   money to beat that bid.
8. **Privacy.** His pending claims are private. Never write them to the repo, the public site or any public file; the
   Doc and the phone push are fine.
9. **Doc machine lines.** BID lines follow `claim_list` order. A backup's line ends with `;backup`, for example
   `BID;<sleeper_id>;<name>;<amount>;<drop>;backup`. FREE and SKIP lines are unchanged.
