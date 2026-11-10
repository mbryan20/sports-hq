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

from . import advice, digest, espn, guillotine, nba_lineup, nba_values, notify, radar, wrapup
from . import espn_fantasy as ef
from .common import DATA, ROOT, STATE, ct_label, iso, load_json, now_utc, parse_iso, save_json
from .config import ESPN_PRIVATE, LEAGUES, TZ, WATCH_LEAD_HOURS, WEEKLY_HOUR, WEEKLY_WEEKDAY
from .leagues import (Context, EspnLeague, LeagueOver, SavedYahooLeague, SleeperLeague, SnapshotMissing,
                      YahooLeague, view)
from .notify import push, push_once
from .status import OUTISH
from .swap import MIN_FILL, fa_over_bench, plan_injury_swaps, slot_fa, strength_text
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
            fresh = m and espn.player_news(m.group(1), game)
        except Exception:
            traceback.print_exc()
            continue
        if fresh:
            p["news"] = {**n, **fresh}


def radar_push(league, view_json, notes):
    """NBA trend radar: a push for a rising free agent in a category I need (shq/radar.py). Never fails the run."""
    if getattr(league, "sport", "nfl") != "nba":
        return
    try:
        sent = radar.send_alerts(league, view_json.get("advice"))
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
        # football: a free agent is the better fix when the bench fill-in projects under MIN_FILL or trails him by
        # FA_EDGE+ (same rule as the digest's lineup fixes); a sub-MIN_FILL fill-in isn't worth swapping in
        nba = getattr(league, "sport", "nfl") == "nba"
        fa = league.best_fa(out["positions"], now) if nba else slot_fa(slot, digest.free_agents(league), now)
        better = "" if nba or not (inn and fa_over_bench(inn, fa)) else \
            f" Better: add {fa['name']} ({fa['team']}, {fa['proj']} proj) and start him — add/drop manually."
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


def start_sit_lines(league):
    """Weekly tab start/sit, rebuilt every run so an injury status is never days old."""
    if getattr(league, "sport", "nfl") == "nba":
        return nba_weekly_section(league)["start_sit"]
    from .swap import start_sit
    ss = [f"Start {b['name']} ({b['proj']}) over {s['name']} ({'BYE' if s['bye'] else s['status'] or s['proj']}) at {s['slot']}"
          + (digest.cite(s) if s["status"] and not s["bye"] else "")
          for s, b, _ in start_sit(league.starters, league.bench)]
    return ss or [f"Lineup is optimal by projections ({round(sum(p['proj'] for p in league.starters), 1)} pts)."]


def weekly_section(league):
    from .swap import fa_adds
    ss = start_sit_lines(league)
    if advice.valued(league):  # same rest-of-season list as the league tab
        adds = advice.adds(league)
    else:
        roster = league.starters + league.bench
        adds = [f"Add {fa['name']} ({fa['positions'][0]}, {fa['team']}, {fa['proj']})"
                + (f" over {who['name']} ({who['status'] if who['status'] in OUTISH else who['proj']})" if who else "")
                for _, fa, who in fa_adds(roster, league.free_agents[:300])]
    if not adds:
        adds = ["No free agent projects above your current depth."]
    return {"name": league.name, "week": league.week, "start_sit": ss[:3], "adds": adds[:3]}


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


def laptop_kicks(now, runs=gh_dispatches):
    """Q-037: the laptop starts the time-critical GitHub jobs, so GitHub checks the laptop. Its 2:55am model-health kick is
    never skipped, so it is the daily heartbeat: from 4am CT, if no model-health dispatch was created since 2:50am today,
    push once that day. A late start (laptop asleep at 2:55, the task ran on waking) counts as alive. Returns the footer's
    "Laptop kick" row, or None when the run list can't be read (then no push either)."""
    times = runs()
    if times is None:
        return None
    local = now.astimezone(TZ)
    if local.time() >= LAPTOP_CHECK_AFTER:
        since = dt.datetime.combine(local.date(), LAPTOP_KICK_FROM, TZ)
        if not any(t >= since for t in times):
            push_once(f"laptop-kick-silent:{local.date().isoformat()}", "Laptop didn't start today's Sports HQ jobs",
                      "Laptop off, Windows task broken, or token expired. GitHub's own schedule (hours late) is all "
                      "that's running.", priority=3, tags=["warning"])
    return {"job": "Laptop kick (laptop, daily 2:55am)", "last": iso(max(times, default=None))}


def job_health(now, kicks=laptop_kicks):
    """When each laptop job last delivered, from what it committed. The cloud alerts on staleness."""
    jobs = []
    try:
        row = kicks(now)
        if row:
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
    league_views = {}
    for cfg in LEAGUES:
        name = cfg["name"]
        try:
            if cfg["platform"] == "yahoo":
                lg = YahooLeague(ctx)
            elif cfg["platform"] == "sleeper":
                lg = SleeperLeague(ctx, name, cfg.get("league_id"), cfg.get("format"))
            else:
                lg = EspnLeague(ctx, cfg)
                if lg.captured and now - lg.captured > ROSTER_STALE:
                    push_once(f"espn-stale:{name}:{iso(lg.captured)}", f"{name}: ESPN sync is stale",
                              f"Last read from ESPN {ct_label(lg.captured)} CT. Is the laptop on with the Claude app open?",
                              tags=["warning"])
                    notes.append(f"{name}: ESPN snapshot is stale")
            lg.dynasty = bool(cfg.get("dynasty"))
            lg.assets = bool(cfg.get("assets"))  # 3-Ball: picks and minors from the league sheet
            if cfg.get("format") == "guillotine":
                guillotine_odds(lg, ctx, now)
            better_news(lg)
            leagues.append(lg)
            league_views[name] = league_view(lg, now)
            radar_push(lg, league_views[name], notes)
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
                if now - lg.captured > ROSTER_STALE:
                    push_once(f"roster-stale:{saved['captured']}", f"{name}: roster sync is stale",
                              f"Last read from Yahoo {ct_label(lg.captured)} CT. Is the laptop on with the Claude app open? "
                              "Alerts are using that roster.", tags=["warning"])
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
    status["jobs"] = job_health(now)
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
                day = now.astimezone(TZ).date().isoformat()
                if forced:
                    push(title, msg, priority=3, tags=["sunrise"])
                else:
                    push_once(f"digest:{day}", title, msg, priority=3, tags=["sunrise"])
        except Exception as e:
            traceback.print_exc()
            errors.append(f"digest: {type(e).__name__}: {e}")

    weekly = load_json(DATA / "weekly.json", {}) or {}
    if weekly_due(now, parse_iso(weekly.get("generated"))) or os.environ.get("FORCE_WEEKLY") == "1":
        try:
            weekly = {"generated": iso(now), "week": ctx.week,
                      "leagues": [nba_weekly_section(lg) if getattr(lg, "sport", "nfl") == "nba" else weekly_section(lg)
                                  for lg in leagues]}
            save_json(DATA / "weekly.json", weekly)
            if os.environ.get("FORCE_WEEKLY") != "1":
                push(f"Week {ctx.week} plan ready", "Start/sit and FA adds are on the Weekly tab.", priority=2, tags=["clipboard"])
        except Exception as e:
            traceback.print_exc()
            errors.append(f"weekly: {type(e).__name__}: {e}")
    elif weekly.get("week") == ctx.week:
        # adds stay Tuesday's plan; start/sit follows the latest injury news
        by_name = {lg.name: lg for lg in leagues}
        for sec in weekly.get("leagues", []):
            try:
                if sec["name"] in by_name:
                    sec["start_sit"] = start_sit_lines(by_name[sec["name"]])[:3]
            except Exception:
                traceback.print_exc()
        weekly["start_sit_updated"] = iso(now)
        save_json(DATA / "weekly.json", weekly)

    # weekend wrap-up: Sunday night after the late games, final Tuesday 8am (shq/wrapup.py decides)
    try:
        note = wrapup.run(now, ctx.week, ctx.games, league_views, force=os.environ.get("FORCE_WRAPUP") == "1")
        if note:
            notes.append(note)
    except Exception as e:
        traceback.print_exc()
        errors.append(f"wrap-up: {type(e).__name__}: {e}")

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
