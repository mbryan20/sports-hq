"""Normalize injury designations from Sleeper, Yahoo and ESPN into one vocabulary."""

OUTISH = {"OUT", "IR", "PUP", "SUSP", "INACTIVE", "NA"}
SEVERITY = {None: 0, "Q": 1, "D": 2, "OUT": 3, "SUSP": 3, "PUP": 3, "NA": 3, "INACTIVE": 3, "IR": 4}

_MAP = {
    "questionable": "Q", "q": "Q", "day-to-day": "Q",
    "doubtful": "D", "d": "D",
    "out": "OUT", "o": "OUT", "dnr": "OUT",
    "ir": "IR", "ir-r": "IR", "ir-return": "IR", "injury_reserve": "IR", "day_to_day": "Q", "injured reserve": "IR", "ir-nr": "IR",
    "pup": "PUP", "pup-r": "PUP", "pup-p": "PUP", "physically unable to perform": "PUP",
    "nfi-r": "PUP", "nfi-a": "PUP", "non football injury": "PUP",
    "sus": "SUSP", "susp": "SUSP", "suspension": "SUSP", "suspended": "SUSP",
    "na": "NA", "inactive": "INACTIVE", "practice squad": "INACTIVE",
    "cov": "OUT", "covid-19": "OUT",
}


def norm(raw):
    if not raw:
        return None
    return _MAP.get(str(raw).strip().lower())


DEAD = OUTISH | {"D"}
GAME_ONLY = {"OUT", "D", "INACTIVE"}   # set for one game; IR/PUP/SUSP/NA last for weeks


def confirm(status, why, entry, week_start=None):
    """A status that would bench someone must be backed by ESPN's injury report, which carries a dated
    news note: ESPN lists him as out too and, for a one-game designation, the note is from this NFL week
    (week_start; None for NBA). Otherwise he's shown as Q with the disagreement spelled out, so nothing
    is benched or swapped on it. Returns (status, why, news, conflict)."""
    news = {"note": entry["note"], "at": entry["date"], "url": entry["url"]} if entry and entry.get("note") else None
    if status not in DEAD:
        return status, why, news, False
    espn = norm(entry["status"]) if entry else None
    current = espn not in GAME_ONLY or week_start is None or bool(entry.get("date") and entry["date"] >= week_start)
    if espn in DEAD and current:
        return status, why, news, False
    if not entry:
        reason = "not on ESPN's injury report"
    elif espn in DEAD:
        reason = f"ESPN's {entry['status']} is from last week"
    else:
        reason = f"ESPN says {entry['status']}"
    return "Q", f"{why}, but {reason}: unconfirmed", news, True


def worst(*sources):
    """Combine (source, raw) pairs → (status, 'Src: raw' explanation of the worst one)."""
    best, why = None, ""
    for src, raw in sources:
        s = norm(raw)
        if SEVERITY.get(s, 0) > SEVERITY.get(best, 0):
            best, why = s, f"{src}: {raw}"
    return best, why
