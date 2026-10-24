"""Save the Kosmonauts roster read off the Yahoo website and push it to GitHub.

Run by the laptop's scheduled task while Yahoo's API is gated:
    py -m shq.save_roster <file>
<file> holds one player per line, pipe-separated: slot|name|yahoo_id|team|pos|status
(the output of the extraction snippet in the task prompt). Validates before writing, and only
commits when the roster actually changed (or the last capture is >20h old, to refresh staleness)."""
import datetime as dt
import subprocess
import sys

from .common import ROOT, iso, load_json, now_utc, parse_iso, save_json
from .run import SAVED_ROSTER

SLOTS = {"QB", "RB", "WR", "TE", "K", "DEF", "BN", "IR", "IR+", "W/R/T"}


def parse(text):
    players = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 6:
            raise ValueError(f"bad line: {line!r}")
        slot, name, yid, team, pos, status = parts
        if slot not in SLOTS or not name or not yid.isdigit():
            raise ValueError(f"bad line: {line!r}")
        players.append({"slot": slot, "name": name, "yahoo_id": yid, "key": None, "team": team.upper(),
                        "pos": pos, "eligible": [pos] if pos else [], "status": status or None})
    starters = [p for p in players if p["slot"] not in ("BN", "IR", "IR+")]
    if len(starters) < 6 or not any(p["slot"] == "QB" for p in starters):
        raise ValueError(f"only {len(starters)} starters parsed; page layout may have changed")
    return players


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main(path):
    players = parse(open(path, encoding="utf-8").read())
    prev = load_json(SAVED_ROSTER) or {}
    fresh_enough = prev.get("captured") and now_utc() - parse_iso(prev["captured"]) < dt.timedelta(hours=20)
    if prev.get("players") == players and fresh_enough:
        print("Roster unchanged; nothing to commit.")
        return
    git("pull", "-q", "--rebase")
    save_json(SAVED_ROSTER, {"captured": iso(now_utc()), "players": players})
    git("add", str(SAVED_ROSTER.relative_to(ROOT)))
    git("commit", "-q", "-m", "Kosmonauts roster sync from Yahoo website")
    git("push", "-q")
    print(f"Saved {len(players)} players and pushed.")


if __name__ == "__main__":
    main(sys.argv[1])
