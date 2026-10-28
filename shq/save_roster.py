"""Save the Kosmonauts roster read off the Yahoo website and push it to GitHub.

Run by the laptop's scheduled task while Yahoo's API is gated:
    py -m shq.save_roster <file>
<file> holds one player per line, pipe-separated: slot|name|yahoo_id|team|pos|status
(the output of the extraction snippets in the task prompt). Roster lines come first; lines with
slot FA are the top available players per position from the league's player list. Validates before
writing, and only commits when something changed (or the last capture is >20h old, to refresh
staleness). A file without FA lines keeps the previously saved free agents."""
import datetime as dt
import subprocess
import sys

from .common import ROOT, iso, load_json, now_utc, parse_iso, save_json
from .run import SAVED_ROSTER

SLOTS = {"QB", "RB", "WR", "TE", "K", "DEF", "BN", "IR", "IR+", "W/R/T", "FA"}
FA_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def _lines(text):
    out = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 6:
            raise ValueError(f"bad line: {line!r}")
        slot, name, yid, team, pos, status = parts
        if slot not in SLOTS or not name or not yid.isdigit():
            raise ValueError(f"bad line: {line!r}")
        out.append({"slot": slot, "name": name, "yahoo_id": yid, "key": None, "team": team.upper(),
                    "pos": pos, "eligible": [pos] if pos else [], "status": status or None})
    return out


def parse(text):
    """The roster lines (FA lines are skipped)."""
    players = [p for p in _lines(text) if p["slot"] != "FA"]
    starters = [p for p in players if p["slot"] not in ("BN", "IR", "IR+")]
    if len(starters) < 6 or not any(p["slot"] == "QB" for p in starters):
        raise ValueError(f"only {len(starters)} starters parsed; page layout may have changed")
    return players


def parse_free_agents(text):
    """The FA lines, or None when there are none (the FA read was skipped or failed)."""
    fas = [p for p in _lines(text) if p["slot"] == "FA"]
    if not fas:
        return None
    if any(p["pos"] not in FA_POSITIONS for p in fas):
        raise ValueError(f"unexpected FA position: {next(p for p in fas if p['pos'] not in FA_POSITIONS)}")
    positions = {p["pos"] for p in fas}
    if len(positions) < 4 or len(fas) < 20:
        raise ValueError(f"only {len(fas)} free agents at {len(positions)} positions; page layout may have changed")
    seen, out = set(), []
    for p in fas:
        if p["yahoo_id"] not in seen:
            seen.add(p["yahoo_id"])
            out.append(p)
    return out


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main(path):
    text = open(path, encoding="utf-8").read()
    players, fas = parse(text), parse_free_agents(text)
    prev = load_json(SAVED_ROSTER) or {}
    fresh_enough = prev.get("captured") and now_utc() - parse_iso(prev["captured"]) < dt.timedelta(hours=20)
    if prev.get("players") == players and fas in (None, prev.get("free_agents")) and fresh_enough:
        print("Roster and free agents unchanged; nothing to commit.")
        return
    git("pull", "-q", "--no-rebase", "--no-edit")
    data = {"captured": iso(now_utc()), "players": players}
    if fas is not None:
        data.update(free_agents=fas, fa_captured=data["captured"])
    elif prev.get("free_agents"):
        data.update(free_agents=prev["free_agents"], fa_captured=prev.get("fa_captured"))
    save_json(SAVED_ROSTER, data)
    git("add", str(SAVED_ROSTER.relative_to(ROOT)))
    git("commit", "-q", "-m", "Kosmonauts roster sync from Yahoo website")
    git("push", "-q")
    print(f"Saved {len(players)} players" + (f" and {len(fas)} free agents" if fas else " (no free agents read)")
          + " and pushed.")


if __name__ == "__main__":
    main(sys.argv[1])
