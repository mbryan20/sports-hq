"""ntfy push alerts. Topic comes from the NTFY_TOPIC secret; dedup state lives in state/alerts.json.

Dedup across runs (Q-049): a laptop kick and a cron loop can run passes side by side, each with its own checkout.
`seen()` is this checkout's state/alerts.json plus origin/main's (read fresh, only right before a real push), and
`.github/commit_data.sh` merges state/alerts.json key by key (shq/statemerge.py), so one run's commit never drops
another run's keys."""
import datetime as dt
import json
import os
import subprocess
import traceback

from .common import ROOT, STATE, iso, load_json, now_utc, save_json, session
from .config import SITE_URL

ALERTS = STATE / "alerts.json"
KEEP = dt.timedelta(days=21)
sent = []  # what this run pushed (or would have, in dry-run)


def push(title, message, priority=3, tags=None, click=None, actions=None, delay=None):
    """click: URL the notification opens (default the site); actions: ntfy view buttons; delay: e.g. "3m"."""
    sent.append({"title": title, "message": message, "click": click})
    topic = os.environ.get("NTFY_TOPIC")
    if os.environ.get("DRY_RUN") == "1" or not topic:
        print(f"[push skipped] {title}: {message}")
        return
    body = {"topic": topic, "title": title, "message": message,
            "priority": priority, "tags": tags or [], "click": click or SITE_URL}
    if actions:
        body["actions"] = actions
    if delay:
        body["delay"] = delay
    r = session.post("https://ntfy.sh/", json=body, timeout=20)
    r.raise_for_status()


def live():
    """True only where a push really goes out: GitHub Actions with a topic, not a dry run (never in tests)."""
    return (os.environ.get("GITHUB_ACTIONS") == "true" and bool(os.environ.get("NTFY_TOPIC"))
            and os.environ.get("DRY_RUN") != "1")


def origin_state(path="state/alerts.json"):
    """origin/main's copy of a state file ({} when it can't be read). Another run may have pushed (and committed)
    an alert after this checkout was made."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, timeout=60, check=True, capture_output=True)
        out = subprocess.run(["git", "show", f"origin/main:{path}"], cwd=ROOT, timeout=30, check=True,
                             capture_output=True, text=True, encoding="utf-8").stdout
        data = json.loads(out)
        return data if isinstance(data, dict) else {}
    except Exception:
        traceback.print_exc()
        return {}


def merge(*states):
    """Key-by-key union; a key in both keeps the later time (values are ISO times, so they sort as strings)."""
    out = {}
    for s in states:
        for k, v in (s or {}).items():
            if k not in out or str(v) > str(out[k]):
                out[k] = v
    return out


def _save(state):
    cutoff = iso(now_utc() - KEEP)
    save_json(ALERTS, {k: v for k, v in state.items() if str(v) >= cutoff})


def seen(fresh=False):
    """Alert keys already pushed: this checkout's; with `fresh` (just before a real push) also origin/main's, which
    are then kept here too so later passes don't fetch again."""
    local = load_json(ALERTS, {}) or {}
    if not (fresh and live()):
        return local
    both = merge(local, origin_state())
    if both != local:
        _save(both)
    return both


def mark(keys, when=None):
    """Record alert keys as sent (or a marker's time) without pushing. Keeps 21 days."""
    when = iso(when or now_utc())
    _save(merge(load_json(ALERTS, {}) or {}, {k: when for k in keys}))


def push_once(key, title, message, **kw):
    """Push unless this exact alert key was already sent (here or, just before a real push, on origin/main)."""
    if key in seen() or key in seen(fresh=True):
        return False
    push(title, message, **kw)
    mark([key])
    return True
