"""Expert consensus ranks for football: ESPN's fantasy analysts' weekly position ranks, averaged (Q-052).

Why ESPN and not FantasyPros (checked Nov 10, 2026): FantasyPros' robots.txt allows its public ranking pages, but its
Terms of Use (fantasypros.com/about/legal/) allow only "a single copy made for personal use" and forbid republishing
or posting anything from the site; Sports HQ is a public repo and a public site. Its API needs a key (the free tier is
"non-production use" only; personal use is the $8.99/mo Premium key or a HOF membership's personal key). So we use the
closest free consensus we can read: ESPN's own experts' weekly PPR ranks, from the same public ESPN fantasy API the
3-Ball leagues already use (no sign-in, generic User-Agent, nothing personal in the request).

What it gives, per player (QB/RB/WR/TE; ESPN doesn't rank kickers or defenses in this feed):
  wk      consensus position rank this week: players ordered by their average rank across ESPN's experts (each
          ranked by at least MIN_EXPERTS), "WR18". None until ESPN publishes the week (usually Tuesday-Wednesday).
  lately  median of his last 3 weekly consensus ranks as a real option (inside 1.5x the usual starters; weeks he was out
          or on a bye skipped, up to 6 weeks back): the experts' recent view, our stand-in for a rest-of-season rank
          (ESPN's feed has no rest-of-season expert ranks).
Ranks are PPR; half-PPR leagues get the same ranks (no half-PPR set in the feed).

Backtest (weeks 1-9, 2026, every pair of players at a position ranked within 12 spots of each other, both played,
half-PPR points, 15,973 pairs): Sleeper's projection picked the higher scorer 57.5% of the time, the experts 56.8%, a 50/50 blend
57.9% (better in 5 of 9 weeks). Too small and too uneven to change lineups, so the model still decides on Sleeper's
projections; the experts are shown next to every call, the big disagreements are listed, and shq/health.py re-runs
the comparison nightly (`backtest`) so a lasting edge shows up.

Fetched at most every MAX_AGE (cached in .cache, which Actions keeps between runs); a failed read uses the last
cache and never fails the run."""
import json
import re
import statistics
import time
import traceback

from .common import CACHE, get_json, load_json, save_json

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league}"
CACHE_FILE = CACHE / "espn_experts.json"
MAX_AGE = 3 * 3600
LIMIT = 600                      # most-rostered players read; ESPN's experts rank ~260 a week
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}
SLOTS = [0, 2, 4, 6]            # ESPN lineup slots QB, RB, WR, TE
MIN_EXPERTS = 3
LATELY = 3                       # weeks in the "lately" median
LOOKBACK = 6                     # weeks read for it (an injured player's parked weeks are skipped)
IDLE = 0.15                      # bottom share of a week's position list = parked (bye, ruled out), not a real rank
TOP = {"QB": 24, "RB": 36, "WR": 48, "TE": 18}  # a free agent the experts rank inside this is a real start option
BIG = {"QB": 6, "TE": 6, "RB": 10, "WR": 10}   # rank gap that counts as a big disagreement
WHO = "ESPN experts"
# ESPN pro team ids -> abbreviations (fixed by ESPN; used to match players across platforms)
TEAMS = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND",
         12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
         22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL",
         34: "HOU"}


def name_key(name):
    words = re.sub(r"[^a-z ]", "", (name or "").lower().replace("-", " ")).split()
    return " ".join(w for w in words if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


# ---------- fetch and cache ----------
def fetch(season, league_id, weeks, get=get_json):
    """ESPN's kona_player_info for the most-rostered QB/RB/WR/TE with their weekly PPR expert ranks."""
    flt = {"players": {"limit": LIMIT, "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                       "filterSlotIds": {"value": SLOTS},
                       "filterRanksForScoringPeriodIds": {"value": list(weeks)},
                       "filterRanksForRankTypes": {"value": ["PPR"]},
                       "filterStatsForTopScoringPeriodIds": {"value": 1, "additionalValue": [f"00{season}"]}}}
    return get(API.format(season=season, league=league_id), {"view": "kona_player_info"},
               headers={"X-Fantasy-Filter": json.dumps(flt)})


def compact(raw):
    """{"players": {espn id: [name, pos, team]}, "weeks": {week: {espn id: [avg rank, best, worst, experts]}}}.
    The averaged row ESPN adds itself (source 0) is skipped; we average the experts directly."""
    players, weeks = {}, {}
    for e in raw.get("players") or []:
        p = e.get("player") or e
        pos = POS.get(p.get("defaultPositionId"))
        if not pos:
            continue
        eid = str(p["id"])
        players[eid] = [p.get("fullName"), pos, TEAMS.get(p.get("proTeamId"))]
        for wk, rows in (p.get("rankings") or {}).items():
            rs = [x["rank"] for x in rows if x.get("rankType") == "PPR" and x.get("rankSourceId") and x.get("rank")]
            if len(rs) >= MIN_EXPERTS:
                weeks.setdefault(str(wk), {})[eid] = [round(statistics.mean(rs), 2), min(rs), max(rs), len(rs)]
    return {"players": players, "weeks": weeks}


def load(season, league_id, week, now=None, get=get_json, path=CACHE_FILE):
    """Compact ranks (see compact) for weeks up to `week`, from the cache when it is under MAX_AGE old; else a fresh
    read. A failed read falls back to the cache at any age, then None. Never raises."""
    now = now if now is not None else time.time()
    cached = load_json(path)
    if cached and cached.get("week") == week and now - cached.get("_fetched", 0) < MAX_AGE:
        return cached
    try:
        weeks = range(max(1, week - LOOKBACK), week + 1)
        data = {**compact(fetch(season, league_id, weeks, get)), "week": week, "_fetched": now}
        if not data["players"]:
            raise ValueError("ESPN returned no ranked players")
        save_json(path, data)
        return data
    except Exception:
        traceback.print_exc()
        return cached or None


# ---------- per-week consensus ----------
def position_ranks(week_rows, players):
    """({espn id: consensus position rank}, {espn ids ranked as not playing}): players at each position ordered by
    average expert rank, ties broken by the best single rank. ESPN's experts park players on a bye or ruled out at the
    bottom of their lists, so the bottom IDLE share at each position counts as "not ranked to play", not a real rank."""
    by_pos = {}
    for eid, (avg, best, *_rest) in week_rows.items():
        pos = (players.get(eid) or [None, None])[1]
        if pos:
            by_pos.setdefault(pos, []).append((avg, best, eid))
    out, idle = {}, set()
    for rows in by_pos.values():
        keep = len(rows) - int(len(rows) * IDLE)
        for i, (_, _, eid) in enumerate(sorted(rows), 1):
            out[eid] = i
            if i > keep:
                idle.add(eid)
    return out, idle


class Ranks:
    """Consensus ranks for one NFL week plus the "lately" median, with lookups for any league's player dict."""

    def __init__(self, data, week, sleeper_db=None):
        self.week, self.players = week, data.get("players") or {}
        weeks = data.get("weeks") or {}
        self.published = bool(weeks.get(str(week)))
        self.now, self.idle = position_ranks(weeks.get(str(week)) or {}, self.players)
        self.detail = weeks.get(str(week)) or {}
        past = [position_ranks(weeks[w], self.players) for w in sorted(weeks, key=int, reverse=True) if int(w) < week]
        self.lately = {}
        for eid in self.players:
            # his last LATELY weeks ranked as a real option (inside 1.5x the usual starters): weeks he was parked for a
            # bye or an injury (ranked WR100 while out) would say nothing about him
            cap = TOP.get(self.players[eid][1], 48) * 1.5
            rs = [r[eid] for r, idle in past if eid in r and eid not in idle and r[eid] <= cap][:LATELY]
            if rs:
                self.lately[eid] = round(statistics.median(rs))
        self.by_name = {}
        for eid, (name, pos, team) in self.players.items():
            self.by_name.setdefault((name_key(name), pos), []).append((team, eid))
        self.sleeper_to_espn = {sid: str(p["espn_id"]) for sid, p in (sleeper_db or {}).items() if p.get("espn_id")}

    def espn_id(self, p):
        """ESPN id for a league's player dict: ESPN leagues carry it ("key"), Sleeper players via Sleeper's espn_id,
        anyone else by name + position (+ team when two share a name)."""
        if str(p.get("id", "")).startswith("espn") and p.get("key") is not None:
            return str(p["key"])
        eid = self.sleeper_to_espn.get(str(p.get("id")))
        if eid in self.players:
            return eid
        for pos in p.get("positions") or []:
            cands = self.by_name.get((name_key(p.get("name")), pos)) or []
            if len(cands) == 1:
                return cands[0][1]
            same = [e for t, e in cands if t and _team(t) == _team(p.get("team"))]
            if len(same) == 1:
                return same[0]
        return None

    def of(self, p):
        """{"pos", "wk", "lately", "best", "worst", "n", "published", "idle"} or None when the experts don't rank him.
        wk is None when this week isn't published, he isn't in it, or he's ranked as not playing ("idle")."""
        eid = self.espn_id(p)
        if not eid or eid not in self.players:
            return None
        pos = self.players[eid][1]
        idle = eid in self.idle
        wk, lately = (None if idle else self.now.get(eid)), self.lately.get(eid)
        if wk is None and lately is None and not idle:
            return None
        d = [None] * 4 if idle else (self.detail.get(eid) or [None] * 4)
        return {"pos": pos, "wk": wk, "lately": lately, "best": d[1], "worst": d[2], "n": d[3],
                "published": self.published, "idle": idle}


def _team(t):
    from .espn import norm_team
    return norm_team(t)


def label(x, lately=True):
    """'WR18 this week' / 'WR18 this week, WR22 lately' / 'not ranked to play this week, WR22 lately' /
    'WR22 lately (this week's ranks aren't out yet)'."""
    if not x:
        return None
    parts = []
    if x.get("wk"):
        parts.append(f"{x['pos']}{x['wk']} this week")
    elif x.get("idle") or x.get("published"):
        parts.append("not ranked to play this week")
    if lately and x.get("lately") and (not x.get("wk") or x["lately"] != x["wk"]):
        pending = not (x.get("wk") or x.get("published") or x.get("idle"))
        parts.append(f"{x['pos']}{x['lately']} lately" + (" (this week's ranks aren't out yet)" if pending else ""))
    return ", ".join(parts) or None


# ---------- league annotations ----------
def ranks_for(ctx):
    """One Ranks per run (cached on the context); None when ESPN can't be read and nothing is cached."""
    if "_experts" not in ctx.__dict__:
        ctx._experts = None
        try:
            from .config import LEAGUES, SEASON
            src = next(lg for lg in LEAGUES if lg["platform"] == "espn" and lg["sport"] == "nfl" and not lg.get("private"))
            data = load(SEASON, src["league_id"], ctx.week)
            if data:
                ctx._experts = Ranks(data, ctx.week, getattr(ctx, "players", None))
        except Exception:
            traceback.print_exc()
    return ctx._experts


def annotate(league, ranks):
    """Put "exp" (see Ranks.of) on every player the league holds: mine, other teams', free agents."""
    if not ranks:
        return False
    groups = [league.starters, league.bench, list(getattr(league, "ir_blocked", None) or []),
              list(getattr(league, "free_agents", None) or [])]
    groups += [t["players"] for t in getattr(league, "others", None) or []]
    for g in groups:
        for p in g:
            if not p.get("empty") and "exp" not in p:
                p["exp"] = ranks.of(p)
    return True


def _pos(p):
    return next((x for x in p.get("positions") or [] if x in BIG), None)


def _better(a, b, key):
    """Rank gap when the experts rank a ahead of b at the same position by a big margin, else 0."""
    xa, xb = a.get("exp") or {}, b.get("exp") or {}
    if not (xa.get(key) and xb.get(key)) or xa["pos"] != xb["pos"]:
        return 0
    gap = xb[key] - xa[key]
    return gap if gap >= BIG.get(xa["pos"], 10) else 0


def disagreements(league, moves=None, limit=6):
    """Lines where our call goes against the experts by a big margin (BIG rank spots), both numbers shown:
    - a starter we keep in over a bench player the experts rank well ahead this week;
    - a "start X over Y" move of ours where the experts rank Y well ahead of X;
    - a free agent the experts rank well ahead of one of my starters at his position, that we don't add.
    Uses this week's ranks; nothing before ESPN publishes them."""
    from .digest import DEAD
    from .swap import playable
    out = []
    dead = lambda p: bool(p.get("empty") or p.get("bye") or p.get("status") in DEAD or p.get("started"))
    starters = [p for p in league.starters if not p.get("empty") and _pos(p)]
    bench = [p for p in league.bench if _pos(p) and not dead(p)]
    moved = {(s["name"], b["name"]) for s, b, _ in (moves or [])}
    for s in starters:
        if dead(s):
            continue   # a dead starter is already a fix; a locked one can't move
        for b in bench:
            if _pos(b) != _pos(s) or (s["name"], b["name"]) in moved:
                continue
            gap = _better(b, s, "wk")
            if gap and b["proj"] <= s["proj"] and b["exp"]["wk"] <= TOP[_pos(b)]:
                out.append((gap, f"Experts would start {b['name']} ({b['exp']['pos']}{b['exp']['wk']}) over your "
                                 f"{s['name']} ({s['exp']['pos']}{s['exp']['wk']}) at {s['slot']}; we keep {s['name']}: "
                                 f"{s['proj']} vs {b['proj']} projected."))
    for s, b, _ in moves or []:
        gap = _better(s, b, "wk")
        if gap:
            out.append((gap, f"We say start {b['name']} over {s['name']} ({b['proj']} vs {s['proj']} projected); experts rank "
                             f"{s['name']} {s['exp']['pos']}{s['exp']['wk']}, {b['name']} {b['exp']['pos']}{b['exp']['wk']}."))
    now = getattr(getattr(league, "ctx", None), "now", None)
    covered = set()   # one free agent per starter: the one the experts rank highest
    fas = [fa for fa in list(getattr(league, "free_agents", None) or [])[:300]
           if _pos(fa) and not dead(fa) and fa.get("proj") and (fa.get("exp") or {}).get("wk")
           and fa["exp"]["wk"] <= TOP[_pos(fa)] and (not now or playable(fa, now))]
    for fa in sorted(fas, key=lambda f: f["exp"]["wk"]):
        worst = max((s for s in starters if _pos(s) == _pos(fa) and not dead(s) and (s.get("exp") or {}).get("wk")),
                    key=lambda s: s["exp"]["wk"], default=None)
        if worst and worst["name"] not in covered:
            gap = _better(fa, worst, "wk")
            if gap:
                covered.add(worst["name"])
                out.append((gap, f"Free agent {fa['name']} ({fa['team']}) is {fa['exp']['pos']}{fa['exp']['wk']} with the experts this "
                                 f"week, ahead of your starter {worst['name']} ({worst['exp']['pos']}{worst['exp']['wk']}); "
                                 f"we project {fa['proj']} vs {worst['proj']}."))
    out.sort(key=lambda t: -t[0])
    return [t for _, t in out[:limit]]


def names(league, extra=()):
    """{player name: label} for every ranked player on my roster, the free agents named in the advice, and `extra`
    names (guillotine bids); the page tags each fix, move and add with the players it names."""
    out = {}
    pool = (list(league.starters) + list(league.bench) + list(getattr(league, "ir_blocked", None) or [])
            + list(getattr(league, "free_agents", None) or []))
    for t in getattr(league, "others", None) or []:
        pool += t["players"]
    for p in pool:
        lab = label(p.get("exp"))
        if lab and p["name"] not in out:
            out[p["name"]] = lab
    return out


def extra_names(league, wanted):
    """{name: label} for extra names (guillotine bids and their drops), from the league's players or, for a player
    the league doesn't list (a cut team's), by name alone."""
    ranks = ranks_for(league.ctx) if getattr(league, "ctx", None) is not None else None
    if not ranks:
        return {}
    have = names(league)
    out = {}
    for n in wanted:
        if not n or n in out:
            continue
        lab = have.get(n) or label(ranks.of({"id": "", "name": n, "positions": list(BIG)}))
        if lab:
            out[n] = lab
    return out


def block(league, lines, moves=None):
    """The league page's experts block, or None (basketball, or no ranks): {"week", "published", "names" (only the
    names that appear in `lines` or on my roster), "disagree", "basis"}."""
    ranks = ranks_for(league.ctx) if getattr(league, "ctx", None) is not None else None
    if not ranks or getattr(league, "sport", "nfl") != "nfl":
        return None
    annotate(league, ranks)
    every = names(league)
    text = " \n".join(lines)
    mine = {p["name"] for p in list(league.starters) + list(league.bench) + list(getattr(league, "ir_blocked", None) or [])}
    shown = {n: v for n, v in every.items() if n in mine or n in text}
    return {
        "week": ranks.week, "published": ranks.published, "names": shown,
        "disagree": disagreements(league, moves) if ranks.published else [],
        "basis": f"{WHO}: ESPN's fantasy analysts' weekly PPR position ranks, averaged (players ranked by "
                 f"{MIN_EXPERTS}+ of them; QB/RB/WR/TE). \"Lately\" = median of their last {LATELY} weekly ranks with him as a real option (weeks he was out or on a bye skipped). "
                 "Big disagreement = " + ", ".join(f"{k} {v}+" for k, v in BIG.items()) + " spots. "
                 + ("" if ranks.published else f"Week {ranks.week}'s ranks aren't out yet (ESPN usually posts them Tuesday-Wednesday). ")
                 + "Our calls still use Sleeper's projections: in weeks 1-9, a 50/50 blend with the experts picked the better "
                   "of two players 57.9% of the time vs 57.5% for Sleeper alone, and won only 5 of 9 weeks, so the nightly "
                   "health check keeps testing it.",
    }


# ---------- backtest (shq/health.py) ----------
def pairs_accuracy(weeks, top=None, max_gap=12):
    """Start/sit accuracy on realistic pairs. weeks: {week: [{"rk": expert position rank, "proj": Sleeper projection,
    "pts": actual, "pos"}]} (players who played). Every pair at a position ranked within max_gap of each other by the
    experts (and inside 1.5x the usual starters), with different scores: did the source rank the higher scorer first?
    Returns {"n", "sleeper", "experts", "blend", "edge" (blend - sleeper), "weeks": {week: {...}}, "blend_wins"}."""
    top = top or {"QB": 24, "RB": 36, "WR": 48, "TE": 18}
    tot = {"sleeper": 0.0, "experts": 0.0, "blend": 0.0, "n": 0}
    per = {}
    for w, rows in weeks.items():
        acc = {"sleeper": 0.0, "experts": 0.0, "blend": 0.0, "n": 0}
        for pos, cap in top.items():
            rs = [r for r in rows if r["pos"] == pos]
            if len(rs) < 5:
                continue
            curve = sorted((r["proj"] for r in rs), reverse=True)
            ep = lambda rk: curve[min(len(curve), rk) - 1]
            rel = [{**r, "blend": 0.5 * r["proj"] + 0.5 * ep(r["rk"])} for r in rs if r["rk"] <= cap * 1.5]
            for i, a in enumerate(rel):
                for b in rel[i + 1:]:
                    if abs(a["rk"] - b["rk"]) > max_gap or a["pts"] == b["pts"]:
                        continue
                    truth = a["pts"] > b["pts"]
                    for k, va, vb in (("sleeper", a["proj"], b["proj"]), ("experts", -a["rk"], -b["rk"]),
                                      ("blend", a["blend"], b["blend"])):
                        acc[k] += 0.5 if va == vb else float((va > vb) == truth)
                    acc["n"] += 1
        if acc["n"]:
            per[w] = {k: round(acc[k] / acc["n"], 4) for k in ("sleeper", "experts", "blend")} | {"n": acc["n"]}
            for k in tot:
                tot[k] += acc[k]
    n = tot["n"]
    res = {"n": n, "weeks": per}
    if n:
        res.update({k: round(tot[k] / n, 4) for k in ("sleeper", "experts", "blend")})
        res["edge"] = round(res["blend"] - res["sleeper"], 4)
        res["blend_wins"] = sum(1 for v in per.values() if v["blend"] > v["sleeper"])
    return res


def backtest_rows(data, week, proj, stats, sleeper_db, key="pts_half_ppr"):
    """Rows for pairs_accuracy for one week: every expert-ranked player who played, with Sleeper's projection (`proj`
    {sleeper id: stats}) and actual points (`stats`)."""
    ranks = Ranks(data, week, sleeper_db)
    by_name = {}
    for sid, p in (sleeper_db or {}).items():
        by_name.setdefault((name_key(p.get("full_name")), p.get("position")), []).append(sid)
    espn_to_sleeper = {e: s for s, e in ranks.sleeper_to_espn.items()}
    rows = []
    for eid, rk in ranks.now.items():
        if eid in ranks.idle:
            continue
        name, pos, _team_ = ranks.players[eid]
        sid = espn_to_sleeper.get(eid)
        if not sid:
            c = by_name.get((name_key(name), pos)) or []
            sid = c[0] if len(c) == 1 else None
        st, pj = (stats or {}).get(sid), (proj or {}).get(sid)
        if not sid or pj is None or not st or (st.get("gp") or 0) < 1:
            continue
        rows.append({"rk": rk, "pos": pos, "proj": pj.get(key) or 0.0, "pts": st.get(key) or 0.0, "name": name, "sid": sid})
    return rows
