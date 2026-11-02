---
taskId: pool-picks-signin-check
title: "Sports HQ: sign-in check (manual)"
cron: "manual"   # local time (CT)
status: copied 2026-11-02
---

Read-only sign-in check for Sports HQ's laptop jobs, requested by Michael. Do not change anything:
- no commits, pushes or file edits
- no notifications
- no clicks, no form fills, no typing
- never enter a password or press a sign-in button

Use Michael's Chrome via Claude in Chrome — follow C:\Claude\sports-hq\ops\BROWSER.md to connect (never the built-in browser). Open each URL below with navigate, then read the page with get_page_text:
1. https://beattheoddspickem.com/player/dashboard
2. https://ncaa-pool-two.vercel.app/player/picks
3. https://football.fantasysports.yahoo.com/college/3659
4. https://football.fantasysports.yahoo.com/f1/681200/11 (Kosmonauts)
5. https://fantasy.espn.com/basketball/team?leagueId=190278&teamId=5&seasonId=2027 (ESPN)

For each site, report:
- SIGNED-IN or SIGNED-OUT. A redirect to a /login page, login.yahoo.com, or an ESPN log-in prompt means signed out.
- The page title and final host.
- For a signed-in page, one detail that identifies the account, such as the welcome name, balance, team or group name.

Close every tab you opened. End with one line in the form "BTO: X, CFP: X, Yahoo picks: X, Kosmonauts: X, ESPN: X".
