"""Cached HTTP for CFBD, ESPN and Open-Meteo. CFBD calls are budgeted (<900/month) and cached in cache/."""
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


def cfbd(endpoint, max_age_h=24 * 365, **params):
    """GET a CFBD endpoint. Served from cache when younger than max_age_h; offline-safe if no key."""
    url = CFBD_BASE + endpoint
    p = _path("cfbd", url, params)
    if p.exists() and (time.time() - p.stat().st_mtime) / 3600 < max_age_h:
        return json.loads(p.read_text(encoding="utf-8"))
    key = _key()
    ok, b, month = _budget_ok()
    if not key or not ok:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        raise RuntimeError(f"CFBD {endpoint} not cached and no key/budget")
    r = requests.get(url, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=60)
    b[month] = b.get(month, 0) + 1
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(b, indent=1))
    r.raise_for_status()
    data = r.json()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data


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
