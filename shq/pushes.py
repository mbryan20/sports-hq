"""Which pushes go out when two would say the same thing (Q-049). Every suppressed push's content is still on the site:
the Weekly tab, the Today tab, the wrap-up page and the footer's job rows are written whether or not anything pushes.

- Tuesday morning: the "Week N plan ready" push (7am), the 8am digest and the wrap-up "final" (8am) carried the same
  pickups and start/sit moves. From 7am CT on the weekly plan day they wait, and the first pass at or after 8am sends
  ONE push with all three (the wrap-up's PDF as the tap target). Each part's own key is marked sent, so none of them
  pushes again on its own. The guillotine bid push (laptop, ~7:11am) is separate and untouched.
- The digest never repeats an injury-watch push: an urgent line about a starter the watch already pushed ("make this
  swap", "no healthy bench", "CHECK LINEUP") is left out of the push, and a digest with nothing else urgent doesn't push.
- Laptop or Chrome down: "ESPN sync is stale", "roster sync is stale" and "Laptop didn't start today's jobs" are one
  outage, so one push ("Laptop/roster sync down") listing every symptom. No second push until the laptop has delivered
  something new (a kick or a fresh read) and every symptom has cleared.
All state is in state/alerts.json through shq/notify.py (push_once keys, merged across parallel runs)."""
import datetime as dt

from . import digest, notify
from .common import DATA, ct_label, load_json, parse_iso
from .config import DIGEST_HOUR, SEASON, SITE_URL, TZ, WEEKLY_HOUR, WEEKLY_WEEKDAY

BUNDLE_HOUR = DIGEST_HOUR            # 8am CT: the digest and the wrap-up final are both due then
WRAPUPS = DATA.parent / "wrapups" / "index.json"
MAX_MSG = 3500                       # ntfy's limit is 4096 bytes; arrows and dashes take 3


# ---------- Tuesday morning ----------

def plan_anchor(now):
    """This plan week's start: the latest weekly-plan day at WEEKLY_HOUR CT (Tuesday 7am), as in shq.run.weekly_due."""
    local = now.astimezone(TZ)
    anchor = (local - dt.timedelta(days=(local.weekday() - WEEKLY_WEEKDAY) % 7)).replace(
        hour=WEEKLY_HOUR, minute=0, second=0, microsecond=0)
    return anchor - dt.timedelta(days=7) if anchor > local else anchor


def bundle_key(now):
    return f"tuesday:{plan_anchor(now).date().isoformat()}"


def plan_key(now):
    return f"weekly-plan:{plan_anchor(now).date().isoformat()}"


def holding(now):
    """Plan day from 7am CT until the morning push has gone: the plan, digest and wrap-up final wait for it."""
    local = now.astimezone(TZ)
    return (local.weekday() == WEEKLY_WEEKDAY and local.hour >= WEEKLY_HOUR
            and bundle_key(now) not in notify.seen())


def plan_push(now, week):
    """The weekly plan was just built (not forced): wait for the morning push, else push once for this plan week
    (a catch-up build after the morning push, or on another day)."""
    if holding(now):
        return None
    return notify.push_once(plan_key(now), f"Week {week} plan ready", "Start/sit and FA adds are on the Weekly tab.",
                            priority=2, tags=["clipboard"])


def wrapup_deliver(now, force=False):
    """wrapup.run's push step: a Tuesday final waits for the morning push (which reads it from the archive index)."""
    from . import wrapup

    def deliver(model, urls):
        if model.get("edition") == "final" and not force and holding(now):
            return
        wrapup.send(model, urls)
    return deliver


def wrapup_key(issue):
    return f"wrapup:{issue.get('season', SEASON)}:{issue['week']}:{issue['edition']}"


def _today(ts, now, hour):
    t = parse_iso(ts) if isinstance(ts, str) else ts
    if not t:
        return False
    local, lt = now.astimezone(TZ), t.astimezone(TZ)
    return lt.date() == local.date() and lt.hour >= hour


def bundle_parts(now, leagues, seen):
    """(plan, digest items, wrap-up issue) still to announce this morning, each None when absent or already pushed."""
    anchor = plan_anchor(now)
    weekly = load_json(DATA / "weekly.json", {}) or {}
    gen = parse_iso(weekly.get("generated"))
    plan = weekly if gen and gen >= anchor and plan_key(now) not in seen else None
    today = load_json(DATA / "digest.json", {}) or {}
    day = now.astimezone(TZ).date().isoformat()
    items = None
    if _today(today.get("generated"), now, DIGEST_HOUR) and f"digest:{day}" not in seen:
        items = uncovered(today.get("items") or [], leagues, seen)
    issues = (load_json(WRAPUPS, {}) or {}).get("issues", [])
    wrap = next((i for i in issues if i.get("edition") == "final" and _today(i.get("generated"), now, WEEKLY_HOUR)
                 and wrapup_key(i) not in seen), None)
    return plan, items, wrap


def bundle_message(now, plan, items, wrap):
    """(title, message, click, actions) for the morning push."""
    urgent = [i for i in items or [] if i["urgent"]]
    head = []
    if urgent:
        head.append(f"{len(urgent)} thing{'s' if len(urgent) != 1 else ''} to fix")
    if plan:
        head.append(f"Week {plan.get('week')} plan")
    if wrap:
        head.append(f"wk {wrap['week']} wrap-up")
    title = f"{now.astimezone(TZ).strftime('%A')}: " + " · ".join(head)
    lines = []
    if items is not None:
        lines += ([f"{'⚠ ' if i['urgent'] else ''}{i['league']}: {i['text']}" for i in items if i["urgent"]]
                  or ["Today: all clear."])
    if plan:
        lines.append(f"Week {plan.get('week')} plan: start/sit and FA adds are on the Weekly tab.")
    if wrap:
        lines.append(f"Wrap-up, NFL wk {wrap['week']} final:")
        lines += list(wrap.get("headline") or [])
    msg = "\n".join(lines)
    if len(msg) > MAX_MSG:
        msg = msg[:MAX_MSG - 1].rsplit("\n", 1)[0] + "\n…more on the site"
    click, actions = SITE_URL, None
    if wrap:
        base = SITE_URL + "wrapups/"
        html = base + wrap["html"]
        pdf = base + wrap["pdf"] if wrap.get("pdf") else None
        click = pdf or html
        actions = [{"action": "view", "label": "PDF", "url": pdf or html},
                   {"action": "view", "label": "Web page", "url": html}]
    return title, msg, click, actions


def tuesday_push(now, leagues=()):
    """At or after 8am CT on the plan day: one push with the week's plan, today's digest and the wrap-up final, then
    each part's own key is marked so none pushes again by itself. Needs a plan, a wrap-up or an urgent digest line.
    Returns the title pushed, or None."""
    local = now.astimezone(TZ)
    if local.weekday() != WEEKLY_WEEKDAY or local.hour < BUNDLE_HOUR:
        return None
    seen = notify.seen()
    key = bundle_key(now)
    if key in seen:
        return None
    plan, items, wrap = bundle_parts(now, leagues, seen)
    if not (plan or wrap or any(i["urgent"] for i in items or [])):
        return None
    title, msg, click, actions = bundle_message(now, plan, items, wrap)
    if not notify.push_once(key, title, msg, priority=3, tags=["clipboard", "newspaper"], click=click,
                            actions=actions, delay="3m" if wrap else None):   # GitHub Pages needs a minute or two
        return None
    done = ([plan_key(now)] if plan else []) + ([f"digest:{local.date().isoformat()}"] if items is not None else []) + \
        ([wrapup_key(wrap)] if wrap else [])
    notify.mark(done, now)
    return title


# ---------- the digest never repeats an injury-watch push ----------

def watch_pushed(leagues, seen):
    """(league name, player name) for every starter the injury watch already pushed about this week."""
    out = set()
    for lg in leagues or ():
        key, week = getattr(lg, "key", None), getattr(lg, "week", None)
        for p in list(getattr(lg, "starters", []) or []) + list(getattr(lg, "bench", []) or []):
            base = f"{key}:w{week}:{p.get('id')}"
            if any(base + s in seen for s in (":swap", ":fa", ":unconfirmed")):
                out.add((lg.name, p["name"]))
    return out


def uncovered(items, leagues, seen):
    """Digest items minus the urgent ones about a starter the injury watch already pushed."""
    covered = watch_pushed(leagues, seen)
    return [i for i in items if not (i["urgent"] and any(i["league"] == lg and i["text"].startswith(name + " (")
                                                         for lg, name in covered))]


def digest_push(items, leagues, now, forced=False):
    """The daily digest's push (the Today tab is saved by the caller either way). Forced: as before, everything.
    On the plan day it waits for the morning push. Otherwise once a day before DIGEST_PUSH_UNTIL, only for urgent
    lines the injury watch hasn't already pushed."""
    if forced:
        title, msg = digest.message(items)
        notify.push(title, msg, priority=3, tags=["sunrise"])
        return True
    if holding(now) or not digest.push_window(now):
        return False
    left = uncovered(items, leagues, notify.seen())
    if not any(i["urgent"] for i in left):
        return False
    title, msg = digest.message(left)
    return notify.push_once(f"digest:{now.astimezone(TZ).date().isoformat()}", title, msg, priority=3, tags=["sunrise"])


# ---------- laptop / Chrome outage: one push ----------

DOWN, UP = "laptop-down", "laptop-up"


def _t(s):
    try:
        return parse_iso(s) if isinstance(s, str) else s
    except ValueError:
        return None


def _open(seen):
    """When the current outage was pushed, or None when there's no open outage."""
    down, up = _t(seen.get(DOWN)), _t(seen.get(UP))
    return down if down and (not up or up < down) else None


def recovered(down, jobs):
    """The laptop delivered after the outage push: its daily kick when the run list was readable (the heartbeat a
    Chrome-only outage keeps sending, and an off laptop doesn't), else any laptop job."""
    kick = next((j for j in jobs or () if str(j.get("job", "")).startswith("Laptop kick")), None)
    lasts = [kick.get("last")] if kick else [j.get("last") for j in jobs or ()]
    return any(_t(t) and _t(t) > down for t in lasts)


def outage_push(now, causes, jobs=()):
    """`causes`: this pass's laptop symptoms (stale ESPN snapshot, stale Yahoo roster, no kick today). One push per
    outage listing them all; the outage ends when there are no symptoms and the laptop delivered after the push
    (`recovered`). Returns the title pushed, or None."""
    down = _open(notify.seen())
    if not causes:
        if down and recovered(down, jobs):
            notify.mark([UP], now)
        return None
    if down or _open(notify.seen(fresh=True)):   # another run may have pushed this outage already
        return None
    title = "Laptop/roster sync down"
    msg = ("\n".join(causes) + "\nIs the laptop on with Chrome and the Claude app open? Alerts use the last saved "
           "rosters; the site's footer shows each job's last run. One push per outage.")
    notify.push(title, msg, priority=3, tags=["warning"])
    notify.mark([DOWN], now)
    return title


def stale_cause(name, captured, what="ESPN"):
    return f"{name}: last read from {what} {ct_label(captured)} CT."
