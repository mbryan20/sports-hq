"""Our player values ("ours") next to the FantasyCalc market, for the dynasty leagues (Sunday's Best, 3-Ball FB).

ours = market x e^edge. The edge predicts how much more (or less) a player's value will move over the next 12 months than
similar players (same position, age band, season), from a few signals that beat the market on seasons the model never saw
(shq/pv_train.py writes the weights and that test into state/pv_model.json; research/player-values-build-plan.md).

- Versions: "in" (in-season, from week 5 through January: season to date) and "off" (February to week 4: last full season).
- A position/version is "live" only if it passed the ship test (4 parts: 3%+ less error than the market over the test
  seasons, better in 3 of the last 4, big calls right 58%+ with 20+ calls, 80+ test cases) and Model health hasn't paused it
  (state/pv_status.json: under half of its last 30 scored calls right). Everything else shows "Ours = market".
- Guards: market value under MIN_VALUE, too few games, IR/out for the season, and a QB with a higher-valued QB teammate (a
  fill-in starter: Drew Lock in Nov 2026 looked +40% on efficiency alone) all get no edge. One call moves the value CAP at most.
- Advice (Michael's pick on the review page, Nov 20: "Use ours where it beat the market; always show both"): dv(p) is the
  decision value = ours where live, else the market. Trade fairness always stays on the market (what the other owner sees).
- Rookies: a trial (shown, never used in advice) until their own test passes on 4 classes."""
import math

from . import pv_data
from .common import STATE, load_json
from .config import SEASON

MODEL_FILE = STATE / "pv_model.json"
STATUS_FILE = STATE / "pv_status.json"     # Model health: paused positions and the live record per position/version
CAP = 0.35
MIN_VALUE = 1000
OUT = ("IR", "PUP", "SUSP", "NFI")
USE = "proven"     # "proven" (pick A), "market" (B: show both, advice on the market), "all" (C)


def version(now, week):
    """"in" from week 5 (4 weeks played) through January, else "off"."""
    m = now.month
    if m in (9, 10, 11, 12) and week >= 5 or m == 1:
        return "in"
    return "off"


def last_full_season(now):
    """The last season whose regular season is over: Feb-Aug of year Y and Sep-Dec of year Y-1 both read season Y-1
    (in January the in-season version reads the season just finished)."""
    return now.year - 1


def z(x, m, s):
    return 0.0 if x is None else (x - m) / s


def X(pos, ver, f):
    """Feature vector (must match shq/pv_train.py's training rows; research exp2_signals.py lean_oct / lean_aug)."""
    if ver == "in":
        if pos in ("WR", "TE"):
            return [1.0, (f["ppg"] - 12) / 6, (f["tshare"] - 0.12) / 0.08]
        if pos == "QB":
            return [1.0, ((f["epa_db"] if f.get("epa_db") is not None else 0.05) - 0.05) / 0.15, (f["ppg"] - 15) / 6]
        return [1.0, (f["ppg"] - 12) / 6]
    has = 1.0 if f and f.get("games", 0) >= pv_data.MIN_GAMES_OFF else 0.0
    g = lambda k, m, s: z(f.get(k), m, s) if has else 0.0
    if pos in ("WR", "TE"):
        return [1.0, has, g("tshare", 0.15, 0.07), g("games", 13, 4)]
    if pos == "QB":
        return [1.0, has, g("epa_pg", 2, 6), g("games", 13, 4)]
    return [1.0, has, g("ppg", 12, 6), g("games", 13, 4)]


def why(pos, ver, f):
    if ver == "in":
        pts = f"{f['ppg']:.1f} pts/g"
        if pos == "QB":
            return (f"EPA per dropback {f['epa_db']:+.2f}, " if f.get("epa_db") is not None else "") + pts + " this season"
        if pos in ("WR", "TE"):
            return f"target share {100 * f['tshare']:.0f}%, {pts} this season"
        return f"{pts} this season"
    gm = f"{f['games']:.0f} games"
    if pos == "QB":
        return f"passing EPA {f['epa_pg']:+.1f} a game, {gm} last season"
    if pos in ("WR", "TE"):
        return f"target share {100 * (f.get('tshare') or 0):.0f}%, {gm} last season"
    return f"{f['ppg']:.1f} pts/g, {gm} last season"


class Features:
    """nflverse features for the live run, loaded once per process."""

    def __init__(self, now, week):
        self.now, self.week, self.ver = now, week, version(now, week)
        self._ids = self._wk = self._season = None

    def ids(self):
        if self._ids is None:
            self._ids = pv_data.ids()
        return self._ids

    def of(self, sid):
        g = self.ids()["sleeper"].get(str(sid or ""))
        if not g:
            return None
        if self.ver == "in":
            if self._wk is None:
                self._wk = pv_data.week_stats(SEASON)
            return pv_data.to_date(self._wk.get(g), max(0, self.week - 1))
        if self._season is None:
            self._season = pv_data.season_stats(last_full_season(self.now))
        f = self._season.get(g)
        return f if f and f["games"] >= pv_data.MIN_GAMES_OFF else None


def load_model():
    return load_json(MODEL_FILE) or {}


def load_status():
    return load_json(STATUS_FILE) or {}


def entry(model, ver, pos):
    return ((model.get("versions") or {}).get(ver) or {}).get(pos)


def live(model, status, ver, pos):
    """Passed its test and not paused by Model health."""
    e = entry(model, ver, pos)
    paused = (status.get("paused") or {}).get(f"{ver}:{pos}")
    return bool(e and (e.get("gate") or {}).get("pass") and not paused)


def record_text(model, status, ver, pos):
    """'Beat the market in 3 of the last 4 seasons · live: right 11 of 16' (rule 27: every call shows its track record)."""
    e = entry(model, ver, pos) or {}
    yrs = sorted((e.get("by_year") or {}).items())[-4:]
    parts = []
    if yrs:
        parts.append(f"beat the market in {sum(1 for _, y in yrs if y.get('cut', 0) > 0)} of the last {len(yrs)} seasons")
    lv = (status.get("live") or {}).get(f"{ver}:{pos}") or {}
    if lv.get("calls", 0) >= 10:
        parts.append(f"live calls right {lv['right']} of {lv['calls']}")
    else:
        parts.append("live record: too new to score")
    paused = (status.get("paused") or {}).get(f"{ver}:{pos}")
    if paused:
        parts.append(f"paused: {paused}")
    return "; ".join(parts)


def qb_fill_ins(values_by_sid, team_of):
    """sids of QBs with a higher-valued QB on the same NFL team (backups and fill-in starters)."""
    best = {}
    for sid, v in values_by_sid.items():
        if v.get("pos") == "QB" and team_of(sid):
            t = team_of(sid)
            if v.get("value", 0) > best.get(t, (0, None))[0]:
                best[t] = (v.get("value", 0), sid)
    return {sid for sid, v in values_by_sid.items()
            if v.get("pos") == "QB" and team_of(sid) and best.get(team_of(sid), (0, sid))[1] != sid}


def call(model, status, feats, pos, market, sid, status_tag=None, fill_in=False):
    """{"ours", "edge", "why", "record", "live", "ver"} for one player, or None (no call: show the market)."""
    ver = feats.ver
    e = entry(model, ver, pos)
    if not e or not market or market < MIN_VALUE or pos not in pv_data.SKILL:
        return None
    if status_tag in OUT:
        return None
    if pos == "QB" and fill_in:
        return None
    f = feats.of(sid)
    if not f:
        return None
    x = X(pos, ver, f)
    raw = sum(a * b for a, b in zip(e["w"], x)) * e.get("shrink", 1.0)
    edge = max(-CAP, min(CAP, raw))
    return {"ours": int(round(market * math.exp(edge), -1)), "edge": round(edge, 3), "why": why(pos, ver, f),
            "record": record_text(model, status, ver, pos), "live": live(model, status, ver, pos), "ver": ver,
            "capped": abs(raw) > CAP}


def dv(p, use=None):
    """Decision value: ours where its position passed (pick A), else the market."""
    use = use or USE
    pv = p.get("pv")
    if pv and (use == "all" or (use == "proven" and pv.get("live"))):
        return pv["ours"]
    return p.get("val", 0)


def label(p):
    """'ours 8,500 (+15%)' or 'ours = market' for the site and advice text."""
    pv = p.get("pv")
    if not pv:
        return "ours = market"
    pct = round(100 * (math.exp(pv["edge"]) - 1))
    return f"ours {pv['ours']:,} ({pct:+d}%)" + ("" if pv.get("live") else ", trial")


def annotate(players, fc, team_of, statuses, now, week, model=None, status=None, feats=None):
    """Put p["pv"] on each player dict that has "sid" and "val" (the market). `fc` is FantasyCalc's {sid: row} for the
    league's settings (for the QB fill-in guard), team_of(sid) his NFL team, statuses {sid: injury tag}."""
    model = load_model() if model is None else model
    if not model.get("versions"):
        return 0
    status = load_status() if status is None else status
    feats = feats or Features(now, week)
    fill = qb_fill_ins(fc, team_of)
    n = 0
    for p in players:
        sid = p.get("sid")
        pos = next((x for x in p.get("positions") or [] if x in pv_data.SKILL), None) or (fc.get(sid or "") or {}).get("pos")
        try:
            c = call(model, status, feats, pos, p.get("val"), sid, statuses.get(sid) or p.get("status"), sid in fill)
        except Exception:
            c = None
        p["pv"] = c
        n += bool(c)
    return n


def rookie_call(model, pos, market, draft_info, class_mean_log, now):
    """Rookie trial (display only): {"ours", "edge", "why", "trial": True} from NFL draft position; None when its entry is
    missing. Applies from the NFL draft through the rookie's first 3 games (then the in-season model takes over)."""
    e = ((model.get("rookie") or {}).get(pos))
    if not e or not market or not draft_info or not draft_info.get("pick"):
        return None
    x = [1.0, (math.log(draft_info["pick"]) - 3.5), (math.log(market) - class_mean_log)]
    raw = sum(a * b for a, b in zip(e["w"], x)) * e.get("shrink", 1.0)
    edge = max(-CAP, min(CAP, raw))
    rnd = draft_info.get("round")
    return {"ours": int(round(market * math.exp(edge), -1)), "edge": round(edge, 3), "trial": True, "live": False,
            "ver": "rookie", "why": f"NFL draft pick {draft_info['pick']}" + (f" (round {rnd})" if rnd else ""),
            "record": "rookie trial: shown only until it beats the market on 4 draft classes"}



def rookie_class(now):
    """The latest NFL draft class: this year's from May, last year's before."""
    return now.year if now.month >= 5 else now.year - 1


def rookies(players, fc, now, model=None, draft=None, ids=None):
    """Rookie trial on players with no call yet: this draft class only (shown as a trial, never used in advice)."""
    model = load_model() if model is None else model
    if not model.get("rookie"):
        return 0
    yr = rookie_class(now)
    cls = [v["value"] for v in fc.values() if (v.get("draft") or {}).get("year") == yr and v.get("value", 0) >= 300]
    if not cls:
        return 0
    mean_log = sum(math.log(v) for v in cls) / len(cls)
    draft = pv_data.draft() if draft is None else draft
    ids = pv_data.ids() if ids is None else ids
    n = 0
    for p in players:
        if p.get("pv") or not p.get("sid"):
            continue
        row = fc.get(p["sid"]) or {}
        if (row.get("draft") or {}).get("year") != yr:
            continue
        d = draft.get(ids["sleeper"].get(p["sid"], ""))
        c = rookie_call(model, row.get("pos"), p.get("val"), {"pick": d[2], "round": d[1]} if d else None, mean_log, now)
        if c:
            p["pv"] = c
            n += 1
    return n
