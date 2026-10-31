"""Public NFL data for the War Room: nflverse weekly stats, rosters, injuries, schedule, and the
dynastyprocess id map (Sleeper id -> nflverse gsis id). Downloads go to .cache/warroom (not committed)."""
import collections
import csv
import io
import time

from shq.common import CACHE, session

DIR = CACHE / "warroom"
MAX_AGE = 3600
URLS = {
    "ids.csv": "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv",
    "stats_player_week.csv": "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv",
    "stats_team_week.csv": "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{season}.csv",
    "injuries.csv": "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv",
    "roster_weekly.csv": "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.csv",
    "games.csv": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
}
TEAMFIX = {"LA": "LAR", "LVR": "LV", "JAC": "JAX", "WSH": "WAS", "GBP": "GB", "KCC": "KC", "NEP": "NE",
           "NOS": "NO", "SFO": "SF", "TBB": "TB"}
K_FG = [("fg_made_0_19", 3), ("fg_made_20_29", 3), ("fg_made_30_39", 3), ("fg_made_40_49", 4),
        ("fg_made_50_59", 5), ("fg_made_60_", 5)]


def nt(team):
    return TEAMFIX.get(team, team)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def fetch(season):
    """{name: rows} for every file, re-downloaded when older than an hour."""
    DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, url in URLS.items():
        path = DIR / name
        if not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE:
            r = session.get(url.format(season=season), timeout=180)
            r.raise_for_status()
            path.write_bytes(r.content)
        out[name] = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    return out


def pa_pts(x):
    return 10 if x == 0 else 7 if x <= 6 else 4 if x <= 13 else 1 if x <= 20 else 0 if x <= 27 else -1 if x <= 34 else -4


class Nfl:
    """Weekly 0.5 PPR points per player (league scoring: 4-pt pass TD, -1 INT) and team defense."""

    def __init__(self, season, files=None):
        files = files or fetch(season)
        self.season = season
        self.ids = {r["sleeper_id"]: r for r in files["ids.csv"] if r["sleeper_id"] not in ("", "NA")}
        by_gsis = {r["gsis_id"]: r for r in files["ids.csv"] if r["gsis_id"] not in ("", "NA")}
        self.cur = {}   # gsis -> (week, team, status) from the latest weekly roster
        for r in files["roster_weekly.csv"]:
            sid, g, w = r.get("sleeper_id"), r["gsis_id"], int(r["week"])
            if sid and sid != "NA" and sid not in self.ids:
                base = dict(by_gsis.get(g, {}))
                base.update(gsis_id=g, name=r["full_name"], position=r["position"], team=r["team"])
                self.ids[sid] = base
            if g not in self.cur or w >= self.cur[g][0]:
                self.cur[g] = (w, nt(r["team"]), r["status"])
        self.pts = collections.defaultdict(dict)
        self.team_of = {}
        for s in files["stats_player_week.csv"]:
            if s.get("season_type", "REG") != "REG":
                continue
            w = int(s["week"])
            if s["position"] == "K":
                p = f(s["pat_made"]) - f(s["pat_missed"]) + sum(v * f(s.get(k)) for k, v in K_FG) - f(s["fg_missed"])
            else:
                # nflverse fantasy_points is non-PPR with -2 per INT; the league is 0.5 PPR with -1 per INT
                p = f(s["fantasy_points"]) + 0.5 * f(s["receptions"]) + f(s.get("passing_interceptions"))
            self.pts[s["player_id"]][w] = round(p, 2)
            self.team_of[s["player_id"]] = s["team"]
        self.games = [g for g in files["games.csv"] if g["season"] == str(season) and g["game_type"] == "REG"]
        allowed = {}
        for g in self.games:
            if g["away_score"]:
                allowed[(nt(g["away_team"]), int(g["week"]))] = int(g["home_score"])
                allowed[(nt(g["home_team"]), int(g["week"]))] = int(g["away_score"])
        self.defpts = collections.defaultdict(dict)
        for t in files["stats_team_week.csv"]:
            if t.get("season_type", "REG") != "REG":
                continue
            w, tm = int(t["week"]), nt(t["team"])
            p = (f(t.get("def_sacks")) + 2 * f(t.get("def_interceptions")) + 2 * f(t.get("fumble_recovery_opp"))
                 + 6 * f(t.get("def_tds")) + 2 * f(t.get("def_safeties")) + 6 * f(t.get("special_teams_tds")))
            self.defpts[tm][w] = round(p + pa_pts(allowed.get((tm, w), 20)), 2)
        teams_wk = collections.defaultdict(set)
        for g in self.games:
            teams_wk[int(g["week"])] |= {nt(g["away_team"]), nt(g["home_team"])}
        every = set().union(*teams_wk.values()) if teams_wk else set()
        self.bye = collections.defaultdict(list)
        for w in sorted(teams_wk):
            for t in every - teams_wk[w]:
                self.bye[t].append(w)
        self.injuries = collections.defaultdict(dict)   # week -> gsis -> (status, injury)
        for r in files["injuries.csv"]:
            if r.get("report_status"):
                self.injuries[int(r["week"])][r["gsis_id"]] = (r["report_status"], r.get("report_primary_injury") or "")

    def final_weeks(self):
        """Weeks whose games all have final scores in nflverse's schedule."""
        weeks = collections.defaultdict(list)
        for g in self.games:
            weeks[int(g["week"])].append(bool(g["away_score"]))
        return {w for w, done in weeks.items() if all(done)}

    def stats_weeks(self):
        return {w for p in self.pts.values() for w in p}

    def player(self, sid, sleeper_db=None):
        """{name, pos, team, gsis}; Sleeper's own player list fills in ids nflverse doesn't map."""
        if not sid[0].isdigit():
            return {"name": sid + " DEF", "pos": "DEF", "team": sid, "gsis": None}
        r = self.ids.get(sid)
        db = (sleeper_db or {}).get(sid) or {}
        if not r:
            return {"name": db.get("full_name") or "?" + sid, "pos": db.get("position") or "?",
                    "team": nt(db.get("team") or "FA"), "gsis": None}
        g = r["gsis_id"] if r.get("gsis_id") not in (None, "", "NA") else None
        return {"name": r.get("name") or db.get("full_name") or sid, "pos": r.get("position") or db.get("position") or "?",
                "team": nt(self.team_of.get(g, r.get("team") or db.get("team") or "FA")), "gsis": g}

    def week_points(self, sid, week, info=None):
        info = info or self.player(sid)
        if info["pos"] == "DEF":
            return self.defpts.get(sid, {}).get(week)
        return self.pts.get(info["gsis"], {}).get(week)
