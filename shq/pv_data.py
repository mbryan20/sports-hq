"""Player values, data layer ("ours" vs the FantasyCalc market; hopper item 11, research/player-values-build-plan.md).

Shared by the live run (shq/pv_model.py) and the trainer (shq/pv_train.py), so a player's features are computed the same
way in both. Free, allowed sources only (checked Nov 20, 2026):
- nflverse weekly and season player stats (CC-BY 4.0), github.com/nflverse/nflverse-data releases, updated daily in season.
- DynastyProcess player-ID table (GPL-3.0): sleeper / espn / gsis ids and birthdates.
- nflverse draft picks (CC-BY 4.0): overall pick for rookies.
Not used: OverTheCap contracts (its terms bar "player valuations" on websites until it says otherwise), KeepTradeCut (terms
ban automated collection), FantasyPros pages.

Feature definitions are the lean ones that beat the market in planning (exp2_signals.py section F):
- in-season, season to date (3+ games): points per game; WR/TE target share; QB EPA per dropback (40+ dropbacks).
- offseason, last full season (6+ games): WR/TE target share and games; QB passing EPA per game and games; RB points per
  game and games."""
import csv
import datetime as dt
import gzip
import io
import json
import time

from .common import CACHE, STATE, session

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
WEEK_URL = NFLVERSE + "/stats_player/stats_player_week_{y}.csv"
REG_URL = NFLVERSE + "/stats_player/stats_player_reg_{y}.csv"
DRAFT_URL = NFLVERSE + "/draft_picks/draft_picks.csv"
IDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
PV_CACHE = CACHE / "pv"
DAY = 86400
SKILL = ("QB", "RB", "WR", "TE")
MIN_GAMES_IN = 3           # in-season: games played so far
MIN_GAMES_OFF = 6          # offseason: games in the last full season
MIN_DROPBACKS = 40
FC_HISTORY = STATE / "fc_history"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_text(url, name, max_age):
    """Text of `url`, cached in .cache/pv/<name> for max_age seconds; a stale copy stands in when the fetch fails."""
    path = PV_CACHE / name
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_text(encoding="utf-8")
    try:
        r = session.get(url, timeout=90)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig")
    except Exception:
        if path.exists():
            return path.read_text(encoding="utf-8")
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


# ---- ids ----
def read_ids(text):
    """{"sleeper"|"espn"|"fp": {id: gsis}, "birth": {gsis: "YYYY-MM-DD"}} from DynastyProcess's db_playerids.csv."""
    out = {"sleeper": {}, "espn": {}, "fp": {}, "birth": {}}
    for r in csv.DictReader(io.StringIO(text)):
        g = r.get("gsis_id")
        if not g or g == "NA":
            continue
        for k, col in (("sleeper", "sleeper_id"), ("espn", "espn_id"), ("fp", "fantasypros_id")):
            v = r.get(col)
            if v and v != "NA":
                out[k][v] = g
        if r.get("birthdate") and r["birthdate"] != "NA":
            out["birth"][g] = r["birthdate"][:10]
    return out


def ids():
    return read_ids(fetch_text(IDS_URL, "db_playerids.csv", 7 * DAY))


# ---- nflverse stats ----
def read_week(text):
    """{gsis: [compact weekly rows, regular season]} from stats_player_week_<y>.csv."""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("season_type") != "REG" or r.get("position") not in SKILL:
            continue
        out.setdefault(r["player_id"], []).append({
            "wk": int(r["week"]), "team": r.get("team"), "ppr": fnum(r.get("fantasy_points_ppr")) or 0.0,
            "ts": fnum(r.get("target_share")), "db": (fnum(r.get("attempts")) or 0) + (fnum(r.get("sacks_suffered")) or 0),
            "epa": fnum(r.get("passing_epa")) or 0.0})
    return out


def read_season(text):
    """{gsis: {"games", "ppg", "tshare", "epa_pg"}} from stats_player_reg_<y>.csv."""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("position") not in SKILL:
            continue
        g = fnum(r.get("games")) or 0
        if g < 1:
            continue
        out[r["player_id"]] = {"games": g, "ppg": (fnum(r.get("fantasy_points_ppr")) or 0) / g,
                               "tshare": fnum(r.get("target_share")), "epa_pg": (fnum(r.get("passing_epa")) or 0) / g}
    return out


def to_date(rows, upto_week):
    """Season-to-date features from weekly rows, weeks <= upto_week; None under MIN_GAMES_IN games."""
    rs = [r for r in rows or [] if r["wk"] <= upto_week]
    if len(rs) < MIN_GAMES_IN:
        return None
    db = sum(r["db"] for r in rs)
    ts = [r["ts"] for r in rs if r["ts"] is not None]
    return {"g": len(rs), "ppg": sum(r["ppr"] for r in rs) / len(rs), "tshare": sum(ts) / len(ts) if ts else 0.0,
            "epa_db": sum(r["epa"] for r in rs) / db if db >= MIN_DROPBACKS else None}


def week_stats(season, max_age=DAY):
    return read_week(fetch_text(WEEK_URL.format(y=season), f"week_{season}.csv", max_age))


def season_stats(season, max_age=7 * DAY):
    return read_season(fetch_text(REG_URL.format(y=season), f"reg_{season}.csv", max_age))


def read_draft(text):
    """{gsis: (season, round, overall pick)} from nflverse draft_picks.csv."""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        g = r.get("gsis_id")
        if g and g != "NA" and r.get("pick"):
            out[g] = (int(r["season"]), int(r["round"]), int(r["pick"]))
    return out


def draft():
    return read_draft(fetch_text(DRAFT_URL, "draft_picks.csv", 7 * DAY))


# ---- FantasyCalc history (plan step 0) ----
def save_fc_snapshot(settings_key, values, now):
    """Once a day per settings (e.g. "2qb-12t-1ppr"), every valued player and pick FantasyCalc lists, so live scoring is not
    limited to rostered players: state/fc_history/<date>.json.gz = {settings_key: {id: value}}. Returns True when written."""
    day = now.date().isoformat()
    path = FC_HISTORY / f"{day}.json.gz"
    data = {}
    if path.exists():
        try:
            data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        except (OSError, ValueError):
            data = {}
    if settings_key in data:
        return False
    data[settings_key] = {str(k): v for k, v in sorted(values.items())}
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: the same content always gives the same bytes, so a rerun never makes a needless commit
    path.write_bytes(gzip.compress(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"), mtime=0))
    return True


def load_fc_snapshot(day, settings_key):
    path = FC_HISTORY / f"{day}.json.gz" if isinstance(day, str) else FC_HISTORY / f"{day.isoformat()}.json.gz"
    try:
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8")).get(settings_key) or {}
    except (OSError, ValueError):
        return {}


def age_on(birth, when):
    try:
        b = dt.date.fromisoformat(birth)
    except (TypeError, ValueError):
        return None
    return (when - b).days / 365.25
