"""ESPN public site API: kickoff times, game state, injury designations."""
import re
import time

from .common import CACHE, get_json, load_json, parse_iso, save_json

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


def injury_report(league="football/nfl"):
    """{espn_athlete_id: {status, name, team, date, note, url}} from ESPN's public injury report. The
    note is the latest dated news blurb ESPN carries for him (Rotowire), url his ESPN player card."""
    out = {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/{league}/injuries"
    for team in get_json(url).get("injuries", []):
        for item in team.get("injuries", []):
            ath = item.get("athlete", {})
            for link in ath.get("links", []):
                m = re.search(r"/id/(\d+)", link.get("href", ""))
                if m:
                    out[m.group(1)] = {"status": item.get("status"), "name": ath.get("displayName"),
                                       "team": norm_team((ath.get("team") or {}).get("abbreviation")),
                                       "date": parse_iso(item["date"]) if item.get("date") else None,
                                       "note": item.get("shortComment") or "", "url": link["href"]}
                    break
    return out


NEWS_FILE = CACHE / "espn_player_news.json"
NEWS_MAX_AGE = 3600  # the run loops every 10 min; a headline used only as a citation can be an hour old


def player_news(espn_id, game="ffl"):
    """Latest ESPN fantasy news item for one player: {note, at} or None. Cached an hour per player so the
    10-minute game-day loop doesn't re-ask ESPN for the same headline six times an hour."""
    cache = load_json(NEWS_FILE, {}) or {}
    key = f"{game}:{espn_id}"
    hit = cache.get(key)
    if hit and time.time() - hit["t"] < NEWS_MAX_AGE:
        item = hit["item"]
    else:
        feed = get_json(f"https://site.api.espn.com/apis/fantasy/v2/games/{game}/news/players",
                        {"playerId": espn_id, "limit": 1}).get("feed") or []
        item = {"note": feed[0]["headline"], "published": feed[0].get("published")} if feed and feed[0].get("headline") else None
        cache = {k: v for k, v in cache.items() if time.time() - v["t"] < NEWS_MAX_AGE}
        cache[key] = {"t": time.time(), "item": item}
        save_json(NEWS_FILE, cache)
    if not item:
        return None
    return {"note": item["note"], "at": parse_iso(item["published"]) if item.get("published") else None}


def injuries(league="football/nfl"):
    """{espn_athlete_id: status string} e.g. 'Out', 'Questionable', 'Injured Reserve'."""
    return {aid: r["status"] for aid, r in injury_report(league).items()}
