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
  (the weakest remaining bench player; Ball is Life, Nov 10: Austin Reaves).

Michael's fantasy rules (Drive: Claude Home/claude-audit/fantasy-rules.md, Nov 12; he rejected these moves
"what feels like 10 times"): every swap is one of three kinds, and nothing else is suggested.
- Dead roster spot: always.
- Upgrade (rules 1, 2, 4): the add is better for the rest of the season by UPGRADE_MARGIN value per game, and a drop
  with a real role (ROLE_MIN minutes, or minutes rising ROLE_RISE) is only swapped for an add who has one too.
  A drop whose minutes are rising is only swapped for an add whose minutes rise too. Dynasty leagues allow only this
  kind, with DYNASTY_MARGIN and an add no older than the drop (rest-of-career value) whose minutes aren't FALLING;
  a much younger add (DYNASTY_YOUNGER years) needs only DYNASTY_YOUNG_MARGIN. 3-Ball, Nov 12: Saddiq Bey (27, -2.4/g)
  for Paul Reed (27, -1.1/g) was a this-week stream, not a long-term upgrade.
- Stream (redraft only, rules 3 and 4): the this-week gain, and only when the drop is the single lowest-value player
  on the roster and has no real role. Ball is Life, Nov 12: Obi Toppin (21 min/g, rising) for Jordan Goodwin (18,
  falling). With no safe drop the answer is no swap ("take the zero").
- IR (rule 6): when a player sits in an IR slot ESPN won't allow and moving him forces a drop, the move is suggested
  only on a day he plays and with a drop that is the lowest-value player with no role; otherwise he stays in IR and,
  since ESPN blocks adds and drops until he moves, there are no swaps (Ajay Mitchell, Nov 12)."""
from .nba_values import by_id

WEIGHT = {"close": 1.5, "lose": 0.5, "win": 0.5, "tie": 1.0}
SEASON_SLACK = 1.0     # value per game an add may give up against the drop for a better week
MIN_GAIN = 3.0         # this-week gain worth a move
DYNASTY_KEEP = 40      # % rostered ESPN-wide: a dynasty player this owned isn't a drop
DYNASTY_YOUNG = 24     # ...nor one younger than this (a prospect; ages from shq/nba_ages.py)
MAX_SWAPS = 3
UPGRADE_MARGIN = 2.0   # value per game rest of season: an add clearly better than the drop (not a one-week stream)
DYNASTY_MARGIN = 2.0   # dynasty: clearly better, and no older than the drop
DYNASTY_YOUNGER = 3    # dynasty: an add this many years younger...
DYNASTY_YOUNG_MARGIN = 1.0   # ...needs only this edge per game
FALLING = -2.0         # minutes down this much lately: a shrinking role, never a dynasty add
ROLE_MIN = 20.0        # minutes per game: a real rotation role
ROLE_RISE = 2.0        # ...or minutes up this much lately (with at least ROLE_FLOOR)
ROLE_FLOOR = 15.0
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


def role(p):
    """A real rotation role: ROLE_MIN minutes a game, or minutes rising ROLE_RISE from at least ROLE_FLOOR."""
    m = p.get("min") or 0
    return m >= ROLE_MIN or (m >= ROLE_FLOOR and (p.get("dmin") or 0) >= ROLE_RISE)


def long_term(a, d):
    """Dynasty (rules 1, 2): the add has clearly more rest-of-career value than the drop. Ages unknown never pass."""
    if not a.get("age") or not d.get("age") or (a.get("dmin") or 0) <= FALLING:
        return False
    gap = a["v"] - d["v"]
    return (gap >= DYNASTY_MARGIN and a["age"] <= d["age"]) or (gap >= DYNASTY_YOUNG_MARGIN
                                                                and a["age"] <= d["age"] - DYNASTY_YOUNGER)


def kind(a, d, gain, dynasty, lowest):
    """'upgrade', 'stream' or None (not suggested) for adding a in place of my non-dead d."""
    if role(d) and not role(a):
        return None                      # rule 4: never cut a rotation player for one who has no role
    if (d.get("dmin") or 0) >= ROLE_RISE and (a.get("dmin") or 0) < ROLE_RISE:
        return None                      # his minutes are growing and the add's aren't: his season value lags his role
    if dynasty:
        return "upgrade" if long_term(a, d) else None
    if a["v"] >= d["v"] + UPGRADE_MARGIN:
        return "upgrade"
    if d is lowest and not role(d) and gain >= MIN_GAIN and a["v"] >= d["v"] - SEASON_SLACK:
        return "stream"
    return None


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
    live = [p for p in mine if not dead(p)]
    lowest = min(live, key=lambda p: p["v"], default=None)      # the only player a stream may cost (rule 4)
    pairs = []
    for d in drops:
        wd = 0.0 if dead(d) else worth(d, block, w, horizon)
        for a in adds:
            gain = worth(a, block, w, horizon) - wd
            k = "dead" if dead(d) else kind(a, d, gain, dynasty, lowest)
            if k:
                # dead spots first, then rest-of-season upgrades by value gap, then a stream by this week's gain
                pairs.append(({"dead": 0, "upgrade": 1, "stream": 2}[k], -(a["v"] - d["v"]) if k == "upgrade" else -gain,
                              d, a, gain, k))
    pairs.sort(key=lambda t: t[:2])
    swaps, used = [], set()
    for _, _, d, a, gain, k in pairs:
        if d["id"] in used or a["id"] in used:
            continue
        used |= {d["id"], a["id"]}
        swaps.append({"drop": d, "add": a, "gain": round(gain, 1), "helps": helps(block, a, d, cats), "dead": k == "dead",
                      "kind": k, "unkept": str(d["id"]) in unkept})
        if len(swaps) == MAX_SWAPS:
            break
    when = "this week" if horizon == 0 else "next week"
    blocked, room, hold = ir_first(league, drops, used)
    if hold:                               # rule 6: he stays in IR today, and ESPN blocks every add and drop meanwhile
        swaps, room = [], []
    lines = [line(s, when, dynasty) for s in swaps]
    if blocked and lines:
        lines[0] = first_line(blocked, room, lines[0])
    if hold:
        lines = [hold]
    return {"swaps": swaps, "dead": deads, "horizon": when, "blocked": blocked, "room": room, "hold": hold, "lines": lines
            + [f"{p['name']} has no NBA team: a dead roster spot. Drop him for any free agent below." for p in deads
               if not hold and not any(s["drop"] is p for s in swaps)],
            "basis": f"Gain = each player's value above a waiver-level player × games {when}, categories weighted by this "
                     "week's need (close ones most). Never gives up more than "
                     f"{SEASON_SLACK:g} value per game for the rest of the season; never drops a player the trend radar "
                     "shows rising on your bench unless it may fade or his value is well below the next drop; a day-to-day "
                     "player's next game counts at his chance to play it (ESPN probable 90%, questionable or no word 50%, "
                     "doubtful 25%); a swap is a clear rest-of-season upgrade "
                     f"(+{UPGRADE_MARGIN:g}/g) or, in redraft only, a stream that costs just your lowest-value player with no "
                     f"real role ({ROLE_MIN:g}+ min/g); never a rotation player for one without a role"
                     + (f"; dynasty: never drops anyone {DYNASTY_KEEP}%+ rostered on ESPN or under {DYNASTY_YOUNG}, never "
                        f"streams, and adds only a player at least {DYNASTY_MARGIN:g}/g better and no older" if dynasty else "")
                     + "."}


def ir_first(league, drops, used):
    """(names of my players stuck in an IR slot ESPN won't allow, the drop that makes room to move them to the bench
    when the roster is full, hold). The room drop is a dead spot, or else my lowest-value player the swaps don't
    already drop, and only if he has no real role (rule 4). hold is the line to show instead of any move (rule 6) when moving him forces a
    drop and he has no game today, or no drop is safe: he stays in IR, and ESPN blocks adds and drops until he moves."""
    ir = getattr(league, "ir_blocked", None) or []
    blocked = [p["name"] for p in ir]
    need = max(0, len(blocked) - (getattr(league, "open_spots", 0) or 0))
    if not blocked or not need:
        return blocked, [], None
    who = " and ".join(blocked)
    hold = (f"Leave {who} in IR for now: moving {'them' if len(blocked) > 1 else 'him'} out takes a drop with your "
            "roster full")
    if any(p.get("bye") for p in ir):
        return blocked, [], hold + (", and he has no game today. ESPN blocks adds and drops until he moves, so no "
                                    "pickups today; move him on a day he plays.")
    slot = {str(p["id"]): p.get("slot") for p in league.data["roster"]}
    left = [p for p in drops if p["id"] not in used]
    left.sort(key=lambda p: (not dead(p), p["v"], slot.get(str(p["id"])) != 12))   # dead spot, then weakest first
    if len(left) < need or any(role(p) and not dead(p) for p in left[:need]):
        return blocked, [], (hold + ", and every player you could drop has a real role. No pickups today (ESPN "
                             "blocks adds and drops until he moves); take the zero.")
    return blocked, left[:need], None


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
    official word is added when the NBA injury report or Sleeper decided it (Q-058)."""
    gd = (p.get("gd") or {}).get("t")
    today = f"; today: {gd[0].lower()}{gd[1:]}" if gd else ""
    if not p.get("inj"):
        return f", {gd[0].lower()}{gd[1:]}" if gd else ""
    play = p.get("play", 1.0)
    return (f", {str(p['inj']).replace('_', '-').lower()}" + (f" (ESPN: {p['word']})" if p.get("word") else "")
            + (f", next game counted at {play:.0%}" if play < 1 and p["g"][0] else "") + today)


def line(s, when, dynasty):
    if s.get("kind") == "upgrade":
        return upgrade_line(s, dynasty)
    d, a, g = s["drop"], s["add"], 0 if when == "this week" else 1
    why = "no NBA team, a dead roster spot" if s["dead"] else (
        f"{d['g'][g]} game{'s' if d['g'][g] != 1 else ''} {when}" + (status_text(d) if g == 0 else "") + f", value {d['v']:+.1f}/g")
    text = (f"Drop {d['name']} ({why}), add {a['name']} ({a['pos']}, {a['team']}, {a['g'][g]} game{'s' if a['g'][g] != 1 else ''} "
            f"{when}{status_text(a) if g == 0 else ''}, value {a['v']:+.1f}/g, {a['pct']:.0f}% rostered): +{s['gain']:.1f} {when}"
            + ("" if s["dead"] else f" over keeping {d['name']}"))
    if s["helps"]:
        text += f" (helps {', '.join(s['helps'])})"
    if s.get("kind") == "stream":
        text += f". {d['name']} is your lowest-value player and has no real role ({d.get('min') or 0:.0f} min/g)"
    if dynasty and not s["dead"] and d.get("age"):
        text += f". Dynasty: {d['name']} is {int(d['age'])}"   # whole years: 28.9 is 28
    return text + "."


def upgrade_line(s, dynasty):
    """'Drop X (value -2.4/g, 27 min/g, 31), add Y (PF, PHI, value +0.3/g, 24 min/g, 23, 12% rostered): +2.7/g for the
    rest of the season, 8 years younger.' The reason is rest-of-season (and in dynasty, age), never this week's games."""
    d, a = s["drop"], s["add"]
    age = lambda p: f", {int(p['age'])}" if dynasty and p.get("age") else ""
    mins = lambda p: f", {p.get('min') or 0:.0f} min/g"
    text = (f"Drop {d['name']} (value {d['v']:+.1f}/g{mins(d)}{age(d)}), add {a['name']} ({a['pos']}, {a['team']}, "
            f"value {a['v']:+.1f}/g{mins(a)}{age(a)}, {a['pct']:.0f}% rostered): +{a['v'] - d['v']:.1f}/g for the rest of "
            "the season")
    if dynasty and a.get("age") and d.get("age") and d["age"] - a["age"] >= 1:
        text += f", {int(d['age'] - a['age'])} years younger"
    if s["helps"]:
        text += f" (helps {', '.join(s['helps'])})"
    return text + "."
