"""Season check: stats pick vs betting-market favorite on Michael's graded Yahoo games (Nov 27 fix).

The card's old "model 70% vs market 75%" line was a one-time backtest of weeks 1-8 (Oct 31) repeated every week.
Each card build now logs its Yahoo rows' stats and market win chances to data/model_log/<YEAR>-wNN.json; the Tuesday
postmortem grades who won (data/postmortem). This joins the two, so the line re-computes as weeks are graded.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def log_rows(cards, week, year, root=ROOT):
    """Save this build's Yahoo rows (key, pick_team, model, market). Later builds in the week overwrite it."""
    rows = [{"key": r["key"], "pick_team": r.get("pick_team"), "model": r.get("model"), "market": r.get("market")}
            for c in cards if c.get("id") == "yahoo" for r in c.get("rows", [])
            if r.get("key") and r.get("model") is not None and r.get("market") is not None]
    if not rows:
        return
    d = root / "data" / "model_log"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{year}-w{week:02d}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


def _graded(root):
    for f in sorted((root / "data" / "model_log").glob("*.json")):
        pm = root / "data" / "postmortem" / f.name
        if not pm.exists():
            continue
        try:
            res = {p["key"]: p for p in json.loads(pm.read_text(encoding="utf-8-sig"))["pools"]["yahoo"]["card"]["picks"]}
            rows = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        week = int(f.stem.split("-w")[-1])
        for r in rows:
            p = res.get(r["key"])
            if not p or p.get("pick") != r.get("pick_team") or p.get("result") not in (0, 1, 0.0, 1.0):
                continue  # pick changed after the log, or game not graded
            yield week, r, p["result"] == 1


def summary(root=ROOT):
    n = model = market = dis = dis_model = dis_market = close = close_model = close_market = 0
    weeks = set()
    for week, r, won in _graded(root):
        weeks.add(week)
        mr, kr = (r["model"] >= 0.5) == won, (r["market"] >= 0.5) == won
        n += 1; model += mr; market += kr
        if (r["model"] >= 0.5) != (r["market"] >= 0.5):
            dis += 1; dis_model += mr; dis_market += kr
        if 0.4 <= r["market"] <= 0.6:
            close += 1; close_model += mr; close_market += kr
    return {"n": n, "weeks": sorted(weeks), "model": model, "market": market, "dis": dis, "dis_model": dis_model,
            "dis_market": dis_market, "close": close, "close_model": close_model, "close_market": close_market}


def line(root=ROOT):
    s = summary(root)
    if not s["n"]:
        return None
    w = s["weeks"]
    span = f"week {w[0]}" if len(w) == 1 else f"weeks {w[0]}-{w[-1]}" if w == list(range(w[0], w[-1] + 1)) else "weeks " + ", ".join(map(str, w))
    pct = lambda a, b: f"{a * 100 / b:.0f}%"
    out = (f"This season, your Yahoo games ({span}, {s['n']} graded): market favorite won {pct(s['market'], s['n'])}, "
           f"stats pick {pct(s['model'], s['n'])}")
    if s["dis"]:
        out += f"; when they disagreed ({s['dis']}): market right {s['dis_market']}, stats {s['dis_model']}"
    if s["close"]:
        out += f"; close games (40-60%, {s['close']}): market {s['close_market']}, stats {s['close_model']}"
    return out + "."
