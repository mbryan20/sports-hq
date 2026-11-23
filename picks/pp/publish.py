"""Commit + push, wait for the GitHub Pages build of that commit, then send the ntfy push.

Usage: py -m pp.publish --stage draft|final|refresh|postmortem [--title ...] [--no-push-notify]
Phone sound: final always; draft/refresh only when something needs fixing before a lock within 24h; postmortem
silent (push_urgent; Michael's Nov 23 rule).
"""
import argparse, json, os, subprocess, time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from .push import CT, _kick_dt, load as push_load, message as push_message, prev_card

ROOT = Path(__file__).resolve().parent.parent
REPO = "mbryan20/sports-hq"
PAGE = "https://mbryan20.github.io/sports-hq/picks/"
NTFY_FILE = ROOT / ".ntfy_topic"  # local only (gitignored); CI uses the NTFY_TOPIC secret


def sh(*a, check=True):
    return subprocess.run(a, cwd=ROOT, check=check, capture_output=True, text=True).stdout.strip()


def topic():
    t = os.environ.get("NTFY_TOPIC")
    if not t and NTFY_FILE.exists():
        t = NTFY_FILE.read_text().strip()
    return t


# Michael's rule (Nov 23, 2026), as in shq/notify.py: a push that needs him within 24 hours, is about money, or says
# something broke keeps its sound (priority at least 4); everything else is silent (2). Unsure = urgent.
URGENT, SILENT = 4, 2
SILENT_STAGES = {"postmortem"}        # a look back at last week: never needs him
CONTENT_STAGES = {"draft", "refresh"}  # urgent only when he has something to fix before a lock within 24h
NEEDS_ACTION = ("nothing saved yet", "not saved yet", "not read")   # body lines that mean "check your saved picks"


def level(urgent=True, priority=None):
    """ntfy priority: urgent -> its own priority, at least URGENT (max 5); anything else -> SILENT."""
    if not urgent:
        return SILENT
    try:
        p = int(priority)
    except (TypeError, ValueError):
        p = 0
    return min(max(p, URGENT), 5)


def next_lock(slate, now):
    """When the next open pool or game stops taking changes, from the slate: BTO bets due Fri 8pm CT, the slate's
    deadlines (CFP Sat 11am), and every unlocked BTO / Yahoo kickoff. None when nothing in the slate says."""
    now = now.astimezone(CT)
    times = []
    for pid in ("bto", "cfp", "yahoo"):
        pool = slate.get(pid) or {}
        if pool.get("deadline"):
            try:
                times.append(datetime.fromisoformat(pool["deadline"]))
            except ValueError:
                pass
        times += [k for g in pool.get("games") or [] if not g.get("locked") and (k := _kick_dt(g.get("kick")))]
    if (slate.get("bto") or {}).get("games") and now.weekday() <= 4:
        times.append((now + timedelta(days=4 - now.weekday())).replace(hour=20, minute=0, second=0, microsecond=0))
    future = [t for t in times if t > now]
    return min(future) if future else None


def push_urgent(stage, msg, flagged, slate, now, note=False):
    """Does this card's push keep its sound? Postmortem: never. Final, and any stage not listed: always.
    Draft and refresh: a --msg note (a failure) always; otherwise only when something needs fixing (`flagged`: a CHANGE
    line or a moved pick; or nothing saved / saved picks unread) and the next lock is within 24h (or can't be told)."""
    if stage in SILENT_STAGES:
        return False
    if stage not in CONTENT_STAGES or note:
        return True
    if not (flagged or any(s in msg for s in NEEDS_ACTION)):
        return False
    lock = next_lock(slate, now)
    return lock is None or lock - now.astimezone(CT) <= timedelta(hours=24)


def notify(title, msg, tags="football", priority=None, urgent=True):
    """Send one push. urgent: needs Michael within 24h, money, or something broke (sound); False = silent."""
    t = topic()
    if not t:
        print("no ntfy topic; skipped push")
        return False
    r = requests.post(f"https://ntfy.sh/{t}", data=msg.encode(), timeout=30,
                      headers={"Title": title, "Tags": tags, "Click": PAGE, "Priority": str(level(urgent, priority))})
    print("ntfy", r.status_code)
    return r.ok


def _contains(commit, sha):
    sh("git", "fetch", "-q", "origin", "main", check=False)
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, commit], cwd=ROOT).returncode == 0


def wait_pages(sha, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = json.loads(sh("gh", "api", f"repos/{REPO}/pages/builds/latest"))
            # Sports HQ's data jobs push often, so the latest build may be a later commit that
            # already contains ours.
            if b.get("commit") and _contains(b["commit"], sha):
                if b.get("status") == "built":
                    return True
                if b.get("status") == "errored" and b["commit"] == sha:
                    return False
        except subprocess.CalledProcessError:
            pass
        time.sleep(15)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--title")
    ap.add_argument("--msg")
    ap.add_argument("--no-push-notify", action="store_true")
    ap.add_argument("--due", help="pools in the push, e.g. bto,yahoo (default: by weekday, see pp.push.DUE)")
    a = ap.parse_args()
    sh("git", "add", "-A", "--", ".", "../docs/picks")  # only Pool Picks files
    if sh("git", "status", "--porcelain"):
        sh("git", "commit", "-m", f"Pool picks: {a.stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    sh("git", "pull", "--no-rebase", "--no-edit", "--autostash", "origin", "main", check=False)  # merge, never rebase
    sh("git", "push", "origin", "main")
    sha = sh("git", "rev-parse", "HEAD")
    built = wait_pages(sha)
    print("pages built:", built)
    if a.no_push_notify:
        return
    cards, slate = push_load()
    meta = cards["meta"]
    if a.msg:  # postmortem and failure notes
        title, msg, urgent = a.title or f"Pool Picks {meta['stage_label']} posted", a.msg, False
    else:
        # standalone push: CHANGE / Differs lines, one line per pool due before the next run, the page link
        title, msg, urgent = push_message(cards["cards"], slate, meta["stage_label"],
                                          a.due.split(",") if a.due else None, final_call=meta.get("stage") != "draft",
                                          prev=prev_card(meta))
        if a.title and not urgent:
            title = a.title
        if (meta.get("checked") or {}).get("stage") != meta.get("stage"):
            print("WARNING: no second-opinion check recorded for this build (py -m pp.checks --record ...)")
    if not built:
        msg += " (page may take a minute to update)"
    loud = push_urgent(a.stage, msg, urgent, slate, datetime.now(CT), note=bool(a.msg))
    notify(title, msg, tags="rotating_light" if urgent else "football", urgent=loud)


if __name__ == "__main__":
    main()
