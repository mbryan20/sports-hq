"""Train and test our player values (shq/pv_model.py) on past seasons; writes state/pv_model.json.

Run at the four value reviews (rule 28: ~Sep 3, ~Oct 27, ~Feb 10, ~May 10), on the laptop:
    py -I -m shq.pv_train --dp <clone of github.com/dynastyprocess/data> [--write] [--report research.md]
The clone is `git clone --filter=blob:none https://github.com/dynastyprocess/data` (GitHub's API rate-limits; the clone
doesn't). DynastyProcess's superflex value (value_2qb) is the market history: FantasyCalc has none before Nov 6, 2026.

The test (research/player-values-build-plan.md section 1 and 4):
- Rows: players worth 1,000+ at an anchor date; target = log(value 12 months later / value now), a player who left the
  list counts as a crash (value FLOOR). In-season anchors: early Oct, early Nov, early Dec (season to date through weeks 4,
  8, 12). Offseason anchors: mid-Feb, mid-May (after the NFL draft), late Aug (last full season).
- "Excess move" = that change minus the average change of the same position on the same date, minus the age-band average
  from the TRAINING rows only (no peeking at the test season).
- Walk-forward: each test year's rows are predicted by a model fitted only on rows whose 12 months ended before the test
  year's first anchor. Market alone = predicts no excess move.
- Ship test per position and version (all four): error cut >= 3% pooled over the last 4 test years; better in 3+ of them;
  big calls (15%+ off the market) right >= 58% with 20+ calls; 80+ test rows."""
import argparse
import collections
import csv
import io
import datetime as dt
import json
import math
import statistics as st
import subprocess
import sys

from . import pv_data
from .common import iso, now_utc, save_json
from .pv_model import MODEL_FILE, X

FLOOR = 50.0
MIN_V = 1000.0
MIN_V_ROOKIE = 300.0
BIG = 0.15
LAMBDA = 20.0
SHRINKS = (1.0, 0.5)
GATE = {"cut": 0.03, "years_better": 3, "years": 4, "hit": 0.58, "calls": 20, "n": 80}
IN_ANCHORS = (((10, 6), 4), ((11, 3), 8), ((12, 1), 12))
OFF_ANCHORS = ((2, 12), (5, 15), (8, 25))


# ---- market history from the DynastyProcess clone ----
class DP:
    def __init__(self, repo, ids):
        self.repo, self.fp = repo, ids["fp"]
        last = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cs", "--", "files/values-players.csv"],
                              capture_output=True, text=True).stdout.strip()
        self.last = dt.date.fromisoformat(last)
        self._cache = {}

    def at(self, day):
        """{gsis: {"pos", "age", "v", "dy"}} as of the last commit on or before `day`; None after the clone's last commit."""
        if day > self.last:
            return None
        if day in self._cache:
            return self._cache[day]
        sha = subprocess.run(["git", "-C", self.repo, "log", "-1", "--format=%H", f"--until={day.isoformat()}T23:59:59Z",
                              "--", "files/values-players.csv"], capture_output=True, text=True).stdout.strip()
        text = subprocess.run(["git", "-C", self.repo, "show", f"{sha}:files/values-players.csv"], capture_output=True,
                              text=True, encoding="utf-8").stdout if sha else ""
        out = {}
        for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
            v = pv_data.fnum(r.get("value_2qb"))
            g = self.fp.get(r.get("fp_id") or "")
            if r.get("pos") in pv_data.SKILL and v and g:
                out[g] = {"pos": r["pos"], "age": pv_data.fnum(r.get("age")), "v": v, "dy": r.get("draft_year")}
        self._cache[day] = out
        return out


def ageband(a):
    return None if a is None else min(max(int(a), 21), 32)


def rows_for(dp, stats_week, stats_season, draft, years):
    """Training rows for both versions and the rookie trial."""
    rows = []
    for y in years:
        for (m, d), wk in IN_ANCHORS:
            a = dt.date(y, m, d)
            rows += _rows(dp, a, "in", y, lambda g, pos: pv_data.to_date((stats_week.get(y) or {}).get(g), wk))
        for (m, d) in OFF_ANCHORS:
            a = dt.date(y, m, d)
            rows += _rows(dp, a, "off", y, lambda g, pos: (stats_season.get(y - 1) or {}).get(g) or {}, allow_empty=True)
        rows += _rookies(dp, dt.date(y, 5, 15), y, draft)
    return rows


def _rows(dp, a, ver, y, feat, allow_empty=False):
    now, later = dp.at(a), dp.at(a + dt.timedelta(days=365))
    if now is None or later is None:
        return []
    out = []
    for g, p in now.items():
        if p["v"] < MIN_V:
            continue
        f = feat(g, p["pos"])
        if f is None or (not f and not allow_empty):
            continue
        end = (later.get(g) or {}).get("v") or FLOOR
        out.append({"ver": ver, "pos": p["pos"], "year": y, "anchor": a, "end": a + dt.timedelta(days=365), "g": g,
                    "age": p["age"], "v": p["v"], "ch": math.log(end / p["v"]), "x": X(p["pos"], ver, f)})
    return out


def _rookies(dp, a, y, draft):
    now, later = dp.at(a), dp.at(a + dt.timedelta(days=365))
    if now is None or later is None:
        return []
    rk = [(g, p) for g, p in now.items() if p["dy"] == str(y) and p["v"] >= MIN_V_ROOKIE and g in draft]
    if not rk:
        return []
    mean_log = st.mean(math.log(p["v"]) for _, p in rk)
    out = []
    for g, p in rk:
        end = (later.get(g) or {}).get("v") or FLOOR
        pick = draft[g][2]
        out.append({"ver": "rookie", "pos": p["pos"], "year": y, "anchor": a, "end": a + dt.timedelta(days=365), "g": g,
                    "age": p["age"], "v": p["v"], "ch": math.log(end / p["v"]),
                    "x": [1.0, math.log(pick) - 3.5, math.log(p["v"]) - mean_log]})
    return out


def relative(rows):
    """r["rel"] = change minus the same position's average change on the same anchor date."""
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["ver"], r["anchor"], r["pos"])].append(r["ch"])
    m = {k: st.mean(v) for k, v in by.items()}
    for r in rows:
        r["rel"] = r["ch"] - m[(r["ver"], r["anchor"], r["pos"])]


def age_base(train):
    by = collections.defaultdict(list)
    for r in train:
        by[ageband(r["age"])].append(r["rel"])
    return {k: st.mean(v) for k, v in by.items() if len(v) >= 5}


def target(r, base):
    return r["rel"] - (base.get(ageband(r["age"]), 0.0) if r["ver"] != "rookie" else 0.0)


def ridge(train, base, lam=LAMBDA):
    k = len(train[0]["x"])
    A = [[0.0] * k for _ in range(k)]
    b = [0.0] * k
    for r in train:
        x, t = r["x"], target(r, base)
        for i in range(k):
            b[i] += x[i] * t
            for j in range(k):
                A[i][j] += x[i] * x[j]
    for i in range(1, k):
        A[i][i] += lam
    M = [A[i] + [b[i]] for i in range(k)]
    for i in range(k):
        piv = max(range(i, k), key=lambda q: abs(M[q][i]))
        M[i], M[piv] = M[piv], M[i]
        if abs(M[i][i]) < 1e-12:
            continue
        for q in range(k):
            if q != i:
                fc = M[q][i] / M[i][i]
                M[q] = [a - fc * c for a, c in zip(M[q], M[i])]
    return [M[i][k] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(k)]


def predict(w, r, shrink):
    return shrink * sum(a * b for a, b in zip(w, r["x"]))


def fit(train):
    """(weights, shrink, base): the shrink is chosen on the training rows only (last training year held out)."""
    base = age_base(train)
    shrink = 1.0
    yrs = sorted({r["year"] for r in train})
    if len(yrs) >= 2:
        hold = yrs[-1]
        te = [r for r in train if r["year"] == hold]
        first = min(r["anchor"] for r in te)
        tr = [r for r in train if r["end"] <= first]
        if len(tr) >= 40 and te:
            b2 = age_base(tr)
            w2 = ridge(tr, b2)
            errs = {s: sum((target(r, b2) - predict(w2, r, s)) ** 2 for r in te) for s in SHRINKS}
            shrink = min(errs, key=errs.get)
    return ridge(train, base), shrink, base


def walk(rows, first_test, min_train=40):
    """{year: {"cut", "n", "calls", "right"}} for one version and position."""
    out = {}
    for ty in sorted({r["year"] for r in rows}):
        if ty < first_test:
            continue
        te = [r for r in rows if r["year"] == ty]
        first = min(r["anchor"] for r in te)
        tr = [r for r in rows if r["end"] <= first]
        if len(tr) < min_train or len(te) < 6:
            continue
        w, shrink, base = fit(tr)
        e0 = sum(target(r, base) ** 2 for r in te)
        e1 = sum((target(r, base) - predict(w, r, shrink)) ** 2 for r in te)
        big = [(predict(w, r, shrink), target(r, base)) for r in te if abs(predict(w, r, shrink)) >= BIG]
        out[ty] = {"cut": round(1 - e1 / e0, 4) if e0 else 0.0, "n": len(te), "calls": len(big),
                   "right": sum(1 for p, a in big if (p > 0) == (a > 0)), "e0": e0, "e1": e1}
    return out


def gate(by_year):
    yrs = sorted(by_year)[-GATE["years"]:]
    if not yrs:
        return {"pass": False, "why": "no test seasons"}
    e0 = sum(by_year[y]["e0"] for y in yrs)
    e1 = sum(by_year[y]["e1"] for y in yrs)
    cut = 1 - e1 / e0 if e0 else 0.0
    better = sum(1 for y in yrs if by_year[y]["cut"] > 0)
    calls = sum(by_year[y]["calls"] for y in yrs)
    right = sum(by_year[y]["right"] for y in yrs)
    n = sum(by_year[y]["n"] for y in yrs)
    hit = right / calls if calls else 0.0
    fails = [w for w, ok in (("error cut under 3%", cut >= GATE["cut"]),
                             (f"better in only {better} of {len(yrs)} seasons", better >= min(GATE["years_better"], len(yrs)) and len(yrs) >= GATE["years"]),
                             (f"big calls right {right} of {calls}", calls >= GATE["calls"] and hit >= GATE["hit"]),
                             (f"only {n} test cases", n >= GATE["n"])) if not ok]
    return {"pass": not fails, "cut": round(cut, 4), "years_better": better, "years": len(yrs), "calls": calls,
            "right": right, "hit": round(hit, 3), "n": n, "why": "; ".join(fails) or "passed all four parts"}


def train(rows, first_test=2022):
    relative(rows)
    model = {"versions": {"in": {}, "off": {}}, "rookie": {}}
    for ver in ("in", "off", "rookie"):
        for pos in pv_data.SKILL:
            sel = [r for r in rows if r["ver"] == ver and r["pos"] == pos]
            if len(sel) < (30 if ver == "rookie" else 60):
                continue
            by_year = walk(sel, first_test, 20 if ver == "rookie" else 40)
            g = gate(by_year)
            w, shrink, base = fit(sel)
            e = {"w": [round(x, 5) for x in w], "shrink": shrink, "gate": g, "rows": len(sel),
                 "by_year": {str(y): {k: v for k, v in d.items() if k not in ("e0", "e1")} for y, d in by_year.items()}}
            (model["rookie"] if ver == "rookie" else model["versions"][ver])[pos] = e
    return model


def report(model):
    lines = []
    for ver, block in (("in-season", model["versions"]["in"]), ("offseason", model["versions"]["off"]), ("rookie trial", model["rookie"])):
        for pos, e in block.items():
            g = e["gate"]
            yrs = "; ".join(f"{y}: {100 * d['cut']:+.0f}% ({d['right']}/{d['calls']})" for y, d in sorted(e["by_year"].items()))
            lines.append(f"{ver} {pos}: {'LIVE' if g['pass'] else 'market'} | error cut {100 * g.get('cut', 0):+.1f}%, "
                         f"better in {g.get('years_better', 0)} of {g.get('years', 0)}, big calls {g.get('right', 0)}/{g.get('calls', 0)}, "
                         f"n {g.get('n', 0)}, shrink {e['shrink']} | {g['why']} | {yrs}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dp", required=True, help="clone of github.com/dynastyprocess/data")
    ap.add_argument("--write", action="store_true", help="write state/pv_model.json")
    ap.add_argument("--report", help="also write the test table to this file")
    ap.add_argument("--first", type=int, default=2020)
    args = ap.parse_args(argv)
    ids = pv_data.ids()
    dp = DP(args.dp, ids)
    last = dp.last.year
    years = list(range(args.first, last + 1))
    sw = {y: pv_data.week_stats(y, max_age=30 * pv_data.DAY) for y in years if y < last or dp.last.month >= 10}
    ss = {y - 1: pv_data.season_stats(y - 1, max_age=30 * pv_data.DAY) for y in years}
    draft = pv_data.draft()
    rows = rows_for(dp, sw, ss, draft, years)
    model = train(rows)
    model.update({"trained": iso(now_utc()), "market_history_through": dp.last.isoformat(),
                  "rows": collections.Counter(r["ver"] for r in rows), "gate_rules": GATE})
    out = report(model)
    print("\n".join(out))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(f"# Player-value model test ({model['trained']}, market history through {model['market_history_through']})\n\n")
            fh.write("\n".join(f"- {l}" for l in out) + "\n")
    if args.write:
        save_json(MODEL_FILE, json.loads(json.dumps(model, default=str)))
        print("wrote", MODEL_FILE)
    return model


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
