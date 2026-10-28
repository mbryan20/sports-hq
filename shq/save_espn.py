"""Laptop side of the private ESPN leagues.

    py -m shq.save_espn --js           print the JavaScript to run in a signed-in fantasy.espn.com tab
    py -m shq.save_espn <file.json>    validate what it returned, save state/espn/*.json, commit + push

The JavaScript returns compact league snapshots (see espn_fantasy.compact), including every other
team's roster for the trade finder. Commits only when a roster (yours or another team's), injury or
free-agent list changed, or the last snapshot is over 20h old."""
import datetime as dt
import json
import subprocess
import sys

from .common import ROOT, now_utc, parse_iso
from .config import ESPN_PRIVATE
from .espn_fantasy import GAME, LAPTOP_SNAPSHOT_JS, SNAPSHOTS, load_snapshot
from .values import ESPN_STATS


def js():
    specs = [[c["sport"], GAME[c["sport"]], c["season"], c["league_id"], c["team_id"]] for c in ESPN_PRIVATE]
    return LAPTOP_SNAPSHOT_JS.replace("__SPECS__", json.dumps(specs)).replace("__STATS__", json.dumps(ESPN_STATS))


def validate(snap):
    if snap.get("error"):
        raise ValueError(f"{snap.get('sport')} {snap.get('league_id')}: {snap['error']}")
    want = {(c["sport"], c["league_id"]): c for c in ESPN_PRIVATE}
    cfg = want.get((snap.get("sport"), snap.get("league_id")))
    if not cfg:
        raise ValueError(f"unexpected league {snap.get('sport')} {snap.get('league_id')}")
    if len(snap.get("roster") or []) < 8 or not (snap.get("team") or {}).get("name"):
        raise ValueError(f"{cfg['name']}: roster looks incomplete ({len(snap.get('roster') or [])} players)")
    return cfg


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def main(path):
    snaps = json.loads(open(path, encoding="utf-8").read())
    if isinstance(snaps, str):  # the browser tool sometimes hands back the JSON string itself
        snaps = json.loads(snaps)
    errors, changed = [], []
    for snap in snaps:
        try:
            cfg = validate(snap)
        except ValueError as e:
            errors.append(str(e))
            continue
        prev = load_snapshot(snap["sport"], snap["league_id"]) or {}
        same = all(prev.get(k) == snap.get(k) for k in ("roster", "free_agents", "scoring_period", "opponent", "teams"))
        fresh = prev.get("captured") and now_utc() - parse_iso(prev["captured"]) < dt.timedelta(hours=20)
        if same and fresh:
            continue
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        (SNAPSHOTS / f"{snap['sport']}-{snap['league_id']}.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
        changed.append(cfg["name"])
    if changed:
        git("pull", "-q", "--no-rebase", "--no-edit")
        git("add", str(SNAPSHOTS.relative_to(ROOT)))
        git("commit", "-q", "-m", "ESPN snapshot: " + ", ".join(changed))
        git("push", "-q")
    print(f"Saved: {', '.join(changed) or 'nothing changed'}." + (f" Problems: {'; '.join(errors)}" if errors else ""))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    print(js()) if sys.argv[1:] == ["--js"] else main(sys.argv[1])
