"""Normalize injury designations from Sleeper, Yahoo and ESPN into one vocabulary."""

OUTISH = {"OUT", "IR", "PUP", "SUSP", "INACTIVE", "NA"}
SEVERITY = {None: 0, "Q": 1, "D": 2, "OUT": 3, "SUSP": 3, "PUP": 3, "NA": 3, "INACTIVE": 3, "IR": 4}

_MAP = {
    "questionable": "Q", "q": "Q", "day-to-day": "Q",
    "doubtful": "D", "d": "D",
    "out": "OUT", "o": "OUT", "dnr": "OUT",
    "ir": "IR", "ir-r": "IR", "injury_reserve": "IR", "day_to_day": "Q", "injured reserve": "IR", "ir-nr": "IR",
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


def worst(*sources):
    """Combine (source, raw) pairs → (status, 'Src: raw' explanation of the worst one)."""
    best, why = None, ""
    for src, raw in sources:
        s = norm(raw)
        if SEVERITY.get(s, 0) > SEVERITY.get(best, 0):
            best, why = s, f"{src}: {raw}"
    return best, why
