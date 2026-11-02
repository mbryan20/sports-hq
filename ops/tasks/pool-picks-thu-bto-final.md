---
taskId: pool-picks-thu-bto-final
title: "Sports HQ: Picks Thu 8pm BTO final"
cron: "0 20 * * 4"   # local time (CT)
status: saved picks, decisions log, second opinion and standalone push added 2026-11-02
---

Pool Picks is now part of the Sports HQ project (repo C:\Claude\sports-hq; this job's code is in its picks\ folder; the page is https://mbryan20.github.io/sports-hq/picks/). Use git merge, never rebase, if you need to sync by hand (py -m pp.publish already handles it). Sports HQ Picks is Michael's only pool picker.

Run the Pool Picks weekly job with STAGE=bto_final.

Work in C:\Claude\sports-hq\picks. Open and follow C:\Claude\sports-hq\picks\RUNBOOK.md exactly, using the "bto_final" stage steps and the section "Every card run" (A saved picks, B decisions log, C second opinion, D standalone push):
1. git pull.
2. Re-read the BTO slate, balance and leaderboard, and the Yahoo slate, in Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). Mark games that already kicked off (Thursday NFL) as locked. On the same pages, read his already-SAVED picks (read-only) for BTO, CFP and Yahoo and write them to the slate as bto.saved, cfp.saved and yahoo.saved.
3. Read the Google Doc "Decisions log (agreed with Michael)" with the Google Docs connector (read_doc, id 1sQYBSQdJ7nrzLzBYx5y9UUAVg38dVgPSAqTEpPiKSfY).
4. Do fresh research with sources.
5. Run `py -m pp.cards --stage final --pools bto,yahoo,cfp,survivor`. BTO and Yahoo's Friday game and TB2 are FINAL tonight because TB2 locks Fri 6:25pm. CFP stays a draft until Friday; say so in the CFP card's notes if needed. Record any departure from a decision in the slate's decisions.differs and run `py -m pp.cards --render-only`. Never change course silently.
6. Sanity-check that BTO obeys the mode rules: bet count, Big Game included, largest bet at most 2x the smallest, $10 multiples, 4 line points.
7. Second opinion (RUNBOOK C): run `py -m pp.checks`, then spawn one subagent that did not build the card to check formats per pool, lock times, wager rules and minimums, decisions and saved picks, no "if X then Y" hedging, and that the numbers add up. Fix what it finds, then `py -m pp.checks --record "Checked: <what passed>"`.
8. Preview the push with `py -m pp.push`, then run `py -m pp.publish --stage final --title "Pool Picks: BTO FINAL posted"` (no --msg). The push leads with CHANGE / Differs lines (anything unsaved counts tonight), then BTO and Yahoo lines, then the page link.
9. Confirm https://mbryan20.github.io/sports-hq/picks/ updated.

Hard rules:
- Read-only on the pool sites: never submit, save or change picks, never sign in or type a password. If a site is signed out, set that pool's saved = {"unread": "signed out"} and push a one-line alert.
- If a permission check blocks the Decisions log read, don't work around it: set decisions.unread and say what's blocked in the push.
- Never print or commit the CFBD key or the ntfy topic. Don't copy the Decisions log's other entries into the repo (it's public).
- Close any browser tabs you opened.
