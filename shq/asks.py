"""Ask Claude (Q-054): a question typed in a league page's "Ask Claude" box (docs/lib/move.js) becomes a GitHub issue
labelled "ask" ("Ask: <league>: <question>", body: the question, then "League: <name>" and the move on screen).
.github/workflows/ask.yml answers it with Claude (ops/tasks/ask-claude.md) and this module keeps the answers,
newest first, per league in docs/data/asks.json, which the league page shows under its box.

    python -m shq.asks parse  > .ask/question.json      issue text from ISSUE_TITLE / ISSUE_BODY / ISSUE_NUMBER / ISSUE_CREATED
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


def parse(title, body, number=None, created=None, names=None):
    """{"issue", "asked", "league", "question", "move"} from the issue the Ask box opened. A league not in
    lineups.json (or no "League:" line) is "General"."""
    names = leagues() if names is None else names
    body = (body or "").replace("\r\n", "\n")
    head, _, meta = body.partition("\n---\n")
    m = re.search(r"^League: (.+)$", meta, re.M)
    lg = m.group(1).strip() if m else None
    if not lg:
        t = re.match(r"Ask: ([^:]+): ", title or "")
        lg = t.group(1).strip() if t else None
    mv = re.search(r"^Move on screen: (.+)$", meta, re.M)
    q = head.strip() or re.sub(r"^Ask: [^:]+: ", "", title or "").strip()
    return {"issue": int(number) if number else None, "asked": created, "league": lg if lg in names else "General",
            "question": q[:2000], "move": mv.group(1).strip() if mv else None}


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
    rows = [r for r in data["leagues"].get(question["league"], []) if r.get("issue") is None or r.get("issue") != row["issue"]]
    data["leagues"][question["league"]] = ([row] + rows)[:KEEP]
    data["updated"] = now
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return data


def main(argv):
    if argv[:1] == ["parse"]:
        e = os.environ
        print(json.dumps(parse(e.get("ISSUE_TITLE", ""), e.get("ISSUE_BODY", ""), e.get("ISSUE_NUMBER"), e.get("ISSUE_CREATED")), indent=1))
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
