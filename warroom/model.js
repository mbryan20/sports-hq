// War Room model: projections, elimination sim, rival price model, bid candidates. No DOM, so the page
// (app.js) and the GitHub build (export.js, under Node) run the same code and get the same numbers.
// Expects a global D (app_data.json from warroom/model.py).
const ME = String(D.me), CUT = D.cut ? String(D.cut.roster) : null;
const W0 = D.week, LAST = D.last_week;                       // next week to play, last cut week
const WEEKS = []; for (let w = W0; w <= LAST; w++) WEEKS.push(w);
const NEAR = WEEKS.slice(0, 4);                              // the weeks a rival bids for
const ALIVE = Object.keys(D.teams).filter(t => t !== CUT);
const POSMEAN = (() => { const m = {}; for (const p of ['K','DEF']) { const v = Object.values(D.P).filter(x => x.p === p && x.own && x.g >= 3).map(x => x.a); m[p] = v.reduce((a, b) => a + b, 0) / Math.max(1, v.length); } return m; })();
const POSCAP = (() => { const m = {}; for (const h of D.hist) for (const [r, b] of h.bids) m[h.p] = Math.max(m[h.p] || 0, b); return m; })();
const S = { blend:.5, sd:21, aggr:1, reserve:10, dpw:20, sims:2000, adds:new Set() };
const tname = t => (D.teams[t] ? D.teams[t].n : (D.dead[t] || ('R'+t)));
const pname = s => D.P[s] ? D.P[s].n : s;

// ---------- projections ----------
let PJ = {};
function proj(s, w) {
  const k = s + ':' + w; if (k in PJ) return PJ[k];
  const p = D.P[s]; let v = 0;
  if (p && p.g > 0) {
    v = S.blend * p.r + (1 - S.blend) * p.a;
    if (p.g < 3) v *= 0.85;                      // thin sample: shade down
    if (p.p === 'K' || p.p === 'DEF') v = 0.5 * v + 0.5 * POSMEAN[p.p];   // K/DEF are noisy: pull halfway to the average
    if (p.bye.includes(w)) v = 0;
    if (p.st === 'RES' && w < W0 + 4) v = 0;
    if (w === W0) { if (p.inj === 'Out') v = 0; else if (p.inj === 'Doubtful') v *= .3; else if (p.inj === 'Questionable') v *= .85; }
  }
  return PJ[k] = v;
}
const SLOTS = [['QB',['QB']],['RB',['RB']],['RB',['RB']],['WR',['WR']],['WR',['WR']],['WR',['WR']],['TE',['TE']],['K',['K']],['DEF',['DEF']],['FLEX',['RB','WR','TE']],['FLEX',['RB','WR','TE']]];
function lineup(roster, w) {
  const pool = roster.filter(s => D.P[s]).map(s => ({ s, p: D.P[s].p, v: proj(s, w) })).sort((a, b) => b.v - a.v);
  const used = new Set(), st = []; let tot = 0;
  for (const [slot, ok] of SLOTS) {
    const c = pool.find(x => !used.has(x.s) && ok.includes(x.p));
    if (c) { used.add(c.s); st.push({ slot, s: c.s, v: c.v }); tot += c.v; } else st.push({ slot, s: null, v: 0 });
  }
  return { tot, st };
}
function roster(t, extra) {
  let r = D.teams[t].roster.slice();
  if (t === ME) r = r.concat([...S.adds]);
  if (extra) r = r.concat(extra);
  return r;
}
function teamProj(t, extra) { const o = {}; for (const w of WEEKS) o[w] = lineup(roster(t, extra), w).tot; return o; }

// ---------- simulation ----------
function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function simulate(projs, n) {
  const R = rng(20261027), teams = Object.keys(projs);
  const cut = {}; teams.forEach(t => cut[t] = Object.fromEntries(WEEKS.map(w => [w, 0])));
  const win = Object.fromEntries(teams.map(t => [t, 0]));
  const gauss = () => { let u = 0, v = 0; while (!u) u = R(); v = R(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  for (let i = 0; i < n; i++) {
    let alive = teams.slice();
    for (const w of WEEKS) {
      if (alive.length < 2) break;
      let lo = null, lv = 1e9;
      for (const t of alive) { const x = projs[t][w] + S.sd * gauss(); if (x < lv) { lv = x; lo = t; } }
      cut[lo][w]++; alive = alive.filter(t => t !== lo);
    }
    if (alive.length === 1) win[alive[0]]++;
  }
  const out = {};
  for (const t of teams) {
    let surv = 1, exp = 0; const pAlive = {}, pCut = {};
    for (const w of WEEKS) { pAlive[w] = surv; pCut[w] = cut[t][w] / n; surv -= pCut[w]; exp += pAlive[w] - pCut[w]; }
    out[t] = { pCut, pAlive, expWeeks: exp, pWin: win[t] / n };
  }
  return out;
}

// ---------- market model ----------
const MAXPCT = {};
for (const t of ALIVE) MAXPCT[t] = 20;
for (const h of D.hist) for (const [r, b, pc] of h.pct) { const k = String(r); if (k in MAXPCT && b > 0) MAXPCT[k] = Math.max(MAXPCT[k], pc); }
function rivalGain(t, s) { let g = 0; for (const w of NEAR) g += lineup(roster(t, [s]), w).tot - lineup(roster(t), w).tot; return g / NEAR.length; }
function threats(s) {
  const out = [];
  for (const t of ALIVE) {
    if (t === ME) continue;
    const g = rivalGain(t, s), faab = D.teams[t].faab;
    if (g < 1 || faab <= 0) continue;
    const need = Math.min(1, g / 6);
    const p = D.P[s].p, cap = (p === 'K' || p === 'DEF') ? Math.round((POSCAP[p] || 5) * S.aggr) : 1e9;
    const base = NEAR.reduce((a, w) => a + proj(s, w), 0) / NEAR.length || (S.blend * D.P[s].r + (1 - S.blend) * D.P[s].a);
    const q = p === 'QB' ? (base - 14) / 12 : (base - 6) / 10;           // player quality: 0 = replacement, 1 = stud
    const quality = Math.max(0.1, Math.min(1, q));
    const bid = Math.min(faab, cap, Math.round(faab * MAXPCT[t] / 100 * need * quality * S.aggr));
    out.push({ t, g, bid });
  }
  return out.sort((a, b) => b.bid - a.bid);
}

let BASE = null;
function computeBase() {
  PJ = {};
  const projs = {}; for (const t of ALIVE) projs[t] = teamProj(t);
  BASE = { projs, sim: simulate(projs, S.sims) };
}

// players freed by the latest cut who no surviving team has claimed yet
function freedPlayers() {
  if (!CUT || !D.teams[CUT]) return [];
  const owned = new Set(); for (const t of ALIVE) D.teams[t].roster.forEach(s => owned.add(s));
  return D.teams[CUT].roster.filter(s => D.P[s] && !owned.has(s));
}

function candidates() {
  const freed = freedPlayers();
  const owned = new Set(); for (const t of ALIVE) D.teams[t].roster.forEach(s => owned.add(s));
  const fa = Object.keys(D.P).filter(s => !owned.has(s) && !freed.includes(s) && D.P[s].own === 0 && D.P[s].g >= 2)
    .map(s => [s, WEEKS.reduce((a, w) => a + proj(s, w), 0)]).sort((a, b) => b[1] - a[1]).slice(0, 60).map(x => x[0]);
  const myBase = roster(ME);
  const rows = [];
  const quick = Math.max(500, Math.round(S.sims / 2));
  // baseline at the same sim count for a fair comparison
  const baseQ = simulate(BASE.projs, quick)[ME];
  for (const s of freed.concat(fa)) {
    if (S.adds.has(s)) { rows.push({ s, freed: freed.includes(s), added: true }); continue; }
    const g1 = lineup(myBase.concat([s]), W0).tot - lineup(myBase, W0).tot;
    let gR = 0; for (const w of WEEKS) gR += (lineup(myBase.concat([s]), w).tot - lineup(myBase, w).tot);
    if (gR < 0.5 && !freed.includes(s)) continue;
    rows.push({ s, freed: freed.includes(s), g1, gR });
  }
  // simulate the most promising
  const perPos = {};
  const pick = rows.filter(r => !r.added).sort((a, b) => b.gR - a.gR).filter(r => { if (r.freed) return true; const p = D.P[r.s].p; perPos[p] = (perPos[p] || 0) + 1; return perPos[p] <= 2; }).slice(0, 18);
  rows.splice(0, rows.length, ...rows.filter(r => r.added), ...pick);
  pick.forEach(r => {
    const projs = Object.assign({}, BASE.projs, { [ME]: teamProj(ME, [r.s]) });
    const sm = simulate(projs, quick)[ME];
    r.dW = sm.expWeeks - baseQ.expWeeks; r.dWin = sm.pWin - baseQ.pWin;
  });
  return rows;
}

// price, value-based max and the call for one candidate row (freed players go through FAAB waivers;
// a plain free agent costs $0 once waivers clear)
function decide(r) {
  const cap = Math.max(0, D.teams[ME].faab - S.reserve);
  if (!r.freed) return { th: [], price: 0, mx: 0, call: r.dW >= .05 ? 'Add free' : 'Skip' };
  const th = threats(r.s), price = th.length ? th[0].bid + 1 : 1;
  let mx = Math.min(cap, Math.max(0, Math.round(r.dW * S.dpw))), call;
  if (r.dW < 0.05) { call = 'Skip'; mx = 0; }
  else if (mx >= price) call = 'Bid';
  else if (mx >= price * .7) call = 'Coin flip';
  else call = 'Priced out';
  return { th, price, mx, call };
}

// Everything the AI write-up and the Tuesday bid check need, at the default slider settings.
function exportBids() {
  S.adds = new Set(); computeBase();
  const r1 = x => Math.round(x * 10) / 10, r3 = x => Math.round(x * 1000) / 1000;
  const player = s => { const p = D.P[s]; return { sleeper_id: s, name: p.n, pos: p.p, team: p.t, injury: p.inj || null, ir: p.st === 'RES', season_avg: r1(p.a), last3_avg: r1(p.r) }; };
  const bids = candidates().filter(r => r.dW !== undefined).sort((a, b) => b.dW - a.dW).map(r => {
    const d = decide(r);
    return { ...player(r.s), source: r.freed ? 'freed' : 'free agent', gain_next_week: r1(r.g1), gain_rest_of_season: r1(r.gR),
             extra_weeks_alive: Math.round(r.dW * 100) / 100, extra_win_odds: r3(r.dWin),
             est_price: r.freed ? d.price : 0, your_max: r.freed ? d.mx : 0, call: d.call,
             likely_rival_bids: d.th.slice(0, 3).map(x => ({ team: tname(x.t), bid: x.bid })) };
  });
  const sim = BASE.sim;
  return {
    league: D.league, data_as_of: D.asof, last_sleeper_move: D.data_as_of, week: W0, last_week: LAST,
    cut: D.cut ? { team: tname(CUT), week: D.cut.week, confirmed: D.cut.confirmed } : null,
    waivers: D.waivers, my_team: tname(ME), my_faab: D.teams[ME].faab, reserve: S.reserve,
    settings: { blend_recent: S.blend, score_sd: S.sd, rival_aggression: S.aggr, dollars_per_week: S.dpw, sims: S.sims },
    me: { cut_risk_next_week: r3(sim[ME].pCut[W0]), expected_weeks_left: r1(sim[ME].expWeeks), win_odds: r3(sim[ME].pWin),
          projected_next_week: r1(BASE.projs[ME][W0]) },
    cut_risks: ALIVE.slice().sort((a, b) => sim[b].pCut[W0] - sim[a].pCut[W0]).map(t => ({
      team: tname(t), me: t === ME, faab: D.teams[t].faab, boldest_bid_pct: MAXPCT[t], projected_next_week: r1(BASE.projs[t][W0]),
      cut_risk_next_week: r3(sim[t].pCut[W0]), expected_weeks_left: r1(sim[t].expWeeks), win_odds: r3(sim[t].pWin) })),
    freed_players: freedPlayers().map(player),
    my_roster: (() => { const L = lineup(roster(ME), W0), on = new Set(L.st.map(x => x.s));
      return L.st.filter(x => x.s).map(x => ({ slot: x.slot, ...player(x.s), proj_next_week: r1(x.v) }))
        .concat(roster(ME).filter(s => D.P[s] && !on.has(s)).map(s => ({ slot: 'BN', ...player(s), proj_next_week: r1(proj(s, W0)) }))); })(),
    bids,
  };
}
