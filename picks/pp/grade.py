"""Tuesday postmortem grading: the posted card picks and Michael's actual entries vs final scores.

Usage: py -m pp.grade --week NN
Reads data/published/2026-wNN-*.json (cards) and data/entries/2026-wNN.json (what he entered,
read from the pool sites by the run). Writes data/postmortem/2026-wNN.json (its existence marks the
week as graded) and prints a markdown summary for the history bullets.
"""
import argparse, glob, json, re
from pathlib import Path
from . import model as M
from .cards import YEAR, norm

ROOT = Path(__file__).resolve().parent.parent
PICK_RE = re.compile(r"^(?P<team>.+?)\s+(?P<line>[+-]\d+(?:\.\d+)?)")


def cfb_result(week, game):
    away, home = [x.strip() for x in game.replace("★", "").split(" @ ")]
    for g in M.games(YEAR):
        if g["week"] == week and {norm(g["awayTeam"]), norm(g["homeTeam"])} == {norm(away), norm(home)}:
            if not g.get("completed"):
                return None
            return {norm(g["homeTeam"]): g["homePoints"], norm(g["awayTeam"]): g["awayPoints"]}
    return None


def nfl_result(game):
    from .nfl import results
    results.cache_clear()
    away, home = [x.strip().upper() for x in game.replace("★", "").split(" @ ")]
    for h, a, m, _ in reversed(results()):
        if {h, a} == {home, away}:
            return {norm(h): m, norm(a): -m, "_margin": True}
    return None


def grade_pick(week, game, pick_text, ats):
    """Returns 1 win, 0 loss, 0.5 push, None if not final/unknown."""
    # All-caps could be NFL (KC) or college (LSU, BYU), so try college first.
    is_nfl = game.replace("★", "").split(" @ ")[0].strip().isupper()
    res = cfb_result(week, game) or (nfl_result(game) if is_nfl else None)
    if not res:
        return None
    if ats:
        m = PICK_RE.match(pick_text)
        if not m:
            return None
        team, line = norm(m["team"]), float(m["line"])
    else:
        team, line = norm(pick_text.replace(" (dog)", "")), 0.0
    opp = [k for k in res if k not in (team, "_margin")]
    if team not in res or not opp:
        return None
    margin = res[team] if res.get("_margin") else res[team] - res[opp[0]]
    x = margin + line
    return 1.0 if x > 0 else 0.5 if x == 0 else 0.0


def money(w):
    w = str(w).replace("$", "").replace(",", "").strip()
    try:
        return float(w)
    except ValueError:
        return 0.0


def grade_set(week, picks, ats):
    out, net, rec = [], 0.0, [0, 0, 0]
    for key, p in picks.items():
        game = p.get("game", key.replace("@", " @ "))
        r = grade_pick(week, game, p["pick"], ats)
        if r is not None:
            rec[0 if r == 1 else 1 if r == 0 else 2] += 1
            if ats:
                net += money(p.get("wager")) * (2 * r - 1)
        out.append({"key": key, "game": game, "pick": p["pick"], "wager": p.get("wager", ""), "result": r})
    return {"picks": out, "record": f"{rec[0]}-{rec[1]}" + (f"-{rec[2]}" if rec[2] else ""), "net": net}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    a = ap.parse_args()
    wk = a.week
    M.games.cache_clear()
    entries_f = ROOT / f"data/entries/{YEAR}-w{wk:02d}.json"
    entries = json.loads(entries_f.read_text(encoding="utf-8")) if entries_f.exists() else {}
    report = {"week": wk, "pools": {}, "entries_read": entries_f.exists(), "standings": entries.get("standings")}
    lines = [f"### CFBD week {wk} (Yahoo week {wk})"]
    files = {Path(f).stem.split("-")[-1]: Path(f) for f in glob.glob(str(ROOT / f"data/published/{YEAR}-w{wk:02d}-*.json"))}
    for pool in sorted(set(files) | {k for k in entries if k != "standings"}):
        ats = pool in ("bto", "cfp")
        card = json.loads(files[pool].read_text(encoding="utf-8")) if pool in files else {}
        card = {k: (v if isinstance(v, dict) else {"pick": v, "team": v}) for k, v in card.items()}
        cg = grade_set(wk, card, ats)
        mine = entries.get(pool)
        eg = grade_set(wk, mine, ats) if mine else None
        diffs = []
        if mine:
            for k, p in card.items():
                e = mine.get(k)
                if e and norm(PICK_RE.match(e["pick"])["team"] if ats and PICK_RE.match(e["pick"]) else e["pick"].replace(" (dog)", "")) != norm(p["team"]):
                    diffs.append({"key": k, "card": p["pick"], "entered": e["pick"],
                                  "card_result": grade_pick(wk, p.get("game", k), p["pick"], ats),
                                  "entry_result": grade_pick(wk, e.get("game", k.replace("@", " @ ")), e["pick"], ats)})
        report["pools"][pool] = {"card": cg, "entered": eg, "differences": diffs}
        lines.append(f"- **{pool}** card " + (cg["record"] if card else "none posted") + (f" (net {cg['net']:+,.0f})" if ats and card else "")
                     + (f"; entered {eg['record']}" + (f" (net {eg['net']:+,.0f})" if ats else "") if eg else "; entries not read")
                     + (f"; {len(diffs)} differences" if diffs else ""))
        for d in diffs:
            lines.append(f"  - {d['key']}: card {d['card']} ({d['card_result']}), entered {d['entered']} ({d['entry_result']})")
    out = ROOT / f"data/postmortem/{YEAR}-w{wk:02d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
