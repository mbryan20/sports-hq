"""Entry point for every scheduled run: refresh lineups, run the injury watch when inside a
pre-kickoff window, build the Weekly tab on Tuesday 7am CT. Exits non-zero on any real error so
the workflow's failure step pushes an alert."""
import datetime as dt
import os
import sys
import traceback

from . import notify
from .common import DATA, ct_label, iso, load_json, now_utc, parse_iso, save_json
from .config import TZ, WATCH_LEAD_HOURS, WEEKLY_HOUR, WEEKLY_WEEKDAY
from .leagues import Context, SleeperLeague, YahooLeague, view
from .notify import push, push_once
from .status import OUTISH
from .swap import plan_injury_swaps
from .yahoo import YahooPending, YahooWriteDenied


def watch_active(ctx, now):
    return any(k - dt.timedelta(hours=WATCH_LEAD_HOURS) <= now < k for k in ctx.kickoffs())


def label(p):
    extra = f" ({p['why']})" if p.get("why") else ""
    return f"{p['name']}{extra}"


def injury_watch(league, now):
    actions = []
    for item in plan_injury_swaps(league.starters, league.bench, now, WATCH_LEAD_HOURS):
        out, inn, slot = item["out"], item["in"], item["slot"]
        key = f"{league.key}:w{league.week}:{out['id']}"
        locks = ct_label(out["kickoff"])
        if inn and league.can_write:
            try:
                if os.environ.get("DRY_RUN") == "1":
                    ok = True
                    print(f"[dry-run] would swap {out['name']} -> {inn['name']} ({slot})")
                else:
                    ok = league.execute_swap(out, inn)
                if ok:
                    push(f"{league.name}: lineup fixed", f"Swapped {out['name']} → {inn['name']} ({slot}). "
                         f"{out['name']}: {out['why']}.", priority=4, tags=["arrows_counterclockwise"])
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
                      f"Bench {label(out)} → start {inn['name']} ({inn['proj']} proj) at {slot}. Locks {locks}.",
                      priority=4, tags=["rotating_light"])
            actions.append(f"suggested {out['name']} -> {inn['name']}")
        else:
            fa = league.best_fa(out["positions"], now)
            tip = f"Best FA: {fa['name']} ({fa['team']}, {fa['proj']} proj) — add/drop manually." if fa else "No playable FA found."
            push_once(key + ":fa", f"{league.name}: no healthy bench {slot}",
                      f"{label(out)} is out and no healthy bench player fits {slot}. {tip} Locks {locks}.",
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


def weekly_section(league):
    from .swap import fa_adds, start_sit
    ss = [f"Start {b['name']} ({b['proj']}) over {s['name']} ({'BYE' if s['bye'] else s['status'] or s['proj']}) at {s['slot']}"
          for s, b, _ in start_sit(league.starters, league.bench)]
    if not ss:
        ss = [f"Lineup is optimal by projections ({round(sum(p['proj'] for p in league.starters), 1)} pts)."]
    roster = league.starters + league.bench
    adds = [f"Add {fa['name']} ({fa['positions'][0]}, {fa['team']}, {fa['proj']})"
            + (f" over {who['name']} ({who['status'] if who['status'] in OUTISH else who['proj']})" if who else "")
            for _, fa, who in fa_adds(roster, league.free_agents[:300])]
    if not adds:
        adds = ["No free agent projects above your current depth."]
    return {"name": league.name, "week": league.week, "start_sit": ss[:3], "adds": adds[:3]}


def main():
    now = now_utc()
    errors, notes, leagues = [], [], []
    if os.environ.get("TEST_PUSH") == "1":
        push("Sports HQ test push", f"Alerts are working. Sent from GitHub Actions at {ct_label(now)} CT.", tags=["white_check_mark"])
    status = {"last_run": iso(now), "dry_run": os.environ.get("DRY_RUN") == "1"}

    ctx = Context(now)
    status["week"] = ctx.week
    upcoming = [k for k in ctx.kickoffs() if k > now]
    status["next_kickoff"] = iso(upcoming[0]) if upcoming else None

    prev_views = (load_json(DATA / "lineups.json", {}) or {}).get("leagues", {})
    league_views = {}
    for name, cls in (("Kosmonauts", YahooLeague), ("Domo Arigato", SleeperLeague)):
        try:
            lg = cls(ctx)
            leagues.append(lg)
            league_views[name] = view(lg)
            if (prev_views.get(name) or {}).get("pending"):
                push_once(f"{lg.key}:access-live", f"{name}: Yahoo access is live",
                          "Yahoo approved the app. The lineup tab and injury watch now cover this league.",
                          tags=["tada"])
        except YahooPending as e:
            league_views[name] = {"name": name, "platform": "yahoo", "pending": True,
                                  "message": "Waiting on Yahoo Fantasy API approval (Yahoo blocked unapproved apps in July 2026)."}
            notes.append(f"{name}: Yahoo pending ({e})")
        except Exception as e:
            traceback.print_exc()
            errors.append(f"{name}: {type(e).__name__}: {e}")
            league_views[name] = {**(prev_views.get(name) or {"name": name}), "stale": True}

    status["watch_active"] = watch_active(ctx, now)
    actions = []
    if status["watch_active"]:
        for lg in leagues:
            try:
                actions += injury_watch(lg, now)
                league_views[lg.name] = view(lg)  # reflect any swap
            except Exception as e:
                traceback.print_exc()
                errors.append(f"{lg.name} injury watch: {type(e).__name__}: {e}")
    status["actions"] = actions

    save_json(DATA / "lineups.json", {"updated": iso(now), "week": ctx.week, "leagues": league_views})

    weekly = load_json(DATA / "weekly.json", {}) or {}
    if weekly_due(now, parse_iso(weekly.get("generated"))) or os.environ.get("FORCE_WEEKLY") == "1":
        try:
            weekly = {"generated": iso(now), "week": ctx.week,
                      "leagues": [weekly_section(lg) for lg in leagues]}
            save_json(DATA / "weekly.json", weekly)
            if os.environ.get("FORCE_WEEKLY") != "1":
                push(f"Week {ctx.week} plan ready", "Start/sit and FA adds are on the Weekly tab.", priority=2, tags=["clipboard"])
        except Exception as e:
            traceback.print_exc()
            errors.append(f"weekly: {type(e).__name__}: {e}")

    status["errors"], status["notes"], status["pushes"] = errors, notes, len(notify.sent)
    status["ok"] = not errors
    save_json(DATA / "status.json", status)
    print(f"week {ctx.week} watch={status['watch_active']} actions={actions} notes={notes} errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
