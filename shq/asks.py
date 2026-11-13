"""Ask Claude (Q-054): a question typed in a league page's "Ask Claude" box (docs/lib/move.js) becomes a GitHub issue
labelled "ask" ("Ask: <league>: <question>", body: the question, then "League: <name>" and the move on screen).
.github/workflows/ask.yml answers it with Claude (ops/tasks/ask-claude.md) and this module keeps the answers,
newest first, per league in docs/data/asks.json, which the league page shows under its box.

    python -m shq.asks parse  > .ask/question.json      issue text from ISSUE_TITLE / ISSUE_BODY / ISSUE_NUMBER / ISSUE_CREATED
    python -m shq.asks images .ask/question.json .ask/img     screenshots in the issue -> .ask/img/1.png ... (image_files)
    python -m shq.asks record .ask/question.json .ask/answer.md     answer -> docs/data/asks.json
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASKS = ROOT / "docs" / "data" / "asks.json"
LINEUPS = ROOT / "docs" / "data" / "lineups.json"
KEEP = 20            # answers kept per league (older ones stay in the GitHub issues)
MAX_ANSWER = 6000    # characters shown on the page


def leagues():
    try:
        return list(json.loads(LINEUPS.read_text(encoding="utf-8"))["leagues"])
    except Exception:
        return []


# Screenshots (Nov 12): pasted or dropped into the GitHub issue box, they land in the body as Markdown or <img> links on
# GitHub's own image hosts. Only those hosts are fetched, at most MAX_IMAGES, each under MAX_IMAGE_BYTES.
IMG_HOSTS = ("https://github.com/user-attachments/assets/", "https://user-images.githubusercontent.com/",
             "https://private-user-images.githubusercontent.com/")
IMG_MD = re.compile(r"!\[[^\]]*\]\((\S+?)\)")
IMG_TAG = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)
MAX_IMAGES, MAX_IMAGE_BYTES = 4, 8_000_000


def images(text):
    """The screenshot links in the issue text, GitHub's image hosts only, in order, no repeats."""
    out = []
    for m in sorted(list(IMG_MD.finditer(text or "")) + list(IMG_TAG.finditer(text or "")), key=lambda m: m.start()):
        u = m.group(1)
        if u.startswith(IMG_HOSTS) and u not in out:
            out.append(u)
    return out[:MAX_IMAGES]


def parse(title, body, number=None, created=None, names=None):
    """{"issue", "asked", "league", "question", "move", "images"} from the issue the Ask box opened. A league not in
    lineups.json (or no "League:" line) is "General". Screenshots anywhere in the body are listed in "images" and
    taken out of the question text."""
    names = leagues() if names is None else names
    body = (body or "").replace("\r\n", "\n")
    shots = images(body)
    body = IMG_TAG.sub("", IMG_MD.sub("", body))
    body = re.sub(r"\n{3,}", "\n\n", body)
    head, _, meta = body.partition("\n---\n")
    m = re.search(r"^League: (.+)$", meta, re.M)
    lg = m.group(1).strip() if m else None
    if not lg:
        t = re.match(r"Ask: ([^:]+): ", title or "")
        lg = t.group(1).strip() if t else None
    mv = re.search(r"^Move on screen: (.+)$", meta, re.M)
    q = head.strip() or re.sub(r"^Ask: [^:]+: ", "", title or "").strip()
    if not q and shots:
        q = "(see the screenshot)"
    return {"issue": int(number) if number else None, "asked": created, "league": lg if lg in names else "General",
            "question": q[:2000], "move": mv.group(1).strip() if mv else None, "images": shots}


def fetch_images(question, folder, opener=None):
    """Download the screenshots to folder/1.png ... and list them in question["image_files"] (paths Claude reads).
    No token is sent: GitHub serves a public repo's attachments without one. A failed download is noted, not fatal."""
    import urllib.request
    opener = opener or urllib.request.urlopen
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files, failed = [], 0
    for n, url in enumerate(question.get("images") or [], 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sports-hq-ask", "Accept": "image/*"})
            with opener(req, timeout=30) as r:
                kind = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                data = r.read(MAX_IMAGE_BYTES + 1)
            if not kind.startswith("image/") or len(data) > MAX_IMAGE_BYTES:
                failed += 1
                continue
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}.get(kind, "png")
            p = folder / f"{n}.{ext}"
            p.write_bytes(data)
            files.append(str(p))
        except Exception:
            failed += 1
    question["image_files"] = files
    if failed:
        question["images_failed"] = failed
    return question


def record(question, answer, path=ASKS, now=None):
    """Add one answer under its league (replacing an earlier answer to the same issue); returns the file's data."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("leagues", {})
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    a = answer.strip()
    if len(a) > MAX_ANSWER:
        a = a[:MAX_ANSWER].rsplit("\n", 1)[0] + "\n…(the full answer is in the GitHub thread)"
    row = {"issue": question.get("issue"), "q": question["question"], "a": a, "asked": question.get("asked"), "answered": now}
    if question.get("move"):
        row["move"] = question["move"]
    if question.get("images"):
        row["shots"] = len(question["images"])
    rows = [r for r in data["leagues"].get(question["league"], []) if r.get("issue") is None or r.get("issue") != row["issue"]]
    data["leagues"][question["league"]] = ([row] + rows)[:KEEP]
    data["updated"] = now
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return data


def main(argv):
    if argv[:1] == ["parse"]:
        e = os.environ
        print(json.dumps(parse(e.get("ISSUE_TITLE", ""), e.get("ISSUE_BODY", ""), e.get("ISSUE_NUMBER"), e.get("ISSUE_CREATED")), indent=1))
    elif argv[:1] == ["images"] and len(argv) == 3:
        p = Path(argv[1])
        q = fetch_images(json.loads(p.read_text(encoding="utf-8")), argv[2])
        p.write_text(json.dumps(q, indent=1), encoding="utf-8")
        print(f"{len(q['image_files'])} screenshot(s) saved" + (f", {q['images_failed']} failed" if q.get("images_failed") else ""))
    elif argv[:1] == ["record"] and len(argv) == 3:
        q = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        p = Path(argv[2])
        a = p.read_text(encoding="utf-8") if p.exists() else ""
        if not a.strip():
            a = "Claude didn't finish an answer this time. Ask again, or open the GitHub thread for what happened."
        record(q, a, ASKS)
        print(f"recorded #{q.get('issue')} under {q['league']}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
