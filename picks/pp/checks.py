"""Second-opinion support: automatic rule checks on the built card, and recording the reviewer's verdict.

The runbook's second opinion is a subagent that didn't build the card. It reads `py -m pp.checks` (these
automatic checks plus the push as it would go out), the slate (rules, saved picks) and the Decisions log, and
judges what code can't: hedging, contradictions, reasons. After fixes, the run records the verdict:

    py -m pp.checks --record "Checked: formats, locks, wager rules, saved picks, decisions, no hedging, totals"

which stores it in data/cards.json and redraws the page (picks unchanged). Rules: docs/picks/method/pool-rules.md.
"""
import argparse, json, re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .names import norm
from .push import PICK_RE, _kick_dt, compose, load, money, parse_pick

ROOT = Path(__file__).resolve().parent.parent
CT = ZoneInfo("America/Chicago")
MIN_FRAC = {"normal": 0.25, "three": 0.5, "one": 1.0}
BET_COUNT = {"three": 3, "one": 1}
# a conditional pick ("take X if Y", "if Y then X", "X unless Y"), not a reason that merely describes news
HEDGE = re.compile(r"\b(take|pick|bet|switch|play|go with|move)\b[^.;]*\b(if|unless)\b|\bif\b[^.;]*\bthen\b"
                   r"|\bif\b[^.;]*,\s*(take|pick|bet|switch|play)\b|\beither\b.*\bor\b", re.I)


def _side_line(sg, team):
    """The pool's posted line for that side (home_spread is the home team's line)."""
    return sg["home_spread"] if norm(team) == norm(sg["home"]) else -sg["home_spread"]


def _games(slate, pid):
    return {f"{g['away']}@{g['home']}": g for g in (slate.get(pid) or {}).get("games") or []}


def check_bto(card, slate, now):
    out, b = [], slate.get("bto") or {}
    rows, games = card["rows"], _games(slate, "bto")
    if not rows:
        return out
    mode = b.get("mode", "normal")
    stakes = [money(r["wager"]) for r in rows]
    bal = b.get("balance") or 0
    lp = [float(m[1]) if (m := re.search(r"\(LP ([0-9.]+)\)", r["pick"])) else 0.0 for r in rows]
    out.append(("BTO format: every pick has a spread", all(PICK_RE.match(r["pick"]) for r in rows), ""))
    if mode in BET_COUNT:
        out.append((f"BTO {mode} mode: exactly {BET_COUNT[mode]} bets", len(rows) == BET_COUNT[mode], f"{len(rows)} bets"))
    if mode != "one" and any(g.get("big") for g in games.values()):
        big = {k for k, g in games.items() if g.get("big")}
        out.append(("BTO Big Game included", any(r["key"] in big for r in rows), ""))
    lo = MIN_FRAC.get(mode, 0.25) * bal
    out.append((f"BTO total ${sum(stakes):,} within ${lo:,.0f}-${bal:,}", lo <= sum(stakes) <= bal, ""))
    out.append(("BTO wagers in $10 multiples", all(s % 10 == 0 and s > 0 for s in stakes), str(stakes)))
    out.append(("BTO largest bet at most 2x smallest", max(stakes) <= 2 * min(stakes), str(stakes)))
    out.append((f"BTO line points {sum(lp):g} of 4, in 0.5 steps", sum(lp) <= 4 and all((x * 2) % 1 == 0 for x in lp), ""))
    bad_line, locked = [], []
    for r, l in zip(rows, lp):
        sg = games.get(r["key"])
        if not sg:
            bad_line.append(f"{r['key']} not on the slate")
            continue
        team, line = parse_pick(r["pick"])
        if line is None or abs(line - (_side_line(sg, r["pick_team"]) + l)) > 1e-6:
            bad_line.append(r["pick"])
        k = _kick_dt(sg.get("kick"))
        if sg.get("locked") or (k and k <= now):
            locked.append(r["game"])
    out.append(("BTO lines = pool line + line points", not bad_line, ", ".join(bad_line)))
    out.append(("BTO no pick on a locked game", not locked, ", ".join(locked)))
    return out


def check_cfp(card, slate, now):
    out, c = [], slate.get("cfp") or {}
    rows, games = card["rows"], _games(slate, "cfp")
    if not rows:
        return out
    bal = c.get("balance") or 0
    total = sum(money(r["wager"]) for r in rows)
    out.append(("CFP format: every pick has a spread", all(PICK_RE.match(r["pick"]) for r in rows), ""))
    out.append((f"CFP total {total:,} is 50-100% of {bal:,}", 0.5 * bal <= total <= bal, f"{total / bal * 100:.0f}%" if bal else ""))
    bad = [r["pick"] for r in rows if r["key"] not in games
           or parse_pick(r["pick"])[1] != _side_line(games[r["key"]], r["pick_team"])]
    out.append(("CFP lines = pool's posted spread", not bad, ", ".join(bad)))
    lock = now.replace(hour=11, minute=0, second=0, microsecond=0)
    out.append(("CFP built before its Sat 11am lock", not (now.weekday() == 5 and now >= lock), ""))
    return out


def check_yahoo(card, slate):
    out, y = [], slate.get("yahoo") or {}
    rows = card["rows"]
    if not rows:
        return out
    out.append(("Yahoo format: straight-up (no spreads)", not any(PICK_RE.match(r["pick"]) for r in rows), ""))
    n = len(y.get("games") or [])
    out.append((f"Yahoo picks {len(rows)} of {n} games", len(rows) == n, ""))
    tbs = card.get("tiebreakers", [])
    out.append(("Yahoo TB1 for every designated game", sum(t.startswith("TB1 ") for t in tbs) == len(y.get("tb1") or []), ""))
    out.append(("Yahoo TB2 most and fewest set", any("most points" in t for t in tbs) and any("fewest points" in t for t in tbs), ""))
    return out


def run(cards, slate, now=None):
    """-> [{"check", "ok", "detail"}] for every pool card plus the no-hedging check."""
    now = now or datetime.now(CT)
    res = []
    for c in cards:
        res += {"bto": lambda: check_bto(c, slate, now), "cfp": lambda: check_cfp(c, slate, now),
                "yahoo": lambda: check_yahoo(c, slate)}.get(c["id"], list)()
    hedges = [f"{c['id']}: {r['pick']}" for c in cards for r in c["rows"] if HEDGE.search(r["pick"]) or HEDGE.search(r.get("why", ""))]
    res.append(("No 'if X then Y' hedging in picks or reasons", not hedges, "; ".join(hedges)))
    return [{"check": n, "ok": bool(ok), "detail": d} for n, ok, d in res]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--record", help='the reviewer\'s verdict, e.g. "Checked: formats, locks, wager rules, ..."')
    a = ap.parse_args()
    d, slate = load(a.week)
    built = d["meta"].get("generated_iso")  # lock checks are about when the card was built
    res = run(d["cards"], slate, datetime.fromisoformat(built).astimezone(CT) if built else None)
    if not a.record:
        alerts, body = compose(d["cards"], slate, final_call=d["meta"].get("stage") != "draft")
        print(json.dumps({"auto_checks": res, "push_alerts": alerts, "push_pools": body}, indent=1, ensure_ascii=False))
        return
    fails = [r["check"] + (f" ({r['detail']})" if r["detail"] else "") for r in res if not r["ok"]]
    text = a.record.strip()
    d["meta"]["checked"] = {"text": text if text.lower().startswith("checked") else f"Checked: {text}",
                            "stage": d["meta"].get("stage"), "at": datetime.now(CT).strftime("%a %I:%M %p CT"),
                            "auto_passed": sum(r["ok"] for r in res), "auto_total": len(res), "auto_fails": fails}
    (ROOT / "data/cards.json").write_text(json.dumps(d, indent=1, default=str))
    from .cards import rerender
    rerender(d["meta"].get("week"))
    print(json.dumps(d["meta"]["checked"], indent=1))


if __name__ == "__main__":
    main()
