"""Commit + push, wait for the GitHub Pages build of that commit, then send the ntfy push.

Usage: py -m pp.publish --stage draft|final|refresh|postmortem [--title ...] [--no-push-notify]
"""
import argparse, json, os, subprocess, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = "mbryan20/pool-picks"
PAGE = "https://mbryan20.github.io/pool-picks/"
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


def wait_pages(sha, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = json.loads(sh("gh", "api", f"repos/{REPO}/pages/builds/latest"))
            if b.get("commit") == sha and b.get("status") == "built":
                return True
            if b.get("commit") == sha and b.get("status") == "errored":
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
    a = ap.parse_args()
    sh("git", "add", "-A")
    if sh("git", "status", "--porcelain"):
        sh("git", "commit", "-m", f"Pool picks: {a.stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    sh("git", "pull", "--rebase", "origin", "main", check=False)
    sh("git", "push", "origin", "main")
    sha = sh("git", "rev-parse", "HEAD")
    built = wait_pages(sha)
    print("pages built:", built)
    if a.no_push_notify:
        return
    cards = json.loads((ROOT / "data/cards.json").read_text())
    changed = [f"{c['title']}: {r['pick']}" for c in cards["cards"] for r in c["rows"] if r.get("changed")]
    title = a.title or f"Pool Picks {cards['meta']['stage_label']} posted"
    msg = a.msg or ("CHANGED: " + "; ".join(changed) if changed else "New cards are up. Tap to open.")
    if not built:
        msg += " (page may take a minute to update)"
    notify(title, msg, tags="rotating_light" if changed else "football", priority=4 if changed else 3)


if __name__ == "__main__":
    main()
