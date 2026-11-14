"""Moves Michael skipped on HQ's fantasy cards (HQ "fantasy live sync", approved by Michael Nov 14: "Yes, build it").

docs/data/decisions.json is a list written by HQ's Go runner after he taps Skip on HQ card `fantasy` or `fantasy-nba`:
    [{"id", "sport", "app", "league", "move", "reason", "until"?, "at"}]
reason is a code only (the repo is public; his own words stay in HQ): bad | handled | notworth | notnow | other.
An empty or missing file means no skips. Every build reads it once. A move that matches an entry:
  - is left out of the league page's Fix now, Lineup moves and Waiver adds, the Weekly start/sit, the Today check and
    the texts, so the next-best move takes its place;
  - is listed on the league page under "You skipped" as "You skipped this (<reason>, <date>)";
  - comes back only when `until` has passed or the entry is removed (an undo in HQ removes it).

MATCHING RULE (HQ writes `move` so it matches; same rule both sides):
  league: Sports HQ's league name, case and spaces ignored ("Sunday's Best", "Kosmonauts", "3-Ball FB", ...).
  move:   reduced to a key, the action plus the players, so numbers, slots, times and reasons never matter:
    1. lowercase; drop anything in (...) or [...]; cut at the first " → ", ": ", " — ", ", +", " before ", "; ".
    2. "start A over B ..." / "play A over B"            -> "start|a|b"
       "add A for B" / "add A, drop B" / "add A and drop B" / "drop B, add A" / "drop B for A" / "drop B and add A"
                                                         -> "add|a|b"
       a Fix now line "B ... → start A"                   -> "start|a|b"
       an NBA swap "First move X out of IR (...); then drop B (...), add A (...)" -> "add|a|b"
       anything else                                     -> its words (step 1 text, letters and spaces)
    3. names: letters only, without a trailing Jr/Sr/II/III/IV/V.
  Example: "start Devaughn Vele over Kaelon Black at SUPER_FLEX" and Sports HQ's
  "Start Devaughn Vele (9.1) over Kaelon Black (6.0) at SUPER_FLEX, +3.1" are both "start|devaughnvele|kaelonblack".
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "docs" / "data" / "decisions.json"
REASONS = {"bad": "Bad advice", "handled": "Already handled", "notworth": "Not worth it", "notnow": "Not now", "other": "Skipped"}
CUTS = re.compile(r" → |: | — | -- |, \+|\bbefore\b|; ")
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$")


def _name(s):
    return re.sub(r"[^a-z]", "", SUFFIX.sub("", s.strip().lower().rstrip(".")))


def _words(s):
    return re.sub(r"[^a-z]+", " ", s).strip()


def move_key(text):
    """The action and players a move names (see MATCHING RULE)."""
    raw = str(text or "").lower()
    fix = None
    if " → " in raw:                                     # Fix now: "<problem player> (SLOT) is Out → start <bench player>"
        head, _, tail = raw.partition(" → ")
        m = re.match(r"\s*(?:start|play) (.+?)(?: \(| at |,|$)", tail)
        who = re.match(r"\s*(.+?) \(", head)
        if m and who:
            fix = f"start|{_name(m.group(1))}|{_name(who.group(1))}"
    if fix:
        return fix
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", raw)
    t = re.sub(r"^\s*first move .+?; then ", "", t)        # NBA swap after an IR fix: the swap is the move
    t = CUTS.split(t)[0]
    t = re.sub(r"\s+", " ", t).strip(" .,")
    m = re.match(r"(?:start|play) (.+?) over (.+?)(?: at .*)?$", t)
    if m:
        return f"start|{_name(m.group(1))}|{_name(m.group(2))}"
    m = (re.match(r"add (.+?)(?:,| and)? (?:drop|for) (.+)$", t) or re.match(r"(?:pick up|claim) (.+?)(?:,| and)? drop (.+)$", t))
    if m:
        return f"add|{_name(m.group(1))}|{_name(m.group(2))}"
    m = re.match(r"drop (.+?)(?:,| and)? (?:add|for) (.+)$", t)
    if m:
        return f"add|{_name(m.group(2))}|{_name(m.group(1))}"
    return _words(t)


def _league(s):
    return re.sub(r"\s+", "", str(s or "").lower())


def _when(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load(path=None):
    try:
        d = json.loads(Path(path or DECISIONS).read_text(encoding="utf-8"))
    except Exception:
        return []
    return [e for e in (d if isinstance(d, list) else d.get("items") or []) if isinstance(e, dict) and e.get("league") and e.get("move")]


_cache = {}


def active(now, path=None):
    """{(league, move key): entry} for skips still in force. The file is read once per run."""
    path = path or DECISIONS
    if path not in _cache:
        _cache[path] = load(path)
    out = {}
    for e in _cache[path]:
        until = _when(e.get("until")) if e.get("until") else None
        if until and until <= now:
            continue
        out[(_league(e["league"]), move_key(e["move"]))] = e
    return out


def skipped(league, text, now, path=None):
    """The skip entry this line matches, or None."""
    return active(now, path).get((_league(league), move_key(text))) if text else None


def tag(e):
    """'You skipped this (Not worth it, Nov 14)' for an entry."""
    at = _when(e.get("at"))
    day = f"{at:%b} {at.day}" if at else ""
    return f"You skipped this ({REASONS.get(e.get('reason'), 'Skipped')}{', ' + day if day else ''})"


def split(league, lines, now, get=lambda x: x, path=None):
    """(lines to show, [{"text", "tag", "reason", "at", "until"}] for the ones he skipped)."""
    keep, gone = [], []
    for x in lines or []:
        e = skipped(league, get(x), now, path)
        if e:
            gone.append({"text": get(x), "tag": tag(e), "reason": e.get("reason"), "at": e.get("at"), "until": e.get("until")})
        else:
            keep.append(x)
    return keep, gone


def note(league_obj, gone):
    """Collect skipped lines on the league object for the page (advice["skipped"]), without repeats."""
    have = getattr(league_obj, "skipped", None)
    if have is None:
        have = []
        try:
            league_obj.skipped = have
        except AttributeError:
            return
    for g in gone:
        if all(g["text"] != h["text"] for h in have):
            have.append(g)
