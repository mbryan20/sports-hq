"""The phone push: Michael's saved picks vs the card, decisions-log departures, then one line per pool due
before the next run. The push alone must be enough to act on without opening the page.

Inputs: data/cards.json (the card) and slates/<year>-wNN.json, where the laptop run stores what it read:
  <pool>.saved = {"read": iso, "bets": [{"key": "Away@Home", "pick": "<Team> <line incl. LP>", "wager": 1300}]}   (bto, cfp)
  yahoo.saved  = {"read": iso, "picks": {"Away@Home": "<Team>"}, "tb1": {"Away@Home": "<Away> 17, <Home> 20"},
                  "tb2": {"most": "<Team>", "fewest": "<Team>"}}
  <pool>.saved = {"unread": "<why, e.g. signed out>"} when the site couldn't be read
  decisions    = {"read": iso, "differs": [{"date": "Oct 23", "old": "...", "new": "...", "because": "..."}]}
                 or {"unread": "<why>"} when the Decisions log Google Doc couldn't be read
  survivor_note = "<one line>" only when a newer pool email says Michael is still alive

Usage: py -m pp.push [--week NN] [--due bto,cfp,yahoo]   (prints the push; pp.publish sends it)
"""
import argparse, json, re, subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .names import norm

ROOT = Path(__file__).resolve().parent.parent
PAGE = "https://mbryan20.github.io/sports-hq/picks/"
CT = ZoneInfo("America/Chicago")
YEAR = 2026
PICK_RE = re.compile(r"^(?P<team>.+?)\s+(?P<line>[+-]\d+(?:\.\d+)?)")
LOCKS = {"bto": "locks Fri 8pm", "cfp": "locks Sat 11am"}
LABEL = {"bto": "BTO", "cfp": "CFP", "yahoo": "Yahoo"}
# which pools each run's push covers (the pools due before the next run)
DUE = {2: ("bto", "cfp", "yahoo"), 3: ("bto", "cfp", "yahoo"), 4: ("cfp", "yahoo"), 5: ("cfp", "yahoo"), 6: ("cfp", "yahoo")}  # Fri run is after BTO's 8pm lock


def money(x):
    return int(re.sub(r"[^\d]", "", str(x)) or 0)


def parse_pick(text):
    """'MIN +7.5 (LP 4)' -> ('min', 7.5). Lines include any line points."""
    m = PICK_RE.match(str(text).replace(" (dog)", ""))
    return (norm(m["team"]), float(m["line"])) if m else (norm(str(text)), None)


def fmt_wager(pid, w):
    return f"${money(w):,}" if pid == "bto" else f"{money(w):,}"


def _scores(text):
    """'Wisconsin 13, Iowa 23' -> {'wisconsin': 13, 'iowa': 23}"""
    return {norm(t.strip()): int(s) for t, s in re.findall(r"([^,]+?)\s+(\d+)(?:,|$)", str(text))}


def _kick_dt(kick):
    """Yahoo kicks look like 'Sat 10/31 2:30 PM' (CT)."""
    m = re.search(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*([AP]M)", str(kick or ""))
    if not m:
        return None
    h = int(m[3]) % 12 + (12 if m[5] == "PM" else 0)
    return datetime(YEAR, int(m[1]), int(m[2]), h, int(m[4]), tzinfo=CT)


def _kick_passed(kick, now):
    """A game already under way can't be changed, so it's never a CHANGE."""
    when = _kick_dt(kick)
    return bool(when and when <= now)


def yahoo_tb(card):
    """TB picks from the card's tiebreaker lines: ({'Away @ Home': 'A 13, H 23'}, most, fewest)."""
    tb1, most, fewest = {}, None, None
    for t in card.get("tiebreakers", []):
        if m := re.match(r"TB1 (.+?): <b>(.+?)</b>", t):
            tb1[m[1]] = m[2]
        elif m := re.match(r"TB2 most points: <b>(.+?)</b>", t):
            most = m[1]
        elif m := re.match(r"TB2 fewest points: <b>(.+?)</b>", t):
            fewest = m[1]
    return tb1, most, fewest


def compare_ats(card, saved):
    """BTO/CFP: the bets are one package (wagers depend on each other), so any difference is one CHANGE line.
    Returns (status, change_line) with status 'unread' | 'empty' | 'match' | 'differ'."""
    if not saved or saved.get("unread"):
        return "unread", None
    if not card["rows"]:  # no card picks yet (slate not read): nothing to compare
        return "nocard", None
    bets = saved.get("bets") or []
    if not bets:
        return "empty", None
    mine = {b["key"]: (*parse_pick(b["pick"]), money(b["wager"])) for b in bets}
    card_b = {r["key"]: (*parse_pick(r["pick"]), money(r["wager"])) for r in card["rows"]}
    if mine == card_b:
        return "match", None
    new = [r for r in card["rows"] if mine.get(r["key"]) != card_b[r["key"]]]
    reason = new[0]["why"] if new else "card drops some of your bets"
    if card.get("saved_vs"):
        reason += f"; {card['saved_vs']}"
    yours = "; ".join(f"{b['pick']} {fmt_wager(card['id'], b['wager'])}" for b in bets)
    ours = "; ".join(f"{r['pick']} {r['wager']}" for r in card["rows"])
    return "differ", f"CHANGE: {LABEL[card['id']]}: yours {yours} → card {ours} ({reason})"


def compare_yahoo(card, saved, slate_games, now):
    """Per game and per tiebreaker. Returns (status, change_lines, unsaved_labels)."""
    if not saved or saved.get("unread"):
        return "unread", [], []
    picks = saved.get("picks") or {}
    kicks = {f"{g['away']}@{g['home']}": g.get("kick") for g in slate_games}
    lines, unsaved = [], []
    for r in card["rows"]:
        if _kick_passed(kicks.get(r["key"]) or r.get("kick"), now):
            continue
        mine = picks.get(r["key"])
        if not mine:
            unsaved.append(r["game"])
        elif norm(mine) != norm(r["pick_team"]):
            lines.append(f"CHANGE: Yahoo: yours {mine} → card {r['pick_team']} ({r['why']})")
    tb1, most, fewest = yahoo_tb(card)
    saved_tb1 = {k.replace("@", " @ "): v for k, v in (saved.get("tb1") or {}).items()}
    for game, pick in tb1.items():
        if _kick_passed(kicks.get(game.replace(" @ ", "@")), now):
            continue
        mine = saved_tb1.get(game)
        if not mine:
            unsaved.append(f"TB1 {game}")
        elif _scores(mine) != _scores(pick):
            lines.append(f"CHANGE: Yahoo TB1 {game}: yours {mine} → card {pick}")
    tb2 = saved.get("tb2") or {}
    first = min((d for d in map(_kick_dt, kicks.values()) if d), default=None)
    if not (first and first <= now):  # TB2 locks before the week's first game
        for side, pick in (("most", most), ("fewest", fewest)):
            if pick and not tb2.get(side):
                unsaved.append(f"TB2 {side}")
            elif pick and norm(tb2[side]) != norm(pick):
                lines.append(f"CHANGE: Yahoo TB2 {side}: yours {tb2[side]} → card {pick}")
    status = "differ" if lines or unsaved else "match"
    return status, lines, unsaved


def early_lock(card, saved, games, now):
    """BTO games lock at kickoff, so a package touching a Thursday game must be edited before that kickoff,
    not by the Friday deadline (Nov 4: Michael's saved JAX bet locked Thu 7:15pm)."""
    if card["id"] != "bto":
        return ""
    keys = {r["key"] for r in card["rows"]} | {b["key"] for b in (saved or {}).get("bets") or []}
    kicks = [(_kick_dt(g.get("kick")), g) for g in games if f"{g['away']}@{g['home']}" in keys and not g.get("locked")]
    if now.weekday() > 4:
        return ""  # Sat/Sun: this week's Friday deadline has passed
    deadline = (now + timedelta(days=4 - now.weekday())).replace(hour=20, minute=0, second=0, microsecond=0)  # Fri 8pm
    kicks = [(k, g) for k, g in kicks if k and now < k < deadline]
    if not kicks:
        return ""
    k, g = min(kicks, key=lambda x: x[0])
    return f". Edit by {k:%a} {k.hour % 12 or 12}:{k:%M}{'pm' if k.hour >= 12 else 'am'} ({g['away']}@{g['home']} locks then)"


def pool_line(card, status, unsaved=()):
    pid = card["id"]
    head = f"{LABEL[pid]} ({LOCKS[pid]})" if pid in LOCKS else LABEL[pid]
    if card.get("status") and not card["rows"]:
        return f"{head}: {card['status']}"
    if status == "match":
        return f"{head}: your saved picks match"
    if pid in ("bto", "cfp"):
        txt = "; ".join(f"{r['pick']} {r['wager']}" for r in card["rows"])
        return f"{head}: {txt}" + (" (nothing saved yet)" if status == "empty" else "")
    tb1, most, fewest = yahoo_tb(card)
    close = [r for r in card["rows"] if (r.get("market") or r.get("model") or 1) < 0.6 or "(dog)" in r["pick"]]
    parts = [f"{len(card['rows'])} set"]
    if close:
        parts.append("close calls: " + ", ".join(f"{r['game'].replace(' @ ', '@')}: {r['pick']}" for r in close[:6]))
    if tb1:
        parts.append("TB1 " + "; ".join(tb1.values()))
    if most:
        parts.append(f"TB2 most {most}, fewest {fewest}")
    if unsaved:
        parts.append(f"not saved yet: {', '.join(unsaved[:6])}" + (f" +{len(unsaved) - 6}" if len(unsaved) > 6 else ""))
    return f"{head}: " + "; ".join(parts)


def ats_locked(pid, now):
    """BTO locks Fri 8pm CT; after that (Fri night final, Sat refresh) a card-vs-saved difference can't be acted on,
    so it isn't a CHANGE line (Nov 6: the Fri 9pm final re-showed Thursday's BTO card after the lock)."""
    return pid == "bto" and (now.weekday() in (5, 6) or (now.weekday() == 4 and now.hour >= 20))


def compose(cards, slate, due=None, now=None, final_call=False):
    """-> (alerts, lines). alerts = CHANGE / Differs lines (also shown at the top of the page).
    final_call: the last run before a lock (Thu, Fri, Sat), where anything unsaved is itself a CHANGE."""
    now = now or datetime.now(CT)
    due = due or DUE.get(now.weekday(), ("bto", "cfp", "yahoo"))
    alerts, body = [], []
    order = {"bto": 0, "cfp": 1, "yahoo": 2}
    for c in sorted(cards, key=lambda c: order.get(c["id"], 9)):
        pid = c["id"]
        if pid not in LABEL:
            continue
        saved = (slate.get(pid) or {}).get("saved")
        if pid == "yahoo":
            status, ch, unsaved = compare_yahoo(c, saved, (slate.get("yahoo") or {}).get("games") or [], now)
            alerts += ch
            if unsaved and final_call and pid in due:
                alerts.append(f"CHANGE: Yahoo: not saved yet: {', '.join(unsaved[:8])}")
        else:
            status, ch = compare_ats(c, saved)
            unsaved = []
            if ch and not ats_locked(pid, now):
                alerts.append(ch + early_lock(c, saved, (slate.get(pid) or {}).get("games") or [], now))
        if pid in due:
            line = pool_line(c, status, unsaved)
            if status == "unread" and c["rows"]:
                line += f" (saved picks not read: {(saved or {}).get('unread') or 'not read this run'})"
            body.append(line)
    dec = slate.get("decisions") or {}
    for d in dec.get("differs") or []:
        alerts.append(f"Differs from your decision on {d['date']}: {d['old']} → {d['new']}, because {d['because']}")
    if dec.get("unread"):
        body.insert(0, f"Decisions log not read ({dec['unread']}); departures from your decisions not checked")
    if slate.get("survivor_note"):
        body.append(f"Survivor: {slate['survivor_note']}")
    return alerts, body


def prev_card(meta, git=None):
    """The last committed card before this one (another generated time, same week), or None. Used for the push's
    'Changed since <time>:' lead (Nov 12: Michael wanted every redraft to say what moved and why)."""
    def run(*a):
        return subprocess.run(("git",) + a, cwd=ROOT.parent, capture_output=True, text=True, encoding="utf-8").stdout
    git = git or run
    for sha in git("log", "-n", "12", "--format=%H", "--", "picks/data/cards.json").split():
        try:
            doc = json.loads(git("show", f"{sha}:picks/data/cards.json"))
        except ValueError:
            continue
        m = doc.get("meta") or {}
        if m.get("generated_iso") != meta.get("generated_iso"):
            return doc if m.get("week") == meta.get("week") else None
    return None


SINCE_FIELDS = {"pick", "line", "wager", "added", "dropped"}


def since_lines(cards, prev):
    """'Changed since Wed Nov 11, 09:33 PM CT:' then one line per changed pick/line/wager, per pool, with the new
    card's reason; or one line saying nothing changed. [] without a previous card."""
    if not prev:
        return []
    from .history import extract, diff_pool
    old = extract(prev)
    new = extract({"cards": cards})
    why = {(c["id"], r.get("key")): r.get("why") or "" for c in cards for r in c.get("rows") or []}
    def bet(r):
        return f"{r['game']} {r['pick']}" + (f" {r['wager']}" if r.get("wager") else "")

    out = []
    for pid in ("bto", "cfp", "yahoo"):
        if pid not in new:
            continue
        diffs = [d for d in diff_pool(old.get(pid), new[pid], pid) if SINCE_FIELDS & set(d["fields"])]
        added = [d for d in diffs if "added" in d["fields"]]
        dropped = [d for d in diffs if "dropped" in d["fields"]]
        if added and dropped:  # the ATS package moved to other games: one line, old bets -> new bets
            o = "; ".join(bet(old[pid]["rows"][d["key"]]) for d in dropped)
            n = "; ".join(bet(new[pid]["rows"][d["key"]]) for d in added)
            w = "; ".join(filter(None, (why.get((pid, d["key"])) for d in added)))
            out.append(f"{LABEL[pid]}: {o} → {n}" + (f" ({w})" if w else ""))
            diffs = [d for d in diffs if d not in added and d not in dropped]
        for d in diffs:
            w = why.get((pid, d["key"])) if {"pick", "line", "added"} & set(d["fields"]) else ""
            text = re.sub(r", (?:win|cover|market) [^,]*", "", d["text"])   # odds wiggles aren't changes
            out.append(f"{LABEL[pid]}: {text}" + (f" ({w})" if w else ""))
    when = ((prev.get("meta") or {}).get("generated") or "the last card").replace(" CT", "")
    return [f"Changed since {when}:"] + (out or ["no pick, line or wager changed."])


def message(cards, slate, stage_label, due=None, now=None, final_call=False, prev=None):
    """-> (title, body, urgent). Order: changed since the last card, CHANGE / Differs, picks that moved since the
    last post, pool lines, link."""
    alerts, body = compose(cards, slate, due, now, final_call)
    since = since_lines(cards, prev)
    moved = [f"{r['pick']} (was {r['was']})" for c in cards for r in c["rows"] if r.get("changed")]
    n = sum(a.startswith("CHANGE") for a in alerts)
    title = f"Pool Picks {stage_label}: {n} change{'s' if n != 1 else ''}" if n else f"Pool Picks {stage_label} posted"
    extra = ["Card changed since last post: " + "; ".join(moved)] if moved else []
    msg = "\n".join(since + alerts + extra + body + [PAGE])
    return title, msg, bool(alerts or moved)


def load(week=None):
    cards = json.loads((ROOT / "data/cards.json").read_text(encoding="utf-8"))
    week = week or cards["meta"].get("week")
    if not week:  # cards built before meta carried the week
        from .lines import latest_slate
        week = latest_slate()[1]
    f = ROOT / f"slates/{YEAR}-w{week:02d}.json"
    slate = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return cards, slate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--due", help="pools in the push, e.g. bto,yahoo (default: by weekday)")
    ap.add_argument("--final-call", action="store_true")
    a = ap.parse_args()
    cards, slate = load(a.week)
    title, msg, _ = message(cards["cards"], slate, cards["meta"]["stage_label"], a.due.split(",") if a.due else None,
                            final_call=a.final_call, prev=prev_card(cards["meta"]))
    print(title)
    print(msg)


if __name__ == "__main__":
    main()
