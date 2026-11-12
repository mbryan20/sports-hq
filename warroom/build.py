"""Rebuild War Room v2: Sleeper + nflverse -> docs/war-room-v2/index.html (the page, with its data inlined)
and docs/war-room-v2/bids.json (bids table, cut risks, freed players, FAAB; computed by the page's own
model under Node, so both always agree).

    py -m warroom.build            needs `node` on PATH (or NODE=<path to node>)

Read-only: it only reads Sleeper's public API. Files are written only when their content changed."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from shq.common import ROOT, now_utc

from .model import build

HERE = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "war-room-v2"


def write_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def node(*args, data):
    """Run export.js with `data` written to a temp file as its last argument."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write(data)
    try:
        return subprocess.run([os.environ.get("NODE", "node"), str(HERE / "export.js"), *args, tmp.name],
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout
    finally:
        os.unlink(tmp.name)


def ladder(cases, estimates):
    """Sorted ratios of what each past claim actually went for to the model's raw estimate at the time,
    split at a $10 estimate (the model underprices stars more). The page turns these into a win chance
    for any bid. Freed players nobody claimed count as going for $0."""
    lo, hi = [], []
    for case, got in zip(cases, estimates):
        for (sid, paid), est in zip(case["targets"], got["est"]):
            (hi if est >= 10 else lo).append(round(paid / max(1, est), 3))
    if len(hi) < 12:          # too few big claims to stand alone: one shared ladder
        lo, hi = lo + hi, []
    return {"lo": sorted(lo), "hi": sorted(hi)}


def rank_tier(rank):
    return 0 if rank == 1 else 1 if rank <= 3 else 2 if rank <= 8 else 3


def need_tier(g):
    return 0 if g < 1 else 1 if g < 3 else 2 if g < 6 else 3


def rival_model(cases, inputs, hist, me):
    """The rival-by-rival price model (model.js rivalWin), fitted on every past waiver run as it stood. For each
    surviving rival and each player on waivers that run: did he claim him, and for how much as a share of his own
    FAAB. q = claim chance by (player's rank among that run's targets, lineup points he'd add for that rival),
    smoothed toward the overall rate; shares = his bid / his FAAB by rank tier; scale and cap = each rival's own
    habit (his average share vs the league's, half-weighted; his biggest share so far). Michael's own claims are left
    out. Replaces the one-ladder estimate, whose 10-30% "coin flips" on stars won 1 in 79 in weeks 6-9 (Nov 12)."""
    import collections
    bids = collections.defaultdict(dict)
    for h in hist:
        for r, b in h["bids"]:
            k = (h["leg"], h["sid"])
            bids[k][str(r)] = max(bids[k].get(str(r), -1), b)
    rows = []
    for case, got in zip(cases, inputs):
        L, teams, cut = case["leg"], case["D"]["teams"], str(case["D"]["cut"]["roster"])
        order = sorted(range(len(case["targets"])), key=lambda i: -got["rival"][i]["base"])
        rank = {i: pos + 1 for pos, i in enumerate(order)}
        for i, (sid, _) in enumerate(case["targets"]):
            for t, g in got["rival"][i]["needs"].items():
                if t in (str(me), cut) or t not in teams:
                    continue
                rows.append((rank_tier(rank[i]), need_tier(g), teams[t]["faab"], t, bids[(L, sid)].get(t, -1)))
    if not rows:
        return None
    cq, nq = collections.Counter(), collections.Counter()
    shares, pers = collections.defaultdict(list), collections.defaultdict(list)
    for rk, g, B, t, b in rows:
        nq[(rk, g)] += 1
        if b >= 0:
            cq[(rk, g)] += 1
            if B > 0:
                shares[rk].append(min(1.0, b / B))
                pers[t].append(min(1.0, b / B))
    allsh = [x for v in shares.values() for x in v]
    mean_all = sum(allsh) / max(1, len(allsh))
    base_q = sum(cq.values()) / sum(nq.values())
    return {"n": len(rows), "q_base": round(base_q, 4),
            "q": {f"{rk},{g}": round((cq[(rk, g)] + 2 * base_q) / (nq[(rk, g)] + 2), 4) for rk, g in nq},
            "shares": {str(rk): sorted(round(x, 3) for x in v) for rk, v in shares.items()},
            "all": sorted(round(x, 3) for x in allsh),
            "scale": {t: round(0.5 + 0.5 * (sum(v) / len(v)) / mean_all, 3) for t, v in pers.items() if len(v) >= 3 and mean_all},
            "cap": {t: round(max(v), 3) for t, v in pers.items() if len(v) >= 3}}


def page_files(blob):
    """The page (data inlined) plus what the league pages' Try-a-move box loads (docs/lib/move.js, Q-054): the same
    data and model as separate files, so the Guillotine page runs the War Room's own numbers."""
    page = ((HERE / "app_template.html").read_text(encoding="utf-8")
            .replace("__DATA__", blob.replace("</", r"<\/"))
            .replace("__MODEL__", (HERE / "model.js").read_text(encoding="utf-8"))
            .replace("__JS__", (HERE / "app.js").read_text(encoding="utf-8")))
    return (("index.html", page), ("data.json", blob), ("model.js", (HERE / "model.js").read_text(encoding="utf-8")),
            ("compare.js", (HERE / "compare.js").read_text(encoding="utf-8")),
            ("compare.html", (HERE / "compare.html").read_text(encoding="utf-8")))


def repage():
    """Rebuild the page files from the data already inlined in docs/war-room-v2/index.html (no Sleeper, no Node):
    for a change to app.js, model.js or the template between scheduled builds.  py -m warroom.build --repage"""
    import re
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', (OUT / "index.html").read_text(encoding="utf-8"), re.S)
    blob = m.group(1).replace(r"<\/", "</")
    return [name for name, text in page_files(blob) if write_if_changed(OUT / name, text)]


def main():
    data = build(now_utc())
    cases = data.pop("calib")
    got = json.loads(node("--calibrate", data=json.dumps(cases))) if cases else []
    data["ladder"] = ladder(cases, got) if cases else None
    data["rival_model"] = rival_model(cases, got, data["hist"], data["me"]) if cases else None
    data["rules"] = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))   # Michael's own numbers
    blob = json.dumps(data, separators=(",", ":"), sort_keys=True)
    bids = node(data=blob)
    files = (("bids.json", bids),) + page_files(blob)
    changed = [name for name, text in files if write_if_changed(OUT / name, text)]
    summary = json.loads(bids)
    print(f"{data['asof']} | week {data['week']} | swing {data['sd']} | ladder {len((data['ladder'] or {}).get('lo', []))}+"
          f"{len((data['ladder'] or {}).get('hi', []))} claims | rival model {(data['rival_model'] or {}).get('n', 0)} | $/win point {summary['budget']['dollars_per_win_point']} | "
          f"my cut risk {summary['me']['cut_risk_next_week']:.1%} | "
          f"{len(summary['bids'])} bid rows | changed: {', '.join(changed) or 'nothing'}")


if __name__ == "__main__":
    import sys
    print(repage()) if "--repage" in sys.argv else main()
