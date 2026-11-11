// War Room model: projections, elimination sim, rival price model, bid candidates. No DOM, so the page
// (app.js) and the GitHub build (export.js, under Node) run the same code and get the same numbers.
// Expects a global D (app_data.json from warroom/model.py).
//
// Settings were tested against this league's own history (Nov 3 2026, see warroom/README.md):
// - Projections: Sleeper's weekly projections (team-score misses ~16 pts vs ~20 for any blend of past points).
// - Score swing: measured from how far real team scores landed from projections (D.sd), growing per week ahead.
// - Prices: the rival-bid estimate is turned into a chance of winning at each bid from how past claims went
//   (D.ladder), because one point estimate missed by ~$15 and stars went for ~1.65x it.
// - Value: the league is winner-take-all, so a player is worth the win odds he adds, priced at the $ per
//   win-odds point at which your FAAB would run out over the weeks you're expected to stay alive.
const ME = String(D.me), CUT = D.cut ? String(D.cut.roster) : null;
const W0 = D.week, LAST = D.last_week;                       // next week to play, last cut week
const WEEKS = []; for (let w = W0; w <= LAST; w++) WEEKS.push(w);
const NEAR = WEEKS.slice(0, 4);                              // the weeks a rival bids for
const ALIVE = Object.keys(D.teams).filter(t => t !== CUT);
const POSMEAN = (() => { const m = {}; for (const p of ['K','DEF']) { const v = Object.values(D.P).filter(x => x.p === p && x.own && x.g >= 3).map(x => x.a); m[p] = v.reduce((a, b) => a + b, 0) / Math.max(1, v.length); } return m; })();
const POSCAP = (() => { const m = {}; for (const h of D.hist) for (const [r, b] of h.bids) m[h.p] = Math.max(m[h.p] || 0, b); return m; })();
const SD_MEASURED = (D.sd && D.sd.measured) || 23, SD_GROWTH = (D.sd && D.sd.growth) || 0;
const S = { sd: SD_MEASURED, aggr: 1, reserve: LAST - W0 < 3 ? 0 : 5, dpp: 0, sims: 6000, adds: new Set() };   // dpp 0 = auto
const tname = t => (D.teams[t] ? D.teams[t].n : (D.dead[t] || ('R'+t)));
const pname = s => D.P[s] ? D.P[s].n : s;
const MIN_WIN = 0.003;    // win odds a move must add to be worth a claim: below this the simulation can't tell it from noise

// ---------- projections ----------
let PJ = {};
function proj(s, w) {
  const k = s + ':' + w; if (k in PJ) return PJ[k];
  const p = D.P[s]; let v = 0;
  if (p && p.pw) v = p.pw[w - W0] || 0;              // Sleeper's projection (byes and players ruled out are already 0)
  else if (p && p.g > 0) {                           // no Sleeper projection: fall back to recent points
    v = 0.5 * p.r + 0.5 * p.a;
    if (p.g < 3) v *= 0.85;
    if (p.p === 'K' || p.p === 'DEF') v = 0.5 * v + 0.5 * POSMEAN[p.p];
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
function roster(t, extra, drop) {
  let r = D.teams[t].roster.slice();
  if (t === ME) r = r.concat([...S.adds]);
  if (extra) r = r.concat(extra);
  if (drop) { const d = [].concat(drop); r = r.filter(s => !d.includes(s)); }
  return r;
}
function teamProj(t, extra, drop) { const o = {}; for (const w of WEEKS) o[w] = lineup(roster(t, extra, drop), w).tot; return o; }
// rosters are full, so every add is also a drop: the player whose loss costs the fewest projected points.
// A K or DEF add never drops an RB, WR or TE worth KEEP_FLOOR points a week (season average or the coming
// weeks' projection): on the bench he counts as nearly free in the lineup math, but he is the cover for
// byes and injuries (Q-041, Nov 10: MIN DEF for $1 would have dropped Breece Hall).
const KEEP_FLOOR = 8;
function keeper(d) {
  const p = D.P[d];
  if (!p || !['RB', 'WR', 'TE'].includes(p.p)) return false;
  const near = NEAR.length ? NEAR.reduce((a, w) => a + proj(d, w), 0) / NEAR.length : 0;
  return Math.max(p.a || 0, near) >= KEEP_FLOOR;
}
function bestDrop(t, s, skip) {
  let best = null, bestTot = -1e9;
  const kd = D.P[s] && (D.P[s].p === 'K' || D.P[s].p === 'DEF');
  for (const d of roster(t)) {
    if (d === s || S.adds.has(d) || (skip && skip.has(d))) continue;
    if (kd && keeper(d)) continue;
    const tot = WEEKS.reduce((a, w) => a + lineup(roster(t, [s], d), w).tot, 0);
    if (tot > bestTot) { bestTot = tot; best = d; }
  }
  return best;
}

// ---------- simulation ----------
const swing = w => S.sd + SD_GROWTH * (w - W0);              // further-out weeks are less certain
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
      let lo = null, lv = 1e9; const sd = swing(w);
      for (const t of alive) { const x = projs[t][w] + sd * gauss(); if (x < lv) { lv = x; lo = t; } }
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
    const base = NEAR.reduce((a, w) => a + proj(s, w), 0) / NEAR.length || (0.5 * D.P[s].r + 0.5 * D.P[s].a);
    const q = p === 'QB' ? (base - 14) / 12 : (base - 6) / 10;           // player quality: 0 = replacement, 1 = stud
    const quality = Math.max(0.1, Math.min(1, q));
    const bid = Math.min(faab, cap, Math.round(faab * MAXPCT[t] / 100 * need * quality * S.aggr));
    out.push({ t, g, bid });
  }
  return out.sort((a, b) => b.bid - a.bid);
}
// the model's raw estimate: one more than the boldest rival it expects (calibrated by the ladder below)
const rawEstimate = th => (th.length ? th[0].bid : 0) + 1;
// chance that a bid of b beats every rival, from how past winning bids compared with the model's estimate
// for the same claim (D.ladder: sorted ratios winning bid / estimate; "hi" for estimates of $10+)
function winChance(b, est) {
  const xs = D.ladder ? (est >= 10 && D.ladder.hi.length ? D.ladder.hi : D.ladder.lo) : null;
  if (!xs || !xs.length) return b >= est ? 0.5 : 0;
  let c = 0;
  for (const x of xs) if (x * est < b || (b === 0 && x === 0)) c++;
  return c / xs.length;
}
function priceFor(chance, est, cap = 999) {
  for (let b = 0; b <= cap; b++) if (winChance(b, est) >= chance) return b;
  return null;
}
// Likely rival bids on the same scale as the win chance (Q-039). threats() guesses each rival's bid from his
// boldest past bids, and past claims went for less than that guess (often $0: nobody claimed him), which the
// ladder measures. So each guess is scaled by (price that wins half of comparable claims) / (raw estimate);
// `raw` keeps the unscaled guess. Without a ladder the guesses are shown as they are.
function rivalBids(r) {
  const th = r.th || [];
  if (!th.length) return [];
  const f = D.ladder && r.est ? (priceFor(.5, r.est) ?? r.est) / r.est : 1;
  return th.map(x => ({ t: x.t, bid: Math.round(x.bid * f), raw: x.bid }));
}
// a waiver claim the model recommends (a $0 claim is still a claim: it needs a drop and can beat no claim)
const isBid = r => r.call === 'Bid' || r.call === 'Coin flip';
// out this week and projected 0 for an injury (not a bye): Out or on IR (Q-040)
function outNow(s) {
  const p = D.P[s];
  return !!p && (p.inj === 'Out' || p.st === 'RES') && proj(s, W0) === 0 && !(p.bye || []).includes(W0);
}

// Bids worth comparing for one player: the best-value bid, the bids that won about 25%, 50% and 80% of
// comparable past claims, and his full value. Each with its win chance and average payoff
// (= chance x (value - bid): what that bid is worth to you on average; negative means overpaying).
function bidOptions(r, value, spend) {
  const faab = D.teams[ME].faab;      // the 80% price is shown even above what you can spend, up to your FAAB
  const amts = new Set([r.bid, priceFor(.25, r.est), priceFor(.5, r.est), priceFor(.8, r.est, faab), Math.min(value, spend)]
    .filter(b => b !== null && (b > 0 || (b === r.bid && isBid(r))) && b <= faab));
  return [...amts].sort((a, b) => a - b).map(b => { const p = winChance(b, r.est); return { bid: b, chance: p, payoff: p * (value - b) }; });
}

let BASE = null;
function computeBase() {
  PJ = {};
  const projs = {}; for (const t of ALIVE) projs[t] = teamProj(t);
  BASE = { projs, sim: simulate(projs, S.sims) };
}

// players freed by the latest cut who no surviving team has claimed yet
// (once the waiver run after the cut has processed they're ordinary free agents, so none are listed)
function freedPlayers() {
  if (!CUT || !D.teams[CUT] || D.cut.freed_status === 'cleared') return [];
  const owned = new Set(); for (const t of ALIVE) D.teams[t].roster.forEach(s => owned.add(s));
  return D.teams[CUT].roster.filter(s => D.P[s] && !owned.has(s));
}

function candidates() {
  const freed = freedPlayers();
  const owned = new Set(); for (const t of ALIVE) D.teams[t].roster.forEach(s => owned.add(s));
  const fa = Object.keys(D.P).filter(s => !owned.has(s) && !freed.includes(s) && D.P[s].own === 0 && (D.P[s].g >= 2 || D.P[s].pw))
    .map(s => [s, WEEKS.reduce((a, w) => a + proj(s, w), 0)]).sort((a, b) => b[1] - a[1]).slice(0, 60).map(x => x[0]);
  const myBase = roster(ME), myBaseTot = WEEKS.map(w => lineup(myBase, w).tot);
  const rows = [];
  const quick = Math.max(500, Math.round(S.sims / 2));
  const baseQ = BASE.quick = simulate(BASE.projs, quick)[ME];    // same sim count and seed for a fair comparison
  for (const s of freed.concat(fa)) {
    if (S.adds.has(s)) { rows.push({ s, freed: freed.includes(s), added: true }); continue; }
    const drop = bestDrop(ME, s), mine = roster(ME, [s], drop);
    const g1 = lineup(mine, W0).tot - myBaseTot[0];
    let gR = 0; WEEKS.forEach((w, i) => gR += lineup(mine, w).tot - myBaseTot[i]);
    if (gR < 0.5 && !freed.includes(s)) continue;
    rows.push({ s, freed: freed.includes(s), g1, gR, drop });
  }
  const perPos = {};
  const pick = rows.filter(r => !r.added).sort((a, b) => b.gR - a.gR).filter(r => { if (r.freed) return true; const p = D.P[r.s].p; perPos[p] = (perPos[p] || 0) + 1; return perPos[p] <= 3; }).slice(0, 24);
  rows.splice(0, rows.length, ...rows.filter(r => r.added), ...pick);
  pick.forEach(r => { gains(r); if (r.freed) { r.th = threats(r.s); r.est = rawEstimate(r.th); } });
  return rows;
}
// extra expected weeks and win odds from adding r.s and dropping r.drop
function gains(r) {
  const sm = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, [r.s], r.drop) }), Math.max(500, Math.round(S.sims / 2)))[ME];
  r.dW = sm.expWeeks - BASE.quick.expWeeks; r.dWin = sm.pWin - BASE.quick.pWin;
}

// extra expected weeks and win odds from r on top of earlier claims `prior` ([{s, drop}]) that all won (Q-052)
function gainsOnTop(r, prior) {
  const n = Math.max(500, Math.round(S.sims / 2)), ps = prior.map(x => x.s), pd = prior.map(x => x.drop);
  const base = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, ps, pd) }), n)[ME];
  const sm = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, ps.concat([r.s]), pd.concat([r.drop])) }), n)[ME];
  return { dW: sm.expWeeks - base.expWeeks, dWin: sm.pWin - base.pWin };
}

// $ per point of win odds at which your FAAB runs out: line up this week's freed players by win odds per $
// (at the price that wins ~80% of the time), assume a similar crop at every waiver run you're expected to
// see, and take the ratio of the deal where the money would run out. S.dpp overrides it.
function autoDpp(rows) {
  const spend = Math.max(0, D.teams[ME].faab - S.reserve), runs = Math.max(1, Math.round(BASE.sim[ME].expWeeks));
  const deals = rows.filter(r => r.freed && r.dWin > 0.0005).map(r => ({ v: r.dWin * 100, c: Math.max(1, priceFor(.8, r.est) || r.est) }))
    .sort((a, b) => b.v / b.c - a.v / a.c);
  let used = 0, rate = null;
  for (const d of deals) { rate = d.c / d.v; used += runs * d.c; if (used >= spend) break; }
  return rate;
}
const dollarsPerPoint = rows => S.dpp > 0 ? S.dpp : autoDpp(rows);

// The call for every candidate. Freed players (on waivers): value = win odds added x $ per point; the bid is the
// amount with the best (chance of winning) x (value - bid); then all bids together must fit FAAB minus reserve.
function decideAll(rows) {
  const faab = D.teams[ME].faab, spend = Math.max(0, faab - S.reserve), dpp = dollarsPerPoint(rows);
  const price = r => {        // value, best bid and call for one candidate at its current drop
    if (outNow(r.s)) return Object.assign(r, { call: 'Skip', bid: 0, value: 0, chance: null, options: [],
      price: r.freed ? (priceFor(.5, r.est) ?? r.est) : 0, price80: r.freed ? (priceFor(.8, r.est) ?? r.est) : 0,
      why: 'out this week (injury or IR): not worth a roster spot now' });
    if (!r.freed) return Object.assign(r, { call: r.dWin >= MIN_WIN ? 'Add free' : 'Skip', bid: 0, value: 0, price: 0, price80: 0, chance: null,
      why: r.dWin >= MIN_WIN ? 'free agent' : 'adds too little to matter' });
    const value = dpp ? Math.floor(r.dWin * 100 * dpp) : 0, cap = Math.min(spend, value);
    // $0 counts with its own payoff: a $1 bid that wins no more often than $0 buys nothing (Q-038)
    const p0 = winChance(0, r.est);
    let best = { b: 0, ev: p0 * value, p: p0 };
    for (let b = 1; b <= cap; b++) { const p = winChance(b, r.est), ev = p * (value - b); if (ev > best.ev + 1e-9) best = { b, ev, p }; }
    const small = value < 1 || r.dWin < MIN_WIN, call = small ? 'Skip' : best.ev <= 0 ? 'Priced out' : best.p >= .5 ? 'Bid' : 'Coin flip';
    Object.assign(r, { call, bid: call === 'Bid' || call === 'Coin flip' ? best.b : 0, chance: best.p, value, ev: best.ev,
      price: priceFor(.5, r.est) ?? r.est, price80: priceFor(.8, r.est) ?? r.est,
      why: small ? 'adds too little to matter' : best.ev <= 0 ? 'likely price is above his value to you' : '' });
    r.options = small ? [] : bidOptions(r, value, spend);
    return r;
  };
  rows.filter(r => !r.added && r.dW !== undefined).forEach(price);
  // only one K and one DEF start: don't pay for one while a free agent at the same position helps as much (Q-041)
  for (const r of rows) {
    if (r.added || !r.freed || !isBid(r) || !['K', 'DEF'].includes(D.P[r.s].p)) continue;
    const free = rows.find(x => !x.added && !x.freed && x.call === 'Add free' && D.P[x.s].p === D.P[r.s].p && x.gR >= r.gR);
    if (free) Object.assign(r, { call: 'Skip', bid: 0, options: [], why: `${pname(free.s)} is a free add and helps as much` });
  }
  // All your bids must fit your FAAB minus the reserve, and each claim needs its own drop (Sleeper fails a claim
  // whose drop is already gone). The most valuable claims choose first; a later claim moves to its next-best
  // drop and is re-valued, since that drop may cost more.
  // A claim at the same position as a better claim is worth less: if that one wins, this one only adds what it adds on
  // top of him (two TEs for one TE spot). Its value is the chance-weighted mix of both cases (Q-052, Nov 10: Fannin and
  // Hockenson were both claimed for Goedert's bye, each valued as if it were the only one).
  let used = 0; const drops = new Set(), taken = [];
  for (const r of rows.filter(r => !r.added && isBid(r)).sort((a, b) => b.ev - a.ev)) {
    if (drops.has(r.drop)) {
      r.drop = bestDrop(ME, r.s, drops);
      if (!r.drop) { Object.assign(r, { call: 'Skip', bid: 0, why: 'no roster spot left to drop' }); continue; }
      gains(r); price(r);
      if (!isBid(r)) continue;
      r.why = 'drop changed: a better claim uses the first choice';
    }
    const same = r.freed ? taken.filter(x => D.P[x.s].p === D.P[r.s].p) : [];
    if (same.length) {
      const pAny = 1 - same.reduce((a, x) => a * (1 - (x.chance ?? 0)), 1), top = gainsOnTop(r, same);
      r.dW = (1 - pAny) * r.dW + pAny * top.dW; r.dWin = (1 - pAny) * r.dWin + pAny * top.dWin;
      const why = r.why; price(r);
      const names = same.map(x => pname(x.s)).join(' and ');
      if (!isBid(r)) { r.why = `adds little if your ${names} claim wins (${Math.round(pAny * 100)}%)`; continue; }
      r.why = (why ? why + '; ' : '') + `valued with your ${names} claim in mind`;
    }
    if (used + r.bid > spend) { Object.assign(r, { call: 'Skip', bid: 0, why: 'your other bids use the budget' }); continue; }
    used += r.bid; drops.add(r.drop); taken.push(r);
  }
  return { dpp, spend, used };
}

// Everything the AI write-up and the Tuesday checks need, at the default settings.
function exportBids() {
  S.adds = new Set(); computeBase();
  const r1 = x => Math.round(x * 10) / 10, r3 = x => Math.round(x * 1000) / 1000;
  const player = s => { const p = D.P[s]; return { sleeper_id: s, name: p.n, pos: p.p, team: p.t, injury: p.inj || null, ir: p.st === 'RES', season_avg: r1(p.a), last3_avg: r1(p.r),
    proj_next_week: r1(proj(s, W0)), bye_week: p.bye[0] || null }; };
  const rows = candidates(), money = decideAll(rows);
  const bids = rows.filter(r => r.dW !== undefined).sort((a, b) => b.dWin - a.dWin || b.dW - a.dW).map(r => ({
    ...player(r.s), source: r.freed ? (D.cut.freed_status === 'projected' ? 'freed (projected)' : 'freed') : 'free agent',
    gain_next_week: r1(r.g1), gain_rest_of_season: r1(r.gR), drop: r.drop && D.P[r.drop] ? D.P[r.drop].n : null, drop_id: r.drop || null,
    extra_weeks_alive: Math.round(r.dW * 100) / 100, extra_win_odds: r3(r.dWin),
    // est_price: the bid that would have won about half of comparable past claims; price_80: about 80%
    est_price: r.freed ? r.price : 0, price_80: r.freed ? r.price80 : 0, value: r.freed ? r.value : 0,
    bid: r.bid, win_chance: r.freed && r.chance !== null ? r3(r.chance) : null, your_max: r.freed ? Math.min(money.spend, r.value) : 0,
    call: r.call, why: r.why || null,
    // chance of winning at every bid from $0 to your FAAB (index = bid), for the side-by-side bookmark
    win_curve: r.freed && r.est ? Array.from({ length: D.teams[ME].faab + 1 }, (_, b) => Math.round(winChance(b, r.est) * 100) / 100) : null,
    bid_options: (r.options || []).map(o => ({ bid: o.bid, win_chance: r3(o.chance), avg_payoff: r1(o.payoff), recommended: o.bid === r.bid,
      over_spendable: o.bid > money.spend })),
    likely_rival_bids: rivalBids(r).slice(0, 3).map(x => ({ team: tname(x.t), bid: x.bid, raw: x.raw })) }));
  const sim = BASE.sim;
  return {
    league: D.league, data_as_of: D.asof, last_sleeper_move: D.data_as_of, week: W0, last_week: LAST,
    cut: D.cut ? { team: tname(CUT), week: D.cut.week, confirmed: D.cut.confirmed, freed_status: D.cut.freed_status } : null,
    // FAAB claims are only possible while the cut team's players sit on waivers; otherwise est_price is 0
    // everywhere except projected-freed rows, which are planning numbers for after the cut
    waivers_open: !!D.cut && D.cut.freed_status === 'on waivers', next_waiver_run: D.next_waiver_run,
    waivers: D.waivers, my_team: tname(ME), my_faab: D.teams[ME].faab, reserve: S.reserve,
    budget: { spendable: money.spend, recommended_bids_total: money.used, dollars_per_win_point: money.dpp ? r1(money.dpp) : null },
    settings: { projections: 'Sleeper weekly', score_sd: S.sd, score_sd_measured_from: D.sd ? D.sd.n : null, sd_growth_per_week: SD_GROWTH,
                rival_aggression: S.aggr, value: 'win odds (winner takes all)', sims: S.sims,
                price_ladder_claims: D.ladder ? D.ladder.lo.length + D.ladder.hi.length : 0 },
    me: { cut_risk_next_week: r3(sim[ME].pCut[W0]), expected_weeks_left: r1(sim[ME].expWeeks), win_odds: r3(sim[ME].pWin),
          projected_next_week: r1(BASE.projs[ME][W0]) },
    cut_risks: ALIVE.slice().sort((a, b) => sim[b].pCut[W0] - sim[a].pCut[W0]).map(t => ({
      team: tname(t), me: t === ME, faab: D.teams[t].faab, boldest_bid_pct: MAXPCT[t], projected_next_week: r1(BASE.projs[t][W0]),
      cut_risk_next_week: r3(sim[t].pCut[W0]), expected_weeks_left: r1(sim[t].expWeeks), win_odds: r3(sim[t].pWin) })),
    freed_players: freedPlayers().map(player),
    my_roster: (() => { const L = lineup(roster(ME), W0), on = new Set(L.st.map(x => x.s));
      return L.st.filter(x => x.s).map(x => ({ slot: x.slot, ...player(x.s), proj_next_week: r1(x.v) }))
        .concat(roster(ME).filter(s => D.P[s] && !on.has(s)).map(s => ({ slot: 'BN', ...player(s), proj_next_week: r1(proj(s, W0)) }))); })(),
    bids, names: D.names || {},
  };
}

// Calibration helper for build.py: the raw estimate for each past claim, rebuilt as of that waiver run.
function rawEstimates(sids) { PJ = {}; return sids.map(s => rawEstimate(threats(s))); }
