# Site feedback

Michael's 👍 / 👎 / ideas from the site's Feedback buttons (on the main page and every layout in
the ▦ menu). Each tap opens a pre-filled GitHub issue; `.github/workflows/feedback.yml` adds it below under **Inbox**
as one line (date, mood, layout, spot on the page, screen width and theme, his words, issue link) and closes the issue.
Feedback typed straight into a new issue titled "Feedback: …" lands here too.

- **Intake chat:** at the start of each session, and whenever Michael says "check feedback", route every Inbox line
  like any other request (ROADMAP.md "Hand-off practice"), then move it to **Handled** with where it went.
- **Monthly review:** reads the whole file for patterns (what he keeps liking or disliking, per layout) and ranks
  layout work alongside everything else.
- Layout ideas waiting their turn live in ROADMAP.md "Next layout ideas".

## Inbox

- 2026-10-31 👍 Like · Lab page · Layout A · 1920px, dark: "generally pretty easy to use on the computer - a good start" ([#2](https://github.com/mbryan20/sports-hq/issues/2))
- 2026-10-31 👎 Dislike · Lab page · Layout D · 1920px, dark: "Right now it is very noisy - maybe useful on nfl game days. I will check then. This should not be the default by any means." ([#3](https://github.com/mbryan20/sports-hq/issues/3))

## Handled

- 2026-11-15 👎 Dislike · A · Scoreboard · Domo Arigato detail · 402px, dark: "No where to say skip or comment on what I think about something. Also, on the main part if I click on fixes I’d like to be taken to some sort of screen or presented with a pop up that shows what needs to be fixed or addressed so I can quickly address that and move on." ([#5](https://github.com/mbryan20/sports-hq/issues/5)) — **Handled 2026-11-17 (commit de0e3b4):** each fix, lineup move and waiver add on a league page now has Skip (opens a pre-filled feedback issue) and Comment (opens the feedback sheet) buttons; tapping the "Fixes now" total on the main page opens a pop-up listing every fix by league with Clear / Skip / Comment and an Open league link.
