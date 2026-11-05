"""NBA players' birth dates from ESPN's public team rosters (30 small reads, cached a day). ESPN's fantasy player pool
has no age; the roster feed uses the same player ids. Used for dynasty drops (shq/nba_swaps.py) and the 3-Ball trade
checker's age curve."""
import datetime as dt
import time
import traceback

from .common import CACHE, get_json, load_json, save_json

ROSTER = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/roster"
FILE, MAX_AGE = CACHE / "nba_ages.json", 24 * 3600
TEAMS = range(1, 31)


def birth_dates():
    """{espn id: "YYYY-MM-DD"}; {} when ESPN can't be read (callers treat a missing age as unknown)."""
    hit = load_json(FILE)
    if hit and time.time() - hit["t"] < MAX_AGE and hit.get("born"):
        return hit["born"]
    born = {}
    for team in TEAMS:
        try:
            for a in get_json(ROSTER.format(team)).get("athletes") or []:
                if a.get("dateOfBirth"):
                    born[str(a["id"])] = a["dateOfBirth"][:10]
        except Exception:
            traceback.print_exc()
    if born:
        save_json(FILE, {"t": time.time(), "born": born})
    return born or (hit or {}).get("born") or {}


def age(born, on):
    """Age in years (one decimal) on a date, or None."""
    if not born:
        return None
    return round((on - dt.date.fromisoformat(born)).days / 365.25, 1)
