"""Rest-of-season ranks (docs/data/ros.json) from experts who updated recently and rank well for accuracy.

Michael, Nov 14: "we need to be cognizant of when experts last updated their rankings. I don't need rest of season
rankings that haven't been updated in recent months. The consensus one is probably ok but i always prefer to filter for
more accurate ones that make sense whenever possible." (fantasy-rules.md rule 15)

FantasyPros' public ROS pages carry, for every expert on that page, the date he last updated and his accuracy rank this
season (expertGroupsData), plus the default consensus (ecrData; a small panel FantasyPros picks). Custom expert filters
need a FantasyPros account, so this builds its own consensus instead: each FRESH (updated in the last MAX_AGE_DAYS) and
ACCURATE (2026 in-season accuracy rank <= MAX_ACC_RANK) expert whose own ROS page is public, averaged rank by rank.
Fewer than MIN_EXPERTS such experts at a position: the FantasyPros default consensus is used and the file says so.

    py -m shq.ros refresh            ranks only (no AI): updates rank/fp_rank/panel in docs/data/ros.json, keeps the why lines
    py -m shq.ros merge <file.json>  adds why lines a research run wrote ({key: {why, tier, basis, source, news_date, dynasty}})

Read-only on FantasyPros: public pages, no sign-in, a handful of requests per run."""
import datetime as dt
import html
import json
import re
import sys
import time

from .common import DATA, load_json, session

OUT = DATA / "ros.json"
MAX_AGE_DAYS = 7          # an expert's ROS ranks count only if he updated them in the last week
MAX_ACC_RANK = 50         # ... and he's in FantasyPros' top 50 for 2026 in-season accuracy
MIN_EXPERTS = 3           # fewer usable experts at a position: fall back to FantasyPros' default consensus
BASE = "https://www.fantasypros.com/nfl/rankings/"
PAGES = {"QB": "ros-qb.php", "RB": "ros-ppr-rb.php", "WR": "ros-ppr-wr.php", "TE": "ros-ppr-te.php", "K": "ros-k.php", "DEF": "ros-dst.php"}
FP_POS = {"DEF": "DST"}
TEAM_FIX = {"JAC": "JAX", "WSH": "WAS"}
UA = {"User-Agent": "Mozilla/5.0 (sports-hq rest-of-season ranks; read-only)"}


def key(name, pos):
    return re.sub(r"[^a-z]", "", (name or "").lower()) + "|" + pos


def _var(text, name):
    m = re.search(r"var " + name + r"\s*=\s*", text)
    if not m:
        return None
    return json.JSONDecoder().raw_decode(text[m.end():])[0]


def _get(url):
    for i in range(3):
        try:
            r = session.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception:
            if i == 2:
                raise
            time.sleep(2 * (i + 1))


def expert_ranks(text):
    """[(player name, team, rank)] from one expert's public ROS page (a plain HTML table)."""
    out = []
    for m in re.finditer(r'<tr><td class="center">(\d+)</td>\s*<td class="player-label">.*?fp-player-name="([^"]+)".*?</td>\s*'
                         r'<td class="center">([A-Z]{2,3})?</td>', text, re.S):
        out.append((html.unescape(m.group(2)), TEAM_FIX.get(m.group(3) or "", m.group(3) or ""), int(m.group(1))))
    return out


def panel(experts, now):
    """The fresh, accurate experts with a public page, best accuracy first."""
    keep = []
    for e in experts:
        age = (now - dt.datetime.fromtimestamp(int(e.get("last_updated") or 0), dt.timezone.utc)).days
        acc = str(e.get("in_season_rank") or "")
        if age <= MAX_AGE_DAYS and acc.isdigit() and int(acc) <= MAX_ACC_RANK and e.get("rankings_link"):
            keep.append({"id": e["id"], "name": e["name"], "site": e.get("site"), "accuracy_rank": int(acc), "age_days": age,
                         "updated": dt.datetime.fromtimestamp(int(e["last_updated"]), dt.timezone.utc).strftime("%b %d"),
                         "link": e["rankings_link"]})
    return sorted(keep, key=lambda x: x["accuracy_rank"])


def consensus(lists):
    """Average rank across experts (a player an expert leaves out counts as one past his last rank), best first."""
    names, teams = {}, {}
    for lst in lists:
        for n, t, _ in lst:
            names[n] = n
            teams[n] = teams.get(n) or t
    rows = []
    for n in names:
        rs = []
        for lst in lists:
            hit = next((r for nn, _, r in lst if nn == n), None)
            rs.append(hit if hit is not None else len(lst) + 1)
        rows.append((sum(rs) / len(rs), n, teams[n]))
    rows.sort()
    return [(n, t, i + 1, round(avg, 1)) for i, (avg, n, t) in enumerate(rows)]


def position(pos, now, fetch=_get):
    page = fetch(BASE + PAGES[pos])
    ecr, eg = _var(page, "ecrData") or {}, _var(page, "expertGroupsData") or {}
    fp = [(p["player_name"], TEAM_FIX.get(p.get("player_team_id"), p.get("player_team_id")), int(p["rank_ecr"])) for p in ecr.get("players", [])]
    chosen = panel(eg.get("expert_data", []), now)
    lists, used = [], []
    for e in chosen:
        link = re.sub(r"position=[A-Z]+", "position=" + FP_POS.get(pos, pos), e["link"])
        try:
            got = expert_ranks(fetch(link))
        except Exception as ex:
            print(f"{pos}: {e['name']} skipped: {ex!r}")
            continue
        if got:
            lists.append(got)
            used.append({k: e[k] for k in ("name", "site", "accuracy_rank", "updated")})
    mine = consensus(lists) if len(lists) >= MIN_EXPERTS else None
    return {"fp": fp, "mine": mine, "panel": used, "fp_panel": ecr.get("total_experts"), "fp_updated": ecr.get("last_updated")}


ALIAS = {"zonovanknight": "bamknight"}     # same player under two names


def _norm(name):
    """Name for matching: letters only, without Jr./Sr./II-style endings (FantasyPros writes "KC Concepcion Jr.")."""
    n = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", (name or "").lower().strip())
    n = re.sub(r"[^a-z]", "", n)
    return ALIAS.get(n, n)


def _match(entry, rows, pos):
    """A ros.json entry's row in a ranking: by name, or by team for a defense."""
    if pos == "DEF":
        return next((r for r in rows if r[1] == entry.get("team")), None)
    k = _norm(entry.get("name"))
    return next((r for r in rows if _norm(r[0]) == k), None)


def refresh(now=None, fetch=_get, path=OUT):
    now = now or dt.datetime.now(dt.timezone.utc)
    data = load_json(path, {"players": {}})
    method = {}
    for pos in PAGES:
        try:
            got = position(pos, now, fetch)
        except Exception as ex:
            print(f"{pos}: page failed, ranks kept as they were: {ex!r}")
            continue
        method[pos] = {"experts": got["panel"], "fallback": got["mine"] is None, "fantasypros_panel": got["fp_panel"],
                       "fantasypros_updated": got["fp_updated"]}
        for k, p in data["players"].items():
            if p.get("pos") != pos:
                continue
            fp = _match(p, got["fp"], pos)
            mine = _match(p, got["mine"], pos) if got["mine"] else None
            p["fp_rank"] = f"{pos}{fp[2]}" if fp else None
            p["rank"] = f"{pos}{mine[2]}" if mine else p["fp_rank"]
            p["rank_basis"] = (f"{len(got['panel'])} experts updated in the last {MAX_AGE_DAYS} days and in the top {MAX_ACC_RANK} for accuracy"
                               if mine else f"FantasyPros default consensus ({got['fp_panel']} experts; too few fresh, accurate experts)")
    data["ranks_updated"] = now.isoformat(timespec="minutes")
    data["method"] = method
    data["_about_ranks"] = (f"rank: average of the FantasyPros experts who updated their rest-of-season ranks in the last {MAX_AGE_DAYS} days AND "
                            f"rank in the top {MAX_ACC_RANK} for 2026 in-season accuracy (their own public pages; list per position in method). "
                            "fp_rank: FantasyPros' default consensus. Michael's rule 15 (fantasy-rules.md).")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return data


def merge(src, path=OUT):
    """Why lines from a research run: {key: {why, tier, basis, source, news_date, dynasty, name, pos, team}}."""
    data = load_json(path, {"players": {}})
    new = json.loads(open(src, encoding="utf-8").read())
    for k, v in (new.get("players", new)).items():
        if "|" not in k or not v.get("why"):
            continue
        data["players"].setdefault(k, {}).update({x: v[x] for x in v if x in ("why", "tier", "basis", "source", "news_date", "dynasty", "name", "pos", "team")})
    data["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return data


if __name__ == "__main__":
    if sys.argv[1:2] == ["refresh"]:
        d = refresh()
        for pos, m in d["method"].items():
            print(pos, "fallback to FantasyPros default" if m["fallback"] else ", ".join(f"{e['name']} (#{e['accuracy_rank']}, {e['updated']})" for e in m["experts"]))
    elif sys.argv[1:2] == ["merge"] and len(sys.argv) > 2:
        merge(sys.argv[2])
        print("merged")
    else:
        print(__doc__)
