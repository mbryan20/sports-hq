"""Helpers for .github/workflows/picks-backup.yml (stdlib only: the failure step may run before pip installs).

  python -m pp.backup decide --cron "<schedule>" [--stage S]   -> stage=, fresh=, slot= lines for $GITHUB_OUTPUT
  python -m pp.backup fresh --cron "<schedule>" --cards FILE   -> prints 1 if that cards.json is the slot's card
  python -m pp.backup fail --cron "<schedule>" [--stage S] [--log FILE]   -> the failure push text (Q-055)

Fresh = the laptop posted after this slot opened (2h before the cron time), measured from the slot, not from now:
GitHub can run a schedule hours late (Oct 30: 9h; Nov 12: 8h) and an age rule then overwrote a researched card.
"""
import argparse, datetime as d, json, os, re, sys

SLOTS = {"45 3 * * 4": ("Wed 9pm draft", "draft"), "45 2 * * 5": ("Thu 8pm BTO final", "final"),
         "45 3 * * 6": ("Fri 9pm final", "final"), "45 14 * * 6": ("Sat 8am refresh", "refresh")}
SUCCESS_TITLE = "Picks BACKUP card posted"
SUCCESS_TEXT = "Laptop run missed; model-only card (no fresh injury research)."
FAIL_TITLE = "Picks backup failed"


def slot(cron, stage=None):
    """(label, stage) for a schedule; a manual run is labelled by its stage."""
    if cron in SLOTS:
        return SLOTS[cron]
    st = stage or "draft"
    return f"manual {st}", st


def slot_start(cron, now):
    """The latest time this cron fired at or before now (cron day 0 = Sunday); now when not a schedule."""
    f = (cron or "").split()
    if len(f) != 5:
        return now
    mi, hr, dow = int(f[0]), int(f[1]), int(f[4])
    s = now.replace(hour=hr, minute=mi, second=0, microsecond=0)
    s -= d.timedelta(days=((now.isoweekday() % 7) - dow) % 7)
    if s > now:
        s -= d.timedelta(days=7)
    return s


def fresh(meta, cron, now=None):
    """True when cards.json meta was generated after this slot opened (2h before the cron time)."""
    now = now or d.datetime.now(d.timezone.utc)
    made = d.datetime.fromisoformat((meta or {}).get("generated_iso") or "2000-01-01T00:00:00+00:00")
    return made >= slot_start(cron, now) - d.timedelta(hours=2)


ERR = re.compile(r"^(?:[\w.]+\.)?(\w+(?:Error|Exception|Unavailable|Exit|Interrupt)): (.+)$")


def reason(log_text, outcomes=None):
    """Why the backup didn't post, in plain words, from the build log and the step outcomes."""
    o = outcomes or {}
    if o.get("build") == "failure":
        lines = [l.strip() for l in (log_text or "").splitlines() if l.strip()]
        hit = next((m for m in (ERR.match(l) for l in reversed(lines)) if m), None)
        if hit:
            cls, msg = hit.groups()
            if cls in ("CFBDUnavailable", "LinesUnavailable"):
                return msg  # already plain words (pp.http / pp.market)
            if cls == "FileNotFoundError" and "slates" in msg:
                return "this week's pool slate isn't saved in the repo yet"
            if cls in ("ConnectionError", "ReadTimeout", "ConnectTimeout", "HTTPError"):
                return f"a sports site didn't answer ({msg[:140]})"
            return f"the card build crashed ({cls}: {msg[:140]})"
        if lines and len(lines[-1]) <= 200:  # SystemExit("...") prints its message alone
            return f"the card build stopped: {lines[-1]}"
        return "the card build crashed (tap for the log)"
    if o.get("push") == "failure":
        return "the card was built, but saving it to GitHub failed (tap for the log)"
    if o.get("decide") == "failure":
        return "the check for the laptop's card failed (tap for the log)"
    return "GitHub's setup steps failed (tap for the log)"


def failure_text(slot_label, why):
    return f"No picks card reached the site for the {slot_label} slot, and the backup couldn't build one: {why.rstrip('.')}."


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["decide", "fresh", "fail"])
    ap.add_argument("--cron", default="")
    ap.add_argument("--stage", default="")
    ap.add_argument("--cards", default="data/cards.json")
    ap.add_argument("--log", default="")
    a = ap.parse_args(argv)
    label, st = slot(a.cron, a.stage)
    if a.cmd in ("decide", "fresh"):
        with open(a.cards, encoding="utf-8") as f:
            meta = json.load(f)["meta"]
        f = int(fresh(meta, a.cron))
        print(f if a.cmd == "fresh" else f"stage={st}\nfresh={f}\nslot={label}")
        return
    log = ""
    if a.log and os.path.exists(a.log):
        with open(a.log, encoding="utf-8", errors="replace") as f:
            log = f.read()
    outcomes = {k: os.environ.get(f"OUTCOME_{k.upper()}", "") for k in ("decide", "build", "push")}
    print(failure_text(label, reason(log, outcomes)))


if __name__ == "__main__":
    sys.exit(main())
