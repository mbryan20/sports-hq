# War Room v2 vs the current War Room: week 8 (checked Sat Oct 31 2026, ~10am CT)

Both runs use the same model and default sliders. I ran each page's own JavaScript on its own data:
- **Current War Room:** the docs/war-room copy, data "Week 7 final; roster 4 cut confirmed (roster
  empty); week 8 waivers settled. Sat Oct 31", built by the claude.ai task at 6:19am.
- **v2:** built straight from Sleeper's API, with data through Fri 7:30pm CT.

## Same
- **Rosters and FAAB:** every surviving team's roster and FAAB match exactly.
- **Player averages:** all 320 shared players have identical season and last-3 averages.
- **Cut risk for week 8:** identical to the tenth of a percent for all 11 teams.

  | Team | FAAB | Week 8 cut risk | Exp. weeks left | Win |
  |---|---|---|---|---|
  | MoneyManChas | $150 | 25.6% | 2.1 | 0.3% |
  | GoodFellas77 | $77 | 17.4% | 4.2 | 2.8% |
  | SteelRob420 | $43 | 11.9% | 3.9 | 3.1% |
  | CodyRust | $0 | 10.1% | 5.7 | 12.2% |
  | robert8063 | $37 | 9.3% | 3.9 | 0.9% |
  | Aniasin1 | $4 | 8.5% | 4.3 | 1.5% |
  | JHED1979 | $43 | 3.8% | 4.7 | 6.1% |
  | damonhawk1 | $106 | 3.7% | 7.2 | 25.1% |
  | Swegs4 | $20 | 3.7% | 7.3 | 27.1% |
  | **michaelbryan** | **$59** | **3.2%** | **6.0** | **11.6%** |
  | drewpepin1 | $15 | 3.1% | 5.7 | 9.6% |
- **Free-agent calls:** the same "Add free" list, led by Jayden Daniels, Bryce Young and Davante Adams.

## Different, and why
1. **Freed players.**
   - **Current:** shows none. Heston80's roster was already empty, and the old builder took freed
     players from that roster. This is the "page errored when the cut roster was empty" problem; the
     patch kept the page up but lost the list.
   - **v2:** takes them from Sleeper's chop record, so it lists the 5 Heston80 players nobody has
     claimed yet:
     - **Bo Nix (QB):** Bid, est. price $3, your max $6.
     - **Jake Bates (K):** Priced out, $11 vs $2.
     - **Jaylin Noel, Jadarian Price, Cooper Kupp:** Skip.
2. **Team projections:** up to 0.1 pt apart (for example MoneyManChas 115.2 vs 115.3, you 140.2 vs
   140.3). Too small to change any risk at the precision shown. Not confirmed: probably nflverse
   files re-downloaded 4 hours apart (stat corrections), since rosters and averages match.
3. **Bid history:** v2 has 150 claims vs 149. It includes one daily-waiver claim processed after the
   old builder's read.
4. **TEN DEF** shows as an "Add free" row in v2 only. It's a borderline row: its rest-of-season gain is
   right at the list's cutoff.

## Versus the dashboard (shq/guillotine.py)
- The dashboard also says 3% for you this week.
- It ranks the bottom differently (CodyRust 24%, MoneyManChas 18%) because it uses Sleeper's weekly
  projections instead of past points.
- That's the one-set-of-numbers decision for later (audit item 1, option 4).
