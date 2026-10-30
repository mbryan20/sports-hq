"""3-Ball dynasty assets: my future draft picks and minor leaguers, from a copy of the league's Google Sheet.

The sheet isn't public, so state/dynasty_sheet.json holds the "Updated Draft Picks" grid and the minor-league
spots as read with the Sheets connector (the monthly review re-reads it). In the pick grid each owner has four
rows (1st-4th round) and one column per draft ("27 NFL"); a cell is "<n> Rd" while the owner still holds the
pick, or the name of whoever holds it now."""
import datetime as dt

from .common import STATE, load_json

SHEET = STATE / "dynasty_sheet.json"
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


def block(sport, now, sheet=None):
    """What to do card section for a 3-Ball league: this sport's picks first, then the other sports and the
    minor leaguers. None when the sheet copy is missing."""
    sheet = sheet or load_json(SHEET)
    if not sheet:
        return None
    h = holdings(sheet, now)
    first = SPORT[sport]
    keys = sorted(h, key=lambda k: (k[1] != first, k[1], k[0]))
    return {"lines": [_line(y, s, h[(y, s)]) for y, s in keys] + [f"Minor leaguers: {', '.join(minors(sheet))}"],
            "source": f"League sheet: picks updated {sheet['picks_updated']}, minors log through {sheet['minors_updated']}; "
                      f"copied {sheet['read']}",
            "url": sheet["url"]}
