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
from .values import espn_scoring

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
FA_FILTER = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "limit": 50,
                         "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
FA_POOL = 20   # NBA reads this many free agents for category ideas; the first 12 stay the usual list

# NBA category leagues: ESPN stat ids, and the ratio categories with their (made, attempted) parts.
NBA_STATS = {0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 4: "OREB", 5: "DREB", 6: "REB", 11: "TO", 13: "FGM",
             14: "FGA", 15: "FTM", 16: "FTA", 17: "3PM", 18: "3PA", 19: "FG%", 20: "FT%", 21: "3P%", 35: "A/TO",
             37: "DD", 38: "TD"}
RATIO = {19: (13, 14), 20: (15, 16), 21: (17, 18), 35: (3, 11)}


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


def _deadline(s):
    ms = (s.get("tradeSettings") or {}).get("deadlineDate")
    return iso(dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)) if ms else None


def _faab(s, team):
    acq = s.get("acquisitionSettings") or {}
    if not acq.get("isUsingAcquisitionBudget"):
        return None
    return {"budget": acq.get("acquisitionBudget"), "spent": (team.get("transactionCounter") or {}).get("acquisitionBudgetSpent", 0)}


def _avg(p, season, keep):
    """Per-game averages: this season once a player has 5 games, before that ESPN's season projection."""
    by_id = {x.get("id"): x.get("averageStats") or {} for x in p.get("stats") or []}
    cur = by_id.get(f"00{season}") or {}
    a = cur if cur.get("42", 0) >= 5 else by_id.get(f"10{season}") or cur
    return {k: round(a[k], 2) for k in keep if a.get(k)}


def cat_matchup(raw, team_id, opp_id, free_agents):
    """This week's category totals (mMatchup scoreByStat) for both teams, plus per-game averages (by player
    id) for both rosters and the free agents so shq.categories can project the rest of the week. The players
    themselves are already in the snapshot ("roster", "teams", "free_agents"); "fa_more" adds the free
    agents past the usual 12."""
    s = raw["settings"]["scoringSettings"]
    if "CATEGORY" not in (s.get("scoringType") or "") or opp_id is None:
        return None
    cats = [[i["statId"], bool(i.get("isReverseItem"))] for i in s.get("scoringItems") or []]
    keep = list(dict.fromkeys(str(x) for c, _ in cats for x in RATIO.get(c, (c,))))
    score = {}
    for m in raw.get("schedule") or []:
        if m.get("matchupPeriodId") == raw["status"]["currentMatchupPeriod"]:
            for side in (m.get("home"), m.get("away")):
                if side:
                    by = (side.get("cumulativeScore") or {}).get("scoreByStat") or {}
                    score[side.get("teamId")] = {k: v["score"] for k, v in by.items() if v.get("score") is not None}
    players = [e["playerPoolEntry"]["player"] for t in raw["teams"] if t["id"] in (team_id, opp_id)
               for e in (t.get("roster") or {}).get("entries", [])] + [f["player"] for f in free_agents or []]
    avg = {str(p["id"]): a for p in players if (a := _avg(p, raw["seasonId"], keep))}
    return {"cats": cats, "mine": score.get(team_id, {}), "opp": score.get(opp_id, {}), "opp_id": opp_id, "avg": avg,
            "fa_more": [{"id": p["id"], "name": p["fullName"], "pro_team": p.get("proTeamId"), "injury": p.get("injuryStatus"),
                         "eligible": p.get("eligibleSlots") or []} for p in (f["player"] for f in (free_agents or [])[12:])]}


def compact(raw, sport, team_id, free_agents=None):
    """Snapshot shape shared with LAPTOP_SNAPSHOT_JS. "teams" holds every other roster (trade finder)."""
    period, mp, s = raw["scoringPeriodId"], raw["status"]["currentMatchupPeriod"], raw["settings"]
    team = next(t for t in raw["teams"] if t["id"] == team_id)
    opp = other = None
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
        "size": s.get("size"), "scoring": espn_scoring(s["scoringSettings"].get("scoringItems")),
        "trade_deadline": _deadline(s), "faab": _faab(s, team),
        "team": {"id": team_id, "name": _team_name(team)}, "opponent": opp,
        "roster": [{**_player(e["playerPoolEntry"], period), "slot": e["lineupSlotId"]} for e in team["roster"]["entries"]],
        "free_agents": [_player(fa, period) for fa in (free_agents or [])[:12 if sport == "nba" else 50]],
        "teams": [{"id": t["id"], "name": _team_name(t),
                   "roster": [{**_player(e["playerPoolEntry"], period), "slot": e["lineupSlotId"]}
                              for e in (t.get("roster") or {}).get("entries") or []]}
                  for t in raw["teams"] if t["id"] != team_id],
        **({"matchup": cat_matchup(raw, team_id, other, free_agents)} if sport == "nba" else {}),
    }


def fetch_public(sport, season, league_id, team_id):
    url = _url(sport, season, league_id)
    raw = get_json(url, [("view", v) for v in VIEWS])
    filt = {"players": {**FA_FILTER["players"], "limit": FA_POOL if sport == "nba" else 12}}
    fas = get_json(url, {"view": "kona_player_info", "scoringPeriodId": raw["scoringPeriodId"]},
                   headers={"X-Fantasy-Filter": json.dumps(filt)}).get("players", [])
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
const SPECS = __SPECS__, STATS = __STATS__;
const out = [], now = new Date().toISOString();
const tn = t => t ? (t.name || ((t.location||'') + ' ' + (t.nickname||'')).trim()) : null;
// NBA category matchup, same shape as espn_fantasy.cat_matchup()
const RATIO = {19: [13, 14], 20: [15, 16], 21: [17, 18], 35: [3, 11]};
const avg = (p, season, keep) => { const by = {}; (p.stats || []).forEach(x => { by[x.id] = x.averageStats || {}; });
  const cur = by['00' + season] || {}, a = (cur['42'] || 0) >= 5 ? cur : (by['10' + season] || cur);
  return Object.fromEntries(keep.filter(k => a[k]).map(k => [k, Math.round(a[k] * 100) / 100])); };
const cm = (raw, tid, oid, fap) => {
  const sc = raw.settings.scoringSettings;
  if (!(sc.scoringType || '').includes('CATEGORY') || oid == null) return null;
  const cats = (sc.scoringItems || []).map(i => [i.statId, !!i.isReverseItem]);
  const keep = [...new Set(cats.flatMap(([c]) => RATIO[c] || [c]).map(String))], score = {};
  (raw.schedule || []).filter(m => m.matchupPeriodId === raw.status.currentMatchupPeriod).forEach(m => [m.home, m.away].forEach(sd => {
    if (sd) score[sd.teamId] = Object.fromEntries(Object.entries((sd.cumulativeScore || {}).scoreByStat || {})
      .filter(([k, v]) => v.score != null).map(([k, v]) => [k, v.score])); }));
  const players = raw.teams.filter(x => x.id === tid || x.id === oid).flatMap(x => (x.roster || {}).entries || [])
    .map(e => e.playerPoolEntry.player).concat(fap.map(f => f.player));
  const av = Object.fromEntries(players.map(p => [String(p.id), avg(p, raw.seasonId, keep)]).filter(([k, a]) => Object.keys(a).length));
  return {cats, mine: score[tid] || {}, opp: score[oid] || {}, opp_id: oid, avg: av,
          fa_more: fap.slice(12).map(f => f.player).map(p => ({id: p.id, name: p.fullName, pro_team: p.proTeamId, injury: p.injuryStatus || null, eligible: p.eligibleSlots || []}))};
};
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
  const filt = {players: {filterStatus: {value: ['FREEAGENT', 'WAIVERS']}, limit: sport === 'nba' ? 20 : 50, sortPercOwned: {sortPriority: 1, sortAsc: false}}};
  const acq = s.acquisitionSettings || {}, dl = (s.tradeSettings || {}).deadlineDate;
  const ros = x => ((x.roster || {}).entries || []).map(e => ({...pc(e.playerPoolEntry), slot: e.lineupSlotId}));
  let fa = {players: []};
  try { fa = await (await fetch(base + `?view=kona_player_info&scoringPeriodId=${period}`, {credentials: 'include', headers: {'X-Fantasy-Filter': JSON.stringify(filt)}})).json(); } catch (e) {}
  out.push({captured: now, sport, league_id: lid, season, league_name: s.name, scoring_period: period, matchup_period: mp,
    matchup_scoring_periods: ((s.scheduleSettings || {}).matchupPeriods || {})[mp] || [],
    scoring_type: s.scoringSettings.scoringType,
    slot_counts: Object.fromEntries(Object.entries(s.rosterSettings.lineupSlotCounts).filter(([k, v]) => v)),
    size: s.size, scoring: Object.fromEntries((s.scoringSettings.scoringItems || []).filter(i => STATS[i.statId]).map(i => [STATS[i.statId], i.points])),
    trade_deadline: dl ? new Date(dl).toISOString().replace('.000Z', 'Z') : null,
    faab: acq.isUsingAcquisitionBudget ? {budget: acq.acquisitionBudget, spent: (t.transactionCounter || {}).acquisitionBudgetSpent || 0} : null,
    team: {id: tid, name: tn(t)}, opponent: tn(raw.teams.find(x => x.id === oid)),
    roster: ros(t), free_agents: (fa.players || []).slice(0, sport === 'nba' ? 12 : 50).map(pc),
    teams: raw.teams.filter(x => x.id !== tid).map(x => ({id: x.id, name: tn(x), roster: ros(x)})),
    ...(sport === 'nba' ? {matchup: cm(raw, tid, oid, fa.players || [])} : {})});
}
return JSON.stringify(out);
})()"""
