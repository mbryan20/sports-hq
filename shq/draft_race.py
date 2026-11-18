"""Draft-pick mode for a dynasty league that's out of the playoff race (fantasy-rules.md rule 17, Nov 17).

Sunday's Best (Domo Arigato) pays only the top 3. Its rookie draft order (checked on Sleeper Nov 17: 2025 standings vs
the 2026 draft) is worst record first, fewer points scored breaking a tie, the same order all 3 rounds; playoff teams
pick 7-12. So once a playoff spot is out of reach, the page shows the draft pick he holds now, and the advice drops
small start/sit upgrades and points-only pickups. It never tanks: a starter who is OUT, on bye or missing is still
fixed, and a big start/sit gap (DRAFT_KEEP_GAIN or more) is still shown."""

DRAFT_KEEP_GAIN = 3.0    # a start/sit upgrade this big still shows: benching a clearly better player looks like a tank
DRAFT_ADD_VALUE = 250    # a pickup must add this much FantasyCalc dynasty value over the drop (rule 2), points alone don't count


def _rec(r):
    s = r.get("settings") or {}
    return (s.get("wins") or 0, s.get("losses") or 0, s.get("ties") or 0,
            round((s.get("fpts") or 0) + (s.get("fpts_decimal") or 0) / 100, 1))


def build(settings, rosters, names, my_roster_id):
    """{"out", "eliminated", "record", "games_left", "cut_line", "pick", "teams", "pick_line", "text"} or None.
    out: even winning every game left only reaches the current last playoff seed's wins (practically out).
    eliminated: at least `playoff_teams` teams already have more wins than my best case (mathematically out).
    pick: my draft slot if the season ended now (worst record first, fewer points first on a tie)."""
    settings = settings or {}
    seeds = settings.get("playoff_teams")
    start = settings.get("playoff_week_start")
    done = settings.get("last_scored_leg")
    teams = [r for r in rosters or [] if r.get("roster_id") is not None]
    if not seeds or not start or done is None or len(teams) <= seeds:
        return None
    games_left = max(0, start - 1 - done)
    recs = {r["roster_id"]: _rec(r) for r in teams}
    if my_roster_id not in recs:
        return None
    w, l, t, pf = recs[my_roster_id]
    best_case = w + games_left
    by_seed = sorted(recs.items(), key=lambda kv: (-kv[1][0], -kv[1][3]))
    cut_line = by_seed[seeds - 1][1][0]
    eliminated = sum(1 for rid, rec in recs.items() if rid != my_roster_id and rec[0] > best_case) >= seeds
    out = eliminated or best_case <= cut_line
    order = sorted(recs.items(), key=lambda kv: (kv[1][0], kv[1][3]))   # worst record first, fewer points first
    pick = next(i for i, (rid, _) in enumerate(order, 1) if rid == my_roster_id)
    nm = lambda rid: names.get(rid) or f"Team {rid}"
    rec_txt = lambda rec: f"{rec[0]}-{rec[1]}" + (f"-{rec[2]}" if rec[2] else "")
    ahead = order[pick - 2] if pick > 1 else None
    behind = order[pick] if pick < len(order) else None
    bits = []
    if ahead:
        a = ahead[1]
        bits.append(f"{nm(ahead[0])} ({rec_txt(a)}, {a[3]:g} pts) holds #{pick - 1}")
    if behind:
        b = behind[1]
        bits.append(f"{nm(behind[0])} ({rec_txt(b)}, {b[3]:g} pts) is #{pick + 1}")
    pick_line = f"Draft pick if the season ended now: #{pick} of {len(order)}" + (f" ({'; '.join(bits)})" if bits else "")
    if out:
        why = ("can't make the playoffs" if eliminated else
               f"winning all {games_left} left only reaches {best_case} wins; the last playoff seed already has {cut_line}")
        text = (f"Out of the playoff race ({rec_txt(recs[my_roster_id])}, {why}). Draft-pick mode: worst record picks "
                f"first, fewer points breaks a tie. Normal lineups stay; small start/sit swaps and points-only "
                f"pickups are left out (rule 17).")
    else:
        text = None
    return {"out": out, "eliminated": eliminated, "record": rec_txt(recs[my_roster_id]), "games_left": games_left,
            "cut_line": cut_line, "pick": pick, "teams": len(order), "pick_line": pick_line, "text": text}


def active(league):
    return bool((getattr(league, "race", None) or {}).get("out"))


def keep_move(gain):
    return gain >= DRAFT_KEEP_GAIN


def keep_add(a):
    """A pickup in draft-pick mode: a skill player who adds clear dynasty value over the drop. No K/DEF streams."""
    fa, drop = a["fa"], a.get("drop")
    if not fa.get("val") or (fa.get("positions") or ["?"])[0] in ("K", "DEF"):
        return False
    return fa["val"] - ((drop or {}).get("val") or 0) >= DRAFT_ADD_VALUE
