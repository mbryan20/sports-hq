import datetime as dt
import json
import time
from pathlib import Path

import requests

from .config import TZ

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"   # published on the site
STATE = ROOT / "state"          # committed, not published
CACHE = ROOT / ".cache"         # Actions cache only

session = requests.Session()
session.headers["User-Agent"] = "sports-hq/1.0 (+github actions)"


def get_json(url, params=None, tries=3, **kw):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=30, **kw)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if i == tries - 1 or (status and status < 500 and status != 429):
                raise
            time.sleep(2 * (i + 1))


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=False, default=str), encoding="utf-8")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def parse_iso(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(d):
    return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if d else None


def ct_label(d):
    """'Sun 12:00p' in Central time."""
    if not d:
        return ""
    local = d.astimezone(TZ)
    h = local.strftime("%I").lstrip("0")
    return f"{local.strftime('%a')} {h}:{local.strftime('%M')}{local.strftime('%p')[0].lower()}"
