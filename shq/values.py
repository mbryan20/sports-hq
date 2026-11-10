"""Rest-of-season player values for trades and waiver adds. Free sources only, cached like the
Sleeper players dump (.cache, persisted by the Actions cache).

    fantasycalc(...)  FantasyCalc's public trade values, matched to the league's settings
                      (dynasty or redraft, 1QB or superflex, PPR level, team count)
    ros_projections   Sleeper's weekly projections for the next ROS_WEEKS weeks, so a player's
                      points per game isn't one week's projection (or zero on his bye)
    annotate(league)  puts "sid", "val" and "ppg" on every player the league knows about

Sleeper's later weeks lag behind trades and depth-chart changes (its week-after-next projections can carry a
traded player's old team, or nothing for a new starter), while this week's projection is rebuilt every run. So a
week projected for another team, or not projected at all, takes the player's live per-game number instead of the
stale row or a zero (unless he's out), and his team always comes from Sleeper's live data. A player on IR scores
0 for the games left on the IR minimum (IR_MIN_GAMES).

NFL only: there is no free value source for basketball."""
import time

from .common import CACHE, get_json, load_json, parse_iso, save_json
from .status import OUTISH

FC_URL = "https://api.fantasycalc.com/values/current"
FC_MAX_AGE = 6 * 3600
ROS_FILE = CACHE / "sleeper_ros.json"
ROS_MAX_AGE = 6 * 3600
ROS_WEEKS = 4
ROS_FORMAT = 2                  # bump when the cached shape changes (2: per-player row team, "team_of")
IR_MIN_GAMES = 4                # NFL injured reserve: out at least four games
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
    """One week: stats per player, the teams playing, and the team each projection was made for ("team_of"),
    so a projection made before a trade can be told apart from one for his current team."""
    stats, teams, team_of = {}, set(), {}
    for r in rows:
        s = r.get("stats") or {}
        if not s.get("gp"):
            continue
        if r.get("team"):
            teams.add(r["team"])
        keep = {k: v for k, v in s.items() if v and not k.startswith(DROP_PREFIX) and isinstance(v, (int, float))}
        if keep:
            stats[r["player_id"]] = keep
            if r.get("team"):
                team_of[r["player_id"]] = r["team"]
    return {"stats": stats, "teams": sorted(teams), "team_of": team_of}


def ros_projections(season, week):
    """{"weeks": {week: {"stats": {pid: stats}, "teams": [teams playing]}}} for week..week+ROS_WEEKS-1."""
    want = [w for w in range(week, week + ROS_WEEKS) if w <= LAST_WEEK] or [week]
    cached = load_json(ROS_FILE)
    if cached and cached.get("key") == [season, week, ROS_FORMAT] and time.time() - cached.get("_fetched", 0) < ROS_MAX_AGE:
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
    out = {"_fetched": time.time(), "key": [season, week, ROS_FORMAT], "weeks": weeks}
    save_json(ROS_FILE, out)
    return out


def live_team(row):
    """A player's current team from his row in Sleeper's live (this week's) projections: the embedded player
    record is current even when the row itself was projected for his old team."""
    row = row or {}
    return (row.get("player") or {}).get("team") or row.get("team") or None


def ros_ppg(ros, sid, team, scoring, fill=None, ir_games=0):
    """Projected points per game over the ROS window. Byes don't count as games; weeks with no usable
    projection count as `fill` when given, else zero (see ros_weeks)."""
    if not sid or not team:
        return 0.0
    pts = [x for _, x in ros_weeks(ros, sid, team, scoring, fill, ir_games) if x is not None]
    return round(sum(pts) / len(pts), 1) if pts else 0.0


# Some leagues (Stempak) score a stat per position: "points" is 0 and pointsOverrides holds
# {position id: points} (1 QB, 2 RB, 3 WR, 4 TE). Use the position the stat mostly belongs to.
HOME_POS = {"pass": "1", "rush": "2", "rec": "3", "fum": "2"}


def _points(it, key):
    ov = it.get("pointsOverrides") or {}
    pos = HOME_POS[key.split("_")[0]]
    if pos in ov:
        return ov[pos]
    return next(iter(ov.values())) if ov and not it.get("points") else it.get("points", 0)


def _stale(wk, sid, team):
    """No projection this week, or one made for a team he no longer plays for."""
    row_team = (wk.get("team_of") or {}).get(sid)
    return sid not in wk["stats"] or bool(row_team and row_team != team)


def ros_weeks(ros, sid, team, scoring, fill=None, ir_games=0):
    """[(week, projected points or None on a bye)] over the ROS window, in week order. `team` is his current
    team (byes follow it). A week whose projection is missing or was made for another team counts as `fill`
    (his current per-game number) when given; the first `ir_games` games he'd play count as 0 (IR minimum)."""
    from .leagues import score
    out = []
    for w in sorted(ros["weeks"], key=int):
        wk = ros["weeks"][w]
        if not sid or not team or team not in wk["teams"]:
            out.append((int(w), None))
        elif ir_games > 0:
            ir_games -= 1
            out.append((int(w), 0.0))
        elif fill is not None and _stale(wk, sid, team):
            out.append((int(w), fill))
        else:
            out.append((int(w), score(wk["stats"].get(sid), scoring)))
    return out


def per_game(ros, sid, team, scoring, live_row=None):
    """His current per-game projection, used for weeks Sleeper hasn't projected for his current team: this
    week's live projection when it's for his current team, else the average of his up-to-date weeks, else
    None (nothing to go on: those weeks stay 0)."""
    from .leagues import score
    if not sid or not team:
        return None
    lr = live_row or {}
    if (lr.get("stats") or {}).get("gp") and lr.get("team") == team:
        return score(lr["stats"], scoring)
    fresh = [score(wk["stats"][sid], scoring) for wk in ros["weeks"].values()
             if team in wk["teams"] and not _stale(wk, sid, team)]
    return round(sum(fresh) / len(fresh), 1) if fresh else None


def ir_games_left(p, week_start):
    """Games still covered by the IR minimum for a player whose IR tag is confirmed (status.confirm turns an
    unbacked one into Q). Placement is estimated from the date on ESPN's injury entry; each NFL week since
    counts as a game played out. Unknown date: the full minimum."""
    if p.get("status") != "IR":
        return 0
    at = (p.get("news") or {}).get("at")
    if isinstance(at, str):
        at = parse_iso(at)
    if not at or not week_start:
        return IR_MIN_GAMES
    missed = 0 if at >= week_start else (week_start - at).days // 7 + 1
    return max(0, IR_MIN_GAMES - missed)


def espn_scoring(items):
    """Sleeper-keyed points for the main offensive stats in ESPN's settings.scoringSettings.scoringItems
    (LAPTOP_SNAPSHOT_JS does the same in the browser)."""
    return {ESPN_STATS[it["statId"]]: _points(it, ESPN_STATS[it["statId"]])
            for it in items or [] if it.get("statId") in ESPN_STATS}


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
    live = getattr(ctx, "proj", None) or {}
    week_start = getattr(ctx, "week_start", None)
    espn_map = {}
    if league.platform == "espn":  # Sleeper's DB lacks many ESPN ids; FantasyCalc carries both
        espn_map = {**ctx.espn_to_sleeper(), **{str(v["espn"]): sid for sid, v in fc.items() if v.get("espn")}}
    for p in players_of(league):
        sid = p["id"]
        if league.platform == "espn":
            pos = next((x for x in p["positions"] if x in SKILL), None)
            sid = espn_map.get(str(p["key"])) or (ctx.match(p["name"], p["team"], pos) if pos and hasattr(ctx, "match") else None)
        # current team: Sleeper's live projections first (rebuilt every run), then the players file (cached
        # 6h, so a few hours behind on a trade), then the platform's own
        live_row = live.get(sid or "")
        team = live_team(live_row) or (ctx.players.get(sid or "") or {}).get("team") or p.get("team")
        healthy = p.get("status") not in OUTISH
        fill = per_game(ros, sid, team, scoring, live_row) if healthy else None
        ir = ir_games_left(p, week_start)
        v = fc.get(sid or "") or {}
        p["sid"] = sid
        p["val"] = v.get("value" if dynasty else "redraft", 0)
        p["ppg"] = ros_ppg(ros, sid, team, scoring, fill, ir)
        p["wk"] = ros_weeks(ros, sid, team, scoring, fill, ir)
    league.fc_settings = {"dynasty": dynasty, "qbs": qbs, "teams": teams, "ppr": ppr}
    league._valued = True
    return True
