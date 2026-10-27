"""ESPN public site API: kickoff times, game state, injury designations."""
import re

from .common import get_json, parse_iso

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
TEAM_FIX = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR"}


def norm_team(abbr):
    a = (abbr or "").upper()
    return TEAM_FIX.get(a, a)


def games(season, week):
    """{team: {kickoff, state, opp, home, label}} for one regular-season week."""
    sb = get_json(f"{SITE}/scoreboard", {"seasontype": 2, "week": week, "dates": season})
    by_team = {}
    for ev in sb.get("events", []):
        comp = ev["competitions"][0]
        teams = {c["homeAway"]: norm_team(c["team"]["abbreviation"]) for c in comp["competitors"]}
        info = {"kickoff": parse_iso(ev["date"]), "state": ev["status"]["type"]["state"]}
        by_team[teams["home"]] = {**info, "opp": teams["away"], "home": True}
        by_team[teams["away"]] = {**info, "opp": teams["home"], "home": False}
    return by_team


def injuries(league="football/nfl"):
    """{espn_athlete_id: status string} e.g. 'Out', 'Questionable', 'Injured Reserve'."""
    out = {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/{league}/injuries"
    for team in get_json(url).get("injuries", []):
        for item in team.get("injuries", []):
            ath = item.get("athlete", {})
            aid = None
            for link in ath.get("links", []):
                m = re.search(r"/id/(\d+)", link.get("href", ""))
                if m:
                    aid = m.group(1)
                    break
            if aid:
                out[aid] = item.get("status")
    return out
