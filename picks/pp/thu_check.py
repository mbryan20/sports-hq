"""Thursday 4pm CT BTO check (R2, ops/tasks/pool-picks-thu-bto-check.md). BTO bets lock at each game's kickoff, so in a
week whose BTO slate has a Thursday game, a saved bet on that game can't be fixed by the Thu 8pm final run. At 4pm this
compares Michael's saved BTO bets (read in Chrome by the task, passed in a file) with the published BTO card
(data/published/<year>-wNN-bto.json) and pushes only if they differ: one "yours → card" line per game, then the lock time.

Usage:
  py -m pp.thu_check --needed                 # exit 0 and print the Thursday game(s) if this week needs the check, else exit 3
  py -m pp.thu_check --saved FILE [--push]    # FILE: {"read": iso, "bets": [{"key": "Away@Home", "pick": "...", "wager": 600}]}
                                              # or {"unread": "<why>"}; prints the push, sends it with --push when they differ
Read-only on BTO: it never changes a pick."""
import argparse
import json
import sys
from datetime import datetime

from .push import CT, ROOT, YEAR, _kick_dt, fmt_wager, money, parse_pick

PUBLISHED = ROOT / "data" / "published"


def week_now(now):
    """This week's slate number: the newest slate file (the Wednesday draft creates it)."""
    files = sorted((ROOT / "slates").glob(f"{YEAR}-w*.json"))
    return int(files[-1].stem.split("-w")[1]) if files else None


def load(week):
    slate = json.loads((ROOT / f"slates/{YEAR}-w{week:02d}.json").read_text(encoding="utf-8"))
    f = PUBLISHED / f"{YEAR}-w{week:02d}-bto.json"
    card = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return slate, card


def thursday_games(slate, now):
    """BTO games kicking off on Thursday of this week, not yet started: [(kickoff, "Away@Home")]."""
    out = []
    for g in (slate.get("bto") or {}).get("games") or []:
        k = _kick_dt(g.get("kick"))
        if k and k.weekday() == 3 and k > now and (k - now).days < 7 and not g.get("locked"):
            out.append((k, f"{g['away']}@{g['home']}"))
    return sorted(out)


def _bet(pick, wager):
    return f"{pick} {fmt_wager('bto', wager)}"


def diff(saved, card):
    """['GB@NE: yours NE -2.5 $830 → card NE -2.5 $1,660', ...]; [] when they match. The bets are one package, so every
    game that differs is listed, Thursday's first by the caller."""
    mine = {b["key"]: b for b in (saved or {}).get("bets") or []}
    lines = []
    for key in list(card) + [k for k in mine if k not in card]:
        c, m = card.get(key), mine.get(key)
        if c and m and parse_pick(c["pick"]) == parse_pick(m["pick"]) and money(c["wager"]) == money(m["wager"]):
            continue
        yours = _bet(m["pick"], m["wager"]) if m else "no bet"
        ours = _bet(c["pick"], c["wager"]) if c else "no bet"
        lines.append(f"{key.replace('@', ' @ ')}: yours {yours} → card {ours}")
    return lines


def message(saved, card, games, week):
    """(title, body) to push, or None when nothing needs doing."""
    if not games or not card:
        return None
    first, key = games[0]
    lock = f"{first:%a} {first.hour % 12 or 12}:{first:%M}{'pm' if first.hour >= 12 else 'am'} CT"
    if (saved or {}).get("unread"):
        return (f"BTO: check your saved bets before {lock}",
                f"Couldn't read your saved BTO bets ({saved['unread']}). {key.replace('@', ' @ ')} locks {lock}; "
                f"the card is on the Picks page.")
    lines = diff(saved, card)
    if not lines:
        return None
    thu = {k for _, k in games}
    lines.sort(key=lambda t: t.split(":")[0].replace(" @ ", "@") not in thu)
    stage = next(iter(card.values()), {}).get("stage", "")
    return (f"BTO: saved bets differ from the card, {key.replace('@', ' @ ')} locks {lock}",
            "\n".join(lines) + f"\nEdit in BTO before {lock} ({key.replace('@', ' @ ')} kicks off then). "
            f"Card: week {week} {stage}, published on the Picks page.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--needed", action="store_true")
    ap.add_argument("--saved")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(CT)
    week = a.week or week_now(now)
    slate, card = load(week)
    games = thursday_games(slate, now)
    if a.needed:
        if not games:
            print(f"Week {week}: no Thursday BTO game still to play; nothing to check.")
            return 3
        print(f"Week {week}: Thursday BTO game(s): " + ", ".join(f"{k} ({t:%a %I:%M %p} CT)" for t, k in games))
        return 0
    saved = json.loads(open(a.saved, encoding="utf-8").read()) if a.saved else (slate.get("bto") or {}).get("saved")
    msg = message(saved, card, games, week)
    if not msg:
        print("No push: " + ("no Thursday BTO game" if not games else "no published BTO card" if not card
                             else "your saved BTO bets match the card"))
        return 0
    print(msg[0])
    print(msg[1])
    if a.push:
        from .publish import notify
        notify(msg[0], msg[1], tags="warning", priority=4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
