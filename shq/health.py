"""Nightly model health: re-test every model against what actually happened and write docs/data/health.json.

No AI, no paid APIs, read-only (public Sleeper/ESPN/nflverse reads plus this repo's own git history).

Models and checks:
- War Room v2 (`warroom/`):
  - projection error (team score vs projected best lineup, Sleeper's weekly projections vs the old blend),
  - score swing (`measure_sd`), and how far-week projections miss (from the page's git history, weeks 2-4 ahead),
  - cut predictions (log-loss of each week's cut, in-sample on Sleeper's stored projections; plus the swing
    that would have scored best),
  - price ladder (leave-one-week-out: does a bid at the ladder's 50% / 80% price win about that often?
    split by position and season stage), via the page's own rival-bid model under Node (export.js --calibrate).
- Our bid recommendations (War Room v2's bids.json and the dashboard's guillotine bids, as committed before
  each waiver run): would the bid have won, what the winner paid, what the model expected.
- Guillotine dashboard (`shq/guillotine.py`) vs War Room v2: the cut odds each showed before kickoff, scored
  against the real cut (from docs/data/lineups.json and docs/war-room-v2/bids.json history).
- NBA trend radar (`shq/radar_backtest.py`, last 14 mornings): role held over the next 3 team games for the free agents
  the site showed (and, info only, every flag), value vs the old suggestion ranked by that morning's % rostered.
- Pool Picks: the stored walk-forward backtest (picks/backtest/) and the graded postmortems.
- Start/sit (`shq/experts.py`, weeks played so far): how often Sleeper's projections, ESPN's expert consensus and a 50/50
  blend ranked the higher scorer first in realistic pairs, and our own "Start X over Y" moves as shown before Sunday's
  early games (docs/data/lineups.json history) vs what happened and what the experts said.

Each check is compared with its baseline in state/health_baselines.json (a missing baseline is set from the
first measurement). Status: ok, watch (worse by more than half the tolerance), drift (worse by more than the
tolerance), weak (no better than the simple alternative, e.g. a coin toss, whatever the baseline), waiting (not
enough outcomes yet), info (no baseline by design), error.

    py -m shq.health            writes docs/data/health.json (and new baselines)
    py -m shq.health --print    also prints a one-line-per-check summary"""
import collections
import datetime as dt
import json
import math
import re
import subprocess
import sys
import traceback

from .common import DATA, ROOT, STATE, get_json, iso, load_json, now_utc, save_json
from .config import SEASON, SLEEPER_USERNAME

OUT = DATA / "health.json"
BASELINES = STATE / "health_baselines.json"

# id: (label, better, tolerance, unit). "better" is "lower" or "higher"; None = shown, never drifts.
CHECKS = {
    "wr.proj_mae": ("Team-score miss with Sleeper projections (1 week ahead)", "lower", 2.0, "pts"),
    "wr.blend_mae": ("Team-score miss with the old season/last-3 blend", None, 0, "pts"),
    "wr.proj_edge": ("Sleeper projections' edge over the blend", "higher", 2.0, "pts"),
    "wr.swing": ("Score swing (spread of real scores around projections)", None, 0, "pts"),
    "wr.swing_k2": ("Score swing 2 weeks ahead", None, 0, "pts"),
    "wr.swing_k3": ("Score swing 3 weeks ahead", None, 0, "pts"),
    "wr.swing_k4": ("Score swing 4 weeks ahead", None, 0, "pts"),
    "wr.cut_skill": ("Cut predictions vs a coin toss (in-sample, Sleeper projections)", "higher", 0.05, "%"),
    "wr.best_sd": ("Swing that would have predicted the cuts best", None, 0, "pts"),
    "wr.price_est_mae": ("Raw price estimate miss", "lower", 3.0, "$"),
    "wr.ladder_cov50": ("Bids at the ladder's 50% price that won", "target", 0.15, "%", 0.5),
    "wr.ladder_cov80": ("Bids at the ladder's 80% price that won", "target", 0.12, "%", 0.8),
    "rec.would_win": ("Our recommended bids that would have won", None, 0, "%"),
    "rec.win_brier": ("Win-chance accuracy of our bids (Brier, 0 = perfect)", "lower", 0.05, ""),
    "rec.est_mae": ("Likely-price miss vs what winners paid", "lower", 4.0, "$"),
    "gd.v2_skill": ("War Room v2 cut odds vs a coin toss (as shown before kickoff)", "higher", 0.05, "%"),
    "gd.dash_skill": ("Dashboard cut odds vs a coin toss (as shown before kickoff)", "higher", 0.05, "%"),
    "gd.dash_price_mae": ("Dashboard likely-price miss vs what winners paid", "lower", 4.0, "$"),
    "radar.held": ("Radar free agents shown on the site whose bigger role held (next 3 team games)", "higher", 0.15, "%"),
    "radar.held_all": ("Every flagged free agent whose bigger role held, shown or not", None, 0, "%"),
    "radar.edge": ("Radar flags' value over the old suggestion (z per game, next 3 team games)", "higher", 0.5, "z"),
    "picks.brier_gap": ("College model Brier minus the market's (0 = as good as the market)", "lower", 0.01, ""),
    "picks.stale_cover": ("Stale-line (1.5+ pt) picks that covered, college", "higher", 0.05, "%"),
    "picks.card_ats": ("Posted card picks that won against the spread", "higher", 0.08, "%"),
    "exp.sleeper_acc": ("Start/sit pairs Sleeper's projections called right (season so far)", None, 0, "%"),
    "exp.experts_acc": ("Start/sit pairs ESPN's experts called right (season so far)", None, 0, "%"),
    "exp.blend_edge": ("50/50 experts + Sleeper blend vs Sleeper alone (pairs called right)", None, 0, "%"),
    "exp.last_week_edge": ("Blend vs Sleeper alone, last completed week", None, 0, "%"),
    "exp.calls_right": ("Our \"Start X over Y\" calls where X outscored Y", "higher", 0.10, "%"),
    "exp.calls_vs_experts": ("Our calls the experts disagreed with that were right", None, 0, "%"),
}
MIN_N = {"wr.cut_skill": 4, "gd.v2_skill": 3, "gd.dash_skill": 3, "rec.would_win": 1, "rec.win_brier": 5, "rec.est_mae": 5,
         "gd.dash_price_mae": 5, "wr.ladder_cov50": 20, "wr.ladder_cov80": 20, "picks.card_ats": 10,
         # radar: players, once each at his first flag. Shown is ~10 players per 14 mornings (4 listed a morning, mostly
         # the same names), so 20 would never be reached; every flag and the edge get ~25-40.
         "radar.held": 10, "radar.held_all": 20, "radar.edge": 20,
         "exp.calls_right": 10, "exp.calls_vs_experts": 5}
# A stored baseline measured on fewer than MIN_N outcomes is re-set from the next measurement that has enough.
# the simple alternative a check must beat whatever its baseline says: a value on the wrong side is "weak"
FLOORS = {"wr.cut_skill": 0.0, "gd.v2_skill": 0.0, "gd.dash_skill": 0.0, "wr.proj_edge": 0.0, "radar.edge": 0.0,
          "picks.card_ats": 0.524}     # 52.4% wins against the spread breaks even at -110


# ---------- status and baselines ----------
def judge(cid, value, n, baselines, today):
    """One check row: value vs baseline -> ok / watch / drift / weak / waiting / info."""
    label, better, tol, unit, *target = CHECKS[cid]
    row = {"id": cid, "label": label, "value": value, "n": n, "unit": unit}
    if value is None or n < MIN_N.get(cid, 1):
        return {**row, "status": "waiting"}
    if better is None:
        return {**row, "status": "info"}
    if better == "target":
        miss = abs(value - target[0])
        return {**row, "target": target[0], "tolerance": tol,
                "status": "drift" if miss > tol else "watch" if miss > tol / 2 else "ok"}
    base = baselines.get(cid)
    need = MIN_N.get(cid, 1)
    if base is None or base.get("n", need) < need:      # a baseline with no recorded n is kept
        source = ("first nightly measurement" if base is None else
                  f"re-set: the {base['set']} baseline had n={base['n']}, under the {need} this check needs")
        base = baselines[cid] = {"value": value, "n": n, "set": today, "source": source}
    worse = (value - base["value"]) if better == "lower" else (base["value"] - value)
    row = {**row, "baseline": base["value"], "baseline_set": base["set"], "tolerance": tol,
           "status": "drift" if worse > tol else "watch" if worse > tol / 2 else "ok"}
    floor = FLOORS.get(cid)
    if floor is not None and (value < floor if better == "higher" else value > floor):
        row.update(status="weak", floor=floor)
    return row


RANK = {"error": 4, "drift": 3, "weak": 3, "watch": 2, "ok": 1, "info": 0, "waiting": 0}


def rollup(checks):
    worst = max((c["status"] for c in checks), key=lambda s: RANK[s], default="waiting")
    if worst in ("info", "waiting"):
        return "ok" if any(c["status"] == "info" for c in checks) else "waiting"
    return worst


# ---------- math ----------
def _phi(z):
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _Phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def lowest_probs(means, sd, steps=800):
    """Chance each team scores lowest when every score is normal(mean, sd): exact integral, no sampling noise."""
    if sd <= 0 or len(means) < 2:
        return [1.0 / len(means)] * len(means)
    lo, hi = min(means) - 6 * sd, max(means) + 6 * sd
    h = (hi - lo) / steps
    out = [0.0] * len(means)
    for k in range(steps + 1):
        x = lo + k * h
        surv = [1 - _Phi((x - m) / sd) for m in means]
        w = h * (0.5 if k in (0, steps) else 1)
        for i, m in enumerate(means):
            p = _phi((x - m) / sd) / sd
            for j, s in enumerate(surv):
                if j != i:
                    p *= s
            out[i] += p * w
    t = sum(out) or 1
    return [o / t for o in out]


def cut_scores(weeks):
    """weeks: [(probabilities {team: p}, actual cut team)]. Log-loss, a coin toss's log-loss, skill (1 - ratio),
    mean rank of the real cut team in the predicted order, and its average predicted chance."""
    if not weeks:
        return None
    ll = sum(-math.log(max(p.get(cut, 0.0), 1e-3)) for p, cut in weeks) / len(weeks)
    uni = sum(math.log(len(p)) for p, _ in weeks) / len(weeks)
    ranks = [1 + sum(1 for v in p.values() if v > p.get(cut, 0.0)) for p, cut in weeks]
    return {"n": len(weeks), "logloss": round(ll, 3), "coin_toss": round(uni, 3), "skill": round(1 - ll / uni, 3),
            "cut_team_rank": round(sum(ranks) / len(ranks), 1), "ranks": ranks,
            "cut_team_chance": round(sum(p.get(cut, 0.0) for p, cut in weeks) / len(weeks), 3)}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def r(x, nd=1):
    return None if x is None else round(x, nd)


# ---------- git history ----------
def git_versions(path):
    """[(unix time, sha)] of every commit that touched `path`, oldest first."""
    out = subprocess.run(["git", "log", "--format=%ct %H", "--", path], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted((int(t), h) for t, h in (line.split() for line in out.splitlines() if line.strip()))


def git_json(sha, path):
    out = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
    return json.loads(out.decode("utf-8"))


def git_page_data(sha, path="docs/war-room-v2/index.html"):
    """The app_data JSON inlined in a War Room v2 page version (`<script type="application/json" id="data">`), or None."""
    text = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    start = text.find('id="data">')
    if start < 0:
        return None
    start += len('id="data">')
    return json.loads(text[start:text.index("</script>", start)])


def last_before(versions, t):
    """sha of the newest version committed before unix time t."""
    best = None
    for ts, sha in versions:
        if ts < t:
            best = sha
    return best


# ---------- league facts (one fetch, shared by every section) ----------
class League:
    """Damon's guillotine league as it stands: weekly matchups, Sleeper's stored projections and stats, every
    claim, who was cut each week, names, kickoffs."""

    def __init__(self, fetch=get_json, players=None, kickoffs=None):
        from warroom.model import BASE, LEAGUE_ID, sleeper_projections, sleeper_week_stats
        from . import sleeper
        lg = fetch(f"{BASE}/league/{LEAGUE_ID}")
        self.rosters = fetch(f"{BASE}/league/{LEAGUE_ID}/rosters")
        users = fetch(f"{BASE}/league/{LEAGUE_ID}/users")
        settings = lg.get("settings") or {}
        self.played = int(settings.get("last_scored_leg") or 0)
        sc = lg["scoring_settings"]
        self.weekly = {w: fetch(f"{BASE}/league/{LEAGUE_ID}/matchups/{w}") or [] for w in range(1, self.played + 1)}
        self.proj = {w: sleeper_projections(w, sc, fetch) for w in range(1, self.played + 1)}
        self.stats = {w: sleeper_week_stats(w, sc, fetch) for w in range(1, self.played + 1)}
        txs = {t["transaction_id"]: t for w in range(1, self.played + 2) for t in fetch(f"{BASE}/league/{LEAGUE_ID}/transactions/{w}") or []}
        self.txs = list(txs.values())
        self.db = players if players is not None else sleeper.players()
        me_uid = fetch(f"{BASE}/user/{SLEEPER_USERNAME}")["user_id"]
        self.me = next(r["roster_id"] for r in self.rosters if r["owner_id"] == me_uid)
        by_uid = {u["user_id"]: u for u in users}
        self.display = {r["roster_id"]: (by_uid.get(r["owner_id"]) or {}).get("display_name") or f"R{r['roster_id']}" for r in self.rosters}
        # the dashboard names teams by team_name when one is set (shq/guillotine.py)
        self.team_name = {r["roster_id"]: ((by_uid.get(r["owner_id"]) or {}).get("metadata") or {}).get("team_name") or self.display[r["roster_id"]]
                          for r in self.rosters}
        # since Q-048 the dashboard names them "Team name (username)" (guillotine.team_label)
        from .guillotine import team_label
        self.label = {r["roster_id"]: team_label(by_uid.get(r["owner_id"])) or self.display[r["roster_id"]] for r in self.rosters}
        self.cut_week = {r["roster_id"]: (r.get("settings") or {}).get("eliminated") for r in self.rosters}
        self.kickoffs = kickoffs or {}

    def pos(self, s):
        return (self.db.get(s) or {}).get("position")

    def name_to_id(self):
        out = {}
        for sid, p in self.db.items():
            n = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            if n:
                out.setdefault(n.lower(), sid)
        return out

    def cut_of(self, w):
        """Roster cut in week w: Sleeper's elimination mark, else the week's lowest score."""
        marked = [rid for rid, cw in self.cut_week.items() if cw == w]
        if marked:
            return marked[0]
        alive = [m for m in self.weekly.get(w, []) if m.get("players")]
        return min(alive, key=lambda m: m["points"] or 0)["roster_id"] if alive and w <= self.played else None

    def claims(self, leg):
        """{player id: [(roster, bid, won)]} for one waiver run (claims processed after week `leg`'s cut)."""
        out = collections.defaultdict(list)
        for t in self.txs:
            if t.get("type") != "waiver" or t.get("status") not in ("complete", "failed") or int(t.get("leg") or 0) != leg:
                continue
            rid, bid = (t.get("roster_ids") or [None])[0], int((t.get("settings") or {}).get("waiver_bid") or 0)
            for pid in t.get("adds") or {}:
                out[pid].append((rid, bid, t["status"] == "complete"))
        return out

    def waiver_run(self, leg):
        """Unix time of the waiver run that processed week `leg`'s freed players (the chop, then Wed 2:15am CT)."""
        from .guillotine import next_waivers
        chop = next((t for t in self.txs if t.get("type") == "chopped" and t.get("leg") == leg), None)
        if chop and chop.get("status_updated"):
            at = dt.datetime.fromtimestamp(chop["status_updated"] / 1000, dt.timezone.utc)
        else:
            k = self.kickoffs.get(leg + 1)
            if not k:
                return None
            at = k - dt.timedelta(days=2)       # Tuesday before the next Thursday game
        return int(next_waivers(at).timestamp())


# ---------- War Room v2 ----------
def team_errors(lg, weeks, value):
    from warroom.model import best_lineup
    errs = []
    for w in weeks:
        for m in lg.weekly.get(w, []):
            if m.get("players"):
                errs.append((m["points"] or 0) - best_lineup(m["players"], lambda s: value(s, w), lg.pos))
    return errs


def blend_value(lg):
    """The pre-Nov-3 projection: half season average, half last 3 (players Sleeper projects at 0 count 0)."""
    def v(s, w):
        if lg.proj.get(w, {}).get(s, 0) <= 0:
            return 0.0
        pts = [lg.stats[k][s] for k in range(1, w) if s in lg.stats.get(k, {})]
        return 0.5 * mean(pts[-3:]) + 0.5 * mean(pts) if pts else 0.0
    return v


def warroom_projection(lg):
    weeks = [w for w in range(3, lg.played + 1)]        # the blend needs two weeks of history
    sl = team_errors(lg, weeks, lambda s, w: lg.proj[w].get(s, 0.0))
    bl = team_errors(lg, weeks, blend_value(lg))
    mae = lambda e: mean([abs(x) for x in e])
    return {"weeks": f"{weeks[0]}-{weeks[-1]}" if weeks else None, "n": len(sl), "sleeper_mae": r(mae(sl)), "blend_mae": r(mae(bl)),
            "sleeper_bias": r(mean(sl)), "edge": r(mae(bl) - mae(sl)) if sl else None}


def warroom_cuts(lg, sds=(14, 18, 22, 27, 32, 36)):
    """In-sample: each past week's cut odds from Sleeper's projections and a normal swing, for several swings."""
    from warroom.model import best_lineup
    per_sd = {}
    for sd in sds:
        rows = []
        for w in range(1, lg.played + 1):
            alive = [m for m in lg.weekly.get(w, []) if m.get("players")]
            cut = lg.cut_of(w)
            if len(alive) < 3 or cut is None:
                continue
            means = [best_lineup(m["players"], lambda s: lg.proj[w].get(s, 0.0), lg.pos) for m in alive]
            rows.append((dict(zip([m["roster_id"] for m in alive], lowest_probs(means, sd))), cut))
        per_sd[sd] = cut_scores(rows)
    return per_sd


def far_week_misses(lg, versions=None, load=git_page_data):
    """How far a team's projected best lineup k weeks ahead (as the War Room v2 page showed it before that
    week's first kickoff) landed from its real score, for k = 1..4, after removing each week's league-wide
    shift. {k: (sd, n)}. Needs the page's Sleeper projections (`pw`, since Nov 3 2026)."""
    from warroom.model import best_lineup
    versions = versions if versions is not None else git_versions("docs/war-room-v2/index.html")
    by_k = collections.defaultdict(list)
    for w in range(1, lg.played + 1):
        kick = lg.kickoffs.get(w)
        if not kick:
            continue
        actual = {m["roster_id"]: m["points"] or 0 for m in lg.weekly.get(w, []) if m.get("players")}
        for k in range(1, 5):
            # the snapshot whose next week to play was w - k + 1, taken before that week kicked off
            k0 = lg.kickoffs.get(w - k + 1)
            sha = last_before(versions, k0.timestamp()) if k0 else None
            D = load(sha) if sha else None
            if not D or D.get("week") != w - k + 1:
                continue
            P = D.get("P") or {}
            if not any("pw" in p for p in P.values()):
                continue
            idx = w - D["week"]
            rows = []
            for t, team in D.get("teams", {}).items():
                rid = int(t)
                if rid not in actual:
                    continue
                pj = best_lineup(team["roster"], lambda s: ((P.get(s) or {}).get("pw") or [])[idx] if idx < len((P.get(s) or {}).get("pw") or []) else 0.0,
                                 lambda s: (P.get(s) or {}).get("p"))
                rows.append(actual[rid] - pj)
            if len(rows) >= 2:
                mu = mean(rows)
                by_k[k] += [x - mu for x in rows]
    return {k: (r((sum(x * x for x in v) / len(v)) ** 0.5), len(v)) for k, v in by_k.items() if v}


def win_chance(b, est, ladder):
    """model.js winChance: share of past claims (winning bid / estimate) a bid of b would have beaten."""
    xs = (ladder["hi"] if est >= 10 and ladder["hi"] else ladder["lo"]) if ladder else None
    if not xs:
        return 0.5 if b >= est else 0.0
    return sum(1 for x in xs if x * est < b or (b == 0 and x == 0)) / len(xs)


def price_for(chance, est, ladder, cap=999):
    for b in range(cap + 1):
        if win_chance(b, est, ladder) >= chance:
            return b
    return None


def ladder_backtest(cases, estimates, positions):
    """Leave one waiver run out: build the ladder from the other runs, then check whether bidding its 50% / 80%
    price would have won the held-out claims about that often (a bid wins when it beats what the player went
    for). Also the raw estimate's miss, and the same coverage by position and season stage."""
    from warroom.build import ladder
    rows = []
    for i, (case, got) in enumerate(zip(cases, estimates)):
        others = [c for j, c in enumerate(cases) if j != i]
        lad = ladder(others, [e for j, e in enumerate(estimates) if j != i]) if others else None
        for (sid, paid), est in zip(case["targets"], got["est"]):
            p50, p80 = price_for(.5, est, lad), price_for(.8, est, lad)
            # as in winChance: a bid wins by beating the price, and $0 "wins" a player nobody claimed
            wins = lambda b: b is not None and (b > paid or b == paid == 0)
            rows.append({"leg": case["leg"], "pos": positions.get(sid) or "?", "est": est, "paid": paid,
                         "won50": wins(p50), "won80": wins(p80),
                         "hi": est >= 10})
    if not rows:
        return None

    def cov(rs):
        return {"n": len(rs), "cov50": r(mean([x["won50"] for x in rs]), 2), "cov80": r(mean([x["won80"] for x in rs]), 2),
                "est_mae": r(mean([abs(x["est"] - x["paid"]) for x in rs]))}
    legs = sorted({x["leg"] for x in rows})
    half = legs[len(legs) // 2] if legs else 0
    split = {f"pos {p}": cov([x for x in rows if x["pos"] == p]) for p in sorted({x["pos"] for x in rows})}
    split.update({f"legs {legs[0]}-{half - 1}" if legs else "early": cov([x for x in rows if x["leg"] < half]),
                  f"legs {half}-{legs[-1]}" if legs else "late": cov([x for x in rows if x["leg"] >= half]),
                  "estimate $10+": cov([x for x in rows if x["hi"]]), "estimate under $10": cov([x for x in rows if not x["hi"]])})
    return {**cov(rows), "by": {k: v for k, v in split.items() if v["n"]}}


def node_estimates(cases):
    from warroom.build import node
    return json.loads(node("--calibrate", data=json.dumps(cases)))


def warroom_prices(now, estimate=node_estimates):
    """The calibration cases exactly as the build makes them, the page's own raw estimates for each, and the
    leave-one-run-out ladder check."""
    from warroom.model import build
    data = build(now)
    cases = data.pop("calib")
    if not cases:
        return None
    pos = {sid: (data["P"].get(sid) or {}).get("p") for c in cases for sid, _ in c["targets"]}
    return ladder_backtest(cases, estimate(cases), pos)


# ---------- our bid recommendations ----------
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name):
    """Lower case, no punctuation, no Jr./Sr./II suffix: "Harold Fannin Jr." and "Harold Fannin" meet."""
    words = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in (name or "").lower()).split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return " ".join(words)


def id_lookup(names):
    """Sleeper id for a player name from lg.name_to_id(): exact (lower case) first, then suffix- and
    punctuation-blind."""
    loose = {}
    for n, sid in names.items():
        loose.setdefault(name_key(n), sid)
    return lambda name: names.get((name or "").lower()) or loose.get(name_key(name))


def rec_outcomes(lg, bids_versions=None, dash_versions=None, load=git_json):
    """For every waiver run since tracking began: the War Room v2 bids (bids.json) and the dashboard's guillotine
    bids (lineups.json) as committed just before the run, against what happened (would the bid have beaten
    every rival? what did the winner pay?). A tie counts as a loss (waiver order decides it)."""
    bids_versions = bids_versions if bids_versions is not None else git_versions("docs/war-room-v2/bids.json")
    dash_versions = dash_versions if dash_versions is not None else git_versions("docs/data/lineups.json")
    find = id_lookup(lg.name_to_id())
    v2, dash, runs = [], [], []
    for leg in range(1, lg.played + 1):
        run = lg.waiver_run(leg)
        if not run or run > now_utc().timestamp():
            continue
        claims = lg.claims(leg)

        def outcome(sid, bid):
            got = claims.get(sid, [])
            winner = next(((rid, b) for rid, b, won in got if won), None)
            mine = next(((b, won) for rid, b, won in got if rid == lg.me), None)
            # the price to beat is what a rival won him for: a higher losing bid failed for another reason
            # (budget used up by other wins, its drop already gone)
            rivals = winner[1] if winner and winner[0] != lg.me else max((b for rid, b, _ in got if rid != lg.me), default=None)
            return {"would_win": bid > 0 and (rivals is None or bid > rivals), "top_rival_bid": rivals,
                    "winner": lg.display.get(winner[0]) if winner else None, "paid": winner[1] if winner else 0,
                    "my_bid": mine[0] if mine else None, "i_won": bool(mine and mine[1])}
        sha = last_before(bids_versions, run)
        B = load(sha, "docs/war-room-v2/bids.json") if sha else None
        if B and (B.get("cut") or {}).get("week") == leg:
            runs.append(leg)
            for row in B.get("bids") or []:
                if not str(row.get("source", "")).startswith("freed"):
                    continue
                o = outcome(row["sleeper_id"], row.get("bid") or 0)
                v2.append({"leg": leg, "player": row["name"], "call": row["call"], "bid": row.get("bid") or 0,
                           "win_chance": row.get("win_chance"), "est_price": row.get("est_price"), "value": row.get("value"), **o})
        sha = last_before(dash_versions, run)
        G = (((load(sha, "docs/data/lineups.json") if sha else {}) or {}).get("leagues", {}).get("Guillotine") or {}).get("advice", {}).get("guillotine")
        if G:
            # since Q-044 the page's bids are War Room v2's own calls; the old model's rows sit under "model"
            M = G.get("model") or ({} if (G.get("bid_source") or {}).get("url") else G)
            for row in (M.get("bids") or []) + ((M.get("freed") or {}).get("players") or []):
                if row.get("v2"):
                    continue
                sid = row.get("sid") or find(row["name"])
                if not sid:
                    continue
                bid = row["price"] if row.get("call") == "bid" else 0
                dash.append({"leg": leg, "player": row["name"], "call": row.get("call"), "bid": bid, "est_price": row.get("price"),
                             "max": row.get("max"), **outcome(sid, bid)})
    rec = [x for x in v2 if x["bid"] > 0]
    paid = {}
    for leg in range(1, lg.played + 1):
        rows = []
        for sid, got in lg.claims(leg).items():
            win = next(((rid, b) for rid, b, won in got if won), None)
            if win and win[1] > 0:
                p = lg.db.get(sid) or {}
                rows.append({"player": p.get("full_name") or sid, "pos": p.get("position"), "winner": lg.display.get(win[0]),
                             "paid": win[1], "bids": len(got), "second": max((b for rid, b, _ in got if rid != win[0]), default=0)})
        if rows:
            paid[leg] = sorted(rows, key=lambda x: -x["paid"])[:6]
    return {
        "runs": runs, "winners_paid": paid, "v2_rows": v2, "dash_rows": dash,
        "would_win": r(mean([x["would_win"] for x in rec]), 2) if rec else None, "n_rec": len(rec),
        "brier": r(mean([(x["win_chance"] - x["would_win"]) ** 2 for x in rec if x["win_chance"] is not None]), 3) if rec else None,
        "est_mae": r(mean([abs((x["est_price"] or 0) - x["paid"]) for x in v2 if x["est_price"]])),
        "n_est": sum(1 for x in v2 if x["est_price"]),
        "dash_est_mae": r(mean([abs((x["est_price"] or 0) - x["paid"]) for x in dash])), "n_dash": len(dash),
        "bargains_skipped": [x for x in v2 if x["call"] in ("Priced out", "Skip") and x["value"] and 0 < x["paid"] < x["value"]],
    }


# ---------- dashboard vs War Room v2 cut odds ----------
def shown_cut_odds(lg, bids_versions=None, dash_versions=None, load=git_json):
    """Each model's cut odds as last committed before the week's first kickoff, scored against the real cut."""
    bids_versions = bids_versions if bids_versions is not None else git_versions("docs/war-room-v2/bids.json")
    dash_versions = dash_versions if dash_versions is not None else git_versions("docs/data/lineups.json")
    by_display = {v: k for k, v in lg.display.items()}
    by_team = {v: k for k, v in lg.team_name.items()}
    by_team.update({v: k for k, v in (getattr(lg, "label", None) or {}).items()})
    v2, dash, weeks = [], [], []
    for w in range(1, lg.played + 1):
        kick, cut = lg.kickoffs.get(w), lg.cut_of(w)
        if not kick or cut is None:
            continue
        t = kick.timestamp()
        sha = last_before(bids_versions, t)
        B = load(sha, "docs/war-room-v2/bids.json") if sha else None
        if B and B.get("week") == w:
            v2.append(({by_display.get(x["team"], x["team"]): x["cut_risk_next_week"] for x in B.get("cut_risks") or []}, cut))
            weeks.append(("v2", w))
        sha = last_before(dash_versions, t)
        G = (((load(sha, "docs/data/lineups.json") if sha else {}) or {}).get("leagues", {}).get("Guillotine") or {}).get("advice", {}).get("guillotine")
        if G and G.get("week") == w:
            dash.append(({by_team.get(x["name"], by_display.get(x["name"], x["name"])): x["cut"] for x in G.get("teams") or []}, cut))
            weeks.append(("dashboard", w))
    return {"v2": cut_scores(v2), "dashboard": cut_scores(dash), "weeks": weeks}


# ---------- NBA trend radar ----------
def radar_health(inputs=None):
    """The radar backtest over the last 14 mornings (shq/radar_backtest.py summary): hit rate of the free agents the
    site showed, of every flag, and every flag's value edge over the old suggestion (mornings with an ownership reading)."""
    from . import radar_backtest as rb
    pool, now_ids, txns, cats, last, dates, owned = inputs or rb.inputs()
    return rb.summary(rb.run(pool, now_ids, txns, cats, last, dates, owned))


# ---------- Pool Picks ----------
def picks_health():
    bt = load_json(ROOT / "picks" / "backtest" / "2026_w1-8.json") or {}
    files = sorted((ROOT / "picks" / "backtest").glob("2026_w1-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    if files:
        bt = load_json(files[-1]) or bt
    rep = bt.get("report") or {}
    brier = rep.get("brier") or {}
    stale = ((rep.get("stale_lines") or {}).get("CFB") or {}).get("gap_1.5_plus") or {}
    card = {"w": 0, "l": 0, "p": 0}
    entered = {"w": 0, "l": 0, "p": 0}
    weeks = []
    for f in sorted((ROOT / "picks" / "data" / "postmortem").glob("*.json")):
        pm = load_json(f) or {}
        weeks.append(pm.get("week"))
        for pool in (pm.get("pools") or {}).values():
            for side, tally in (("card", card), ("entered", entered)):
                for p in (pool.get(side) or {}).get("picks") or []:
                    res = p.get("result")
                    if res is None:
                        continue
                    tally["w" if res == 1 else "l" if res == 0 else "p"] += 1
    rate = lambda t: r(t["w"] / (t["w"] + t["l"]), 3) if t["w"] + t["l"] else None
    return {"backtest_file": files[-1].name if files else None,
            "backtest_n": rep.get("n"), "brier_model": r(brier.get("model"), 3), "brier_market": r(brier.get("market"), 3),
            "brier_gap": r(brier["model"] - brier["market"], 3) if "model" in brier and "market" in brier else None,
            "stale_cover": stale.get("cover"), "stale_n": stale.get("n"),
            "graded_weeks": weeks, "card": card, "card_ats": rate(card), "card_n": card["w"] + card["l"],
            "entered": entered, "entered_rate": rate(entered)}


# ---------- ESPN experts vs Sleeper vs our start/sit calls (shq/experts.py) ----------
MOVE_RE = re.compile(r"^Start (.+?) \(([\d.]+)\) over (.+?) \(([\d.]+)\) at ")
SWITCH_EDGE, SWITCH_SHARE = 0.01, 0.7   # when the blend would be worth switching on (see note)


def sunday_lock(thursday_kickoff):
    """Unix time just before Sunday's early games (16:30 UTC; the 1pm ET slate is 17:00/18:00 UTC)."""
    days = (6 - thursday_kickoff.weekday()) % 7
    sunday = (thursday_kickoff + dt.timedelta(days=days)).replace(hour=16, minute=30, second=0, microsecond=0)
    return int(sunday.timestamp())


def our_calls(weeks, first_kicks, versions=None, load=git_json):
    """Every distinct "Start X over Y" lineup move the league pages showed just before Sunday's early games:
    [(week, league, start name, sit name)], from docs/data/lineups.json's git history."""
    versions = git_versions("docs/data/lineups.json") if versions is None else versions
    out = []
    for w in weeks:
        k = first_kicks.get(w)
        sha = last_before(versions, sunday_lock(k)) if k else None
        if not sha:
            continue
        try:
            data = load(sha, "docs/data/lineups.json")
        except Exception:
            continue
        if data.get("week") not in (None, w):
            continue
        for name, lg in (data.get("leagues") or {}).items():
            for t in ((lg.get("advice") or {}).get("moves") or []):
                m = MOVE_RE.match(t)
                if m:
                    out.append((w, name, m.group(1), m.group(3)))
    return sorted(set(out))


def experts_health(fetch=get_json, players=None, versions=None, load=git_json, first_kicks=None, last=None):
    """Weeks played so far: start/sit pair accuracy of Sleeper's projections, ESPN's experts and a 50/50 blend
    (experts.pairs_accuracy, half-PPR points, players who played), and our own "Start X over Y" calls."""
    from . import experts, sleeper
    from .config import LEAGUES
    if last is None:
        st = fetch(f"{sleeper.BASE}/state/nfl")
        last = int(st.get("week") or 1) - 1 if st.get("season_type") == "regular" else int(st.get("week") or 0)
    weeks = list(range(1, max(0, last) + 1))
    if not weeks:
        return {"acc": {"n": 0}, "calls": {}, "weeks": []}
    src = next(lg for lg in LEAGUES if lg["platform"] == "espn" and lg["sport"] == "nfl" and not lg.get("private"))
    data = experts.compact(experts.fetch(SEASON, src["league_id"], weeks, fetch))
    db = players if players is not None else sleeper.players()
    params = [("season_type", "regular")] + [("position[]", p) for p in ("QB", "RB", "WR", "TE")]
    rows, stats_by_week = {}, {}
    for w in weeks:
        proj = {r["player_id"]: r.get("stats") or {} for r in fetch(f"https://api.sleeper.app/projections/nfl/{SEASON}/{w}", params) or []}
        stats = {r["player_id"]: r.get("stats") or {} for r in fetch(f"https://api.sleeper.app/stats/nfl/{SEASON}/{w}", params) or []}
        stats_by_week[w] = stats
        rows[w] = experts.backtest_rows(data, w, proj, stats, db)
    acc = experts.pairs_accuracy({w: r for w, r in rows.items() if r})
    # our calls: did the player we said to start outscore the one we said to sit; what did the experts say
    look = id_lookup({(p.get("full_name") or "").lower(): sid for sid, p in db.items() if p.get("full_name")})
    first_kicks = first_kicks if first_kicks is not None else kickoffs(weeks)
    calls = {"n": 0, "right": 0, "experts_split": 0, "split_right": 0, "agree": 0, "lines": []}
    for w, lg, start, sit in our_calls(weeks, first_kicks, versions, load):
        a, b = look(start), look(sit)
        sa, sb = stats_by_week[w].get(a), stats_by_week[w].get(b)
        if not (sa and sb):
            continue
        pa, pb = sa.get("pts_half_ppr") or 0.0, sb.get("pts_half_ppr") or 0.0
        if pa == pb:
            continue
        right = pa > pb
        calls["n"] += 1
        calls["right"] += right
        rk = {x["sid"]: x["rk"] for x in rows.get(w) or []}
        ra, rb = rk.get(a), rk.get(b)
        if ra and rb:
            if ra > rb:   # the experts ranked the player we benched ahead
                calls["experts_split"] += 1
                calls["split_right"] += right
            else:
                calls["agree"] += 1
        calls["lines"].append(f"Week {w} {lg}: start {start} ({pa:.1f}) over {sit} ({pb:.1f}) {'right' if right else 'wrong'}"
                              + (f"; experts had them #{ra} vs #{rb}" if ra and rb else ""))
    calls["rate"] = r(calls["right"] / calls["n"], 3) if calls["n"] else None
    calls["split_rate"] = r(calls["split_right"] / calls["experts_split"], 3) if calls["experts_split"] else None
    return {"acc": acc, "calls": calls, "weeks": weeks}


# ---------- assemble ----------
def kickoffs(weeks):
    """{week: first kickoff (UTC datetime)} from ESPN's public scoreboard."""
    from . import espn
    out = {}
    for w in weeks:
        try:
            g = espn.games(SEASON, w)
        except Exception:
            continue
        ks = [x["kickoff"] for x in g.values() if x.get("kickoff")]
        if ks:
            out[w] = min(ks)
    return out


def section(name, title, fn):
    try:
        checks, details, notes = fn()
        return {"id": name, "title": title, "status": rollup(checks), "checks": checks, "details": details, "notes": notes}
    except Exception as e:  # one broken model must not hide the others
        traceback.print_exc()
        return {"id": name, "title": title, "status": "error", "checks": [], "details": {}, "notes": [],
                "error": f"{type(e).__name__}: {e}"[:300]}


def build(now=None, baselines=None, lg=None, estimate=node_estimates):
    now = now or now_utc()
    today = now.date().isoformat()
    baselines = baselines if baselines is not None else (load_json(BASELINES) or {})
    j = lambda cid, value, n: judge(cid, value, n, baselines, today)
    state = {}

    def league():
        if "lg" not in state:
            state["lg"] = lg or League(kickoffs=None)
            if not state["lg"].kickoffs:
                state["lg"].kickoffs = kickoffs(range(1, state["lg"].played + 2))
        return state["lg"]

    def wr():
        L = league()
        pj = warroom_projection(L)
        from warroom.model import measure_sd
        sd, sd_n = measure_sd(L.weekly, L.proj, L.pos)
        now_sd = round(sd or 22)
        cuts = warroom_cuts(L, sds=sorted({14, 18, now_sd, 27, 32, 36}))
        cur = cuts.get(now_sd) or {}
        best = min((s for s in cuts if cuts[s]), key=lambda s: cuts[s]["logloss"], default=None)
        far = far_week_misses(L)
        checks = [j("wr.proj_mae", pj["sleeper_mae"], pj["n"]), j("wr.blend_mae", pj["blend_mae"], pj["n"]),
                  j("wr.proj_edge", pj["edge"], pj["n"]), j("wr.swing", sd, sd_n)]
        for k in (2, 3, 4):
            checks.append(j(f"wr.swing_k{k}", *(far.get(k) or (None, 0))))
        checks += [j("wr.cut_skill", cur.get("skill"), cur.get("n", 0)), j("wr.best_sd", best, (cuts.get(best) or {}).get("n", 0))]
        notes = []
        prices = None
        try:
            prices = warroom_prices(now, estimate)
        except Exception as e:
            traceback.print_exc()
            checks.append({"id": "wr.prices", "label": f"Price ladder check failed: {type(e).__name__}: {e}"[:300], "value": None,
                           "n": 0, "unit": "", "status": "error"})
        if prices:
            checks += [j("wr.price_est_mae", prices["est_mae"], prices["n"]),
                       j("wr.ladder_cov50", prices["cov50"], prices["n"]), j("wr.ladder_cov80", prices["cov80"], prices["n"])]
        if cur.get("skill") is not None and cur["skill"] <= 0:
            notes.append(f"Cut odds at the measured {now_sd}-pt swing scored worse than a coin toss over {cur['n']} weeks "
                         f"(the real cut team ranked {cur['ranks']} by predicted risk); a {best}-pt swing would have scored best.")
        if 1 in far:
            notes.append(f"Far-week misses as shown on the page: " + ", ".join(f"{k} wk ahead {v[0]} pts (n={v[1]})" for k, v in sorted(far.items())))
        else:
            notes.append("Far-week projections: waiting for weeks played after Nov 3 (the page has carried Sleeper's projections since then).")
        details = {"projection": pj, "swing": {"sd": sd, "n": sd_n, "by_weeks_ahead": far}, "cuts_by_swing": cuts, "prices": prices}
        return checks, details, notes

    def recs():
        L = league()
        o = rec_outcomes(L)
        checks = [j("rec.would_win", o["would_win"], o["n_rec"]), j("rec.win_brier", o["brier"], o["n_rec"]),
                  j("rec.est_mae", o["est_mae"], o["n_est"]), j("gd.dash_price_mae", o["dash_est_mae"], o["n_dash"])]
        notes = [] if o["runs"] else ["No waiver run has processed since War Room v2's bids.json started (Oct 31); "
                                      "the first is Wed Nov 4, 2:15am CT."]
        for x in o["bargains_skipped"]:
            notes.append(f"Week {x['leg']}: {x['player']} went for ${x['paid']} ({x['winner']}) although his value to you was ${x['value']} "
                         f"and the call was {x['call']}.")
        return checks, o, notes

    def gd():
        L = league()
        s = shown_cut_odds(L)
        v2, dash = s["v2"] or {}, s["dashboard"] or {}
        checks = [j("gd.v2_skill", v2.get("skill"), v2.get("n", 0)), j("gd.dash_skill", dash.get("skill"), dash.get("n", 0))]
        notes = []
        if v2 and dash:
            notes.append(f"Same weeks: War Room v2 log-loss {v2['logloss']} vs dashboard {dash['logloss']} (coin toss {dash['coin_toss']}).")
        return checks, s, notes

    def nba():
        h = radar_health()
        sh, fl = h["shown"], h["flags"]
        checks = [j("radar.held", sh["held_rate"], sh["n"]), j("radar.held_all", fl["held_rate"], fl["n"]),
                  j("radar.edge", fl["edge"], fl["edge_n"])]
        notes = [f"{h['mornings']} mornings replayed; each free agent counted once, at his first flag, on his team's next 3 games "
                 f"(a missed game = 0 min). Shown = the 4 a morning the site lists. Edge: every flag vs the 3 most-owned free "
                 f"agents by that morning's % rostered, {h['wire_mornings']} mornings (state/nba_owned.json starts Nov 3); "
                 f"shown flags alone {sh['edge']} (n={sh['edge_n']})."]
        return checks, h, notes

    def pk():
        h = picks_health()
        checks = [j("picks.brier_gap", h["brier_gap"], h["backtest_n"] or 0), j("picks.stale_cover", h["stale_cover"], h["stale_n"] or 0),
                  j("picks.card_ats", h["card_ats"], h["card_n"])]
        notes = [f"Backtest {h['backtest_file']} is re-run by the laptop (needs the CFBD key); this job reads it."]
        return checks, h, notes

    def exp():
        h = experts_health()
        a, c = h["acc"], h["calls"]
        last = a.get("weeks", {}).get(max(a["weeks"])) if a.get("weeks") else None
        checks = [j("exp.sleeper_acc", a.get("sleeper"), a["n"]), j("exp.experts_acc", a.get("experts"), a["n"]),
                  j("exp.blend_edge", a.get("edge"), a["n"]),
                  j("exp.last_week_edge", r(last["blend"] - last["sleeper"], 4) if last else None, (last or {}).get("n", 0)),
                  j("exp.calls_right", c.get("rate"), c.get("n", 0)), j("exp.calls_vs_experts", c.get("split_rate"), c.get("experts_split", 0))]
        notes = []
        if a["n"]:
            wk = len(a["weeks"])
            notes.append(f"Weeks {min(a['weeks'])}-{max(a['weeks'])}: {a['n']} pairs of players at a position ranked within 12 spots by "
                         f"the experts, both played, half-PPR. Sleeper {a['sleeper']:.1%}, experts {a['experts']:.1%}, blend {a['blend']:.1%}; "
                         f"the blend beat Sleeper in {a['blend_wins']} of {wk} weeks.")
            if a["edge"] >= SWITCH_EDGE and a["blend_wins"] >= SWITCH_SHARE * wk:
                notes.append(f"The blend now clearly beats Sleeper alone (+{a['edge']:.1%}, {a['blend_wins']} of {wk} weeks): worth "
                             "switching start/sit to it (shq/experts.py).")
            else:
                notes.append("Start/sit stays on Sleeper's projections; the experts are shown next to each call (switch when the blend "
                             f"is {SWITCH_EDGE:.0%}+ better in {SWITCH_SHARE:.0%}+ of weeks).")
        if c.get("n"):
            notes.append(f"Our lineup moves: {c['right']} of {c['n']} right; the experts disagreed on {c['experts_split']} and we were right on "
                         f"{c['split_right']} of those.")
        return checks, h, notes

    sections = [
        section("experts", "Start/sit: Sleeper vs ESPN's experts", exp),
        section("warroom", "War Room v2 (guillotine bids)", wr),
        section("recs", "Our guillotine bids vs what happened", recs),
        section("guillotine", "Guillotine cut odds as shown (dashboard vs War Room v2)", gd),
        section("radar", "NBA trend radar", nba),
        section("picks", "Pool Picks", pk),
    ]
    flags = [{"section": s["id"], **c} for s in sections for c in s["checks"] if c["status"] in ("drift", "weak", "watch", "error")]
    flags += [{"section": s["id"], "id": s["id"] + ".error", "label": s["error"], "status": "error"} for s in sections if s.get("error")]
    counts = collections.Counter(c["status"] for s in sections for c in s["checks"])
    return {"generated": iso(now), "summary": {k: counts.get(k, 0) for k in ("ok", "watch", "drift", "weak", "waiting", "info")}
            | {"errors": sum(1 for s in sections if s.get("error"))},
            "flags": flags, "sections": sections}, baselines



def main(argv):
    baselines = load_json(BASELINES) or {}
    out, baselines = build(baselines=baselines)
    save_json(OUT, out)
    save_json(BASELINES, baselines)
    s = out["summary"]
    print(f"health: {s['ok']} ok, {s['watch']} watch, {s['drift']} drift, {s['weak']} weak, {s['waiting']} waiting, {s['errors']} errors")
    if "--print" in argv:
        for sec in out["sections"]:
            print(f"\n[{sec['status']}] {sec['title']}" + (f"  ERROR {sec['error']}" if sec.get("error") else ""))
            for c in sec["checks"]:
                print(f"  {c['status']:8} {c['label']}: {c['value']} (n={c['n']}" + (f", baseline {c['baseline']}" if "baseline" in c else "") + ")")
            for n in sec["notes"]:
                print("  - " + n)


if __name__ == "__main__":
    main(sys.argv[1:])
