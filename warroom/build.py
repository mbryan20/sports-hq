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
    data["ladder"] = ladder(cases, json.loads(node("--calibrate", data=json.dumps(cases)))) if cases else None
    blob = json.dumps(data, separators=(",", ":"), sort_keys=True)
    bids = node(data=blob)
    files = (("bids.json", bids),) + page_files(blob)
    changed = [name for name, text in files if write_if_changed(OUT / name, text)]
    summary = json.loads(bids)
    print(f"{data['asof']} | week {data['week']} | swing {data['sd']} | ladder {len((data['ladder'] or {}).get('lo', []))}+"
          f"{len((data['ladder'] or {}).get('hi', []))} claims | $/win point {summary['budget']['dollars_per_win_point']} | "
          f"my cut risk {summary['me']['cut_risk_next_week']:.1%} | "
          f"{len(summary['bids'])} bid rows | changed: {', '.join(changed) or 'nothing'}")


if __name__ == "__main__":
    import sys
    print(repage()) if "--repage" in sys.argv else main()
