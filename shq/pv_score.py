"""Weekly self-scoring of our player values, inside the nightly Model health job (rule 28: Sep-Jan; no chat).

- Log (Tuesdays Sep-Jan, or when the last log is 6+ days old in that window): every player worth 1,000+ in the two dynasty
  leagues, his FantasyCalc value and our call, from docs/data/players_nfl.json -> state/pv_calls/<date>.json.
- Score: a call matures 12 weeks later. It's right when FantasyCalc moved our way compared with players at the same
  position in the same league (so the whole scale drifting doesn't count). Only live calls 10%+ off the market are scored.
- Fall-back: when the last 30 scored calls of a position/version are right under half the time, state/pv_status.json
  pauses it and the site goes back to the market for it ("paused: ..."). It comes back only after a Claude review passes it
  again (shq/pv_train.py) and clears the pause.
Model health shows one check per position/version ("pv.in_QB" ...)."""
import datetime as dt
import math
import statistics as st

from .common import DATA, STATE, load_json, save_json

CALLS = STATE / "pv_calls"
STATUS = STATE / "pv_status.json"
MATURE_DAYS = 84
MAX_AGE_DAYS = 400
MIN_EDGE = 10            # percent
WINDOW = 30
PAUSE_UNDER = 0.5
SEASON_MONTHS = (9, 10, 11, 12, 1)


def due(now, last_day):
    if now.month not in SEASON_MONTHS:
        return False
    return now.weekday() == 1 or last_day is None or (now.date() - last_day).days >= 6


def snapshot(players_nfl):
    """{league: [{id, pos, fc, e, live, v}]} for the dynasty leagues' players worth 1,000+."""
    out = {}
    for name, L in (players_nfl.get("leagues") or {}).items():
        if not (isinstance(L, dict) and L.get("dynasty")):
            continue
        rows = []
        for p in L.get("players") or []:
            if p.get("pos") in ("QB", "RB", "WR", "TE") and (p.get("fc") or 0) >= 1000:
                pv = p.get("pv") or {}
                rows.append({"id": p["id"], "pos": p["pos"], "fc": p["fc"], "e": pv.get("e"), "live": bool(pv.get("live")),
                             "v": pv.get("v")})
        out[name] = rows
    return out


def log(now, players_nfl=None, calls_dir=None):
    calls_dir = calls_dir or CALLS
    days = sorted(dt.date.fromisoformat(p.stem) for p in calls_dir.glob("*.json")) if calls_dir.exists() else []
    if not due(now, days[-1] if days else None):
        return None
    snap = snapshot(players_nfl if players_nfl is not None else (load_json(DATA / "players_nfl.json") or {}))
    if not any(snap.values()):
        return None
    path = calls_dir / f"{now.date().isoformat()}.json"
    save_json(path, {"at": now.isoformat(), "leagues": snap})
    return path


def score(now, players_nfl=None, calls_dir=None):
    """{"ver:pos": [(day, right)]} newest first, from calls that matured."""
    calls_dir = calls_dir or CALLS
    data = players_nfl if players_nfl is not None else (load_json(DATA / "players_nfl.json") or {})
    cur = {name: {p["id"]: p.get("fc") for p in (L.get("players") or [])}
           for name, L in (data.get("leagues") or {}).items() if isinstance(L, dict)}
    out = {}
    for path in sorted(calls_dir.glob("*.json"), reverse=True) if calls_dir.exists() else []:
        day = dt.date.fromisoformat(path.stem)
        age = (now.date() - day).days
        if age < MATURE_DAYS or age > MAX_AGE_DAYS:
            continue
        logged = load_json(path) or {}
        for name, rows in (logged.get("leagues") or {}).items():
            now_fc = cur.get(name) or {}
            moves = {}
            for r in rows:
                v = now_fc.get(r["id"])
                if v and r["fc"]:
                    moves[r["id"]] = (r["pos"], math.log(v / r["fc"]))
            by_pos = {}
            for pos, m in moves.values():
                by_pos.setdefault(pos, []).append(m)
            avg = {pos: st.mean(ms) for pos, ms in by_pos.items() if len(ms) >= 5}
            for r in rows:
                if not r.get("live") or r.get("e") is None or abs(r["e"]) < MIN_EDGE or r["id"] not in moves:
                    continue
                pos, m = moves[r["id"]]
                if pos not in avg:
                    continue
                rel = m - avg[pos]
                out.setdefault(f"{r['v']}:{pos}", []).append((day.isoformat(), (rel > 0) == (r["e"] > 0)))
    return out


def status(now, scored, old=None):
    """state/pv_status.json: live record per position/version and pauses (kept until a review clears them)."""
    old = old if old is not None else (load_json(STATUS) or {})
    paused = dict(old.get("paused") or {})
    live = {}
    for key, rs in scored.items():
        last = rs[:WINDOW]
        right = sum(1 for _, ok in last if ok)
        live[key] = {"right": right, "calls": len(last)}
        if len(last) >= WINDOW and right / len(last) < PAUSE_UNDER and key not in paused:
            paused[key] = f"right on {right} of the last {len(last)} scored calls (since {now.date().isoformat()})"
    return {"updated": now.isoformat(), "live": live, "paused": paused}


def health(now, j):
    """Model health section: (checks, details, notes). Logs this week's calls when due, scores matured ones, writes the status."""
    logged = log(now)
    scored = score(now)
    st_ = status(now, scored)
    save_json(STATUS, st_)
    checks = []
    for key in sorted(set(st_["live"]) | {"in:QB", "in:WR"}):
        lv = st_["live"].get(key) or {"right": 0, "calls": 0}
        cid = "pv." + key.replace(":", "_")
        checks.append(j(cid, round(lv["right"] / lv["calls"], 3) if lv["calls"] else None, lv["calls"]))
    notes = [f"Calls logged {'today' if logged else 'weekly on Tuesdays, Sep-Jan'}; each matures {MATURE_DAYS // 7} weeks later and is "
             f"right when FantasyCalc moved our way against the same position in that league. Under half right over the last "
             f"{WINDOW} pauses that position (site and advice go back to the market) until a review passes it again."]
    if st_["paused"]:
        notes.append("Paused: " + "; ".join(f"{k}: {v}" for k, v in st_["paused"].items()))
    return checks, {"live": st_["live"], "paused": st_["paused"]}, notes
