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
stale row or a zero, and his team always comes from Sleeper's live data. That fill never applies to this week (no live
projection = 0), to a player any source tags Doubtful/Out/IR/PUP/SUSP (even when status.confirm shows him as Q), or to a
QB's week where Sleeper projects a hurt teammate back as the starter. A player on IR scores 0 for the games left on the
IR minimum (IR_MIN_GAMES), counted from the first run that saw him on IR (state/ir_seen.json), never while Sleeper
projects him to play this week.

NFL only: there is no free value source for basketball."""
import datetime as dt
import time

from .common import CACHE, STATE, get_json, iso, load_json, now_utc, parse_iso, save_json
from .espn import norm_team
from .status import DEAD, worst

FC_URL = "https://api.fantasycalc.com/values/current"
FC_MAX_AGE = 6 * 3600
ROS_FILE = CACHE / "sleeper_ros.json"
ROS_MAX_AGE = 6 * 3600
ROS_WEEKS = 4
ROS_FORMAT = 2                  # bump when the cached shape changes (2: per-player row team, "team_of")
IR_MIN_GAMES = 4                # NFL injured reserve: out at least four games
IR_SEEN = STATE / "ir_seen.json"  # {player: {"last", "first", "placed"}}: when each IR stint was first seen (committed)
IR_FRESH_DAYS = 7               # first sighting: IR news this recent marks a new placement; older, the minimum is served
IR_STINT_GAP_DAYS = 10          # not seen on IR for this long: a later IR tag starts a new stint
IR_KEEP_DAYS = 60               # records not seen for this long are dropped
QB_ROOM_SHARE = 0.6             # a hurt teammate QB projected at this share of the fill or more is that week's starter
STARTER_PASS_YD = 100           # a projected starter passes for at least this many yards
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
    projection count as `fill` when given (a number, or {week: number or None}), else zero (see ros_weeks)."""
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
    (his current per-game number, or a {week: number or None} map from week_fills) when given; the first
    `ir_games` games he'd play count as 0 (IR minimum)."""
    from .leagues import score
    out = []
    for w in sorted(ros["weeks"], key=int):
        wk = ros["weeks"][w]
        f = fill.get(str(w)) if isinstance(fill, dict) else fill
        if not sid or not team or team not in wk["teams"]:
            out.append((int(w), None))
        elif ir_games > 0:
            ir_games -= 1
            out.append((int(w), 0.0))
        elif f is not None and _stale(wk, sid, team):
            out.append((int(w), f))
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


def live_points(live_row, team, scoring):
    """This week's live Sleeper projection when it's for his current team (0 when the row projects no game),
    else None."""
    from .leagues import score
    lr = live_row or {}
    if not lr or not team or lr.get("team") != team:
        return None
    return score(lr["stats"], scoring) if (lr.get("stats") or {}).get("gp") else 0.0


def _when(at):
    at = parse_iso(at) if isinstance(at, str) else at
    if isinstance(at, dt.datetime) and at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)
    return at if isinstance(at, dt.datetime) else None


def load_ir_seen(path=None):
    data = load_json(path or IR_SEEN) or {}
    return data if isinstance(data, dict) else {}


def save_ir_seen(seen, now, path=None):
    """Write the IR records, dropping ones not seen for IR_KEEP_DAYS. Each value starts with "last" so
    shq.statemerge (which keeps the larger value per key) keeps the most recently seen record."""
    cut = (now - dt.timedelta(days=IR_KEEP_DAYS)).date().isoformat()
    save_json(path or IR_SEEN, {k: v for k, v in sorted(seen.items()) if str(v.get("last") or "") >= cut})


def ir_placed(seen, key, p, now, playing=False):
    """When his current IR stint began, updating `seen` (state/ir_seen.json). The first run that sees his IR tag
    records it: IR news from the last IR_FRESH_DAYS (and Sleeper not projecting him this week) marks a new placement
    at the news date; otherwise he has been on IR since before tracking began and the minimum is taken as served
    (None). ESPN's entry date is the latest blurb's, not the placement's, so it is only used at first sight.
    Returns (placed datetime or None, changed)."""
    today = now.date().isoformat()
    rec = seen.get(key)
    if isinstance(rec, dict) and rec.get("last"):
        try:
            gap = (now.date() - dt.date.fromisoformat(rec["last"])).days
        except ValueError:
            gap = IR_STINT_GAP_DAYS + 1
        if gap <= IR_STINT_GAP_DAYS:
            changed = rec["last"] != today
            if changed:
                seen[key] = {**rec, "last": today}
            return _when(rec.get("placed")), changed
    at = _when((p.get("news") or {}).get("at"))
    fresh = bool(at) and now - at <= dt.timedelta(days=IR_FRESH_DAYS) and not playing
    placed = min(at, now) if fresh else None
    seen[key] = {"last": today, "first": iso(now), "placed": iso(placed)}
    return placed, True


def ir_games_left(p, week_start, placed):
    """Games still covered by the IR minimum for a player whose IR tag is confirmed (status.confirm turns an
    unbacked one into Q), from the stint's placement (ir_placed; None = served). Each NFL week since counts as a
    game played out."""
    if p.get("status") != "IR" or placed is None:
        return 0
    if not week_start:
        return IR_MIN_GAMES
    missed = 0 if placed >= week_start else (week_start - placed).days // 7 + 1
    return max(0, IR_MIN_GAMES - missed)


def raw_status(p, ctx, sid, live_row):
    """His worst injury tag from any source before status.confirm softens an unbacked one to Q: the shown status,
    the tag it was decided from ("Sleeper: IR, but ESPN says ...: unconfirmed"), Sleeper's live row and players
    file, and ESPN's injury report."""
    db = (getattr(ctx, "players", None) or {}).get(sid or "") or {}
    first = (p.get("why") or "").split(", but ")[0]
    srcs = [("shown", p.get("status")), ("why", first.split(": ", 1)[-1] if ": " in first else None),
            ("Sleeper", ((live_row or {}).get("player") or {}).get("injury_status")),
            ("Sleeper", db.get("injury_status")),
            ("Sleeper", db.get("status") if db.get("status") not in (None, "Active") else None)]
    report = getattr(ctx, "espn_report", None) or {}
    eid = str(p.get("key") or "") if str(p.get("id") or "").startswith("espn") else str(db.get("espn_id") or "")
    entry = report.get(eid) if eid else None
    if entry:
        srcs.append(("ESPN", entry.get("status")))
    return worst(*srcs)[0]


def _qb_starter_back(ros, w, sid, team, fill, scoring, ctx, live):
    """Sleeper projects a teammate QB who is hurt now to start in week w, at QB_ROOM_SHARE of `fill` or more: the
    filling QB (Lock while Darnold is out, Cousins while Murray is) is his backup that week."""
    from .leagues import score
    wk = ros["weeks"][w]
    for pid, row_team in (wk.get("team_of") or {}).items():
        if pid == sid or row_team != team:
            continue
        st = wk["stats"].get(pid) or {}
        if (st.get("pass_yd") or 0) < STARTER_PASS_YD or score(st, scoring) < QB_ROOM_SHARE * fill:
            continue
        now_team = live_team(live.get(pid)) or ((getattr(ctx, "players", None) or {}).get(pid) or {}).get("team") or row_team
        if now_team == team and raw_status({}, ctx, pid, live.get(pid)):
            return True
    return False


def week_fills(ros, sid, team, scoring, fill, live_pts, is_qb, ctx=None, live=None, current=None):
    """{week: points for a week Sleeper left unprojected or projected for his old team; None = as Sleeper has it}.
    This week (`current`, else the window's first) takes his live projection only (none = 0). Later weeks take
    `fill` (None for a player who is out), except 0 in a QB's week where a hurt teammate is projected back as the
    starter."""
    weeks = sorted(ros["weeks"], key=int)
    cur = str(current) if current else (weeks[0] if weeks else None)
    out = {}
    for w in weeks:
        if int(w) < int(cur):
            out[w] = fill
        elif w == cur:
            out[w] = live_pts if live_pts is not None else 0.0
        elif fill is not None and is_qb and _qb_starter_back(ros, w, sid, team, fill, scoring, ctx, live or {}):
            out[w] = 0.0
        else:
            out[w] = fill
    return out


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
    now = getattr(ctx, "now", None) or now_utc()
    # IR records: a test context hands in its own dict; the real run (leagues.Context) reads and writes the state file
    from .leagues import Context, score
    persist = isinstance(ctx, Context)
    seen = getattr(ctx, "ir_seen", None)
    if seen is None:
        seen = load_ir_seen() if persist else {}
    seen_changed = False
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
        team = live_team(live_row) or (ctx.players.get(sid or "") or {}).get("team") or norm_team(p.get("team")) or None
        # fill eligibility from the raw tags: confirm can show an IR/Out player as Q, and Doubtful is out too
        out = raw_status(p, ctx, sid, live_row) in DEAD
        fill = per_game(ros, sid, team, scoring, live_row) if not out else None
        db = (getattr(ctx, "players", None) or {}).get(sid or "") or {}
        is_qb = "QB" in (p.get("positions") or []) or db.get("position") == "QB"
        fills = week_fills(ros, sid, team, scoring, fill, live_points(live_row, team, scoring), is_qb, ctx, live,
                           getattr(ctx, "week", None))
        ir = 0
        if p.get("status") == "IR":
            lr = live_row or {}
            playing = bool((lr.get("stats") or {}).get("gp")) and score(lr["stats"], scoring) > 0
            placed, ch = ir_placed(seen, sid or f"{league.platform}:{p.get('key') or p.get('id')}", p, now, playing)
            seen_changed |= ch
            # Sleeper projecting him to play this week beats any IR count (activation, or a short stint)
            ir = 0 if playing else ir_games_left(p, week_start, placed)
        v = fc.get(sid or "") or {}
        p["sid"] = sid
        p["val"] = v.get("value" if dynasty else "redraft", 0)
        p["ppg"] = ros_ppg(ros, sid, team, scoring, fills, ir)
        p["wk"] = ros_weeks(ros, sid, team, scoring, fills, ir)
    if persist and seen_changed:
        save_ir_seen(seen, now)
    league.fc_settings = {"dynasty": dynasty, "qbs": qbs, "teams": teams, "ppr": ppr}
    league._valued = True
    return True
