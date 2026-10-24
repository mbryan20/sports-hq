"""Build a uniform view of each league and wire up its platform-specific actions."""
import re

from . import espn, sleeper
from .common import iso, parse_iso
from .config import SEASON, SLEEPER_TEAM_NAME, SLEEPER_USERNAME, YAHOO_LEAGUE_NAME, YAHOO_SCORING
from .status import worst
from .yahoo import Yahoo


class Context:
    """Week-level data shared by both leagues."""

    def __init__(self, now):
        self.now = now
        st = sleeper.state()
        week = max(1, int(st.get("week") or 1))
        games = espn.games(SEASON, week)
        # Once every game of the week is final, everything (lineups, weekly) looks ahead.
        if games and all(g["state"] == "post" for g in games.values()) and week < 18:
            week += 1
            games = espn.games(SEASON, week)
        self.week, self.games = week, games
        self.proj = sleeper.projections(SEASON, week)
        self.players = sleeper.players()
        self.espn_inj = espn.injuries()
        self.yahoo_to_sleeper = {str(p["yahoo_id"]): pid for pid, p in self.players.items() if p.get("yahoo_id")}
        self.by_name = {}
        for pid, p in self.players.items():
            if p.get("position") != "DEF":
                self.by_name.setdefault(name_key(p.get("full_name")), []).append(pid)

    def match(self, name, team, pos):
        """Sleeper id for a player known only by name/team/position (many Yahoo ids aren't mapped)."""
        cands = self.by_name.get(name_key(name), [])
        for want_team in (True, False):
            for pid in cands:
                p = self.players[pid]
                if pos in (p.get("fantasy_positions") or [p.get("position")]) and \
                        (not want_team or espn.norm_team(p.get("team")) == espn.norm_team(team)):
                    return pid
        return None

    def kickoffs(self):
        return sorted({g["kickoff"] for g in self.games.values() if g["kickoff"]})


def name_key(name):
    words = re.sub(r"[^a-z ]", "", (name or "").lower().replace("-", " ")).split()
    return " ".join(w for w in words if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def score(stats, scoring):
    if not stats:
        return 0.0
    return round(sum(v * scoring[k] for k, v in stats.items()
                     if k in scoring and isinstance(v, (int, float))), 1)


def make_player(ctx, scoring, pid, slot, *, name=None, team=None, positions=None, native=None, key=None):
    db = ctx.players.get(pid or "", {})
    pr = ctx.proj.get(pid or "", {})
    pp = pr.get("player") or {}
    team = espn.norm_team(team or pr.get("team") or pp.get("team") or db.get("team")) or None
    positions = positions or db.get("fantasy_positions") or ([db["position"]] if db.get("position") else [])
    sleeper_status = db.get("status") if db.get("status") not in (None, "Active") else None
    sources = [("Sleeper", pp.get("injury_status") or db.get("injury_status")),
               ("Sleeper", sleeper_status),
               ("ESPN", ctx.espn_inj.get(str(db.get("espn_id"))))]
    if native:
        sources.insert(0, native)
    status, why = worst(*sources)
    game = ctx.games.get(team) if team else None
    kickoff = game["kickoff"] if game else None
    started = bool(game) and (game["state"] != "pre" or ctx.now >= kickoff)
    return {
        "id": pid or key or name, "key": key, "name": name or db.get("full_name") or pid or "Empty",
        "team": team, "positions": positions, "slot": slot,
        "status": status, "why": why,
        "kickoff": kickoff, "started": started, "bye": bool(team) and game is None,
        "opp": (("vs " if game["home"] else "@") + game["opp"]) if game else None,
        "proj": score(pr.get("stats"), scoring),
        "empty": not pid,
    }


class SleeperLeague:
    platform = "sleeper"
    can_write = False

    def __init__(self, ctx):
        lg, uid, users = sleeper.find_league(SLEEPER_USERNAME, SLEEPER_TEAM_NAME, SEASON)
        self.key, self.name, self.week = f"sleeper:{lg['league_id']}", SLEEPER_TEAM_NAME, ctx.week
        self.league_name = lg["name"]
        self.scoring = lg["scoring_settings"]
        rosters = sleeper.rosters(lg["league_id"])
        mine = next(r for r in rosters if r["owner_id"] == uid)
        slots = [s for s in lg["roster_positions"] if s != "BN"]
        starter_ids = list(mine.get("starters") or [])
        held = set(mine.get("reserve") or []) | set(mine.get("taxi") or [])
        mp = lambda pid, slot: make_player(ctx, self.scoring, pid if pid not in (None, "0") else None, slot)
        self.starters = [mp(pid, slot) for slot, pid in zip(slots, starter_ids)]
        self.bench = [mp(pid, "BN") for pid in mine.get("players") or [] if pid not in starter_ids and pid not in held]

        rostered = {p for r in rosters for p in (r.get("players") or [])}
        self.free_agents = sorted(
            (make_player(ctx, self.scoring, pid, "FA") for pid in ctx.proj
             if pid not in rostered and pid in ctx.players and ctx.players[pid].get("team")),
            key=lambda p: -p["proj"])

        self.opponent, self.opp_proj = None, None
        try:
            ms = sleeper.matchups(lg["league_id"], ctx.week)
            me = next(m for m in ms if m["roster_id"] == mine["roster_id"])
            opp = next((m for m in ms if m["matchup_id"] == me["matchup_id"] and m["roster_id"] != me["roster_id"]), None)
            if opp:
                owner = next(r["owner_id"] for r in rosters if r["roster_id"] == opp["roster_id"])
                u = next((u for u in users if u["user_id"] == owner), {})
                self.opponent = (u.get("metadata") or {}).get("team_name") or u.get("display_name")
                self.opp_proj = round(sum(score((ctx.proj.get(p) or {}).get("stats"), self.scoring)
                                          for p in opp.get("starters") or [] if p != "0"), 1)
        except (StopIteration, KeyError, TypeError):
            pass

    def best_fa(self, positions, now):
        from .swap import playable
        return next((p for p in self.free_agents if set(p["positions"]) & set(positions) and playable(p, now)), None)


class YahooLeague:
    platform = "yahoo"

    def __init__(self, ctx, client=None):
        self.ctx = ctx
        self.y = client or Yahoo()
        self.name, self.week, self.scoring = YAHOO_LEAGUE_NAME, ctx.week, YAHOO_SCORING
        self.lk, self.tk, self.team_name = self.y.my_team(YAHOO_LEAGUE_NAME, SEASON)
        self.key = f"yahoo:{self.lk}"
        self.can_write = True  # optimistic; flips off on the first YahooWriteDenied
        self.load_roster()
        self.opponent, self.opp_proj = self.y.opponent(self.tk, ctx.week), None
        self._fa_cache = {}

    def _player(self, yp, slot):
        pid = self.ctx.yahoo_to_sleeper.get(str(yp["yahoo_id"]))
        if yp["pos"] == "DEF":
            pid = espn.norm_team(yp["team"])
        elif pid is None and hasattr(self.ctx, "match"):
            pid = self.ctx.match(yp["name"], yp["team"], yp["pos"])
        positions = [p for p in yp["eligible"] if p not in ("BN", "IR", "W/R/T")] or [yp["pos"]]
        return make_player(self.ctx, self.scoring, pid, slot, name=yp["name"], team=yp["team"],
                           positions=positions, native=("Yahoo", yp["status"]), key=yp["key"])

    def load_roster(self):
        roster = self.y.roster(self.tk, self.week)
        self.starters = [self._player(p, p["slot"]) for p in roster if p["slot"] not in ("BN", "IR", "IR+")]
        self.bench = [self._player(p, "BN") for p in roster if p["slot"] == "BN"]

    def fa_at(self, position):
        if position not in self._fa_cache:
            self._fa_cache[position] = sorted((self._player(p, "FA") for p in self.y.free_agents(self.lk, position)),
                                              key=lambda p: -p["proj"])
        return self._fa_cache[position]

    @property
    def free_agents(self):
        out = []
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            out += self.fa_at(pos)
        return sorted(out, key=lambda p: -p["proj"])

    def best_fa(self, positions, now):
        from .swap import playable
        cands = [p for pos in positions for p in self.fa_at(pos) if playable(p, now)]
        return max(cands, key=lambda p: p["proj"], default=None)

    def execute_swap(self, out_p, in_p):
        """Bench out_p, start in_p in its slot, then read the roster back to confirm."""
        self.y.set_positions(self.tk, self.week, [(out_p["key"], "BN"), (in_p["key"], out_p["slot"])])
        roster = {p["key"]: p["slot"] for p in self.y.roster(self.tk, self.week)}
        ok = roster.get(out_p["key"]) == "BN" and roster.get(in_p["key"]) == out_p["slot"]
        if ok:
            self.load_roster()
        return ok


class SavedYahooLeague(YahooLeague):
    """Kosmonauts from the roster the laptop's scheduled task reads off the Yahoo website
    (state/kosmonauts_roster.json) — used only while Yahoo's API is still gated. Read-only and
    without a free-agent list, so swaps and FA ideas come as pushes/notes for you to act on."""
    can_write = False
    saved = True

    def __init__(self, ctx, saved):
        self.ctx, self.name, self.week, self.scoring = ctx, YAHOO_LEAGUE_NAME, ctx.week, YAHOO_SCORING
        self.key, self.captured = "yahoo:saved", parse_iso(saved["captured"])
        self.opponent, self.opp_proj = saved.get("opponent"), None
        roster = saved["players"]
        self.starters = [self._player(p, p["slot"]) for p in roster if p["slot"] not in ("BN", "IR", "IR+")]
        self.bench = [self._player(p, "BN") for p in roster if p["slot"] == "BN"]

    @property
    def free_agents(self):
        return []

    def best_fa(self, positions, now):
        return None


def view(league):
    """JSON for the Lineup tab. Player names and NFL info only — no IDs or tokens."""
    def row(p):
        flags = []
        if p.get("empty"):
            flags.append("EMPTY")
        if p["bye"]:
            flags.append("BYE")
        if p["status"]:
            flags.append(p["status"])
        if p["team"] is None and not p.get("empty") and p["slot"] != "DEF":
            flags.append("NO TEAM")
        return {"slot": p["slot"], "name": p["name"], "team": p["team"], "pos": "/".join(p["positions"][:2]),
                "opp": p["opp"], "kickoff": iso(p["kickoff"]), "started": p["started"], "proj": p["proj"],
                "status": p["status"], "why": p["why"], "flags": flags}
    return {
        "name": league.name, "platform": league.platform, "week": league.week,
        "league": getattr(league, "league_name", None),
        "opponent": league.opponent, "opp_proj": league.opp_proj,
        "roster_synced": iso(league.captured) if getattr(league, "saved", False) else None,
        "proj": round(sum(p["proj"] for p in league.starters), 1),
        "starters": [row(p) for p in league.starters], "bench": [row(p) for p in league.bench],
    }
