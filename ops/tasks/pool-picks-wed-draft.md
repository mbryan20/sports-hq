---
taskId: pool-picks-wed-draft
title: "Sports HQ: Picks Wed 9pm drafts"
cron: "0 21 * * 3"   # local time (CT)
status: saved picks, decisions log, second opinion and standalone push added 2026-11-02
---

Pool Picks is now part of the Sports HQ project (repo C:\Claude\sports-hq; this job's code is in its picks\ folder; the page is https://mbryan20.github.io/sports-hq/picks/). Use git merge, never rebase, if you need to sync by hand (py -m pp.publish already handles it). Sports HQ Picks is Michael's only pool picker.

Run the Pool Picks weekly job with STAGE=draft.

Work in C:\Claude\sports-hq\picks. Open C:\Claude\sports-hq\picks\RUNBOOK.md and follow it exactly, including the section "Every card run" (A saved picks, B decisions log, C second opinion, D standalone push).

FIRST, the Wednesday catch-up: after `git pull`, check whether data/postmortem/2026-wNN.json exists for last week. NN = current_week() - 1, where current_week comes from pp.cards. If it doesn't exist (Tuesday's run was missed), run the full "STAGE = postmortem" section first, including its publish and push.

THEN the draft:
1. Read this week's slates from the BTO, CFP and Yahoo sites in Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). On the same pages, read his already-SAVED picks (read-only) and write them to the slate file as bto.saved, cfp.saved and yahoo.saved (RUNBOOK "Every card run" A).
2. Read the Google Doc "Decisions log (agreed with Michael)" with the Google Docs connector (read_doc, id 1sQYBSQdJ7nrzLzBYx5y9UUAVg38dVgPSAqTEpPiKSfY). Search Gmail (read-only) for emails from shaunguhy@gmail.com newer than the last survivor entry in that log; only if one says Michael is still alive or the pool chopped, set survivor_note in the slate.
3. Do fresh injury, QB, line-movement and weather research with sources.
4. Run `py -m pp.cards --stage draft` and sanity-check data/cards.json. Record any departure from a decision in the slate's decisions.differs and run `py -m pp.cards --render-only` (RUNBOOK B). Never change course silently.
5. Second opinion (RUNBOOK C): run `py -m pp.checks`, then spawn one subagent that did not build the card to check formats per pool, lock times, wager rules and minimums, decisions and saved picks, no "if X then Y" hedging, and that the numbers add up. Fix what it finds, then `py -m pp.checks --record "Checked: <what passed>"`.
6. Preview the push with `py -m pp.push`, then run `py -m pp.publish --stage draft` (no --msg). The push leads with CHANGE / Differs lines, then one line per pool (BTO, CFP, Yahoo), then the page link.
7. Confirm https://mbryan20.github.io/sports-hq/picks/ shows the new timestamp and the Checked line.

Hard rules:
- Read-only on the pool sites: never submit, save or change picks, never sign in or type a password.
- If a site is signed out, note it in the slate file (that pool's saved = {"unread": "signed out"}) and push a one-line alert saying which site Michael needs to sign in to in his Chrome.
- If a permission check blocks the Decisions log read, don't work around it: set decisions.unread and say what's blocked in the push.
- Never print or commit the CFBD key or the ntfy topic. Don't copy the Decisions log's other entries into the repo (it's public).
- Survivor is eliminated (Week 7, NYJ), so make no survivor picks.
- Close any browser tabs you opened when done.
