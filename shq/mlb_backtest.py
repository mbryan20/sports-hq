"""Backtest of the baseball leading-indicator signals (plans/baseball.md): would each have flagged risers early,
and does it beat a simple results-only baseline?

Checkpoints: May 15 and Jun 30 of 2025 and 2026. At each, a signal sees only games before it; it is judged on the
rest of that season (ROS). Every signal is compared with the baseline a manager already has: the player's results
so far (wOBA, K%) in the same bracket. A signal that doesn't beat its baseline is dropped (plans/baseball.md says which).

Market test (2026 only, the season we have 3-Ball's full transaction log for): for each flagged player who was a
free agent in 3-Ball at the checkpoint and turned into a useful player, did a 3-Ball team add him later, and how long
after the flag? ESPN keeps no ownership history, so 3-Ball's own adds are the clock (from now on Sports HQ saves a
daily % rostered reading so future backtests use ESPN-wide ownership).

Free reads only (shq/mlb_data.py, cached in .cache/mlb). Run: py -m shq.mlb_backtest [--write]
(--write saves reviews/<date>-mlb-signal-backtest.md and docs/data/mlb_backtest.json)."""
import datetime as dt
import json
import statistics as stx
import sys
import unicodedata

from . import mlb_data as md
from .common import ROOT, get_json

SEASONS = {2025: ("2025-03-18", "2025-09-28"), 2026: ("2026-03-25", "2026-09-27")}
CHECKS = ("05-15", "06-30")
MIN_EARLY = {"05-15": 60, "06-30": 120}       # PA (hitters) / batters faced (pitchers) before the checkpoint
MIN_ROS = 100
FB = {"hfPT": "FF|SI|"}                       # four-seam + sinker for velocity
LEAGUE = 142878                               # 3-Ball Dynasty baseball (public)


def day(s):
    return dt.date.fromisoformat(s)


def shift(s, n):
    return (day(s) + dt.timedelta(days=n)).isoformat()


def by_id(rows, min_pa=0):
    return {int(r["player_id"]): r for r in rows if isinstance(r.get("pa"), float) and r["pa"] >= min_pa}


def rate(hits, n):
    return f"{hits}/{n} ({100 * hits / n:.0f}%)" if n else "0/0"


def corr(xs, ys):
    if len(xs) < 3:
        return float("nan")
    return stx.correlation(xs, ys)


def windows(season, check):
    start, end = SEASONS[season]
    c = f"{season}-{check}"
    return start, c, shift(c, 1), end


# ---------------------------------------------------------------- hitters

def hitters(season, check):
    start, c, ros0, end = windows(season, check)
    early = by_id(md.savant("batter", start, c), MIN_EARLY[check])
    ros = by_id(md.savant("batter", ros0, end), MIN_ROS)
    prior = by_id(md.savant("batter", *SEASONS.get(season - 1, (f"{season - 1}-03-20", f"{season - 1}-10-01"))), 200)
    last14 = by_id(md.savant("batter", shift(c, -13), c))
    prev14 = by_id(md.savant("batter", shift(c, -27), shift(c, -14)))
    out = []
    for pid, e in early.items():
        r = ros.get(pid)
        p = prior.get(pid)
        out.append({"id": pid, "name": e["player_name"], "season": season, "check": check,
                    "woba": e["woba"], "xwoba": e["xwoba"], "brl": e["barrels_per_pa_percent"], "pa": e["pa"],
                    "ros_woba": r and r["woba"], "ros_pa": r["pa"] if r else 0,
                    "prior_woba": p and p["woba"], "prior_brl": p and p["barrels_per_pa_percent"],
                    "pa14": (last14.get(pid) or {}).get("pa", 0), "pa_prev14": (prev14.get(pid) or {}).get("pa", 0)})
    return out


def hitter_tests(rows):
    res = {}
    j = [r for r in rows if r["ros_woba"] is not None]
    # 1. xwOBA vs wOBA as a predictor of ROS wOBA
    res["predict"] = {"n": len(j), "r_woba": corr([r["woba"] for r in j], [r["ros_woba"] for r in j]),
                      "r_xwoba": corr([r["xwoba"] for r in j], [r["ros_woba"] for r in j]),
                      "r_blend": corr([(r["woba"] + r["xwoba"]) / 2 for r in j], [r["ros_woba"] for r in j])}
    # 2. buy-low: struggling (wOBA <= .310) and xwOBA 30+ points higher -> ROS wOBA up 20+ points
    low = [r for r in j if r["woba"] <= 0.310]
    flag = [r for r in low if r["xwoba"] - r["woba"] >= 0.030]
    rest = [r for r in low if r not in flag]
    up = lambda r: r["ros_woba"] - r["woba"] >= 0.020
    good = lambda r: r["ros_woba"] >= 0.330
    res["buy_low"] = {"flag": len(flag), "flag_up": sum(map(up, flag)), "flag_good": sum(map(good, flag)),
                      "base": len(rest), "base_up": sum(map(up, rest)), "base_good": sum(map(good, rest))}
    # 3. sell-high: hot (wOBA >= .350) and wOBA 30+ points over xwOBA -> ROS wOBA down 20+ points
    hot = [r for r in j if r["woba"] >= 0.350]
    sflag = [r for r in hot if r["woba"] - r["xwoba"] >= 0.030]
    srest = [r for r in hot if r not in sflag]
    down = lambda r: r["woba"] - r["ros_woba"] >= 0.020
    still = lambda r: r["ros_woba"] >= 0.340
    res["sell_high"] = {"flag": len(sflag), "flag_down": sum(map(down, sflag)), "flag_still": sum(map(still, sflag)),
                        "base": len(srest), "base_down": sum(map(down, srest)), "base_still": sum(map(still, srest))}
    # 4. barrel jump vs last season (skill) against a wOBA jump (results) -> ROS wOBA 20+ over last season
    k = [r for r in j if r["prior_woba"] is not None]
    rose = lambda r: r["ros_woba"] - r["prior_woba"] >= 0.020
    b = [r for r in k if r["brl"] - r["prior_brl"] >= 2.5]
    w = [r for r in k if r["woba"] - r["prior_woba"] >= 0.030]
    both = [r for r in b if r in w]
    wonly = [r for r in w if r not in b]
    res["barrel_jump"] = {"n": len(k), "all_rose": sum(map(rose, k)), "brl": len(b), "brl_rose": sum(map(rose, b)),
                          "woba": len(w), "woba_rose": sum(map(rose, w)), "both": len(both),
                          "both_rose": sum(map(rose, both)), "woba_only": len(wonly),
                          "woba_only_rose": sum(map(rose, wonly))}
    # 5. playing time: 40+ PA in the last 14 days after under 25 in the 14 before -> a regular the rest of the way
    regular = lambda r: r["ros_pa"] >= (300 if r["check"] == "05-15" else 220)
    pt = [r for r in rows if r["pa14"] >= 40 and r["pa_prev14"] < 25]
    old = [r for r in rows if r["pa14"] >= 40 and r["pa_prev14"] >= 40]
    res["playing_time"] = {"flag": len(pt), "flag_regular": sum(map(regular, pt)),
                           "already": len(old), "already_regular": sum(map(regular, old))}
    return res


# ---------------------------------------------------------------- pitchers

def pitchers(season, check):
    start, c, ros0, end = windows(season, check)
    pr = SEASONS.get(season - 1, (f"{season - 1}-03-20", f"{season - 1}-10-01"))
    early = by_id(md.savant("pitcher", start, c), MIN_EARLY[check])
    ros = by_id(md.savant("pitcher", ros0, end), MIN_ROS)
    prior = by_id(md.savant("pitcher", *pr), 200)
    fb_e = {int(r["player_id"]): r for r in md.savant("pitcher", start, c, FB) if r["pitches"] >= 75}
    fb_p = {int(r["player_id"]): r for r in md.savant("pitcher", *pr, FB) if r["pitches"] >= 300}
    out = []
    for pid, e in early.items():
        r, p = ros.get(pid), prior.get(pid)
        v0, v1 = (fb_p.get(pid) or {}).get("velocity"), (fb_e.get(pid) or {}).get("velocity")
        out.append({"id": pid, "name": e["player_name"], "season": season, "check": check,
                    "woba": e["woba"], "xwoba": e["xwoba"], "k": e["k_percent"], "bf": e["pa"],
                    "ros_woba": r and r["woba"], "ros_xwoba": r and r["xwoba"], "ros_k": r and r["k_percent"],
                    "ros_bf": r["pa"] if r else 0, "prior_xwoba": p and p["xwoba"], "prior_k": p and p["k_percent"],
                    "velo": v1 if isinstance(v1, float) else None, "prior_velo": v0 if isinstance(v0, float) else None})
    return out


def pitcher_tests(rows):
    res = {}
    j = [r for r in rows if r["ros_woba"] is not None]
    res["predict"] = {"n": len(j), "r_woba": corr([r["woba"] for r in j], [r["ros_woba"] for r in j]),
                      "r_xwoba": corr([r["xwoba"] for r in j], [r["ros_woba"] for r in j]),
                      "r_k": corr([r["k"] for r in j], [r["ros_woba"] for r in j])}
    # luck: getting hit (wOBA >= .330) but xwOBA 25+ points lower -> ROS wOBA against 20+ better
    bad = [r for r in j if r["woba"] >= 0.330]
    f = [r for r in bad if r["woba"] - r["xwoba"] >= 0.025]
    rest = [r for r in bad if r not in f]
    better = lambda r: r["woba"] - r["ros_woba"] >= 0.020
    good = lambda r: r["ros_woba"] <= 0.300
    res["unlucky"] = {"flag": len(f), "flag_better": sum(map(better, f)), "flag_good": sum(map(good, f)),
                      "base": len(rest), "base_better": sum(map(better, rest)), "base_good": sum(map(good, rest))}
    # velocity jump vs last season (skill) against a K% jump (results) -> ROS xwOBA 15+ better than last season
    k = [r for r in j if r["prior_xwoba"] is not None and r["velo"] and r["prior_velo"]]
    imp = lambda r: r["prior_xwoba"] - r["ros_xwoba"] >= 0.015
    v = [r for r in k if r["velo"] - r["prior_velo"] >= 1.0]
    kk = [r for r in k if r["k"] - r["prior_k"] >= 4.0]
    vd = [r for r in k if r["velo"] - r["prior_velo"] <= -1.0]
    worse = lambda r: r["ros_xwoba"] - r["prior_xwoba"] >= 0.015
    res["velo_jump"] = {"n": len(k), "all_imp": sum(map(imp, k)), "velo": len(v), "velo_imp": sum(map(imp, v)),
                        "k": len(kk), "k_imp": sum(map(imp, kk)),
                        "drop": len(vd), "drop_worse": sum(map(worse, vd)), "all_worse": sum(map(worse, k))}
    return res


# ---------------------------------------------------------------- market (3-Ball adds, 2026)

def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = s.replace(".", "").replace(" jr", "").replace(" ii", "").replace(" iii", "")
    if "," in s:                                      # Savant: "Last, First"
        last, first = s.split(",", 1)
        s = first.strip() + " " + last.strip()
    return " ".join(s.split())


def espn_url(season=2026):
    return f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/{season}/segments/0/leagues/{LEAGUE}"


def market_2026():
    """(espn pool {norm name: {id, owned}}, adds [(date, espn id)], rostered-at(date) -> set of espn ids)."""
    url = espn_url()
    hdr = {"x-fantasy-filter": json.dumps({"players": {"limit": 3000, "sortPercOwned": {"sortPriority": 1,
                                                                                       "sortAsc": False}}})}
    pool = get_json(url, {"view": "kona_player_info"}, headers=hdr).get("players") or []
    names = {norm(p["player"]["fullName"]): {"id": p["player"]["id"],
                                             "owned": (p["player"].get("ownership") or {}).get("percentOwned", 0)}
             for p in pool}
    now = {e["playerId"] for t in get_json(url, {"view": "mRoster"})["teams"] for e in t["roster"]["entries"]}
    moves = []
    for sp in range(0, 189):
        txt = md._cached(f"{url}|tx|{sp}", lambda: json.dumps(get_json(url, {"view": "mTransactions2",
                                                                              "scoringPeriodId": sp})))
        for t in json.loads(txt).get("transactions") or []:
            if t.get("status") != "EXECUTED" or t.get("type") not in ("FREEAGENT", "WAIVER", "TRADE_ACCEPT"):
                continue
            when = dt.datetime.fromtimestamp((t.get("processDate") or t["proposedDate"]) / 1000).date()
            for it in t.get("items") or []:
                if it["type"] in ("ADD", "DROP"):
                    moves.append((when, it["type"], it["playerId"]))

    def rostered_at(d):
        ids = set(now)
        for when, kind, pid in sorted(moves, reverse=True):
            if when > d:
                (ids.discard if kind == "ADD" else ids.add)(pid)
        return ids
    adds = [(w, pid) for w, k, pid in moves if k == "ADD"]
    return names, adds, rostered_at


def market_test(flags, useful, names, adds, rostered_at):
    """flags: [(row, check date)] -> how many were 3-Ball free agents, became useful, and got added later."""
    seen, free, hits, added, lead = set(), 0, 0, 0, []
    for r, d in flags:
        e = names.get(norm(r["name"]))
        if not e or r["id"] in seen:
            continue
        if e["id"] in rostered_at(d):
            continue
        seen.add(r["id"])
        free += 1
        if useful(r):
            hits += 1
            later = sorted(w for w, pid in adds if pid == e["id"] and w > d)
            if later:
                added += 1
                lead.append((later[0] - d).days)
    return {"free_agents_flagged": free, "became_useful": hits, "added_later": added,
            "median_days_before_add": stx.median(lead) if lead else None}


# ---------------------------------------------------------------- run

def run():
    H, P = [], []
    for season in SEASONS:
        for check in CHECKS:
            H += hitters(season, check)
            P += pitchers(season, check)
    out = {"hitters": {}, "pitchers": {}}
    for season in list(SEASONS) + ["all"]:
        hs = [r for r in H if season == "all" or r["season"] == season]
        ps = [r for r in P if season == "all" or r["season"] == season]
        out["hitters"][str(season)] = hitter_tests(hs)
        out["pitchers"][str(season)] = pitcher_tests(ps)
    names, adds, rostered_at = market_2026()
    h26 = [r for r in H if r["season"] == 2026 and r["ros_woba"] is not None]
    p26 = [r for r in P if r["season"] == 2026 and r["ros_woba"] is not None]
    cd = lambda r: day(f"2026-{r['check']}")
    useful_h = lambda r: r["ros_woba"] >= 0.340 and r["ros_pa"] >= 150
    useful_p = lambda r: r["ros_xwoba"] <= 0.290 and r["ros_bf"] >= 150
    out["market_2026"] = {
        "buy_low": market_test([(r, cd(r)) for r in h26 if r["woba"] <= 0.310 and r["xwoba"] - r["woba"] >= 0.030],
                               useful_h, names, adds, rostered_at),
        "buy_low_base": market_test([(r, cd(r)) for r in h26 if r["woba"] <= 0.310 and r["xwoba"] - r["woba"] < 0.030],
                                    useful_h, names, adds, rostered_at),
        "barrel_jump": market_test([(r, cd(r)) for r in h26 if r["prior_brl"] is not None
                                    and r["brl"] - r["prior_brl"] >= 2.5], useful_h, names, adds, rostered_at),
        "woba_jump": market_test([(r, cd(r)) for r in h26 if r["prior_woba"] is not None
                                  and r["woba"] - r["prior_woba"] >= 0.030], useful_h, names, adds, rostered_at),
        "playing_time": market_test([(r, cd(r)) for r in h26 if r["pa14"] >= 40 and r["pa_prev14"] < 25],
                                    useful_h, names, adds, rostered_at),
        "velo_jump": market_test([(r, cd(r)) for r in p26 if r["velo"] and r["prior_velo"]
                                  and r["velo"] - r["prior_velo"] >= 1.0], useful_p, names, adds, rostered_at),
        "k_jump": market_test([(r, cd(r)) for r in p26 if r["prior_k"] is not None and r["k"] - r["prior_k"] >= 4.0],
                              useful_p, names, adds, rostered_at),
        "unlucky_p": market_test([(r, cd(r)) for r in p26 if r["woba"] >= 0.330 and r["woba"] - r["xwoba"] >= 0.025],
                                 useful_p, names, adds, rostered_at),
    }
    return out


def main():
    out = run()
    print(json.dumps(out, indent=1, default=str))
    if "--write" in sys.argv:
        (ROOT / "docs" / "data" / "mlb_backtest.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
