"""The week's story for the Picks page: every posted card version side by side, and line movement per game.

Two committed files, both read by docs/picks/changes.js in the browser:
- docs/picks/changes.json: every version of data/cards.json in git (draft, redrafts, finals, refresh, backup cards),
  plus the working-tree card when it isn't committed yet; per pool the pick, line, win/cover %, wager and what changed
  from the version before. Rebuilt by pp.cards each time it writes a card (so pp.publish commits it with the card).
  A shallow checkout (the cloud backup run) adds its card to the newest week's versions kept in
  data/card_versions.json and carries older weeks from the current changes.json.
- docs/data/pick_line_history/<season>-wNN.json: the market spread (and each pool's line) per game, one point each
  time it changes. Appended by pp.lines on every stale-line scan (run.yml, Wed-Sat every 2h, every 30 min before CFP's
  Saturday lock); one JSON line so a merge conflict keeps one side whole. `py -m pp.history --backfill-lines` seeds it
  from the git history of docs/data/pick_lines.json.

Stdlib only: pp.lines imports this inside the cloud loop (requests only, no numpy).
Usage: py -m pp.history [--backfill-lines]
"""
import argparse, hashlib, html, json, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent          # picks/
REPO = ROOT.parent
CARDS_REL = "picks/data/cards.json"
LINES_REL = "docs/data/pick_lines.json"
OUT = REPO / "docs" / "picks" / "changes.json"
VERSIONS = ROOT / "data" / "card_versions.json"   # compact copy of each version, for shallow checkouts
LINE_DIR = REPO / "docs" / "data" / "pick_line_history"
YEAR = 2026
CT = ZoneInfo("America/Chicago")
WEEKS_KEPT = 4
POOLS = ("bto", "cfp", "yahoo", "survivor")
P_MOVE = {"yahoo": 0.03}   # smallest win/cover % move worth a line (Yahoo's model wiggles 1-2 points every build)
P_MOVE_ATS = 0.02
STAGE = {"draft": "draft", "final": "final", "refresh": "refresh"}


# ---------- card versions ----------

def _git(*a):
    return subprocess.run(("git",) + a, cwd=REPO, capture_output=True, text=True, encoding="utf-8").stdout


def week_of(meta):
    """The card's week number: meta.week, else the BTO then Yahoo week in the label. Grouping goes by the label's
    dates (week_group): the Oct 26 card said "Yahoo Week 10" for the Oct 29 - Nov 2 games."""
    if meta.get("week"):
        return int(meta["week"])
    lab = meta.get("week_label") or ""
    m = re.search(r"BTO Week (\d+)", lab) or re.search(r"Yahoo Week (\d+)", lab) or re.search(r"Week (\d+)", lab)
    return int(m[1]) if m else None


def week_group(meta):
    lab = (meta.get("week_label") or "").split(" (")[0].strip()
    return lab or f"w{week_of(meta)}"


def _ts(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def split_pick(pick, team):
    """'Indiana -3.5 (LP 4)' -> 'Indiana', '-3.5 (LP 4)'. Yahoo picks have no line ('Maryland (dog)' -> '')."""
    pick = (pick or "").strip()
    if team and pick.startswith(team):
        rest = pick[len(team):].strip()
        return team, rest if re.match(r"^([+-]\d|PK|EVEN)", rest) else ""
    m = re.match(r"^(.*?)\s+([+-]\d+(?:\.\d+)?(?:\s*\(LP \d+\))?|PK)$", pick)
    return (m[1], m[2]) if m else (pick, "")


def _tb_rows(tbs):
    """Yahoo tiebreakers as rows: 'TB2 most points: <b>Boise St.</b> (10%), alt ...' -> key 'TB2 most points', pick 'Boise St.'."""
    out = []
    for t in tbs or []:
        head, sep, rest = t.partition(":")
        b = re.search(r"<b>(.*?)</b>", rest)
        if sep and b:
            out.append({"game": head.strip(), "key": head.strip(), "team": html.unescape(b[1]), "pick": html.unescape(b[1]),
                        "line": "", "p": None, "pm": None, "wager": "", "tb": True})
    return out


def extract(cards_doc):
    """One cards.json -> {pool: {title, status, rows: {key: cell}}}: just what the history compares."""
    pools = {}
    for c in cards_doc.get("cards") or []:
        rows = {}
        for r in c.get("rows") or []:
            team = r.get("pick_team") or ""
            team2, line = split_pick(r.get("pick"), team)
            m = re.search(r"Pool (?:[A-Z]{2,4} )?([+-]?\d+(?:\.\d+)?) vs (?:market|\w+) ([+-]?\d+(?:\.\d+)?)\b", r.get("why") or "")
            p = r.get("model")
            pm = r.get("market")
            rows[r.get("key") or r.get("game")] = {
                "game": re.sub(r"\s*★\s*$", "", r.get("game") or ""), "team": team or team2, "pick": r.get("pick") or "",
                "line": line, "pool": _num(m[1]) if m else None, "mkt": _num(m[2]) if m else None,
                "p": None if p is None else round(float(p), 3),
                "pm": None if pm is None or (c.get("id") in ("bto", "cfp") and pm == 0.5) else round(float(pm), 3),
                "wager": r.get("wager") or ""}
        if c.get("id") == "yahoo":
            for t in _tb_rows(c.get("tiebreakers")):
                rows[t["key"]] = {k: v for k, v in t.items() if k != "key"}
        pools[c.get("id")] = {"title": c.get("title") or c.get("id"), "status": c.get("status") or "", "rows": rows}
    return pools


def signature(pools):
    return hashlib.sha1(json.dumps(pools, sort_keys=True).encode()).hexdigest()[:12]


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def diff_pool(a, b, pool_id=""):
    """What changed in one pool from version a to version b (each {title, status, rows}, a may be None).
    -> [{key, fields: [...], text}], cells to highlight and the plain-English line ('Kansas → West Virginia')."""
    if a is None:
        return []
    out = []
    ar, br = a.get("rows") or {}, b.get("rows") or {}
    word = "win" if pool_id == "yahoo" else "cover"
    for k, n in br.items():
        o = ar.get(k)
        name = n.get("game") or k
        if o is None:
            bits = [n["pick"]] + ([n["wager"]] if n.get("wager") else [])
            out.append({"key": k, "fields": ["added"], "text": f"{name}: added {', '.join(bits)}"})
            continue
        fields, parts = [], []
        if (o.get("team") or "") != (n.get("team") or ""):
            fields.append("pick")
            parts.append(f"{o.get('team') or o.get('pick')} → {n.get('team') or n.get('pick')}")
        elif (o.get("line") or "") != (n.get("line") or ""):
            fields.append("line")
            parts.append(f"line {o.get('line') or 'none'} → {n.get('line') or 'none'}")
        if o.get("mkt") is not None and n.get("mkt") is not None and o["mkt"] != n["mkt"]:
            fields.append("mkt")
            parts.append(f"market {o['mkt']:+g} → {n['mkt']:+g}")
        po, pn = o.get("p"), n.get("p")
        if po is not None and pn is not None and abs(pn - po) >= P_MOVE.get(pool_id, P_MOVE_ATS) - 1e-9 and not n.get("tb"):
            fields.append("p")
            parts.append(f"{word} {pct(o.get('p'))} → {pct(n.get('p'))}")
        if (o.get("wager") or "") != (n.get("wager") or "") and pool_id != "yahoo":  # Yahoo's is the TB1 score: own row
            fields.append("wager")
            parts.append(f"wager {o.get('wager') or 'none'} → {n.get('wager') or 'none'}")
        if fields:
            out.append({"key": k, "fields": fields, "text": f"{name}: " + ", ".join(parts)})
    for k, o in ar.items():
        if k not in br:
            out.append({"key": k, "fields": ["dropped"], "text": f"{o.get('game') or k}: dropped {o['pick']}"})
    if (a.get("status") or "") != (b.get("status") or "") and b.get("status"):
        out.append({"key": "", "fields": ["status"], "text": f"status: {b['status']}"})
    return out


def _ct(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CT)
    except (AttributeError, ValueError):
        return None


def label(stage, iso):
    """'Wed 9:33 PM draft' (built time, CT)."""
    t = _ct(iso)
    when = f"{t:%a} {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}" if t else ""
    return f"{when} {STAGE.get(stage, stage or '')}".strip()


def git_versions(rel=CARDS_REL, git=_git, since="40.days"):
    """[(sha, commit time ISO, subject, parsed json)] oldest first, for every commit on HEAD touching `rel`."""
    out = []
    args = ["log", "--format=%H %cI %s"] + ([f"--since={since}"] if since else []) + ["HEAD", "--", rel]
    for line in reversed(git(*args).splitlines()):
        sha, t, subj = (line.split(" ", 2) + [""])[:3]
        try:
            out.append((sha, t, subj, json.loads(git("show", f"{sha}:{rel}"))))
        except (ValueError, TypeError):
            continue
    return out


def entry(vid, posted, subj, doc):
    """One card version as the history keeps it (also what data/card_versions.json stores)."""
    meta = doc.get("meta") or {}
    return {"id": vid, "posted": posted, "subj": subj or "",
            "meta": {k: meta.get(k) for k in ("week", "week_label", "stage", "generated_iso")}, "pools": extract(doc)}


def version_rows(entries):
    """Card versions (entry dicts) -> {week: {label, ids, versions}}, consecutive identical builds folded."""
    groups, nums = {}, {}
    for e in sorted(entries, key=lambda x: _ts(x["posted"])):
        meta = e["meta"]
        if not week_of(meta):
            continue
        g = week_group(meta)
        nums.setdefault(g, []).append(week_of(meta))
        sig = signature(e["pools"])
        info = groups.setdefault(g, {"label": g, "versions": [], "ids": []})
        info["ids"].append(e["id"])
        vs = info["versions"]
        if vs and vs[-1]["sig"] == sig:
            continue
        built = meta.get("generated_iso") or e["posted"]
        if any(v["built"] == built for v in vs):  # same build re-posted (a restore, a hand edit): show when it went up
            built = e["posted"]
        note = " (backup)" if re.match(r"picks backup card", e["subj"], re.I) else ""
        if any(v["sig"] == sig for v in vs):
            note += " (restored)"
        vs.append({"id": e["id"], "posted": e["posted"], "built": meta.get("generated_iso"), "stage": meta.get("stage"),
                   "label": label(meta.get("stage"), built) + note, "sig": sig, "pools": e["pools"]})
    weeks = {}
    for g, info in groups.items():
        wk = max(set(nums[g]), key=lambda n: (nums[g].count(n), -n))  # most common number in the group
        weeks[wk] = info
    return weeks


def build_week(wk, info):
    """Per pool: the version columns where that pool changed against the last column shown (first and last always
    kept, so small drifts add up instead of hiding), cells, change lines."""
    vs = info["versions"]
    out = {"week": wk, "label": info["label"], "versions": [{k: v[k] for k in ("id", "posted", "built", "stage", "label")}
                                                              for v in vs], "pools": []}
    for pid in POOLS:
        cols, changes, prev = [], [], None
        idx = [i for i, v in enumerate(vs) if pid in v["pools"]]
        for i in idx:
            cur = vs[i]["pools"][pid]
            ch = diff_pool(prev, cur, pid)
            if prev is None or ch or i == idx[-1]:  # the last version always shows, so the timeline ends "now"
                cols.append(i)
                changes.append(ch)
                prev = cur
        if not cols:
            continue
        keys = []
        for i in cols:
            for k in vs[i]["pools"][pid]["rows"]:
                if k not in keys:
                    keys.append(k)
        out["pools"].append({
            "id": pid, "title": vs[cols[-1]]["pools"][pid]["title"], "cols": cols, "changes": changes,
            "status": [vs[i]["pools"][pid]["status"] for i in cols],
            "rows": [{"key": k, "cells": [vs[i]["pools"][pid]["rows"].get(k) for i in cols]} for k in keys],
            "hidden": len(idx) - len(cols)})
    return out


def _shallow(git):
    return git("rev-parse", "--is-shallow-repository").strip() == "true"


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build(git=_git, cards_path=None, now=None, stored=None, previous=None):
    """(changes.json content, card_versions.json content): the last WEEKS_KEPT weeks of card versions.
    In a shallow checkout (the cloud backup run) git shows only the newest commit, so the newest week also uses
    `stored` (data/card_versions.json: that week's versions) and older weeks are carried from `previous`
    (the current changes.json)."""
    now = now or datetime.now(timezone.utc)
    cards_path = cards_path or (ROOT / "data" / "cards.json")
    entries = [entry(*v) for v in git_versions(git=git)]
    ids = {e["id"] for e in entries}
    shallow = stored is not None or _shallow(git)
    if shallow:
        stored = _load(VERSIONS, []) if stored is None else stored
        previous = _load(OUT, {}) if previous is None else previous
        entries += [e for e in stored if e.get("id") not in ids and e.get("id") != "local"]
    try:
        local = json.loads(Path(cards_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        local = None
    if local:
        e = entry("local", now.isoformat(timespec="seconds"), "", local)
        newest = max(entries, key=lambda x: _ts(x["posted"])) if entries else None
        if not newest or signature(newest["pools"]) != signature(e["pools"]):
            entries.append(e)  # this build, not committed yet (pp.publish commits it with this file)
    weeks = version_rows(entries)
    built = {w: build_week(w, weeks[w]) for w in weeks}
    if shallow:
        for w in (previous or {}).get("weeks") or []:
            built.setdefault(w["week"], w)
    keep = sorted(built)[-WEEKS_KEPT:]
    page = {"generated": now.isoformat(timespec="seconds"), "season": YEAR, "weeks": [built[w] for w in reversed(keep)]}
    newest = max(weeks) if weeks else None
    return page, [e for e in entries if newest and e["id"] in weeks[newest]["ids"] and e["id"] != "local"]


def write(**kw):
    """Rebuild docs/picks/changes.json (+ data/card_versions.json). Called by pp.cards.write; never fails a card build."""
    d, versions = build(**kw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    VERSIONS.write_text(json.dumps(versions, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return d


# ---------- line series ----------

def _home(game):
    a, _, h = (game or "").partition(" @ ")
    return a.strip(), h.strip()


def to_home(game, side, v):
    """pick_lines rows give lines from the value side; store the home team's spread."""
    if v is None:
        return None
    return float(v) if side == _home(game)[1] else -float(v)


def add_point(series, t, v):
    """Append (t, v) when v differs from the last value. Returns True if appended."""
    if v is None:
        return False
    if series and series[-1][1] == v:
        return False
    series.append([t, v])
    return True


def update_series(store, t, rows, extra=()):
    """Fold one scan into a week's store (in place).
    rows: pp.lines gap rows {pool, league, game, side, pool_line, market_line, book, kick}.
    extra: [{game, league, market_home, open_home, kick, pool?}] (Yahoo games and ESPN openers).
    store: {"games": {game: {league, home, away, kick, open, market: [[t, home spread]], pools: {pool: [[t, line]]}}}, ...}."""
    games = store.setdefault("games", {})
    for r in rows:
        g = games.setdefault(r["game"], {"league": r.get("league"), "away": _home(r["game"])[0], "home": _home(r["game"])[1],
                                         "kick": r.get("kick"), "open": None, "market": [], "pools": {}})
        g["kick"] = r.get("kick") or g.get("kick")
        add_point(g["market"], t, to_home(r["game"], r["side"], r.get("market_line")))
        add_point(g["pools"].setdefault(r["pool"], []), t, to_home(r["game"], r["side"], r.get("pool_line")))
        g["seen"] = t
    for e in extra:
        g = games.setdefault(e["game"], {"league": e.get("league"), "away": _home(e["game"])[0], "home": _home(e["game"])[1],
                                         "kick": e.get("kick"), "open": None, "market": [], "pools": {}})
        if e.get("open_home") is not None:
            g["open"] = e["open_home"]
        if not any(r["game"] == e["game"] for r in rows):
            add_point(g["market"], t, e.get("market_home"))
            g["seen"] = t
    store["updated"] = t
    return store


def line_path(week, out_dir=None):
    return Path(out_dir or LINE_DIR) / f"{YEAR}-w{int(week):02d}.json"


def load_store(week, out_dir=None):
    p = line_path(week, out_dir)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"season": YEAR, "week": int(week), "games": {}}


def save_store(store, week, out_dir=None):
    p = line_path(week, out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def extra_lines(slate, events, find):
    """Yahoo games' market spread (home) and every pool game's ESPN opener. events: {"CFB": [...], "NFL": [...]}."""
    out = []
    for pool in ("bto", "cfp", "yahoo"):
        for sg in (slate.get(pool) or {}).get("games") or []:
            game = f"{sg['away']} @ {sg['home']}"
            league = sg.get("league", "CFB")
            ev, flipped = find(events.get(league) or [], sg["away"], sg["home"])
            if not ev:
                continue
            sgn = -1 if flipped else 1
            mh = None if ev.get("home_spread") is None or ev.get("state") != "pre" else sgn * ev["home_spread"]
            oh = None if ev.get("open_home_spread") is None else sgn * ev["open_home_spread"]
            out.append({"game": game, "league": league, "market_home": mh if pool == "yahoo" else None,
                        "open_home": oh, "kick": ev.get("kick")})
    return out


def record_lines(week, rows, now, fetch, slate, out_dir):
    """pp.lines hook: add this scan to the week's line history. Never raises into the scan."""
    from .lines import find
    t = now.astimezone(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
    extra = []
    try:
        events = {"CFB": fetch("CFB", week)}
        nfl_weeks = sorted({g.get("nfl_week") for p in ("bto", "cfp") for g in (slate.get(p) or {}).get("games") or []
                            if g.get("league") == "NFL"} - {None})
        events["NFL"] = [e for w in nfl_weeks for e in fetch("NFL", w)]
        extra = extra_lines(slate, events, find)
    except Exception as ex:  # ESPN hiccup: the pool rows still go in
        print("line history extras skipped:", repr(ex))
    store = load_store(week, out_dir)
    update_series(store, t, rows, extra)
    save_store(store, week, out_dir)
    return store


def backfill_lines(git=_git, out_dir=None):
    """Seed the per-week line files from every committed docs/data/pick_lines.json (merged into what's there)."""
    stores = {}
    for sha, t, _, d in git_versions(LINES_REL, git=git):
        wk = d.get("week")
        if not wk:
            continue
        ts = datetime.fromisoformat(d.get("updated") or t).astimezone(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
        update_series(stores.setdefault(wk, {"season": YEAR, "week": wk, "games": {}}), ts, d.get("rows") or [])
    for wk, s in stores.items():
        save_store(merge_stores(s, load_store(wk, out_dir)), wk, out_dir)
    return sorted(stores)


def merge_stores(a, b):
    """Union of two week stores (each change-only); points re-folded in time order."""
    out = {"season": a.get("season") or b.get("season"), "week": a.get("week") or b.get("week"), "games": {}}
    for src in (a, b):
        for name, g in (src.get("games") or {}).items():
            o = out["games"].setdefault(name, {"league": g.get("league"), "away": g.get("away"), "home": g.get("home"),
                                               "kick": g.get("kick"), "open": g.get("open"), "market": [], "pools": {}})
            o["kick"] = g.get("kick") or o["kick"]
            o["open"] = g.get("open") if g.get("open") is not None else o["open"]
            o["seen"] = max(filter(None, (o.get("seen"), g.get("seen")))) if (o.get("seen") or g.get("seen")) else None
            o["market"] = o["market"] + list(g.get("market") or [])
            for p, s in (g.get("pools") or {}).items():
                o["pools"][p] = o["pools"].get(p, []) + list(s)
    for o in out["games"].values():
        o["market"] = _refold(o["market"])
        o["pools"] = {p: _refold(s) for p, s in o["pools"].items()}
    out["updated"] = max(filter(None, (a.get("updated"), b.get("updated"))), default=None)
    return out


def _refold(points):
    out = []
    for t, v in sorted(points, key=lambda x: x[0]):
        add_point(out, t, v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-lines", action="store_true")
    a = ap.parse_args()
    if a.backfill_lines:
        print("line history weeks:", backfill_lines())
    d = write()
    print(json.dumps({w["week"]: len(w["versions"]) for w in d["weeks"]}))


if __name__ == "__main__":
    main()
