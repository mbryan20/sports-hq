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
// Michael's rules (warroom/rules.json, read by build.py into D.rules; playbook "Michael's rules"): the reserve he sets,
// big money only for players he has named league-winners, marginal claims at $0, never drop a likely starter for an add
// who wouldn't start in his place.
// Reserve (rule 13, Nov 12): kept while he's likely to survive; when his cut risk this week reaches
// release_reserve_at_cut_risk, a claim that lowers that risk by release_min_survival_gain or more may spend it.
const RULES = Object.assign({ reserve: 5, release_reserve_at_cut_risk: 0.25, release_min_survival_gain: 0.02,
  league_winners: [], big_bid_share: 0.25, big_bid_min: 3, marginal_pts_per_week: 2 }, D.rules || {});
const S = { sd: SD_MEASURED, aggr: 1, reserve: RULES.reserve, dpp: 0, sims: 6000, adds: new Set() };   // dpp 0 = auto
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
// Never a likely starter either (his rule 7, Nov 12 revamp): someone in this week's lineup is a drop only when the add
// takes a starting spot that week himself (leg 3 replay: a $0 Kyler Murray claim would have dropped J.K. Dobbins).
function startsFor(t, s, d, w) { return lineup(roster(t, [s], d), w).st.some(x => x.s === s); }
function bestDrop(t, s, skip, anyone = false) {
  let best = null, bestTot = -1e9;
  const kd = D.P[s] && (D.P[s].p === 'K' || D.P[s].p === 'DEF');
  const starters = new Set(anyone ? [] : lineup(roster(t), W0).st.map(x => x.s).filter(Boolean));
  for (const d of roster(t)) {
    if (d === s || S.adds.has(d) || (skip && skip.has(d))) continue;
    if (kd && keeper(d)) continue;
    if (starters.has(d) && !startsFor(t, s, d, W0)) continue;
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
// ---------- rival-by-rival prices (Nov 12 revamp) ----------
// The ladder below was right on average but far too hopeful for stars late in the season: its 10-30% "coin flips"
// won 1 time in 79 in weeks 6-9 (Nacua, Javonte, Taylor, Pickens and Warren went 0 for 5), because players nobody
// claimed ($0) were pooled with stars. D.rival_model (fitted by build.py from every past waiver run) instead asks
// each rival: how likely is he to claim this player (by how good the player is and how much he'd help that rival),
// and what share of HIS OWN money would he bid (capped by his budget and his own habits). A bid wins only if it beats
// every rival: ties go to the better waiver spot, and Michael is last, so any rival claim beats or ties a $0 claim.
const RANK_TIER = rk => rk === 1 ? 0 : rk <= 3 ? 1 : rk <= 8 ? 2 : 3;      // the target's rank among this week's freed players
const NEED_TIER = g => g < 1 ? 0 : g < 3 ? 1 : g < 6 ? 2 : 3;              // lineup points a week he'd add for that rival
function claimChance(rk, g) { const M = D.rival_model, k = rk + ',' + NEED_TIER(g); return k in M.q ? M.q[k] : M.q_base; }
// chance a rival with budget B bids b or more, given he claims
function bidsAtLeast(rk, t, B, b) {
  if (b <= 0) return 1;
  if (b > B) return 0;
  const M = D.rival_model, xs = M.shares[rk] || M.all, sc = M.scale[t] ?? 1, cap = (M.cap[t] ?? 1) * 1.15;
  let c = 0; for (const x of xs) if (Math.min(cap, x * sc) * B >= b - 0.5) c++;
  return xs.length ? c / xs.length : 0;
}
const rivalModel = r => !!(D.rival_model && r && r.rk !== undefined && r.needs);
function rivalWin(b, r) {
  let p = 1;
  for (const t of ALIVE) {
    if (t === ME) continue;
    p *= 1 - claimChance(r.rk, r.needs[t] || 0) * bidsAtLeast(r.rk, t, D.teams[t].faab, b);
  }
  return p;
}
// each rival's chance to claim him and the bid he'd likely make (the middle of his range), richest threat first
function rivalOdds(r) {
  if (!rivalModel(r)) return [];
  const out = [];
  for (const t of ALIVE) {
    if (t === ME) continue;
    const B = D.teams[t].faab, q = claimChance(r.rk, r.needs[t] || 0);
    let lo = 0, hi = B;                                     // median bid if he claims: the b where P(bid >= b) crosses 50%
    while (lo < hi) { const m = Math.ceil((lo + hi) / 2); if (bidsAtLeast(r.rk, t, B, m) >= 0.5) lo = m; else hi = m - 1; }
    out.push({ t, claim: q, bid: lo, faab: B });
  }
  return out.sort((a, b) => b.claim * (b.bid + 1) - a.claim * (a.bid + 1));
}

// chance that a bid of b beats every rival. With D.rival_model and a priced row (r.rk, r.needs): rival by rival.
// Otherwise the old ladder: how past winning bids compared with the model's estimate for the same claim
// (D.ladder: sorted ratios winning bid / estimate; "hi" for estimates of $10+)
function winChance(b, est, r) {
  if (rivalModel(r)) return rivalWin(b, r);
  const xs = D.ladder ? (est >= 10 && D.ladder.hi.length ? D.ladder.hi : D.ladder.lo) : null;
  if (!xs || !xs.length) return b >= est ? 0.5 : 0;
  let c = 0;
  for (const x of xs) if (x * est < b || (b === 0 && x === 0)) c++;
  return c / xs.length;
}
function priceFor(chance, est, cap = 999, r = null) {
  for (let b = 0; b <= cap; b++) if (winChance(b, est, r) >= chance) return b;
  return null;
}
// Likely rival bids on the same scale as the win chance (Q-039). threats() guesses each rival's bid from his
// boldest past bids, and past claims went for less than that guess (often $0: nobody claimed him), which the
// ladder measures. So each guess is scaled by (price that wins half of comparable claims) / (raw estimate);
// `raw` keeps the unscaled guess. Without a ladder the guesses are shown as they are.
function rivalBids(r) {
  if (rivalModel(r)) return rivalOdds(r).filter(x => x.claim >= 0.05).map(x => ({ t: x.t, bid: x.bid, raw: x.bid, claim: x.claim, faab: x.faab }));
  const th = r.th || [];
  if (!th.length) return [];
  const f = D.ladder && r.est ? (priceFor(.5, r.est) ?? r.est) / r.est : 1;
  return th.map(x => ({ t: x.t, bid: Math.round(x.bid * f), raw: x.bid }));
}
// a waiver claim the model recommends (a $0 claim is still a claim: it needs a drop and can beat no claim)
// Calls by honest win chance (Nov 12): Bid 50%+, Coin flip 25-50%, Long shot 10-25% (worth a try, expect to lose);
// under 10% at every bid worth making is Skip. Before, "Coin flip" covered anything under 50% and its 10-30% bids on stars
// won 1 time in 79.
const isBid = r => r.call === 'Bid' || r.call === 'Coin flip' || r.call === 'Long shot' || r.call === 'Backup';
const MIN_CHANCE = 0.10;
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
  const amts = new Set([r.bid, priceFor(.25, r.est, 999, r), priceFor(.5, r.est, 999, r), priceFor(.8, r.est, faab, r), Math.min(value, spend)]
    .filter(b => b !== null && (b > 0 || (b === r.bid && isBid(r))) && b <= faab));
  return [...amts].sort((a, b) => a - b).map(b => { const p = winChance(b, r.est, r); return { bid: b, chance: p, payoff: p * (value - b) }; });
}

let BASE = null;
function computeBase() {
  PJ = {}; RATE = null;
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
    let gR = 0, gN = 0; WEEKS.forEach((w, i) => { const g = lineup(mine, w).tot - myBaseTot[i]; gR += g; if (i < NEAR.length) gN += g; });
    if (gR < 0.5 && !freed.includes(s)) continue;
    rows.push({ s, freed: freed.includes(s), g1, gR, gNear: gN / Math.max(1, NEAR.length), drop });
  }
  const perPos = {};
  const pick = rows.filter(r => !r.added).sort((a, b) => b.gR - a.gR).filter(r => { if (r.freed) return true; const p = D.P[r.s].p; perPos[p] = (perPos[p] || 0) + 1; return perPos[p] <= 3; }).slice(0, 24);
  rows.splice(0, rows.length, ...rows.filter(r => r.added), ...pick);
  pick.forEach(r => { gains(r); if (r.freed) { r.th = threats(r.s); r.est = rawEstimate(r.th); } });
  rankFreed(pick.filter(r => r.freed));
  return rows;
}
// rival-model inputs for freed rows: rank tier among this week's freed players (by projected points over the next
// weeks) and the lineup points each rival would gain
function rankFreed(rows) {
  const base = s => NEAR.reduce((a, w) => a + proj(s, w), 0) / Math.max(1, NEAR.length);
  rows.slice().sort((a, b) => base(b.s) - base(a.s)).forEach((r, i) => {
    r.rk = RANK_TIER(i + 1);
    r.needs = {}; for (const t of ALIVE) if (t !== ME) r.needs[t] = rivalGain(t, r.s);
  });
}
// extra expected weeks and win odds from adding r.s and dropping r.drop
function gains(r) {
  const sm = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, [r.s], r.drop) }), Math.max(500, Math.round(S.sims / 2)))[ME];
  r.dW = sm.expWeeks - BASE.quick.expWeeks; r.dWin = sm.pWin - BASE.quick.pWin;
  r.dCut = BASE.quick.pCut[W0] - sm.pCut[W0];      // how much this add lowers his chance of being cut this week
}
// rule 13: is his cut risk this week high enough that the reserve may go on a claim that keeps him alive?
const myCutRisk = () => (BASE && BASE.sim ? BASE.sim[ME].pCut[W0] : 0);
const reserveReleased = () => myCutRisk() >= RULES.release_reserve_at_cut_risk;
const savesMe = r => r.dCut !== undefined && r.dCut >= RULES.release_min_survival_gain;

// extra expected weeks and win odds from r on top of earlier claims `prior` ([{s, drop}]) that all won (Q-053)
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
  const deals = rows.filter(r => r.freed && r.dWin > 0.0005).map(r => ({ v: r.dWin * 100, c: Math.max(1, priceFor(rivalModel(r) ? .5 : .8, r.est, 999, r) || r.est) }))
    .sort((a, b) => b.v / b.c - a.v / a.c);
  let used = 0, rate = null;
  for (const d of deals) { rate = d.c / d.v; used += runs * d.c; if (used >= spend) break; }
  return rate;
}
const dollarsPerPoint = rows => S.dpp > 0 ? S.dpp : autoDpp(rows);

function isMarginal(r) {
  const p = D.P[r.s];
  return !!p && (p.p === 'K' || p.p === 'DEF' || (r.gNear !== undefined && r.gNear < RULES.marginal_pts_per_week));
}
function bigCap(s) {
  const p = D.P[s], faab = D.teams[ME].faab;
  if (p && (RULES.league_winners || []).some(n => n.toLowerCase() === p.n.toLowerCase())) return 1e9;
  return Math.max(RULES.big_bid_min, Math.floor(faab * RULES.big_bid_share));
}
// The call for every candidate. Freed players (on waivers): value = win odds added x $ per point; the bid is the
// amount with the best (chance of winning) x (value - bid); then all bids together must fit FAAB minus reserve.
function decideAll(rows) {
  const faab = D.teams[ME].faab, spend = Math.max(0, faab - S.reserve), dpp = dollarsPerPoint(rows);
  // rule 13: only a claim that lowers his cut risk this week may dip into the reserve, and only when that risk is high
  const released = reserveReleased(), spendFor = r => (released && savesMe(r) ? faab : spend);
  const price = r => {        // value, best bid and call for one candidate at its current drop
    r.spendCap = spendFor(r);
    if (outNow(r.s)) return Object.assign(r, { call: 'Skip', bid: 0, value: 0, chance: null, options: [],
      price: r.freed ? (priceFor(.5, r.est, 999, r) ?? r.est) : 0, price80: r.freed ? (priceFor(.8, r.est, 999, r) ?? r.est) : 0,
      why: 'out this week (injury or IR): not worth a roster spot now' });
    if (!r.freed) return Object.assign(r, { call: r.dWin >= MIN_WIN ? 'Add free' : 'Skip', bid: 0, value: 0, price: 0, price80: 0, chance: null,
      why: r.dWin >= MIN_WIN ? 'free agent' : 'adds too little to matter' });
    const value = dpp ? Math.floor(r.dWin * 100 * dpp) : 0;
    // his rules: a marginal claim (K, DEF, or under a couple of lineup points a week) goes in at $0; above the big-bid
    // line only for a player he has named a league-winner
    const marginal = isMarginal(r), big = bigCap(r.s);
    const cap = marginal ? 0 : Math.min(r.spendCap, value, big);
    // $0 counts with its own payoff: a $1 bid that wins no more often than $0 buys nothing (Q-038)
    const p0 = winChance(0, r.est, r);
    const bestUpTo = c => { let x = { b: 0, ev: p0 * value, p: p0 }; for (let b = 1; b <= c; b++) { const p = winChance(b, r.est, r), ev = p * (value - b); if (ev > x.ev + 1e-9) x = { b, ev, p }; } return x; };
    const best = bestUpTo(cap);
    // the cap bites when the bid it would make without the big-bid line is above that line
    const free = !marginal && big < Math.min(r.spendCap, value) ? bestUpTo(Math.min(r.spendCap, value)) : best, bites = free.b > big;
    const small = value < 1 || r.dWin < MIN_WIN, slim = best.p < MIN_CHANCE;
    const call = small ? 'Skip' : best.ev <= 0 ? 'Priced out' : slim ? 'Skip' : best.p >= .5 ? 'Bid' : best.p >= .25 ? 'Coin flip' : 'Long shot';
    Object.assign(r, { call, bid: isBid({ call }) ? best.b : 0, chance: best.p, value, ev: best.ev,
      price: priceFor(.5, r.est, 999, r) ?? r.est, price80: priceFor(.8, r.est, 999, r) ?? r.est, marginal, capped: bites ? big : null,
      why: small ? 'adds too little to matter' : best.ev <= 0 ? 'likely price is above his value to you'
        : slim ? `under ${MIN_CHANCE * 100}% to win at any bid worth making`
        : marginal ? `marginal (${D.P[r.s].p === 'K' || D.P[r.s].p === 'DEF' ? D.P[r.s].p : `+${(r.gNear || 0).toFixed(1)} lineup pts a week`}): $0 claim, your rule`
        : bites ? `capped at $${big} (would bid $${free.b}): big money only for players you've named league-winners` : '' });
    r.options = small ? [] : bidOptions(r, value, r.spendCap);
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
    if (used + r.bid > r.spendCap) { Object.assign(r, { call: 'Skip', bid: 0, why: 'your other bids use the budget' }); continue; }
    r.usesReserve = used + r.bid > spend;
    used += r.bid; drops.add(r.drop); taken.push(r);
  }
  addBackups(rows, taken, price);
  return { dpp, spend, used, released };
}

// Backups (Sleeper's copy rule, Nov 12 revamp): with a full roster, a claim that shares a drop with a claim that already
// won fails ("too many players"), so a lower claim on the same drop only runs if every claim above it on that drop lost.
// A backup never raises what you can spend: the most a chain of claims on one drop can cost is its top bid. In this
// league's history no team ever won two claims with one drop (84 such claims failed). Backups go strictly lower than
// the claims above them, so Sleeper's own order (highest bid first) runs them in the right order; $0 backups run in
// your list order. Michael already does this by hand (45 of his backups never needed to fire).
const MAX_BACKUPS = 3;
function addBackups(rows, taken, price) {
  const chains = {};
  for (const x of taken) if (x.drop) (chains[x.drop] = chains[x.drop] || []).push(x);
  const order = () => Object.values(chains).forEach(c => { c.sort((a, b) => b.bid - a.bid); c.forEach((x, i) => { x.chain = x.drop; x.chainOrder = i + 1; }); });
  order();
  if (!Object.keys(chains).length) return;
  const inChain = new Set(taken);
  const pool = rows.filter(r => !r.added && r.freed && !inChain.has(r) && r.dWin >= MIN_WIN && !outNow(r.s) && r.est !== undefined);
  for (let n = 0; n < MAX_BACKUPS; n++) {
    let best = null;
    for (const r of pool) {
      if (inChain.has(r)) continue;
      for (const [d, chain] of Object.entries(chains)) {
        const kd = ['K', 'DEF'].includes(D.P[r.s].p);
        if (r.s === d || (kd && keeper(d))) continue;
        if (lineup(roster(ME), W0).st.some(x => x.s === d) && !startsFor(ME, r.s, d, W0)) continue;
        const low = Math.min(...chain.map(x => x.bid));
        const cand = Object.assign({}, r, { drop: d });
        if (d !== r.drop) { if (!BASE) continue; gains(cand); }   // (no simulation loaded: only its own drop can be judged)
        price(cand);
        if (!isBid(cand) && cand.call !== 'Priced out') continue;
        // the best bid under the chain's lowest (or $0 behind a $0 claim)
        const cap = Math.min(low > 0 ? low - 1 : 0, cand.marginal ? 0 : 1e9, bigCap(r.s));
        let b0 = { b: 0, ev: winChance(0, cand.est, cand) * cand.value, p: winChance(0, cand.est, cand) };
        for (let b = 1; b <= cap; b++) { const p = winChance(b, cand.est, cand), ev = p * (cand.value - b); if (ev > b0.ev + 1e-9) b0 = { b, ev, p }; }
        const lose = chain.reduce((a, x) => a * (1 - (x.chance ?? 0)), 1), gain = lose * b0.ev;
        if (b0.ev > 0 && b0.p >= MIN_CHANCE && gain > 0.05 && (!best || gain > best.gain)) best = { gain, r, d, cand, b0, chain };
      }
    }
    if (!best) break;
    const { r, d, cand, b0, chain } = best;
    Object.assign(r, { drop: d, dW: cand.dW, dWin: cand.dWin, value: cand.value, call: 'Backup', bid: b0.b, chance: b0.p, ev: b0.ev,
      price: cand.price, price80: cand.price80, marginal: cand.marginal, options: [],
      firesIf: chain.map(x => x.s), why: `backup: runs only if you lose ${chain.map(x => pname(x.s)).join(' and ')} (same drop)` });
    chain.push(r); inChain.add(r); order();
  }
}

// One line on why, for every claim and free add (his rule: a plain reason on each move), plus anything to check first.
function whyLine(r) {
  const p = D.P[r.s], bits = [];
  if (r.drop !== undefined) {
    const starts = WEEKS.filter(w => startsFor(ME, r.s, r.drop, w)).length;
    bits.push(starts ? `starts for you ${starts} of the next ${WEEKS.length} weeks` : 'bench depth (starts no week as rosters stand)');
  }
  if (r.dWin) bits.push(`${r.dWin >= 0 ? '+' : ''}${(r.dWin * 100).toFixed(1)} pts of title odds`);
  if (r.freed && isBid(r) && rivalModel(r)) {
    const can = rivalOdds(r).filter(x => x.faab >= r.bid && x.claim >= 0.05).slice(0, 2);
    bits.push(can.length ? `can be outbid by ${can.map(x => `${tname(x.t)} ($${x.faab}, ${Math.round(x.claim * 100)}% to claim)`).join(', ')}` : 'no rival likely to outbid this');
  }
  const flags = [];
  if (p.inj) flags.push(`${p.inj}: check news from the last 48 hours`);
  else if (proj(r.s, W0) === 0 && !(p.bye || []).includes(W0)) flags.push(`projected 0 in week ${W0} with no injury tag: check news`);
  if ((p.bye || []).some(w => w >= W0 && w <= W0 + 1)) flags.push(`bye week ${(p.bye || []).find(w => w >= W0)}`);
  // his rules first: why the bid is capped or $0
  if (r.usesReserve) bits.unshift(`uses your reserve: your cut risk this week is ${Math.round(myCutRisk() * 100)}% and this lowers it ${Math.round((r.dCut || 0) * 100)} pts (your rule)`);
  if (r.capped) bits.unshift(`capped at $${r.capped}: big money only for players you've named league-winners`);
  else if (r.marginal && isBid(r)) bits.unshift('$0 claim: a marginal add (your rule)');
  return bits.join('; ') + (flags.length ? ` (${flags.join('; ')})` : '');
}
// The claims as you'd enter them in Sleeper: highest bid first (Sleeper runs them in that order), backups right after
// the claims they back up, $0 claims last in this order (your drag order breaks ties).
function claimList(rows) {
  return rows.filter(r => !r.added && r.freed && isBid(r))
    .sort((a, b) => b.bid - a.bid || (a.chain === b.chain ? (a.chainOrder || 0) - (b.chainOrder || 0) : (b.ev || 0) - (a.ev || 0)));
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
    bid: r.bid, win_chance: r.freed && r.chance !== null ? r3(r.chance) : null, your_max: r.freed ? Math.min(r.spendCap ?? money.spend, r.value) : 0,
    cut_risk_drop: r.dCut !== undefined ? r3(r.dCut) : null, uses_reserve: !!r.usesReserve,
    call: r.call, why: r.why || null, why_line: r.dW !== undefined ? whyLine(r) : null,
    chain_drop: r.chain && D.P[r.chain] ? D.P[r.chain].n : null, chain_order: r.chainOrder || null,
    fires_if: r.firesIf ? `you lose ${r.firesIf.map(pname).join(' and ')}` : null,
    // chance of winning at every bid from $0 to your FAAB (index = bid), for the side-by-side bookmark
    win_curve: r.freed && r.est ? Array.from({ length: D.teams[ME].faab + 1 }, (_, b) => Math.round(winChance(b, r.est, r) * 100) / 100) : null,
    // rivals with the money to beat this bid (ties go to them: you are last in waiver order) and their chance to claim him
    can_outbid: r.freed ? rivalOdds(r).filter(x => x.faab >= r.bid && x.claim >= 0.05).map(x => ({ team: tname(x.t), faab: x.faab, claim_chance: r3(x.claim) })) : [],
    bid_options: (r.options || []).map(o => ({ bid: o.bid, win_chance: r3(o.chance), avg_payoff: r1(o.payoff), recommended: o.bid === r.bid,
      over_spendable: o.bid > (r.spendCap ?? money.spend) })),
    likely_rival_bids: rivalBids(r).slice(0, 3).map(x => ({ team: tname(x.t), bid: x.bid, raw: x.raw, ...(x.claim !== undefined ? { claim_chance: r3(x.claim) } : {}) })) }));
  const sim = BASE.sim;
  return {
    league: D.league, data_as_of: D.asof, last_sleeper_move: D.data_as_of, week: W0, last_week: LAST,
    cut: D.cut ? { team: tname(CUT), week: D.cut.week, confirmed: D.cut.confirmed, freed_status: D.cut.freed_status } : null,
    // FAAB claims are only possible while the cut team's players sit on waivers; otherwise est_price is 0
    // everywhere except projected-freed rows, which are planning numbers for after the cut
    waivers_open: !!D.cut && D.cut.freed_status === 'on waivers', next_waiver_run: D.next_waiver_run,
    waivers: D.waivers, my_team: tname(ME), my_faab: D.teams[ME].faab, reserve: S.reserve,
    budget: { spendable: money.spend, recommended_bids_total: money.used, dollars_per_win_point: money.dpp ? r1(money.dpp) : null,
              reserve_released: !!money.released, my_cut_risk: r3(myCutRisk()) },
    settings: { projections: 'Sleeper weekly', score_sd: S.sd, score_sd_measured_from: D.sd ? D.sd.n : null, sd_growth_per_week: SD_GROWTH,
                rival_aggression: S.aggr, value: 'win odds (winner takes all)', sims: S.sims,
                price_ladder_claims: D.ladder ? D.ladder.lo.length + D.ladder.hi.length : 0,
                price_model: D.rival_model ? `rival by rival (fitted on ${D.rival_model.n} rival-player chances)` : 'ladder' },
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
    // the list to enter in Sleeper, in order (Sleeper runs claims highest bid first; ties in this order)
    claim_list: claimList(rows).map((r, i) => ({ order: i + 1, name: D.P[r.s].n, pos: D.P[r.s].p, team: D.P[r.s].t, sleeper_id: r.s,
      bid: r.bid, drop: r.drop ? pname(r.drop) : null, drop_id: r.drop || null, win_chance: r.chance !== null ? r3(r.chance) : null,
      kind: r.call === 'Backup' ? 'backup' : 'claim', fires_if: r.firesIf ? `you lose ${r.firesIf.map(pname).join(' and ')}` : null,
      why: whyLine(r) })),
    worst_case_spend: (() => { const c = {}; for (const r of claimList(rows)) c[r.drop] = Math.max(c[r.drop] || 0, r.bid); return Object.values(c).reduce((a, b) => a + b, 0); })(),
    rules: { reserve: S.reserve,
             reserve_rule: `keeps $${S.reserve} while your cut risk this week is under ${Math.round(RULES.release_reserve_at_cut_risk * 100)}%; ` +
               `at ${Math.round(RULES.release_reserve_at_cut_risk * 100)}% or more, a claim that lowers it by ${Math.round(RULES.release_min_survival_gain * 100)}+ pts may use it` +
               ` (now ${Math.round(myCutRisk() * 100)}%: ${money.released ? 'released' : 'kept'})`,
             league_winners: RULES.league_winners, big_bid_cap: bigCap(null),
             marginal: `K, DEF and adds worth under ${RULES.marginal_pts_per_week} lineup pts a week go in at $0`,
             starters: 'never drops a player in this week\'s lineup unless the add starts in his place' },
  };
}

// ---------- try a move (Q-054): any adds and drops, judged by the same simulation as the bids ----------
// Michael, Nov 11: "should I put in a claim for KC Concepcion and drop Tre Tucker?" The Try-a-move box on the War Room
// and on the Guillotine league page (docs/lib/move.js) calls tryMove() with the players he picks.
function ownerOf(s) { for (const t of Object.keys(D.teams)) if (t !== CUT && D.teams[t].roster.includes(s)) return t; return null; }
// every player the model knows, for the search box: who has him now
function playerList() {
  const freed = new Set(freedPlayers()), mine = new Set(roster(ME));
  return Object.keys(D.P).map(s => {
    const p = D.P[s], o = mine.has(s) ? ME : ownerOf(s);
    return { id: s, name: p.n, pos: p.p, team: p.t, own: o === ME ? 'me' : o ? tname(o) : null, freed: freed.has(s), inj: p.inj || (p.st === 'RES' ? 'IR' : '') };
  });
}
let RATE = null;   // $ per point of win odds from this week's candidates; only needed to price a claim, so worked out once on demand
// Each add needs a drop (rosters are full): drops[i] goes with adds[i]; a missing one is the model's own pick (bestDrop).
// Returns the change in win odds, expected weeks alive, this week's cut risk and each week's lineup points, the claim
// price and win chance for a player on waivers, a verdict ('worth' / 'not' / 'coin' / 'unavailable') and its reasons.
function tryMove(adds, drops) {
  adds = (adds || []).filter(s => D.P[s]); drops = (drops || []).slice(0, adds.length);
  if (!adds.length) return null;
  if (!BASE) computeBase();
  const n = Math.max(500, Math.round(S.sims / 2));
  const base = BASE.quick || (BASE.quick = simulate(BASE.projs, n)[ME]);
  const mine = new Set(roster(ME)), used = new Set(drops.filter(Boolean)), picked = [];
  adds.forEach((s, i) => {
    let d = drops[i] && mine.has(drops[i]) ? drops[i] : null, auto = false;
    if (!d) { const sk = new Set([...used, ...adds]); d = bestDrop(ME, s, sk) || bestDrop(ME, s, sk, true); auto = true; if (d) used.add(d); }
    picked.push({ s, drop: d, auto });
  });
  const A = picked.map(x => x.s), Dr = picked.map(x => x.drop).filter(Boolean);
  const now = BASE.projs[ME], after = teamProj(ME, A, Dr);
  const weeks = WEEKS.map(w => ({ w, d: Math.round((after[w] - now[w]) * 10) / 10 }));
  const sm = simulate(Object.assign({}, BASE.projs, { [ME]: after }), n)[ME];
  const out = { week: W0, last: LAST, adds: [], drops: [], weeks, g1: weeks[0] ? weeks[0].d : 0, gR: weeks.reduce((a, x) => a + x.d, 0),
    dWin: sm.pWin - base.pWin, dW: sm.expWeeks - base.expWeeks, winNow: base.pWin, winWith: sm.pWin,
    cutNow: base.pCut[W0], cutWith: sm.pCut[W0], waivers: D.waivers, open: !!D.cut && D.cut.freed_status === 'on waivers' };
  const info = s => { const p = D.P[s]; return { id: s, name: p.n, pos: p.p, team: p.t, inj: p.inj || '', ir: p.st === 'RES',
    bye: (p.bye || []).filter(w => w >= W0 && w <= LAST), out: outNow(s), proj: Math.round(proj(s, W0) * 10) / 10, avg: p.a }; };
  for (const x of picked) {
    const a = info(x.s), o = mine.has(x.s) ? ME : ownerOf(x.s);
    a.drop = x.drop; a.autoDrop = x.auto;
    a.status = o === ME ? 'yours' : o ? 'owned' : out.open && freedPlayers().includes(x.s) ? 'waivers' : 'free';
    if (o && o !== ME) a.owner = tname(o);
    if (a.status === 'waivers') {
      // his claim alone (with his own drop), priced exactly like the bids table
      if (RATE === null) RATE = S.dpp > 0 ? S.dpp : (dollarsPerPoint(candidates()) || 0);
      const solo = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, [x.s], x.drop) }), n)[ME];
      const th = threats(x.s), row = { s: x.s, freed: true, drop: x.drop, th, est: rawEstimate(th), dW: solo.expWeeks - base.expWeeks,
        dWin: solo.pWin - base.pWin, gR: 0 };
      rankFreed([row].concat(freedPlayers().filter(f => f !== x.s).map(f => ({ s: f }))));
      const keep = S.dpp; S.dpp = RATE || keep; decideAll([row]); S.dpp = keep;
      Object.assign(a, { call: row.call, bid: row.bid, chance: row.chance, price: row.price, price80: row.price80, value: row.value });
    }
    out.adds.push(a);
  }
  out.drops = picked.filter(x => x.drop).map(x => info(x.drop));
  // verdict: win odds first; inside the simulation's noise, the next two weeks' lineup points decide (a bye next week costs a
  // week you have to survive), else it's a coin flip
  const near = weeks.slice(0, 2).reduce((a, x) => a + x.d, 0);
  const bad = out.adds.filter(a => a.status === 'owned' || a.status === 'yours');
  // (a move that gains nothing measurable and loses lineup points over the season isn't worth making)
  out.verdict = bad.length ? 'unavailable' : out.dWin >= MIN_WIN ? 'worth' : out.dWin <= -MIN_WIN ? 'not'
    : near <= -1 ? 'not' : near >= 1 && out.dWin > 0 ? 'worth' : out.gR <= -1 ? 'not' : 'coin';
  // one add with the drop he chose: would another drop do clearly better?
  if (picked.length === 1 && !picked[0].auto) {
    const alt = bestDrop(ME, picked[0].s);
    if (alt && alt !== picked[0].drop) {
      const sa = simulate(Object.assign({}, BASE.projs, { [ME]: teamProj(ME, A, [alt]) }), n)[ME];
      if (sa.pWin - sm.pWin >= MIN_WIN) out.better = { drop: alt, name: pname(alt), dWin: sa.pWin - base.pWin };
    }
  }
  const R = [], sg = (x, d = 1) => (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d), pc = x => (x > 0 && x < 0.005 ? '<1' : Math.round(x * 100)) + '%';
  R.push(`Win the league: ${pc(out.winNow)} → ${pc(out.winWith)} (${sg(out.dWin * 100)} points of win odds); expected weeks alive ${sg(out.dW, 2)}.`);
  if (Math.abs(out.dWin) < MIN_WIN) R.push(`A change under ${MIN_WIN * 100} points is inside the simulation's noise, so the lineup points below decide.`);
  R.push(`Week ${W0} lineup ${sg(out.g1)} pts; your week ${W0} cut risk ${pc(out.cutNow)} → ${pc(out.cutWith)}.`);
  const big = weeks.slice(1).filter(x => Math.abs(x.d) >= 3).slice(0, 3);
  R.push(`Weeks ${W0}–${LAST} lineup ${sg(out.gR, 0)} pts in total` + (big.length ? ` (${big.map(x => `week ${x.w} ${sg(x.d)}`).join(', ')})` : '') + '.');
  for (const p of out.adds.concat(out.drops)) {
    const bits = [];
    if (p.bye.length) bits.push(`bye week ${p.bye[0]}`);
    if (p.ir) bits.push('on IR'); else if (p.inj) bits.push(p.inj);
    if (p.out) bits.push(`out for week ${W0}`);
    if (bits.length) R.push(`${p.name}: ${bits.join(', ')}.`);
  }
  for (const a of out.adds) {
    if (a.status === 'owned') R.push(`${a.name} is on ${a.owner}'s roster: not available to add.`);
    else if (a.status === 'yours') R.push(`${a.name} is already on your roster.`);
    else if (a.status === 'waivers') R.push(`${a.name} is on waivers until ${D.waivers}: likely price $${a.price} (wins about half of similar claims) to $${a.price80} (about 80%). `
      + `He's worth $${a.value} to you; ` + (isBid(a) ? `bid $${a.bid} (${pc(a.chance)} to win${a.call === 'Long shot' ? ', a long shot' : ''}).` : `the bids table says ${a.call.toLowerCase()}.`));
    else R.push(`${a.name} is a free agent: add him now for $0` + (out.open ? '' : ' (nothing is on waivers until the next cut)') + '.');
    if (a.autoDrop && a.drop) R.push(`No drop picked for ${a.name}: the model drops ${pname(a.drop)} (costs you the fewest points).`);
  }
  if (out.better) R.push(`Better drop: ${out.better.name} instead (${sg(out.better.dWin * 100)} points of win odds in total).`);
  out.reasons = R;
  return out;
}

// Calibration helper for build.py: the raw estimate for each past claim, rebuilt as of that waiver run.
function rawEstimates(sids) { PJ = {}; return sids.map(s => rawEstimate(threats(s))); }
// ...and what build.py fits the rival-by-rival model on: each target's projected points (to rank them) and the lineup
// points it would add for every surviving rival
function rivalInputs(sids) {
  PJ = {};
  return sids.map(s => ({ base: NEAR.reduce((a, w) => a + proj(s, w), 0) / Math.max(1, NEAR.length),
    needs: Object.fromEntries(ALIVE.filter(t => t !== ME).map(t => [t, Math.round(rivalGain(t, s) * 100) / 100])) }));
}
