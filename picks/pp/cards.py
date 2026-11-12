"""Build the weekly pick cards (data/cards.json + docs/index.html).

Usage: py -m pp.cards --stage draft|final|refresh [--pools yahoo,bto,cfp]
Inputs: slates/<year>-wNN.json (read from the pool sites), research/<year>-wNN-*.json (fresh
research with sources), CFBD cache, Open-Meteo. Market lines are shown for comparison and
used only after the stats model is built (blend for outcome sims, never as a model input).
"""
import argparse, glob, html, json, os, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from . import model as M
from .market import lines, NOTE as MARKET_NOTE
from .http import STALE as HTTP_STALE
from .lines import overlay
from .names import norm
from .push import compose as push_compose, _kick_dt
from .sim import sim_game, exact_score_pick, p_cover
from .weather import kickoff_weather, total_adjustment
from . import pools as P
from . import explain

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT.parent / "docs" / "picks"  # served by Sports HQ's GitHub Pages at /picks/
YEAR = 2026
CT = ZoneInfo("America/Chicago")  # cards show "CT"


def current_week():
    now = datetime.now(timezone.utc)
    up = [g["week"] for g in M.games(YEAR) if datetime.fromisoformat(g["startDate"].replace("Z", "+00:00")) > now - timedelta(hours=12)]
    return min(up)


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return np.log(p / (1 - p))


def blend(pm, pk):
    if pk is None:
        return pm
    return float(1 / (1 + np.exp(-(0.5 * logit(pm) + 0.5 * logit(pk)))))


def short(s, n=12):
    w = s.split()
    return " ".join(w[:n])


def load_research(week):
    adj, notes, at = {}, [], ""
    for f in sorted(glob.glob(str(ROOT / f"research/{YEAR}-w{week:02d}-*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for a in d.get("adjustments", []):
            adj.setdefault(norm(a["team"]), []).append(a)
        notes += d.get("notes", [])
        at = max(at, d.get("researched_at") or "")
    return adj, notes, at


class Week:
    def __init__(self, week):
        self.week, self.year = week, YEAR
        self.games = [g for g in M.games(YEAR) if g["week"] == week]
        self.by_pair = {(norm(g["awayTeam"]), norm(g["homeTeam"])): g for g in self.games}
        # CFBD lines (cached up to 6h, keeps the opener) with ESPN's current line on top
        # (no CFBD key/budget: a saved copy of any age, else ESPN's scoreboard; market.NOTE says which)
        self.lines = overlay(lines(YEAR, week, max_age_h=6, games=self.games), week, YEAR, self.games)
        self.research, self.notes, self.researched_at = load_research(week)
        self.rng = np.random.default_rng(2026 * 100 + week)
        self._sims = {}

    def find(self, away, home):
        a, h = norm(away), norm(home)
        return self.by_pair.get((a, h)) or self.by_pair.get((h, a))

    def team_adj(self, g, unpriced_only=False):
        adj = {g["homeTeam"]: 0.0, g["awayTeam"]: 0.0}
        why = []
        for t, o in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"])):
            for a in self.research.get(norm(t), []):
                if unpriced_only and a.get("priced"):
                    continue  # ATS pools center on the market line, which already reflects this news
                adj[t] += a.get("off_pts", 0)
                adj[o] += a.get("def_pts", 0)
                why.append(a)
        try:
            w = kickoff_weather(g)
        except Exception:
            w = None  # weather is a small adjustment; never block a card on it
        wt = total_adjustment(w)
        for t in adj:
            adj[t] += wt / 2
        return adj, why, w

    def sim(self, g):
        if g["id"] not in self._sims:
            adj, why, w = self.team_adj(g)
            mh, ma = M.project(YEAR, self.week, g["homeTeam"], g["awayTeam"], g.get("neutralSite"), adj)
            h, a = sim_game(mh, ma, self.rng)
            self._sims[g["id"]] = {"h": h, "a": a, "why": why, "wx": w, "mh": mh, "ma": ma}
        return self._sims[g["id"]]


MODEL_W = 0.1  # backtest (2026 wks 4-8): stats margin adds ~nothing beyond the market spread
ATS_SD = 14.5  # residual SD of actual margin around the closing spread, same backtest


def fair_margins(W, g):
    """ATS pools: margin sims centered on the current market spread plus research news and a small
    stats tilt. The edge comes from stale pool lines, line points and fresh news, not the raw model."""
    S = W.sim(g)
    m = (S["h"] - S["a"]).astype(float)
    mk = W.lines.get(g["id"])
    adj, _, _ = W.team_adj(g, unpriced_only=True)
    news = adj[g["homeTeam"]] - adj[g["awayTeam"]]
    if not mk:
        return np.rint(m), S
    stats_mu = S["mh"] - S["ma"] - news
    center = -mk["home_spread"] + MODEL_W * (stats_mu - (-mk["home_spread"])) + news
    return np.rint((m - m.mean()) * (ATS_SD / m.std()) + center), S


def anchored(W, g):
    """Method rules 6-7: tiebreaker scores start from market-implied team totals; the stats model
    (with research) may move each team by at most 3 points."""
    S = W.sim(g)
    mk = W.lines.get(g["id"])
    if not mk or mk.get("total") is None:
        return S["h"], S["a"]
    ih, ia = (mk["total"] - mk["home_spread"]) / 2, (mk["total"] + mk["home_spread"]) / 2
    th = ih + float(np.clip(S["mh"] - ih, -3, 3))
    ta = ia + float(np.clip(S["ma"] - ia, -3, 3))
    return (np.maximum(np.rint(S["h"] + th - S["h"].mean()), 0).astype(int),
            np.maximum(np.rint(S["a"] + ta - S["a"].mean()), 0).astype(int))


def yahoo_deadline(y):
    """Yahoo games lock 5 minutes before kickoff; name the first lock from the slate's kicks ('Fri 11/06 6:00 PM' CT)."""
    kicks = [k for k in (_kick_dt(g.get("kick")) for g in y.get("games", [])) if k]
    if not kicks:
        return "Games lock 5 min before kickoff"
    k = min(kicks) - timedelta(minutes=5)
    return f"Games lock 5 min before kickoff; first lock {k:%a} {k.hour % 12 or 12}:{k:%M}{'pm' if k.hour >= 12 else 'am'} CT"


def favors(a, team):
    """True when research item `a` helps `team`'s margin (off_pts < 0 hurts a.team, def_pts > 0 hurts it),
    so a pick's reason never cites news that argues for the other side (Nov 4: 'Sayin out' as the Ohio St. reason)."""
    edge = a.get("off_pts", 0) - a.get("def_pts", 0)
    return (edge if norm(a["team"]) == norm(team) else -edge) > 0


def research_why(S, g, team=None):
    """Most material research item for the game that favors `team`, prefixed with the team it concerns."""
    items = [a for a in S["why"] if abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0)) >= 1
             and (team is None or favors(a, team))]
    if team is not None:
        net = sum((1 if norm(a["team"]) == norm(team) else -1) * (a.get("off_pts", 0) - a.get("def_pts", 0)) for a in S["why"])
        if net <= 0:
            items = []  # the week's news on balance hurts the pick (Nov 4: Oregon's QB note cited for Ohio St. with Sayin out)
    if not items:
        return None, None
    a = max(items, key=lambda a: abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0)))
    return short(f"{a['team']}: {a['reason']}"), a["source"]


def ats_why(S, team=None):
    """ATS reasons: unpriced research items that favor `team`, most material first."""
    items = [a for a in S["why"] if not a.get("priced") and (team is None or favors(a, team))]
    return sorted(items, key=lambda a: -(abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0))))


def market_side_line(W, sg, g, side_home):
    """The market's spread for the pool side (home line flipped for the away side), or None."""
    if g is not None:
        mk = (W.lines.get(g["id"]) or {}).get("home_spread")
        if mk is not None and norm(sg["home"]) != norm(g["homeTeam"]):
            mk = -mk
    else:
        mk = sg.get("market_home_spread")
    return None if mk is None else (mk if side_home else -mk)


def gap_why(line, mkt, p, lp=0):
    """ATS fallback reason: the pool line vs the market, which is the edge when no news favors the side."""
    tail = f"cover {p*100:.0f}%" + (" after line points" if lp else "")
    if mkt is not None and mkt != line:
        return short(f"Pool {line:+g} vs market {mkt:+g}; {tail}")
    return short(f"Cover {p*100:.0f}% vs pool line at current market; top edge")


def src_link(g, research):
    if research:
        return research[0]["source"]
    return f"https://www.espn.com/college-football/game/_/gameId/{g['id']}"


def game_label(g, short_names):
    return f"{short_names.get(g['awayTeam'], g['awayTeam'])} @ {short_names.get(g['homeTeam'], g['homeTeam'])}"


def load_slate(week):
    """This week's slate; if the laptop hasn't read it yet, carry balances forward with no games."""
    f = ROOT / f"slates/{YEAR}-w{week:02d}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    prev = sorted(glob.glob(str(ROOT / f"slates/{YEAR}-w*.json")))
    s = json.loads(Path(prev[-1]).read_text(encoding="utf-8")) if prev else {"bto": {}, "cfp": {}}
    msg = "Slate not read from the site yet (laptop run missed)."
    s["label"] = f"CFBD week {week} (Yahoo week {week})"
    s["yahoo"] = None
    for k in ("bto", "cfp"):
        s[k] = {**{kk: vv for kk, vv in s.get(k, {}).items() if kk not in ("games", "status")}, "status": msg}
    return s


def build_yahoo(W, slate):
    y = slate["yahoo"]
    if not y:
        return {"id": "yahoo", "title": "Yahoo pick'em (Kosmos, 14)", "deadline": "", "rows": [],
                "status": "Slate not read from Yahoo yet (laptop run missed). Picks post when it is."}
    rows, idx, p_true, fav_home, pub_home, eligible, sims_tb2 = [], [], [], [], [], [], []
    names = {}
    for i, sg in enumerate(y["games"]):
        g = W.find(sg["away"], sg["home"])
        if g is None:
            raise SystemExit(f"Yahoo game not found in CFBD week {W.week}: {sg}")
        names[g["awayTeam"]], names[g["homeTeam"]] = sg["away"], sg["home"]
        home_is_cfbd_home = norm(sg["home"]) == norm(g["homeTeam"])
        S = W.sim(g)
        pm = float((S["h"] > S["a"]).mean())
        mk = W.lines.get(g["id"])
        pk = mk["p_home"] if mk else None
        pt = blend(pm, pk)
        fav = (pk if pk is not None else pm) >= 0.5
        pub = sg["pub"].get(sg["home"] if home_is_cfbd_home else sg["away"], 50) / 100
        # underdog rule: spread <= ~4, model disagrees, 2+ independent signals, group on favorite
        signals = []
        dog_home = not fav
        p_dog_model = pm if dog_home else 1 - pm
        if mk:
            spread = abs(mk["home_spread"])
            if p_dog_model > 0.5:
                signals.append("stats model")
            if mk.get("open_spread") is not None:
                move = mk["home_spread"] - mk["open_spread"]  # negative = moved toward home
                if (dog_home and move <= -1) or (not dog_home and move >= 1):
                    signals.append(f"line moved {abs(move):g} toward dog")
            dog_team = g["homeTeam"] if dog_home else g["awayTeam"]
            fav_team = g["awayTeam"] if dog_home else g["homeTeam"]
            for a in S["why"]:
                if (norm(a["team"]) == norm(fav_team) and (a.get("off_pts", 0) < -1 or a.get("def_pts", 0) > 1)) or \
                   (norm(a["team"]) == norm(dog_team) and a.get("off_pts", 0) > 1):
                    signals.append("injury news")
                    break
            pub_fav = pub if fav else 1 - pub
            if spread <= 4.5 and "stats model" in signals and len(signals) >= 2 and pub_fav >= 0.6:
                eligible.append(i)
        else:
            signals.append("no market line")
        rows.append({"g": g, "sg": sg, "pm": pm, "pk": pk, "S": S, "signals": signals, "mk": mk})
        p_true.append(pt); fav_home.append(fav); pub_home.append(pub)
        ah, aa = anchored(W, g)
        h_is_home = norm(sg["home"]) == norm(g["homeTeam"])
        sims_tb2.append((sg["home"], sg["away"], ah if h_is_home else aa, aa if h_is_home else ah))
    p_true, fav_home, pub_home = map(np.array, (p_true, fav_home, pub_home))
    picks, chosen, curve = P.yahoo_optimize(p_true, fav_home, eligible, pub_home, n_opp=y["group_size"] - 1)
    kept = keep_saved_picks(rows, picks, chosen, fav_home, p_true, pub_home, y)

    tb1 = {}
    for away, home in y["tb1"]:
        g = W.find(away, home)
        best, alt = exact_score_pick(*anchored(W, g))
        hn, an = (home, away) if norm(home) == norm(g["homeTeam"]) else (away, home)
        tb1[f"{away} @ {home}"] = {"pick": f"{an} {best[1]}, {hn} {best[0]}", "alt": f"{an} {alt[1]}, {hn} {alt[0]}",
                                   "short": f"TB1 {best[1]}-{best[0]}", "key": (away, home)}
    most, fewest = P.extremes(sims_tb2)

    out = []
    for i, r in enumerate(rows):
        g, sg, S, mk = r["g"], r["sg"], r["S"], r["mk"]
        home_pick = bool(picks[i])
        pick = sg["home"] if home_pick else sg["away"]
        pm = r["pm"] if home_pick else 1 - r["pm"]
        pk = None if r["pk"] is None else (r["pk"] if home_pick else 1 - r["pk"])
        is_dog = i in chosen
        rwhy, rsrc = research_why(S, g, pick)
        if i in kept:
            why = kept[i]
        elif is_dog:
            why = short(f"Upset: {', '.join(r['signals'])}; group on favorite")
        elif rwhy:
            why = rwhy
        elif S["wx"] and total_adjustment(S["wx"]) <= -2:
            why = short(f"Stats {pm*100:.0f}% win; wind {S['wx']['wind']:.0f} mph lowers scoring")
        else:
            gap = (pm - (pk or pm)) * 100
            if pm < 0.5:  # stats lean the other way; the favorite stays (Nov 5: Northwestern at 49% read "agrees")
                why = f"Stats {pm*100:.0f}%" + (f" vs market {pk*100:.0f}%" if pk is not None else "") + "; favorite kept"
            elif abs(gap) < 8:
                why = f"Stats {pm*100:.0f}% agrees with market"
            elif gap > 0:
                why = f"Stats {pm*100:.0f}%, stronger than market {pk*100:.0f}%"
            else:
                why = f"Stats {pm*100:.0f}% vs market {pk*100:.0f}%; favorite kept"
        tbs = ""
        for k, v in tb1.items():
            if v["key"] == (sg["away"], sg["home"]):
                tbs = v["short"]
        out.append({"game": f"{sg['away']} @ {sg['home']}", "kick": sg["kick"], "pick": pick + (" (dog)" if is_dog else ""),
                    "model": pm, "market": pk, "wager": tbs, "why": why, "source": rsrc or src_link(g, []),
                    "key": f"{sg['away']}@{sg['home']}", "pick_team": pick})
    n_dogs = len(chosen)
    watch = upset_watch(rows, picks, set(chosen) | set(kept), pub_home) + group_value(rows, picks, fav_home, p_true, pub_home, y)
    return {
        "id": "yahoo", "title": "Yahoo pick'em (Kosmos, 14)", "deadline": yahoo_deadline(y),
        "rows": out,
        "tiebreakers": [
            *[f"TB1 {k}: <b>{v['pick']}</b> (alt {v['alt']})" for k, v in tb1.items()],
            f"TB2 most points: <b>{most[0][0]}</b> ({most[0][1]*100:.0f}%), alt {most[1][0]} ({most[1][1]*100:.0f}%)",
            f"TB2 fewest points: <b>{fewest[0][0]}</b> ({fewest[0][1]*100:.0f}%), alt {fewest[1][0]} ({fewest[1][1]*100:.0f}%)",
            f"TB2 locks {y['tb2_deadline']}",
        ],
        "notes": [f"Underdogs: {n_dogs}. Pool sim (10k): P(win week) {max(curve)*100:.1f}% vs {curve[0]*100:.1f}% all favorites; {len(eligible)} dogs passed the 4-pt / 2-signal rule.",
                  f"Group: you {y['standings']['me']} pts, rank {y['standings']['rank']}, leader {y['standings']['leader']}."]
                 + watch,
    }


REBUILT = 0.10   # returned under 10% of last season's production (CFBD returning production, PPA share)


def rebuilt_note(teams):
    """teams: [(CFBD name, label)]. The stats model still gives last season ~3 games of weight (the backtest keeps
    that: it predicts best overall), so for a rebuilt roster it leans on a team that no longer exists."""
    try:
        ret = M._ret(YEAR)
    except Exception:
        return None
    low = [(label, ret.get(t, {}).get("percentPPA")) for t, label in teams]
    low = [(label, r) for label, r in low if r is not None and r < REBUILT]
    if not low:
        return None
    who = " and ".join(f"{label} ({max(r, 0) * 100:.0f}%)" for label, r in low)
    return (f"rebuilt roster{'s' if len(low) > 1 else ''}: {who} returned almost none of last year's production, "
            f"so our stats lean on last season here; trust the betting odds")


def cite(a):
    """Linked source with its publish date, so every research claim can be checked: 'on3.com, Oct 31'."""
    m = re.match(r"https?://(?:www\.)?([^/]+)", a.get("source") or "")
    site = m.group(1) if m else ""
    day = ""
    if a.get("published"):
        d = datetime.fromisoformat(a["published"][:10])
        day = f", {d.strftime('%b')} {d.day}"
    return f'<a href="{html.escape(a.get("source") or "")}">{html.escape(site)}{day}</a>' if site else "no source"


def season_flips(rows, picks, fav_home, p_true, pub_home):
    """Season-long value of flipping each open game's pick (pp.yahoo_value). Returns None without a group
    profile, else (base, vals, combo, games, meta, row_index) with one entry per open game."""
    from . import yahoo_value as V
    prof = V.load_profile()
    if not prof:
        return None
    now = datetime.now(timezone.utc)
    games, meta, idx = [], [], []
    for i, r in enumerate(rows):
        start = r["g"].get("startDate")
        if r["mk"] is None or (start and datetime.fromisoformat(start.replace("Z", "+00:00")) <= now):
            continue
        fh = bool(fav_home[i])
        games.append({"p_fav": p_true[i] if fh else 1 - p_true[i], "spread": abs(r["mk"]["home_spread"]),
                      "pub_dog": (1 - pub_home[i]) if fh else pub_home[i], "my_dog": bool(picks[i]) != fh})
        sg = r["sg"]
        meta.append(((sg["home"], sg["away"]) if fh else (sg["away"], sg["home"]), sg["kick"]))
        idx.append(i)
    if not games:
        return None
    base, vals, combo = V.season_values(games, prof)
    return base, vals, combo, games, meta, idx, prof


def keep_saved_picks(rows, picks, chosen, fav_home, p_true, pub_home, y):
    """Where Michael saved the other side and the card's own season sim says that side raises his chance to win
    the group, the card keeps his pick instead of telling him to switch (Nov 12: the card said 'switch Kansas to
    West Virginia' while its own notes said Kansas raised his chance 0.8% -> 1.0%). Flips picks in place.
    Returns {row index: reason}."""
    saved = ((y.get("saved") or {}).get("picks")) or {}
    if not saved:
        return {}
    sv = season_flips(rows, picks, fav_home, p_true, pub_home)
    if not sv:
        return {}
    base, vals, _combo, games, _meta, idx, _prof = sv
    kept = {}
    for j, i in enumerate(idx):
        if i in chosen or vals[j] <= 0:
            continue
        sg = rows[i]["sg"]
        mine = saved.get(f"{sg['away']}@{sg['home']}")
        card_side = sg["home"] if picks[i] else sg["away"]
        if not mine or norm(mine) == norm(card_side):
            continue
        if norm(mine) not in (norm(sg["home"]), norm(sg["away"])):
            continue
        picks[i] = not bool(picks[i])
        g = games[j]
        p_side = (1 - g["p_fav"]) if not g["my_dog"] else g["p_fav"]   # the flipped side's win chance
        kept[i] = (f"Your pick kept: {mine} wins {p_side * 100:.0f}%, "
                   f"season chance {base * 100:.1f}%→{base * 100 + vals[j]:.1f}%")
    return kept


def group_value(rows, picks, fav_home, p_true, pub_home, y):
    """Season-long value of taking the other side in each open game (pp.yahoo_value), as card notes."""
    sv = season_flips(rows, picks, fav_home, p_true, pub_home)
    if not sv:
        return []
    base, vals, combo, games, meta, _idx, prof = sv
    st = y["standings"]
    out = [f"Chance to win the group this season: {base * 100:.1f}% (you're #{st['rank']}, {st['leader'] - st['me']} back; "
           f"simulated against each member's own pick habits over the last {len(prof['weeks'])} weeks)."]
    order = sorted(range(len(games)), key=lambda i: -vals[i])
    shown = [i for i in order if vals[i] > 0][:5] or order[:3]
    out.append("Value of taking the other side (open games):")
    for i in shown:
        (fav, dog), kick = meta[i]
        g = games[i]
        side, other = (fav, dog) if g["my_dog"] else (dog, fav)
        out.append(f"{side} instead of {other} ({kick}): {vals[i]:+.2f} points of win chance "
                   f"({base * 100:.1f}% → {base * 100 + vals[i]:.1f}%); {side} wins "
                   f"{(g['p_fav'] if g['my_dog'] else 1 - g['p_fav']) * 100:.0f}%, "
                   f"{(1 - g['pub_dog'] if g['my_dog'] else g['pub_dog']) * 100:.0f}% of Yahoo players on {side}")
    if combo > 0:
        n_pos = sum(1 for v in vals if v > 0)
        out.append(f"All {n_pos} switches that help (top {len(shown)} above) together: {base * 100:.1f}% → {base * 100 + combo:.1f}%.")
    else:
        out.append("No other side raises your chance this week: the card's picks are the best for the season.")
    return out


WATCH_MAX_FAV = 0.55   # our stats give the favorite this or less
WATCH_GAP = 0.10       # or our stats sit this far below the betting odds on the favorite


def upset_watch(rows, picks, chosen, pub_home, limit=4):
    """'Upset watch': favorites on the card that our numbers only barely back, so Michael can weigh a
    contrarian pick himself. Betting odds = the win chance implied by sportsbook moneylines, vig removed.
    Games that have kicked off are left out."""
    now = datetime.now(timezone.utc)
    cands = []
    for i, r in enumerate(rows):
        if i in chosen or r["pk"] is None:
            continue
        start = r["g"].get("startDate")
        if start and datetime.fromisoformat(start.replace("Z", "+00:00")) <= now:
            continue
        home_pick = bool(picks[i])
        fav_p = r["pm"] if home_pick else 1 - r["pm"]
        fav_mk = r["pk"] if home_pick else 1 - r["pk"]
        if fav_p > WATCH_MAX_FAV and fav_mk - fav_p < WATCH_GAP:
            continue
        sg = r["sg"]
        fav, dog = (sg["home"], sg["away"]) if home_pick else (sg["away"], sg["home"])
        group_dog = (1 - pub_home[i]) if home_pick else pub_home[i]
        extra = [s for s in r["signals"] if s not in ("stats model", "no market line", "injury news")]
        bits = [f"our stats give {dog} {(1 - fav_p) * 100:.0f}%", f"betting odds {(1 - fav_mk) * 100:.0f}%",
                f"{group_dog * 100:.0f}% of Yahoo players on {dog}"] + extra
        rebuilt = rebuilt_note([(r["g"]["homeTeam"], sg["home"]), (r["g"]["awayTeam"], sg["away"])])
        if rebuilt:
            bits.append(rebuilt)
        news = sorted((a for a in r["S"]["why"] if abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0)) >= 0.3),
                      key=lambda a: -(abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0))))[:2]
        cands.append((fav_p, html.escape(f"{dog} over {fav} ({sg['kick']}): " + "; ".join(bits))
                      + "".join(f"; {html.escape(a['team'] + ': ' + a['reason'])} ({cite(a)})" for a in news)))
    cands.sort(key=lambda t: t[0])
    if not cands:
        return []
    return ["Upset watch (favorites our numbers barely back; your call):"] + [t for _, t in cands[:limit]]


def build_cfp(W, slate):
    c = slate["cfp"]
    if not c.get("games"):
        return {"id": "cfp", "title": "CFP 2026 points pool", "deadline": "Locks Sat 11:00am CT",
                "status": c["status"], "rows": [],
                "notes": [f"Balance {c.get('balance', 0):,} (#{c.get('rank', '?')}); leader {c.get('leader', 0):,}. Must wager 50-100%.",
                          "Rebuy window: a bust before 11am Nov 7 can be reset to 10,000 for $25 (your call)." if c.get("rebuy_deadline") and not c.get("rebuy_used") else ""]}
    return build_cfp_slate(W, slate)


def build_cfp_slate(W, slate):
    c = slate["cfp"]
    cands = []
    for sg in c["games"]:
        g = W.find(sg["away"], sg["home"]); m, S = fair_margins(W, g)
        home_line = sg["home_spread"]
        if norm(sg["home"]) != norm(g["homeTeam"]):
            m = -m
        ph = p_cover(m, home_line)
        sh = ph >= 0.5
        S = {**S, "why": ats_why(S, sg["home"] if sh else sg["away"])}
        cands.append({"sg": sg, "g": g, "S": S, "home": sh, "p": ph if sh else 1 - ph, "mkt": W.lines.get(g["id"]),
                      "line": home_line if sh else -home_line, "mkt_line": market_side_line(W, sg, g, sh)})
    cands.sort(key=lambda x: -x["p"])
    best, table = P.cfp_plan(c["balance"], c["field"], [x["p"] for x in cands],
                             weeks_left=c.get("weeks_left", 6), rebuy_ok=not c.get("rebuy_used") and c.get("rebuy_window", True))
    nb = best["bets"]; stake = int(c["balance"] * best["frac"] / nb)
    rows = []
    for x in cands[:nb]:
        team = x["sg"]["home"] if x["home"] else x["sg"]["away"]
        rows.append({"game": f"{x['sg']['away']} @ {x['sg']['home']}", "pick": f"{team} {x['line']:+g}", "model": x["p"], "market": 0.5,
                     "wager": f"{stake:,}", "why": short(f"{x['S']['why'][0]['team']}: {x['S']['why'][0]['reason']}") if x["S"]["why"] else gap_why(x["line"], x["mkt_line"], x["p"]),
                     "source": src_link(x["g"], x["S"]["why"]), "key": f"{x['sg']['away']}@{x['sg']['home']}", "pick_team": team})
    alt = sorted(table, key=lambda r: -r["p_first"])[1]

    def side(x):
        team = x["sg"]["home"] if x["home"] else x["sg"]["away"]
        why = short(f"{x['S']['why'][0]['team']}: {x['S']['why'][0]['reason']}") if x["S"]["why"] else "next-best edge vs pool line"
        return f"{team} {x['line']:+g} (cover {x['p']*100:.0f}%): {why}"

    # the next-best sides, so a primary pick never hides options worth a look (each has a breakdown below)
    alts = [f"Also worth a look: {side(x)}" for x in cands[nb:nb + 3]]
    if alt["bets"] > 1:
        alts.append(f"Split option: {' + '.join(side(x).split(' (')[0] for x in cands[:alt['bets']])}, "
                    f"{int(c['balance'] * alt['frac'] / alt['bets']):,} each → P(1st) {alt['p_first']*100:.1f}%.")
    return {"id": "cfp", "title": "CFP 2026 points pool", "deadline": "Locks Sat 11:00am CT", "rows": rows,
            "notes": [f"Sizing sim (10k seasons): {nb} bet(s), {best['frac']*100:.0f}% of {c['balance']:,} → P(1st) {best['p_first']*100:.1f}%, P(top 3) {best['p_top3']*100:.1f}%." + (" Assumes $25 rebuy if busted this week." if best["rebuy"] else ""),
                      f"Alternate: {alt['bets']} bet(s) at {alt['frac']*100:.0f}% → P(1st) {alt['p_first']*100:.1f}%."]
                     + alts + ([c["note"]] if c.get("note") else [])}


def build_bto(W, slate):
    b = slate["bto"]
    if not b.get("games"):
        return {"id": "bto", "title": "BTO Beat the Odds", "deadline": "Due Fri 8:00pm CT (games lock at kickoff)",
                "status": b["status"], "rows": [],
                "notes": [f"Balance ${b.get('balance', 0):,} ({b.get('balance_note', '')}), #{b.get('rank', '?')} of {b.get('players', 49)}; mode {b.get('mode', '?')}" + (": exactly 3 bets incl. Big Game, 50%+ of balance, 4 line points." if b.get("mode") in ("Three Bet", "three") else "."),
                          f"Playoff line (12th) ${b.get('twelfth', 0):,}; leader ${b.get('leader', 0):,}."]}
    return build_bto_slate(W, slate)


def build_bto_slate(W, slate):
    from .nfl import nfl_sim
    b = slate["bto"]
    cands = []
    for sg in b["games"]:
        if sg.get("locked"):
            continue
        if sg["league"] == "CFB":
            g = W.find(sg["away"], sg["home"]); m, S = fair_margins(W, g)
            if norm(sg["home"]) != norm(g["homeTeam"]):
                m = -m
        else:
            g = None
            m, src, why = nfl_sim(sg, W.rng)
            if why and why[0].get("source"):
                src = why[0]["source"]  # link the article behind the row's reason, not the scoreboard
        for side_home in (True, False):
            line = sg["home_spread"] if side_home else -sg["home_spread"]
            mm = m if side_home else -m
            if sg["league"] == "CFB":
                why = ats_why(S, sg["home"] if side_home else sg["away"]); src = src_link(g, why)
            cands.append({"sg": sg, "home": side_home, "margin": mm, "line": line, "p": p_cover(mm, line), "src": src, "why": why,
                          "mkt_line": market_side_line(W, sg, g, side_home)})
    if b["mode"] == "one":
        # One Bet: exactly 1 game, Big Game not required, all 4 line points on it. Rank each side by its
        # cover chance after the line points (Nov 11: the old loop always seeded the Big Game and only
        # checked the count after adding a second game, so it put all 16 games on the card).
        ranked = sorted(((P.allocate_line_points([c["margin"]], [c["line"]])[1][0], i) for i, c in enumerate(cands)), reverse=True)
        pick = [cands[ranked[0][1]]]
        alts, seen = [], {id(pick[0]["sg"])}
        for p1, i in ranked[1:]:
            c = cands[i]
            if id(c["sg"]) in seen:
                continue
            seen.add(id(c["sg"]))
            team = c["sg"]["home"] if c["home"] else c["sg"]["away"]
            alts.append(f"Also worth a look: {team} {c['line']+4:+g} (LP 4), cover {p1*100:.0f}%")
            if len(alts) == 2:
                break
    else:
        alts = []
        big = max((c for c in cands if c["sg"].get("big")), key=lambda c: c["p"])
        others = sorted((c for c in cands if not c["sg"].get("big") and c["sg"] is not big["sg"]), key=lambda c: -c["p"])
        seen, pick = set(), [big]
        for c in others:
            k = id(c["sg"])
            if k not in seen:
                seen.add(k); pick.append(c)
            if len(pick) == {"three": 3}.get(b["mode"], 4):
                break
    lp, probs = P.allocate_line_points([c["margin"] for c in pick], [c["line"] for c in pick])
    best, table = P.bto_plan(b["balance"], b["field"], probs, b["mode"], b.get("weeks_left", 6))
    rows = []
    for c, l, p, s in zip(pick, lp, probs, best["stakes"]):
        team = c["sg"]["home"] if c["home"] else c["sg"]["away"]
        rows.append({"game": f"{c['sg']['away']} @ {c['sg']['home']}" + (" ★" if c["sg"].get("big") else ""),
                     "pick": f"{team} {c['line']+l:+g}" + (f" (LP {l:g})" if l else ""), "model": p, "market": 0.5,
                     "wager": f"${s:,}", "why": (short(f"{c['why'][0]['team']}: {c['why'][0]['reason']}") if "team" in c["why"][0] else short(c["why"][0]["reason"]))
                     if c["why"] else gap_why(c["line"], c["mkt_line"], p, l),
                     "source": c["src"], "key": f"{c['sg']['away']}@{c['sg']['home']}", "pick_team": team})
    return {"id": "bto", "title": "BTO Beat the Odds", "deadline": "Due Fri 8:00pm CT (games lock at kickoff)", "rows": rows,
            "notes": [f"Sizing sim: {best['frac']*100:.0f}% of ${b['balance']:,}, {best['split']} split → P(top 12) {best['p_top12']*100:.0f}%, P(top 4) {best['p_top4']*100:.0f}%."] + alts}


def build_survivor():
    return {"id": "survivor", "title": "Guhy NFL survivor", "deadline": "", "status": "Eliminated in Week 7 (NYJ). No picks needed.", "rows": []}


def mark_changes(card, stage, week):
    """Flag picks that changed since the last posted card (Sat refresh), and save what was posted
    (team, pick text with line, wager) for the Tuesday postmortem."""
    pub = ROOT / f"data/published/{YEAR}-w{week:02d}-{card['id']}.json"
    prev = json.loads(pub.read_text()) if pub.exists() else {}
    for r in card["rows"]:
        old = prev.get(r["key"])
        old = old.get("team") if isinstance(old, dict) else old
        r["changed"] = bool(stage == "refresh" and old and old != r["pick_team"])
        if r["changed"]:
            r["was"] = old
        elif stage == "refresh" and prev and r["key"] not in prev:
            # the pick moved to a game the last card didn't play (ATS pools re-rank on fresh lines)
            dropped = [v.get("pick", k) if isinstance(v, dict) else v for k, v in prev.items()
                       if k not in {x["key"] for x in card["rows"]}]
            r["changed"], r["was"] = True, ("not on last card; dropped " + ", ".join(dropped)) if dropped else "not on last card"
    card["rows"].sort(key=lambda r: not r["changed"])
    if card["rows"]:
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(json.dumps({r["key"]: {"team": r["pick_team"], "pick": r["pick"], "wager": r["wager"],
                                              "game": r["game"], "stage": stage} for r in card["rows"]}, indent=1))


# Live stale-line gaps: pp.lines writes docs/data/pick_lines.json every 2h Wed-Sat (run.yml), so the
# page reads it in the browser instead of waiting for the next card build.
GAPS_HTML = """<section id="gaps" hidden><h2>Pool lines vs market now</h2><p class="meta" id="gaps-up"></p>
<table class="gt"><thead><tr><th>Pool</th><th>Pool line (value side)</th><th>Market</th><th>Gap</th></tr></thead><tbody id="gaps-rows"></tbody></table>
<p class="meta">Bold = 1.5+ points or a key number gained (push sent once per game). Edges only; picks above already price them.</p></section>
<script>
fetch("../data/pick_lines.json?t=" + Date.now()).then(r => r.json()).then(d => {
  const rows = (d.rows || []).filter(r => r.gap > 0);
  if (!rows.length) return;
  const f = x => x ? (x > 0 ? "+" : "") + x : "PK";
  const tb = document.getElementById("gaps-rows");
  for (const r of rows) {
    const tr = tb.insertRow(); if (r.flag) tr.className = "flag";
    const keys = r.keys.length ? " (gains " + r.keys.join("/") + ")" : "";
    [r.pool.toUpperCase(), r.side + " " + f(r.pool_line), f(r.market_line) + " " + r.book, r.gap + keys]
      .forEach(t => { tr.insertCell().textContent = t; });
  }
  const up = new Date(d.updated), old = (Date.now() - up) / 36e5 > 3;
  document.getElementById("gaps-up").textContent = "Checked " + up.toLocaleString([], {weekday: "short", hour: "numeric", minute: "2-digit"})
    + (old ? " (over 3h ago)" : "") + " · open games only";
  document.getElementById("gaps").hidden = false;
}).catch(() => {});
</script>"""


# Per-game breakdowns (pp.explain): each lives once in a <template>; tapping a row clones it into the hidden
# row under it, so a game on three cards and in All games doesn't ship its panel four times.
BD_JS = """<script>
function bdToggle(tr) {
  const row = tr.nextElementSibling, td = row.firstElementChild;
  if (!td.hasChildNodes()) { const t = document.getElementById(tr.dataset.bd); if (t) td.appendChild(t.content.cloneNode(true)); }
  row.hidden = !row.hidden; tr.classList.toggle("open", !row.hidden); tr.setAttribute("aria-expanded", !row.hidden);
}
document.addEventListener("click", e => { const tr = e.target.closest("tr[data-bd]"); if (tr && !e.target.closest("a")) bdToggle(tr); });
document.addEventListener("keydown", e => { const tr = e.target.closest && e.target.closest("tr[data-bd]");
  if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); bdToggle(tr); } });
</script>"""


def bd_attrs(bd, cls=""):
    """Row attributes that make a table row open its breakdown."""
    if not bd:
        return f' class="{cls}"' if cls else ""
    return f' class="{" ".join(filter(None, ("x", cls)))}" data-bd="{html.escape(bd)}" tabindex="0" aria-expanded="false"'


def all_games_html(games):
    if not games:
        return ""
    tag = {"yahoo": "Y", "bto": "B", "cfp": "C"}
    rows = []
    for g in games:
        pools = " ".join(f"<b class='g'>{tag[p]}</b>" if picked else tag[p] for p, picked in g["pools"])
        day, _, tm = explain.kick_ct(g["kick"]).partition(", ")
        rows.append(f"<tr{bd_attrs(g['id'])}><td>{html.escape(tm)}<br><span class='mk'>{html.escape(day)}</span></td>"
                    f"<td><span class='tg'>&#9656;</span> {html.escape(g['label'])}</td><td>{html.escape(g['market'])}</td><td>{pools}</td></tr>"
                    f"<tr class='bdr' hidden><td colspan='4'></td></tr>")
    return ("<section id='allg'><h2>All pool games</h2><p class='meta'>Tap any game (here or on a card) for what the model saw: lines, "
            "model vs market, stats matchup with strengths and weaknesses, injuries and news, weather, pool context.</p>"
            "<table class='ag'><thead><tr><th>Kick (CT)</th><th>Game</th><th>Market</th><th>Pools</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table><p class='meta'>Y Yahoo, B BTO, C CFP; green = on that card.</p></section>")


def checks_html(meta):
    """Top of the page: saved-pick CHANGE / decision Differs lines (same as the push), then the second opinion."""
    al = "".join(f"<li>{html.escape(a)}</li>" for a in meta.get("alerts") or [])
    ck = meta.get("checked")
    if ck and ck.get("stage") == meta.get("stage"):
        fails = f" Automatic checks failed: {html.escape('; '.join(ck['auto_fails']))}." if ck.get("auto_fails") else ""
        line = (f"<p class='meta ck'>{html.escape(ck['text'])} (second opinion, {html.escape(ck['at'])}; "
                f"{ck['auto_passed']}/{ck['auto_total']} automatic checks passed).{fails}</p>")
    else:
        line = "<p class='meta ck'>Second-opinion check: pending for this build.</p>"
    return (f"<ul class='alerts'>{al}</ul>" if al else "") + line


def alerts_for(cards, slate, stage):
    try:
        return push_compose(cards, slate, final_call=stage != "draft")[0]
    except Exception as ex:  # the page and push must still go out
        print("saved-pick compare skipped:", repr(ex))
        return []


NEXT_DRAFT = "Wednesday 9pm CT"  # RUNBOOK: drafts Wed 9pm (picks-backup.yml covers a missed slot at 9:45pm)


def card_over(meta):
    """When a card's week is over: midnight CT starting the first Tuesday after it was built. Cards are built
    Wed-Sat for games through Monday night; the Tuesday 8pm postmortem grades them and the next draft is Wednesday."""
    try:
        made = datetime.fromisoformat(meta["generated_iso"]).astimezone(CT)
    except (KeyError, TypeError, ValueError):
        return None
    day = (made + timedelta(days=(1 - made.weekday()) % 7 or 7)).date()     # weekday(): Tuesday = 1
    return datetime(day.year, day.month, day.day, tzinfo=CT)


def old_card_html(meta):
    """A banner, hidden until the card's week is over (checked in the browser, since the page stays up from Saturday's
    refresh to Wednesday's draft): says it's last week's card and when the new drafts come, hides the "next lock ..."
    lines (all passed) and greys the stage chip (#666 under white text: 5.7:1 in light and dark mode; the old --mut grey
    was 2.85:1 in dark mode). Self-contained (own style and script)."""
    over = card_over(meta)
    if not over:
        return ""
    week = html.escape((meta.get("week_label") or "").split(" (")[0])
    return ("<style>.old{margin:8px 0;padding:10px 12px;border-radius:8px;font-size:13px;line-height:1.4;background:#fff4d6;"
            "color:#4a3200;border:1px solid #e0b44c}@media (prefers-color-scheme:dark){.old{background:#2e2610;color:#ffdc8a;"
            "border-color:#7a6224}}body.oldcard .stage{background:#666;color:#fff}body.oldcard .dl{display:none}</style>"
            f"<p id='oldcard' class='old' data-over='{over.isoformat()}' hidden><b>Last week's card.</b> "
            f"{week + ': t' if week else 'T'}hese games are over and every lock on this page has passed. "
            f"New drafts post {NEXT_DRAFT}.</p>"
            "<script>(function(){var b=document.getElementById('oldcard');"
            "if(b&&Date.now()>=Date.parse(b.getAttribute('data-over'))){b.hidden=false;document.body.classList.add('oldcard');}})();</script>")


def render(cards, meta, games=()):
    def pct(x):
        return "—" if x is None else f"{x*100:.0f}"
    body = []
    for c in cards:
        rows = []
        for r in c["rows"]:
            cls = "chg" if r.get("changed") else ""
            was = f'<br><span class="was">was {html.escape(r["was"])}</span>' if r.get("changed") else ""
            tg = "<span class='tg'>&#9656;</span> " if r.get("bd") else ""
            rows.append(f"<tr{bd_attrs(r.get('bd'), cls)}><td>{tg}{html.escape(r['game'])}</td><td><b>{html.escape(r['pick'])}</b>{was}</td>"
                        f"<td>{pct(r['model'])}<span class='mk'>/{pct(r['market'])}</span></td><td>{html.escape(r['wager'])}</td>"
                        f"<td>{html.escape(r['why'])}</td><td><a href=\"{html.escape(r['source'])}\">link</a></td></tr>"
                        + ("<tr class='bdr' hidden><td colspan='6'></td></tr>" if r.get("bd") else ""))
        table = ("<table><thead><tr><th>Game</th><th>Pick</th><th>Win %<br><span class='mk'>model/mkt</span></th><th>Wager / score</th><th>Why</th><th>Src</th></tr></thead><tbody>"
                 + "".join(rows) + "</tbody></table>") if rows else ""
        extra = "".join(f"<li>{t}</li>" for t in c.get("tiebreakers", []) + c.get("notes", []))
        status = f"<p class='st'>{html.escape(c['status'])}</p>" if c.get("status") else ""
        body.append(f"<section><h2>{html.escape(c['title'])}</h2><p class='dl'>{html.escape(c.get('deadline',''))}</p>{status}{table}"
                    + (f"<ul>{extra}</ul>" if extra else "") + "</section>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pool Picks</title><style>
:root{{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd;--acc:#0b5;--red:#c00;--chg:#fde8e8;--bd:#f4f6f5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mut:#999;--line:#333;--acc:#3d8;--red:#f66;--chg:#3a1414;--bd:#1b1e1d}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:12px 8px 40px;background:var(--bg);color:var(--fg);font:13px/1.35 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}}
h1{{font-size:18px;margin:0 0 2px}}h2{{font-size:15px;margin:18px 0 2px}}.meta,.dl,.mk,.was{{color:var(--mut);font-size:11px}}
.st{{margin:4px 0;font-weight:600}}table{{width:100%;table-layout:fixed;border-collapse:collapse;font-size:11.5px}}
th,td{{border-bottom:1px solid var(--line);padding:4px 2px;vertical-align:top;word-wrap:break-word;overflow-wrap:anywhere;text-align:left}}
th{{font-size:10.5px;color:var(--mut)}}th:nth-child(1){{width:23%}}th:nth-child(2){{width:19%}}th:nth-child(3){{width:12%}}th:nth-child(4){{width:13%}}th:nth-child(5){{width:25%}}th:nth-child(6){{width:8%}}
tr.chg td{{background:var(--chg);color:var(--red)}}a{{color:var(--acc)}}ul{{padding-left:16px;margin:6px 0}}li{{margin:2px 0}}
.stage{{display:inline-block;padding:1px 6px;border-radius:4px;background:var(--acc);color:#fff;font-size:11px;font-weight:700}}
table.gt th{{width:auto}}table.gt th:nth-child(1){{width:14%}}table.gt th:nth-child(4){{width:16%}}tr.flag td{{font-weight:700;color:var(--acc)}}
tr.x{{cursor:pointer}}.tg{{display:inline-block;color:var(--acc);transition:transform .15s}}tr.open .tg{{transform:rotate(90deg)}}
tr.bdr>td{{padding:0 0 8px;background:var(--bd)}}.bd{{padding:4px 6px;font-size:12px;line-height:1.4}}.bd p{{margin:4px 0}}.bd ul{{margin:2px 0}}
.bd h4{{font-size:11px;margin:10px 0 2px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}}.bl{{font-weight:600}}
table.mt th,table.ag th{{width:auto}}table.mt th:nth-child(1){{width:36%}}table.mt td{{padding:2px}}tr.sh td{{font-weight:700;color:var(--mut);padding-top:6px}}
table.ag th:nth-child(1){{width:21%}}table.ag th:nth-child(2){{width:39%}}table.ag th:nth-child(4){{width:15%}}.g{{color:var(--acc)}}.r{{color:var(--red)}}
ul.alerts{{color:var(--red);font-weight:600;margin:8px 0}}.ck{{margin:2px 0 6px}}
</style></head><body><p class="meta"><a href="../">&larr; Sports HQ</a></p><h1>Pool Picks <span class="stage">{html.escape(meta['stage_label'])}</span></h1>
<p class="meta">{html.escape(meta['week_label'])} · updated {html.escape(meta['generated'])}{(' · breakdowns ' + html.escape(meta['breakdowns'])) if meta.get('breakdowns') else ''}</p>
{old_card_html(meta)}
{checks_html(meta)}
{''.join(body)}
{GAPS_HTML}
<script src="changes.js" defer></script>
{all_games_html(games)}
<section><h2>Model check</h2><ul>{''.join(f'<li>{t}</li>' for t in meta['calibration'])}</ul>
<p class="meta">Win % = stats-only model / market implied. Method: <a href="method/pool-method.html">pool method</a> · <a href="method/pool-rules.html">pool rules</a> · <a href="history.html">history</a></p></section>
{''.join(f'<template id="{html.escape(g["id"])}">{g["html"]}</template>' for g in games)}
{BD_JS if games else ''}
</body></html>"""


def add_breakdowns(W, slate, cards, meta):
    """Per-game 'what the model saw' panels (pp.explain). Presentation only: never blocks the cards."""
    try:
        games, index = explain.build(W, slate, cards)
    except Exception as ex:
        print("breakdowns skipped:", repr(ex))
        return []
    for c in cards:
        for r in c["rows"]:
            r["bd"] = index.get((c["id"], r["key"]))
    meta["breakdowns"] = datetime.now(CT).strftime("%a %I:%M %p CT")
    return games


def write(cards, meta, games):
    (ROOT / "data").mkdir(exist_ok=True)
    # game_stats: {breakdown id (a card row's "bd"): per-game stats dict from pp.explain (nflverse for NFL, CFBD for CFB)}
    stats = {g["id"]: g["stats"] for g in games if g.get("stats")}
    (ROOT / "data/cards.json").write_text(json.dumps({"meta": meta, "cards": cards, "game_stats": stats}, indent=1, default=str))
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(render(cards, meta, games), encoding="utf-8")
    try:  # the week's card history (docs/picks/changes.json, pp.history); never blocks a card
        from . import history
        history.write()
    except Exception as ex:
        print("card history skipped:", repr(ex))


def rerender(week=None):
    """Rebuild the breakdowns and the page around the posted cards (picks, wagers and stage unchanged)."""
    d = json.loads((ROOT / "data/cards.json").read_text(encoding="utf-8"))
    cards, meta = d["cards"], d["meta"]
    week = week or meta.get("week") or current_week()
    W = Week(week)
    slate = load_slate(week)
    meta["alerts"] = alerts_for(cards, slate, meta.get("stage"))
    games = add_breakdowns(W, slate, cards, meta)
    write(cards, meta, games)
    print(json.dumps({"rerendered": week, "breakdowns": len(games)}))


def degraded_notes():
    """Model-check lines when CFBD couldn't be called this build (Q-055): where the lines came from, and one line
    for team stats served from saved copies."""
    out = list(MARKET_NOTE)
    other = [(ep, why) for ep, why, _ in HTTP_STALE if ep != "/lines"]
    if other:
        out.append(f"CFBD unavailable at build ({other[0][1]}); team stats from saved copies "
                   f"({', '.join(sorted({ep for ep, _ in other}))}).")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="draft", choices=["draft", "final", "refresh"])
    ap.add_argument("--week", type=int)
    ap.add_argument("--pools", default="yahoo,bto,cfp,survivor")
    ap.add_argument("--render-only", action="store_true", help="refresh breakdowns around data/cards.json; picks unchanged")
    a = ap.parse_args()
    if a.render_only:
        return rerender(a.week)
    week = a.week or current_week()
    slate = load_slate(week)
    W = Week(week)
    builders = {"yahoo": lambda: build_yahoo(W, slate), "bto": lambda: build_bto(W, slate),
                "cfp": lambda: build_cfp(W, slate), "survivor": build_survivor}
    cards = [builders[p]() for p in a.pools.split(",")]
    for c in cards:
        mark_changes(c, a.stage, week)
    cards.sort(key=lambda c: not any(r.get("changed") for r in c["rows"]))
    bt = json.loads((ROOT / "backtest/2026_w1-8.json").read_text())["report"]
    cal = {c["bin"]: c for c in bt["calibration"]}
    calib = [f"Backtest 2026 wks 1-8 ({bt['n']} games): picks rated 60-70% hit {cal['60-70%']['hit']*100:.0f}%, 70-80% hit {cal['70-80%']['hit']*100:.0f}%, 80-90% hit {cal['80-90%']['hit']*100:.0f}%, 90%+ hit {cal['90-100%']['hit']*100:.0f}%.",
             f"Straight-up: model {bt['su_accuracy']['model']*100:.0f}% vs market {bt['su_accuracy']['market']*100:.0f}%; model trails early weeks, near market by wks 6-8."]
    srcs = sorted({W.lines[g["id"]]["src"] for g in W.games if (W.lines.get(g["id"]) or {}).get("src")})
    calib.append(f"Market lines: {srcs[-1]} for {sum(1 for g in W.games if (W.lines.get(g['id']) or {}).get('src'))} games; CFBD consensus for the rest."
                 if srcs else "Market lines: CFBD consensus (ESPN odds unavailable at build).")
    calib += degraded_notes()
    stage_label = {"draft": "DRAFT", "final": "FINAL", "refresh": "SAT REFRESH"}[a.stage]
    if os.environ.get("BACKUP"):
        stage_label += " - BACKUP (no fresh research)"
    meta = {"stage": a.stage, "stage_label": stage_label, "week_label": slate["label"], "week": week,
            "generated": datetime.now(CT).strftime("%a %b %d, %I:%M %p CT"),
            "generated_iso": datetime.now(timezone.utc).isoformat(), "calibration": calib,
            "alerts": alerts_for(cards, slate, a.stage)}
    write(cards, meta, add_breakdowns(W, slate, cards, meta))
    changed = [f"{c['title']}: {r['pick']}" for c in cards for r in c["rows"] if r.get("changed")]
    print(json.dumps({"stage": stage_label, "week": week, "changed": changed}))


if __name__ == "__main__":
    main()
