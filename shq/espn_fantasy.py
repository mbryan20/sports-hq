"""ESPN fantasy leagues (football and basketball).

Public leagues (the 3-Ball dynasty ones) are read straight from ESPN's API. Private leagues come
from a compact snapshot the laptop task saves with Michael's ESPN sign-in
(state/espn/<sport>-<league_id>.json, written by shq.save_espn). Both paths produce the same
compact shape, so the rest of the app doesn't care which one it got. The JavaScript that builds
the snapshot in the browser lives in LAPTOP_SNAPSHOT_JS below and must stay in step with compact().
"""
import datetime as dt
import json

from .common import STATE, get_json, iso, now_utc

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/{game}/seasons/{season}"
GAME = {"nfl": "ffl", "nba": "fba"}
VIEWS = ["mRoster", "mTeam", "mSettings", "mMatchup"]
SNAPSHOTS = STATE / "espn"

SLOT_NAMES = {
    "nfl": {0: "QB", 2: "RB", 4: "WR", 6: "TE", 7: "OP", 16: "D/ST", 17: "K", 20: "BN", 21: "IR", 23: "FLEX"},
    "nba": {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "SG/SF", 8: "G/F", 9: "PF/C",
            10: "F/C", 11: "UT", 12: "BN", 13: "IR"},
}
BENCH = {"nfl": (20, 21), "nba": (12, 13)}       # BN, IR
FA_FILTER = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 12,
                         "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}


def _url(sport, season, league_id=None):
    base = API.format(game=GAME[sport], season=season)
    return f"{base}/segments/0/leagues/{league_id}" if league_id else base


def _player(pool_entry, period):
    p = pool_entry["player"]
    proj = next((s.get("appliedTotal") for s in p.get("stats") or []
                 if s.get("scoringPeriodId") == period and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 1), None)
    return {"id": p["id"], "name": p["fullName"], "pro_team": p.get("proTeamId"), "eligible": p.get("eligibleSlots") or [],
            "pos": p.get("defaultPositionId"), "injury": p.get("injuryStatus"),
            "proj": round(proj, 1) if proj is not None else None,
            "owned": round((p.get("ownership") or {}).get("percentOwned", 0), 1)}


def _team_name(t):
    return t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()


def compact(raw, sport, team_id, free_agents=None):
    period, mp, s = raw["scoringPeriodId"], raw["status"]["currentMatchupPeriod"], raw["settings"]
    team = next(t for t in raw["teams"] if t["id"] == team_id)
    opp = None
    for m in raw.get("schedule") or []:
        ids = [(m.get("home") or {}).get("teamId"), (m.get("away") or {}).get("teamId")]
        if m.get("matchupPeriodId") == mp and team_id in ids:
            other = next((i for i in ids if i != team_id), None)
            opp = next((_team_name(t) for t in raw["teams"] if t["id"] == other), None)
    return {
        "captured": iso(now_utc()), "sport": sport, "league_id": raw["id"], "season": raw["seasonId"],
        "league_name": s.get("name"), "scoring_period": period, "matchup_period": mp,
        "matchup_scoring_periods": ((s.get("scheduleSettings") or {}).get("matchupPeriods") or {}).get(str(mp), []),
        "scoring_type": s["scoringSettings"].get("scoringType"),
        "slot_counts": {k: v for k, v in s["rosterSettings"]["lineupSlotCounts"].items() if v},
        "team": {"id": team_id, "name": _team_name(team)}, "opponent": opp,
        "roster": [{**_player(e["playerPoolEntry"], period), "slot": e["lineupSlotId"]} for e in team["roster"]["entries"]],
        "free_agents": [_player(fa, period) for fa in free_agents or []],
    }


def fetch_public(sport, season, league_id, team_id):
    url = _url(sport, season, league_id)
    raw = get_json(url, [("view", v) for v in VIEWS])
    fas = get_json(url, {"view": "kona_player_info", "scoringPeriodId": raw["scoringPeriodId"]},
                   headers={"X-Fantasy-Filter": json.dumps(FA_FILTER)}).get("players", [])
    return compact(raw, sport, team_id, fas)


def load_snapshot(sport, league_id):
    try:
        return json.loads((SNAPSHOTS / f"{sport}-{league_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def pro_schedule(sport, season):
    """{pro_team_id: {"abbrev", "games": {scoring_period: [(kickoff, opp_id, is_home)]}}}"""
    raw = get_json(_url(sport, season), {"view": "proTeamSchedules_wl"})
    out = {}
    for t in raw["settings"]["proTeams"]:
        games = {}
        for period, gs in (t.get("proGamesByScoringPeriod") or {}).items():
            games[int(period)] = [(dt.datetime.fromtimestamp(g["date"] / 1000, dt.timezone.utc),
                                   g["awayProTeamId"] if g["homeProTeamId"] == t["id"] else g["homeProTeamId"],
                                   g["homeProTeamId"] == t["id"]) for g in gs]
        out[t["id"]] = {"abbrev": (t.get("abbrev") or "").upper(), "games": games}
    return out


# Run by the laptop task inside a signed-in fantasy.espn.com tab; returns JSON text, one compact
# league per entry (same shape as compact()). SPECS = [sport, game, season, leagueId, teamId].
LAPTOP_SNAPSHOT_JS = r"""(async () => {
const SPECS = __SPECS__;
const out = [], now = new Date().toISOString();
const tn = t => t ? (t.name || ((t.location||'') + ' ' + (t.nickname||'')).trim()) : null;
for (const [sport, game, season, lid, tid] of SPECS) {
  const base = `https://lm-api-reads.fantasy.espn.com/apis/v3/games/${game}/seasons/${season}/segments/0/leagues/${lid}`;
  let raw;
  try { raw = await (await fetch(base + '?view=mRoster&view=mTeam&view=mSettings&view=mMatchup', {credentials: 'include'})).json(); }
  catch (e) { out.push({sport, league_id: lid, error: String(e)}); continue; }
  if (!raw.teams) { out.push({sport, league_id: lid, error: JSON.stringify(raw).slice(0, 200)}); continue; }
  const period = raw.scoringPeriodId, mp = raw.status.currentMatchupPeriod, s = raw.settings;
  const pc = pe => { const p = pe.player; const st = (p.stats||[]).find(x => x.scoringPeriodId === period && x.statSourceId === 1 && x.statSplitTypeId === 1);
    return {id: p.id, name: p.fullName, pro_team: p.proTeamId, eligible: p.eligibleSlots || [], pos: p.defaultPositionId,
            injury: p.injuryStatus || null, proj: st ? Math.round(st.appliedTotal * 10) / 10 : null,
            owned: Math.round(((p.ownership || {}).percentOwned || 0) * 10) / 10}; };
  const t = raw.teams.find(x => x.id === tid);
  const m = (raw.schedule || []).find(x => x.matchupPeriodId === mp && [x.home && x.home.teamId, x.away && x.away.teamId].includes(tid));
  const oid = m ? (m.home && m.home.teamId === tid ? (m.away || {}).teamId : (m.home || {}).teamId) : null;
  const filt = {players: {filterStatus: {value: ['FREEAGENT', 'WAIVERS']}, limit: 12, sortPercOwned: {sortPriority: 1, sortAsc: false}}};
  let fa = {players: []};
  try { fa = await (await fetch(base + `?view=kona_player_info&scoringPeriodId=${period}`, {credentials: 'include', headers: {'X-Fantasy-Filter': JSON.stringify(filt)}})).json(); } catch (e) {}
  out.push({captured: now, sport, league_id: lid, season, league_name: s.name, scoring_period: period, matchup_period: mp,
    matchup_scoring_periods: ((s.scheduleSettings || {}).matchupPeriods || {})[mp] || [],
    scoring_type: s.scoringSettings.scoringType,
    slot_counts: Object.fromEntries(Object.entries(s.rosterSettings.lineupSlotCounts).filter(([k, v]) => v)),
    team: {id: tid, name: tn(t)}, opponent: tn(raw.teams.find(x => x.id === oid)),
    roster: t.roster.entries.map(e => ({...pc(e.playerPoolEntry), slot: e.lineupSlotId})),
    free_agents: (fa.players || []).map(pc)});
}
return JSON.stringify(out);
})()"""
