"""Copy the Guillotine War Room page (a claude.ai artifact, which work networks block) onto the
Sports HQ site: `py -m shq.save_warroom <downloaded index.html>` adds the back link and noindex tag,
writes docs/war-room/index.html, and commits + pushes only if it changed."""
import pathlib
import subprocess
import sys

from .common import ROOT

OUT = ROOT / "docs" / "war-room" / "index.html"
LINK = ('<a href="../" style="position:fixed;top:calc(env(safe-area-inset-top,0px) + 6px);right:8px;z-index:9999;'
        'font:600 12px -apple-system,sans-serif;background:#111;color:#fff;padding:5px 9px;border-radius:999px;'
        'text-decoration:none">&larr; Sports HQ</a>')


def main(src):
    s = pathlib.Path(src).read_text(encoding="utf-8")
    if "Guillotine War Room" not in s or len(s) < 20000:
        sys.exit("That doesn't look like the War Room page.")
    s = s.replace("<body>", "<body>" + LINK, 1)
    s = s.replace("<title>Guillotine War Room</title>", '<title>Guillotine War Room</title><meta name="robots" content="noindex">', 1)
    if OUT.exists() and OUT.read_text(encoding="utf-8") == s:
        print("War Room unchanged.")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(s, encoding="utf-8")
    run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, check=True)
    run("pull", "-q", "--no-rebase", "--no-edit")
    run("add", str(OUT.relative_to(ROOT)))
    run("commit", "-q", "-m", "War Room refreshed from its artifact")
    run("push", "-q")
    print("War Room updated and pushed.")


if __name__ == "__main__":
    main(sys.argv[1])
