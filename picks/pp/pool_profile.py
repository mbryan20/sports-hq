"""How Michael's Yahoo group picks, from its own history, saved without names.

    py -m pp.pool_profile     rebuild data/pool_profile.json from .private/ (laptop only)

Inputs are private league data and stay in the gitignored picks/.private/ folder:
  grouppicks_2026.json  {week: {"g": "FAV,spread,DOG;...", "p": {member: "FFDF-..."}}} from the group's Group Picks
                        page (football.fantasysports.yahoo.com/college/3659/grouppicks?week=N, pg=2 for games 14-25)
  standings.json        {"me": "Michael B.", "points": {member: total}, "read": date} from the group page
The output (committed) holds only anonymous numbers: underdog-pick rates by spread, each other member's
lean relative to the group (as a multiplier), and the standings points."""
import json
from datetime import date

from .cards import ROOT

PRIVATE = ROOT / ".private"
OUT = ROOT / "data/pool_profile.json"
BUCKETS = ((0, 3), (3, 7), (7, 14), (14, 99))
SKIP = {"HG"}           # two inactive entries share this name and can't be told apart


def build(picks, standings):
    tot = {b: [0, 0] for b in BUCKETS}
    per = {}
    for v in picks.values():
        games = [g.split(",") for g in v["g"].split(";")]
        for name, s in v["p"].items():
            if name in SKIP:
                continue
            for (_, spread, _), c in zip(games, s):
                if c == "-":
                    continue
                b = next(b for b in BUCKETS if b[0] <= float(spread) < b[1])
                tot[b][0] += c == "D"
                tot[b][1] += 1
                per.setdefault(name, [0, 0])
                per[name][0] += c == "D"
                per[name][1] += 1
    # a spread range with no games yet falls back to roughly what this group did over its first 8 weeks
    default = dict(zip(BUCKETS, (0.39, 0.19, 0.05, 0.005)))
    rate = {b: tot[b][0] / tot[b][1] if tot[b][1] else default[b] for b in BUCKETS}
    # each member's lean: their dogs / the dogs an average member would have picked on the same games
    exp = {}
    for v in picks.values():
        games = [g.split(",") for g in v["g"].split(";")]
        for name, s in v["p"].items():
            if name in SKIP:
                continue
            for (_, spread, _), c in zip(games, s):
                if c != "-":
                    exp[name] = exp.get(name, 0.0) + rate[next(b for b in BUCKETS if b[0] <= float(spread) < b[1])]
    me = standings["me"]
    others = [n for n in standings["points"] if n != me and n not in SKIP]
    mult = lambda n: round(per[n][0] / exp[n], 2) if n in per and exp.get(n) and per[n][1] >= 50 else 1.0
    return {
        "updated": standings.get("read") or date.today().isoformat(),
        "weeks": sorted(int(w) for w in picks),
        "dog_rate_by_spread": [[lo, hi, round(rate[(lo, hi)], 3)] for lo, hi in BUCKETS],
        "spreads": sorted(float(g.split(",")[1]) for v in picks.values() for g in v["g"].split(";")),
        "me": {"points": standings["points"][me], "lean": mult(me)},
        "others": sorted(({"points": standings["points"][n], "lean": mult(n)} for n in others),
                         key=lambda o: -o["points"]),
        "note": "Anonymous: built from the group's own picks; names stay in picks/.private/ on the laptop.",
    }


if __name__ == "__main__":
    picks = json.loads((PRIVATE / "grouppicks_2026.json").read_text(encoding="utf-8"))
    standings = json.loads((PRIVATE / "standings.json").read_text(encoding="utf-8"))
    prof = build(picks, standings)
    OUT.write_text(json.dumps(prof, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(prof['others'])} other members, weeks {prof['weeks'][0]}-{prof['weeks'][-1]}")
