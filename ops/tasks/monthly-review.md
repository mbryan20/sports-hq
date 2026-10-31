---
taskId: sports-hq-monthly-review
title: "Sports HQ: monthly review"
cron: "0 10 1 * *"   # 1st of each month, 10am CT
status: CREATED 2026-10-27 (scheduled task, Auto mode); rules check added 2026-10-31
---

Monthly review of Michael's Sports HQ system (repo C:\Claude\sports-hq; site https://mbryan20.github.io/sports-hq/; README.md explains every part). Goal: scrutinize what exists, find what's broken, flaky, missing or improvable, and propose ranked improvements. Do NOT change code, schedules or tasks yourself; this run only investigates and reports. Michael approves changes.

Setup (PowerShell): $env:Path=[Environment]::GetEnvironmentVariable('Path','Machine')+';'+[Environment]::GetEnvironmentVariable('Path','User'); Set-Location C:\Claude\sports-hq; git pull --no-rebase --no-edit -q

Check, with evidence:
1. Reliability: `gh run list -L 200 --json workflowName,conclusion,createdAt` — failure/cancel rate per workflow over the last 30 days, and the longest gap between successful "Sports HQ run" runs on game days. Do the tests pass (`py -m unittest discover -s tests`)?
2. Freshness: docs/data/status.json "jobs" (laptop jobs' last delivery), "notes" and "errors"; state/alerts.json for stale-sync alerts this month; each Sports HQ laptop task's recent runs (list_task_runs): failures and reasons.
3. Usefulness: alerts sent (state/alerts.json) vs what happened (injured starters caught before lock? any missed?). Open the site at phone width; note anything confusing, stale or missing.
4. Coverage vs Michael's goals (one all-in-one system for all his fantasy leagues and pools; phone-first; minimal manual work): read IDEAS.md and README.md "Open items".
5. External changes: Yahoo Fantasy API approval (does Kosmonauts still read from the saved roster?), ESPN/Sleeper API changes, upcoming season starts that need setup.
6. Rules check (drift between the written rules and what the code does). Read ROADMAP.md "Rules that must not break", picks/RUNBOOK.md "Hard rules" and Michael's global CLAUDE.md rules. For each rule, check that the code, .github/ workflows and scripts, ops/tasks/ and the Sports HQ scheduled-task prompts actually follow it, and cite file:line for every break. At minimum:
   - Secrets: `git grep -c -F -f picks/.ntfy_topic` must find nothing (print counts only, never the topic); no CFBD key, Yahoo token, cookie or password in tracked files; .gitignore still covers picks/.env, picks/.ntfy_topic and state/dynasty_sheet.json.
   - Git: no rebase anywhere (`git grep -n -- "--rebase"`). Known open as of 2026-10-31: .github/commit_data.sh, .github/workflows/picks-backup.yml, picks/pp/publish.py.
   - No paid APIs and no AI calls in GitHub Actions (the workflows and the Python they run).
   - Read-only on fantasy and pool sites: nothing adds, drops, trades, bids or submits picks; the only allowed write is a Yahoo lineup swap via the API.
   - CFBD: picks/cache/cfbd_calls.json is under 900 for this month, and nothing calls CFBD without going through picks/pp/http.py.
   - Injury calls: benching, swaps and pushes still go through status.confirm (ESPN-confirmed, dated, cited).
   - Phone width: every tab and the Picks page at 375px with no horizontal scroll.
   - LF line endings: `git ls-files --eol` shows no crlf files in the index.
   Also flag any rule that looks outdated, contradicts another rule, or is not written down anywhere but clearly matters.

Write reviews\YYYY-MM.md: a 3-line health summary; problems found (each with evidence); a "Rule breaks" section from check 6 (or "none found"); up to 10 ranked improvements with effort (S/M/L), value and risk, with rule breaks ranked among them. Append new ideas to IDEAS.md under "Proposed by monthly review". Commit both (git add reviews IDEAS.md; git commit -m "Monthly review YYYY-MM"; git pull --no-rebase --no-edit; git push). Never commit the ntfy topic.

Finally send ONE push (replace TEXT with the 3-line summary, the number of rule breaks, plus the top 3 improvements):
Invoke-RestMethod -Method Post -Uri https://ntfy.sh/ -ContentType 'application/json' -Body (@{topic=(Get-Content C:\Claude\sports-hq\picks\.ntfy_topic).Trim(); title='Sports HQ monthly review'; message='TEXT'; tags=@('mag'); click='https://github.com/mbryan20/sports-hq/tree/main/reviews'} | ConvertTo-Json)

Rules: read-only on all fantasy and pool sites; never type passwords; close any browser tabs you open.
