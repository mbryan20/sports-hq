"""NBA pickups as swaps: "Drop X, add Y: +N this week (helps AST, 3PM)". Pure logic, no AI; ideas only, nothing is sent.

Built on the player values (shq/nba_values.py) and this week's category table (shq/categories.py):
- A player's this-week worth is (his value per game - a waiver-level player's) x games left, the same "Wk" as the Players
  page, but with each category weighted by this week's need: close categories count most, ones already safe or out of
  reach count less (weights rescaled to average 1, so the numbers stay on the Players page's scale).
- A swap's gain is the add's worth minus the drop's. Once the week has no games left it uses next week's games.
- Never suggested: a drop from an IR slot (it frees no spot), an add who is out, a swap that costs more than SEASON_SLACK
  value per game for the rest of the season (one good week isn't worth a worse player), and in dynasty leagues a drop
  rostered on DYNASTY_KEEP% or more of ESPN leagues or younger than DYNASTY_YOUNG. A dead roster spot (no NBA team) always goes first.
- Never a drop either: a bench player of mine the trend radar shows rising, unless his rise "may fade"
  (league.radar["keep"], shq/radar.py, Q-047), and only while his value per game isn't more than KEEP_SLACK below the
  weakest player the swaps could drop instead (Ball is Life, Nov 10: a protected Ryan Dunn at -5.5/g made the swaps drop
  John Collins and Draymond Green). The radar would say start him while this said drop him; the weekly plan uses these
  same swaps.
- Nor a player today's Lineup moves start (build()'s starting ids, from shq/nba_lineup.py via advice.build; Q-047).
- A day-to-day player's next game counts at his chance to play it (nba_values "play": ESPN's note says probable 0.9,
  questionable 0.5, doubtful 0.25; no word 0.5), and the line names his status (3-Ball BB, Nov 10: Isaiah Stewart,
  questionable for Wednesday, showed as a clean 3 games).
- A player in an IR slot ESPN won't allow there (league.ir_blocked: healthy or day-to-day) blocks every add and drop,
  so the first line says to move him out first and, with the roster full, names the drop that makes room for him
  (the weakest remaining bench player; Ball is Life, Nov 10: Austin Reaves)."""
from .nba_values import by_id

WEIGHT = {"close": 1.5, "lose": 0.5, "win": 0.5, "tie": 1.0}
SEASON_SLACK = 1.0     # value per game an add may give up against the drop for a better week
MIN_GAIN = 3.0         # this-week gain worth a move
DYNASTY_KEEP = 40      # % rostered ESPN-wide: a dynasty player this owned isn't a drop
DYNASTY_YOUNG = 24     # ...nor one younger than this (a prospect; ages from shq/nba_ages.py)
MAX_SWAPS = 3
KEEP_SLACK = 1.0       # a rising bench player stays protected unless his value per game is this far below the next drop


def weights(block, cats):
    """{category name: weight} from this week's outlook; all 1 when there is no live matchup."""
    rows = {r["cat"]: r["outlook"] for r in (cats or {}).get("rows") or []}
    live = rows and any((cats or {}).get("games_left") or [0])
    raw = {c: WEIGHT.get(rows.get(c), 1.0) if live else 1.0 for c in block["cats"]}
    mean = sum(raw.values()) / len(raw)
    return {c: w / mean for c, w in raw.items()}


def worth(p, block, w, horizon):
    """Need-weighted value above a waiver-level player times games (this week, or next week once this one is done)."""
    if p.get("out") and horizon == 0:
        return 0.0
    v = sum(w[c] * z for c, z in zip(block["cats"], p["z"]))
    games = p["g"][horizon]
    if horizon == 0 and games:
        games -= 1 - p.get("play", 1.0)     # day-to-day: his next game counts at his chance to play it
    return (v - block["repl"]) * games


def dead(p):
    return not p.get("team") or p["team"] == "FA"


def helps(block, add, drop, cats):
    """Categories the swap improves most, the ones I need this week first (against nothing for a dead spot)."""
    need = {r["cat"] for r in (cats or {}).get("rows") or [] if r["outlook"] in ("close", "lose")}
    base = [0] * len(add["z"]) if dead(drop) else drop["z"]
    diff = [(c, a - d) for c, a, d in zip(block["cats"], add["z"], base)]
    up = sorted((x for x in diff if x[1] >= 0.4), key=lambda x: (x[0] not in need, -x[1]))
    return [c for c, _ in up[:3]]


def build(league, cats=None, starting=()):
    """{"swaps": [...], "dead": [...], "lines": [...]} for my roster in an NBA category league, or None without values.
    starting: ESPN ids of players today's Lineup moves start; none of them is a drop."""
    block = getattr(league, "values", None)
    if not block:
        return None
    w = weights(block, cats)
    ids = by_id(block)
    horizon = 0 if any(p["g"][0] for p in block["players"] if p["own"] == "me") else 1
    dynasty = bool(getattr(league, "dynasty", False))
    ir = {str(p["id"]) for p in league.data["roster"] if p.get("slot") == 13}
    mine = [ids[str(p["id"])] for p in league.data["roster"] if str(p["id"]) in ids and str(p["id"]) not in ir]
    deads = [p for p in mine if dead(p)]
    start = {str(x) for x in starting or ()}                                 # Lineup moves start him today
    rising = set((getattr(league, "radar", None) or {}).get("keep") or [])   # bench risers the radar shows, not "may fade"
    ok = lambda p: not dynasty or (p["pct"] < DYNASTY_KEEP and (p.get("age") or 99) >= DYNASTY_YOUNG)
    # a riser stays off the drop list only while his value isn't clearly below the weakest player it would cost instead
    others = [p["v"] for p in mine if not dead(p) and ok(p) and str(p["id"]) not in rising | start]
    floor = min(others, default=None)
    keep = start | {k for k in rising if k in ids and (floor is None or ids[k]["v"] >= floor - KEEP_SLACK)}
    unkept = {k for k in rising if k not in keep}
    drops = [p for p in mine if dead(p) or (str(p["id"]) not in keep and ok(p))]
    adds = [p for p in block["players"] if not p["own"] and not p.get("out") and not dead(p)]
    pairs = []
    for d in drops:
        wd = 0.0 if dead(d) else worth(d, block, w, horizon)
        for a in adds:
            gain = worth(a, block, w, horizon) - wd
            if not dead(d) and (gain < MIN_GAIN or a["v"] < d["v"] - SEASON_SLACK):
                continue
            pairs.append((not dead(d), -gain, d, a, gain))
    pairs.sort(key=lambda t: t[:2])
    swaps, used = [], set()
    for _, _, d, a, gain in pairs:
        if d["id"] in used or a["id"] in used:
            continue
        used |= {d["id"], a["id"]}
        swaps.append({"drop": d, "add": a, "gain": round(gain, 1), "helps": helps(block, a, d, cats), "dead": dead(d),
                      "unkept": str(d["id"]) in unkept})
        if len(swaps) == MAX_SWAPS:
            break
    when = "this week" if horizon == 0 else "next week"
    blocked, room = ir_first(league, drops, used)
    lines = [line(s, when, dynasty) for s in swaps]
    if blocked and lines:
        lines[0] = first_line(blocked, room, lines[0])
    return {"swaps": swaps, "dead": deads, "horizon": when, "blocked": blocked, "room": room, "lines": lines
            + [f"{p['name']} has no NBA team: a dead roster spot. Drop him for any free agent below." for p in deads
               if not any(s["drop"] is p for s in swaps)],
            "basis": f"Gain = each player's value above a waiver-level player × games {when}, categories weighted by this "
                     "week's need (close ones most). Never gives up more than "
                     f"{SEASON_SLACK:g} value per game for the rest of the season; never drops a player the trend radar "
                     "shows rising on your bench unless it may fade or his value is well below the next drop; a day-to-day "
                     "player's next game counts at his chance to play it (ESPN probable 90%, questionable or no word 50%, "
                     "doubtful 25%)"
                     + (f"; dynasty: never drops anyone {DYNASTY_KEEP}%+ rostered on ESPN or under {DYNASTY_YOUNG}" if dynasty else "")
                     + "."}


def ir_first(league, drops, used):
    """(names of my players stuck in an IR slot ESPN won't allow, the drop that makes room to move them to the bench
    when the roster is full). The room drop is the weakest bench player the swaps don't already drop."""
    blocked = [p["name"] for p in getattr(league, "ir_blocked", None) or []]
    need = max(0, len(blocked) - (getattr(league, "open_spots", 0) or 0))
    if not blocked or not need:
        return blocked, []
    slot = {str(p["id"]): p.get("slot") for p in league.data["roster"]}
    left = [p for p in drops if p["id"] not in used]
    left.sort(key=lambda p: (not dead(p), slot.get(str(p["id"])) != 12, p["v"]))   # dead spot, then bench, weakest first
    return blocked, left[:need]


def first_line(blocked, room, text):
    """'First move X out of IR (Fix now); ... then drop A, add B ...': ESPN blocks every add and drop until he's moved."""
    who = " and ".join(blocked)
    head = f"First move {who} out of IR (Fix now): ESPN blocks every add and drop until {'they are' if len(blocked) > 1 else 'he is'} on your bench"
    if room:
        head += (f"; your roster is full, so that takes a drop too: "
                 + " and ".join(f"{p['name']} (value {p['v']:+.1f}/g)" for p in room))
    return f"{head}; then {text[0].lower()}{text[1:]}"


def status_text(p):
    """'day-to-day (ESPN: questionable), next game counted at 50%' for an add or drop who isn't fully healthy; today's
    official word is added when the NBA injury report or Sleeper decided it (Q-057)."""
    gd = (p.get("gd") or {}).get("t")
    today = f"; today: {gd[0].lower()}{gd[1:]}" if gd else ""
    if not p.get("inj"):
        return f", {gd[0].lower()}{gd[1:]}" if gd else ""
    play = p.get("play", 1.0)
    return (f", {str(p['inj']).replace('_', '-').lower()}" + (f" (ESPN: {p['word']})" if p.get("word") else "")
            + (f", next game counted at {play:.0%}" if play < 1 and p["g"][0] else "") + today)


def line(s, when, dynasty):
    d, a, g = s["drop"], s["add"], 0 if when == "this week" else 1
    why = "no NBA team, a dead roster spot" if s["dead"] else (
        f"{d['g'][g]} game{'s' if d['g'][g] != 1 else ''} {when}" + (status_text(d) if g == 0 else "") + f", value {d['v']:+.1f}/g")
    text = (f"Drop {d['name']} ({why}), add {a['name']} ({a['pos']}, {a['team']}, {a['g'][g]} game{'s' if a['g'][g] != 1 else ''} "
            f"{when}{status_text(a) if g == 0 else ''}, value {a['v']:+.1f}/g, {a['pct']:.0f}% rostered): +{s['gain']:.1f} {when}"
            + ("" if s["dead"] else f" over keeping {d['name']}"))
    if s["helps"]:
        text += f" (helps {', '.join(s['helps'])})"
    if dynasty and not s["dead"] and d.get("age"):
        text += f". Dynasty: {d['name']} is {int(d['age'])}"   # whole years: 28.9 is 28
    return text + "."
