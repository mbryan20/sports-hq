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


def main():
    data = build(now_utc())
    blob = json.dumps(data, separators=(",", ":"), sort_keys=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write(blob)
    try:
        bids = subprocess.run([os.environ.get("NODE", "node"), str(HERE / "export.js"), tmp.name],
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout
    finally:
        os.unlink(tmp.name)
    page = ((HERE / "app_template.html").read_text(encoding="utf-8")
            .replace("__DATA__", blob.replace("</", r"<\/"))
            .replace("__MODEL__", (HERE / "model.js").read_text(encoding="utf-8"))
            .replace("__JS__", (HERE / "app.js").read_text(encoding="utf-8")))
    changed = [name for name, text in (("index.html", page), ("bids.json", bids)) if write_if_changed(OUT / name, text)]
    summary = json.loads(bids)
    print(f"{data['asof']} | week {data['week']} | my cut risk {summary['me']['cut_risk_next_week']:.1%} | "
          f"{len(summary['bids'])} bid rows | changed: {', '.join(changed) or 'nothing'}")


if __name__ == "__main__":
    main()
