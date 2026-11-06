---
taskId: pool-picks-thu-bto-check
title: "Sports HQ: Picks Thu 4pm BTO check"
cron: "0 16 * * 4"   # local time (CT)
status: written 2026-11-05 (R2 / Q-030); the Claude Ops session creates the scheduled task
---

Pool Picks Thursday check, for weeks where a BTO bet locks before the Thu 8pm final run. BTO locks each game at its
kickoff, so a saved bet on a Thursday NFL game (usually 7:15pm CT) can't be fixed by the 8pm run. Repo C:\Claude\sports-hq;
code in its picks\ folder. Read-only on BTO. No commits.

1. In C:\Claude\sports-hq: `git pull --no-rebase --no-edit` (never rebase).
2. In C:\Claude\sports-hq\picks run `py -m pp.thu_check --needed`. If it exits 3 ("no Thursday BTO game still to play"),
   stop here: no browser, no push.
3. Read Michael's saved BTO bets, read-only, in Michael's Chrome via Claude in Chrome. Follow C:\Claude\sports-hq\ops\BROWSER.md
   to connect (never the built-in browser). Open a new tab at https://beattheoddspickem.com/player/picks/current and read his
   saved bets: pick, adjusted line including line points, wager (picks\RUNBOOK.md "Every card run", A: `get_page_text` can
   return nothing there; read `document.body.innerText` with `javascript_tool`, in pieces if long). Never click Save, Submit
   or any pick, and never sign in or type a password.
4. Write what you read to `%TEMP%\bto_saved.json` (not into the repo), in this shape:
   `{"read": "<ISO time>", "bets": [{"key": "<Away>@<Home>", "pick": "<Team> <line incl. LP>", "wager": 600}]}`, with keys
   exactly as in this week's `picks\slates\<year>-wNN.json` BTO games (ESPN abbreviations for NFL teams). An empty `bets`
   list when nothing is saved. If the site is signed out or won't load, write `{"unread": "signed out"}` (or the reason).
5. Run `py -m pp.thu_check --saved %TEMP%\bto_saved.json --push`. It compares the saved bets with the published card
   (`picks\data\published\<year>-wNN-bto.json`) and pushes (ntfy, topic from `picks\.ntfy_topic`) only when they differ,
   with one "yours → card" line per game, the Thursday game first, and the lock time; an unread site also pushes, so Michael
   still checks before the lock. When they match it prints "No push" and sends nothing.
6. Close the tab you opened. Delete `%TEMP%\bto_saved.json`.

Hard rules:
- Read-only on BTO: never submit, save or change a pick, never sign in, never type a password.
- Never print or commit the ntfy topic. Don't commit anything from this run (the Thu 8pm final re-reads the saved bets).
- If Chrome isn't connected, push nothing and end with "FAILED: Chrome not connected" as the last line.
