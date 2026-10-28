"""Rest-of-season player values for trades and waiver adds. Free sources only, cached like the
Sleeper players dump (.cache, persisted by the Actions cache).

    fantasycalc(...)  FantasyCalc's public trade values, matched to the league's settings
                      (dynasty or redraft, 1QB or superflex, PPR level, team count)
    ros_projections   Sleeper's weekly projections for the next ROS_WEEKS weeks, so a player's
                      points per game isn't one week's projection (or zero on his bye)
    annotate(league)  puts "sid", "val" and "ppg" on every player the league knows about

NFL only: there is no free value source for basketball."""
import time

from .common import CACHE, get_json, load_json, save_json

FC_URL = "https://api.fantasycalc.com/values/current"
FC_MAX_AGE = 6 * 3600
ROS_FILE = CACHE / "sleeper_ros.json"
ROS_MAX_AGE = 6 * 3600
ROS_WEEKS = 4
LAST_WEEK = 17                  # fantasy regular season + playoffs
SKILL = ("QB", "RB", "WR", "TE")
# Sleeper stat keys worth keeping from the 2MB-a-week projections (everything any league scores on)
DROP_PREFIX = ("adp_", "pos_adp_", "pts_")

# ESPN scoringItems statId -> Sleeper stat key, for the offensive stats that decide a player's value
ESPN_STATS = {3: "pass_yd", 4: "pass_td", 19: "pass_2pt", 20: "pass_int", 24: "rush_yd", 25: "rush_td",
              26: "rush_2pt", 42: "rec_yd", 43: "rec_td", 44: "rec_2pt", 53: "rec", 72: "fum_lost"}
DEFAULT_SCORING = {"pass_yd": 0.04, "pass_td": 4, "pass_int": -2, "pass_2pt": 2, "rush_yd": 0.1, "rush_td": 6,
                   "rush_2pt": 2, "rec": 0.5, "rec_yd": 0.1, "rec_td": 6, "rec_2pt": 2, "fum_lost": -2}


def fantasycalc(dynasty, qbs, teams, ppr):
    """{sleeper_id: {"value", "redraft", "name", "pos"}} for one settings combo."""
    params = {"isDynasty": "true", "numQbs": qbs, "numTeams": teams, "ppr": ppr}
    path = CACHE / f"fantasycalc-{qbs}qb-{teams}t-{ppr}ppr.json"
    cached = load_json(path)
    if cached and time.time() - cached.get("_fetched", 0) < FC_MAX_AGE:
        return cached["values"]
    try:
        # the dynasty list carries redraftValue too and covers twice as many players as the redraft list
        rows = get_json(FC_URL, params)
    except Exception:
        if cached:
            return cached["values"]
        raise
    out = {}
    for r in rows:
        p = r.get("player") or {}
        if p.get("sleeperId") and p.get("position") in SKILL:
            out[p["sleeperId"]] = {"value": r.get("value") or 0, "redraft": r.get("redraftValue") or 0,
                                   "name": p.get("name"), "pos": p.get("position"), "espn": p.get("espnId")}
    save_json(path, {"_fetched": time.time(), "params": params, "values": out})
    return out


def _slim(rows):
    stats, teams = {}, set()
    for r in rows:
        s = r.get("stats") or {}
        if not s.get("gp"):
            continue
        if r.get("team"):
            teams.add(r["team"])
        keep = {k: v for k, v in s.items() if v and not k.startswith(DROP_PREFIX) and isinstance(v, (int, float))}
        if keep:
            stats[r["player_id"]] = keep
    return {"stats": stats, "teams": sorted(teams)}


def ros_projections(season, week):
    """{"weeks": {week: {"stats": {pid: stats}, "teams": [teams playing]}}} for week..week+ROS_WEEKS-1."""
    want = [w for w in range(week, week + ROS_WEEKS) if w <= LAST_WEEK] or [week]
    cached = load_json(ROS_FILE)
    if cached and cached.get("key") == [season, week] and time.time() - cached.get("_fetched", 0) < ROS_MAX_AGE:
        return cached
    weeks = {}
    try:
        for w in want:
            rows = get_json(f"https://api.sleeper.app/projections/nfl/{season}/{w}",
                            [("season_type", "regular")] + [("position[]", p) for p in SKILL])
            weeks[str(w)] = _slim(rows)
    except Exception:
        if cached:
            return cached
        raise
    out = {"_fetched": time.time(), "key": [season, week], "weeks": weeks}
    save_json(ROS_FILE, out)
    return out


def ros_ppg(ros, sid, team, scoring):
    """Projected points per game over the ROS window. Byes don't count as games; weeks a healthy
    player isn't projected (injured) count as zero."""
    from .leagues import score
    if not sid or not team:
        return 0.0
    total, games = 0.0, 0
    for wk in ros["weeks"].values():
        if team not in wk["teams"]:
            continue
        games += 1
        total += score(wk["stats"].get(sid), scoring)
    return round(total / games, 1) if games else 0.0


def espn_scoring(items):
    """Sleeper-keyed points for the main offensive stats in ESPN's settings.scoringSettings.scoringItems
    (LAPTOP_SNAPSHOT_JS does the same in the browser)."""
    return {ESPN_STATS[it["statId"]]: it.get("points", 0) for it in items or [] if it.get("statId") in ESPN_STATS}


def fc_settings(slots, teams, scoring):
    qbs = 2 if any(s in ("SUPER_FLEX", "OP", "Q/W/R/T") for s in slots) or slots.count("QB") > 1 else 1
    ppr = scoring.get("rec", 0)
    return qbs, int(teams or 12), (1 if ppr >= 0.75 else 0.5 if ppr >= 0.25 else 0)


def players_of(league):
    out = list(league.starters) + list(league.bench) + list(league.free_agents)
    for t in getattr(league, "others", None) or []:
        out += t["players"]
    return out


def annotate(league):
    """Fill sid/val/ppg on every player. Returns False for leagues this can't value (NBA, no context)."""
    ctx = getattr(league, "ctx", None)
    if getattr(league, "sport", "nfl") != "nfl" or ctx is None or not hasattr(ctx, "ros") or not getattr(league, "slots", None):
        return False
    if getattr(league, "_valued", False):
        return True
    scoring = league.value_scoring() if hasattr(league, "value_scoring") else league.scoring
    qbs, teams, ppr = fc_settings(league.slots, getattr(league, "team_count", 12), scoring)
    dynasty = bool(getattr(league, "dynasty", False))
    fc = fantasycalc(dynasty, qbs, teams, ppr)
    ros = ctx.ros()
    espn_map = {}
    if league.platform == "espn":  # Sleeper's DB lacks many ESPN ids; FantasyCalc carries both
        espn_map = {**ctx.espn_to_sleeper(), **{str(v["espn"]): sid for sid, v in fc.items() if v.get("espn")}}
    for p in players_of(league):
        sid = p["id"]
        if league.platform == "espn":
            pos = next((x for x in p["positions"] if x in SKILL), None)
            sid = espn_map.get(str(p["key"])) or (ctx.match(p["name"], p["team"], pos) if pos and hasattr(ctx, "match") else None)
        team = (ctx.players.get(sid or "") or {}).get("team")
        v = fc.get(sid or "") or {}
        p["sid"] = sid
        p["val"] = v.get("value" if dynasty else "redraft", 0)
        p["ppg"] = ros_ppg(ros, sid, team, scoring)
    league.fc_settings = {"dynasty": dynasty, "qbs": qbs, "teams": teams, "ppr": ppr}
    league._valued = True
    return True
