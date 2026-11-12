"""Entry point for every scheduled run: refresh lineups, run the injury watch when inside a
pre-kickoff window, post the daily digest at 8am CT, build the Weekly tab on Tuesday 7am CT, publish the weekend
wrap-up (Sunday night, final Tuesday 8am). Exits non-zero on any real error so the workflow's failure step pushes an alert."""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import traceback

from . import advice, darko, digest, espn, experts, guillotine, nba_lineup, nba_values, notify, pushes, radar, wrapup
from . import espn_fantasy as ef
from .common import DATA, ROOT, STATE, ct_label, iso, load_json, now_utc, parse_iso, save_json
from .config import ESPN_PRIVATE, LEAGUES, TZ, WATCH_LEAD_HOURS, WEEKLY_HOUR, WEEKLY_WEEKDAY
from .leagues import (Context, EspnLeague, LeagueOver, SavedYahooLeague, SleeperLeague, SnapshotMissing,
                      YahooLeague, view)
from .notify import push, push_once
from .status import OUTISH
from .swap import MIN_FILL, fa_over_bench, plan_injury_swaps, q_tag, slot_fa, strength_text
from .yahoo import YahooPending, YahooWriteDenied


SAVED_ROSTER = STATE / "kosmonauts_roster.json"   # written by the laptop task (shq.save_roster)
ROSTER_STALE = dt.timedelta(hours=30)


KEEP_ALIVE_AHEAD = dt.timedelta(hours=3)


def keep_watching(status, now):
    """Should the workflow's loop do another pass in 10 minutes? Yes while a watch window is open
    or opens within KEEP_ALIVE_AHEAD — GitHub drops many scheduled triggers, so a run that does
    start carries the whole game-day window instead of trusting the next cron."""
    lead = dt.timedelta(hours=WATCH_LEAD_HOURS)
    return any(parse_iso(k) - lead <= now + KEEP_ALIVE_AHEAD and parse_iso(k) > now
               for k in status.get("upcoming_kickoffs") or [])


def watch_active(ctx, now):
    return any(k - dt.timedelta(hours=WATCH_LEAD_HOURS) <= now < k for k in ctx.kickoffs())


def label(p):
    extra = f" ({p['why']})" if p.get("why") else ""
    return f"{p['name']}{extra}{digest.cite(p)}"


def league_view(league, now):
    """Lineup tab JSON plus the "what to do" block. Advice is best-effort: a bug there never blocks the
    lineup data or the injury watch."""
    try:
        tips = advice.build(league, now)
        if tips is not None and getattr(league, "guillotine", None):
            tips["guillotine"] = league.guillotine
            if tips.get("experts"):   # tag the bid players too (shq/experts.py); never costs the tab its advice
                try:
                    g = league.guillotine or {}
                    bids = list(g.get("bids") or []) + list((g.get("freed") or {}).get("players") or [])
                    tips["experts"]["names"].update(
                        experts.extra_names(league, [b.get("name") for b in bids] + [b.get("drop") for b in bids]))
                except Exception:
                    traceback.print_exc()
    except Exception:
        traceback.print_exc()
        tips = None
    return view(league, tips)


def better_news(league):
    """ESPN's injury report sometimes carries only a bare status ("questionable") as its note. For my own
    players with a status, swap that for the player's latest ESPN news headline so the citation says why."""
    game = "fba" if getattr(league, "sport", "nfl") == "nba" else "ffl"
    for p in league.starters + league.bench + getattr(league, "ir_blocked", []):
        n = p.get("news")
        if not (p["status"] and n and len(n["note"]) < 30):
            continue
        m = re.search(r"/id/(\d+)", n.get("url") or "")
        try:
            fresh = m and espn.player_news(m.group(1), game, p["name"])
        except Exception:
            traceback.print_exc()
            continue
        if fresh:
            p["news"] = {**n, **fresh}


def radar_push(queue, notes):
    """NBA trend radar: one push a day for every NBA league together, for rising free agents in a category I need
    (shq/radar.py, Q-049). `queue` is [(league, league view)]. Never fails the run."""
    try:
        sent = radar.send_all([(lg, (v or {}).get("advice")) for lg, v in queue
                               if getattr(lg, "sport", "nfl") == "nba"])
        if sent:
            notes.append(f"radar push: {sent}")
    except Exception:
        traceback.print_exc()


def guillotine_odds(league, ctx, now):
    """Survival odds + bid guidance for a guillotine league. Best-effort like the advice: on a bug the tab
    keeps the plain projected standing."""
    try:
        g = league.guillotine = guillotine.analyze(league, ctx, now)
        if not g:
            return
        # the simulated best-lineup standing replaces the set-lineup one, so tab, digest and push agree
        league.standing = {"rank": g["rank"], "n": g["n"], "gap": g["gap"], "cut": g["cut"]}
        alert = digest.danger_push(league)
        if alert:
            push_once(*alert, priority=4, tags=["warning"])
    except Exception:
        traceback.print_exc()


def injury_watch(league, now):
    actions = []
    for item in plan_injury_swaps(league.starters, league.bench, now, WATCH_LEAD_HOURS):
        out, inn, slot = item["out"], item["in"], item["slot"]
        key = f"{league.key}:w{league.week}:{out['id']}"
        locks = ct_label(out["kickoff"])
        nba = getattr(league, "sport", "nfl") == "nba"
        # NBA: an Out the official injury report backs (a rest day, a late scratch) gets at most the day's one lineup
        # push (shq/nba_lineup.py); once that has gone out, it's on the site only, never a second push (Q-058)
        if nba and (out.get("gd") or {}).get("src") == "nba" and nba_lineup.pushed_today(now):
            actions.append(f"site only (after today's NBA lineup push): {out['name']}")
            continue
        # football: a free agent is the better fix when the bench fill-in projects under MIN_FILL or trails him by
        # FA_EDGE+ (same rule as the digest's lineup fixes); a sub-MIN_FILL fill-in isn't worth swapping in
        # guillotine with War Room v2 current: only players addable now, never a pending waiver claim (digest.fix_pool)
        fa = league.best_fa(out["positions"], now) if nba else slot_fa(slot, digest.fix_pool(league), now)
        better = "" if nba or not (inn and fa_over_bench(inn, fa)) else \
            f" Better: add {fa['name']} ({fa['team']}{q_tag(fa)}, {fa['proj']} proj) and start him — add/drop manually."
        weak = None
        if better and inn["proj"] < MIN_FILL:
            weak, inn = inn, None
        if inn and league.can_write:
            try:
                if os.environ.get("DRY_RUN") == "1":
                    ok = True
                    print(f"[dry-run] would swap {out['name']} -> {inn['name']} ({slot})")
                else:
                    ok = league.execute_swap(out, inn)
                if ok:
                    push(f"{league.name}: lineup fixed", f"Swapped {out['name']} → {inn['name']} ({slot}). "
                         f"{out['name']}: {out['why']}.{digest.cite(out)}{better}", priority=4, tags=["arrows_counterclockwise"])
                    actions.append(f"swapped {out['name']} -> {inn['name']}")
                    continue
                push_once(key + ":unconfirmed", f"{league.name}: CHECK LINEUP",
                          f"Tried {out['name']} → {inn['name']} ({slot}) but the roster read-back didn't match. "
                          f"Please check before {locks}.", priority=5, tags=["warning"])
                actions.append(f"swap unconfirmed {out['name']}")
                continue
            except YahooWriteDenied:
                league.can_write = False
        if inn:
            push_once(key + ":swap", f"{league.name}: make this swap",
                      f"Bench {label(out)} → start {inn['name']} ({strength_text(inn)}) at {slot}.{better} Locks {locks}.",
                      priority=4, tags=["rotating_light"])
            actions.append(f"suggested {out['name']} -> {inn['name']}")
        else:
            if fa:
                tip = f"Best FA: {fa['name']} ({fa['team']}, {strength_text(fa)}) — add/drop manually."
            else:
                tip = "No playable FA found."
            bench = (f"your best bench fit, {weak['name']}, projects {strength_text(weak)}" if weak
                     else f"no healthy bench player fits {slot}")
            push_once(key + ":fa", f"{league.name}: no healthy bench {slot}",
                      f"{label(out)} is out and {bench}. {tip} Locks {locks}.",
                      priority=4, tags=["rotating_light"])
            actions.append(f"no bench for {out['name']}")
    return actions


def weekly_due(now, last_generated):
    local = now.astimezone(TZ)
    anchor = (local - dt.timedelta(days=(local.weekday() - WEEKLY_WEEKDAY) % 7)).replace(
        hour=WEEKLY_HOUR, minute=0, second=0, microsecond=0)
    if anchor > local:
        anchor -= dt.timedelta(days=7)
    return last_generated is None or last_generated < anchor


def start_sit_lines(league, fixes=None):
    """Weekly tab start/sit, rebuilt every run so an injury status is never days old. `fixes` is the league page's
    live fix list (advice["fixes"]): when given, its lines lead (a bye QB's "add <free agent> and start him", an IR
    starter's fix) and the start/sit upgrades cover only healthy starters, so the plan says what the league page says
    (Q-048). All fixes are kept; upgrades fill up to 3 lines."""
    if getattr(league, "sport", "nfl") == "nba":
        return nba_weekly_section(league)["start_sit"]
    from .swap import start_sit
    if fixes is not None:
        moves = [f"Start {b['name']} ({b['proj']}) over {s['name']} ({s['proj']}) at {s['slot']}"
                 for s, b, _ in start_sit(league.starters, league.bench) if not advice._dead(s)]
        ss = list(fixes) + moves[:max(0, 3 - len(fixes))]
        live = round(sum(p["proj"] for p in league.starters if not advice._dead(p)), 1)
        return ss or [f"Lineup is optimal by projections ({live} pts)."]
    ss = [f"Start {b['name']} ({b['proj']}) over {s['name']} ({'BYE' if s['bye'] else s['status'] or s['proj']}) at {s['slot']}"
          + (digest.cite(s) if s["status"] and not s["bye"] else "")
          for s, b, _ in start_sit(league.starters, league.bench)]
    return ss[:3] or [f"Lineup is optimal by projections ({round(sum(p['proj'] for p in league.starters), 1)} pts)."]


def _advice(view):
    """A league view's live "what to do" block, or None when this run couldn't build it (stale or pending league)."""
    if not view or view.get("stale") or view.get("pending"):
        return None
    return view.get("advice") or None


# an NBA swap after an IR fix reads "First move X out of IR (...); then drop A (...), add B (..." (shq/nba_swaps.py)
ADD_RE = re.compile(r"^(?:First move .+?; then )?(?:[Dd]rop (?P<drop1>.+?) \(.*?\), add |Add )?(?P<add>.+?) \(")
DROP_RE = re.compile(r"\) (?:for|over) (?P<drop>.+?) \(|, drop (?P<drop2>.+?) \(")


def add_key(line):
    """(player added, player dropped) named by a Weekly/league-page add line, so Tuesday's plan can be compared with
    the live list without the numbers (values, projections) that move every run. Unparsed lines key on their text."""
    m = ADD_RE.match(line or "")
    if not m:
        return (line, None)
    d = DROP_RE.search(line[m.end():])
    drop = m.group("drop1") or (d and (d.group("drop") or d.group("drop2")))
    return (m.group("add").strip(), (drop or "").strip() or None)


def live_adds(sec, adv):
    """Q-048: the Weekly plan's adds follow the league page's live list (advice["adds"], rebuilt every run). Tuesday's
    7am list stays as `plan_adds`; `plan_changed` holds its lines whose add or drop the live list no longer makes."""
    if not adv or not adv.get("adds"):
        return
    sec.setdefault("plan_adds", list(sec.get("adds") or []))
    sec["adds"] = list(adv["adds"][:3])
    now_keys = {add_key(a) for a in sec["adds"]}
    sec["plan_changed"] = [a for a in sec["plan_adds"] if add_key(a) not in now_keys
                           and not a.startswith("No free agent")]


def refresh_weekly(weekly, leagues, views, now):
    """Every run between Tuesday plans: start/sit from the live fixes and upgrades, adds from the live league page."""
    by_name = {lg.name: lg for lg in leagues}
    for sec in weekly.get("leagues", []):
        try:
            adv = _advice(views.get(sec["name"]))
            if sec["name"] in by_name:
                sec["start_sit"] = start_sit_lines(by_name[sec["name"]], adv.get("fixes") if adv else None)
            live_adds(sec, adv)
        except Exception:
            traceback.print_exc()
    weekly["start_sit_updated"] = iso(now)
    return weekly


def weekly_section(league, adv=None):
    """Tuesday's plan for one football league. `adv` is the league page's advice from this same run: its fixes lead
    the start/sit and its adds are the plan's adds, so the two pages start the week identical (Q-048)."""
    from .swap import fa_adds
    ss = start_sit_lines(league, adv.get("fixes") if adv else None)
    if adv and adv.get("adds"):
        adds = list(adv["adds"])
    elif advice.valued(league):  # same rest-of-season list as the league tab
        adds = advice.adds(league)
    else:
        roster = league.starters + league.bench
        adds = [f"Add {fa['name']} ({fa['positions'][0]}, {fa['team']}, {fa['proj']})"
                + (f" over {who['name']} ({who['status'] if who['status'] in OUTISH else who['proj']})" if who else "")
                for _, fa, who in fa_adds(roster, league.free_agents[:300])]
    if not adds:
        adds = ["No free agent projects above your current depth."]
    return {"name": league.name, "week": league.week, "start_sit": ss, "adds": adds[:3]}


def nba_weekly_section(league):
    """Category leagues have no point projections: plan around games played and health."""
    live = [p for p in league.starters + league.bench if p["status"] not in OUTISH]
    games = {p["name"]: league.games_in_matchup(p) for p in live}
    ss = [f"Bench {p['name']} ({p['status']}) — he can't play{digest.cite(p)}" for p in league.starters if p["status"] in OUTISH]
    few = sorted((g, n) for n, g in games.items() if any(s["name"] == n for s in league.starters))[:2]
    if few:
        ss.append("Fewest games left this week: " + ", ".join(f"{n} ({g})" for g, n in few))
    if not ss:
        ss = [f"{sum(games.values())} games left this week across your healthy players."]
    fas = sorted(((league.games_in_matchup(p), p["owned"], p) for p in league.free_agents if p["status"] not in OUTISH),
                 key=lambda t: (-t[0], -t[1]))[:3]
    adds = [f"Add {p['name']} ({'/'.join(p['positions'][:2])}, {p['team']}): {g} games left, {o}% owned" for g, o, p in fas]
    swaps = getattr(league, "swaps", None)   # drop/add swaps on category value (shq/nba_swaps.py) when values exist
    if swaps:
        adds = swaps["lines"] or ["No free agent beats anyone on your roster by enough this week."]
    return {"name": league.name, "week": league.week, "start_sit": ss[:3],
            "adds": adds or ["No free agent data in the latest snapshot."]}


def origin_digest():
    """When origin/main's digest.json was generated, or None: another run (a laptop kick beside a cron run, Q-029) may
    have built today's digest after this checkout."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, timeout=60, check=True, capture_output=True)
        out = subprocess.run(["git", "show", "origin/main:docs/data/digest.json"], cwd=ROOT, timeout=30, check=True,
                             capture_output=True, text=True, encoding="utf-8").stdout
        return parse_iso(json.loads(out).get("generated"))
    except Exception:
        return None


def digest_due(now, local_generated, origin=origin_digest):
    """Today's digest is due here unless this checkout or origin/main already has it (no second 8am push)."""
    return digest.due(now, local_generated) and digest.due(now, origin())


def refresh_digest(today, leagues, now, cards=None):
    """Q-048: after the day's 8am digest, every later run rebuilds its items in place from this run's leagues (the
    same digest.league_items the league pages' fixes come from), so the Today check never contradicts a league page.
    Leagues this run couldn't read keep their earlier items. Never pushes: the 8am push was the day's one, and the
    injury watch pushes a new OUT before kickoff. Returns the updated digest, or None when there's nothing to refresh
    (no digest from today yet, or no item changed)."""
    gen = parse_iso(today.get("generated"))
    if not gen or "items" not in today or gen.astimezone(TZ).date() != now.astimezone(TZ).date():
        return None
    fresh = {lg.name for lg in leagues} | {"Picks"}
    kept = [i for i in today["items"] if i.get("league") not in fresh]
    order = {c["name"]: n for n, c in enumerate(LEAGUES)}
    # sorted() is stable: each league's items keep their own order; leagues follow config, Picks last
    items = sorted(digest.build(leagues, now, cards) + kept, key=lambda i: order.get(i.get("league"), len(order)))
    if items == today["items"]:
        return None
    title, _ = digest.message(items)
    return {**today, "title": title, "items": items, "updated": iso(now)}


LAPTOP_KICK_FROM = dt.time(2, 50)       # the laptop's daily 2:55am model-health kick (\SportsHQ\Kick model health)
LAPTOP_CHECK_AFTER = dt.time(4, 0)


def gh_dispatches(workflow="model-health.yml"):
    """When the last few workflow_dispatch runs of a workflow were created, or None when that can't be read (outside
    GitHub Actions, or gh failed). run.yml gives gh its token and `actions: read`."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    try:
        out = subprocess.run(["gh", "run", "list", "--workflow", workflow, "--event", "workflow_dispatch", "-L", "5",
                              "--json", "createdAt"], cwd=ROOT, timeout=60, check=True, capture_output=True,
                             text=True, encoding="utf-8").stdout
        return [parse_iso(r["createdAt"]) for r in json.loads(out) if r.get("createdAt")]
    except Exception:
        traceback.print_exc()
        return None


KICK_SILENT = ("No laptop kick since 2:55am today: laptop off, Windows task broken, or token expired. GitHub's own "
               "schedule (hours late) is all that's running.")


def laptop_kicks(now, runs=gh_dispatches):
    """Q-037: the laptop starts the time-critical GitHub jobs, so GitHub checks the laptop. Its 2:55am model-health kick is
    never skipped, so it is the daily heartbeat: from 4am CT, if no model-health dispatch was created since 2:50am today,
    the row says "silent" and job_health hands that to the one laptop-outage push (shq/pushes.py, Q-049). A late start
    (laptop asleep at 2:55, the task ran on waking) counts as alive. Returns the footer's "Laptop kick" row, or None when
    the run list can't be read (then no alert either)."""
    times = runs()
    if times is None:
        return None
    local = now.astimezone(TZ)
    row = {"job": "Laptop kick (laptop, daily 2:55am)", "last": iso(max(times, default=None))}
    if local.time() >= LAPTOP_CHECK_AFTER:
        since = dt.datetime.combine(local.date(), LAPTOP_KICK_FROM, TZ)
        if not any(t >= since for t in times):
            row["silent"] = True
    return row


def job_health(now, kicks=laptop_kicks, outage=None):
    """When each laptop job last delivered, from what it committed. The cloud alerts on staleness: a silent kick goes
    on `outage` (this pass's laptop symptoms) for the one outage push."""
    jobs = []
    try:
        row = kicks(now)
        if row:
            if row.pop("silent", False) and outage is not None:
                outage.append(KICK_SILENT)
            jobs.append(row)
    except Exception:
        traceback.print_exc()
    roster = load_json(SAVED_ROSTER) or {}
    jobs.append({"job": "Kosmonauts roster (laptop, daily)", "last": roster.get("captured")})
    for cfg in ESPN_PRIVATE:
        snap = ef.load_snapshot(cfg["sport"], cfg["league_id"]) or {}
        jobs.append({"job": f"{cfg['name']} ESPN snapshot (laptop, daily)", "last": snap.get("captured")})
    cards = (load_json(ROOT / "picks" / "data" / "cards.json", {}) or {}).get("meta", {})
    jobs.append({"job": "Picks cards (laptop, Wed–Sat)", "last": cards.get("generated_iso")})
    return jobs


def main():
    now = now_utc()
    errors, notes, leagues = [], [], []
    if os.environ.get("TEST_PUSH") == "1":
        push("Sports HQ test push", f"Alerts are working. Sent from GitHub Actions at {ct_label(now)} CT.", tags=["white_check_mark"])
    status = {"last_run": iso(now), "dry_run": os.environ.get("DRY_RUN") == "1"}

    ctx = Context(now)
    status["week"] = ctx.week

    prev_views = (load_json(DATA / "lineups.json", {}) or {}).get("leagues", {})
    league_views, radar_queue, outage = {}, [], []
    for cfg in LEAGUES:
        name = cfg["name"]
        try:
            if cfg["platform"] == "yahoo":
                lg = YahooLeague(ctx)
            elif cfg["platform"] == "sleeper":
                lg = SleeperLeague(ctx, name, cfg.get("league_id"), cfg.get("format"))
            else:
                lg = EspnLeague(ctx, cfg)
                if lg.captured and now - lg.captured > ROSTER_STALE:   # one laptop-outage push (shq/pushes.py)
                    outage.append(pushes.stale_cause(name, lg.captured, "ESPN"))
                    notes.append(f"{name}: ESPN snapshot is stale")
            lg.dynasty = bool(cfg.get("dynasty"))
            lg.assets = bool(cfg.get("assets"))  # 3-Ball: picks and minors from the league sheet
            if cfg.get("format") == "guillotine":
                guillotine_odds(lg, ctx, now)
            better_news(lg)
            leagues.append(lg)
            league_views[name] = league_view(lg, now)
            radar_queue.append((lg, league_views[name]))
            prev = prev_views.get(name) or {}
            if cfg["platform"] == "yahoo" and (prev.get("pending") or prev.get("roster_synced")):
                push_once(f"{lg.key}:access-live", f"{name}: Yahoo access is live",
                          "Yahoo approved the app. The lineup tab and injury watch now cover this league.",
                          tags=["tada"])
        except (LeagueOver, SnapshotMissing) as e:
            notes.append(str(e))
            league_views[name] = {"name": name, "platform": cfg["platform"], "sport": cfg["sport"],
                                  "pending": True, "message": str(e).split(": ", 1)[-1]}
        except YahooPending as e:
            notes.append(f"{name}: Yahoo API pending ({e})")
            saved = load_json(SAVED_ROSTER)
            if saved:
                lg = SavedYahooLeague(ctx, saved)
                better_news(lg)
                leagues.append(lg)
                league_views[name] = league_view(lg, now)
                if now - lg.captured > ROSTER_STALE:   # one laptop-outage push (shq/pushes.py)
                    outage.append(pushes.stale_cause(name, lg.captured, "Yahoo (laptop roster sync)"))
                    notes.append(f"{name}: saved roster is stale")
            else:
                league_views[name] = {"name": name, "platform": "yahoo", "pending": True,
                                      "message": "Waiting on Yahoo Fantasy API approval (Yahoo blocked unapproved apps in July 2026)."}
        except Exception as e:
            traceback.print_exc()
            errors.append(f"{name}: {type(e).__name__}: {e}")
            league_views[name] = {**(prev_views.get(name) or {"name": name}), "stale": True}

    kicks = set(ctx.kickoffs())
    for lg in leagues:
        if isinstance(lg, EspnLeague):
            kicks |= lg.kickoffs()
    upcoming = sorted(k for k in kicks if k > now)
    status["next_kickoff"] = iso(upcoming[0]) if upcoming else None
    status["upcoming_kickoffs"] = [iso(k) for k in upcoming]
    lead = dt.timedelta(hours=WATCH_LEAD_HOURS)
    status["watch_active"] = any(k - lead <= now < k for k in kicks)
    radar_push(radar_queue, notes)
    status["jobs"] = job_health(now, outage=outage)
    try:   # laptop or Chrome down: one push per outage, every symptom in it (Q-049)
        sent = pushes.outage_push(now, outage, status["jobs"])
        if sent:
            notes.append(f"outage push: {sent}")
    except Exception:
        traceback.print_exc()
    try:   # NBA: one lineup push a day before the first tip, only when a move is needed (shq/nba_lineup.py)
        sent = nba_lineup.send([lg for lg in leagues if getattr(lg, "sport", "nfl") == "nba"], now)
        if sent:
            notes.append(f"nba lineup push: {sent}")
    except Exception:
        traceback.print_exc()
    actions = []
    if status["watch_active"]:
        for lg in leagues:
            try:
                actions += injury_watch(lg, now)
                league_views[lg.name] = league_view(lg, now)  # reflect any swap
            except Exception as e:
                traceback.print_exc()
                errors.append(f"{lg.name} injury watch: {type(e).__name__}: {e}")
    status["actions"] = actions

    # DARKO's projected minutes, once a day from 7am CT, for the players the basketball advice uses: the value-source
    # trial's snapshot (shq/darko.py; never fails)
    dk = darko.track(now, darko.run_blocks(leagues, league_views))
    if dk:
        notes.append(dk)
    save_json(DATA / "lineups.json", {"updated": iso(now), "week": ctx.week, "leagues": league_views})
    try:   # the Players page: NBA category values (shq/nba_values.py), football ranks (shq/nfl_players.py)
        nba_values.save(DATA / "players.json", {lg.name: getattr(lg, "values", None) for lg in leagues
                                                 if getattr(lg, "sport", "nfl") == "nba"}, iso(now))
        nba_values.save(DATA / "players_nfl.json", {lg.name: getattr(lg, "players_block", None) for lg in leagues
                                                     if getattr(lg, "sport", "nfl") == "nfl"}, iso(now))
    except Exception as e:
        traceback.print_exc()
        errors.append(f"players: {type(e).__name__}: {e}")

    today = load_json(DATA / "digest.json", {}) or {}
    forced = os.environ.get("FORCE_DIGEST") == "1"
    if forced or digest_due(now, parse_iso(today.get("generated")), origin_digest):
        try:
            items = digest.build(leagues, now, load_json(ROOT / "picks" / "data" / "cards.json", {}))
            title, msg = digest.message(items)
            save_json(DATA / "digest.json", {"generated": iso(now), "title": title, "items": items})
            if any(i["urgent"] for i in items) and digest.push_window(now):
                # once a day; on Tuesday it rides in the morning push; never repeats an injury-watch push (Q-049)
                pushes.digest_push(items, leagues, now, forced)
        except Exception as e:
            traceback.print_exc()
            errors.append(f"digest: {type(e).__name__}: {e}")
    else:
        try:   # later runs keep today's items in step with the league pages, without pushing (Q-048)
            fresh = refresh_digest(today, leagues, now, load_json(ROOT / "picks" / "data" / "cards.json", {}))
            if fresh:
                save_json(DATA / "digest.json", fresh)
        except Exception:
            traceback.print_exc()

    weekly = load_json(DATA / "weekly.json", {}) or {}
    if weekly_due(now, parse_iso(weekly.get("generated"))) or os.environ.get("FORCE_WEEKLY") == "1":
        try:
            weekly = {"generated": iso(now), "week": ctx.week,
                      "leagues": [nba_weekly_section(lg) if getattr(lg, "sport", "nfl") == "nba"
                                  else weekly_section(lg, _advice(league_views.get(lg.name))) for lg in leagues]}
            save_json(DATA / "weekly.json", weekly)
            if os.environ.get("FORCE_WEEKLY") != "1":   # Tuesday: rides in the 8am morning push (Q-049)
                pushes.plan_push(now, ctx.week)
        except Exception as e:
            traceback.print_exc()
            errors.append(f"weekly: {type(e).__name__}: {e}")
    elif weekly.get("week") == ctx.week:
        # Tuesday's framing stays; start/sit and adds follow the league pages (Tuesday's adds kept as plan_adds)
        save_json(DATA / "weekly.json", refresh_weekly(weekly, leagues, league_views, now))

    # weekend wrap-up: Sunday night after the late games, final Tuesday 8am (shq/wrapup.py decides)
    try:
        forced_wrap = os.environ.get("FORCE_WRAPUP") == "1"
        note = wrapup.run(now, ctx.week, ctx.games, league_views, force=forced_wrap,
                          deliver=pushes.wrapup_deliver(now, forced_wrap))
        if note:
            notes.append(note)
    except Exception as e:
        traceback.print_exc()
        errors.append(f"wrap-up: {type(e).__name__}: {e}")

    try:   # Tuesday 8am CT: ONE push with the week's plan, today's digest and the wrap-up final (Q-049)
        sent = pushes.tuesday_push(now, leagues)
        if sent:
            notes.append(f"morning push: {sent}")
    except Exception as e:
        traceback.print_exc()
        errors.append(f"morning push: {type(e).__name__}: {e}")

    status["errors"], status["notes"], status["pushes"] = errors, notes, len(notify.sent)
    status["ok"] = not errors
    save_json(DATA / "status.json", status)
    print(f"week {ctx.week} watch={status['watch_active']} actions={actions} notes={notes} errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["--keep-watching"]:
        sys.exit(0 if keep_watching(load_json(DATA / "status.json", {}) or {}, now_utc()) else 1)
    main()
