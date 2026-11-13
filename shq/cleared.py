"""Cleared Fix now lines (Nov 12, Michael: "Need the ability to clear items like this on fix now").

A league page's Fix now line has a Clear button (docs/lib/core.js). It hides the line on that device at once and
opens a pre-filled GitHub issue labelled "clear" ("Clear: <league>: <line>", body: the line, then "League: <name>").
.github/workflows/clear.yml records it here in docs/data/cleared.json; every build then leaves that line out of the
league page's Fix now, the Today check and the texts (digest.league_items), on every device, until it expires.

A line is matched by its key: the problem part only (before " → ", without the dated ESPN note), letters only, so a
new projection or a refreshed note doesn't bring it back, but a changed status ("Out" → "Questionable") does.

    python -m shq.cleared record      issue text from ISSUE_TITLE / ISSUE_BODY / ISSUE_NUMBER / ISSUE_CREATED
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEARED = ROOT / "docs" / "data" / "cleared.json"
DAYS = 7              # a cleared line comes back after a week even if it never changes
CITE = re.compile(r"\s*\[ESPN[^\]]*\]")


def key(text):
    """The part of a line that names the problem, letters only (same rule as clearKey in docs/lib/core.js)."""
    t = CITE.sub("", str(text or "")).split(" → ")[0].lower()
    return re.sub(r"[^a-z]+", " ", t).strip()


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def load(path=CLEARED):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_cache = {}


def active(now, path=CLEARED):
    """{(league, key)} cleared and not yet expired. Read once per run."""
    if path not in _cache:
        _cache[path] = load(path).get("items") or []
    return {(i.get("league"), i.get("key")) for i in _cache[path]
            if (_when(i.get("until")) or now) > now and i.get("key")}


def is_cleared(league, text, now, path=CLEARED):
    return (league, key(text)) in active(now, path)


def drop(league, items, now, path=CLEARED):
    """Items (digest dicts) without the ones he cleared."""
    gone = active(now, path)
    if not gone:
        return items
    return [i for i in items if (league, key(i["text"])) not in gone]


def parse(title, body, number=None, created=None):
    """{"issue", "league", "text", "key"} from the issue the Clear button opened, or None."""
    body = (body or "").replace("\r\n", "\n")
    head, _, meta = body.partition("\n---\n")
    m = re.search(r"^League: (.+)$", meta, re.M)
    lg = m.group(1).strip() if m else None
    if not lg:
        t = re.match(r"Clear: ([^:]+): ", title or "")
        lg = t.group(1).strip() if t else None
    text = head.strip()
    if not lg or not key(text):
        return None
    return {"issue": int(number) if number else None, "league": lg, "text": text[:600], "key": key(text), "asked": created}


def record(item, now, path=CLEARED):
    """Add one cleared line (replacing an earlier clear of the same line) and drop expired ones."""
    data = load(path)
    keep = [i for i in data.get("items") or []
            if (_when(i.get("until")) or now) > now and (i.get("league"), i.get("key")) != (item["league"], item["key"])]
    row = {"league": item["league"], "key": item["key"], "text": item["text"], "cleared": _iso(now),
           "until": _iso(now + timedelta(days=DAYS)), "issue": item.get("issue")}
    data = {"updated": _iso(now), "items": [row] + keep}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    _cache.pop(path, None)
    return row


def main(argv):
    if argv[:1] == ["record"]:
        e = os.environ
        item = parse(e.get("ISSUE_TITLE", ""), e.get("ISSUE_BODY", ""), e.get("ISSUE_NUMBER"), e.get("ISSUE_CREATED"))
        if not item:
            print("not a Clear issue (no league or line)")
            return 1
        row = record(item, datetime.now(timezone.utc))
        print(f"cleared under {row['league']} until {row['until']}: {row['key']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
