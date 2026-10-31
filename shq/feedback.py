"""Site feedback: a feedback issue (opened from the site's 👍 / 👎 / Feedback buttons) becomes one FEEDBACK.md line.

Run by .github/workflows/feedback.yml with the issue in env vars; stdlib only, no AI.
The site (docs/lib/core.js, feedbackURL) writes the issue body as: free text, a "---" line, then
"Mood:", "Layout:", "Spot:", "Screen:" and "Page:" lines.
"""
import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")
INBOX, HANDLED = "## Inbox", "## Handled"
MAX_TEXT = 600


def parse(title, body):
    """Free text and the metadata lines from an issue body. Issues typed by hand have no metadata."""
    body = (body or "").replace("\r\n", "\n")
    text, _, tail = body.partition("\n---\n")
    meta = {}
    for line in tail.splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip() in ("Mood", "Layout", "Spot", "Screen", "Page"):
            meta[k.strip().lower()] = v.strip()
    text = text.strip()
    if text == "(no comment)":
        text = ""
    if not meta and not text:
        text = re.sub(r"^Feedback:\s*", "", title or "").strip()
    return text, meta


def entry(number, url, created, title, body):
    text, meta = parse(title, body)
    day = dt.datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(TZ).date().isoformat()
    text = re.sub(r"\s+", " ", text)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT - 1].rstrip() + "…"
    where = " · ".join(v for v in (meta.get("mood"), meta.get("layout"), meta.get("spot"), meta.get("screen")) if v)
    said = f': "{text}"' if text else ""
    return f"- {day} {where or 'Feedback'}{said} ([#{number}]({url}))"


def add(doc, line):
    """Append the line at the end of the Inbox section (before Handled); create sections if missing."""
    if INBOX not in doc:
        doc = doc.rstrip("\n") + f"\n\n{INBOX}\n\n{HANDLED}\n"
    head, _, rest = doc.partition(INBOX)
    inbox, sep, after = rest.partition(HANDLED)
    items = inbox.strip("\n")
    inbox = "\n\n" + (items + "\n" if items else "") + line + "\n\n"
    return head + INBOX + inbox + sep + after


def main():
    e = os.environ
    line = entry(e["ISSUE_NUMBER"], e["ISSUE_URL"], e["ISSUE_CREATED"], e.get("ISSUE_TITLE", ""), e.get("ISSUE_BODY", ""))
    path = sys.argv[1] if len(sys.argv) > 1 else "FEEDBACK.md"
    with open(path, encoding="utf-8") as f:
        doc = f.read()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(add(doc, line))
    print(line)


if __name__ == "__main__":
    main()
