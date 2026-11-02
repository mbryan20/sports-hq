---
taskId: pool-picks-sat-refresh
title: "Sports HQ: Picks Sat 8am injury refresh"
cron: "0 8 * * 6"   # local time (CT)
status: saved picks, decisions log, second opinion and standalone push added 2026-11-02
---

Pool Picks is now part of the Sports HQ project (repo C:\Claude\sports-hq; this job's code is in its picks\ folder; the page is https://mbryan20.github.io/sports-hq/picks/). Use git merge, never rebase, if you need to sync by hand (py -m pp.publish already handles it). Sports HQ Picks is Michael's only pool picker.

Run the Pool Picks weekly job with STAGE=refresh.

Work in C:\Claude\sports-hq\picks. Open and follow C:\Claude\sports-hq\picks\RUNBOOK.md exactly, using the "refresh" stage steps and the section "Every card run" (A saved picks, B decisions log, C second opinion, D standalone push):
1. git pull.
2. In Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser) — read his already-SAVED picks (read-only) on the CFP and Yahoo pages (and BTO, for the record) and write them to the slate as cfp.saved, yahoo.saved and bto.saved. CFP locks at 11am CT, so an unsaved or different CFP pick is the most urgent line.
3. Read the Google Doc "Decisions log (agreed with Michael)" with the Google Docs connector (read_doc, id 1sQYBSQdJ7nrzLzBYx5y9UUAVg38dVgPSAqTEpPiKSfY).
4. Re-check injury and QB news only for the games still to be played, using fresh sources from the last 48 hours. Write research/2026-wNN-refresh.json.
5. Run `py -m pp.cards --stage refresh`. Any pick that changed moves to the top of its card in red. Record any departure from a decision in the slate's decisions.differs and run `py -m pp.cards --render-only`. Never change course silently.
6. Second opinion (RUNBOOK C): run `py -m pp.checks`, then spawn one subagent that did not build the card to check formats per pool, lock times, wager rules and minimums, decisions and saved picks, no "if X then Y" hedging, and that the numbers add up. Fix what it finds, then `py -m pp.checks --record "Checked: <what passed>"`.
7. Preview the push with `py -m pp.push`, then run `py -m pp.publish --stage refresh` (no --msg). The push leads with CHANGE / Differs lines, then picks that moved since Friday, then CFP and Yahoo lines ("your saved picks match" when they do), then the page link.
8. Confirm https://mbryan20.github.io/sports-hq/picks/ updated.

Hard rules:
- Read-only on the pool sites: never submit, save or change picks, never sign in or type a password. If a site is signed out, set that pool's saved = {"unread": "signed out"} and push a one-line alert.
- If a permission check blocks the Decisions log read, don't work around it: set decisions.unread and say what's blocked in the push.
- Never print or commit the CFBD key or the ntfy topic. Don't copy the Decisions log's other entries into the repo (it's public).
- Close any browser tabs you opened.
