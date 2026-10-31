"""3-Ball dynasty assets: my future draft picks and minor leaguers, from a copy of the league's Google Sheet.

The sheet is the league's private data and this repo is public, so the full copy (state/dynasty_sheet.json: the
"Updated Draft Picks" grid and the minor-league spots, read with the Sheets connector) stays on the laptop,
gitignored. `py -m shq.dynasty --export` writes only my own holdings to state/dynasty_assets.json, which the cloud
reads. In the pick grid each owner has four rows (1st-4th round) and one column per draft ("27 NFL"); a cell is
"<n> Rd" while the owner still holds the pick, or the name of whoever holds it now."""
import datetime as dt
import json
import sys

from .common import STATE, load_json

SHEET = STATE / "dynasty_sheet.json"      # laptop only (gitignored)
ASSETS = STATE / "dynasty_assets.json"    # my holdings only (committed)
SPORT = {"nfl": "NFL", "nba": "NBA", "mlb": "MLB"}
ROUNDS = ("1st", "2nd", "3rd", "4th")


def holdings(sheet, now):
    """{(year, sport): {"mine": [(round, via or None)], "lost": [(round, to)]}} for drafts still ahead.
    A draft counts as ahead until about six months before its year starts being past (Oct 2026 shows 2027+)."""
    me, grid = sheet["me"], sheet["picks"]
    first = (now + dt.timedelta(days=182)).year % 100
    cols = [(c, *h.split()) for c, h in enumerate(grid[0]) if c and h]
    out, owner, rnd = {}, None, 0
    for row in grid[1:]:
        if not any(x.strip() for x in row):
            continue
        if row[0].strip():
            owner, rnd = row[0].strip(), 0
        rnd += 1
        for c, yy, sport in cols:
            if int(yy) < first or c >= len(row):
                continue
            cell = row[c].strip()
            slot = out.setdefault((2000 + int(yy), sport), {"mine": [], "lost": []})
            kept = cell.endswith("Rd")
            if owner == me and kept:
                slot["mine"].append((rnd, None))
            elif owner == me:
                slot["lost"].append((rnd, cell))
            elif cell == me:
                slot["mine"].append((rnd, owner))
    return out


def minors(sheet):
    head = sheet["minors"][0]
    col = head.index(sheet["me"])
    return [r[col].strip() for r in sheet["minors"][1:] if col < len(r) and r[col].strip()]


def _line(year, sport, h):
    mine = ", ".join(ROUNDS[r - 1] + (f" (via {via})" if via else "") for r, via in sorted(h["mine"]))
    lost = "; ".join(f"your {ROUNDS[r - 1]} went to {to}" for r, to in sorted(h["lost"]))
    return f"{year} {sport}: {mine or 'none'}" + (f" ({lost})" if lost else "")


def export(sheet, now):
    """My holdings only: what the public repo and site may carry."""
    return {"me": sheet["me"], "read": sheet["read"], "picks_updated": sheet["picks_updated"],
            "minors_updated": sheet["minors_updated"],
            "picks": [{"year": y, "sport": s, **h} for (y, s), h in sorted(holdings(sheet, now).items())],
            "minors": minors(sheet)}


def block(sport, now, assets=None):
    """What to do card section for a 3-Ball league: this sport's picks first, then the other sports and the
    minor leaguers. None until the laptop has exported my holdings."""
    assets = assets or load_json(ASSETS)
    if not assets:
        return None
    first_year = (now + dt.timedelta(days=182)).year
    h = {(p["year"], p["sport"]): p for p in assets["picks"] if p["year"] >= first_year}
    first = SPORT[sport]
    keys = sorted(h, key=lambda k: (k[1] != first, k[1], k[0]))
    return {"lines": [_line(y, s, h[(y, s)]) for y, s in keys] + [f"Minor leaguers: {', '.join(assets['minors'])}"],
            "source": f"3-Ball league sheet: picks updated {assets['picks_updated']}, minors log through "
                      f"{assets['minors_updated']}; read {assets['read']}"}


if __name__ == "__main__":
    if sys.argv[1:] == ["--export"]:
        out = export(load_json(SHEET), dt.datetime.now(dt.timezone.utc))
        ASSETS.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {ASSETS.name}: {len(out['picks'])} drafts, {len(out['minors'])} minor leaguers")
