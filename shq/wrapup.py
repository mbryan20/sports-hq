"""Weekend wrap-up: one tight report on every league and pool after the weekend's games, published as a phone-sized
PDF and a web page under docs/wrapups/ and pushed with the PDF link. Templates over the numbers, no AI.

Editions (anchors, not exact crons, because GitHub drops scheduled runs; see due()):
    sunday  first run after every NFL game before Monday is final (SNF ends ~10:30pm CT). College is final by then;
            Monday night players are listed as still to play.
    final   first run from Tuesday 8am CT once the week is over (MNF in, and the 7:30am laptop sync has read the
            private ESPN leagues). Same files, so the archive keeps one issue per week.
    The final is redrawn without a push when the Tuesday 8pm picks postmortem lands with what Michael entered.

Privacy (public repo): standings show my place and the leader's record only, pools show my balance and rank, and
nothing from the 3-Ball sheet or the Yahoo group members' picks is read.

    py -m shq.wrapup --week 8 --edition final [--push]    build (and push) from docs/data/lineups.json"""
import argparse
import datetime as dt
import functools
import re
import sys
import traceback

from . import espn, notify, sleeper
from . import guillotine as guillotine_mod
from . import espn_fantasy as ef
from .common import DATA, ROOT, STATE, ct_label, get_json, iso, load_json, now_utc, parse_iso, save_json
from .config import LEAGUES, SEASON, SITE_URL, SLEEPER_USERNAME, TZ, YAHOO_SCORING
from .leagues import name_key, score
from .swap import FLEX_SLOTS, eligible

OUT = ROOT / "docs" / "wrapups"
INDEX = OUT / "index.json"
PICKS = ROOT / "picks"
FINAL_WEEKDAY, FINAL_HOUR = 1, 8          # Tuesday 8am CT
BOOM = 6.0                                # boom/bust: at least this many points off projection...
BOOM_SHARE = 0.4                          # ...and this share of it
STALE_BACKTEST = "61%"                    # stale 1.5+ openers covered 61% in the backtest (ROADMAP)
DONE = "post"
GAME_LENGTH = dt.timedelta(hours=3, minutes=30)   # an NFL game is over this long after kickoff (laptop-read leagues)
PICK_RE = re.compile(r"^(?P<team>.+?)\s+(?P<line>[+-]\d+(?:\.\d+)?)")
CITE_RE = re.compile(r" \[ESPN, (\w+ \d+)[^\]]*\]")


# ---------- when ----------

def due(now, week, games, issues, force=False):
    """(NFL week, edition) to build on this run, or None. `week`/`games` are Context's: once every game of a week is
    final, Context has already moved on to the next week (no game started yet)."""
    local = now.astimezone(TZ)
    started = any(g["state"] != "pre" for g in games.values())
    have = {(i["week"], i["edition"]) for i in issues}
    if started:
        if force:
            return week, "sunday"
        if local.weekday() not in (6, 0) or (week, "sunday") in have or (week, "final") in have:
            return None
        monday = local.date() + dt.timedelta(days=1 if local.weekday() == 6 else 0)
        weekend = [g for g in games.values() if g["kickoff"] and g["kickoff"].astimezone(TZ).date() < monday]
        if not any(g["kickoff"].astimezone(TZ).weekday() == 6 for g in weekend):
            return None
        return (week, "sunday") if all(g["state"] == DONE for g in weekend) else None
    last = week - 1
    if last < 1:
        return None
    if force:
        return last, "final"
    tuesday = (local - dt.timedelta(days=(local.weekday() - FINAL_WEEKDAY) % 7)).replace(
        hour=FINAL_HOUR, minute=0, second=0, microsecond=0)
    # Tue 8am through Thursday (a later catch-up would read next week's lineups as "next week")
    if local.weekday() in (1, 2, 3) and local >= tuesday and (last, "final") not in have:
        return last, "final"
    return None


def refresh_due(issues):
    """A final issue built before the picks postmortem existed, whose postmortem has now landed."""
    for i in issues:
        if i["edition"] == "final" and not i.get("entries") and (PICKS / f"data/postmortem/{SEASON}-w{i['cfb_week']:02d}.json").exists():
            return i
    return None


# ---------- helpers ----------

def _f(x):
    return f"{x:.1f}"


def _clean(s):
    return " ".join((s or "").split())


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _pct(x):
    return "<1%" if 0 < x < 0.005 else f"{round(x * 100)}%"


def _money(w):
    try:
        return float(str(w).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0


@functools.lru_cache(None)
def _proj(week):
    return sleeper.projections(SEASON, week)


@functools.lru_cache(None)
def _stats(week):
    rows = get_json(f"https://api.sleeper.app/stats/nfl/{SEASON}/{week}",
                    [("season_type", "regular")] + [("position[]", p) for p in sleeper.POSITIONS])
    return {r["player_id"]: r.get("stats") or {} for r in rows}


@functools.lru_cache(None)
def _games(week):
    return espn.games(SEASON, week) if 1 <= week <= 18 else {}


@functools.lru_cache(None)
def _abbrevs(sport, season):
    return {tid: t["abbrev"] for tid, t in ef.pro_schedule(sport, season).items()}


def state(team, games):
    """'post' / 'in' / 'pre' for the team's game this week, 'bye' without one."""
    g = games.get(team) if team else None
    return g["state"] if g else "bye"


def best_lineup(slots, players):
    """Most points a legal lineup could have scored: narrowest slots first, best player who fits."""
    order = sorted(slots, key=lambda s: len(FLEX_SLOTS.get(s, ())))
    used, picks = set(), []
    for slot in order:
        p = max((p for p in players if id(p) not in used and eligible(slot, p["pos"])), key=lambda p: p["pts"], default=None)
        if p:
            used.add(id(p))
            picks.append(p)
    return round(sum(p["pts"] for p in picks), 2), picks


def lineup_review(players, games):
    """Points left on the bench (only over games that are over), the biggest miss, and booms/busts vs projection.
    players: {name, pos, team, slot ("BN" bench, "IR" ignored, else a starting slot), pts, proj}."""
    done = lambda p: state(p["team"], games) in (DONE, "bye")
    starters = [p for p in players if p["slot"] not in ("BN", "IR")]
    open_slots = [p["slot"] for p in starters if done(p)]
    pool = [p for p in players if p["slot"] != "IR" and done(p)]
    actual = sum(p["pts"] for p in starters if done(p))
    best, picks = best_lineup(open_slots, pool)
    left = round(best - actual, 1)
    miss = None
    ins = sorted((p for p in picks if p["slot"] == "BN"), key=lambda p: -p["pts"])
    outs = [p for p in starters if done(p) and not any(p is q for q in picks)]
    if left >= 0.5 and ins and outs:
        i = ins[0]
        o = min((o for o in outs if eligible(o["slot"], i["pos"])), key=lambda o: o["pts"], default=min(outs, key=lambda o: o["pts"]))
        miss = f"{i['name']} ({_f(i['pts'])}) over {o['name']} ({_f(o['pts'])}) at {o['slot']}"
    deltas = [(p["pts"] - p["proj"], p) for p in starters if done(p) and p["proj"] > 0 and state(p["team"], games) != "bye"]
    big = lambda d, p: abs(d) >= max(BOOM, BOOM_SHARE * p["proj"])
    boom = [f"{p['name']} {_f(p['pts'])} (proj {_f(p['proj'])})" for d, p in sorted(deltas, key=lambda t: -t[0]) if d > 0 and big(d, p)][:2]
    bust = [f"{p['name']} {_f(p['pts'])} (proj {_f(p['proj'])})" for d, p in sorted(deltas, key=lambda t: t[0]) if d < 0 and big(d, p)][:2]
    pending = [p for p in starters if not done(p)]
    return {"left": left if left >= 0.5 else 0.0, "miss": miss, "boom": boom, "bust": bust,
            "vs_proj": round(sum(d for d, _ in deltas), 1), "pending": pending}


def standings(rows, me, through, cats=False):
    """(rank, teams, my record, leader record) from decided matchups up to `through`, or None.
    rows: [period, home, home score, away, away score, winner H/A/T or "", tied categories] (espn_fantasy.results).
    Ranked by win share, then points for. Category leagues (H2H_CATEGORY) count every category."""
    rec = {}
    for mp, h, hs, a, as_, win, ties in rows:
        if mp > through or not win:
            continue
        for t in (h, a):
            rec.setdefault(t, [0, 0, 0, 0.0])
        if cats:
            rec[h][0] += hs; rec[h][1] += as_; rec[h][2] += ties
            rec[a][0] += as_; rec[a][1] += hs; rec[a][2] += ties
        else:
            w = {"H": (0, 1), "A": (1, 0)}.get(win)
            if w:
                rec[h][w[0]] += 1; rec[a][w[1]] += 1
            else:
                rec[h][2] += 1; rec[a][2] += 1
            rec[h][3] += hs; rec[a][3] += as_
    if me not in rec:
        return None
    share = lambda t: (rec[t][0] + 0.5 * rec[t][2]) / max(1, sum(rec[t][:3]))
    order = sorted(rec, key=lambda t: (-share(t), -rec[t][3]))
    fmt = lambda t: f"{rec[t][0]}-{rec[t][1]}" + (f"-{rec[t][2]}" if rec[t][2] else "")
    return order.index(me) + 1, len(order), fmt(me), fmt(order[0])


def standing_text(rows, me, week, decided, cats=False):
    now = standings(rows, me, week if decided else week - 1, cats)
    if not now:
        return None
    rank, n, mine, lead = now
    was = standings(rows, me, week - 1, cats) if decided else None
    move = ""
    if was and was[0] != rank:
        move = f", {'up' if was[0] > rank else 'down'} {abs(was[0] - rank)}"
    elif was:
        move = ", no change"
    leader = "" if rank == 1 else f"; leader {lead}"
    return f"{_ord(rank)} of {n} ({mine}{move}{leader})" + ("" if decided else ", before this week")


def margin(a, b):
    """a - b as shown next to the two scores: from the one-decimal scores the reader sees, so 182.8-7.0 reads
    "by 175.8" even when the raw 182.76 - 7.04 is 175.72. A gap that rounds away reads "by less than 0.1"."""
    d = float(_f(a)) - float(_f(b))
    return _f(d) if abs(d) >= 0.05 else "less than 0.1"


def h2h_line(mine, opp, opp_name, pending_mine, pending_opp=None, opp_known=True):
    """Result line for a points matchup. pending_*: starters still to play (Monday night). opp_known: whether
    pending_opp is real (ESPN box scores only carry my players, so theirs is known only once the week is over)."""
    opp_name = _clean(opp_name) or "your opponent"
    if not pending_mine and not pending_opp and opp_known:
        if mine > opp:
            return "W", f"Won {_f(mine)}-{_f(opp)} vs {opp_name}, by {margin(mine, opp)}"
        if mine < opp:
            return "L", f"Lost {_f(mine)}-{_f(opp)} vs {opp_name}, by {margin(opp, mine)}"
        return "T", f"Tied {_f(mine)}-{_f(opp)} vs {opp_name}"
    lead = "Leading" if mine > opp else "Trailing" if mine < opp else "Tied"
    text = f"{lead} {_f(mine)}-{_f(opp)} vs {opp_name}"
    if pending_mine:
        who = ", ".join(p["name"] for p in pending_mine[:3]) + (f" +{len(pending_mine) - 3} more" if len(pending_mine) > 3 else "")
        text += f"; still to play for you: {who} (proj {_f(sum(p['proj'] for p in pending_mine))})"
    if pending_opp is not None:
        text += (f"; for them: {len(pending_opp)} (proj {_f(sum(p['proj'] for p in pending_opp))})" if pending_opp else "; they're done")
    elif not opp_known:
        text += "; their Monday players may still be out"
    return ("leading" if mine > opp else "trailing"), text


# ---------- leagues ----------

def sleeper_section(cfg, view, week, games, edition):
    lg, uid, users = (sleeper.league_by_id(SLEEPER_USERNAME, cfg["league_id"]) if cfg.get("league_id")
                      else sleeper.find_league(SLEEPER_USERNAME, cfg["name"], SEASON))
    lid, scoring = lg["league_id"], lg["scoring_settings"]
    rosters = sleeper.rosters(lid)
    names = {u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name") for u in users}
    if cfg.get("format") == "guillotine":   # "Team name (username)", as on the league page and War Room (Q-047)
        names = {u["user_id"]: guillotine_mod.team_label(u) for u in users}
    team = {r["roster_id"]: _clean(names.get(r["owner_id"])) or f"Team {r['roster_id']}" for r in rosters}
    mine = next(r["roster_id"] for r in rosters if r["owner_id"] == uid)
    db, proj = sleeper.players(), _proj(week)

    def player(pid, slot, pts):
        d = db.get(pid, {})
        pos = d.get("fantasy_positions") or [d.get("position") or ("DEF" if pid.isalpha() else "")]
        return {"name": d.get("full_name") or pid, "pos": pos, "team": espn.norm_team(pid if pid.isalpha() else d.get("team")),
                "slot": slot, "pts": pts or 0.0, "proj": score((proj.get(pid) or {}).get("stats"), scoring)}

    def side(m):
        slots = [s for s in lg["roster_positions"] if s != "BN"]
        st = list(m.get("starters") or [])
        r = next((r for r in rosters if r["roster_id"] == m["roster_id"]), {})
        held = set(r.get("reserve") or []) | set(r.get("taxi") or [])
        pp = m.get("players_points") or {}
        out = [player(pid, slot, pp.get(pid)) for slot, pid in zip(slots, st) if pid and pid != "0"]
        out += [player(pid, "IR" if pid in held else "BN", pp.get(pid)) for pid in m.get("players") or [] if pid not in st]
        return out

    ms = sleeper.matchups(lid, week) or []
    me = next(m for m in ms if m["roster_id"] == mine)
    players = side(me)
    rev = lineup_review(players, games)
    sec = {"name": cfg["name"], "sport": "nfl", "review": rev}
    final = edition == "final"
    if cfg.get("format") == "guillotine":
        sec.update(guillotine(ms, mine, team, side, games, week, lid))
        return sec
    opp = next((m for m in ms if m["matchup_id"] == me["matchup_id"] and m["roster_id"] != mine), None)
    if opp:
        theirs = [p for p in side(opp) if p["slot"] not in ("BN", "IR")]
        pend_opp = [p for p in theirs if state(p["team"], games) not in (DONE, "bye")]
        sec["result"], sec["line"] = h2h_line(me.get("points") or 0, opp.get("points") or 0, team[opp["roster_id"]], rev["pending"], pend_opp)
        sec["score"] = f"{_f(me.get('points') or 0)}-{_f(opp.get('points') or 0)}"
    rows = []
    for w in range(1, week + 1):
        wm = ms if w == week else (sleeper.matchups(lid, w) or [])
        pairs = {}
        for m in wm:
            if m.get("matchup_id"):
                pairs.setdefault(m["matchup_id"], []).append(m)
        for a, b in (p for p in pairs.values() if len(p) == 2):
            decided = w < week or final
            pa, pb = a.get("points") or 0, b.get("points") or 0
            rows.append([w, a["roster_id"], pa, b["roster_id"], pb, ("H" if pa > pb else "A" if pb > pa else "T") if decided else "", 0])
    sec["standing"] = standing_text(rows, mine, week, final)
    return sec


def guillotine(ms, mine, team, side, games, week, lid):
    """Survived or cut, the margin over the lowest team, and every live team's score for the chart. Monday players
    count at their projection until they play."""
    alive = []
    for m in ms:
        if not any(p and p != "0" for p in m.get("starters") or []):
            continue
        pend = [p for p in side(m) if p["slot"] not in ("BN", "IR") and state(p["team"], games) not in (DONE, "bye")]
        pts = m.get("points") or 0
        alive.append({"team": team[m["roster_id"]], "me": m["roster_id"] == mine, "pts": round(pts, 1),
                      "proj": round(pts + sum(p["proj"] for p in pend), 1), "left": len(pend)})
    if not alive:
        return {"line": "No guillotine scores this week."}
    live = any(t["left"] for t in alive)
    key = "proj" if live else "pts"
    alive.sort(key=lambda t: -t[key])
    my = next(t for t in alive if t["me"])
    rank, low = alive.index(my) + 1, alive[-1]
    others_low = min((t for t in alive if not t["me"]), key=lambda t: t[key])
    gap = round(my[key] - others_low[key], 1)
    word = "projected " if live else ""
    if low["me"]:
        result = "cut"
        line = f"{'Projected to be cut' if live else 'Cut'} with {word}{_f(my[key])}, {_f(-gap)} below {others_low['team']}"
    else:
        result = "survived"
        line = (f"{'On track to survive' if live else 'Survived'}, {_ord(rank)} of {len(alive)} with {word}{_f(my[key])}, "
                f"{_f(gap)} over the lowest team ({low['team']}, {word}{_f(low[key])})")
    if live:
        line += f"; {my['left']} of yours still to play" if my["left"] else "; you're done"
    prev = None
    try:
        last = [m for m in sleeper.matchups(lid, week - 1) or [] if any(p and p != "0" for p in m.get("starters") or [])]
        order = sorted(last, key=lambda m: -(m.get("points") or 0))
        prev = next((i for i, m in enumerate(order, 1) if m["roster_id"] == mine), None)
    except Exception:
        traceback.print_exc()
    standing = f"{_ord(rank)} of {len(alive)} this week" + (f" (last week {_ord(prev)} of {len(order)})" if prev else "")
    return {"result": result, "line": line, "score": f"{_f(my[key])}, cut line {_f(low[key])}", "standing": standing,
            "chart": {"title": f"Week {week} scores{' (Monday players at projection)' if live else ''}",
                      "bars": [{"label": t["team"], "value": t[key], "me": t["me"], "low": t is low} for t in alive]}}


def espn_section(cfg, view, week, games, edition):
    sport = cfg["sport"]
    if cfg.get("private"):
        snap = ef.load_snapshot(sport, cfg["league_id"]) or {}
        data = {"results": snap.get("results"), "names": {t["id"]: t["name"] for t in snap.get("teams") or []},
                "box": (snap.get("box") or {}).get(str(week)), "captured": snap.get("captured")}
        data["names"][cfg["team_id"]] = (snap.get("team") or {}).get("name")
    else:
        data = ef.fetch_week(sport, cfg["season"], cfg["league_id"], cfg["team_id"], week if sport == "nfl" else None)
    sec = {"name": cfg["name"], "sport": sport}
    rows, names = data.get("results"), {k: _clean(v) for k, v in (data.get("names") or {}).items()}
    if not rows:
        sec["line"] = "Scores arrive with the next laptop ESPN sync (it now reads results and box scores)."
        return sec
    if sport == "nba":
        return {**sec, **nba_section(cfg, view, rows, names, edition)}
    b = data.get("box")
    if b and data.get("captured"):
        # a laptop read is a snapshot in time: a game that hadn't ended when it was read counts as still to play
        read = parse_iso(data["captured"])
        games = {t: (g if g["state"] != DONE or not g.get("kickoff") or g["kickoff"] + GAME_LENGTH <= read else {**g, "state": "in"})
                 for t, g in games.items()}
    if b:
        ab = _abbrevs("nfl", SEASON)
        sl, bench = ef.SLOT_NAMES["nfl"], ef.BENCH["nfl"]
        players = [{"name": p["name"], "pos": [sl[x] for x in p["eligible"] if x in sl and x not in bench],
                    "team": espn.norm_team(ab.get(p["pro_team"])), "pts": p["pts"], "proj": p["proj"],
                    "slot": "IR" if p["slot"] == bench[1] else "BN" if p["slot"] == bench[0] else sl.get(p["slot"], str(p["slot"]))}
                   for p in b["players"]]
        rev = sec["review"] = lineup_review(players, games)
        sec["result"], sec["line"] = h2h_line(b["pts"], b["opp_pts"], names.get(b["opp_id"]), rev["pending"],
                                              opp_known=all(g["state"] == DONE for g in games.values()))
        sec["score"] = f"{_f(b['pts'])}-{_f(b['opp_pts'])}"
    else:
        game = next((r for r in rows if r[0] == week and cfg["team_id"] in (r[1], r[3])), None)
        if game:
            home = game[1] == cfg["team_id"]
            mine, opp = (game[2], game[4]) if home else (game[4], game[2])
            sec["result"], sec["line"] = h2h_line(mine, opp, names.get(game[3] if home else game[1]), [], None)
            if not game[5]:
                sec["result"], sec["line"] = "leading" if mine > opp else "trailing", sec["line"].replace("Won", "Ahead").replace("Lost", "Behind") + " (not final)"
            sec["score"] = f"{_f(mine)}-{_f(opp)}"
        else:
            sec["line"] = f"No week {week} score in the latest read."
    decided = any(r[0] == week and r[5] for r in rows if cfg["team_id"] in (r[1], r[3]))
    sec["standing"] = standing_text(rows, cfg["team_id"], week, decided)
    if data.get("captured"):
        sec["note"] = f"ESPN read by the laptop {ct_label(parse_iso(data['captured']))} CT"
    return sec


def nba_section(cfg, view, rows, names, edition):
    """Category matchups run Monday to Sunday. Sunday night: the current matchup as it stands (games may still be
    on); otherwise the last decided one."""
    me = cfg["team_id"]
    cats = (view.get("advice") or {}).get("cats") or {}
    out = {}
    mine = [r for r in rows if me in (r[1], r[3])]
    decided = [r for r in mine if r[5]]
    if edition == "sunday" and cats.get("now"):
        w, l, t = (int(x) for x in cats["now"].split("-"))
        word = "Leading" if w > l else "Trailing" if w < l else "Even"
        out["result"] = "leading" if w > l else "trailing" if w < l else "even"
        out["line"] = f"{word} {w}-{l}" + (f"-{t}" if t else "") + f" vs {_clean(view.get('opponent'))}, Sunday's games still counting"
        out["score"] = cats["now"]
        last = max((r[0] for r in decided), default=0)
        out["standing"] = standing_text(rows, me, last, True, cats=True) if last else None
        return out
    if not decided:
        return {"line": "No finished matchup yet."}
    r = max(decided, key=lambda r: r[0])
    home = r[1] == me
    w, l = (r[2], r[4]) if home else (r[4], r[2])
    t = r[6]
    res = {"H": "W" if home else "L", "A": "L" if home else "W", "T": "T"}[r[5]]
    out["result"] = res
    word = {"W": "Won", "L": "Lost", "T": "Tied"}[res]
    out["line"] = f"{word} {w}-{l}" + (f"-{t}" if t else "") + \
        f" vs {names.get(r[3] if home else r[1]) or 'opponent'} (matchup {r[0]})"
    out["score"] = f"{w}-{l}" + (f"-{t}" if t else "")
    out["standing"] = standing_text(rows, me, r[0], True, cats=True)
    return out


def kosmonauts_section(cfg, view, week, games, edition):
    """Yahoo's API is gated, so: my starters from the laptop's roster read, scored with Sleeper's box-score stats
    and Kosmonauts scoring. The opponent's score isn't readable yet."""
    saved = load_json(STATE / "kosmonauts_roster.json") or {}
    if not saved.get("players"):
        return {"name": cfg["name"], "sport": "nfl", "line": "No roster read from the laptop yet."}
    db, stats, proj = sleeper.players(), _stats(week), _proj(week)
    by_yahoo = {str(p["yahoo_id"]): pid for pid, p in db.items() if p.get("yahoo_id")}
    by_name = {}
    for pid, p in db.items():
        by_name.setdefault((name_key(p.get("full_name")), espn.norm_team(p.get("team"))), pid)
    players = []
    for yp in saved["players"]:
        team = espn.norm_team(yp.get("team"))
        pid = team if yp.get("pos") == "DEF" else by_yahoo.get(str(yp.get("yahoo_id"))) or by_name.get((name_key(yp["name"]), team))
        slot = "IR" if yp["slot"] in ("IR", "IR+") else yp["slot"]
        players.append({"name": yp["name"], "pos": [x for x in yp.get("eligible") or [yp["pos"]] if x not in ("BN", "IR", "W/R/T")] or [yp["pos"]],
                        "team": team, "slot": slot, "pts": score(stats.get(pid), YAHOO_SCORING) if pid else 0.0,
                        "proj": score((proj.get(pid) or {}).get("stats"), YAHOO_SCORING) if pid else 0.0})
    rev = lineup_review(players, games)
    mine = sum(p["pts"] for p in players if p["slot"] not in ("BN", "IR"))
    opp = _clean(saved.get("opponent") or view.get("opponent"))
    line = f"Your starters scored about {_f(mine)}" + (f" vs {opp}" if opp else "") + \
        "; Yahoo's score isn't readable until the API is approved, so no W/L here"
    if rev["pending"]:
        line += f"; {len(rev['pending'])} still to play (proj {_f(sum(p['proj'] for p in rev['pending']))})"
    return {"name": cfg["name"], "sport": "nfl", "line": line, "score": f"~{_f(mine)}", "review": rev,
            "note": f"Lineup as of the laptop's Yahoo read {ct_label(parse_iso(saved['captured']))} CT; "
                    "points from Sleeper's stats with Kosmonauts scoring, so they can differ slightly from Yahoo's"}


def next_items(cfg, view, nxt_games, week):
    """What to do next week, from the league tab's What to do card (shq/advice.py built it this run)."""
    a = view.get("advice") or {}
    # the full ESPN note is in "Injuries to watch"; here the citation keeps only its date
    items = ["Fix: " + CITE_RE.sub(r" [ESPN, \1]", x) for x in (a.get("fixes") or [])[:2]]
    if cfg["sport"] == "nfl" and nxt_games:
        byes = [f"{r['name']} ({r['slot']})" for r in view.get("starters") or [] if r.get("team") and r["team"] not in nxt_games]
        if byes and not any("BYE" in x for x in items):
            items.append(f"Byes in week {week + 1}: " + ", ".join(byes))
    items += [f"Start/sit: {x}" for x in (a.get("moves") or [])[:1]]
    adds = [x for x in a.get("adds") or [] if not x.startswith("No free agent")]
    if adds:
        items.append(f"Waiver: {adds[0]}")
    t = a.get("trades") or {}
    if t.get("offers"):
        o = t["offers"][0]
        items.append(f"Trade idea: offer {o['team']} {' + '.join(o['give'])} for {' + '.join(o['get'])} "
                     f"(you +{o['my_gain']}/gm, them +{o['their_gain']}/gm)")
    for c in ((a.get("cats") or {}).get("chase") or [])[:1]:
        if not c.startswith("No category"):
            items.append(f"Categories: {c}")
    return items[:5]


SERIOUS = {"OUT", "IR", "D", "PUP", "SUSP"}


def injuries(view):
    """Injuries that matter next week: starters with any status, bench players who are out or doubtful, each with
    the dated ESPN note behind it (rule: every injury call is cited). Most serious first, three at most."""
    rows = [(0, r) for r in view.get("starters") or []] + [(1, r) for r in view.get("bench") or [] if r.get("status") in SERIOUS]
    rows = sorted((t for t in rows if t[1].get("status") and t[1].get("news")),
                  key=lambda t: (t[1]["status"] not in SERIOUS, t[0]))
    out = []
    for bench, r in rows[:3]:
        n, at = r["news"], parse_iso(r["news"].get("at"))
        when = f"{at.astimezone(TZ).strftime('%b')} {at.astimezone(TZ).day}" if at else "undated"
        note = n["note"] if len(n["note"]) <= 110 else n["note"][:110].rsplit(" ", 1)[0] + "..."
        out.append({"text": f"{r['name']} ({r['status']}{', bench' if bench else ''}): {note}",
                    "source": f"ESPN, {when}", "url": n.get("url")})
    return out


def league_section(cfg, view, week, games, nxt, edition):
    if cfg["platform"] == "sleeper":
        sec = sleeper_section(cfg, view, week, games, edition)
    elif cfg["platform"] == "espn":
        sec = espn_section(cfg, view, week, games, edition)
    else:
        sec = kosmonauts_section(cfg, view, week, games, edition)
    sec["next"] = next_items(cfg, view, nxt, week)
    sec["injuries"] = injuries(view)
    rev = sec.pop("review", None)
    if rev:
        sec["bench"] = (f"{_f(rev['left'])} pts left on the bench: {rev['miss']}" if rev["miss"]
                        else "Best lineup started" if not rev["pending"] else None)
        sec["bench_pts"] = rev["left"]
        sec["boom"], sec["bust"], sec["vs_proj"] = rev["boom"], rev["bust"], rev["vs_proj"]
    return sec


# ---------- pools ----------

def _events(cfb_week, week):
    if str(PICKS) not in sys.path:
        sys.path.insert(0, str(PICKS))
    from pp import lines  # Pool Picks' ESPN scoreboard reader (cached, no CFBD calls)
    ev = {}
    for league, wk in (("CFB", cfb_week), ("NFL", week)):
        try:
            for e in lines.espn_odds(league, wk, SEASON):
                ev[e["id"]] = e
                if league == "NFL":
                    ev[f"nfl-{espn.norm_team(e['away_abbr'])}-{espn.norm_team(e['home_abbr'])}"] = e
        except Exception:
            traceback.print_exc()
    return ev


def grade_row(row, events, ats):
    """1 win, 0 loss, 0.5 push, None not final. Side from the card's "Away @ Home" order, line from the pick text."""
    e = events.get((row.get("bd") or "").replace("bd-", ""))
    if not e or e.get("state") != DONE or e.get("home_score") is None:
        return None
    away = row["game"].replace("★", "").split(" @ ")[0].strip()
    side_away = row.get("pick_team", "").strip() == away
    hs, as_ = float(e["home_score"]), float(e["away_score"])
    margin = (as_ - hs) if side_away else (hs - as_)
    line = 0.0
    if ats:
        m = PICK_RE.match(row["pick"])
        if not m:
            return None
        line = float(m["line"])
    x = margin + line
    return 1.0 if x > 0 else 0.5 if x == 0 else 0.0


def _record(rs):
    w, l, p = rs.count(1.0), rs.count(0.0), rs.count(0.5)
    return f"{w}-{l}" + (f"-{p}" if p else "")


def pools_section(week, now):
    cards = load_json(PICKS / "data" / "cards.json", {}) or {}
    label = (cards.get("meta") or {}).get("week_label", "")
    m_nfl, m_bto = re.search(r"NFL Week (\d+)", label), re.search(r"BTO Week (\d+)", label)
    cfb_week = int(m_bto.group(1)) if m_bto else week + 1
    if not m_nfl or int(m_nfl.group(1)) != week:
        cfb_week = week + 1   # CFBD/BTO/Yahoo week N is NFL week N-1 (picks/RUNBOOK.md)
    out = {"cfb_week": cfb_week, "pools": [], "model": [], "stale": None, "entries": False}
    pm = load_json(PICKS / "data" / "postmortem" / f"{SEASON}-w{cfb_week:02d}.json")
    entries = load_json(PICKS / "data" / "entries" / f"{SEASON}-w{cfb_week:02d}.json", {}) or {}
    out["entries"] = bool(pm)
    if not m_nfl or int(m_nfl.group(1)) != week:
        # the live cards have moved on to another week: what Michael entered, from the postmortem, is all there is
        titles = {"bto": "BTO Beat the Odds", "cfp": "CFP points pool", "yahoo": "Yahoo pick'em"}
        for pid, e in ((pm or {}).get("pools") or {}).items():
            if e.get("entered"):
                out["pools"].append({"id": pid, "title": titles.get(pid, pid), "card": None, "open": 0, "net": None, "picks": [],
                                     "entered": e["entered"]["record"] + (f" ({e['entered']['net']:+,.0f})" if pid != "yahoo" else ""),
                                     "after": (entries.get("standings") or {}).get(pid)})
        out["note"] = ("Card picks for this week weren't archived; these are your graded entries." if out["pools"]
                       else "No picks card or graded entries on file for this week.")
        return out
    events = _events(cfb_week, week)
    slate = load_json(PICKS / "slates" / f"{SEASON}-w{cfb_week:02d}.json", {}) or {}
    for c in cards.get("cards") or []:
        if c["id"] not in ("bto", "cfp", "yahoo") or not c.get("rows"):
            continue
        ats = c["id"] != "yahoo"
        graded = [(r, grade_row(r, events, ats)) for r in c["rows"]]
        done = [(r, g) for r, g in graded if g is not None]
        rs = [g for _, g in done]
        net = sum(_money(r.get("wager")) * (2 * g - 1) for r, g in done) if ats else None
        pool = {"id": c["id"], "title": c["title"], "card": _record(rs), "open": len(graded) - len(done),
                "net": net, "picks": [{"pick": r["pick"], "game": r["game"].replace("★", "").strip(),
                                       "result": {1.0: "W", 0.0: "L", 0.5: "P", None: "-"}[g]} for r, g in graded]}
        before = slate.get(c["id"]) or {}
        if c["id"] == "bto" and before.get("balance"):
            pool["before"] = f"${before['balance']:,} (#{before.get('rank')} of {before.get('players')})"
        elif c["id"] == "cfp" and before.get("balance"):
            pool["before"] = f"{before['balance']:,} pts (#{before.get('rank')})"
        elif c["id"] == "yahoo" and before.get("standings"):
            s = before["standings"]
            pool["before"] = f"{s.get('me')} pts, {_ord(s['rank'])} of {before.get('group_size')} (leader {s.get('leader')})"
        if pm:
            e = (pm.get("pools") or {}).get(c["id"]) or {}
            if e.get("entered"):
                pool["entered"] = e["entered"]["record"] + (f" ({e['entered']['net']:+,.0f})" if ats else "")
                pool["differences"] = len(e.get("differences") or [])
            pool["after"] = (entries.get("standings") or {}).get(c["id"])
        out["pools"].append(pool)
        probs = [r.get("model") for r, _ in done if isinstance(r.get("model"), (int, float))]
        if probs:
            out["model"].append({"pool": c["title"], "n": len(probs), "won": sum(rs), "expected": round(sum(probs), 1)})
    out["stale"] = stale_lines(cfb_week, events)
    return out


def stale_lines(cfb_week, events):
    """The stale-line scanner's flags (pool line 1.5+ off the market or across a key number) graded at the pool line."""
    d = load_json(DATA / "pick_lines.json", {}) or {}
    if d.get("week") != cfb_week:
        return None
    hits = []
    for r in d.get("rows") or []:
        if not r.get("flag"):
            continue
        e = events.get(str(r.get("espn_id")))
        if not e or e.get("state") != DONE or e.get("home_score") is None:
            hits.append({"text": f"{r['side']} {r['pool_line']:+g} ({r['pool'].upper()})", "result": "-"})
            continue
        away = r["game"].split(" @ ")[0].strip()
        hs, as_ = float(e["home_score"]), float(e["away_score"])
        x = ((as_ - hs) if r["side"] == away else (hs - as_)) + r["pool_line"]
        hits.append({"text": f"{r['side']} {r['pool_line']:+g} ({r['pool'].upper()}, market {r['market_line']:+g})",
                     "result": "W" if x > 0 else "P" if x == 0 else "L"})
    return hits


# ---------- war room ----------

def warroom_section(names=None):
    """`names` maps War Room v2's usernames to the league page's "Team name (username)" labels (Q-047)."""
    b = load_json(ROOT / "docs" / "war-room-v2" / "bids.json")
    if not b:
        return None
    names = names or {}
    nm = lambda t: names.get(t, t)
    me, cut = b.get("me") or {}, b.get("cut") or {}
    lines = []
    if cut.get("team"):
        lines.append(f"Week {cut['week']} cut: {nm(cut['team'])} ({'confirmed' if cut.get('confirmed') else 'projected'}).")
    if me:
        lines.append(f"You next week (week {b.get('week')}): {_pct(me.get('cut_risk_next_week') or 0)} cut risk, "
                     f"projected {_f(me.get('projected_next_week') or 0)}, about {me.get('expected_weeks_left')} weeks left, "
                     f"{_pct(me.get('win_odds') or 0)} to win it.")
    risk = sorted((t for t in b.get("cut_risks") or [] if not t.get("me")), key=lambda t: -(t.get("cut_risk_next_week") or 0))[:3]
    if risk:
        lines.append("Most at risk: " + ", ".join(f"{nm(t['team'])} {_pct(t['cut_risk_next_week'])}" for t in risk) + ".")
    bids = [x for x in b.get("bids") or [] if x.get("call") in ("Bid", "Add free")][:3]
    if bids:
        lines.append(f"Bids before waivers {b.get('waivers')} (${b.get('my_faab')} left): " + "; ".join(
            f"{x['name']} ({x['pos']}) " + (f"bid up to ${x['your_max']} (likely ${x['est_price']})" if x["call"] == "Bid" else "free add")
            for x in bids) + ".")
    return {"lines": lines, "source": f"War Room v2, {b.get('data_as_of')}"}


# ---------- the report ----------

def _v2_names(views):
    """{username: label} from the Guillotine league page's survival block (shq/guillotine.py), or {}."""
    for cfg in LEAGUES:
        if cfg.get("format") == "guillotine":
            g = (((views or {}).get(cfg["name"]) or {}).get("advice") or {}).get("guillotine") or {}
            return g.get("labels") or {}
    return {}


def build(now, week, edition, views):
    games, nxt = _games(week), _games(week + 1)
    leagues = []
    for cfg in LEAGUES:
        view = views.get(cfg["name"]) or {}
        try:
            leagues.append(league_section(cfg, view, week, games, nxt, edition))
        except Exception as e:
            traceback.print_exc()
            leagues.append({"name": cfg["name"], "sport": cfg["sport"], "line": f"Couldn't read this league ({type(e).__name__}).",
                            "next": next_items(cfg, view, nxt, week), "injuries": injuries(view)})
    try:
        pools = pools_section(week, now)
    except Exception as e:
        traceback.print_exc()
        pools = {"cfb_week": week + 1, "pools": [], "model": [], "stale": None, "entries": False,
                 "note": f"Couldn't grade the pools ({type(e).__name__})."}
    model = {"week": week, "cfb_week": pools["cfb_week"], "season": SEASON, "edition": edition,
             "generated": iso(now), "generated_label": f"{now.astimezone(TZ).strftime('%a %b')} {now.astimezone(TZ).day}, {ct_label(now).split(' ')[1]} CT",
             "leagues": leagues, "pools": pools, "warroom": warroom_section(_v2_names(views))}
    model["numbers"] = numbers(model)
    model["headline"] = headline(model)
    return model


def numbers(model):
    out = []
    lg = [l for l in model["leagues"] if "vs_proj" in l]
    if lg:
        beat = sum(1 for l in lg if l["vs_proj"] > 0)
        out.append(f"Projections: your starters beat them in {beat} of {len(lg)} football leagues "
                   f"({sum(l['vs_proj'] for l in lg):+.1f} pts in all, finished games only).")
    for m in model["pools"].get("model") or []:
        out.append(f"{m['pool']}: card picks were rated to win {m['expected']} of {m['n']}; they won {_f(m['won']).rstrip('0').rstrip('.')}.")
    st = model["pools"].get("stale")
    if st:
        done = [h for h in st if h["result"] in ("W", "L", "P")]
        if done:
            out.append(f"Stale-line flags: {sum(h['result'] == 'W' for h in done)} of {len(done)} covered the pool line "
                       f"(backtest {STALE_BACKTEST}): " + "; ".join(f"{h['text']} {h['result']}" for h in done) + ".")
        else:
            out.append(f"Stale-line flags: {len(st)}, none final yet.")
    elif st is not None:
        out.append("Stale-line scanner: no flags this week.")
    return out


def headline(model):
    out = []
    h2h = [l for l in model["leagues"] if l.get("result") in ("W", "L", "T", "leading", "trailing", "even")]
    if h2h:
        w = sum(l["result"] == "W" for l in h2h)
        l_ = sum(l["result"] == "L" for l in h2h)
        t = sum(l["result"] == "T" for l in h2h)
        open_ = [l for l in h2h if l["result"] in ("leading", "trailing", "even")]
        text = f"Head-to-head: {w}-{l_}" + (f"-{t}" if t else "")
        if open_:
            text += f", plus {len(open_)} still open (" + ", ".join(f"{l['name']} {l['result']}" for l in open_) + ")"
        out.append(text + ".")
    g = next((l for l in model["leagues"] if l.get("result") in ("survived", "cut")), None)
    if g:
        first = g["line"].split(";")[0]
        out.append(f"Guillotine: {first[0].lower()}{first[1:]}.")
    missing = [l["name"] for l in model["leagues"] if not l.get("score")]
    if missing:
        out.append("No score yet: " + ", ".join(missing) + ".")
    pools = model["pools"].get("pools") or []
    if pools:
        carded = any(p.get("card") for p in pools)
        parts = [f"{p['title'].split(' ')[0]} " + (p["card"] + (f" ({p['open']} open)" if p["open"] else "") if p.get("card")
                                                   else f"entered {p.get('entered')}") for p in pools]
        tail = " (card as posted; your entries are graded Tuesday night)" if carded and not model["pools"].get("entries") else ""
        out.append(("Picks card: " if carded else "Picks: ") + ", ".join(parts) + tail + ".")
    benchy = max((l for l in model["leagues"] if l.get("bench_pts")), key=lambda l: l["bench_pts"], default=None)
    if benchy and benchy["bench_pts"] >= 5:
        out.append(f"Most left on a bench: {_f(benchy['bench_pts'])} in {benchy['name']}.")
    return out


# ---------- publish ----------

def paths(model):
    stem = f"{model['season']}-w{model['week']:02d}"
    return stem, OUT / f"{stem}.json", OUT / f"{stem}.html", OUT / f"{stem}.pdf"


def publish(model):
    """Write the issue (JSON model, HTML page, PDF) and the archive index. Returns {"html": url, "pdf": url|None}."""
    from . import wrapup_render as render
    stem, jp, hp, pp = paths(model)
    OUT.mkdir(parents=True, exist_ok=True)
    save_json(jp, model)
    hp.write_text(render.html(model), encoding="utf-8", newline="\n")
    pdf_ok = True
    try:
        pp.write_bytes(render.pdf(model))
    except Exception:  # the page still goes out if the PDF library is missing or fails
        traceback.print_exc()
        pdf_ok = False
    index = load_json(INDEX, {"issues": []})
    issues = [i for i in index["issues"] if i["week"] != model["week"] or i.get("season", SEASON) != model["season"]]
    issues.append({"season": model["season"], "week": model["week"], "cfb_week": model["cfb_week"], "edition": model["edition"],
                   "generated": model["generated"], "html": f"{stem}.html", "pdf": f"{stem}.pdf" if pdf_ok else None,
                   "headline": model["headline"], "entries": model["pools"].get("entries", False)})
    issues.sort(key=lambda i: (i.get("season", SEASON), i["week"]), reverse=True)
    save_json(INDEX, {"issues": issues})
    (OUT / "index.html").write_text(render.archive(issues), encoding="utf-8", newline="\n")
    base = SITE_URL + "wrapups/"
    return {"html": base + f"{stem}.html", "pdf": base + f"{stem}.pdf" if pdf_ok else None}


def send(model, urls, intro=None):
    title = (f"Weekend wrap-up: NFL wk {model['week']}" + (" (Sunday)" if model["edition"] == "sunday" else " final"))
    msg = "\n".join(([intro] if intro else []) + model["headline"])[:900] or "Tap for the PDF."
    notify.push_once(f"wrapup:{model['season']}:{model['week']}:{model['edition']}", title, msg, priority=3, tags=["newspaper"],
                     click=urls["pdf"] or urls["html"], delay="3m",  # GitHub Pages needs a minute or two to publish
                     actions=[{"action": "view", "label": "PDF", "url": urls["pdf"] or urls["html"]},
                              {"action": "view", "label": "Web page", "url": urls["html"]}])


def merge_entries(old, new):
    """Add the postmortem's graded entries and standings to an issue's pools, keeping its card grading (the live
    cards move on to the next week on Wednesday)."""
    by_id = {p["id"]: p for p in new.get("pools") or []}
    for p in old.get("pools") or []:
        n = by_id.pop(p["id"], {})
        for k in ("entered", "differences", "after"):
            if n.get(k) is not None:
                p[k] = n[k]
    old.setdefault("pools", []).extend(by_id.values())
    old["entries"] = new.get("entries", False)
    if old["entries"] and old.get("note", "").startswith("No picks card"):
        old.pop("note")
    return old


def run(now, week, games, views, force=False):
    """Called by shq.run every pass. Builds, publishes and pushes when an edition is due; quietly redraws a final
    issue's pools when the Tuesday postmortem lands. Returns a note for the log, or None."""
    issues = (load_json(INDEX, {}) or {}).get("issues", [])
    want = due(now, week, games, issues, force)
    if want:
        model = build(now, want[0], want[1], views)
        urls = publish(model)
        send(model, urls)
        return f"wrap-up week {want[0]} {want[1]} published"
    stale = refresh_due(issues)
    if stale:
        _, jp, _, _ = paths({"season": stale.get("season", SEASON), "week": stale["week"]})
        model = load_json(jp)
        if model:
            merge_entries(model["pools"], pools_section(model["week"], now))
            model["numbers"], model["headline"] = numbers(model), headline(model)
            model["pools_updated"] = iso(now)
            publish(model)
            return f"wrap-up week {model['week']} redrawn with entries"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--edition", choices=("sunday", "final"), default="final")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--intro", help="a first line for the push")
    ap.add_argument("--out", help="write the PDF/HTML here instead of publishing to docs/wrapups")
    a = ap.parse_args()
    views = (load_json(DATA / "lineups.json", {}) or {}).get("leagues", {})
    model = build(now_utc(), a.week, a.edition, views)
    if a.out:
        from . import wrapup_render as render
        from pathlib import Path
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        save_json(out / "wrapup.json", model)
        (out / "wrapup.html").write_text(render.html(model), encoding="utf-8", newline="\n")
        (out / "wrapup.pdf").write_bytes(render.pdf(model))
        print(f"wrote {out}")
        return
    urls = publish(model)
    print(urls)
    if a.push:
        send(model, urls, a.intro)


if __name__ == "__main__":
    main()
