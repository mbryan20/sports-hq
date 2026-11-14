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
  league: Sports HQ's league name or the app's own league name, letters and digits only, case ignored. App names:
          "Sunday's Best" = Domo Arigato, "Damon's Guillotine League 2026" (any name with "guill") = Guillotine,
          "3-Ball Dynasty League" = 3-Ball FB (sport football) or 3-Ball BB (sport basketball),
          "Stempak Family and Friends 2026" = Stempak, "We playin basketball" = Ball is Life, his 3-Ball team name
          "Ragonk Force" = 3-Ball FB or 3-Ball BB by sport.
  move:   reduced to a key, the action plus the players, so numbers, slots, times and reasons never matter:
    1. lowercase; drop anything in (...) or [...]; cut at the first " → ", ": ", " — ", ", +", " before ", "; ".
    2. "start A over B ..." / "play A over B"            -> "start|a|b"
       "add A for B" / "add A, drop B" / "add A and drop B" / "drop B, add A" / "drop B for A" / "drop B and add A"
                                                         -> "add|a|b"
       a Fix now line "B ... → start A"                   -> "start|a|b"
       an NBA swap "First move X out of IR (...); then drop B (...), add A (...)" -> "add|a|b"
       "move A out of IR" / "move A from IR" / "activate A" (anything after, like ", dropping B") -> ir|A
       a name ends at ",", " and ", " then " or " to " ("drop B, add A, start him" -> add|A|B)
       "drop B, move A from IR ..." -> ir|A;  "move A to IR ..." -> toir|A
       a leading "optional:", "maybe:", "if needed:" or "before <time>:" is ignored
    FALLBACK: no key match, but every player the skip names (two or more: from its key, else its runs of capitalized
       words) appears in the line -> match. One-player skips (ir|A, toir|A) match by key only.
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


PREFIX = re.compile(r"^\s*(?:optional|maybe|if needed|before (?:[^:]*\d:\d\d[^:]*|[^:]+))\s*:\s*", re.I)


def _clean(raw):
    """Lowercased move text without (...)/[...], a leading "optional:"/"before ...:", or anything after the first cut."""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", raw)
    t = PREFIX.sub("", t)
    t = re.sub(r"^\s*first move .+?; then ", "", t)        # NBA swap after an IR fix: the swap is the move
    t = CUTS.split(t)[0]
    return re.sub(r"\s+", " ", t).strip(" .,")


STOP = {"add", "drop", "start", "sit", "bench", "move", "play", "claim", "pick", "up", "optional", "maybe", "before", "then",
        "him", "over", "for", "and", "at", "from", "to", "into", "ir", "dropping", "adding", "if", "a", "the", "is", "open",
        "slot", "activate"}


def names(text):
    """Players a move names (letters only), for the fallback: from its key, else from its runs of capitalized words."""
    k = move_key(text)
    if "|" in k:
        return [x for x in k.split("|")[1:] if x]
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(text or ""))
    t = PREFIX.sub("", t)
    out, run = [], []
    for w in re.findall(r"[A-Za-z][A-Za-z'.\-]*", t) + [""]:
        if w and (w[0].isupper() or (run and SUFFIX.match(" " + w.lower()))) and w.lower().strip(".") not in STOP:
            run.append(w)
            continue
        if len(run) >= 2:
            out.append(_name(" ".join(run)))
        run = []
    return out


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
    t = _clean(raw)
    m = re.match(r"(?:move|activate) (.+?)(?: (?:out of|from|off) (?:the )?ir\b.*|,.*| and .*)?$", t)
    if m and re.search(r" (?:out of|from|off) (?:the )?ir\b", t) or t.startswith("activate "):
        return f"ir|{_name(m.group(1))}" if m else _words(t)
    m = re.match(r"drop .+?(?:,| and)? (?:move|activate) (.+?) (?:out of|from|off) (?:the )?ir\b", t)   # "drop B, move A from IR"
    if m:
        return f"ir|{_name(m.group(1))}"
    m = re.match(r"move (.+?) (?:to|into) (?:the )?ir\b", t)                                          # "move A to IR if a slot is open"
    if m:
        return f"toir|{_name(m.group(1))}"
    m = re.match(r"(?:start|play) (.+?) over (.+?)(?: at .*|,.*| and .*| then .*)?$", t)
    if m:
        return f"start|{_name(m.group(1))}|{_name(m.group(2))}"
    m = (re.match(r"add (.+?)(?:,| and)? (?:drop|for) (.+?)(?:,| and | then | to |$)", t)
         or re.match(r"(?:pick up|claim) (.+?)(?:,| and)? drop (.+?)(?:,| and | then | to |$)", t))
    if m:
        return f"add|{_name(m.group(1))}|{_name(m.group(2))}"
    m = re.match(r"drop (.+?)(?:,| and)? (?:add|for|pick up|claim) (.+?)(?:,| and | then | to |$)", t)
    if m:
        return f"add|{_name(m.group(2))}|{_name(m.group(1))}"
    return _words(t)


# the apps' own league names -> Sports HQ's (lineups.json "league"); 3-Ball is one name for two sports
LEAGUE_ALIAS = {"sundaysbest": "domoarigato", "stempakfamilyandfriends2026": "stempak", "stempakfamilyandfriends": "stempak",
                "weplayinbasketball": "ballislife"}
SPORT = {"football": "fb", "nfl": "fb", "basketball": "bb", "nba": "bb"}


def _league(s, sport=None):
    k = re.sub(r"[^a-z0-9]", "", str(s or "").lower())
    if "guill" in k:
        return "guillotine"
    if (k.startswith("3balldynasty") or k == "ragonkforce") and SPORT.get(str(sport or "").lower()):   # his 3-Ball team name
        return "3ball" + SPORT[str(sport).lower()]
    return LEAGUE_ALIAS.get(k, k)


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
        out[(_league(e["league"], e.get("sport")), move_key(e["move"]))] = e
    return out


def skipped(league, text, now, path=None):
    """The skip entry this line matches, or None: the same key, or (fallback) every player the skip names (two or more)
    appears in the line."""
    if not text:
        return None
    act, lg = active(now, path), _league(league)
    hit = act.get((lg, move_key(text)))
    if hit:
        return hit
    flat = re.sub(r"[^a-z]", "", str(text).lower())
    for (l, _), e in act.items():
        ns = names(e["move"])
        if l == lg and len(ns) >= 2 and all(n and n in flat for n in ns):
            return e
    return None


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
