"""ntfy push alerts. Topic comes from the NTFY_TOPIC secret; dedup state lives in state/alerts.json."""
import datetime as dt
import os

from .common import STATE, iso, load_json, now_utc, save_json, session
from .config import SITE_URL

ALERTS = STATE / "alerts.json"
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


def push_once(key, title, message, **kw):
    """Push unless this exact alert key was already sent."""
    seen = load_json(ALERTS, {})
    if key in seen:
        return False
    push(title, message, **kw)
    seen[key] = iso(now_utc())
    cutoff = iso(now_utc() - dt.timedelta(days=21))
    save_json(ALERTS, {k: v for k, v in seen.items() if v >= cutoff})
    return True
