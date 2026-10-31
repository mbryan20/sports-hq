"""Per-game breakdowns for the Picks page: what the model saw, built from the numbers by templates (no AI).

Every pool game (Yahoo, BTO, CFP) gets one: kickoff and TV, pool line vs market and opener, the model vs the
market, an opponent-adjusted stats matchup with national ranks, strengths and weaknesses (a weakness only
counts when the opponent can exploit it: pool-method rule 4), injuries and news with dates and sources,
weather, and each pool's context. Presentation only: nothing here feeds the picks or the sizing.
CFBD: the game-level advanced stats the model already caches, plus cached season stats (havoc), SP+ and talent.
NFL: opponent-adjusted EPA/success splits and style stats from nflverse play-by-play (pp.nflverse).
Each panel also returns a compact `stats` dict that pp.cards writes to data/cards.json `game_stats`.
"""
import html, re
from datetime import datetime
from functools import lru_cache
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from .http import cfbd, get_json
from .lines import espn_odds, find as espn_find, gap_row
from .names import norm
from .weather import venues, total_adjustment

# numpy, the model and the sims are imported inside the functions that need them, so the text helpers
# (traits, edges, notes_for, formatting) load and test without numpy, like pp.lines (CI installs none).

CT = ZoneInfo("America/Chicago")
RESEARCH_LOG = "https://github.com/mbryan20/sports-hq/tree/main/picks/research"  # where run notes live
NFL_INJ = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
NFLVERSE = "https://github.com/nflverse/nflverse-data"

# (key, table label, value from a CFBD game-level offense record, higher is better for the offense).
# epa and sr come from the model's own ratings (M.ratings), so the table matches what the sims used.
FACETS = [("epa", "EPA/play", None, True), ("sr", "Success rate", None, True),
          ("rush", "EPA/rush", lambda o: o["rushingPlays"]["ppa"], True),
          ("pass", "EPA/pass", lambda o: o["passingPlays"]["ppa"], True),
          ("expl", "Explosiveness", lambda o: o["explosiveness"], True),
          ("pdsr", "Passing-down SR", lambda o: o["passingDowns"]["successRate"], True),
          ("sdsr", "Standard-down SR", lambda o: o["standardDowns"]["successRate"], True),
          ("line", "Line yards/rush", lambda o: o["lineYards"], True),
          ("stuff", "Run stuff rate", lambda o: o["stuffRate"], False)]
OFF_NAME = {"epa": "offense", "sr": "down-to-down offense", "rush": "run game", "pass": "pass game",
            "expl": "big-play offense", "pdsr": "passing-down offense", "sdsr": "standard-down offense", "line": "offensive line (line yards)", "stuff": "run blocking", "havoc": "protection (havoc allowed)"}
DEF_NAME = {"epa": "defense", "sr": "down-to-down defense", "rush": "run defense", "pass": "pass defense",
            "expl": "big-play defense", "pdsr": "passing-down defense", "sdsr": "standard-down defense", "line": "front seven (line yards)", "stuff": "run stuffs", "havoc": "havoc (TFLs, sacks, PBUs)"}
TOP, EXPLOIT = 25, 50  # rank <= TOP is a strength; an opponent unit ranked <= EXPLOIT can exploit a weakness


def _adjust(rows, lam=3.0):
    """rows (team, opp, loc, y): y = mu + O[team] + D[opp] + h*loc, ridge toward the league average
    (~3 games of prior). Returns {team: (offense per game, defense allowed per game)} vs an average foe."""
    import numpy as np
    teams = sorted({r[0] for r in rows} | {r[1] for r in rows})
    if not rows:
        return {}
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X = np.zeros((len(rows), 2 * n + 2))
    ri = np.arange(len(rows))
    X[ri, [ix[r[0]] for r in rows]] = 1
    X[ri, [n + ix[r[1]] for r in rows]] = 1
    X[:, 2 * n] = 1
    X[:, 2 * n + 1] = [r[2] for r in rows]
    A = X.T @ X + np.diag([lam] * (2 * n) + [1e-6, 1e-6])
    sol = np.linalg.solve(A, X.T @ np.array([r[3] for r in rows], float))
    mu = sol[2 * n]
    return {t: (mu + sol[ix[t]], mu + sol[n + ix[t]]) for t in teams}


def _havoc(year):
    try:
        rows = cfbd("/stats/season/advanced", max_age_h=20, year=year, excludeGarbageTime="true")
    except Exception as ex:  # havoc is a nice-to-have; never block the page on it
        print("CFBD season stats unavailable (havoc skipped):", ex)
        return {}
    return {r["team"]: (((r.get("offense") or {}).get("havoc") or {}).get("total"),
                        ((r.get("defense") or {}).get("havoc") or {}).get("total")) for r in rows}


def _cfbd_extra(year):
    """Current-season SP+ (Bill Connelly, via CFBD) and the 247 talent composite. Context only: SP+ has no
    week-by-week history to backtest. {} on any failure."""
    out = {}
    try:
        for r in cfbd("/ratings/sp", max_age_h=20, year=year):
            if r.get("rating") is not None:
                out.setdefault(r["team"], {})["sp"] = r["rating"]
    except Exception as ex:
        print("CFBD SP+ unavailable:", ex)
    try:
        for r in cfbd("/talent", max_age_h=24 * 30, year=year):
            out.setdefault(r["team"], {})["talent"] = r.get("talent")
    except Exception as ex:
        print("CFBD talent unavailable:", ex)
    return out


SP_HFA = 2.5  # home field in SP+ points (assumed; Connelly's own projections use about this)


def _rank(vals, higher_better, pool):
    order = sorted((t for t in pool if vals.get(t) is not None), key=lambda t: vals[t], reverse=higher_better)
    return {t: i + 1 for i, t in enumerate(order)}


@lru_cache(None)
def profiles(year, week):
    """{team: {facet: {o, d, ro, rd}}, plus pace, runrate, havoc, record, last3} from games before `week`.
    Ranks are among FBS teams (1 = best; for runrate 1 = most run-heavy, for pace 1 = most plays)."""
    import numpy as np
    from . import model as M
    gmap = {g["id"]: g for g in M.games(year)}
    recs = [r for r in M.adv(year) if r["week"] < week and r["gameId"] in gmap]
    fbs = M.fbs_teams(year)
    R = M.ratings(year, week)
    P = {}

    def put(key, vals, higher_better, d_higher_better=None):
        ro = _rank({t: v[0] for t, v in vals.items()}, higher_better, fbs)
        rd = _rank({t: v[1] for t, v in vals.items()}, (not higher_better) if d_higher_better is None else d_higher_better, fbs)
        for t, (o, d) in vals.items():
            P.setdefault(t, {})[key] = {"o": o, "d": d, "ro": ro.get(t), "rd": rd.get(t)}

    for key, _, get, hb in FACETS:
        if get is None:
            mu, _, tab = R[{"epa": "ppa", "sr": "sr"}[key]]
            vals = {t: (mu + o, mu + d) for t, (o, d) in tab.items()}
        else:
            rows = []
            for r in recs:
                try:
                    y = get(r["offense"])
                except (KeyError, TypeError):
                    continue
                if y is not None:
                    rows.append((r["team"], r["opponent"], M._loc(gmap[r["gameId"]], r["team"]), float(y)))
            vals = _adjust(rows)
        put(key, vals, hb)
    ex = _cfbd_extra(year)
    for key in ("sp", "talent"):
        rk = _rank({t: v.get(key) for t, v in ex.items()}, True, fbs)
        for t, v in ex.items():
            if v.get(key) is not None:
                P.setdefault(t, {})[key] = {"o": v[key], "ro": rk.get(t)}
    hv = {t: v for t, v in _havoc(year).items() if v[0] is not None and v[1] is not None}
    put("havoc", hv, False, d_higher_better=True)  # offense: less havoc allowed is better
    plays, runs = {}, {}
    for r in recs:
        o = r["offense"]
        plays.setdefault(r["team"], []).append(o.get("plays") or 0)
        rp, pp = o.get("rushingPlays") or {}, o.get("passingPlays") or {}
        if rp.get("ppa") and pp.get("ppa"):
            nr, npass = rp["totalPPA"] / rp["ppa"], pp["totalPPA"] / pp["ppa"]
            if nr > 0 and npass > 0:
                runs.setdefault(r["team"], []).append((nr, npass))
    put("pace", {t: (float(np.mean(v)), None) for t, v in plays.items()}, True)
    put("runrate", {t: (sum(a for a, _ in v) / sum(a + b for a, b in v), None) for t, v in runs.items()}, True)
    for g in sorted((g for g in M.games(year) if g.get("completed") and g["week"] < week), key=lambda g: g["startDate"]):
        for t, o, me, them, at in ((g["homeTeam"], g["awayTeam"], g["homePoints"], g["awayPoints"], "vs"),
                                   (g["awayTeam"], g["homeTeam"], g["awayPoints"], g["homePoints"], "@")):
            if me is None or them is None:
                continue
            p = P.setdefault(t, {})
            p.setdefault("games", []).append(("W" if me > them else "L", me, them, at if not g.get("neutralSite") else "vs", o))
    P["_n"] = len(fbs)
    return P


# ---------- formatting ----------

def ordn(r):
    return "—" if r is None else f"#{r}"


def fmt_spread(team, s):
    return f"{team} PK" if not s else f"{team} {s:+g}"


def fav_line(home, away, home_spread):
    """'Georgia -12.5' from a home spread (negative = home favored)."""
    if home_spread is None:
        return "—"
    return fmt_spread(home, home_spread) if home_spread <= 0 else fmt_spread(away, -home_spread)


def by(home, away, margin):
    if abs(margin) < 0.25:
        return "even"
    return f"{home if margin > 0 else away} by {abs(margin):.1f}"


def kick_ct(iso):
    if not iso:
        return ""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CT)
    return f"{t:%a %b} {t.day}, {t.hour % 12 or 12}:{t:%M %p}"


def src_name(url):
    try:
        return urlparse(url).netloc.replace("www.", "") or "source"
    except Exception:
        return "source"


def esc(s):
    return html.escape(str(s))


def link(url, text=None):
    return f'<a href="{esc(url)}" rel="noopener">{esc(text or src_name(url))}</a>'


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _cell(key, side, P, n):
    """'.21 #12' for one team's unit; colored by rank."""
    s = (P.get(key) or {})
    v, r = s.get(side), s.get("r" + side)
    if v is None:
        return "—"
    if key in ("sr", "pdsr", "sdsr", "stuff", "havoc", "runrate"):
        txt = f"{v * 100:.0f}%"
    elif key == "pace":
        txt = f"{v:.0f}"
    elif key in ("expl", "line"):
        txt = f"{v:.2f}"
    else:
        txt = f"{v:+.2f}".replace("0.", ".")
    cls = " class='g'" if r and r <= TOP else (" class='r'" if r and r > n - 35 else "")
    return f"{txt} <span{cls}>{ordn(r)}</span>"


# ---------- strengths, weaknesses, key matchups (rule 4) ----------

def _pct(rank, n):
    return 1 - (rank - 1) / (n - 1)


def _usage_ok(facet, opp, n):
    """Does the opponent lean on this kind of play enough to exploit a weakness against it?"""
    rr = (opp.get("runrate") or {}).get("ro")
    if rr is None:
        return True, ""
    if facet == "rush" and rr > n * 2 / 3:
        return False, f"rarely runs ({opp['runrate']['o'] * 100:.0f}% runs)"
    if facet == "pass" and rr < n / 3:
        return False, f"rarely throws ({(1 - opp['runrate']['o']) * 100:.0f}% passes)"
    return True, ""


CFB_TRAITS = ("epa", "rush", "pass", "expl", "pdsr", "stuff", "havoc")


def traits(team, opp, T, O, n, facets=CFB_TRAITS, top=TOP, exploit=EXPLOIT, bottom=35):
    """Strengths and weaknesses for `team` vs `opp`. A weakness is 'exploitable' only when the opponent's
    matching unit ranks in the top `exploit` and leans on that kind of play (pool-method rule 4).
    Defaults are for 138 FBS teams; the NFL panel passes its own 32-team cutoffs."""
    strengths, weak = [], []
    for side, names, other in (("o", OFF_NAME, "d"), ("d", DEF_NAME, "o")):
        for f in facets:
            r = (T.get(f) or {}).get("r" + side)
            if r is None:
                continue
            if r <= top:
                strengths.append((r, f"{names[f]} {ordn(r)}"))
            elif r > n - bottom:
                ro = (O.get(f) or {}).get("r" + other)
                oname = (DEF_NAME if other == "d" else OFF_NAME)[f]
                ok, why = _usage_ok(f, O, n) if side == "d" else (True, "")
                if ro is not None and ro <= exploit and ok:
                    weak.append((-r, f"{names[f]} {ordn(r)}: <b>exploitable</b>, {esc(opp)}'s {oname} is {ordn(ro)}"))
                else:
                    reason = why or (f"{esc(opp)}'s {oname} is only {ordn(ro)}" if ro else "opponent unranked")
                    weak.append((n - r, f"{names[f]} {ordn(r)}: probably won't matter, {reason}"))
    strengths = [s for _, s in sorted(strengths)[:4]]
    weak = [w for _, w in sorted(weak)[:4]]
    return strengths, weak


def edges(a, h, A, H, n):
    """Biggest unit-vs-unit mismatches either way, weighted by how much the offense uses that play type."""
    out = []
    for off, dfn, O, D in ((a, h, A, H), (h, a, H, A)):
        rr = (O.get("runrate") or {}).get("o", 0.5)
        for f, w in (("epa", 1.2), ("rush", rr / 0.5), ("pass", (1 - rr) / 0.5), ("expl", 0.9), ("pdsr", 0.9), ("havoc", 0.8)):
            ro, rd = (O.get(f) or {}).get("ro"), (D.get(f) or {}).get("rd")
            if ro is None or rd is None:
                continue
            e = _pct(ro, n) - _pct(rd, n)
            if abs(e) < 0.3:
                continue
            lean = ""
            if f == "rush" and rr >= 0.55:
                lean = f", runs {rr * 100:.0f}%"
            elif f == "pass" and rr <= 0.45:
                lean = f", passes {(1 - rr) * 100:.0f}%"
            o_txt = f"{esc(off)}'s {OFF_NAME[f]} ({ordn(ro)}{lean})"
            d_txt = f"{esc(dfn)}'s {DEF_NAME[f]} ({ordn(rd)})"
            txt = f"{o_txt} vs {d_txt}: edge <b>{esc(off)}</b>" if e > 0 else f"{d_txt} vs {o_txt}: edge <b>{esc(dfn)}</b>"
            out.append((abs(e) * min(max(w, 0.6), 1.4), txt))
    return [t for _, t in sorted(out, reverse=True)[:3]]


# ---------- research ----------

_NOT_SAME = r"(?![ ](state|st\b|st\.|tech|a&m|atlantic|international|intl|christian)|\s*\()"


def notes_for(notes, names):
    pats = [re.compile(r"(?<![a-z])" + re.escape(x.lower()) + r"(?![a-z])" + _NOT_SAME) for x in names if x and len(x) >= 3]
    return list(dict.fromkeys(nt for nt in notes if any(p.search(nt.lower()) for p in pats)))


def research_html(items, notes, researched):
    li = []
    for a in items:
        eff = []
        if a.get("off_pts"):
            eff.append(f"offense {a['off_pts']:+g} pts")
        if a.get("def_pts"):
            eff.append(f"points allowed {a['def_pts']:+g}")
        tag = ("model: " + ", ".join(eff)) if eff else "no model change"
        if a.get("priced"):
            tag += "; market already has it"
        li.append(f"<li><b>{esc(a['team'])}</b>: {esc(a.get('status') or a.get('reason'))} <span class='mk'>({tag}; "
                  f"{esc(a.get('published', '?'))}, {link(a['source'])})</span></li>")
    for nt in notes:
        li.append(f"<li>{esc(nt)} <span class='mk'>(research run {esc(researched)}, {link(RESEARCH_LOG, 'log')})</span></li>")
    return "<ul>" + "".join(li) + "</ul>" if li else "<p class='mk'>No injury or news items found for either team this week.</p>"


# ---------- breakdown builders ----------

def _venue_line(g, ev, wx):
    v = venues().get(g.get("venueId")) or {}
    name = (ev or {}).get("venue") or v.get("name") or "venue unknown"
    where = ", ".join(x for x in (v.get("city"), v.get("state")) if x)
    if v.get("dome") or (ev or {}).get("indoor"):
        return f"Indoors at {esc(name)}: no weather effect."
    if not wx:
        return f"{esc(name)}{', ' + esc(where) if where else ''}: no forecast yet (Open-Meteo covers 15 days)."
    adj = total_adjustment(wx)
    eff = f"model takes {-adj:.1f} pts off the total" if adj < 0 else "no scoring effect"
    return (f"{esc(name)}{', ' + esc(where) if where else ''}: {wx['temp']:.0f}°F at kickoff, wind up to {wx['wind']:.0f} mph, "
            f"{wx['precip']:.1f} mm rain over the game ({eff}). Open-Meteo forecast.")


def _move(open_s, now_s, home, away):
    if open_s is None or now_s is None:
        return ""
    d = now_s - open_s
    if abs(d) < 0.25:
        return "no movement since the open"
    toward = away if d > 0 else home
    keys = sorted({k for k in (3, 7, 10, 14) for s in (k, -k) if min(-open_s, -now_s) < s < max(-open_s, -now_s)})
    return f"moved {abs(d):g} toward {toward}" + (f", through {'/'.join(map(str, keys))}" if keys else "")


def cfb_breakdown(W, g, pools, ev, slate):
    """One college game. `pools`: [(pool, slate game, card row or None)]."""
    import numpy as np
    from .cards import fair_margins, MODEL_W
    from .sim import p_cover
    P = profiles(W.year, W.week)
    n = P["_n"]
    h, a = g["homeTeam"], g["awayTeam"]
    H, A = P.get(h, {}), P.get(a, {})
    S = W.sim(g)
    mk = W.lines.get(g["id"]) or {}
    flip_ev = bool(ev) and norm(h) in ev["away_names"]
    hs = mk.get("home_spread")
    stats_m = S["mh"] - S["ma"]
    pm = float((S["h"] > S["a"]).mean())
    m, _ = fair_margins(W, g)
    center = float(np.mean(m))
    lines = []
    if ev:
        k = ("away", "home") if flip_ev else ("home", "away")
        rank = lambda side: f"#{ev[side + '_rank']} " if ev.get(side + "_rank") else ""
        recs = f"{rank(k[1])}{esc(a)} ({ev.get(k[1] + '_record') or '?'}) @ {rank(k[0])}{esc(h)} ({ev.get(k[0] + '_record') or '?'})"
        if ev.get("state") == "post":
            recs += f" · <b>Final {esc(a)} {ev.get(k[1] + '_score')}, {esc(h)} {ev.get(k[0] + '_score')}</b>"
        elif ev.get("state") == "in":
            recs += f" · in progress {esc(a)} {ev.get(k[1] + '_score')}, {esc(h)} {ev.get(k[0] + '_score')}"
        lines.append(recs)
    lines.append(f"{kick_ct(g['startDate'])} CT" + (f" · TV {esc(ev['tv'])}" if ev and ev.get("tv") else "")
                 + (" · neutral site" if g.get("neutralSite") else ""))
    opn = mk.get("open_spread")
    if opn is None and ev and ev.get("open_home_spread") is not None:
        opn = -ev["open_home_spread"] if flip_ev else ev["open_home_spread"]
    if hs is not None:
        lines.append(f"Market now: <b>{esc(fav_line(h, a, hs))}</b>" + (f", total {mk['total']:g}" if mk.get("total") else "")
                     + f" <span class='mk'>({esc(mk.get('src') or 'CFBD consensus')})</span>")
        if opn is not None:
            lines.append(f"Opened {esc(fav_line(h, a, opn))}: {_move(opn, hs, h, a)}.")
    gaps = []
    for pool, sg, _ in pools:
        if pool == "yahoo" or sg.get("home_spread") is None:
            continue
        flipped = norm(sg["home"]) != norm(h)
        line = f"{pool.upper()} line {esc(fmt_spread(sg['home'], sg['home_spread']))}"
        if hs is not None:
            r = gap_row(pool, sg, {"home_spread": hs, "book": "market", "kick": g["startDate"], "id": g["id"]}, flipped, "CFB")
            if r["gap"]:
                line += (f": <b>{r['gap']:g} pts better for {esc(r['side'])}</b> than the market"
                         + (f", gains {'/'.join(map(str, r['keys']))}" if r["keys"] else "") + (" (stale)" if r["flag"] else ""))
            else:
                line += ": same as the market"
        gaps.append(line)
    lines += gaps

    model = [f"Stats model (opponent-adjusted EPA and success rate, SP+ prior, news and weather): "
             f"<b>{esc(h)} {S['mh']:.0f}, {esc(a)} {S['ma']:.0f}</b>, {esc(by(h, a, stats_m))}; {esc(h)} wins {pct(pm)} of 10k sims."]
    if hs is not None:
        mkt_p = mk.get("p_home")
        model.append(f"Market: {esc(by(h, a, -hs))}; {esc(h)} wins {pct(mkt_p)}." if mkt_p is not None else f"Market: {esc(by(h, a, -hs))}.")
        diff = stats_m - (-hs)
        model.append(f"Model vs market: {abs(diff):.1f} pts {'more' if diff > 0 else 'less'} on {esc(h)}"
                     + (" (a real disagreement: check the news)" if abs(diff) >= 7 else "")
                     + f". ATS cards center on <b>{esc(by(h, a, center))}</b> (market + {MODEL_W:g} × the gap + unpriced news); "
                       "the backtest had the market ahead of the model 75% to 70% straight-up.")
    sph, spa = (H.get("sp") or {}).get("o"), (A.get("sp") or {}).get("o")
    if sph is not None and spa is not None:
        spm = sph - spa + (0 if g.get("neutralSite") else SP_HFA)
        model.append(f"SP+ (Bill Connelly, current ratings via CFBD): <b>{esc(by(h, a, spm))}</b>"
                     + (f", {abs(spm + hs):.1f} pts {'more' if spm > -hs else 'less'} on {esc(h)} than the market" if hs is not None else "")
                     + ". Built from the same kind of play data as our model, so it isn't a separate signal under rule 3; not backtested.")
    for pool, sg, _ in pools:
        if pool == "yahoo" or sg.get("home_spread") is None:
            continue
        mm = -m if norm(sg["home"]) != norm(h) else m
        ph = p_cover(mm, sg["home_spread"])
        model.append(f"{pool.upper()} cover at the pool line: {esc(sg['home'])} {pct(ph)}, {esc(sg['away'])} {pct(1 - ph)} (before line points).")

    rows = []
    for title, side in (("Offense", "o"), ("Defense (allowed)", "d")):
        rows.append(f"<tr class='sh'><td colspan='3'>{title}</td></tr>")
        for key, label, _, _ in FACETS + [("havoc", "Havoc rate", None, False)]:
            rows.append(f"<tr><td>{label}</td><td>{_cell(key, side, A, n)}</td><td>{_cell(key, side, H, n)}</td></tr>")
    rows.append("<tr class='sh'><td colspan='3'>Style and form</td></tr>")
    rows.append(f"<tr><td>Plays/game</td><td>{_cell('pace', 'o', A, n)}</td><td>{_cell('pace', 'o', H, n)}</td></tr>")
    rows.append(f"<tr><td>Run rate</td><td>{_cell('runrate', 'o', A, n)}</td><td>{_cell('runrate', 'o', H, n)}</td></tr>")
    sp_cell = lambda T: f"{T['sp']['o']:+.1f} <span>{ordn(T['sp']['ro'])}</span>" if T.get("sp") else "—"
    tal_cell = lambda T: f"{T['talent']['o']:.0f} <span>{ordn(T['talent']['ro'])}</span>" if T.get("talent") else "—"
    rows.append(f"<tr><td>SP+ (now)</td><td>{sp_cell(A)}</td><td>{sp_cell(H)}</td></tr>")
    rows.append(f"<tr><td>Talent (247)</td><td>{tal_cell(A)}</td><td>{tal_cell(H)}</td></tr>")
    form = lambda T: " ".join(f"{r}" for r, *_ in T.get("games", [])[-3:]) or "—"
    rows.append(f"<tr><td>Last 3</td><td>{form(A)}</td><td>{form(H)}</td></tr>")
    table = (f"<table class='mt'><thead><tr><th></th><th>{esc(a)}</th><th>{esc(h)}</th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>"
             f"<p class='mk'>Per game vs an average opponent, opponent-adjusted (havoc, plays, run rate, SP+ and talent are raw). "
             f"#rank of {n} FBS; green top {TOP}, red bottom 35. Games before week {W.week}.</p>")
    ed = edges(a, h, A, H, n)
    tr = []
    for t, o, T, O in ((a, h, A, H), (h, a, H, A)):
        s, w = traits(t, o, T, O, n)
        tr.append(f"<p><b>{esc(t)}</b><br>Strengths: {', '.join(s) or 'none in the top ' + str(TOP)}<br>"
                  f"Weaknesses: {'; '.join(w) or 'none in the bottom 35'}</p>")
    last = lambda T, t: "; ".join(f"{r} {me}-{them} {at} {esc(o)}" for r, me, them, at, o in T.get("games", [])[-3:])
    form_txt = f"<p class='mk'>{esc(a)}: {last(A, a) or '—'}<br>{esc(h)}: {last(H, h) or '—'}</p>"

    items = W.research.get(norm(h), []) + W.research.get(norm(a), [])
    names = {h, a} | {x for _, sg, _ in pools for x in (sg["home"], sg["away"])}
    if ev:
        names |= {ev["home"], ev["away"]}
    researched = _researched(W)
    news = research_html(items, notes_for(W.notes, names), researched)
    bottom = _bottom(h, a, stats_m, hs, ed)
    return {"lines": lines, "model": model, "table": table, "edges": ed, "traits": "".join(tr) + form_txt,
            "news": news, "weather": _venue_line(g, ev, S.get("wx")), "bottom": bottom,
            "stats": cfb_stats_dict(P, h, a, W.week, stats_m)}


CFB_DICT = [k for k, *_ in FACETS] + ["havoc"]


def cfb_stats_dict(P, h, a, week, stats_margin=None):
    """Compact per-game stats for data/cards.json `game_stats` (same shape as pp.nflverse.stats_dict):
    {team: {"o_<facet>": [value, rank], "d_<facet>": [...], "sp", "talent", "pace", "runrate"}}; rank 1 = best
    of P["_n"] FBS teams (for runrate 1 = most run-heavy, pace 1 = most plays)."""
    rnd = lambda x: None if x is None else round(float(x), 4)
    out = {"source": "CFBD game advanced stats, opponent-adjusted; SP+ and talent via CFBD", "through_week": week - 1,
           "n_teams": P.get("_n"), "teams": {}}
    if stats_margin is not None:
        out["stats_home_margin"] = round(float(stats_margin), 1)
    for t in (a, h):
        T, d = P.get(t, {}), {}
        for k in CFB_DICT:
            f = T.get(k) or {}
            d["o_" + k] = [rnd(f.get("o")), f.get("ro")]
            d["d_" + k] = [rnd(f.get("d")), f.get("rd")]
        for k in ("sp", "talent", "pace", "runrate"):
            f = T.get(k) or {}
            d[k] = [rnd(f.get("o")), f.get("ro")]
        out["teams"][t] = d
    return out


def _researched(W):
    return W.researched_at[:10] if getattr(W, "researched_at", None) else "this week"


def _bottom(h, a, stats_m, hs, ed):
    if hs is None:
        return f"Stats make it {esc(by(h, a, stats_m))}; no market line."
    diff = stats_m - (-hs)
    s = f"Market {esc(by(h, a, -hs))}; stats {esc(by(h, a, stats_m))}"
    s += " (close to the market)." if abs(diff) < 3 else f" ({abs(diff):.0f} pts {'more' if diff > 0 else 'less'} on {esc(h)})."
    if ed:
        s += " Biggest mismatch: " + ed[0] + "."
    return s


# ---------- NFL ----------

@lru_cache(None)
def nfl_games(year=2026, through_week=18):
    """Completed NFL games [(week, home, away, home pts, away pts)]: nflverse first, ESPN as the backup."""
    from . import nflverse
    try:
        return [(r["week"], r["home"], r["away"], r["home_score"], r["away_score"])
                for r in nflverse.results(year, current=year) if r["week"] <= through_week]
    except Exception as ex:
        print("nflverse results unavailable, using ESPN:", ex)
    from .nfl import SB
    out = []
    for w in range(1, through_week + 1):
        d = get_json("espn", SB, max_age_h=12, seasontype=2, week=w, dates=year)
        for e in d.get("events", []):
            c = e["competitions"][0]
            if not c["status"]["type"]["completed"]:
                continue
            t = {x["homeAway"]: x for x in c["competitors"]}
            out.append((w, t["home"]["team"]["abbreviation"], t["away"]["team"]["abbreviation"],
                        int(t["home"]["score"]), int(t["away"]["score"])))
    return out


@lru_cache(None)
def nfl_profiles(year=2026):
    import numpy as np
    from .nfl import ratings
    R, hfa = ratings(year)
    P = {t: {"games": []} for t in R}
    for w, hm, aw, hs, as_ in nfl_games(year):
        for t, o, me, them, at in ((hm, aw, hs, as_, "vs"), (aw, hm, as_, hs, "@")):
            P.setdefault(t, {"games": []})["games"].append(("W" if me > them else ("L" if me < them else "T"), me, them, at, o))
    for t, p in P.items():
        gs = p["games"]
        p["rating"] = R.get(t)
        p["pf"] = np.mean([x[1] for x in gs]) if gs else None
        p["pa"] = np.mean([x[2] for x in gs]) if gs else None
        p["rec"] = f"{sum(x[0] == 'W' for x in gs)}-{sum(x[0] == 'L' for x in gs)}" + (f"-{sum(x[0] == 'T' for x in gs)}" if any(x[0] == "T" for x in gs) else "")
    for key, hb in (("rating", True), ("pf", True), ("pa", False)):
        rk = _rank({t: p[key] for t, p in P.items()}, hb, list(P))
        for t in P:
            P[t]["r_" + key] = rk.get(t)
    return P, hfa


def nfl_injuries(teams):
    """ESPN's public NFL injury report: Out/Doubtful players for these teams, each with ESPN's dated note."""
    try:
        d = get_json("espn", NFL_INJ, max_age_h=3)
    except Exception as ex:
        print("ESPN NFL injuries unavailable:", ex)
        return []
    out = []
    for team in d.get("injuries", []):
        for it in team.get("injuries", []):
            ath = it.get("athlete") or {}
            ab = (ath.get("team") or {}).get("abbreviation")
            if ab in teams and it.get("status") in ("Out", "Doubtful"):
                url = next((l["href"] for l in ath.get("links", []) if "/player/" in l.get("href", "")), None)
                out.append({"team": ab, "name": ath.get("displayName"), "pos": (ath.get("position") or {}).get("abbreviation", ""),
                            "status": it["status"], "note": it.get("shortComment") or "", "date": (it.get("date") or "")[:10], "url": url})
    return out


# nflverse play-by-play facets (pp.nflverse.profiles): opponent-adjusted per play; style rows are raw.
NFL_FACETS = [("epa", "EPA/play"), ("sr", "Success rate"), ("pass", "EPA/dropback"), ("rush", "EPA/rush"), ("expl", "Explosive plays")]
NFL_STYLE = [("ed_pass", "Early-down pass rate"), ("proe", "Pass rate over expected"), ("cpoe", "CPOE"), ("to_pg", "Giveaways/g")]
NFL_TOP, NFL_EXPLOIT, NFL_BOTTOM = 8, 12, 8  # of 32: strength top 8, exploitable by a top-12 unit, weakness bottom 8


def nfl_epa(year, week):
    """nflverse profiles for games before NFL `week`, plus a runrate facet (early-down run share, rank 1 =
    most run-heavy) so traits() can apply rule 4. {} when nflverse is unavailable."""
    from . import nflverse
    try:
        P = {t: dict(v) for t, v in nflverse.profiles(year, week or 99).items()}
    except Exception as ex:
        print("nflverse unavailable for breakdowns:", ex)
        return {}
    run = {t: 1 - p["ed_pass"]["o"] for t, p in P.items() if (p.get("ed_pass") or {}).get("o") is not None}
    rk = _rank(run, True, list(run))
    for t, v in run.items():
        P[t]["runrate"] = {"o": v, "ro": rk.get(t)}
    return P


def _ncell(key, side, T):
    s = T.get(key) or {}
    v, r = s.get(side), s.get("r" + side)
    if v is None:
        return "—"
    if key in ("sr", "expl", "ed_pass"):
        txt = f"{v * 100:.0f}%"
    elif key in ("proe", "cpoe"):
        txt = f"{v:+.1f}"
    elif key == "to_pg":
        txt = f"{v:.1f}"
    else:
        txt = f"{v:+.2f}".replace("0.", ".")
    cls = " class='g'" if r and r <= NFL_TOP else (" class='r'" if r and r > 32 - NFL_BOTTOM else "")
    return f"{txt} <span{cls}>{ordn(r)}</span>"


def nfl_breakdown(sg, ev, flipped, slate, pools, rng, year=2026):
    from .nfl import nfl_sim, stats_margin, MODEL_W
    from .sim import p_cover
    P, hfa = nfl_profiles()
    h, a = sg["home"], sg["away"]
    H, A = P.get(h, {}), P.get(a, {})
    lines = []
    if ev:
        k = ("away", "home") if flipped else ("home", "away")
        lines.append(f"{esc(a)} ({ev.get(k[1] + '_record') or A.get('rec', '?')}) @ {esc(h)} ({ev.get(k[0] + '_record') or H.get('rec', '?')})"
                     + (f" · <b>Final {esc(a)} {ev.get(k[1] + '_score')}, {esc(h)} {ev.get(k[0] + '_score')}</b>" if ev.get("state") == "post" else ""))
        lines.append(f"{kick_ct(ev['kick'])} CT" + (f" · TV {esc(ev['tv'])}" if ev.get("tv") else "") + f" · NFL week {sg.get('nfl_week', '?')}")
    hs = None
    if ev and ev.get("home_spread") is not None:
        hs = -ev["home_spread"] if flipped else ev["home_spread"]
        lines.append(f"Market now: <b>{esc(fav_line(h, a, hs))}</b>" + (f", total {ev['total']:g}" if ev.get("total") else "") + f" <span class='mk'>({esc(ev['book'])})</span>")
        if ev.get("open_home_spread") is not None:
            o = -ev["open_home_spread"] if flipped else ev["open_home_spread"]
            lines.append(f"Opened {esc(fav_line(h, a, o))} ({esc(ev['book'])}): {_move(o, hs, h, a)}.")
        r = gap_row("bto", sg, ev, flipped, "NFL")
        lines.append(f"BTO line {esc(fmt_spread(h, sg['home_spread']))}: " + (
            f"<b>{r['gap']:g} pts better for {esc(r['side'])}</b> than the market" + (f", gains {'/'.join(map(str, r['keys']))}" if r["keys"] else "")
            if r["gap"] else "same as the market"))
    elif sg.get("market_home_spread") is not None:
        hs = sg["market_home_spread"]
        lines.append(f"Market (research run): {esc(fav_line(h, a, hs))}; BTO line {esc(fmt_spread(h, sg['home_spread']))}.")
    wk = sg.get("nfl_week")
    E = nfl_epa(year, wk)
    EH, EA = E.get(h, {}), E.get(a, {})
    stats, src = stats_margin(h, a, wk, sg.get("neutral"), year)
    score_m = (H.get("rating") or 0) - (A.get("rating") or 0) + (0 if sg.get("neutral") else hfa)
    if src.startswith("nflverse"):
        model = [f"EPA model (opponent-adjusted EPA/play and success rate, nflverse play-by-play): <b>{esc(by(h, a, stats))}</b>. "
                 f"Power ratings from scores alone: {esc(by(h, a, score_m))}."]
    else:
        model = [f"Power ratings (this season's scores, ridge): {esc(h)} {H.get('rating', 0):+.1f} ({ordn(H.get('r_rating'))}), "
                 f"{esc(a)} {A.get('rating', 0):+.1f} ({ordn(A.get('r_rating'))}), home field {hfa:+.1f} → <b>{esc(by(h, a, stats))}</b>."]
    if hs is not None:
        diff = stats - (-hs)
        model.append(f"Market {esc(by(h, a, -hs))}: stats {abs(diff):.1f} pts {'more' if diff > 0 else 'less'} on {esc(h)}. "
                     + (f"The card centers on the market + {MODEL_W:g} × that gap + research ({sg.get('adj_home_pts', 0):+g} pts)." if MODEL_W else
                        f"The card centers on the market + research ({sg.get('adj_home_pts', 0):+g} pts): in the 2023-26 backtest, "
                        "leaning toward the stats lost to the closing line every season."))
    if not sg.get("locked"):
        try:
            m, _, _ = nfl_sim(sg, rng)
            ph = p_cover(m, sg["home_spread"])
            model.append(f"BTO cover at the pool line: {esc(h)} {pct(ph)}, {esc(a)} {pct(1 - ph)} (before line points).")
        except Exception as ex:
            print("NFL cover sim skipped:", ex)
    rows = []
    if E:
        for title, side in (("Offense", "o"), ("Defense (allowed)", "d")):
            rows.append(f"<tr class='sh'><td colspan='3'>{title}</td></tr>")
            rows += [f"<tr><td>{label}</td><td>{_ncell(k, side, EA)}</td><td>{_ncell(k, side, EH)}</td></tr>" for k, label in NFL_FACETS]
        rows.append("<tr class='sh'><td colspan='3'>Style and form</td></tr>")
        rows += [f"<tr><td>{label}</td><td>{_ncell(k, 'o', EA)}</td><td>{_ncell(k, 'o', EH)}</td></tr>" for k, label in NFL_STYLE]
    rows += [f"<tr><td>Record</td><td>{esc(A.get('rec', '—'))}</td><td>{esc(H.get('rec', '—'))}</td></tr>",
            f"<tr><td>Power rating</td><td>{A.get('rating', 0):+.1f} {ordn(A.get('r_rating'))}</td><td>{H.get('rating', 0):+.1f} {ordn(H.get('r_rating'))}</td></tr>",
            f"<tr><td>Points/g</td><td>{A.get('pf') or 0:.1f} {ordn(A.get('r_pf'))}</td><td>{H.get('pf') or 0:.1f} {ordn(H.get('r_pf'))}</td></tr>",
            f"<tr><td>Allowed/g</td><td>{A.get('pa') or 0:.1f} {ordn(A.get('r_pa'))}</td><td>{H.get('pa') or 0:.1f} {ordn(H.get('r_pa'))}</td></tr>",
            f"<tr><td>Last 3</td><td>{' '.join(x[0] for x in A.get('games', [])[-3:]) or '—'}</td><td>{' '.join(x[0] for x in H.get('games', [])[-3:]) or '—'}</td></tr>"]
    note = (f"Per play vs an average opponent, opponent-adjusted, from {link(NFLVERSE, 'nflverse')} play-by-play (CC BY 4.0; dropbacks and runs; explosive = "
            f"20+ yd pass or 10+ yd run). Style rows are raw season averages; early-down pass rate is in neutral game states "
            f"(10-90% win chance, outside the last 2 minutes of a half). #rank of 32; green top {NFL_TOP}, red bottom {NFL_BOTTOM}. "
            f"Games before NFL week {wk}." if E else "#rank of 32. nflverse play-by-play was unavailable, so scores only (ESPN).")
    table = (f"<table class='mt'><thead><tr><th></th><th>{esc(a)}</th><th>{esc(h)}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
             f"<p class='mk'>{note}</p>")
    tr = []
    ed = edges(a, h, EA, EH, 32) if E else []
    for t, o, T, O, ET, EO in ((a, h, A, H, EA, EH), (h, a, H, A, EH, EA)):
        last = "; ".join(f"{r} {me}-{them} {at} {esc(op)}" for r, me, them, at, op in T.get("games", [])[-3:])
        if E:
            s, w = traits(t, o, ET, EO, 32, facets=("epa", "sr", "pass", "rush", "expl"), top=NFL_TOP, exploit=NFL_EXPLOIT, bottom=NFL_BOTTOM)
            tr.append(f"<p><b>{esc(t)}</b><br>Strengths: {', '.join(s) or f'none in the top {NFL_TOP}'}<br>"
                      f"Weaknesses: {'; '.join(w) or f'none in the bottom {NFL_BOTTOM}'}<br><span class='mk'>Last 3: {last or '—'}</span></p>")
            continue
        s, w = [], []
        for key, name, oppkey, oppname in (("r_pf", "scoring offense", "r_pa", "scoring defense"), ("r_pa", "scoring defense", "r_pf", "scoring offense")):
            r, ro = T.get(key), O.get(oppkey)
            if r and r <= 8:
                s.append(f"{name} {ordn(r)}")
            elif r and r >= 25:
                w.append(f"{name} {ordn(r)}: " + (f"<b>exploitable</b>, {esc(o)}'s {oppname} is {ordn(ro)}" if ro and ro <= 16
                                                   else f"probably won't matter, {esc(o)}'s {oppname} is {ordn(ro)}"))
        tr.append(f"<p><b>{esc(t)}</b><br>Strengths: {', '.join(s) or 'none top 8'}<br>Weaknesses: {'; '.join(w) or 'none bottom 8'}"
                  f"<br><span class='mk'>Last 3: {last or '—'}</span></p>")
    checked = (slate.get("read_at_bto_cfp") or slate.get("read_at") or "")[:10]
    li = [f"<li>{esc(w['reason'])} <span class='mk'>(checked {esc(checked)}, {link(w['source'])})</span></li>" for w in sg.get("why", [])]
    for i in nfl_injuries({h, a}):
        li.append(f"<li><b>{esc(i['team'])} {esc(i['name'])}</b> {esc(i['pos'])} {esc(i['status'])}: {esc(i['note'])} "
                  f"<span class='mk'>(ESPN {esc(i['date'])}{', ' + link(i['url'], 'player card') if i['url'] else ''})</span></li>")
    news = "<ul>" + "".join(li) + "</ul>" if li else "<p class='mk'>No injury or news items.</p>"
    if ev and ev.get("indoor"):
        wx = f"Indoors at {esc(ev.get('venue') or 'the stadium')}: no weather effect."
    else:
        wx = (f"{esc((ev or {}).get('venue') or 'Outdoors')}: weather comes from the research run; "
              "no Open-Meteo pull for NFL games (see the news items above).")
    bottom = (f"Market {esc(by(h, a, -hs))}; stats {esc(by(h, a, stats))}." if hs is not None else f"Stats {esc(by(h, a, stats))}.")
    if ed:
        bottom += " Biggest mismatch: " + ed[0] + "."
    st = None
    if E:
        from .nflverse import stats_dict
        try:
            st = stats_dict(year, wk or 99, h, a)
            st["stats_home_margin"] = round(float(stats), 1)
        except Exception as ex:
            print("NFL stats dict skipped:", ex)
    return {"lines": lines, "model": model, "table": table, "edges": ed, "traits": "".join(tr), "news": news,
            "weather": wx, "bottom": bottom, "stats": st}


# ---------- pool context ----------

def pool_html(pools):
    li = []
    for pool, sg, row in pools:
        if pool == "yahoo":
            pub = sg.get("pub") or {}
            s = (f"Yahoo: {esc(sg['away'])} {pub.get(sg['away'], '?')}% · {esc(sg['home'])} {pub.get(sg['home'], '?')}% of Yahoo players"
                 + (f"; card picks <b>{esc(row['pick'])}</b>" if row else "")
                 + (f" ({esc(row['wager'])})" if row and row.get("wager") else ""))
        elif pool == "bto":
            s = (f"BTO{' Big Game ★' if sg.get('big') else ''}: pool line {esc(fmt_spread(sg['home'], sg['home_spread']))}"
                 + ("; locked" if sg.get("locked") else "")
                 + (f"; card: <b>{esc(row['pick'])}</b> for {esc(row['wager'])}" if row else "; not on the card"))
        else:
            s = (f"CFP: pool line {esc(fmt_spread(sg['home'], sg['home_spread']))}"
                 + (f"; card: <b>{esc(row['pick'])}</b>, stake {esc(row['wager'])} pts" if row else "; not on the card"))
        li.append(f"<li>{s}</li>")
    return "<ul>" + "".join(li) + "</ul>"


def render_one(b):
    """HTML for one breakdown (goes in a <template>; the page clones it under the tapped row)."""
    ed = "".join(f"<li>{e}</li>" for e in b["edges"])
    return (f"<div class='bd'><p class='bl'>{b['bottom']}</p>"
            f"<h4>Kickoff and lines</h4><ul>{''.join(f'<li>{x}</li>' for x in b['lines'])}</ul>"
            f"<h4>Model vs market</h4><ul>{''.join(f'<li>{x}</li>' for x in b['model'])}</ul>"
            f"<h4>Matchup</h4>{b['table']}"
            + (f"<p><b>Key matchups</b></p><ul>{ed}</ul>" if ed else "")
            + f"{b['traits']}"
            f"<h4>Injuries and news</h4>{b['news']}"
            f"<h4>Weather</h4><p>{b['weather']}</p>"
            f"<h4>Pools</h4>{b['pools']}</div>")


def build(W, slate, cards):
    """All pool games' breakdowns. Returns (games, index) where games is a list of
    {id, kick, label, market, pools, html} sorted by kickoff, and index maps (card id, row key) -> id."""
    rows = {(c["id"], r["key"]): r for c in cards for r in c["rows"]}
    games, index = {}, {}
    try:
        ev_cfb = {e["id"]: e for e in espn_odds("CFB", W.week, W.year)}
    except Exception as ex:
        print("ESPN CFB scoreboard unavailable for breakdowns:", ex)
        ev_cfb = {}
    nfl_ev = {}
    for pool in ("yahoo", "bto", "cfp"):
        for sg in ((slate.get(pool) or {}).get("games") or []):
            key = f"{sg['away']}@{sg['home']}"
            if sg.get("league") == "NFL":
                bid = f"bd-nfl-{sg['away']}-{sg['home']}"
                ent = games.setdefault(bid, {"league": "NFL", "sg": sg, "pools": []})
            else:
                g = W.find(sg["away"], sg["home"])
                if g is None:
                    continue
                bid = f"bd-{g['id']}"
                ent = games.setdefault(bid, {"league": "CFB", "g": g, "pools": []})
            ent["pools"].append((pool, sg, rows.get((pool, key))))
            index[(pool, key)] = bid
    import numpy as np
    out = []
    rng = np.random.default_rng(7)
    for bid, ent in games.items():
        try:
            if ent["league"] == "NFL":
                sg = ent["sg"]
                wk = sg.get("nfl_week")
                if wk not in nfl_ev:
                    try:
                        nfl_ev[wk] = espn_odds("NFL", wk, W.year)
                    except Exception:
                        nfl_ev[wk] = []
                ev, flipped = espn_find(nfl_ev[wk], sg["away"], sg["home"])
                b = nfl_breakdown(sg, ev, flipped, slate, ent["pools"], rng)
                kick = (ev or {}).get("kick") or ""
                label, market = f"{sg['away']} @ {sg['home']}", None
                if ev and ev.get("home_spread") is not None:
                    market = fav_line(sg["home"], sg["away"], -ev["home_spread"] if flipped else ev["home_spread"])
            else:
                g = ent["g"]
                ev = ev_cfb.get(str(g["id"]))
                b = cfb_breakdown(W, g, ent["pools"], ev, slate)
                kick = g["startDate"]
                label = f"{g['awayTeam']} @ {g['homeTeam']}"
                hs = (W.lines.get(g["id"]) or {}).get("home_spread")
                market = fav_line(g["homeTeam"], g["awayTeam"], hs) if hs is not None else None
        except Exception as ex:  # one bad game never blocks the page
            print(f"breakdown skipped for {bid}: {ex!r}")
            continue
        b["pools"] = pool_html(ent["pools"])
        out.append({"id": bid, "kick": kick, "label": label, "market": market or "—", "league": ent["league"],
                    "pools": [(p, bool(r)) for p, _, r in ent["pools"]], "html": render_one(b), "stats": b.get("stats")})
    out.sort(key=lambda x: x["kick"] or "9999")
    return out, {k: v for k, v in index.items() if any(o["id"] == v for o in out)}
