"""Commit + push, wait for the GitHub Pages build of that commit, then send the ntfy push.

Usage: py -m pp.publish --stage draft|final|refresh|postmortem [--title ...] [--no-push-notify]
"""
import argparse, json, os, subprocess, time
from pathlib import Path
import requests
from .push import load as push_load, message as push_message

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


def notify(title, msg, tags="football", priority=3):
    t = topic()
    if not t:
        print("no ntfy topic; skipped push")
        return False
    r = requests.post(f"https://ntfy.sh/{t}", data=msg.encode(), timeout=30,
                      headers={"Title": title, "Tags": tags, "Click": PAGE, "Priority": str(priority)})
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
                                          a.due.split(",") if a.due else None, final_call=meta.get("stage") != "draft")
        if a.title and not urgent:
            title = a.title
        if (meta.get("checked") or {}).get("stage") != meta.get("stage"):
            print("WARNING: no second-opinion check recorded for this build (py -m pp.checks --record ...)")
    if not built:
        msg += " (page may take a minute to update)"
    notify(title, msg, tags="rotating_light" if urgent else "football", priority=4 if urgent else 3)


if __name__ == "__main__":
    main()
