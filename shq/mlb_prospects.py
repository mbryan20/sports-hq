"""Prospect model and dynasty watch list for 3-Ball Dynasty baseball (plans/baseball.md). Free reads, no AI.

Model: a prospect's season at his highest full level, scored on
- performance against that level (OPS and K% for hitters, K-BB% and ERA for pitchers, as z-scores vs the level),
- age vs level (years younger than the level's average player),
- level (A=0 .. AAA=3),
- MLB Pipeline's Top 100 rank, when he has one (a "scouts" term; 0 when unranked).
Weights come from a logistic fit on the 2021 and 2022 cohorts. The backtest scores the 2023 and 2024 cohorts with those
weights and checks who became a useful MLB player in the next two seasons, against three baselines: performance alone,
performance + level (no age), and Pipeline's next-preseason rank alone. The watch list uses weights refit on 2021-2024.

Useful = any season in the next two with 350+ PA and (OPS .750+ or 20+ SB) for hitters; 100+ IP with ERA 4.00 or
better, or 20+ saves+holds with ERA 3.50 or better, for pitchers.

Run: py -m shq.mlb_prospects [--write]  (--write saves docs/data/mlb_prospects.json and the backtest numbers)."""
import json
import math
import sys
import unicodedata

from . import mlb_data as md
from .common import ROOT, get_json

LEVELS = {14: 0, 13: 1, 12: 2, 11: 3}
LNAME = {0: "A", 1: "A+", 2: "AA", 3: "AAA"}
TRAIN, TEST, ALL = (2021, 2022), (2023, 2024), (2021, 2022, 2023, 2024)
WATCH_YEAR = 2026
MAX_AGE = 25
LEAGUE = 142878
MY_TEAM = 6


def outs(ip):
    if ip in (None, ""):
        return 0
    whole, _, frac = str(ip).partition(".")
    return int(whole or 0) * 3 + int(frac or 0)


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().replace(".", "")
    for suf in (" jr", " ii", " iii", " iv"):
        s = s.replace(suf, "")
    return " ".join(s.split())


# ---------------------------------------------------------------- data

def mlb_lines(group):
    """{year: {id: line}} MLB regular season 2018-2026."""
    return {y: {r["id"]: r for r in md.season_stats(y, group, 1)} for y in range(2018, 2027)}


def cohort(year, group):
    """One row per prospect: his line at the highest level he played enough at, with level norms."""
    rows = []
    for sport in LEVELS:
        rows += md.season_stats(year, group, sport)
    hit = group == "hitting"
    vol = (lambda r: r.get("plateAppearances") or 0) if hit else (lambda r: outs(r.get("inningsPitched")) / 3)
    need, total_need = (80, 150) if hit else (20, 40)
    norms = {}
    for lv in LEVELS.values():
        g = [r for r in rows if LEVELS[r["sport"]] == lv and vol(r) >= (100 if hit else 30) and r.get("age")]
        w = sum(vol(r) for r in g) or 1
        feats = {"age": [r["age"] for r in g]}
        if hit:
            feats["ops"] = [float(r["ops"]) for r in g]
            feats["k"] = [r["strikeOuts"] / r["plateAppearances"] for r in g]
        else:
            feats["kbb"] = [(r["strikeOuts"] - r["baseOnBalls"]) / max(r["battersFaced"], 1) for r in g]
            feats["era"] = [float(r["era"]) if r.get("era") not in (None, "-.--") else 9.0 for r in g]
        norms[lv] = {}
        for k, vals in feats.items():
            m = sum(v * vol(r) for v, r in zip(vals, g)) / w
            sd = (sum(vol(r) * (v - m) ** 2 for v, r in zip(vals, g)) / w) ** 0.5 or 1
            norms[lv][k] = (m, sd)
    by = {}
    for r in rows:
        by.setdefault(r["id"], []).append(r)
    out = []
    for pid, rs in by.items():
        if sum(vol(r) for r in rs) < total_need:
            continue
        ok = [r for r in rs if vol(r) >= need and r.get("age")]
        if not ok:
            continue
        top = max(ok, key=lambda r: (LEVELS[r["sport"]], vol(r)))
        lv, nm = LEVELS[top["sport"]], norms[LEVELS[top["sport"]]]
        row = {"id": pid, "name": top["name"], "age": top["age"], "lvl": lv, "team": top["team"],
               "team_id": top["team_id"], "pos": top["pos"], "year": year, "vol": round(sum(vol(r) for r in rs)),
               "age_gap": nm["age"][0] - top["age"]}
        if hit:
            k = top["strikeOuts"] / top["plateAppearances"]
            row.update(ops=float(top["ops"]), k=k, hr=sum(r.get("homeRuns") or 0 for r in rs),
                       sb=sum(r.get("stolenBases") or 0 for r in rs),
                       perf=(float(top["ops"]) - nm["ops"][0]) / nm["ops"][1], perf2=-(k - nm["k"][0]) / nm["k"][1])
        else:
            kbb = (top["strikeOuts"] - top["baseOnBalls"]) / max(top["battersFaced"], 1)
            era = float(top["era"]) if top.get("era") not in (None, "-.--") else 9.0
            row.update(kbb=kbb, era=era, gs=sum(r.get("gamesStarted") or 0 for r in rs),
                       perf=(kbb - nm["kbb"][0]) / nm["kbb"][1], perf2=-(era - nm["era"][0]) / nm["era"][1])
        out.append(row)
    return out


def label(rows, group, mlb):
    """Drop players past rookie limits or too old; add `useful` (next two MLB seasons) and `debut_next`."""
    hit = group == "hitting"
    out = []
    for r in rows:
        y = r["year"]
        before = sum((mlb[x].get(r["id"]) or {}).get("plateAppearances" if hit else "battersFaced", 0) or 0
                     for x in mlb if x <= y)
        if before > (130 if hit else 200) or r["age"] > MAX_AGE:
            continue
        nxt = [mlb[x].get(r["id"]) for x in (y + 1, y + 2) if x in mlb]
        nxt = [n for n in nxt if n]
        if hit:
            useful = any(n.get("plateAppearances", 0) >= 350 and (float(n["ops"]) >= 0.750 or n.get("stolenBases", 0) >= 20)
                         for n in nxt)
        else:
            def good(n):
                era = float(n["era"]) if n.get("era") not in (None, "-.--") else 9
                return (outs(n.get("inningsPitched")) >= 300 and era <= 4.0) or \
                       ((n.get("saves", 0) + n.get("holds", 0)) >= 20 and era <= 3.5)
            useful = any(good(n) for n in nxt)
        r = dict(r, useful=useful, debut_next=bool(mlb.get(y + 1, {}).get(r["id"])))
        out.append(r)
    return out


# ---------------------------------------------------------------- model

FEATS = ("perf", "perf2", "age_gap", "lvl", "pipe")


def pipe_term(rank):
    """Pipeline Top 100 rank as a feature: 1 at #1 sliding to ~0.3 at #100, 0 unranked."""
    return 0.0 if not rank else 1.0 - 0.7 * (rank - 1) / 99


def x_of(r, feats):
    return [1.0] + [r[f] for f in feats]


def fit(rows, feats, l2=0.5, steps=3000, lr=0.1):
    """Plain logistic regression (gradient descent, small ridge); returns weights incl. intercept.
    Uses numpy (laptop only; scoring with fixed weights needs nothing but the standard library)."""
    import numpy as np
    X = np.array([x_of(r, feats) for r in rows])
    y = np.array([1.0 if r["useful"] else 0.0 for r in rows])
    w = np.zeros(X.shape[1])
    reg = np.r_[0.0, np.ones(X.shape[1] - 1)] * l2 / len(rows)
    for _ in range(steps):
        p = 1 / (1 + np.exp(-X @ w))
        w -= lr * (X.T @ (p - y) / len(rows) + reg * w)
    return [float(v) for v in w]


def prob(w, r, feats):
    return 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, x_of(r, feats)))))


def auc(scores, ys):
    pos = [s for s, y in zip(scores, ys) if y]
    neg = [s for s, y in zip(scores, ys) if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def top_hits(scores, ys, k):
    order = sorted(range(len(ys)), key=lambda i: -scores[i])[:k]
    return sum(ys[i] for i in order)


def evaluate(group, mlb, pipes):
    """Backtest numbers for one group (hitting / pitching)."""
    data = {y: label(cohort(y, group), group, mlb) for y in ALL}
    for y, rows in data.items():
        nxt = pipes.get(y + 1, {})
        for r in rows:
            r["pipe_rank"] = nxt.get(r["id"])
            r["pipe"] = pipe_term(r["pipe_rank"])
    train = [r for y in TRAIN for r in data[y]]
    models = {
        "perf only": ("perf",),
        "perf + level (no age)": ("perf", "perf2", "lvl"),
        "stats model (perf + age + level)": ("perf", "perf2", "age_gap", "lvl"),
        "stats model + Pipeline rank": FEATS,
    }
    weights = {name: fit(train, f) for name, f in models.items()}
    res = {"weights": {k: [round(x, 3) for x in v] for k, v in weights.items()}, "test": {}}
    for y in TEST:
        rows = data[y]
        ys = [r["useful"] for r in rows]
        k = sum(1 for r in rows if r["pipe_rank"])
        t = {"n": len(rows), "useful": sum(ys), "pipeline_ranked": k}
        for name, f in models.items():
            sc = [prob(weights[name], r, f) for r in rows]
            t[name] = {"auc": round(auc(sc, ys), 3), "top25": top_hits(sc, ys, 25), "top50": top_hits(sc, ys, 50),
                       f"top{k}": top_hits(sc, ys, k)}
        pr = [-(r["pipe_rank"] or 999) for r in rows]
        t["Pipeline rank only"] = {"auc": round(auc(pr, ys), 3), "top25": top_hits(pr, ys, 25),
                                   "top50": top_hits(pr, ys, 50), f"top{k}": top_hits(pr, ys, k)}
        # the edge: useful players Pipeline's Top 100 missed, and how many the stats model had in its top 50
        f = models["stats model (perf + age + level)"]
        sc = [prob(weights["stats model (perf + age + level)"], r, f) for r in rows]
        top50 = set(sorted(range(len(rows)), key=lambda i: -sc[i])[:50])
        missed = [i for i, r in enumerate(rows) if r["useful"] and not r["pipe_rank"]]
        t["useful but not on Pipeline"] = {"n": len(missed), "in stats top 50": sum(i in top50 for i in missed),
                                           "names": [rows[i]["name"] for i in missed if i in top50]}
        res["test"][str(y)] = t
    # call-up timing: share who debut the next season, by level and age gap
    allr = [r for y in ALL for r in data[y]]
    timing = {}
    for lv in range(4):
        for band, test in (("young", lambda g: g >= 1.5), ("normal", lambda g: -0.5 <= g < 1.5), ("old", lambda g: g < -0.5)):
            g = [r for r in allr if r["lvl"] == lv and test(r["age_gap"])]
            if g:
                timing[f"{LNAME[lv]} {band}"] = [sum(r["debut_next"] for r in g), len(g)]
    res["debut_next_season"] = timing
    final = fit(allr, FEATS)
    res["final_weights"] = [round(x, 3) for x in final]
    return res, final


# ---------------------------------------------------------------- watch list

def espn_pool():
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/2026/segments/0/leagues/{LEAGUE}"
    hdr = {"x-fantasy-filter": json.dumps({"players": {"limit": 4000, "sortPercOwned": {"sortPriority": 1,
                                                                                       "sortAsc": False}}})}
    pool = get_json(url, {"view": "kona_player_info"}, headers=hdr).get("players") or []
    teams = get_json(url, {"view": ["mTeam", "mRoster"]})["teams"]
    owner = {}
    for t in teams:
        for e in t["roster"]["entries"]:
            owner[e["playerId"]] = (t["id"], t.get("name") or "")
    out = {}
    for p in pool:
        pl = p["player"]
        out.setdefault(norm(pl["fullName"]), []).append(
            {"espn_id": pl["id"], "team": ESPN_TEAM.get(pl.get("proTeamId"), "FA"),
             "owned": round((pl.get("ownership") or {}).get("percentOwned", 0), 1), "owner": owner.get(pl["id"])})
    return out


# ESPN proTeamId -> MLB Stats API abbreviation (ESPN's own abbreviations differ for a few teams)
ESPN_TEAM = {1: "BAL", 2: "BOS", 3: "LAA", 4: "CWS", 5: "CLE", 6: "DET", 7: "KC", 8: "MIL", 9: "MIN", 10: "NYY",
             11: "ATH", 12: "SEA", 13: "TEX", 14: "TOR", 15: "ATL", 16: "CHC", 17: "CIN", 18: "HOU", 19: "LAD",
             20: "WSH", 21: "NYM", 22: "PHI", 23: "PIT", 24: "STL", 25: "SD", 26: "SF", 27: "COL", 28: "MIA",
             29: "AZ", 30: "TB", 0: "FA"}


def lookup(pool, name, org):
    """The ESPN entry for this prospect: same name AND his organization (or no MLB team on ESPN). Two players can share
    a name (a minor-league Cade Smith is not the Guardians' reliever), so a name alone never matches."""
    for e in pool.get(norm(name)) or []:
        if e["team"] == org or e["team"] == "FA":
            return e
    return None


def orgs(season):
    d = md.stats_api("/teams", {"sportIds": "11,12,13,14,16", "season": season}, max_age=24 * 30)
    return {t["id"]: t.get("parentOrgId") for t in d.get("teams") or []}


def forty_man(season):
    d = md.stats_api("/teams", {"sportId": 1, "season": season}, max_age=24 * 30)
    out, names = set(), {}
    for t in d.get("teams") or []:
        names[t["id"]] = t.get("abbreviation") or t["name"]
        r = md.stats_api(f"/teams/{t['id']}/roster", {"rosterType": "40Man", "season": season}, max_age=24 * 7)
        out |= {e["person"]["id"] for e in r.get("roster") or []}
    return out, names


def blockers(mlb_hit, org_of_mlb, season):
    """{(org, pos): [names]} MLB regulars (400+ PA this season, 31 or younger) at each position."""
    out = {}
    for r in mlb_hit[season].values():
        if (r.get("plateAppearances") or 0) >= 400 and (r.get("age") or 99) <= 31:
            out.setdefault((r["team_id"], r["pos"]), []).append(r["name"])
    return out


def why(r, hit, afl):
    lv = LNAME[r["lvl"]]
    gap = r["age_gap"]
    young = f"{gap:.1f} yrs younger than the {lv} average" if gap >= 0.5 else (
        f"{-gap:.1f} yrs older than the {lv} average" if gap <= -0.5 else f"about the {lv} average age")
    if hit:
        s = (f"{r['age']} in {lv}, {young}; {r['ops']:.3f} OPS ({r['perf']:+.1f} sd vs {lv}), {100 * r['k']:.0f}% K, "
             f"{r['hr']} HR, {r['sb']} SB")
    else:
        s = f"{r['age']} in {lv}, {young}; {100 * r['kbb']:.0f}% K-BB ({r['perf']:+.1f} sd vs {lv}), {r['era']:.2f} ERA"
    if afl:
        s += f"; Fall League {afl}"
    return s


def key(name):
    """Loose name key for the league sheet: last name + first 3 letters ("Leodalis De Vries" = "Leo De Vries")."""
    parts = norm(name).split()
    return (parts[-1] if parts else "", parts[0][:3] if parts else "")


def sheet_holders():
    """{key: owner} from the laptop's private copy of the 3-Ball league sheet (minor-league spots); {} elsewhere."""
    # gitignored, so a worktree doesn't have it: fall back to the main checkout (worktrees live in <repo>/.claude/worktrees)
    path = next((p for p in (md.ROOT / "state" / "dynasty_sheet.json",
                             md.ROOT.parents[2] / "state" / "dynasty_sheet.json") if p.exists()), None)
    if not path:
        return {}, None
    sh = json.loads(path.read_text(encoding="utf-8"))
    head = sh["minors"][0]
    out = {}
    for row in sh["minors"][1:]:
        for c, name in enumerate(row):
            if name.strip() and c < len(head):
                out[key(name)] = head[c]
    return out, sh


def watch(weights, mlb_hit, mlb_pit, pipes):
    """(public list, unscored Pipeline names, private rows). Public rows carry only public facts: ESPN rosters
    (the league is public), Michael's own minors (already public in state/dynasty_assets.json), Pipeline, MLB data.
    Who holds other prospects in the league sheet's minor-league spots is private league data: private rows only."""
    pool = espn_pool()
    org = orgs(WATCH_YEAR)
    forty, abbr = forty_man(WATCH_YEAR)
    block = blockers(mlb_hit, org, WATCH_YEAR)
    holders, _ = sheet_holders()
    assets = json.loads((md.ROOT / "state" / "dynasty_assets.json").read_text(encoding="utf-8"))
    mine_minors = {key(n) for n in assets.get("minors") or []}
    afl = {}
    for grp in ("hitting", "pitching"):
        for r in md.season_stats(WATCH_YEAR, grp, 17, max_age=24, league_id=119):
            afl[r["id"]] = (f"{r['ops']} OPS in {r['plateAppearances']} PA" if grp == "hitting"
                            else f"{r['era']} ERA, {r['strikeOuts']} K in {r['inningsPitched']} IP")
    cur = pipes.get(WATCH_YEAR, {})
    out = []
    for grp, mlb, w in (("hitting", mlb_hit, weights["hitting"]), ("pitching", mlb_pit, weights["pitching"])):
        hit = grp == "hitting"
        for r in label(cohort(WATCH_YEAR, grp), grp, mlb):
            r["pipe_rank"] = cur.get(r["id"])
            r["pipe"] = pipe_term(r["pipe_rank"])
            o = org.get(r["team_id"], r["team_id"])
            e = lookup(pool, r["name"], abbr.get(o, ""))
            espn_team = e["owner"] if e and e["owner"] else None
            mine = bool(espn_team and espn_team[0] == MY_TEAM) or key(r["name"]) in mine_minors
            out.append({"name": r["name"], "mlbam": r["id"],
                        "pos": r["pos"] if hit else ("SP" if r["gs"] >= 8 else "RP"),
                        "age": r["age"], "level": LNAME[r["lvl"]], "org": abbr.get(o, ""),
                        "p_useful": round(prob(w, r, FEATS), 3),
                        "p_stats": round(prob(w, dict(r, pipe=0.0), FEATS), 3),
                        "pipeline": r["pipe_rank"], "forty_man": r["id"] in forty,
                        "espn_owned": e["owned"] if e else None,
                        "espn_roster": None if not espn_team else ("mine" if espn_team[0] == MY_TEAM else espn_team[1]),
                        "mine": mine, "blockers": (block.get((o, r["pos"]), []) if hit else [])[:2],
                        "why": why(r, hit, afl.get(r["id"]))})
    out.sort(key=lambda x: -x["p_useful"])
    srank = {x["mlbam"]: i + 1 for i, x in enumerate(sorted(out, key=lambda x: -x["p_stats"]))}
    for i, x in enumerate(out):
        x["rank"] = i + 1
        s = srank[x["mlbam"]]
        if s <= 40 and (not x["pipeline"] or x["pipeline"] > 75):
            x["edge"] = f"Stats rank #{s}: the numbers like him more than Pipeline does"
        elif x["pipeline"] and x["pipeline"] <= 25 and s > 150:
            x["edge"] = f"Pipeline #{x['pipeline']} but stats rank #{s}: scouting, not numbers"
    have = {x["mlbam"] for x in out}
    missing = [pid for pid in cur if pid not in have]
    people = {}
    if missing:
        d = md.stats_api("/people", {"personIds": ",".join(map(str, missing)), "hydrate": "currentTeam"}, max_age=24 * 7)
        people = {p["id"]: p for p in d.get("people") or []}
    unscored = []
    for pid in sorted(missing, key=lambda p: cur[p]):
        p = people.get(pid) or {}
        nm = p.get("fullName", str(pid))
        team = (p.get("currentTeam") or {}).get("id")
        e = lookup(pool, nm, abbr.get(org.get(team, team), ""))
        espn_team = e["owner"] if e and e["owner"] else None
        unscored.append({"name": nm, "mlbam": pid, "pipeline": cur[pid],
                         "pos": (p.get("primaryPosition") or {}).get("abbreviation", ""),
                         "age": p.get("currentAge"), "draft": p.get("draftYear"),
                         "espn_roster": None if not espn_team else ("mine" if espn_team[0] == MY_TEAM else espn_team[1]),
                         "mine": bool(espn_team and espn_team[0] == MY_TEAM) or key(nm) in mine_minors})
    private = [dict(x, sheet=holders.get(key(x["name"]))) for x in out + unscored]
    return out, unscored, private


def private_doc(private, path):
    """Markdown for Michael's private Doc: availability from the league sheet (laptop only, never committed)."""
    _, sh = sheet_holders()
    me = (sh or {}).get("me", "MB")
    taken = lambda x: x.get("sheet") or x.get("espn_roster")
    scored = [x for x in private if "p_useful" in x]
    mine = [x for x in scored if x.get("sheet") == me or x.get("espn_roster") == "mine"]
    avail = [x for x in scored if not taken(x)]
    others = [x for x in scored if taken(x) and x not in mine]
    pct = lambda x: f"{round(100 * x['p_useful'])}%"
    pipe = lambda x: f"#{x['pipeline']}" if x["pipeline"] else "-"
    hdr = "| Rank | Player | Chance useful | Pipeline | Why |\n|---|---|---|---|---|"
    line = lambda x: (f"| {x['rank']} | **{x['name']}** {x['pos']}, {x['org']} | {pct(x)} | {pipe(x)} | {x['why']}"
                      + (f" ({x['edge']})" if x.get("edge") else "") + " |")
    out = ["# 3-Ball baseball: prospect watch list (private)",
           f"Built {dt_now()} from 2026 minor-league stats, the Fall League and Pipeline's current Top 100. "
           f"Availability from the league sheet (minors log through {(sh or {}).get('minors_updated', '?')}, "
           f"read {(sh or {}).get('read', '?')}) and ESPN rosters. Chance useful = the model's estimate that he becomes a "
           "useful MLB player within two seasons. Estimates, not facts.",
           "", "## Draft targets: not on any 3-Ball ESPN roster or minor-league spot", hdr]
    out += [line(x) for x in avail[:30]]
    pu = [x for x in private if "p_useful" not in x and not taken(x)]
    if pu:
        out += ["", "Also available, on Pipeline's Top 100 but with too few 2026 minor-league games to score (mostly 2026 MLB draftees; also injuries or MLB time): "
                + "; ".join(f"{x['name']} (#{x['pipeline']}, {x['pos']}, drafted {x['draft'] or '?'})" for x in pu)]
    out += ["", "## Yours (league-sheet minors and ESPN roster)", hdr] + [line(x) for x in mine]
    seen = {key(x["name"]) for x in mine}
    left = [n for r in (sh or {}).get("minors", [[]])[1:] for c, n in enumerate(r)
            if n.strip() and c < len(sh["minors"][0]) and sh["minors"][0][c] == me and key(n) not in seen]
    if left:
        out += ["", "Not scored (too few 2026 minor-league games, or past the rookie limits): " + ", ".join(left)
                + ". Pipeline ranks: " + ", ".join(f"{x['name']} #{x['pipeline']}" for x in private
                                                   if "p_useful" not in x and key(x["name"]) in {key(n) for n in left})]
    assets = json.loads((md.ROOT / "state" / "dynasty_assets.json").read_text(encoding="utf-8"))
    picks = next((p for p in assets.get("picks") or [] if p["year"] == 2027 and p["sport"] == "MLB"), None)
    if picks:
        rounds = sorted(picks["mine"])
        out += ["", "Your 2027 3-Ball MLB draft picks (league sheet, updated " + assets.get("picks_updated", "?") + "): "
                + ", ".join(f"round {r}" + (f" (from {via})" if via else "") for r, via in rounds)
                + "".join(f"; your round {r} went to {to}" for r, to in picks.get("lost") or [])]
    out += ["", "## Trade targets: held by other teams",
            "| Rank | Player | Chance useful | Pipeline | Held by | Why |", "|---|---|---|---|---|---|"]
    out += [f"| {x['rank']} | **{x['name']}** {x['pos']}, {x['org']} | {pct(x)} | {pipe(x)} | "
            f"{x.get('sheet') or 'ESPN: ' + str(x['espn_roster'])} | {x['why']} |" for x in others[:20]]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def dt_now():
    import datetime as dt
    from .config import TZ
    d = dt.datetime.now(TZ)
    return f"{d:%b} {d.day}, {d.year}"


def main():
    write = "--write" in sys.argv
    pipes = {y: md.pipeline(y) for y in range(2021, WATCH_YEAR + 1)}
    try:                                   # next preseason's Top 100 (late January) replaces this year's once it is out
        nxt = md.pipeline(WATCH_YEAR + 1, max_age=24)
        if len(nxt) >= 50:
            pipes[WATCH_YEAR] = nxt
            print(f"using Pipeline {WATCH_YEAR + 1} Top 100")
        else:
            print(f"Pipeline {WATCH_YEAR + 1} not out yet; using {WATCH_YEAR}")
    except Exception as e:                 # 404 until it is published
        print(f"Pipeline {WATCH_YEAR + 1} not out yet ({type(e).__name__}); using {WATCH_YEAR}")
    mlb_hit, mlb_pit = mlb_lines("hitting"), mlb_lines("pitching")
    res, weights = {}, {}
    for grp, mlb in (("hitting", mlb_hit), ("pitching", mlb_pit)):
        res[grp], weights[grp] = evaluate(grp, mlb, pipes)
    print(json.dumps(res, indent=1))
    lst, unscored, private = watch(weights, mlb_hit, mlb_pit, pipes)
    for x in lst[:40]:
        print(f"{x['rank']:>3} {x['p_useful']:.2f} {x['p_stats']:.2f} P#{x['pipeline'] or '-':>3} {x['name']:<24} "
              f"{x['pos']:<3} {x['org']:<4} {str(x['espn_roster']):<14} mine={x['mine']} | {x['why']} | {x.get('edge', '')}")
    print("Pipeline-ranked without a 2026 line to score:", [(u["name"], u["pipeline"]) for u in unscored])
    priv = md.CACHE / "watch-private.md"
    private_doc(private, priv)
    print("private doc:", priv)
    if write:
        (ROOT / "docs" / "data" / "mlb_prospects.json").write_text(json.dumps(
            {"season": WATCH_YEAR, "built": dt_now(), "weights": weights, "backtest": res, "players": lst[:150],
             "pipeline_unscored": unscored}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()


