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
NEWS_ITEMS = 5       # ESPN's player feed mixes multi-player roundups in with the player's own notes
NOTE_MAX = 1500      # a player note's story is a paragraph; a roundup's runs to thousands of characters
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def last_name(name):
    """"Harold Fannin Jr." → "fannin"; "" without a name."""
    words = re.sub(r"[^a-z' -]", "", (name or "").lower()).replace("-", " ").split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return words[-1] if len(words) > 1 else ""


def about(item, name):
    """True when a feed item is this player's own news: a Rotowire-style player note, or a headline or a short story
    naming him by last name. A roundup that only mentions him deep in its story is not (Nov 10: "Fantasy buzz: Malik
    Willis placed on IR, are there any Dolphins you should start?" was cited for Rhamondre Stevenson and Garrett
    Wilson)."""
    last = last_name(name)
    named = lambda text: bool(last) and re.search(rf"\b{re.escape(last)}\b", (text or "").lower()) is not None
    if item.get("type") == "Rotowire":
        return not last or named(item.get("headline")) or named(item.get("story"))
    return named(item.get("headline")) or (len(item.get("story") or "") <= NOTE_MAX and named(item.get("story")))


def pick_news(feed, name=None):
    """The first item that is this player's own news (Rotowire notes first, then a headline naming him), or None."""
    feed = [f for f in feed or [] if f.get("headline")]
    hit = next((f for f in feed if f.get("type") == "Rotowire" and about(f, name)), None) \
        or next((f for f in feed if name and about(f, name)), None)
    return {"note": hit["headline"], "published": hit.get("published")} if hit else None


def player_news(espn_id, game="ffl", name=None):
    """Latest ESPN fantasy news item about one player (`name` checks it names him): {note, at} or None. Cached an
    hour per player so the 10-minute game-day loop doesn't re-ask ESPN for the same headline six times an hour."""
    cache = load_json(NEWS_FILE, {}) or {}
    key = f"own:{game}:{espn_id}"   # "own:": entries cached before the roundup filter are ignored
    hit = cache.get(key)
    if hit and time.time() - hit["t"] < NEWS_MAX_AGE:
        item = hit["item"]
    else:
        feed = get_json(f"https://site.api.espn.com/apis/fantasy/v2/games/{game}/news/players",
                        {"playerId": espn_id, "limit": NEWS_ITEMS}).get("feed") or []
        item = pick_news(feed, name)
        cache = {k: v for k, v in cache.items() if time.time() - v["t"] < NEWS_MAX_AGE}
        cache[key] = {"t": time.time(), "item": item}
        save_json(NEWS_FILE, cache)
    if not item:
        return None
    return {"note": item["note"], "at": parse_iso(item["published"]) if item.get("published") else None}


def injuries(league="football/nfl"):
    """{espn_athlete_id: status string} e.g. 'Out', 'Questionable', 'Injured Reserve'."""
    return {aid: r["status"] for aid, r in injury_report(league).items()}
