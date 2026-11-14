// War Room page: rendering and controls. The model itself lives in model.js (shared with the GitHub build).
const $ = id => document.getElementById(id);
const esc = x => String(x).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// ---------- tap-to-explain (Nov 14: "I don't know what all I am looking at here") ----------
// Every column, tile and mark has a plain-English line: tap the small "?" (or a tile) to read it.
const EXPLAIN = {
  faab: 'FAAB left: your waiver budget in dollars. The highest bid wins a claim; on a tie the better waiver spot wins, and you are last.',
  cut: 'Cut risk this week: the chance your score is the lowest this week, so you get cut. Under 10% is comfortable; 25% or more is danger (then your $5 reserve may be spent on a claim that keeps you alive: your rule 13).',
  weeks: 'Expected weeks left: on average, how many more weekly cuts you survive, out of the weeks left, across thousands of simulated seasons.',
  win: 'Win odds: the share of simulated seasons where you are the last team standing. The league is winner-take-all, so this is what every move is judged on.',
  player: 'Player, position, NFL team and injury tag (Out, Questionable, IR). Tap a name for his card: points every week so far, projections for every week left, rest-of-season rank and why.',
  source: 'Freed = dropped by this week\'s cut team and on waivers: you need a bid. Free agent = add him now for $0.',
  bye: 'His bye week still to come (he scores 0 that week). "passed" = he already had it.',
  g1: 'Week gain: how many more points your starting lineup projects THIS week with him in and the drop out. Counts the small chance a starting RB misses the game. 0 = he would not start this week.',
  season: 'Season gain: the same lineup gain added up over every week left. Bigger = more help over the rest of the season.',
  dwin: '+Win odds: how many percentage points this move adds to your chance of winning the league (simulated). Under +0.3% is too small to tell from noise.',
  drop: 'Drop: who the model cuts to make room (rosters are full): the player whose loss costs the fewest points. Never a likely starter, and never a handcuff unless the add clearly wins (rule 14). "used 3×" = three moves pick the same drop; you can only drop him once, so only one of those moves can happen.',
  rivals: 'Likely rival bids: the rivals who would want him and the bid each would likely make, from their budgets and past bids. Ties go to them: you are last in waiver order.',
  value: 'Value: what he is worth to you in FAAB dollars (win odds added × dollars per point of win odds). Bidding above this is overpaying.',
  bidopts: 'Bid options: each line is a bid, its chance to win, and its average payoff = chance × (value − bid). ★ = the bid with the best payoff, which is often below the likely price: the aim is to spend wisely, not win every claim.',
  call: 'Call: Bid = 50%+ to win. Coin flip = 25–50%. Long shot = 10–25% (expect to lose). Backup = only runs if a claim above it with the same drop loses. Add free = $0 now. Skip = not worth it. Priced out = the likely price is above his value to you.',
  slot: 'Slot: where he plays in your best lineup this week. BN = bench. FLEX takes an RB, WR or TE.',
  proj: 'Projection: Sleeper\'s expected points for him this week, in this league\'s scoring. 0 = bye, Out or IR.',
  avg: 'Season average: his real points per game played this season.',
  hc: 'Handcuff: a backup RB who starts if your starter from the same NFL team gets hurt (Braelon Allen behind Breece Hall). He is kept unless an add clearly beats the injury insurance he gives (your rule 14).',
  cutwk: 'Cut this week: each team\'s chance of the lowest score this week.',
  cutby: 'Cut by: the chance a team is gone by that week (any of the cuts until then).',
  win2: 'Win: chance this team is the last one standing.',
  heat: 'W10, W11…: each team\'s projected starting-lineup score that week. Red = low (danger), green = high. Bye weeks show as dips.',
  boldest: 'Boldest bid: the biggest share of his budget this team has ever bid on one player.',
  biggest: 'Biggest win: the most this team has paid for one player this season.',
  needs: 'Needs: lineup slots where this team projects furthest below the league\'s middle team over the next 4 weeks. They are the teams most likely to bid on a player at that position.',
  dips: 'Bye-week dips: weeks this team projects 12+ points below its own average (byes or injuries): weeks it is more likely to be cut.',
};
const qx = k => `<button type="button" class="qx" data-x="${k}" aria-label="What is this?">?</button>`;
function showExplain(btn) {
  let pop = $('xpop');
  if (!pop) { pop = document.createElement('div'); pop.id = 'xpop'; pop.setAttribute('role', 'dialog'); document.body.appendChild(pop); }
  const k = btn.dataset.x, html = btn.dataset.html;
  if (pop.dataset.k === k && !pop.hidden) { pop.hidden = true; return; }
  pop.dataset.k = k; pop.innerHTML = (html !== undefined ? decodeURIComponent(html) : esc(EXPLAIN[k] || '')) + '<button type="button" class="xclose" aria-label="Close">×</button>';
  pop.hidden = false;
  const r = btn.getBoundingClientRect(), w = Math.min(340, innerWidth - 24);
  pop.style.width = w + 'px';
  pop.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + scrollX - 20)) + 'px';
  pop.style.top = (r.bottom + scrollY + 6) + 'px';
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-x]');
  if (b) { e.preventDefault(); e.stopPropagation(); showExplain(b); return; }
  const pop = $('xpop');
  if (pop && !pop.hidden && (e.target.closest('.xclose') || !e.target.closest('#xpop'))) pop.hidden = true;
}, true);
addEventListener('keydown', e => { if (e.key === 'Escape' && $('xpop')) $('xpop').hidden = true; });

// Outside experts' rest-of-season ranks are NOT on this public page: their source's terms forbid republishing, so they live
// in Michael's private Google Doc (his choice, Nov 14: "1: private Doc"; built by shq/ros.py). This page links to it.
const ROS_DOC = 'https://docs.google.com/document/d/1vRM45a7tMhqsBKvDW2mcLenuzaj6au_FFPIo4MHP9og/edit';

// A player's card: every week so far, every week left, and whether he's a handcuff.
function playerCard(s) {
  const p = D.P[s]; if (!p) return '';
  const past = (p.w || []).map((v, i) => `<span><i>W${i + 1}</i>${v === null || v === undefined ? '–' : fmt(v)}</span>`).join('');
  const next = WEEKS.map(w => `<span><i>W${w}</i>${fmt(proj(s, w))}</span>`).join('');
  const r = roster(ME), pair = handcuffPairs(r).find(x => x[0] === s || x[1] === s);
  let hc = '';
  if (pair && pair[1] === s) hc = `<p><b>Handcuff</b> for ${esc(pname(pair[0]))}: about ${fmt(asStarter(pair[0], s, W0))} pts a week if he sits; worth ${fmt(WEEKS.reduce((a, w) => a + insurance(r, s, w), 0))} lineup pts of insurance over the season. Kept unless an add clearly beats that (your rule 14).</p>`;
  else if (pair) hc = `<p>${esc(pname(pair[1]))} is his handcuff on your roster.</p>`;
  const owner = (() => { for (const t of Object.keys(D.teams)) if (D.teams[t].roster.includes(s)) return t === ME ? 'yours' : tname(t); return 'free agent'; })();
  return `<h3 style="margin:0">${esc(p.n)} <span class="pos">${p.p} ${p.t}</span></h3>`
    + `<p class="sub">${esc(owner)}${p.inj ? ' · ' + esc(p.inj) : ''}${p.st === 'RES' ? ' · IR' : ''}${p.bye.length ? ' · bye week ' + p.bye[0] : ''} · season avg ${fmt(p.a)} (${p.g} games) · last 3 avg ${fmt(p.r)}</p>`
    + hc + `<div class="wks"><b>Points so far</b>${past}</div><div class="wks"><b>Projected</b>${next}</div>`;
}
const pbtn = s => `<button type="button" class="pname" data-x="card-${s}" data-html="${encodeURIComponent(playerCard(s))}">${esc(D.P[s].n)}</button>`;

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
const CLAIMS = new Set(['Bid', 'Coin flip', 'Long shot', 'Backup', 'Add free']);
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
  // (a backup shares its drop on purpose: it only runs if the claim above it lost)
  for (const r of rows) if (!r.added && CLAIMS.has(r.call) && r.call !== 'Backup' && r.drop) dropUse[r.drop] = (dropUse[r.drop] || 0) + 1;
  const key = SORTS[VIEW.sort] ? SORTS[VIEW.sort][1] : SORTS.dwin[1];
  const out = rows.filter(r => (!VIEW.pos || D.P[r.s].p === VIEW.pos)
      && (VIEW.show === 'all' || (VIEW.show === 'freed' && r.freed) || (VIEW.show === 'fa' && !r.freed) || (VIEW.show === 'claims' && (r.added || CLAIMS.has(r.call)))))
    .sort((a, b) => (b.added - a.added) || (VIEW.sort === 'name' ? key(a).localeCompare(key(b)) : key(b) - key(a)) || (b.dWin - a.dWin));
  $('bidbar').innerHTML = bidBar();
  const pill = c => `<span class="pill ${{ 'Bid': 'p-good', 'Add free': 'p-good', 'Coin flip': 'p-warn', 'Long shot': 'p-warn', 'Backup': 'p-mute', 'Priced out': 'p-bad' }[c] || 'p-mute'}">${c}</span>`;
  // a handcuff drop shows rule 14's side-by-side (only when the add clearly wins: otherwise the model never picks him)
  const hcLine = r => { const h = r.drop && isHandcuff(roster(ME), r.drop) ? handcuffCheck(ME, r.s, r.drop) : null;
    return h ? `<div class="hcbox"><b>Handcuff drop (rule 14).</b> ${esc(h.handcuff)} ~${fmt(h.as_starter)} pts if ${esc(h.starter)} sits (${Math.round(h.miss_chance * 100)}%/wk); without him ${h.instead ? esc(h.instead.name) + ' starts' : 'nobody is left'}. Week by week, add vs insurance: ${h.weeks.map(x => `W${x.w} +${fmt(x.add)}/${fmt(x.ins)}`).join(', ')}. ${esc(h.verdict)}</div>` : ''; };
  const drop = r => r.drop && D.P[r.drop] ? esc(D.P[r.drop].n) + (isHandcuff(roster(ME), r.drop) ? ' <span class="pill p-warn">handcuff</span>' : '') + (dropUse[r.drop] > 1 && CLAIMS.has(r.call) && r.call !== 'Backup' ? ` <span class="pill p-warn" data-x="drop" role="button" tabindex="0" title="More than one move here drops this player">used ${dropUse[r.drop]}× ?</span>` : '') + hcLine(r) : '—';
  const opts = r => r.freed ? (r.options || []).map(o => `<div${o.bid === r.bid && isBid(r) ? ' class="best"' : ''}>$${o.bid} · ${pct(o.chance)} · ${o.payoff >= 0 ? '+' : '−'}$${Math.abs(Math.round(o.payoff))}${o.bid === r.bid && isBid(r) ? ' ★' : ''}${o.bid > money.spend ? ' (over budget)' : ''}</div>`).join('') || '—' : '$0';
  const rivals = r => rivalBids(r).slice(0, 3).map(x => `${esc(tname(x.t))} ~$${x.bid}`).join(', ') || (r.freed ? 'No rival needs him much' : '—');
  const tag = p => { const s = Object.keys(D.P).find(k => D.P[k] === p);
    return `${pbtn(s)} <span class="pos">${p.p} ${p.t}${p.inj ? ' · ' + p.inj : ''}${p.st === 'RES' ? ' · IR' : ''}</span>`; };
  const btn = r => `<button class="add" data-s="${r.s}" aria-pressed="${S.adds.has(r.s)}">${S.adds.has(r.s) ? '✓ Added' : '+ Add'}</button>`;
  const why = r => r.why && r.why !== 'free agent' ? '<div class="sub">' + esc(r.why) + '</div>' : '';
  const bye = p => p.bye.length ? 'Wk ' + p.bye[0] : 'passed';
  const th = (k, lab, cls = '', x = '') => `<th class="${cls}${k ? ' sortable' : ''}"${k ? ` data-sort="${k}" aria-sort="${VIEW.sort === k ? 'descending' : 'none'}"` : ''}>${lab}${VIEW.sort === k ? ' ▾' : ''}${x ? ' ' + qx(x) : ''}</th>`;
  let html = `<thead><tr>${th('name', 'Player', '', 'player')}<th>Source ${qx('source')}</th><th>Bye ${qx('bye')}</th><th class="n">Wk ${W0} gain ${qx('g1')}</th>${th('season', 'Season gain', 'n', 'season')}${th('dwin', '+Win odds', 'n', 'dwin')}<th>Drop ${qx('drop')}</th><th>Likely rival bids ${qx('rivals')}</th>${th('value', 'Value', 'n', 'value')}${th('bid', 'Bid options<br><span class="sub">bid · win chance · avg payoff</span>', '', 'bidopts')}<th>Call ${qx('call')}</th><th></th></tr></thead><tbody>`;
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
      + `<div class="facts"><span><b>${r.dWin >= 0 ? '+' : ''}${fmt(r.dWin * 100, 1)}%</b> win odds ${qx('dwin')}</span>${r.freed ? `<span><b>$${r.value}</b> value</span>` : ''}<span>+${fmt(r.g1)} wk ${W0} · +${fmt(r.gR, 0)} season</span></div>`
      + (r.freed && isBid(r) ? `<div class="bidline">Bid <b>$${r.bid}</b> (${pct(r.chance)} to win)</div>` : '')
      + `<div class="sub">Drop ${qx('drop')}: ${drop(r)}</div>`
      + (r.freed ? `<div class="opts">${opts(r)}</div><div class="sub">Rivals: ${rivals(r)}</div>` : '')
      + `${why(r)}<div class="foot"><span class="sub">Call ${qx('call')}</span>${btn(r)}</div></div>`;
  }
  $('cand').innerHTML = html + '</tbody>';
  $('cards').innerHTML = cards || '<p class="sub">No players match.</p>';
  $('bidcount').textContent = `${out.length} of ${rows.length} players`;
  document.querySelectorAll('#cand button.add, #cards button.add').forEach(b => b.onclick = () => { const s = b.dataset.s; S.adds.has(s) ? S.adds.delete(s) : S.adds.add(s); rerender(); });
  document.querySelectorAll('#bidbar .chip').forEach(b => b.onclick = () => { VIEW.pos = b.dataset.pos; saveView(); drawBids(); });
  $('bshow').onchange = e => { VIEW.show = e.target.value; saveView(); drawBids(); };
  $('bsort').onchange = e => { VIEW.sort = e.target.value; saveView(); drawBids(); };
  document.querySelectorAll('#cand th.sortable').forEach(t => t.onclick = e => { if (e.target.closest('.qx')) return; VIEW.sort = t.dataset.sort; saveView(); drawBids(); });
}

function renderLineup() {
  const L = lineup(roster(ME), W0);
  const on = new Set(L.st.map(x => x.s));
  const r = roster(ME), cuffs = handcuffPairs(r), hcOf = s => cuffs.find(x => x[1] === s);
  let h = `<thead><tr><th>Slot ${qx('slot')}</th><th>Player ${qx('player')}</th><th class="n">Wk ${W0} proj ${qx('proj')}</th><th class="n">Season avg ${qx('avg')}</th></tr></thead><tbody>`;
  for (const x of L.st) {
    const p = x.s ? D.P[x.s] : null;
    const flag = !p ? '<span class="pill p-bad">Empty</span>' : x.v < 4 ? ' <span class="pill p-bad">Weak</span>' : '';
    h += `<tr><td class="pos">${x.slot}</td><td>${p ? pbtn(x.s) + ' <span class="pos">' + p.p + ' ' + p.t + '</span>' : ''}${flag}</td><td class="n">${fmt(x.v)}</td><td class="n">${p ? fmt(p.a) : ''}</td></tr>`;
  }
  const bench = r.filter(s => !on.has(s) && D.P[s]);
  for (const s of bench) { const p = D.P[s]; const why = p.bye.includes(W0) ? 'bye' : p.inj === 'Out' ? 'out' : p.st === 'RES' ? 'IR' : '';
    h += `<tr><td class="pos">BN</td><td class="sub">${pbtn(s)} <span class="pos">${p.p} ${p.t}${why ? ' · ' + why : ''}</span>${hcOf(s) ? ` <span class="pill p-warn">handcuff</span> ${qx('hc')}` : ''}</td><td class="n">${fmt(proj(s, W0))}</td><td class="n">${fmt(p.a)}</td></tr>`; }
  $('mylineup').innerHTML = h + `<tr><td></td><td><b>Projected total</b></td><td class="n"><b>${fmt(L.tot)}</b></td><td></td></tr></tbody>`;
  const byes = r.filter(s => D.P[s] && D.P[s].bye.includes(W0)).map(s => D.P[s].n + ' (' + D.P[s].p + ')');
  const hcs = cuffs.map(([st, hh]) => `${D.P[hh].n} is ${D.P[st].n}'s handcuff: about ${fmt(asStarter(st, hh, W0))} pts a week if ${D.P[st].n} sits, worth ${fmt(WEEKS.reduce((a, w) => a + insurance(r, hh, w), 0))} lineup pts of insurance over the season, so the model keeps him unless an add clearly beats that (your rule 14).`);
  $('mynote').textContent = [byes.length ? `On bye in week ${W0}: ${byes.join(', ')}.` : '', ...hcs].filter(Boolean).join(' ');
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
  $('survleg').innerHTML = `<span><i class="sw" style="background:var(--accent)"></i>Chance you're still alive after each week (the line falls by your cut risk each week)</span><span>Expected weeks survived: <b>${fmt(s.expWeeks, 1)}</b> of ${WEEKS.length} ${qx('weeks')}</span><span>Win the league: <b>${pct(s.pWin)}</b> ${qx('win')}</span>`;
}

function renderForecast() {
  const sim = BASE.sim, P = BASE.projs;
  const order = ALIVE.slice().sort((a, b) => sim[a].expWeeks - sim[b].expWeeks);
  let lo = 1e9, hi = 0; for (const t of ALIVE) for (const w of WEEKS) { lo = Math.min(lo, P[t][w]); hi = Math.max(hi, P[t][w]); }
  let h = `<thead><tr><th>Team</th><th class="n">FAAB ${qx('faab')}</th><th>Cut wk ${W0} ${qx('cutwk')}</th><th>Cut by wk ${Math.min(LAST, W0 + 3)} ${qx('cutby')}</th><th class="n">Exp. weeks left ${qx('weeks')}</th><th class="n">Win ${qx('win2')}</th>${WEEKS.map((w, i) => `<th class="n">W${w}${i === 0 ? ' ' + qx('heat') : ''}</th>`).join('')}</tr></thead><tbody>`;
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
  let h = `<thead><tr><th>Team</th><th class="n">FAAB ${qx('faab')}</th><th class="n">Boldest bid<br>(% of budget) ${qx('boldest')}</th><th class="n">Biggest win ${qx('biggest')}</th><th class="n">Wk ${W0} proj ${qx('proj')}</th><th>Needs (vs league median) ${qx('needs')}</th><th>Bye-week dips ${qx('dips')}</th></tr></thead><tbody>`;
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

// The Tuesday list (bids.json, the same numbers the written guide and the 7:11am push use). The "Your moves" box shows
// it while the controls are at their defaults, so the page, the guide and the push give one answer (Nov 12 revamp);
// with changed controls it shows this page's own numbers and says so.
let TUESDAY = null, LASTTOP = null;
fetch('bids.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(j => { if (j && j.claim_list) { TUESDAY = j; renderHeader(LASTTOP); } }).catch(() => {});
const atDefaults = () => S.sd === SD_MEASURED && S.aggr === 1 && S.reserve === RULES.reserve && !(S.dpp > 0) && !S.adds.size;

// "Your moves" box: the claims in the order to enter them in Sleeper (highest bid first; backups right after the claim
// they back up), each with its drop, win chance and a one-line why; the best free adds; the most you can spend; the
// deadline; the written guide.
function planHtml() {
  const name = s => s && D.P[s] ? esc(D.P[s].n) : 'your weakest player';
  const live = claimList(BIDROWS);
  const claims = live.filter(r => r.call !== 'Backup');
  const claimBy = Object.fromEntries(claims.map(r => [r.drop, r]));
  const fromJson = TUESDAY && atDefaults();
  const list = fromJson ? TUESDAY.claim_list.map(c => ({ ...c, name: esc(c.name), drop: c.drop ? esc(c.drop) : 'your weakest player' }))
    : live.map(r => ({ name: esc(D.P[r.s].n), pos: D.P[r.s].p, team: D.P[r.s].t, bid: r.bid, drop: name(r.drop), win_chance: r.chance,
        kind: r.call === 'Backup' ? 'backup' : 'claim', fires_if: r.firesIf ? `you lose ${r.firesIf.map(pname).join(' and ')}` : null, why: whyLine(r), call: r.call }));
  // the best free add at each position, two at most (two backup QBs is never the plan)
  const seen = new Set();
  const free = BIDROWS.filter(r => !r.added && !r.freed && r.call === 'Add free' && r.dWin > 0).sort((a, b) => b.dWin - a.dWin)
    .filter(r => !seen.has(D.P[r.s].p) && (seen.add(D.P[r.s].p), true)).slice(0, 2)
    // a second free add whose drop the first already uses can't happen too (Nov 11: Jacobs and Cousins both dropped Marks)
    .filter((r, i, a) => i === 0 || r.drop !== a[0].drop);
  const li = [];
  const label = c => c.win_chance >= .5 ? '' : c.win_chance >= .25 ? ' (coin flip)' : ' (long shot: expect to lose)';
  for (const c of list) li.push(`<li><b>${c.kind === 'backup' ? 'Backup: claim' : 'Claim'} ${c.name}</b> (${c.pos} ${c.team}) for <b>$${c.bid}</b>, drop ${c.drop}: `
    + `${pct(c.win_chance || 0)} to win${c.kind === 'backup' ? `, only runs if ${esc(c.fires_if)}` : label(c)}.`
    + (c.why ? `<div class="sub">${esc(c.why)}</div>` : '') + '</li>');
  // a free add happens now, so its drop is gone before the claims run: say which claim then needs another drop
  for (const r of free) li.push(`<li><b>Add ${esc(D.P[r.s].n)}</b> (${D.P[r.s].p} ${D.P[r.s].t}) now for $0, drop ${name(r.drop)}`
    + (claimBy[r.drop] ? ` (your ${esc(D.P[claimBy[r.drop].s].n)} claim also drops him: give that claim another drop, or skip this add)` : '') + '.</li>');
  const worst = fromJson ? TUESDAY.worst_case_spend : (() => { const c = {}; for (const r of live) c[r.drop] = Math.max(c[r.drop] || 0, r.bid); return Object.values(c).reduce((a, b) => a + b, 0); })();
  const open = D.cut && D.cut.freed_status === 'on waivers';
  const when = open && D.waivers ? `before waivers run (${esc(D.waivers)})` : 'this week (nothing on waivers until the next cut)';
  return `<div class="plan"><p><b>Your moves ${when}:</b></p>`
    + (li.length ? `<ol>${li.join('')}</ol>` : '<p>Nothing worth claiming or adding this week.</p>')
    + (list.length ? `<p class="sub">The most these claims can cost: $${worst} of the $${MONEY.spend} you can spend ($${S.reserve} always kept back). `
      + `In Sleeper's classic site, enter them in this order: Players, search the name, Claim, enter the bid, pick the drop. `
      + `Claims that share a drop are backups: once one of them wins, the rest fail, so you never pay twice.</p>` : '')
    + (list.length ? `<p class="sub">${fromJson ? `Same list as your written guide and Tuesday push (built ${esc(TUESDAY.data_as_of)}).` : 'From this page\'s settings and quicker simulation, not the Tuesday list: reset the controls to see that.'}</p>` : '')
    + `<p class="sub"><a href="${GUIDE_URL}" target="_blank" rel="noopener">Written guide: the full breakdown with news, rivals and why &rarr;</a></p></div>`;
}

function renderHeader(top) {
  const me = D.teams[ME], s = BASE.sim[ME];
  $('asof').textContent = `${D.league} · ${D.asof} · ${ALIVE.length} teams alive`;
  $('cutname').textContent = CUT ? tname(CUT) + ({ projected: ', projected, not yet confirmed', 'on waivers': `; on waivers until ${D.waivers}`,
    cleared: '; they already cleared waivers and are plain free agents now, so nothing is on waivers until the next cut' }[D.cut.freed_status] || '') : 'none yet';
  document.querySelectorAll('.wk').forEach(e => e.textContent = W0); document.querySelectorAll('.pw').forEach(e => e.textContent = D.cut ? D.cut.week : W0 - 1); document.querySelectorAll('.lw').forEach(e => e.textContent = LAST);
  $('kpis').innerHTML = [['FAAB left', '$' + me.faab, 'faab'], ['Wk ' + W0 + ' cut risk', pct(s.pCut[W0]), 'cut'], ['Exp. weeks left', fmt(s.expWeeks, 1), 'weeks'], ['Win odds', pct(s.pWin), 'win']]
    .map(([a, b, k]) => `<button type="button" class="kpi" data-x="${k}" aria-label="${a}: ${b}. What is this?"><b>${b}</b><span>${a} ?</span></button>`).join('');
  const order = ALIVE.slice().sort((a, b) => BASE.sim[b].pCut[W0] - BASE.sim[a].pCut[W0]).slice(0, 3);
  let t = `<p><b>Week ${W0} cut watch:</b> ${order.map(x => `${esc(tname(x))}${x === ME ? ' (you)' : ''} ${pct(BASE.sim[x].pCut[W0])}`).join(' · ')}.</p>`;
  $('headline').innerHTML = planHtml() + t;
}

// ---------- rest of season (Nov 14) ----------
// His roster and the realistic adds with Sports HQ's own numbers (Sleeper's projection per game for the weeks left) and the
// handcuff check. Outside experts' ranks: a link to his private Doc only (see ROS_DOC).
function renderRos() {
  if (!$('rosT') || !BASE) return;
  const avgLeft = s => WEEKS.reduce((a, w) => a + proj(s, w), 0) / Math.max(1, WEEKS.filter(w => !(D.P[s].bye || []).includes(w)).length);
  const mine = roster(ME).filter(s => D.P[s]), adds = BIDROWS.filter(r => !r.added && r.dWin > 0 && !mine.includes(r.s)).slice(0, 10).map(r => r.s);
  const cuffs = handcuffPairs(roster(ME));
  const row = (s, who) => { const p = D.P[s], hc = cuffs.find(x => x[1] === s);
    return `<tr class="${who === 'mine' ? 'me' : ''}"><td>${pbtn(s)} <span class="pos">${p.p} ${p.t}${p.inj ? ' · ' + esc(p.inj) : ''}</span></td>`
      + `<td class="n">${fmt(avgLeft(s))}</td><td class="n">${fmt(p.a)}</td>`
      + `<td class="wrap">${hc ? `Handcuff for ${esc(pname(hc[0]))}: ~${fmt(asStarter(hc[0], s, W0))} pts if he sits.` : ''}</td></tr>`; };
  const posOrder = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'];
  const sortS = a => a.slice().sort((x, y) => posOrder.indexOf(D.P[x].p) - posOrder.indexOf(D.P[y].p) || avgLeft(y) - avgLeft(x));
  const head = `<thead><tr><th>Player ${qx('player')}</th><th class="n">Proj/gm left ${qx('proj')}</th><th class="n">Season avg ${qx('avg')}</th><th>Note</th></tr></thead>`;
  $('rosT').innerHTML = head + '<tbody>' + sortS(mine).map(s => row(s, 'mine')).join('') + '</tbody>';
  $('rosA').innerHTML = head + '<tbody>' + adds.map(s => row(s, 'add')).join('') + '</tbody>';
  $('rossrc').innerHTML = `Proj/gm left: Sleeper's projection per game for the weeks left (byes skipped). Experts' rest-of-season ranks (your rule 15) are in your private Doc, not on this public page: <a href="${ROS_DOC}" target="_blank" rel="noopener">Rest-of-season ranks (private)</a>.`;
}

// ---------- wiring ----------
// [id, setter, label, starting value from the model's defaults]
const ctl = [['sd', v => S.sd = +v, v => v + ' pts' + (+v === SD_MEASURED ? ' (measured)' : ''), SD_MEASURED],
  ['aggr', v => S.aggr = v / 100, v => v + '%', 100], ['reserve', v => S.reserve = +v, v => '$' + v, S.reserve],
  ['dpp', v => S.dpp = +v, v => +v > 0 ? '$' + v : 'auto', 0]];
let timer = null;
function rerender() {
  computeBase();
  const top = LASTTOP = renderBids(); renderLineup(); renderSurv(); renderForecast(); renderRivals(); renderMarket(); renderRos(); renderHeader(top);
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
  const views = ['bids', 'ros', 'forecast', 'rivals', 'market', 'method'];
  const cur = views.includes(v) ? v : 'bids';
  views.forEach(x => { $('v-' + x).hidden = x !== cur; });
  document.querySelectorAll('.tabs a').forEach(a => a.setAttribute('aria-current', a.getAttribute('href') === '#' + cur ? 'page' : 'false'));
}
addEventListener('hashchange', route);
route(); rerender();
// Try a move (Q-054): the shared box (docs/lib/move.js) on this page's own model; it keeps working without it
if (window.SHQ && SHQ.move) SHQ.move.mount($('trymove'), 'Guillotine', { engine: SHQ.move.wrEngine({ playerList, tryMove }) });
else $('trypanel').hidden = true;
