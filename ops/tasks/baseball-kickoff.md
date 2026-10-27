---
taskId: sports-hq-baseball-kickoff
title: "Sports HQ: add baseball (Feb reminder)"
fireAt: "2027-02-01T10:00:00-06:00"   # one-time
status: NOT CREATED YET (needs Michael's OK)
---

Prepare to add Michael's ESPN fantasy BASEBALL leagues to Sports HQ (repo C:\Claude\sports-hq; README.md explains the design). Leagues: "3-Ball Dynasty League" baseball (ESPN leagueId 142878, his team id 6, "Ragonk Force", dynasty) and "Hardball" (ESPN leagueId 143598, team id 2, "Ippei You Later"). Confirm 2027 season ids on https://fantasy.espn.com/baseball/ in the built-in browser (read-only; never type passwords).

Do NOT build it yet. Instead:
1. Check whether each league is publicly readable: GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/2027/segments/0/leagues/<id>?view=mSettings (200 = the cloud reads it directly, like 3-Ball football/basketball; 401 = needs the laptop snapshot, like Stempak). Note draft dates and scoring type.
2. Write plans\baseball.md: changes needed (LEAGUES entries with sport "mlb"; ESPN flb slot ids; MLB schedule and injuries endpoints; daily lineups; probable pitchers / two-start weeks for the weekly tab), effort, and the date each must be live (before each draft).
3. Commit (git pull --no-rebase --no-edit; git add plans; git commit -m "Baseball plan"; git push).
4. Push Michael:
Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Sports HQ: baseball setup is ready to start'; message='Plan written (plans/baseball.md). Open a Claude Code session in C:\Claude\sports-hq and say: build the baseball plan.'; tags=@('baseball')} | ConvertTo-Json)
