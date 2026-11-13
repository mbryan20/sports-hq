"""Free baseball data reads for Sports HQ, cached outside git. No AI, no paid APIs, no sign-in.

Sources (terms and limits in plans/baseball.md, "Data sources"):
- MLB Stats API (statsapi.mlb.com): MLB and minor-league season stats with age, rosters (40-man), transactions.
  MLBAM's notice allows individual, non-commercial, non-bulk use; we read season aggregates, a few calls a day.
- Baseball Savant search (baseballsavant.mlb.com/statcast_search/csv, group_by=name): per-player Statcast aggregates
  (wOBA, xwOBA, barrels, velocity, spin) for any date range. One CSV per call; we cache and pause between calls.
- ESPN fantasy API (public 3-Ball league): % rostered, rosters, transactions.

Raw responses go to .cache/mlb/ (gitignored) and are re-read from there; only summaries are committed.
A cached file is reused for `max_age` hours (None = forever: finished seasons and closed date ranges don't change)."""
import csv
import hashlib
import io
import json
import time
import urllib.parse

import requests

from .common import ROOT

CACHE = ROOT / ".cache" / "mlb"
UA = {"User-Agent": "Mozilla/5.0 (sports-hq personal fantasy research)"}
STATS = "https://statsapi.mlb.com/api/v1"
SAVANT = "https://baseballsavant.mlb.com/statcast_search/csv"
PAUSE = 2.0          # seconds between live Savant calls (no published limit; be polite)
SPORT = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "Rk"}
_last = [0.0]


def _cached(key, fetch, max_age=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".txt")
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age * 3600):
        return path.read_text(encoding="utf-8")
    text = fetch()
    path.write_text(text, encoding="utf-8")
    return text


def stats_api(path, params=None, max_age=None):
    """JSON from the MLB Stats API, cached."""
    url = STATS + path + ("?" + urllib.parse.urlencode(params) if params else "")

    def fetch():
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        return r.text
    return json.loads(_cached(url, fetch, max_age))


def season_stats(season, group, sport_id, max_age=None, league_id=None):
    """Every player's regular-season line at one level: [{id, name, age, team, pos, birth, draft, stat...}].
    league_id narrows a sport (Arizona Fall League = sport 17, league 119)."""
    rows, offset = [], 0
    while True:
        q = {"stats": "season", "group": group, "sportId": sport_id, "season": season, "playerPool": "ALL",
             "gameType": "R", "limit": 1000, "offset": offset, "hydrate": "person"}
        if league_id:
            q["leagueIds"] = league_id
        d = stats_api("/stats", q, max_age)
        block = (d.get("stats") or [{}])[0]
        splits = block.get("splits") or []
        for s in splits:
            p, st = s.get("player") or {}, s.get("stat") or {}
            rows.append({"id": p.get("id"), "name": p.get("fullName"), "age": st.get("age"),
                         "birth": p.get("birthDate"), "draft": p.get("draftYear"),
                         "pos": (s.get("position") or p.get("primaryPosition") or {}).get("abbreviation"),
                         "team": (s.get("team") or {}).get("name"), "team_id": (s.get("team") or {}).get("id"),
                         "level": SPORT.get(sport_id, str(sport_id)), "sport": sport_id, **st})
        offset += len(splits)
        if not splits or offset >= block.get("totalSplits", 0):
            return rows


def savant(player_type, start, end, extra=None, max_age=None):
    """Per-player Statcast aggregates for regular-season games from `start` to `end` (YYYY-MM-DD, inclusive)."""
    q = {"all": "true", "hfGT": "R|", "hfSea": start[:4] + "|", "player_type": player_type,
         "game_date_gt": start, "game_date_lt": end, "group_by": "name", "min_pitches": 0, "min_results": 0,
         "min_pas": 0, "sort_col": "pitches", "sort_order": "desc"}
    q.update(extra or {})
    url = SAVANT + "?" + urllib.parse.urlencode(q)

    def fetch():
        wait = PAUSE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        r = requests.get(url, headers=UA, timeout=180)
        _last[0] = time.time()
        r.raise_for_status()
        return r.content.decode("utf-8-sig")
    out = []
    for row in csv.DictReader(io.StringIO(_cached(url, fetch, max_age))):
        out.append({k: _num(v) for k, v in row.items()})
    return out


def pipeline(year, max_age=None):
    """MLB Pipeline Top 100 for a year: {MLBAM person id: rank}. Ranks only (facts); no scouting text is kept.
    Read from the public page www.mlb.com/milb/prospects/<year>/top100 (robots.txt allows /milb/)."""
    import html
    import re
    url = f"https://www.mlb.com/milb/prospects/{year}/top100"

    def fetch():
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        page = html.unescape(r.text)
        found = re.findall(r'"RankedPlayerEntity","rank":(\d+),.*?"player":\{"__ref":"Person:(\d+)"\}', page)
        return json.dumps({pid: int(rank) for rank, pid in found})
    return {int(k): v for k, v in json.loads(_cached(url, fetch, max_age)).items()}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v
