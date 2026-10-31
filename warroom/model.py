"""Builds the War Room's app_data straight from Sleeper's public API plus nflverse (no transcription step).

Week logic (the fixes the claude.ai builder had to re-make each run, now kept in code):
- `played` is the last finished week: Sleeper's last_scored_leg, or one later once every game of the next
  week is final (ESPN live scoreboard or nflverse schedule), so Monday night counts the moment it ends.
- Week scores: Sleeper's matchup points, unless Sleeper hasn't finalized the week and nflverse's recompute
  of the same starters disagrees by more than 2 points (Sleeper's Tuesday points can miss Monday night).
- A cut is confirmed only when Sleeper marks the roster eliminated for that week (its roster is then
  empty); before that the lowest score is a projected cut. The cut team's players come from Sleeper's
  "chopped" transaction (or its last matchup) so the page works when the roster is already empty.
- Waiver claims keep Sleeper's own `leg` (claims processed after week N's cut carry leg N)."""
import collections
import datetime as dt

from shq import espn, sleeper
from shq.common import ct_label, get_json, iso, parse_iso
from shq.config import LEAGUES, SEASON, SLEEPER_USERNAME
from shq.guillotine import next_waivers
from shq.leagues import score

from .nfl import Nfl

LEAGUE_ID = next(lg["league_id"] for lg in LEAGUES if lg.get("format") == "guillotine")
BASE = sleeper.BASE
MISMATCH = 2.0


def sleeper_week_stats(week, scoring, fetch=get_json):
    """{sleeper_id: league-scored points} from Sleeper's own stats, for a week nflverse hasn't posted."""
    params = [("season_type", "regular")] + [("position[]", p) for p in sleeper.POSITIONS]
    rows = fetch(f"https://api.sleeper.app/stats/nfl/{SEASON}/{week}", params) or []
    out = {}
    for r in rows:
        pid, st = r.get("player_id"), r.get("stats") or {}
        if pid and (st.get("gp") or st.get("gms_active") or st.get("pts_half_ppr")):
            out[pid] = score(st, scoring)
    return out


def played_week(lg, nfl):
    last = int((lg.get("settings") or {}).get("last_scored_leg") or 0)
    nxt = last + 1
    if nxt in nfl.final_weeks():
        return nxt, "nflverse"
    try:
        games = espn.games(SEASON, nxt)
        if games and all(g["state"] == "post" for g in games.values()):
            return nxt, "espn"
    except Exception:  # the scoreboard is a convenience; Sleeper's own leg is the fallback
        pass
    return last, "sleeper"


def claims_history(txs, budget):
    """Bid history in the shape app.js expects: one row per claimed player per leg, winner first,
    with each bid as a share of that roster's FAAB going into the leg."""
    spent = collections.defaultdict(lambda: collections.defaultdict(int))
    by = collections.defaultdict(list)
    for t in txs:
        if t.get("type") != "waiver" or t.get("status") not in ("complete", "failed"):
            continue
        rid, leg = (t.get("roster_ids") or [None])[0], int(t.get("leg") or 0)
        bid = int((t.get("settings") or {}).get("waiver_bid") or 0)
        for pid in (t.get("adds") or {}):
            won = t["status"] == "complete"
            by[(leg, pid)].append((rid, bid, 1 if won else 0))
            if won:
                spent[leg][rid] += bid
    legs = sorted({leg for leg, _ in by} | set(spent))
    rosters = {rid for bids in by.values() for rid, _, _ in bids}
    before = {}
    for rid in rosters:
        left, before[rid] = budget, {}
        for leg in range(1, (max(legs) if legs else 0) + 2):
            before[rid][leg] = left
            left -= spent[leg][rid]
    hist = []
    for (leg, pid), bids in sorted(by.items()):
        seen, rows = set(), []
        for rid, bid, won in sorted(bids, key=lambda x: (-x[2], -x[1])):
            if (rid, bid) not in seen:
                seen.add((rid, bid))
                rows.append((rid, bid, won))
        if not rows[0][2]:
            continue
        hist.append({"leg": leg, "sid": pid, "win": rows[0][0], "bid": rows[0][1],
                     "bids": [[r, b] for r, b, _ in sorted(rows, key=lambda x: -x[1])],
                     "pct": [[r, b, round(100 * b / max(1, before[r][leg]))] for r, b, _ in sorted(rows, key=lambda x: -x[1])]})
    total = {rid: sum(spent[leg][rid] for leg in spent) for rid in rosters}
    return hist, {str(r): v for r, v in before.items()}, total


def build(now, nfl=None, fetch=get_json, players=None):
    """app_data for the page. `nfl`, `fetch` and `players` are swappable for tests."""
    lg = fetch(f"{BASE}/league/{LEAGUE_ID}")
    rosters = fetch(f"{BASE}/league/{LEAGUE_ID}/rosters")
    users = fetch(f"{BASE}/league/{LEAGUE_ID}/users")
    me_uid = fetch(f"{BASE}/user/{SLEEPER_USERNAME}")["user_id"]
    settings = lg.get("settings") or {}
    budget = int(settings.get("waiver_budget") or 200)
    leg = int(settings.get("leg") or 1)
    txs = {t["transaction_id"]: t for w in range(1, leg + 2)
           for t in fetch(f"{BASE}/league/{LEAGUE_ID}/transactions/{w}") or []}.values()
    nfl = nfl or Nfl(SEASON)
    db = players if players is not None else sleeper.players()
    played, source = played_week(lg, nfl)
    name = {u["user_id"]: u.get("display_name") or "?" for u in users}
    rname = {r["roster_id"]: name.get(r["owner_id"], f"R{r['roster_id']}") for r in rosters}
    elim = {r["roster_id"]: (r.get("settings") or {}).get("eliminated") for r in rosters}
    me = next(r["roster_id"] for r in rosters if r["owner_id"] == me_uid)

    # this week's scores and the cut
    matchups = fetch(f"{BASE}/league/{LEAGUE_ID}/matchups/{played}") if played else []
    alive_then = [m for m in matchups or [] if not elim.get(m["roster_id"]) or elim[m["roster_id"]] >= played]
    final = played <= int(settings.get("last_scored_leg") or 0)
    scores, note = {}, None
    nfl_has = played in nfl.stats_weeks()
    for m in alive_then:
        s_pts = round(float(m.get("points") or 0), 2)
        n_pts = round(sum(nfl.week_points(p, played, nfl.player(p, db)) or 0 for p in m.get("starters") or [] if p != "0"), 2)
        scores[m["roster_id"]] = s_pts
        if nfl_has and not final and abs(n_pts - s_pts) > MISMATCH:
            scores[m["roster_id"]] = n_pts
            note = "nflverse points used where Sleeper hadn't finished scoring"
    cut = None
    confirmed = next((rid for rid, w in elim.items() if w and w == played), None)
    if confirmed:
        chop = next((t for t in txs if t.get("type") == "chopped" and confirmed in (t.get("roster_ids") or [])), None)
        freed = list((chop or {}).get("drops") or {}) or next(
            (m.get("players") or [] for m in matchups or [] if m["roster_id"] == confirmed), [])
        cut = {"roster": confirmed, "week": played, "confirmed": True, "players": freed}
    elif played and scores:
        low = min(scores, key=lambda r: scores[r])
        players = next((r.get("players") or [] for r in rosters if r["roster_id"] == low), [])
        cut = {"roster": low, "week": played, "confirmed": False, "players": players}
    if cut:
        cut["scores"] = {str(r): v for r, v in sorted(scores.items(), key=lambda x: x[1])}
        if note:
            cut["note"] = note

    alive = [r for r in rosters if r.get("players") and not elim.get(r["roster_id"])]
    if cut and not cut["confirmed"]:
        alive = [r for r in alive if r["roster_id"] != cut["roster"]]
    teams = {str(r["roster_id"]): {"n": rname[r["roster_id"]],
                                   "faab": budget - int((r.get("settings") or {}).get("waiver_budget_used") or 0),
                                   "roster": list(r.get("players") or [])} for r in alive}
    if cut:
        used = next(int((r.get("settings") or {}).get("waiver_budget_used") or 0) for r in rosters if r["roster_id"] == cut["roster"])
        teams[str(cut["roster"])] = {"n": rname[cut["roster"]], "faab": budget - used, "roster": cut["players"]}
    dead = {str(rid): rname[rid] for rid, w in elim.items() if w and (not cut or rid != cut["roster"])}

    hist, before, spent = claims_history(txs, budget)
    for r in rosters:
        used = int((r.get("settings") or {}).get("waiver_budget_used") or 0)
        if spent.get(r["roster_id"], 0) != used:
            print(f"budget check: {rname[r['roster_id']]} bids won ${spent.get(r['roster_id'], 0)}, Sleeper says ${used} used")

    # players: weekly points 1..played; nflverse first, Sleeper's own stats for a week nflverse lacks
    W0 = played + 1
    fill = {w: sleeper_week_stats(w, lg["scoring_settings"], fetch) for w in range(1, played + 1) if w not in nfl.stats_weeks()}
    owner = {p: int(t) for t, v in teams.items() for p in v["roster"]}
    # `own` marks players on surviving teams only (the cut team's players are free to bid on)
    own = {p: r for p, r in owner.items() if not cut or r != cut["roster"]}
    universe = set(owner) | {h["sid"] for h in hist} | {sid for sid, r in nfl.ids.items() if r.get("gsis_id") in nfl.pts}
    universe |= {t for t in nfl.defpts}
    inj_week = W0 if nfl.injuries.get(W0) else W0 - 1
    P = {}
    for sid in universe:
        info = nfl.player(sid, db)
        pos = "K" if info["pos"] == "PK" else info["pos"]
        if pos not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue
        w = []
        for wk in range(1, played + 1):
            v = fill[wk].get(sid) if wk in fill else nfl.week_points(sid, wk, info)
            w.append(round(v, 2) if v is not None else None)
        g, team, status = info["gsis"], info["team"], "ACT"
        if g in nfl.cur:
            team, status = nfl.cur[g][1], nfl.cur[g][2]
        played_w = [v for v in w if v is not None]
        if not played_w and sid not in owner:
            continue
        rec = [v for v in reversed(w) if v is not None][:3]
        inj = nfl.injuries.get(inj_week, {}).get(g, ("", ""))
        if inj_week != W0 and inj[0] != "Out":
            inj = ("", "")
        P[sid] = {"n": info["name"], "p": pos, "t": team, "w": w, "g": len(played_w),
                  "a": round(sum(played_w) / len(played_w), 2) if played_w else 0,
                  "r": round(sum(rec) / len(rec), 2) if rec else 0, "st": status, "inj": inj[0], "ip": inj[1],
                  "bye": [b for b in nfl.bye.get(team, []) if b >= W0], "own": own.get(sid, 0)}
    keep = {k: v for k, v in P.items() if v["own"] or v["a"] >= 4 or (v["p"] in ("DEF", "K") and v["a"] >= 5)}
    for h in hist:
        h["n"], h["p"] = (P[h["sid"]]["n"], P[h["sid"]]["p"]) if h["sid"] in P else (nfl.player(h["sid"], db)["name"], "?")

    last_tx = max((t.get("status_updated") or 0 for t in txs if t.get("status") == "complete"), default=0)
    cut_txt = (f"{rname[cut['roster']]} cut in week {played}" + (" (confirmed)" if cut["confirmed"] else " (projected, not yet confirmed)")
               if cut else "no cut yet")
    asof = (f"Week {played} final" + {"espn": " (just finished; Sleeper still scoring)", "nflverse": " (Sleeper still scoring)"}.get(source, "")
            + f"; {cut_txt}; moves through {ct_label(parse_iso(iso_ms(last_tx)))} CT")
    return {
        "league": lg.get("name"), "P": keep, "teams": teams, "dead": dead, "hist": hist, "budget": before,
        "bye": {t: v for t, v in nfl.bye.items()}, "me": me, "cut": cut, "week": W0,
        "last_week": played + len(alive) - 1,   # one cut a week until one team is left
        "asof": asof, "data_as_of": iso_ms(last_tx), "waivers": ct_label(next_waivers(now)) + " CT",
    }


def iso_ms(ms):
    return iso(dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)) if ms else None
