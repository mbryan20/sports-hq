"""Game-day NBA status from two free sources, merged into each NBA player's ESPN status (Q-058). Pure reads, no AI.

Sources (both read lightly, cached in .cache, and never allowed to fail a run: a source that's down counts as silent):
- The NBA's official injury report: the season's index page on official.nba.com links one PDF per update (about every
  15 minutes on game days). The newest PDF is parsed into rows (game date, team, player, status, reason). A team marked
  "NOT YET SUBMITTED" is unknown, not healthy. Re-read at most every REPORT_EVERY (game day) / REPORT_OFF seconds.
- Sleeper's public NBA players file (~2.5 MB): injury_status and news_updated. Sleeper carries no ESPN ids for NBA
  players, so players match by name and team. Re-read at most every SLEEPER_GAME_DAY / SLEEPER_OFF seconds.

Precedence (decide()): for today's game the official report wins when it is newer than ESPN's injury note (or ESPN has
none). An older report that disagrees with ESPN's newer note on whether he plays is "unconfirmed": shown as Q, nothing
acts on it (status.confirm's rule). With no row for today (team not submitted, player not listed) Sleeper fills gaps:
only when it is newer than ESPN's note (or ESPN has none) and says something worse, and through status.confirm, so a
Sleeper Out that ESPN doesn't back is unconfirmed. "Injury Management" with Out is a rest day: OUT for today's game
only (a row only ever applies to the game on its own date).

Only our derived status and a short reason are ever shown ("Out (rest) per NBA injury report, 5:30pm"); the report's
table is never republished or linked."""
import datetime as dt
import re
import time
import traceback
import unicodedata
from zoneinfo import ZoneInfo

from .common import CACHE, ct_label, iso, load_json, parse_iso, save_json, session
from .status import DEAD, SEVERITY, confirm

ET = ZoneInfo("America/New_York")
INDEX = "https://official.nba.com/nba-injury-report-{season}-season/"
LINK_RE = re.compile(r"https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})\s*(AM|PM)\.pdf")
REPORT_FILE = CACHE / "nba_injury_report.json"
SLEEPER_FILE = CACHE / "sleeper_nba_players.json"
SLEEPER_URL = "https://api.sleeper.app/v1/players/nba"
REPORT_EVERY, REPORT_OFF = 10 * 60, 60 * 60            # the run loops every 10 min; the NBA updates every ~15
SLEEPER_GAME_DAY, SLEEPER_OFF = 45 * 60, 6 * 3600       # Sleeper asks that the big players file be read sparingly
REPORT_MAX_AGE = dt.timedelta(hours=30)                 # a cached report older than this is no help when both are down
TIMEOUT = 20

OFFICIAL = {"out": "OUT", "doubtful": "D", "questionable": "Q", "probable": None, "available": None}
SLEEPER = {"out": "OUT", "ir": "OUT", "sus": "SUSP", "dtd": "Q", "gtd": "Q", "questionable": "Q", "doubtful": "D"}
SLEEPER_WORDS = {"dtd": "day-to-day", "gtd": "game-time decision", "ir": "out (IR)", "sus": "suspended"}

# official report team names → ESPN's abbreviations (the ESPN pro schedule's, as on the league pages)
TEAMS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GS", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO",
    "New York Knicks": "NY", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SA",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTAH", "Washington Wizards": "WSH",
}
TEAM_KEYS = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in TEAMS.items()}
# Sleeper's NBA abbreviations → ESPN's
SLEEPER_TEAMS = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def key(name):
    """'Luka Dončić' / 'Doncic, Luka' style names → 'luka doncic' (accents and suffixes dropped)."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().replace("-", " ")
    words = re.sub(r"[^a-z ]", "", s).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def season_slug(d):
    """'2026-27' for any date from August 2026 through July 2027."""
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def report_links(html):
    """[(report time, url)] newest first, from the index page's HTML."""
    out = {}
    for m in LINK_RE.finditer(html or ""):
        day, hh, mm, ampm = m.groups()
        h = int(hh) % 12 + (12 if ampm == "PM" else 0)
        at = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(h, int(mm)), ET)
        out[m.group(0)] = at
    return sorted(((at, url) for url, at in out.items()), reverse=True)


# ---------- the PDF ----------

COLS = ("date", "time", "matchup", "team", "player", "status", "reason")


def _columns(tokens):
    """Column left edges and the header row's y from the header labels ("Game Date", "Game Time", "Matchup", "Team",
    "Player Name", "Current Status", "Reason"), or None when the page has no header."""
    at = {}
    for y, x, t in tokens:
        at.setdefault(t, []).append((y, x))
    try:
        hy = at["Matchup"][0][0]
        row = lambda t: sorted(x for y, x in at[t] if abs(y - hy) < 2)
        games = row("Game")
        edges = {"date": games[0], "time": games[1], "matchup": row("Matchup")[0], "team": row("Team")[0],
                 "player": row("Player")[0], "status": row("Current")[0], "reason": row("Reason")[0]}
    except (KeyError, IndexError):
        return None, None
    return edges, hy


def _col(edges, x):
    best = None
    for c in COLS:
        if x + 3 >= edges[c]:
            best = c
    return best


def parse_tokens(pages):
    """Rows from the report's words: `pages` is [[(y, x, word)]] per page, PDF coordinates (y grows upward).
    Each row: {"date": "2026-11-12", "team": "DET", "name": "Jalen Duren", "status": "Out", "reason": "..."}; a team
    that hasn't submitted yet: {"date", "team", "name": None, "status": None, "reason": "NOT YET SUBMITTED"}.
    A cell that wraps (reason, team) is joined to the nearest row; date, time, matchup and team carry down (and across
    pages)."""
    rows, carry, edges = [], {"date": None, "team": None}, None
    for tokens in pages:
        tokens = [(y, x, t.strip()) for y, x, t in tokens if t and t.strip()]
        found, hy = _columns(tokens)
        if found:
            edges = found
        else:                                   # later pages carry no header row: below the "Injury Report:" title
            title = [y for y, x, t in tokens if t == "Report:"]
            if not (edges and title):
                continue
            hy = min(title)
        foot = {round(y) for y, x, t in tokens if t == "Page" and y < hy}
        body = [(y, x, t) for y, x, t in tokens if y < hy - 2 and round(y) not in foot]
        lines = {}
        for y, x, t in body:
            lines.setdefault(round(y, 1), []).append((x, t, _col(edges, x)))
        anchors = [y for y, ws in lines.items()
                   if any(c == "status" for _, _, c in ws)
                   or "NOT YET SUBMITTED" in " ".join(t for _, t, c in sorted(ws) if c == "reason")]
        if not anchors:
            continue
        cells = {a: {c: [] for c in COLS} for a in anchors}
        for y, ws in lines.items():
            a = min(anchors, key=lambda a: abs(a - y))
            for x, t, c in ws:
                if c:
                    cells[a][c].append((-y, x, t))
        for a in sorted(anchors, reverse=True):            # top of the page first
            cell = {c: " ".join(t for _, _, t in sorted(v)) for c, v in cells[a].items()}
            if cell["date"]:
                m = re.search(r"(\d{2})/(\d{2})/(\d{4})", cell["date"])
                if m:
                    carry["date"] = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
            if cell["team"]:
                carry["team"] = TEAM_KEYS.get(re.sub(r"[^a-z0-9]", "", cell["team"].lower()), cell["team"])
            reason = re.sub(r"(\w)- (\w)", r"\1-\2", re.sub(r"\s+", " ", cell["reason"])).strip()
            if "NOT YET SUBMITTED" in reason and not cell["player"]:
                rows.append({"date": carry["date"], "team": carry["team"], "name": None, "status": None,
                             "reason": "NOT YET SUBMITTED"})
                continue
            last, _, first = cell["player"].partition(",")
            name = f"{first.strip()} {last.strip()}".strip()
            if name and cell["status"]:
                rows.append({"date": carry["date"], "team": carry["team"], "name": name,
                             "status": cell["status"].strip().title(), "reason": reason})
    return rows


def pdf_tokens(data):
    """[[(y, x, word)]] per page of a PDF (pypdf; imported here so a missing library only silences this source)."""
    import io

    import pypdf
    pages = []
    for page in pypdf.PdfReader(io.BytesIO(data)).pages:
        words = []

        def visit(text, cm, tm, font, size, words=words):
            if text and text.strip():
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                words.append((y, x, text))
        page.extract_text(visitor_text=visit)
        pages.append(words)
    return pages


UA = "Mozilla/5.0 (compatible; sports-hq/1.0)"   # a generic agent: official.nba.com answers 403 to the session's default


def _get(url):
    r = session.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    return r


def official(now, game_day=True, get=_get):
    """{"at": report time (ISO), "url", "rows"} for the newest official report, or None. Cached; never raises."""
    cached = load_json(REPORT_FILE) or {}
    every = REPORT_EVERY if game_day else REPORT_OFF
    fresh = lambda c: c.get("rows") is not None and now - parse_iso(c["at"]) < REPORT_MAX_AGE
    if cached.get("checked") and time.time() - cached["checked"] < every:
        return cached if fresh(cached) else None
    try:
        links = []
        for season in dict.fromkeys((season_slug(now.astimezone(ET).date()),
                                     season_slug(now.astimezone(ET).date() - dt.timedelta(days=60)))):
            links = report_links(get(INDEX.format(season=season)).text)
            if links:
                break
        if not links:
            raise ValueError("no injury report links on the index page")
        at, url = links[0]
        if url != cached.get("url"):
            rows = parse_tokens(pdf_tokens(get(url).content))
            if not rows:
                raise ValueError(f"no rows parsed from {url.rsplit('/', 1)[-1]}")
            cached = {"url": url, "at": iso(at), "rows": rows}
        cached["checked"] = time.time()
        save_json(REPORT_FILE, cached)
    except Exception:
        traceback.print_exc()
        print("NBA injury report unavailable this pass: using the last good copy if it's recent")
        if cached:
            cached["checked"] = time.time()          # don't hammer a source that's down: wait the usual interval
            save_json(REPORT_FILE, cached)
    return cached if cached and fresh(cached) else None


def sleeper(now, game_day=True, get=_get):
    """{name key: [{"team", "status", "at"}]} for every NBA player Sleeper tags, or {}. Cached; never raises."""
    cached = load_json(SLEEPER_FILE) or {}
    every = SLEEPER_GAME_DAY if game_day else SLEEPER_OFF
    if not (cached.get("_fetched") and time.time() - cached["_fetched"] < every):
        try:
            raw = get(SLEEPER_URL).json()
            slim = {}
            for p in raw.values():
                if p.get("injury_status") and p.get("team"):
                    slim.setdefault(key(p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}"), []).append(
                        {"team": SLEEPER_TEAMS.get(p["team"], p["team"]), "status": p["injury_status"],
                         "at": iso(dt.datetime.fromtimestamp(p["news_updated"] / 1000, dt.timezone.utc)) if p.get("news_updated") else None})
            cached = {"_fetched": time.time(), "players": slim}
            save_json(SLEEPER_FILE, cached)
        except Exception:
            traceback.print_exc()
            print("Sleeper NBA players unavailable this pass: using the last good copy")
            if cached:
                cached["_fetched"] = time.time()
                save_json(SLEEPER_FILE, cached)
    return cached.get("players") or {}


# ---------- the merge ----------

def short_reason(row):
    """'rest', 'right hamstring strain', 'G League', 'personal reasons' from a report row."""
    reason = (row.get("reason") or "").strip()
    low = reason.lower()
    if row.get("status", "").lower() == "out" and ("injury management" in low or low == "rest"):
        return "rest"
    if low.startswith("g league"):
        return "G League"
    part = reason.split(" - ", 1)[1] if low.startswith("injury/illness") and " - " in reason else reason
    part = part.lower().strip(" ;-")
    return part if len(part) <= 50 else part[:50].rsplit(" ", 1)[0]


def clock(at):
    """'5:30pm' in Central time."""
    t = ct_label(at).split(" ")[1]
    return t + "m"


def official_text(row, at):
    why = short_reason(row)
    return f"{row['status']}{f' ({why})' if why else ''} per NBA injury report, {clock(at)}"


def decide(base, entry, row, report_at, sl):
    """base = status.confirm's (status, why, news, conflict) from ESPN alone; entry = ESPN's injury-report entry;
    row = his official report row for today's game (None when not listed or his team hasn't submitted); report_at its
    time; sl = his Sleeper record ({"status", "at"}) or None. Returns (status, why, news, conflict, gd), gd being
    {"src": "nba"/"sleeper", "status", "rest", "at"} when a game-day source decided, else None."""
    status, why, news, conflict = base
    espn_at = entry.get("date") if entry else None
    if row:
        st = OFFICIAL.get(row["status"].lower())
        text = official_text(row, report_at)
        gd = {"src": "nba", "status": row["status"], "rest": short_reason(row) == "rest", "at": report_at}
        if espn_at is None or report_at >= espn_at:
            return st, text, news, False, gd
        if (st in DEAD) == (status in DEAD):           # ESPN's newer note agrees on whether he plays
            return status, why, news, conflict, None
        return "Q", f"{text}, but ESPN's newer note says {entry.get('status')}: unconfirmed", news, True, gd
    if sl and sl.get("status"):
        s = SLEEPER.get(sl["status"].lower())
        sl_at = parse_iso(sl["at"]) if isinstance(sl.get("at"), str) else sl.get("at")
        newer = entry is None or (espn_at is None) or (sl_at is not None and sl_at > espn_at)
        if s and newer and SEVERITY.get(s, 0) > SEVERITY.get(status, 0):
            word = SLEEPER_WORDS.get(sl["status"].lower(), sl["status"])
            text = f"{word[0].upper() + word[1:]} per Sleeper" + (f", {clock(sl_at)}" if sl_at else "")
            st2, why2, news2, conflict2 = confirm(s, text, entry)
            return st2, why2, news2 or news, conflict2, {"src": "sleeper", "status": sl["status"], "rest": False, "at": sl_at}
    return status, why, news, conflict, None


class Feed:
    """Both sources for one run. lookup()/apply() match a player by name and team."""

    def __init__(self, report=None, sleeper_players=None):
        self.report = report or {}
        self.at = parse_iso(self.report["at"]) if self.report.get("at") else None
        self.rows = {}
        for r in self.report.get("rows") or []:
            if r.get("name"):
                self.rows.setdefault(key(r["name"]), []).append(r)
        self.sleeper = sleeper_players or {}

    def __bool__(self):
        return bool(self.rows or self.sleeper)

    @staticmethod
    def _pick(cands, team):
        same = [c for c in cands if c.get("team") == team]
        if same:
            return same[0]
        names = {c.get("team") for c in cands}
        return cands[0] if len(names) == 1 and cands else None      # traded since ESPN's read: one player by that name

    def row(self, name, team, kickoff):
        """His official row for the game at `kickoff` (the report's dates are Eastern), or None."""
        if not kickoff or not self.at:
            return None
        day = kickoff.astimezone(ET).date().isoformat()
        return self._pick([r for r in self.rows.get(key(name), []) if r["date"] == day], team)

    def apply(self, base, entry, name, team, kickoff):
        row = self.row(name, team, kickoff)
        sl = None if row else self._pick(self.sleeper.get(key(name), []), team)
        return decide(base, entry, row, self.at, sl)

    def credit(self):
        """The basis note's credit line, naming what this run actually read."""
        parts = []
        if self.at:
            parts.append(f"the NBA injury report ({clock(self.at)} CT)")
        if self.sleeper:
            parts.append("Sleeper")
        src = " and ".join(parts) if parts else "the NBA injury report and Sleeper (neither readable this run)"
        return (f"Status: ESPN's injury report, updated for today's games from {src}. The official report wins when it's "
                "newer than ESPN's note; Sleeper fills gaps; sources that disagree with nothing official are shown as "
                "unconfirmed and nothing acts on them. A rest day (Out, injury management) counts for that game only.")


def load(now, game_day=True):
    """The run's Feed; empty (falsy) when both sources are down. Never raises."""
    try:
        rep = official(now, game_day)
    except Exception:
        traceback.print_exc()
        rep = None
    try:
        sl = sleeper(now, game_day)
    except Exception:
        traceback.print_exc()
        sl = {}
    return Feed(rep, sl)
