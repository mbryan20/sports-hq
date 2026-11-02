---
taskId: pool-picks-tue-postmortem
title: "Sports HQ: Picks Tue 8pm postmortem"
cron: "0 20 * * 2"   # local time (CT)
status: copied 2026-11-02
---

Pool Picks is now part of the Sports HQ project (repo C:\Claude\sports-hq; this job's code is in its picks\ folder; the page is https://mbryan20.github.io/sports-hq/picks/). Use git merge, never rebase, if you need to sync by hand (py -m pp.publish already handles it).

Run the Pool Picks weekly job with STAGE=postmortem.

Work in C:\Claude\sports-hq\picks. Open C:\Claude\sports-hq\picks\RUNBOOK.md and follow the section "STAGE = postmortem" exactly:
1. git pull.
2. In Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser), read read-only what Michael actually entered last week and his standings:
   - BTO: /player/history and /player/leaderboard
   - CFP: /player/history and /player/leaderboard
   - Yahoo: the group 3659 picks and standings pages
   Write them to data/entries/2026-wNN.json in the runbook schema. NN = last week's CFBD week, which is current_week() - 1.
3. Run `py -m pp.grade --week NN`. It grades the posted card picks and the entries against final scores and lists every difference.
4. Append last week's section to C:\Claude\sports-hq\docs\picks\history.md:
   - the records (card vs entered) and standings
   - for each difference, which call was better and why, judged on pre-kickoff information
   - exactly 3 bullets that separate process from outcome
5. If this week's slates are posted, save them to the next slates file.
6. Run `py -m pp.publish --stage postmortem --title "Pool Picks postmortem posted" --msg "<one-line summary>"`, which sends the ntfy push.

Hard rules:
- Read-only on the pool sites: never submit or change picks, never sign in or type a password. If a site is signed out, note it in the history and push a one-line alert naming the site.
- Never print or commit the CFBD key.
- Close any browser tabs you opened.
