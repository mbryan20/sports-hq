"""Laptop side of the private ESPN leagues.

    py -m shq.save_espn --js           print the JavaScript to run in a signed-in fantasy.espn.com tab
    py -m shq.save_espn <file.json>    validate what it returned, save state/espn/*.json, commit + push
    py -m shq.save_espn --parts FULL_SHA SHA0 SHA1 ...
                                       join .cache/espn_part<k>.txt (gzip+base64 chunks read from the tab),
                                       check every hash, then save as above

Claude in Chrome cuts javascript_tool results off at ~1,000 characters and the snapshot is ~109 KB, so
the laptop task gzips + base64s it in the page (~24 KB) and reads it back in 15,000-character chunks.

The JavaScript returns compact league snapshots (see espn_fantasy.compact), including every other
team's roster for the trade finder; NBA category leagues also carry this week's category totals.
Commits only when a roster (yours or another team's), injury, free-agent list or category total
changed, or the last snapshot is over 20h old."""
import base64
import datetime as dt
import gzip
import hashlib
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
    m = snap.get("matchup")
    if m is not None and not (m.get("cats") and isinstance(m.get("mine"), dict) and isinstance(m.get("opp"), dict)
                              and m.get("my_roster") and m.get("opp_roster")):
        raise ValueError(f"{cfg['name']}: category matchup looks incomplete")
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
        same = all(prev.get(k) == snap.get(k) for k in ("roster", "free_agents", "scoring_period", "opponent", "teams", "matchup"))
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


def join_parts(full_sha, chunk_shas, folder=ROOT / ".cache"):
    """Rebuild the snapshot JSON from the chunk files; raises ValueError on any hash mismatch."""
    chunks = []
    for k, want in enumerate(chunk_shas):
        part = "".join(open(folder / f"espn_part{k}.txt", encoding="utf-8").read().split())
        if hashlib.sha256(part.encode()).hexdigest() != want:
            raise ValueError(f"chunk {k} hash mismatch: re-read espn_part{k}.txt from the tab")
        chunks.append(part)
    text = gzip.decompress(base64.b64decode("".join(chunks))).decode("utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != full_sha:
        raise ValueError("full snapshot hash mismatch after joining")
    out = folder / "espn_snapshot.json"
    out.write_text(text, encoding="utf-8")
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["--js"]:
        print(js())
    elif sys.argv[1:2] == ["--parts"]:
        try:
            path = join_parts(sys.argv[2], sys.argv[3:])
        except ValueError as e:
            sys.exit(f"Problems: {e}")
        main(path)
    else:
        main(sys.argv[1])
