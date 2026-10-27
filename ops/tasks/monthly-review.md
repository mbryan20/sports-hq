---
taskId: sports-hq-monthly-review
title: "Sports HQ: monthly review"
cron: "0 10 1 * *"   # 1st of each month, 10am CT
status: NOT CREATED YET (needs Michael's OK)
---

Monthly review of Michael's Sports HQ system (repo C:\Claude\sports-hq; site https://mbryan20.github.io/sports-hq/; README.md explains every part). Goal: scrutinize what exists, find what's broken, flaky, missing or improvable, and propose ranked improvements. Do NOT change code, schedules or tasks yourself; this run only investigates and reports. Michael approves changes.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

Check, with evidence:
1. Reliability: `gh run list -L 200 --json workflowName,conclusion,createdAt` — failure/cancel rate per workflow over the last 30 days, and the longest gap between successful "Sports HQ run" runs on game days. Do the tests pass (`py -m unittest discover -s tests`)?
2. Freshness: docs/data/status.json "jobs" (laptop jobs' last delivery), "notes" and "errors"; state/alerts.json for stale-sync alerts this month; each Sports HQ laptop task's recent runs (list_task_runs): failures and reasons.
3. Usefulness: alerts sent (state/alerts.json) vs what happened (injured starters caught before lock? any missed?). Open the site at phone width; note anything confusing, stale or missing.
4. Coverage vs Michael's goals (one all-in-one system for all his fantasy leagues and pools; phone-first; minimal manual work): read IDEAS.md and README.md "Open items".
5. External changes: Yahoo Fantasy API approval (does Kosmonauts still read from the saved roster?), ESPN/Sleeper API changes, upcoming season starts that need setup.

Write reviews\YYYY-MM.md: a 3-line health summary; problems found (each with evidence); up to 10 ranked improvements with effort (S/M/L), value and risk. Append new ideas to IDEAS.md under "Proposed by monthly review". Commit both (git add reviews IDEAS.md; git commit -m "Monthly review YYYY-MM"; git pull --no-rebase --no-edit; git push).

Finally send ONE push (replace TEXT with the 3-line summary plus the top 3 improvements):
Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Sports HQ monthly review'; message='TEXT'; tags=@('mag'); click='https://github.com/mbryan20/sports-hq/tree/main/reviews'} | ConvertTo-Json)

Rules: read-only on all fantasy and pool sites; never type passwords; close any browser tabs you open.
