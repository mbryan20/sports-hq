"""Git merge driver for push-dedup state files (Q-049): state/alerts.json and state/pick_lines_sent.json map an alert key
to when it was sent. Two runs (a laptop kick beside a cron loop) each add keys; `git pull --rebase -X theirs` in
.github/commit_data.sh used to keep one side's whole file and drop the other run's keys, so a later pass could push the
same alert again. This keeps every key from both sides (the later time when both have one).

Wired up by .gitattributes (`merge=pushstate`) and commit_data.sh (`git config merge.pushstate.driver ...`).
Usage (git calls it): python -m shq.statemerge %O %A %B  -- writes the result to %A, always exits 0."""
import json
import sys
from pathlib import Path


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def merge_files(ours, theirs):
    """The merged dict, or None when neither side parses (then git keeps %A as it is)."""
    a, b = _read(ours), _read(theirs)
    if a is None and b is None:
        return None
    out = dict(a or {})
    for k, v in (b or {}).items():
        if k not in out or str(v) > str(out[k]):
            out[k] = v
    return out


def main(argv):
    _, ours, theirs = argv[:3]
    merged = merge_files(ours, theirs)
    if merged is not None:
        Path(ours).write_text(json.dumps(merged, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
