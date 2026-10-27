"""Build the weekly pick cards (data/cards.json + docs/index.html).

Usage: py -m pp.cards --stage draft|final|refresh [--pools yahoo,bto,cfp]
Inputs: slates/<year>-wNN.json (read from the pool sites), research/<year>-wNN-*.json (fresh
research with sources), CFBD cache, Open-Meteo. Market lines are shown for comparison and
used only after the stats model is built (blend for outcome sims, never as a model input).
"""
import argparse, glob, html, json, os, re, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from . import model as M
from .market import lines
from .sim import sim_game, exact_score_pick, p_cover
from .weather import kickoff_weather, total_adjustment
from . import pools as P

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT.parent / "docs" / "picks"  # served by Sports HQ's GitHub Pages at /picks/
YEAR = 2026
CT = timezone(timedelta(hours=-5))  # CDT through Nov 1; cards show "CT"
ALIASES = {"miami (fl)": "miami", "n. carolina": "north carolina", "sdsu": "san diego state",
           "connecticut": "uconn", "boston coll.": "boston college", "byu": "byu", "ole miss": "ole miss"}


def norm(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    n = ALIASES.get(n, n)
    n = re.sub(r"\bst\.$", "state", n)
    return n.replace(".", "")


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
    adj, notes = {}, []
    for f in sorted(glob.glob(str(ROOT / f"research/{YEAR}-w{week:02d}-*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for a in d.get("adjustments", []):
            adj.setdefault(norm(a["team"]), []).append(a)
        notes += d.get("notes", [])
    return adj, notes


class Week:
    def __init__(self, week):
        self.week = week
        self.games = [g for g in M.games(YEAR) if g["week"] == week]
        self.by_pair = {(norm(g["awayTeam"]), norm(g["homeTeam"])): g for g in self.games}
        self.lines = lines(YEAR, week, max_age_h=6)
        self.research, self.notes = load_research(week)
        self.rng = np.random.default_rng(2026 * 100 + week)
        self._sims = {}

    def find(self, away, home):
        a, h = norm(away), norm(home)
        return self.by_pair.get((a, h)) or self.by_pair.get((h, a))

    def team_adj(self, g):
        adj = {g["homeTeam"]: 0.0, g["awayTeam"]: 0.0}
        why = []
        for t, o in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"])):
            for a in self.research.get(norm(t), []):
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
    adj, _, _ = W.team_adj(g)
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


def research_why(S, g):
    """Most material research item for the game, prefixed with the team it concerns."""
    items = [a for a in S["why"] if abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0)) >= 1]
    if not items:
        return None, None
    a = max(items, key=lambda a: abs(a.get("off_pts", 0)) + abs(a.get("def_pts", 0)))
    return short(f"{a['team']}: {a['reason']}"), a["source"]


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
    s["label"] = f"CFBD week {week} (Yahoo week {week + 1})"
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
        rwhy, rsrc = research_why(S, g)
        if is_dog:
            why = short(f"Upset: {', '.join(r['signals'])}; group on favorite")
        elif rwhy:
            why = rwhy
        elif S["wx"] and total_adjustment(S["wx"]) <= -2:
            why = short(f"Stats {pm*100:.0f}% win; wind {S['wx']['wind']:.0f} mph lowers scoring")
        else:
            gap = (pm - (pk or pm)) * 100
            if abs(gap) < 8:
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
    return {
        "id": "yahoo", "title": "Yahoo pick'em (Kosmos, 14)", "deadline": "Each game locks at kickoff; first Fri 6:30pm CT",
        "rows": out,
        "tiebreakers": [
            *[f"TB1 {k}: <b>{v['pick']}</b> (alt {v['alt']})" for k, v in tb1.items()],
            f"TB2 most points: <b>{most[0][0]}</b> ({most[0][1]*100:.0f}%), alt {most[1][0]} ({most[1][1]*100:.0f}%)",
            f"TB2 fewest points: <b>{fewest[0][0]}</b> ({fewest[0][1]*100:.0f}%), alt {fewest[1][0]} ({fewest[1][1]*100:.0f}%)",
            f"TB2 locks {y['tb2_deadline']}",
        ],
        "notes": [f"Underdogs: {n_dogs}. Pool sim (10k): P(win week) {max(curve)*100:.1f}% vs {curve[0]*100:.1f}% all favorites; {len(eligible)} dogs passed the 4-pt / 2-signal rule.",
                  f"Group: you {y['standings']['me']} pts, rank {y['standings']['rank']}, leader {y['standings']['leader']}."],
    }


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
        cands.append({"sg": sg, "g": g, "S": S, "home": sh, "p": ph if sh else 1 - ph, "mkt": W.lines.get(g["id"]),
                      "line": home_line if sh else -home_line})
    cands.sort(key=lambda x: -x["p"])
    best, table = P.cfp_plan(c["balance"], c["field"], [x["p"] for x in cands],
                             weeks_left=c.get("weeks_left", 6), rebuy_ok=not c.get("rebuy_used") and c.get("rebuy_window", True))
    nb = best["bets"]; stake = int(c["balance"] * best["frac"] / nb)
    rows = []
    for x in cands[:nb]:
        team = x["sg"]["home"] if x["home"] else x["sg"]["away"]
        rows.append({"game": f"{x['sg']['away']} @ {x['sg']['home']}", "pick": f"{team} {x['line']:+g}", "model": x["p"], "market": 0.5,
                     "wager": f"{stake:,}", "why": short(x["S"]["why"][0]["reason"]) if x["S"]["why"] else short(f"Cover {x['p']*100:.0f}% vs pool line at current market; top edge"),
                     "source": src_link(x["g"], x["S"]["why"]), "key": f"{x['sg']['away']}@{x['sg']['home']}", "pick_team": team})
    alt = sorted(table, key=lambda r: -r["p_first"])[1]
    return {"id": "cfp", "title": "CFP 2026 points pool", "deadline": "Locks Sat 11:00am CT", "rows": rows,
            "notes": [f"Sizing sim (10k seasons): {nb} bet(s), {best['frac']*100:.0f}% of {c['balance']:,} → P(1st) {best['p_first']*100:.1f}%, P(top 3) {best['p_top3']*100:.1f}%." + (" Assumes $25 rebuy if busted this week." if best["rebuy"] else ""),
                      f"Alternate: {alt['bets']} bet(s) at {alt['frac']*100:.0f}% → P(1st) {alt['p_first']*100:.1f}%."]}


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
            g = W.find(sg["away"], sg["home"]); m, S = fair_margins(W, g); src = src_link(g, S["why"]); why = S["why"]
            if norm(sg["home"]) != norm(g["homeTeam"]):
                m = -m
        else:
            m, src, why = nfl_sim(sg, W.rng)
        for side_home in (True, False):
            line = sg["home_spread"] if side_home else -sg["home_spread"]
            mm = m if side_home else -m
            cands.append({"sg": sg, "home": side_home, "margin": mm, "line": line, "p": p_cover(mm, line), "src": src, "why": why})
    big = max((c for c in cands if c["sg"].get("big")), key=lambda c: c["p"])
    others = sorted((c for c in cands if not c["sg"].get("big") and c["sg"] is not big["sg"]), key=lambda c: -c["p"])
    seen, pick = set(), [big]
    for c in others:
        k = id(c["sg"])
        if k not in seen:
            seen.add(k); pick.append(c)
        if len(pick) == {"three": 3, "one": 1}.get(b["mode"], 4):
            break
    lp, probs = P.allocate_line_points([c["margin"] for c in pick], [c["line"] for c in pick])
    best, table = P.bto_plan(b["balance"], b["field"], probs, b["mode"], b.get("weeks_left", 6))
    rows = []
    for c, l, p, s in zip(pick, lp, probs, best["stakes"]):
        team = c["sg"]["home"] if c["home"] else c["sg"]["away"]
        rows.append({"game": f"{c['sg']['away']} @ {c['sg']['home']}" + (" ★" if c["sg"].get("big") else ""),
                     "pick": f"{team} {c['line']+l:+g}" + (f" (LP {l:g})" if l else ""), "model": p, "market": 0.5,
                     "wager": f"${s:,}", "why": short(c["why"][0]["reason"]) if c["why"] else short(f"Cover {p*100:.0f}% after line points; strongest edge"),
                     "source": c["src"], "key": f"{c['sg']['away']}@{c['sg']['home']}", "pick_team": team})
    return {"id": "bto", "title": "BTO Beat the Odds", "deadline": "Due Fri 8:00pm CT (games lock at kickoff)", "rows": rows,
            "notes": [f"Sizing sim: {best['frac']*100:.0f}% of ${b['balance']:,}, {best['split']} split → P(top 12) {best['p_top12']*100:.0f}%, P(top 4) {best['p_top4']*100:.0f}%."]}


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
    card["rows"].sort(key=lambda r: not r["changed"])
    if card["rows"]:
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(json.dumps({r["key"]: {"team": r["pick_team"], "pick": r["pick"], "wager": r["wager"],
                                              "game": r["game"], "stage": stage} for r in card["rows"]}, indent=1))


def render(cards, meta):
    def pct(x):
        return "—" if x is None else f"{x*100:.0f}"
    body = []
    for c in cards:
        rows = []
        for r in c["rows"]:
            cls = ' class="chg"' if r.get("changed") else ""
            was = f'<br><span class="was">was {html.escape(r["was"])}</span>' if r.get("changed") else ""
            rows.append(f"<tr{cls}><td>{html.escape(r['game'])}</td><td><b>{html.escape(r['pick'])}</b>{was}</td>"
                        f"<td>{pct(r['model'])}<span class='mk'>/{pct(r['market'])}</span></td><td>{html.escape(r['wager'])}</td>"
                        f"<td>{html.escape(r['why'])}</td><td><a href=\"{html.escape(r['source'])}\">link</a></td></tr>")
        table = ("<table><thead><tr><th>Game</th><th>Pick</th><th>Win %<br><span class='mk'>model/mkt</span></th><th>Wager / score</th><th>Why</th><th>Src</th></tr></thead><tbody>"
                 + "".join(rows) + "</tbody></table>") if rows else ""
        extra = "".join(f"<li>{t}</li>" for t in c.get("tiebreakers", []) + c.get("notes", []))
        status = f"<p class='st'>{html.escape(c['status'])}</p>" if c.get("status") else ""
        body.append(f"<section><h2>{html.escape(c['title'])}</h2><p class='dl'>{html.escape(c.get('deadline',''))}</p>{status}{table}"
                    + (f"<ul>{extra}</ul>" if extra else "") + "</section>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pool Picks</title><style>
:root{{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd;--acc:#0b5;--red:#c00;--chg:#fde8e8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mut:#999;--line:#333;--acc:#3d8;--red:#f66;--chg:#3a1414}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:12px 8px 40px;background:var(--bg);color:var(--fg);font:13px/1.35 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}}
h1{{font-size:18px;margin:0 0 2px}}h2{{font-size:15px;margin:18px 0 2px}}.meta,.dl,.mk,.was{{color:var(--mut);font-size:11px}}
.st{{margin:4px 0;font-weight:600}}table{{width:100%;table-layout:fixed;border-collapse:collapse;font-size:11.5px}}
th,td{{border-bottom:1px solid var(--line);padding:4px 2px;vertical-align:top;word-wrap:break-word;overflow-wrap:anywhere;text-align:left}}
th{{font-size:10.5px;color:var(--mut)}}th:nth-child(1){{width:23%}}th:nth-child(2){{width:19%}}th:nth-child(3){{width:12%}}th:nth-child(4){{width:13%}}th:nth-child(5){{width:25%}}th:nth-child(6){{width:8%}}
tr.chg td{{background:var(--chg);color:var(--red)}}a{{color:var(--acc)}}ul{{padding-left:16px;margin:6px 0}}li{{margin:2px 0}}
.stage{{display:inline-block;padding:1px 6px;border-radius:4px;background:var(--acc);color:#fff;font-size:11px;font-weight:700}}
</style></head><body><p class="meta"><a href="../">&larr; Sports HQ</a></p><h1>Pool Picks <span class="stage">{html.escape(meta['stage_label'])}</span></h1>
<p class="meta">{html.escape(meta['week_label'])} · updated {html.escape(meta['generated'])}</p>
{''.join(body)}
<section><h2>Model check</h2><ul>{''.join(f'<li>{t}</li>' for t in meta['calibration'])}</ul>
<p class="meta">Win % = stats-only model / market implied. Method: <a href="method/pool-method.html">pool method</a> · <a href="method/pool-rules.html">pool rules</a> · <a href="history.html">history</a></p></section>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="draft", choices=["draft", "final", "refresh"])
    ap.add_argument("--week", type=int)
    ap.add_argument("--pools", default="yahoo,bto,cfp,survivor")
    a = ap.parse_args()
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
    stage_label = {"draft": "DRAFT", "final": "FINAL", "refresh": "SAT REFRESH"}[a.stage]
    if os.environ.get("BACKUP"):
        stage_label += " - BACKUP (no fresh research)"
    meta = {"stage": a.stage, "stage_label": stage_label, "week_label": slate["label"],
            "generated": datetime.now(CT).strftime("%a %b %d, %I:%M %p CT"),
            "generated_iso": datetime.now(timezone.utc).isoformat(), "calibration": calib}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data/cards.json").write_text(json.dumps({"meta": meta, "cards": cards}, indent=1, default=str))
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(render(cards, meta), encoding="utf-8")
    changed = [f"{c['title']}: {r['pick']}" for c in cards for r in c["rows"] if r.get("changed")]
    print(json.dumps({"stage": stage_label, "week": week, "changed": changed}))


if __name__ == "__main__":
    main()
