"""Sleeper public API (read-only)."""
import time

from .common import CACHE, get_json, load_json, save_json

BASE = "https://api.sleeper.app/v1"
PLAYERS_FILE = CACHE / "sleeper_players.json"
PLAYERS_MAX_AGE = 6 * 3600  # Sleeper asks that the 5MB players dump be pulled sparingly
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
KEEP = ("full_name", "first_name", "last_name", "position", "fantasy_positions", "team",
        "injury_status", "status", "yahoo_id", "espn_id")


def state():
    return get_json(f"{BASE}/state/nfl")


def players():
    """Slim copy of the full players DB, refreshed at most every 6h (persisted via Actions cache)."""
    cached = load_json(PLAYERS_FILE)
    if cached and time.time() - cached.get("_fetched", 0) < PLAYERS_MAX_AGE:
        return cached["players"]
    try:
        raw = get_json(f"{BASE}/players/nfl")
    except Exception:
        if cached:
            return cached["players"]
        raise
    slim = {}
    for pid, p in raw.items():
        if p.get("position") not in POSITIONS:
            continue
        q = {k: p.get(k) for k in KEEP if p.get(k) is not None}
        if p.get("position") == "DEF":
            q["full_name"] = f"{p.get('first_name', pid)} {p.get('last_name', '')}".strip()
        slim[pid] = q
    save_json(PLAYERS_FILE, {"_fetched": time.time(), "players": slim})
    return slim


def projections(season, week):
    """{player_id: {stats, player, opponent, team}} — includes Sleeper's live injury_status."""
    params = [("season_type", "regular")] + [("position[]", p) for p in POSITIONS]
    rows = get_json(f"https://api.sleeper.app/projections/nfl/{season}/{week}", params)
    return {r["player_id"]: r for r in rows}


def find_league(username, team_name, season):
    """Locate the league where this user's team carries `team_name`."""
    user = get_json(f"{BASE}/user/{username}")
    uid = user["user_id"]
    for lg in get_json(f"{BASE}/user/{uid}/leagues/nfl/{season}"):
        users = get_json(f"{BASE}/league/{lg['league_id']}/users")
        me = next((u for u in users if u["user_id"] == uid), None)
        if me and (me.get("metadata") or {}).get("team_name", "").strip().lower() == team_name.lower():
            return lg, uid, users
    raise RuntimeError(f"No Sleeper league with team '{team_name}' for {username}")


def league_by_id(username, league_id):
    uid = get_json(f"{BASE}/user/{username}")["user_id"]
    return get_json(f"{BASE}/league/{league_id}"), uid, get_json(f"{BASE}/league/{league_id}/users")


def rosters(league_id):
    return get_json(f"{BASE}/league/{league_id}/rosters")


def matchups(league_id, week):
    return get_json(f"{BASE}/league/{league_id}/matchups/{week}")
