# Improvement queue

Every improvement that has evidence behind it, waiting for Michael's OK. Nothing here is built until its **Decision**
says approved. IDEAS.md stays the place for raw ideas; an idea moves here once someone has evidence for it.

- **Who adds items:** the nightly improvement pass (`ops/tasks/nightly-improvement-pass.md`) from `docs/data/health.json`
  (the nightly model-health job, `shq/health.py`), FEEDBACK.md, IDEAS.md and the monthly review; any session that finds
  something (one item, same format).
- **Who decides:** Michael. Until an approval channel is chosen (`ops/approvals.md`), say "approve Q-003" or "hold Q-005"
  in the Sports HQ intake chat, or edit the Decision line on github.com.
- **Who builds:** a session started for the item once it is approved. When it ships, set Status to `shipped` with the commit;
  the nightly pass sets `verified` once health.json shows the expected change (or `reopened` if it doesn't).

**Status:** `proposed` (evidence, no design yet) → `designed` (the nightly pass drafted a design) → `approved` / `held` /
`rejected` (Michael) → `building` → `shipped` → `verified` / `reopened`. `measuring` = the health job is collecting the
evidence; decide when it reports.

**Fields** (one block per item, keep the labels exactly; the nightly pass and the site parse them):
`### Q-NNN · title`, then Status, Area, Rank, Added, Evidence, Expected impact, Effort (S/M/L), Risk (Low/Med/High),
Measure (the health.json check that should move), Design, Decision.

## Open

### Q-012 · Cut odds are no better than a coin toss
- **Status:** proposed
- **Area:** War Room v2 (`warroom/model.js` `simulate`), dashboard (`shq/guillotine.py`)
- **Rank:** 1
- **Added:** 2026-11-03 by the first model-health run
- **Evidence:** Rebuilding each of the 8 past weeks from Sleeper's projections, the team actually cut ranked 14th, 11th, 9th,
  1st, 1st, 11th, 1st and 10th by predicted risk (average 7th). At the measured 22-pt swing the cut odds score a log-loss of
  2.71 vs 2.66 for treating every team as equally likely (skill −1.7%); wider swings score better (27: +0.7%, 36: +2.3%), and
  the measured swing can't fix the ordering. The dashboard gave week 8's cut team 1.9% before kickoff (10th of 11). 8 cuts is
  a small sample, and the 22-pt swing is measured on the same weeks (in-sample).
- **Expected impact:** cut risk and win odds drive every bid value. If cuts are mostly upsets, both models are too sure who is
  safe, so win-odds gains (and bids) are spread too wide between players. Better-calibrated odds = better $ values.
- **Effort:** S to test, M to change
- **Risk:** Med (moves every bid value)
- **Measure:** `wr.cut_skill`, `gd.v2_skill`, `gd.dash_skill`, `wr.best_sd` in health.json
- **Design:** —
- **Decision:** —

### Q-011 · One guillotine model: the dashboard and War Room v2 still give different numbers
- **Status:** proposed
- **Area:** `shq/guillotine.py` (dashboard, Today tab, cut-risk push) vs `warroom/` (War Room v2, bids.json, Tuesday checks)
- **Rank:** 2
- **Added:** 2026-11-03 (claude-audit item 1, option 4)
- **Evidence:** On Nov 3 the two models disagree for the same week 9: MoneyManChas cut risk 17.0% (dashboard) vs 21.5% (v2),
  robert8063 14.3% vs 12.6%, my projection 119.1 vs 118.8. They use different swings (dashboard per-player position SDs,
  about 27 per team; v2 measured 22), different price models (dashboard: boldest past bid share, $10 reserve per bid; v2:
  calibrated ladder, $5 reserve across all bids) and different values (dashboard: points gained; v2: win odds). The site shows
  the dashboard's bids, the Tuesday push uses v2's. Audit item 1 ("three models give three sets of numbers") recommended folding
  them into one after the redesign.
- **Expected impact:** one answer everywhere (site, push, AI write-up); fixes found in one model reach every screen.
- **Effort:** M (dashboard reads bids.json for odds and bids; keeps its live Sunday locking until Q-002 lands)
- **Risk:** Med (the cut-risk push and Today tab change source)
- **Measure:** `gd.v2_skill` vs `gd.dash_skill` (which predicted cuts better as shown), `gd.dash_price_mae` vs `rec.est_mae`
- **Design:** —
- **Decision:** —

### Q-003 · Price ladder isn't split by position or season stage
- **Status:** measuring
- **Area:** War Room v2 (`warroom/build.py` `ladder`, `model.js` `winChance`)
- **Rank:** 3
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The ladder splits past claims only by estimate size ($10+ vs under). The audit found one estimate missed by
  about $15 and stars went for about 1.65× it; early-season claims (every team rich, weeks 1-3: McCaffrey $150, James Cook
  $156) may not price like late ones. health.json `sections.warroom.details.prices.by` now reports, leave-one-run-out, how
  often bids at the ladder's 50% / 80% price would have won, per position and per half of the season.
- **Expected impact:** truer win chances for RBs vs WRs vs QBs and as budgets shrink, so fewer overpays and fewer lost claims.
- **Effort:** S
- **Risk:** Low-Med (splits get thin: keep the "at least 12 claims or merge" rule)
- **Measure:** `wr.ladder_cov50`, `wr.ladder_cov80` and their `by` splits
- **Design:** —
- **Decision:** —

### Q-010 · Automatic $ per win-point assumes every future crop looks like this week's
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `autoDpp`)
- **Rank:** 4
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** `autoDpp` lines up this week's freed players by win odds per $, assumes a similar crop at every waiver run you're
  expected to see, and takes the rate where FAAB runs out. Crops vary a lot: the top winning bids per run were $150 (wk 1),
  $156 (wk 2), $80 (wk 3) (health.json `recs.details.winners_paid`). The audit called $ per extra week "the biggest lever, and
  a guess"; this replaced the guess with one week's sample.
- **Expected impact:** steadier bid values week to week; less risk of overspending on a weak crop or hoarding before a strong one.
- **Effort:** M (estimate future crops from the remaining rosters: who is likely cut next and what they hold)
- **Risk:** Med (changes every value)
- **Measure:** `rec.would_win`, spending pace vs weeks survived (to add to health once bids have outcomes)
- **Design:** —
- **Decision:** —

### Q-001 · Simulation doesn't hand freed stars to rivals (denial value)
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `simulate`, `gains`)
- **Rank:** 5
- **Added:** 2026-11-03 (Nov 3 slider audit; warroom/README.md "Known limits")
- **Evidence:** The sim keeps current rosters, so a freed star you don't claim never strengthens a rival. In a winner-take-all
  league, a star going to the strongest rival lowers your win odds even if you survive. Not yet measured.
- **Expected impact:** higher values for stars the top rivals need; possibly worth bidding on players who add little to your
  own lineup. Size unknown: first step is to measure how much a rival's win odds move when he wins the top freed player.
- **Effort:** M-L (in each sim, give each unclaimed freed player to his likeliest winner at the estimated price)
- **Risk:** Med (can inflate bids; slower build)
- **Measure:** `rec.would_win`; a one-off what-if on past runs before building
- **Design:** —
- **Decision:** —

### Q-002 · Mid-week, War Room v2 ignores games already played
- **Status:** proposed
- **Area:** War Room v2 (`model.py` / `model.js` `proj`)
- **Rank:** 6
- **Added:** 2026-11-03 (warroom/README.md "Known limits")
- **Evidence:** From Thursday night to Monday, the coming week's projections ignore games already played; only the dashboard
  (`shq/guillotine.py`) locks started games and uses real points. v2's cut risks on Fri-Mon are pre-kickoff numbers.
- **Expected impact:** live cut risk on game days from the same model as the bids; a prerequisite for Q-011 (one model).
- **Effort:** M (lock started players at their real points, zero swing for finished games, like `guillotine.entry`)
- **Risk:** Low
- **Measure:** a Sunday-morning version of `gd.v2_skill` (add when built)
- **Design:** —
- **Decision:** —

### Q-005 · Far-week Sleeper projections aren't backtested yet
- **Status:** measuring
- **Area:** War Room v2 (`model.py` `SD_GROWTH`, `model.js` `swing`)
- **Rank:** 7
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The 1.25-pt-per-week swing growth was measured on the old blend (misses 23 → 27 from 1 to 4 weeks ahead);
  Sleeper's stored past projections are its latest, not what it showed weeks earlier. The page has carried Sleeper's projection
  for every remaining week since Nov 3, so the health job now scores what the page showed 2, 3 and 4 weeks before each week.
  First numbers after week 10 (2 weeks ahead), week 11 (3), week 12 (4).
- **Expected impact:** the right rest-of-season uncertainty, which drives win odds and so every value.
- **Effort:** S (change `SD_GROWTH` once measured)
- **Risk:** Low
- **Measure:** `wr.swing_k2`, `wr.swing_k3`, `wr.swing_k4` vs `wr.swing`
- **Design:** —
- **Decision:** —

### Q-004 · No rival-specific bidding habits
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `threats`)
- **Rank:** 8
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** A rival's predicted bid uses only his boldest past bid share (`MAXPCT`), his need and the player's quality; the
  ladder then corrects league-wide. Some teams win most big claims (CodyRust $150 McCaffrey and $50 Adams in week 1; Aniasin1
  once bid 93% of the FAAB he had left). The ladder holds 165 priced claims, about 10 per team.
- **Expected impact:** better price estimates when a known big spender needs the player.
- **Effort:** M
- **Risk:** Med (about 10 claims per rival: easy to overfit)
- **Measure:** `wr.price_est_mae`, `wr.ladder_cov50`
- **Design:** —
- **Decision:** —

### Q-006 · The page runs 6,000 seasons, bids.json 20,000
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `S.sims`, `export.js`)
- **Rank:** 9
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** The page uses 6,000 so the sliders respond quickly; bids.json, the Tuesday push and the AI write-up use 20,000.
  The audit measured ±0.3-0.7 pts of noise at 2,000. Near a call boundary (0.3-pt noise floor, Bid vs Coin flip at 50%)
  the page can show a different call than the push.
- **Expected impact:** the page always matches the push at default settings.
- **Effort:** S (inline bids.json's default-setting results in the page and recompute only when a slider moves)
- **Risk:** Low
- **Measure:** rows whose call differs page vs bids.json (one-off check)
- **Design:** —
- **Decision:** —

### Q-009 · The 0.3-point win-odds noise floor is a guess
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `MIN_WIN`)
- **Rank:** 10
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Moves adding under 0.3 points of win odds are skipped as noise, but the real noise of `gains()` (10,000 seasons,
  same seed for both sides) has not been measured.
- **Expected impact:** small free adds stop being dropped (or noise stops being recommended).
- **Effort:** S (rerun `gains` with several seeds, set the floor at about 2 standard errors)
- **Risk:** Low
- **Measure:** one-off; then fixed
- **Design:** —
- **Decision:** —

### Q-007 · Free-agent candidates are capped (3 per position, 24 total)
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `candidates`)
- **Rank:** 11
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** Only the top 60 free agents by projected points are tried, then at most 3 per position and 24 overall. The old
  cap of 2 per position hid Bo Nix (audit). A bye-week fill-in or a K/DEF stream can rank 4th at its position and vanish.
- **Expected impact:** no useful free add silently missing.
- **Effort:** S (raise the caps; check build time)
- **Risk:** Low (slower build)
- **Measure:** one-off: free agents beyond the cap that would add more than the noise floor
- **Design:** —
- **Decision:** —

### Q-008 · Rivals' adds ignore their drops
- **Status:** proposed
- **Area:** War Room v2 (`model.js` `rivalGain`, `threats`)
- **Rank:** 12
- **Added:** 2026-11-03 (Nov 3 slider audit)
- **Evidence:** My adds are valued net of my best drop, but a rival's gain (which sets his predicted bid) assumes he adds without
  dropping anyone. Rosters are full, so a rival with no bench to spare gains less than modeled.
- **Expected impact:** small: slightly lower price estimates for players only thin-benched rivals need.
- **Effort:** S
- **Risk:** Low
- **Measure:** `wr.price_est_mae`
- **Design:** —
- **Decision:** —

### Q-013 · Model health scorecard on the site
- **Status:** proposed
- **Area:** site (`docs/lib/`, owned by the dashboard redesign session)
- **Rank:** 13
- **Added:** 2026-11-03
- **Evidence:** health.json is published at `/data/health.json` but nothing shows it. Michael only learned about the Nov 3
  War Room findings because he asked.
- **Expected impact:** a glance at which models are trustworthy this week (ok / watch / drift / weak per model, tap for the checks).
- **Effort:** S
- **Risk:** Low
- **Measure:** —
- **Design:** —
- **Decision:** —

## Done
(Items move here when verified, newest first, with the commit and the health.json numbers that confirmed them.)
