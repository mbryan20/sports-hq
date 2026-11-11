// War Room page: rendering and controls. The model itself lives in model.js (shared with the GitHub build).
const $ = id => document.getElementById(id);
const esc = x => String(x).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// ---------- rendering ----------
const fmt = (x, d = 1) => (Math.round(x * 10 ** d) / 10 ** d).toFixed(d);
const pct = x => (x * 100 < 1 && x > 0 ? '<1' : Math.round(x * 100)) + '%';
function heatCell(v, lo, hi) {
  const z = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
  const bg = z < .33 ? 'var(--bad-soft)' : z < .66 ? 'var(--warn-soft)' : 'var(--good-soft)';
  return `<span class="heat" style="background:${bg}">${Math.round(v)}</span>`;
}
function riskPill(p) { return p >= .25 ? `<span class="pill p-bad">${pct(p)}</span>` : p >= .1 ? `<span class="pill p-warn">${pct(p)}</span>` : `<span class="pill p-good">${pct(p)}</span>`; }

// ---------- bids: sort / filter / phone cards ----------
// Remembered per device (localStorage can be blocked: everything still works without it).
const VIEW = (() => { const v = { pos: '', show: 'all', sort: 'dwin' }; try { Object.assign(v, JSON.parse(localStorage.getItem('wr2-view') || '{}')); } catch (e) {} return v; })();
const saveView = () => { try { localStorage.setItem('wr2-view', JSON.stringify(VIEW)); } catch (e) {} };
const SORTS = {
  dwin: ['Win odds added', r => r.dWin], bid: ['Your bid', r => r.bid || 0], price: ['Likely price', r => r.freed ? r.price : -1],
  chance: ['Win chance', r => isBid(r) ? r.chance : -1], value: ['Value to you', r => r.freed ? r.value : -1],
  season: ['Season gain', r => r.gR], name: ['Name', r => D.P[r.s].n],
};
const CLAIMS = new Set(['Bid', 'Coin flip', 'Add free']);
let BIDROWS = [], MONEY = null;

function renderBids() {
  const rows = candidates(), money = decideAll(rows);
  BIDROWS = rows.filter(r => r.added || r.dW !== undefined); MONEY = money;
  let top = null;
  for (const r of BIDROWS) if (r.freed && isBid(r) && (!top || r.ev > top.ev)) top = r;
  $('budgetline').textContent = money.dpp ? `Value rate: $${fmt(money.dpp)} per point of win odds${S.dpp > 0 ? '' : ' (auto)'}. Bids total $${money.used} of the $${money.spend} you can spend.` : 'No players on waivers right now: free adds only.';
  drawBids();
  return top;
}

function bidBar() {
  const n = p => BIDROWS.filter(r => D.P[r.s].p === p).length;
  const chips = [['', 'All'], ...['QB', 'RB', 'WR', 'TE', 'K', 'DEF'].map(p => [p, p])].filter(([p]) => !p || n(p))
    .map(([p, lab]) => `<button class="chip" data-pos="${p}" aria-pressed="${VIEW.pos === p}">${lab}${p ? ' <span>' + n(p) + '</span>' : ''}</button>`).join('');
  const opt = (o, cur) => Object.entries(o).map(([k, v]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${v}</option>`).join('');
  return `<div class="chips" role="group" aria-label="Position">${chips}</div>
    <label class="sub">Show <select id="bshow">${opt({ all: 'All players', freed: 'On waivers', fa: 'Free agents', claims: 'Claims only' }, VIEW.show)}</select></label>
    <label class="sub">Sort <select id="bsort">${opt(Object.fromEntries(Object.entries(SORTS).map(([k, v]) => [k, v[0]])), VIEW.sort)}</select></label>`;
}

function drawBids() {
  const rows = BIDROWS, money = MONEY;
  // how many recommended moves would drop the same player (a claim whose drop is gone fails in Sleeper)
  const dropUse = {};
  for (const r of rows) if (!r.added && CLAIMS.has(r.call) && r.drop) dropUse[r.drop] = (dropUse[r.drop] || 0) + 1;
  const key = SORTS[VIEW.sort] ? SORTS[VIEW.sort][1] : SORTS.dwin[1];
  const out = rows.filter(r => (!VIEW.pos || D.P[r.s].p === VIEW.pos)
      && (VIEW.show === 'all' || (VIEW.show === 'freed' && r.freed) || (VIEW.show === 'fa' && !r.freed) || (VIEW.show === 'claims' && (r.added || CLAIMS.has(r.call)))))
    .sort((a, b) => (b.added - a.added) || (VIEW.sort === 'name' ? key(a).localeCompare(key(b)) : key(b) - key(a)) || (b.dWin - a.dWin));
  $('bidbar').innerHTML = bidBar();
  const pill = c => `<span class="pill ${{ 'Bid': 'p-good', 'Add free': 'p-good', 'Coin flip': 'p-warn', 'Priced out': 'p-bad' }[c] || 'p-mute'}">${c}</span>`;
  const drop = r => r.drop && D.P[r.drop] ? esc(D.P[r.drop].n) + (dropUse[r.drop] > 1 && CLAIMS.has(r.call) ? ` <span class="pill p-warn" title="More than one move here drops this player">used ${dropUse[r.drop]}×</span>` : '') : '—';
  const opts = r => r.freed ? (r.options || []).map(o => `<div${o.bid === r.bid && isBid(r) ? ' class="best"' : ''}>$${o.bid} · ${pct(o.chance)} · ${o.payoff >= 0 ? '+' : '−'}$${Math.abs(Math.round(o.payoff))}${o.bid === r.bid && isBid(r) ? ' ★' : ''}${o.bid > money.spend ? ' (over budget)' : ''}</div>`).join('') || '—' : '$0';
  const rivals = r => rivalBids(r).slice(0, 3).map(x => `${esc(tname(x.t))} ~$${x.bid}`).join(', ') || (r.freed ? 'No rival needs him much' : '—');
  const tag = p => `<b>${esc(p.n)}</b> <span class="pos">${p.p} ${p.t}${p.inj ? ' · ' + p.inj : ''}${p.st === 'RES' ? ' · IR' : ''}</span>`;
  const btn = r => `<button class="add" data-s="${r.s}" aria-pressed="${S.adds.has(r.s)}">${S.adds.has(r.s) ? '✓ Added' : '+ Add'}</button>`;
  const why = r => r.why && r.why !== 'free agent' ? '<div class="sub">' + esc(r.why) + '</div>' : '';
  const bye = p => p.bye.length ? 'Wk ' + p.bye[0] : 'done';
  const th = (k, lab, cls = '') => `<th class="${cls}${k ? ' sortable' : ''}"${k ? ` data-sort="${k}" aria-sort="${VIEW.sort === k ? 'descending' : 'none'}"` : ''}>${lab}${VIEW.sort === k ? ' ▾' : ''}</th>`;
  let html = `<thead><tr>${th('name', 'Player')}<th>Source</th><th>Bye</th><th class="n">Wk ${W0} gain</th>${th('season', 'Season gain', 'n')}${th('dwin', '+Win odds', 'n')}<th>Drop</th><th>Likely rival bids</th>${th('value', 'Value', 'n')}${th('bid', 'Bid options<br><span class="sub">bid · win chance · avg payoff</span>')}<th>Call</th><th></th></tr></thead><tbody>`;
  let cards = '';
  for (const r of out) {
    const p = D.P[r.s];
    if (r.added) {
      html += `<tr class="me"><td>${tag(p)}</td><td>${r.freed ? 'Freed' : 'Free agent'}</td><td colspan="9" class="sub">On your roster in this model</td><td>${btn(r)}</td></tr>`;
      cards += `<div class="card me"><div class="top">${tag(p)}${btn(r)}</div><div class="sub">On your roster in this model</div></div>`;
      continue;
    }
    html += `<tr><td>${tag(p)}</td><td>${r.freed ? 'Freed' : 'Free agent'}</td><td>${bye(p)}</td><td class="n">${fmt(r.g1)}</td><td class="n">${fmt(r.gR, 0)}</td>`
      + `<td class="n">${r.dWin >= 0 ? '+' : ''}${fmt(r.dWin * 100, 1)}%</td><td class="sub">${drop(r)}</td><td class="wrap">${rivals(r)}</td>`
      + `<td class="n">${r.freed ? '$' + r.value : '—'}</td><td class="opts">${opts(r)}</td><td>${pill(r.call)}${why(r)}</td><td>${btn(r)}</td></tr>`;
    cards += `<div class="card"><div class="top"><div>${tag(p)}<div class="sub">${r.freed ? 'On waivers' : 'Free agent'} · bye ${bye(p)}</div></div>${pill(r.call)}</div>`
      + `<div class="facts"><span><b>${r.dWin >= 0 ? '+' : ''}${fmt(r.dWin * 100, 1)}%</b> win odds</span>${r.freed ? `<span><b>$${r.value}</b> value</span>` : ''}<span>+${fmt(r.g1)} wk ${W0} · +${fmt(r.gR, 0)} season</span></div>`
      + (r.freed && isBid(r) ? `<div class="bidline">Bid <b>$${r.bid}</b> (${pct(r.chance)} to win)</div>` : '')
      + `<div class="sub">Drop: ${drop(r)}</div>`
      + (r.freed ? `<div class="opts">${opts(r)}</div><div class="sub">Rivals: ${rivals(r)}</div>` : '')
      + `${why(r)}<div class="foot">${btn(r)}</div></div>`;
  }
  $('cand').innerHTML = html + '</tbody>';
  $('cards').innerHTML = cards || '<p class="sub">No players match.</p>';
  $('bidcount').textContent = `${out.length} of ${rows.length} players`;
  document.querySelectorAll('#cand button.add, #cards button.add').forEach(b => b.onclick = () => { const s = b.dataset.s; S.adds.has(s) ? S.adds.delete(s) : S.adds.add(s); rerender(); });
  document.querySelectorAll('#bidbar .chip').forEach(b => b.onclick = () => { VIEW.pos = b.dataset.pos; saveView(); drawBids(); });
  $('bshow').onchange = e => { VIEW.show = e.target.value; saveView(); drawBids(); };
  $('bsort').onchange = e => { VIEW.sort = e.target.value; saveView(); drawBids(); };
  document.querySelectorAll('#cand th.sortable').forEach(t => t.onclick = () => { VIEW.sort = t.dataset.sort; saveView(); drawBids(); });
}

function renderLineup() {
  const L = lineup(roster(ME), W0);
  const on = new Set(L.st.map(x => x.s));
  let h = `<thead><tr><th>Slot</th><th>Player</th><th class="n">Wk ${W0} proj</th><th class="n">Season avg</th></tr></thead><tbody>`;
  for (const x of L.st) {
    const p = x.s ? D.P[x.s] : null;
    const flag = !p ? '<span class="pill p-bad">Empty</span>' : x.v < 4 ? ' <span class="pill p-bad">Weak</span>' : '';
    h += `<tr><td class="pos">${x.slot}</td><td>${p ? esc(p.n) + ' <span class="pos">' + p.p + ' ' + p.t + '</span>' : ''}${flag}</td><td class="n">${fmt(x.v)}</td><td class="n">${p ? fmt(p.a) : ''}</td></tr>`;
  }
  const bench = roster(ME).filter(s => !on.has(s) && D.P[s]);
  for (const s of bench) { const p = D.P[s]; const why = p.bye.includes(W0) ? 'bye' : p.inj === 'Out' ? 'out' : p.st === 'RES' ? 'IR' : ''; h += `<tr><td class="pos">BN</td><td class="sub">${esc(p.n)} <span class="pos">${p.p} ${p.t}${why ? ' · ' + why : ''}</span></td><td class="n">${fmt(proj(s, W0))}</td><td class="n">${fmt(p.a)}</td></tr>`; }
  $('mylineup').innerHTML = h + `<tr><td></td><td><b>Projected total</b></td><td class="n"><b>${fmt(L.tot)}</b></td><td></td></tr></tbody>`;
  const byes = roster(ME).filter(s => D.P[s] && D.P[s].bye.includes(W0)).map(s => D.P[s].n + ' (' + D.P[s].p + ')');
  $('mynote').textContent = byes.length ? `On bye in week ${W0}: ${byes.join(', ')}.` : '';
}

function renderSurv() {
  const s = BASE.sim[ME];
  const W = 520, H = 200, L = 34, B = 24, T = 10, R = 10;
  const x = w => L + (w - W0) / Math.max(1, LAST - W0) * (W - L - R), y = p => T + (1 - p) * (H - T - B);
  const pts = WEEKS.map(w => [x(w), y(s.pAlive[w] - s.pCut[w])]);
  let g = '';
  for (const p of [0, .25, .5, .75, 1]) g += `<line x1="${L}" x2="${W - R}" y1="${y(p)}" y2="${y(p)}" stroke="var(--line)"/><text x="${L - 4}" y="${y(p) + 3}" text-anchor="end">${p * 100}%</text>`;
  for (const w of WEEKS) g += `<text x="${x(w)}" y="${H - 8}" text-anchor="middle">W${w}</text>`;
  const path = 'M' + pts.map(p => p.join(',')).join('L');
  const area = path + `L${x(LAST)},${y(0)}L${x(W0)},${y(0)}Z`;
  g += `<path d="${area}" fill="var(--accent-soft)"/><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>`;
  const last = pts[pts.length - 1]; g += `<circle cx="${last[0]}" cy="${last[1]}" r="4" fill="var(--accent)"/>`;
  $('survchart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Chance you are still alive after each week">${g}</svg>`;
  $('survleg').innerHTML = `<span><i class="sw" style="background:var(--accent)"></i>Chance you're still alive after each week</span><span>Expected weeks survived: <b>${fmt(s.expWeeks, 1)}</b> of ${WEEKS.length}</span><span>Win the league: <b>${pct(s.pWin)}</b></span>`;
}

function renderForecast() {
  const sim = BASE.sim, P = BASE.projs;
  const order = ALIVE.slice().sort((a, b) => sim[a].expWeeks - sim[b].expWeeks);
  let lo = 1e9, hi = 0; for (const t of ALIVE) for (const w of WEEKS) { lo = Math.min(lo, P[t][w]); hi = Math.max(hi, P[t][w]); }
  let h = `<thead><tr><th>Team</th><th class="n">FAAB</th><th>Cut wk ${W0}</th><th>Cut by wk ${Math.min(LAST, W0 + 3)}</th><th class="n">Exp. weeks left</th><th class="n">Win</th>${WEEKS.map(w => `<th class="n">W${w}</th>`).join('')}</tr></thead><tbody>`;
  for (const t of order) {
    const s = sim[t], wk = Math.min(LAST, W0 + 3), by11 = 1 - (s.pAlive[wk] - s.pCut[wk]);
    h += `<tr class="${t === ME ? 'me' : ''}"><td><b>${esc(tname(t))}</b>${t === ME ? ' (you)' : ''}</td><td class="n">$${D.teams[t].faab}</td><td>${riskPill(s.pCut[W0])}</td><td>${riskPill(by11)}</td><td class="n">${fmt(s.expWeeks, 1)}</td><td class="n">${pct(s.pWin)}</td>${WEEKS.map(w => `<td class="n">${heatCell(P[t][w], lo, hi)}</td>`).join('')}</tr>`;
  }
  $('fc').innerHTML = h + '</tbody>';
}

function renderRivals() {
  const slotVals = {}; // t -> slotIdx -> avg over the next 4 weeks
  for (const t of ALIVE) { slotVals[t] = SLOTS.map(() => 0); for (const w of NEAR) lineup(roster(t), w).st.forEach((x, i) => slotVals[t][i] += x.v / NEAR.length); }
  const med = SLOTS.map((_, i) => { const v = ALIVE.map(t => slotVals[t][i]).sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; });
  const spentBig = {}; for (const h of D.hist) { const k = String(h.win); spentBig[k] = Math.max(spentBig[k] || 0, h.bid); }
  const order = ALIVE.slice().sort((a, b) => D.teams[b].faab - D.teams[a].faab);
  let h = `<thead><tr><th>Team</th><th class="n">FAAB</th><th class="n">Boldest bid<br>(% of budget)</th><th class="n">Biggest win</th><th class="n">Wk ${W0} proj</th><th>Needs (vs league median)</th><th>Bye-week dips</th></tr></thead><tbody>`;
  for (const t of order) {
    const gaps = SLOTS.map((s, i) => ({ s: s[0], d: slotVals[t][i] - med[i] })).filter(x => x.d < -2).sort((a, b) => a.d - b.d).slice(0, 3);
    const need = gaps.map(x => `<span class="pill ${x.d < -5 ? 'p-bad' : 'p-warn'}">${x.s} ${fmt(x.d, 0)}</span>`).join(' ') || '<span class="pill p-good">None big</span>';
    const pj = BASE.projs[t], avg = WEEKS.reduce((a, w) => a + pj[w], 0) / WEEKS.length;
    const dips = WEEKS.filter(w => pj[w] < avg - 12).map(w => `W${w} (${Math.round(pj[w])})`).join(', ') || '—';
    h += `<tr class="${t === ME ? 'me' : ''}"><td><b>${esc(tname(t))}</b>${t === ME ? ' (you)' : ''}</td><td class="n">$${D.teams[t].faab}</td><td class="n">${MAXPCT[t]}%</td><td class="n">${spentBig[t] ? '$' + spentBig[t] : '—'}</td><td class="n">${fmt(pj[W0], 0)}</td><td class="wrap">${need}</td><td class="wrap">${dips}</td></tr>`;
  }
  $('rv').innerHTML = h + '</tbody>';
}

function renderMarket() {
  const tiers = [['Stud (16+ pts/game)', 16, 99], ['Starter (11–16)', 11, 16], ['Flex (7–11)', 7, 11], ['Depth (<7)', -1, 7]];
  let h = '<thead><tr><th>Tier (season avg, 0.5 PPR)</th><th class="n">Claims</th><th class="n">Median win</th><th class="n">Top win</th><th class="n">Median share of budget</th><th class="n">Last 2 legs median</th></tr></thead><tbody>';
  const med = a => { if (!a.length) return 0; const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  for (const [lab, lo, hi] of tiers) {
    const hs = D.hist.filter(x => D.P[x.sid] && D.P[x.sid].p !== 'DEF' && D.P[x.sid].p !== 'K' && D.P[x.sid].a >= lo && D.P[x.sid].a < hi && x.bids.length > 1);
    const late = hs.filter(x => x.leg >= W0 - 2).map(x => x.bid);
    h += `<tr><td>${lab}</td><td class="n">${hs.length}</td><td class="n">$${med(hs.map(x => x.bid))}</td><td class="n">$${Math.max(0, ...hs.map(x => x.bid))}</td><td class="n">${med(hs.map(x => x.pct[0][2]))}%</td><td class="n">${late.length ? '$' + med(late) : '—'}</td></tr>`;
  }
  $('tiers').innerHTML = h + '</tbody>';
  const pf = $('posf').value;
  const hs = D.hist.filter(x => x.bids.length > 1 || x.bid > 0).filter(x => !pf || x.p === pf).sort((a, b) => b.leg - a.leg || b.bid - a.bid);
  let t = '<thead><tr><th class="n">Leg</th><th>Player</th><th>Winner</th><th class="n">Bid</th><th class="n">Share</th><th>Other bids</th></tr></thead><tbody>';
  for (const x of hs) {
    const others = x.pct.slice(1, 6).map(([r, b, pc]) => `${esc(tname(String(r)))} $${b}`).join(', ');
    t += `<tr class="${String(x.win) === ME ? 'me' : ''}"><td class="n">${x.leg}</td><td>${esc(x.n)} <span class="pos">${x.p}</span></td><td>${esc(tname(String(x.win)))}</td><td class="n">$${x.bid}</td><td class="n">${x.pct[0][2]}%</td><td class="wrap sub">${others || '—'}</td></tr>`;
  }
  $('hist').innerHTML = t + '</tbody>';
}

// The written guide (Google Doc "Guillotine bid strategy (v2)", rewritten each Tuesday from bids.json + news). Michael, Nov 10:
// everything made for him is one tap from Sports HQ.
const GUIDE_URL = 'https://docs.google.com/document/d/1Pa67152FLY8IQ70neRnnHZ4lFFT6XqWZwvWk1iF-tT8/edit';

// "Your moves" box: every claim and the best free adds, each with its own drop, the total vs what you can spend, the
// deadline, how to place them, and the written guide. Same rows and calls as the table below.
function planHtml() {
  const name = s => s && D.P[s] ? esc(D.P[s].n) : 'your weakest player';
  const claims = BIDROWS.filter(r => !r.added && r.freed && isBid(r)).sort((a, b) => b.ev - a.ev);
  const claimBy = Object.fromEntries(claims.map(r => [r.drop, r]));
  // the best free add at each position, two at most (two backup QBs is never the plan)
  const seen = new Set();
  const free = BIDROWS.filter(r => !r.added && !r.freed && r.call === 'Add free' && r.dWin > 0).sort((a, b) => b.dWin - a.dWin)
    .filter(r => !seen.has(D.P[r.s].p) && (seen.add(D.P[r.s].p), true)).slice(0, 2)
    // a second free add whose drop the first already uses can't happen too (Nov 11: Jacobs and Cousins both dropped Marks)
    .filter((r, i, a) => i === 0 || r.drop !== a[0].drop);
  const li = [];
  for (const r of claims) li.push(`<li><b>Claim ${esc(D.P[r.s].n)}</b> (${D.P[r.s].p} ${D.P[r.s].t}) for <b>$${r.bid}</b>, drop ${name(r.drop)}: ${pct(r.chance)} to win${r.call === 'Coin flip' ? ' (coin flip)' : ''}.</li>`);
  // a free add happens now, so its drop is gone before the claims run: say which claim then needs another drop
  for (const r of free) li.push(`<li><b>Add ${esc(D.P[r.s].n)}</b> (${D.P[r.s].p} ${D.P[r.s].t}) now for $0, drop ${name(r.drop)}`
    + (claimBy[r.drop] ? ` (your ${esc(D.P[claimBy[r.drop].s].n)} claim also drops him: give that claim another drop, or skip this add)` : '') + '.</li>');
  const total = claims.reduce((a, r) => a + r.bid, 0);
  const open = D.cut && D.cut.freed_status === 'on waivers';
  const when = open && D.waivers ? `before waivers run (${esc(D.waivers)})` : 'this week (nothing on waivers until the next cut)';
  return `<div class="plan"><p><b>Your moves ${when}:</b></p>`
    + (li.length ? `<ol>${li.join('')}</ol>` : '<p>Nothing worth claiming or adding this week.</p>')
    + (claims.length ? `<p class="sub">Claims total $${total} of the $${MONEY.spend} you can spend ($${S.reserve} kept in reserve). In Sleeper: Players, search the name, Claim, enter the bid, pick the drop. Each claim needs its own drop.</p>` : '')
    + `<p class="sub"><a href="${GUIDE_URL}" target="_blank" rel="noopener">Written guide: the full breakdown with news, rivals and why &rarr;</a></p></div>`;
}

function renderHeader(top) {
  const me = D.teams[ME], s = BASE.sim[ME];
  $('asof').textContent = `${D.league} · ${D.asof} · ${ALIVE.length} teams alive`;
  $('cutname').textContent = CUT ? tname(CUT) + ({ projected: ', projected, not yet confirmed', 'on waivers': `; on waivers until ${D.waivers}`,
    cleared: '; they already cleared waivers and are plain free agents now, so nothing is on waivers until the next cut' }[D.cut.freed_status] || '') : 'none yet';
  document.querySelectorAll('.wk').forEach(e => e.textContent = W0); document.querySelectorAll('.pw').forEach(e => e.textContent = D.cut ? D.cut.week : W0 - 1); document.querySelectorAll('.lw').forEach(e => e.textContent = LAST);
  $('kpis').innerHTML = [['FAAB left', '$' + me.faab], ['Wk ' + W0 + ' cut risk', pct(s.pCut[W0])], ['Exp. weeks left', fmt(s.expWeeks, 1)], ['Win odds', pct(s.pWin)]].map(([a, b]) => `<div class="kpi"><b>${b}</b><span>${a}</span></div>`).join('');
  const order = ALIVE.slice().sort((a, b) => BASE.sim[b].pCut[W0] - BASE.sim[a].pCut[W0]).slice(0, 3);
  let t = `<p><b>Week ${W0} cut watch:</b> ${order.map(x => `${esc(tname(x))}${x === ME ? ' (you)' : ''} ${pct(BASE.sim[x].pCut[W0])}`).join(' · ')}.</p>`;
  if (top) {
    const p = D.P[top.s];
    t += `<p><b>Best claim:</b> ${esc(p.n)} (${p.p} ${p.t}) adds ${fmt(top.dWin * 100, 1)} points of win odds after dropping ${top.drop && D.P[top.drop] ? esc(D.P[top.drop].n) : 'your weakest player'}. Bid $${top.bid} (wins about ${pct(top.chance)} of the time); he's worth $${top.value} to you and usually goes for $${top.price}–$${top.price80}.</p>`;
  }
  $('headline').innerHTML = planHtml() + t;
}

// ---------- wiring ----------
// [id, setter, label, starting value from the model's defaults]
const ctl = [['sd', v => S.sd = +v, v => v + ' pts' + (+v === SD_MEASURED ? ' (measured)' : ''), SD_MEASURED],
  ['aggr', v => S.aggr = v / 100, v => v + '%', 100], ['reserve', v => S.reserve = +v, v => '$' + v, S.reserve],
  ['dpp', v => S.dpp = +v, v => +v > 0 ? '$' + v : 'auto', 0]];
let timer = null;
function rerender() {
  computeBase();
  const top = renderBids(); renderLineup(); renderSurv(); renderForecast(); renderRivals(); renderMarket(); renderHeader(top);
}
for (const [id, set, lab, start] of ctl) {
  const el = $(id), o = $(id + 'O');
  el.value = start;
  const upd = () => { set(el.value); o.textContent = lab(el.value); };
  upd();
  el.addEventListener('input', () => { o.textContent = lab(el.value); clearTimeout(timer); timer = setTimeout(() => { upd(); rerender(); }, 180); });
}
$('posf').onchange = renderMarket;
function route() {
  const v = (location.hash || '#bids').slice(1);
  const views = ['bids', 'forecast', 'rivals', 'market', 'method'];
  const cur = views.includes(v) ? v : 'bids';
  views.forEach(x => { $('v-' + x).hidden = x !== cur; });
  document.querySelectorAll('.tabs a').forEach(a => a.setAttribute('aria-current', a.getAttribute('href') === '#' + cur ? 'page' : 'false'));
}
addEventListener('hashchange', route);
route(); rerender();
// Try a move (Q-054): the shared box (docs/lib/move.js) on this page's own model; it keeps working without it
if (window.SHQ && SHQ.move) SHQ.move.mount($('trymove'), 'Guillotine', { engine: SHQ.move.wrEngine({ playerList, tryMove }) });
else $('trypanel').hidden = true;
