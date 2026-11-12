"""Cached HTTP for CFBD, ESPN and Open-Meteo. CFBD calls are budgeted (<900/month) and cached in cache/.
When CFBD can't be called, saved copies of any age stand in (Q-055: the backup card has no CFBD key)."""
import hashlib, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
BUDGET_FILE = CACHE / "cfbd_calls.json"
CFBD_MONTHLY_CAP = 900
CFBD_BASE = "https://api.collegefootballdata.com"


def _key():
    k = os.environ.get("CFBD_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("CFBD_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _path(kind, url, params):
    h = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:16]
    return CACHE / kind / f"{h}.json"


def _budget_ok():
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    b = json.loads(BUDGET_FILE.read_text()) if BUDGET_FILE.exists() else {}
    return b.get(month, 0) < CFBD_MONTHLY_CAP, b, month


class CFBDUnavailable(RuntimeError):
    """CFBD couldn't be called (no key, no budget, HTTP error) and nothing was saved for this call.
    The message is plain words: the backup workflow's failure push quotes it. `why` = the reason alone."""

    def __init__(self, msg, why=None):
        super().__init__(msg)
        self.why = why


STALE = []  # [(endpoint, why, saved_at)] CFBD calls served from an out-of-date saved copy in this build


def saved_at(p):
    """When a cached file was saved, or None when unknown (a GitHub Actions checkout resets file times)."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)


def when(dt):
    """'Tue Nov 10, 03:10 PM CT', or 'an unknown time'."""
    if dt is None:
        return "an unknown time"
    from zoneinfo import ZoneInfo
    return dt.astimezone(ZoneInfo("America/Chicago")).strftime("%a %b %d, %I:%M %p CT")


def cfbd_cached(endpoint, **params):
    """(data, saved_at) from the saved copy of a CFBD call, any age; None when nothing is saved."""
    p = _path("cfbd", CFBD_BASE + endpoint, params)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")), saved_at(p)


def cfbd_why():
    """Why CFBD can't be called right now (no key / budget used up), or None if it can be tried."""
    if not _key():
        return "no CFBD API key is set"
    if not _budget_ok()[0]:
        return f"this month's CFBD call budget ({CFBD_MONTHLY_CAP}) is used up"
    return None


def cfbd(endpoint, max_age_h=24 * 365, **params):
    """GET a CFBD endpoint. Served from cache when younger than max_age_h. When CFBD can't be called (no key,
    monthly budget used up, or an HTTP/network error) a saved copy of any age is used and recorded in STALE;
    with no saved copy it raises CFBDUnavailable (plain words)."""
    url = CFBD_BASE + endpoint
    p = _path("cfbd", url, params)
    if p.exists() and (time.time() - p.stat().st_mtime) / 3600 < max_age_h:
        return json.loads(p.read_text(encoding="utf-8"))
    why = cfbd_why()
    if why is None:
        key = _key()
        _, b, month = _budget_ok()
        try:
            r = requests.get(url, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=60)
            b[month] = b.get(month, 0) + 1
            BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
            BUDGET_FILE.write_text(json.dumps(b, indent=1))
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # never let the message carry the key: requests errors name the URL, not headers
            why = f"CFBD didn't answer ({type(e).__name__}: {str(e)[:120]})"
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data), encoding="utf-8")
            return data
    if p.exists():
        STALE.append((endpoint, why, saved_at(p)))
        print(f"CFBD {endpoint} unavailable ({why}); using the copy saved {when(saved_at(p))}")
        return json.loads(p.read_text(encoding="utf-8"))
    raise CFBDUnavailable(f"CFBD {endpoint} unavailable ({why}) and no saved copy", why)


def get_json(kind, url, max_age_h=6, **params):
    """Unbudgeted public JSON (ESPN, Open-Meteo) with a cache fallback when offline."""
    p = _path(kind, url, params)
    if p.exists() and (time.time() - p.stat().st_mtime) / 3600 < max_age_h:
        return json.loads(p.read_text(encoding="utf-8"))
    err = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "pool-picks/1.0"})
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            err = e
            time.sleep(2 * (attempt + 1))
    else:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        raise err
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data
