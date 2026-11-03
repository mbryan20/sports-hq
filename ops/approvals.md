# Approval inbox: options (Michael's choice)

**The need:** the nightly improvement pass queues items with evidence in IMPROVEMENTS.md. Michael approves or holds each one
before anything is built, from his phone, including at work (claude.ai is blocked there; github.com, github.io and ntfy work).
It must not drown among game-day pushes (injury swaps, digest, radar, picks, guillotine), and it must not add to them.

**Until he chooses:** say "approve Q-003" or "hold Q-005" in the Sports HQ intake chat, or edit an item's Decision line on
github.com (pencil icon on IMPROVEMENTS.md). The nightly pass reads the Decision lines either way.

## Options

| | What he sees | How he answers | Buried? | Build |
|---|---|---|---|---|
| **A. Approvals card on the site** | A card on the main page (and a full list page) with each item waiting: title, the one-line evidence, expected impact, effort, risk, link to the design | ✅ Approve / ⏸ Hold / ✖ Reject buttons on each item. Each opens a pre-filled GitHub issue ("Approval: Q-012 approve"), exactly like today's 👍/👎 Feedback buttons; a workflow writes the Decision line and closes the issue | No: it sits on the page he already opens, until answered. But nothing tells him when something new arrives | S-M: a parser that turns IMPROVEMENTS.md into `docs/data/queue.json` (nightly), the card (dashboard redesign session owns `docs/lib/` and `docs/index.html`), and an approvals step in `feedback.yml` / `shq/feedback.py` |
| **B. One daily digest push on its own ntfy topic** | One push a day at a fixed time (e.g. 6pm CT, after work), only when something new needs a decision: "3 to decide: Q-012 cut odds no better than chance (S, Med risk), …" | Tap opens the Approvals card (A), or the queue on github.com | Less: a separate topic shows as its own subscription in the ntfy app and can be muted or given its own setting without touching game-day alerts. Fixed time = he knows when to look | S: the nightly pass sends it with ntfy's scheduled delivery so it lands at 6pm whatever time the pass ran (GitHub crons ran 4-7h late in October, so not from Actions). Needs a second topic, kept in a gitignored file like `picks/.ntfy_topic` |
| **C. Email digest** | One email a day (or week) with the same list, under a Gmail label that skips the inbox | Reply "approve 12, hold 5"; the nightly pass reads replies with the Gmail connector | Depends on his inbox; a label keeps it out of the main view but also out of sight | S-M: the nightly pass drafts/sends with the Gmail connector (needs that connector in the scheduled task). Not confirmed: whether Gmail opens on his work computer |
| **D. GitHub Issues** | One issue per item, labels for status | Comment or add a label | Yes: GitHub's notifications mix with everything else from the repo, and the repo is public, so anyone can comment | S, but it splits the queue between a file and issues |

## Recommendation: A + B

The card is the inbox (it never scrolls away, and every answer is one tap that works at work); the single 6pm push on its
own topic is the doorbell, and it only rings on days with something new. Game-day alerts stay on the main topic and never
mix with approvals. The answer path reuses the Feedback pipeline that already works from his phone.

What gets built after he picks A + B:
1. `shq/queue.py`: IMPROVEMENTS.md → `docs/data/queue.json` (items with Status proposed, designed, measuring, held), run by the
   model-health workflow every night; tests.
2. `feedback.yml` + `shq/feedback.py`: issues titled "Approval: Q-NNN approve|hold|reject" from the repo owner set that
   item's Decision line ("approved 2026-11-05") and close the issue (others keep going to FEEDBACK.md).
3. The Approvals card and list page in `docs/lib/` (dashboard redesign session), plus a model-health scorecard (Q-013) beside it.
4. Nightly pass step 9: if any item became `designed` or `reopened` since the last digest, one push to the approvals topic,
   scheduled for 6pm CT, linking to the card.
5. A new topic: Michael subscribes to it in the ntfy app (a manual step with exact instructions when it's built).

Not confirmed: whether the iPhone ntfy app lets one topic have its own sound (Android does, per topic).

## Chosen
(none yet)
