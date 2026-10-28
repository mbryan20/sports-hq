"""Tuesday guillotine bid check (laptop task, read-only).

    py -m shq.guillotine_bids --js        JavaScript to run in a signed-in sleeper.com tab; returns pending claims
    py -m shq.guillotine_bids <file>      print the claims with player names, highest bid first

Sleeper only shows pending claims to the signed-in owner, so the JavaScript queries Sleeper's own
web API from inside Michael's session. It never changes a claim."""
import json
import sys

from . import sleeper

LEAGUE_ID = "1385516543386845184"
USER_ID = "605584791680663552"

JS = r"""(async () => {
const LID = '__LID__', UID = '__UID__';
const rosters = await (await fetch(`https://api.sleeper.app/v1/league/${LID}/rosters`)).json();
const me = rosters.find(r => r.owner_id === UID);
const q = `query league_transactions_filtered { league_transactions_filtered(league_id: "${LID}", roster_id_filters: [${me.roster_id}], type_filters: [], leg_filters: [], status_filters: ["pending"]) { adds drops created settings type } }`;
const r = await fetch('https://sleeper.com/graphql', {method: 'POST', headers: {'content-type': 'application/json', 'authorization': localStorage.getItem('token')},
  body: JSON.stringify({operationName: 'league_transactions_filtered', variables: {}, query: q})});
const j = await r.json();
if (j.errors || !j.data) return JSON.stringify({error: JSON.stringify(j.errors || j).slice(0, 300)});
const lg = await (await fetch(`https://api.sleeper.app/v1/league/${LID}`)).json();
const budget = ((lg.settings || {}).waiver_budget || 0) - ((me.settings || {}).waiver_budget_used || 0);
return JSON.stringify({faab_left: budget, claims: j.data.league_transactions_filtered.map(t => ({
  add: Object.keys(t.adds || {})[0], drop: Object.keys(t.drops || {})[0] || null, bid: (t.settings || {}).waiver_bid || 0, created: t.created}))});
})()"""


def js():
    return JS.replace("__LID__", LEAGUE_ID).replace("__UID__", USER_ID)


def report(path):
    data = json.loads(open(path, encoding="utf-8").read())
    if isinstance(data, str):
        data = json.loads(data)
    if data.get("error"):
        sys.exit(f"Sleeper error: {data['error']}")
    players = sleeper.players()
    name = lambda pid: (players.get(pid) or {}).get("full_name") or pid or "-"
    print(f"FAAB left: ${data['faab_left']}  ·  {len(data['claims'])} pending claims")
    for c in sorted(data["claims"], key=lambda c: (-c["bid"], name(c["add"]))):
        print(f"${c['bid']:<3} add {name(c['add'])} ({(players.get(c['add']) or {}).get('position', '')})  drop {name(c['drop'])}")


if __name__ == "__main__":
    print(js()) if sys.argv[1:] == ["--js"] else report(sys.argv[1])
