# Ideas and open questions

Add anything under "From Michael", one line per idea starting with "- " (from your phone:
https://github.com/mbryan20/sports-hq/edit/main/IDEAS.md). The Sports HQ intake chat picks new lines up, and the
monthly review ranks what's left. Sports HQ only; other projects don't read this file.

## From Michael
- 2026-10-28: Sleeper's beta website now shows the guillotine **Chop** menu (only the app had it before).
  It may give official chop/elimination data a laptop task can read in Chrome. Sent to the guillotine
  session to inspect; findings go in ROADMAP.md "Lessons".
- Baseball leagues (ESPN: 3-Ball dynasty, Hardball) — plan in Feb, before drafts (ops/tasks/baseball-kickoff.md).

## Open decisions
- **Overlap with the older Claude routines.** A separate set of claude.ai routines (Fantasy football helper with
  Chrome auto-swaps and Tuesday pickups/guillotine bids, Basketball helper, Guillotine strategy review,
  Background job runner / Michael's Queue, Laptop watchdog, System health audit) still runs alongside Sports HQ.
  Sports HQ now covers all 8 teams' lineups, injury alerts and weekly plans; the routines still own *actions*
  (auto-swaps through Chrome, FAAB bids) and the War Room's strategy model. Decide per routine: keep, fold into
  Sports HQ, or retire — and turn off duplicate alerts.
- ~~Fantasy Command Center artifact~~: folded into Sports HQ 2026-10-30 (dynasty assets, IR-slot check).

## Proposed by Claude (not built yet)
- Password-lock the whole site (encrypted data, passphrase once per device). Waiting on Michael's go.
- (Built since: guillotine odds + bids, the Today tab, the basketball category view. See ROADMAP.md.)

## Proposed by monthly review
From `reviews/2026-11.md` (ranked there; nothing is built without Michael's OK):
- Laptop 7:30am sync ends with `gh workflow run run.yml`, and manual dispatches get their own concurrency group, so the 8am digest and Tuesday Weekly don't wait on GitHub's dropped crons (no run fired 8am–1pm on Mon Oct 26; 7 manual dispatches were dropped in October).
- Push log: every push (time, title, message; never the topic) goes to `state/pushes.json` for 60 days, with a "Recent alerts" list on the site.
- "Likely out (unconfirmed)" push when a starter's ESPN note says "not expected to play" or projections drop to 0 near lock (Breece Hall, Nov 1). Changes the injury rule, so it needs Michael's call.
- What to do card agrees with itself: waiver drops never touch players the lineup moves start this week; the Bids line matches Waiver adds; IR-slot lines cite the newest ESPN note.
- Picks backup check runs inside run.yml's loop (its own crons ran 4–7h late) and gets the `CFBD_API_KEY` secret.
- Laptop tasks record their own ok/failed result for the footer, and end with "FAILED: <reason>" so a failed run doesn't show as "succeeded".
- Hygiene pass: CRLF→LF (`picks/pp/grade.py`, `model.py`), untrack `picks/cache/cfbd/*.json`, daily-sync prompt reads the ntfy topic from the file, copy every laptop prompt into `ops/tasks/`, remove merged worktrees.
- Reword the ROADMAP browser rule to "never the built-in browser for sign-in sites" (the 375px check needs its viewport emulation).
