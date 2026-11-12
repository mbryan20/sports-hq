"""Football Players page data (F1): every rostered player and the best free agents in each football league, with
rest-of-season and this-week ranks by position. Pure logic on what the run already reads, no AI.

- This week: the league's own projection (ESPN's for ESPN leagues, Sleeper's for Sleeper leagues and Kosmonauts), in the
  league's scoring, as on the lineup tab.
- Rest of season: Sleeper's projections for the next ROS_WEEKS weeks scored with the league's settings, per game
  (byes not counted, weeks Sleeper hasn't re-projected after a trade or depth-chart change take his live weekly number,
  IR minimum weeks count 0; shq/values.py, the same numbers the waiver adds and trade finder use). QB/RB/WR/TE only; kickers
  and defenses rank on this week.
- Value: FantasyCalc's dynasty or redraft value for the league's settings.
- Experts: ESPN's analysts' consensus position rank this week and lately (shq/experts.py), when they rank him.
Written to docs/data/players_nfl.json (docs/players/ shows it next to the basketball leagues)."""
from . import values

POS = ("QB", "RB", "WR", "TE", "K", "DEF")
ALIAS = {"D/ST": "DEF", "DST": "DEF", "PK": "K"}
FA_KEEP = 150          # free agents kept per league, best first (rostered players are all kept)


def position(p):
    for x in p.get("positions") or []:
        x = ALIAS.get(x, x)
        if x in POS:
            return x
    return None


def _owners(league):
    """[(player dict, owner)]: mine "me", other teams by name, free agents None."""
    out = [(p, "me") for p in list(league.starters) + list(league.bench) if not p.get("empty")]
    for t in getattr(league, "others", None) or []:
        out += [(p, t["name"]) for p in t["players"]]
    seen = {p["id"] for p, _ in out}
    out += [(p, None) for p in league.free_agents if p["id"] not in seen]
    return out


def rank(rows, key):
    """Write "<key>_rk" = rank within position (1 = best) for rows with a value."""
    by_pos = {}
    for r in rows:
        if r.get(key):
            by_pos.setdefault(r["pos"], []).append(r)
    for rs in by_pos.values():
        for i, r in enumerate(sorted(rs, key=lambda r: -r[key]), 1):
            r[key + "_rk"] = i


def build(league):
    """{"kind": "nfl", "week", "players", "sources", "basis"} or None for a non-football league."""
    if getattr(league, "sport", "nfl") != "nfl":
        return None
    try:
        valued = values.annotate(league)
    except Exception:
        valued = False
    rows, fas = [], []
    for p, own in _owners(league):
        pos = position(p)
        if not pos:
            continue
        ppg = p.get("ppg") if valued and pos in values.SKILL else None
        proj = p.get("proj") or 0.0
        if own is None and not (ppg or proj):
            continue
        r = {"id": str(p.get("key") or p["id"]), "name": p["name"], "pos": pos, "team": p.get("team") or "FA", "own": own,
             "proj": round(proj, 1), "ros": ppg, "fc": p.get("val") if valued else None,
             "next": [x for _, x in p.get("wk") or []] if valued else [],
             "opp": "BYE" if p.get("bye") else p.get("opp"), "kick": p["kickoff"].isoformat() if p.get("kickoff") else None,
             "inj": p.get("status")}
        x = p.get("exp")   # ESPN experts' consensus position rank (shq/experts.py)
        if x:
            r.update({"exp_wk": x.get("wk"), "exp_lately": x.get("lately"),
                      **({"exp_range": [x["best"], x["worst"], x["n"]]} if x.get("n") else {})})
        (fas if own is None else rows).append(r)
    fas.sort(key=lambda r: -max(r["ros"] or 0, r["proj"]))
    rows += fas[:FA_KEEP]
    rank(rows, "ros")
    rank(rows, "proj")
    src = {"espn": "ESPN", "sleeper": "Sleeper", "yahoo": "Sleeper (Yahoo's own isn't readable yet)"}.get(getattr(league, "platform", ""), "the platform's")
    fc = getattr(league, "fc_settings", None) or {}
    partial = not getattr(league, "others", None)
    return {
        "kind": "nfl", "week": getattr(league, "week", None), "partial": partial, "dynasty": bool(fc.get("dynasty")), "players": sorted(rows, key=lambda r: -(r["ros"] or r["proj"])),
        "basis": f"This week: {src} projections in your league's scoring. Rest of season: Sleeper's projections for the next "
                 f"{values.ROS_WEEKS} weeks in your scoring, per game played (byes skipped; QB/RB/WR/TE; a week Sleeper hasn't "
                 "re-projected since a trade or new starting job uses his current weekly projection; IR players count 0 "
                 "for the 4-game IR minimum). Value: FantasyCalc "
                 + ("dynasty" if fc.get("dynasty") else "redraft") + " for your league's settings. Ranks are by position among "
                 "every rostered player and the best free agents. Experts: ESPN's fantasy analysts' consensus position rank "
                 "this week (their PPR ranks averaged; QB/RB/WR/TE) and lately (median of their last 3 weekly ranks, weeks he "
                 "was out or on a bye skipped); "
                 "green/red = they rank him 10+ spots (QB/TE 6+) better/worse than our this-week rank. "
                 "Which experts: ESPN's feed identifies each analyst only by a number, not a name (usually about 8 analysts), so Sports HQ can't show who ranked whom; tap a player to see how many ranked him and their best-to-worst range. ESPN's weekly rankings articles on espn.com name the panel. "
                 + (" Other teams' rosters aren't readable here yet (Yahoo API pending), so ranks are among your roster and "
                    "the free agents only." if partial else ""),
    }
