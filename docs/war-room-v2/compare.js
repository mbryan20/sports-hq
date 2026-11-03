// War Room v2 side by side: your pending Sleeper claims next to the model's numbers.
// Loaded by a bookmark while you're on sleeper.com, signed in (install page: war-room-v2/compare.html).
// Read-only: it reads your pending claims through Sleeper's own API with the sign-in already in this browser,
// and the public bids.json. It never changes a claim, and nothing is saved or sent anywhere.
(async () => {
  const LID = '1385516543386845184', UID = '605584791680663552';
  const BIDS = 'https://mbryan20.github.io/sports-hq/war-room-v2/bids.json?t=' + Date.now();
  const esc = x => String(x ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pct = x => x == null ? '?' : Math.round(x * 100) + '%';
  document.getElementById('shq-compare')?.remove();
  const box = document.createElement('div');
  box.id = 'shq-compare';
  box.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:#11161c;color:#e6ebf0;overflow:auto;-webkit-overflow-scrolling:touch;'
    + 'font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:12px 12px 40px;box-sizing:border-box';
  const css = `<style>#shq-compare *{box-sizing:border-box}#shq-compare .c{border:1px solid #2b3643;border-radius:8px;padding:9px 11px;margin:0 0 9px;background:#18202a}
    #shq-compare .h{display:flex;justify-content:space-between;gap:8px;align-items:baseline}#shq-compare .m{color:#97a5b4;font-size:12.5px}
    #shq-compare .w{color:#e7b04f}#shq-compare .b{color:#f07b72}#shq-compare .g{color:#5cc48f}#shq-compare b{font-weight:650}
    #shq-compare .x{position:sticky;top:0;float:right;font:600 14px sans-serif;background:#e6ebf0;color:#11161c;border:0;border-radius:999px;padding:6px 12px;cursor:pointer}
    #shq-compare h2{font-size:17px;margin:2px 0 6px}#shq-compare h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#97a5b4;margin:14px 0 6px}</style>`;
  const close = '<button class="x" onclick="this.parentNode.remove()">Close</button>';
  const show = html => { box.innerHTML = css + close + html; };
  document.body.appendChild(box);
  show('<h2>War Room vs your Sleeper claims</h2><p class="m">Loading…</p>');
  try {
    if (!/(^|\.)sleeper\.(com|app)$/.test(location.hostname)) throw 'Open sleeper.com first (signed in), then tap the bookmark again.';
    const token = localStorage.getItem('token');
    if (!token) throw 'Sleeper isn\'t signed in in this browser. Sign in at sleeper.com, then tap the bookmark again.';
    const [rosters, M] = await Promise.all([fetch(`https://api.sleeper.app/v1/league/${LID}/rosters`).then(r => r.json()), fetch(BIDS).then(r => r.json())]);
    const mine = rosters.find(r => r.owner_id === UID);
    const q = `query league_transactions_filtered { league_transactions_filtered(league_id: "${LID}", roster_id_filters: [${mine.roster_id}], type_filters: [], leg_filters: [], status_filters: ["pending"]) { adds drops created settings type } }`;
    const g = await fetch('https://sleeper.com/graphql', { method: 'POST', headers: { 'content-type': 'application/json', authorization: token },
      body: JSON.stringify({ operationName: 'league_transactions_filtered', variables: {}, query: q }) }).then(r => r.json());
    if (g.errors || !g.data) throw 'Sleeper didn\'t return your claims (' + esc(JSON.stringify(g.errors || g).slice(0, 160)) + '). Are you signed in?';
    const claims = g.data.league_transactions_filtered.filter(t => t.type === 'waiver').sort((a, b) => a.created - b.created)
      .map((t, i) => ({ n: i + 1, add: Object.keys(t.adds || {})[0], drop: Object.keys(t.drops || {})[0] || null, bid: (t.settings || {}).waiver_bid || 0 }));
    const model = Object.fromEntries(M.bids.map(b => [b.sleeper_id, b]));
    const names = M.names || {};
    const nm = id => { if (!id) return '—'; const x = names[id]; return x ? `${esc(x[0])} <span class="m">${esc(x[1])} ${esc(x[2] || '')}</span>` : `player ${esc(id)}`; };
    const starters = new Set((M.my_roster || []).filter(p => p.slot !== 'BN').map(p => p.sleeper_id));
    const faab = M.my_faab, total = claims.reduce((a, c) => a + c.bid, 0);
    const byDrop = {};
    claims.forEach(c => { if (c.drop) (byDrop[c.drop] = byDrop[c.drop] || []).push(c.n); });
    const cards = claims.map(c => {
      const m = model[c.add], notes = [];
      const shared = c.drop && byDrop[c.drop].length > 1 ? byDrop[c.drop].filter(n => n !== c.n) : [];
      if (shared.length) notes.push(`<span class="w">Same drop as claim ${shared.join(', ')}: only the first of these to win can go through.</span>`);
      if (starters.has(c.drop)) notes.push('<span class="b">Drops one of your starters this week.</span>');
      let modelLine = '<span class="m">Not on the model\'s list (it adds too little, or the model doesn\'t rate him).</span>', atYours = '';
      if (m) {
        const curve = m.win_curve || [], ch = curve.length ? curve[Math.min(c.bid, curve.length - 1)] : null;
        if (m.source.startsWith('freed')) {
          modelLine = `Model: <b>${esc(m.call)}</b>${m.bid ? ` at <b>$${m.bid}</b> (${pct(m.win_chance)})` : ''} · likely price $${m.est_price}–$${m.price_80} · worth $${m.value} to you`;
          if (ch != null) atYours = `Your $${c.bid}: about <b>${pct(ch)}</b> to win, average payoff ${m.value - c.bid >= 0 ? '+' : '−'}$${Math.abs(Math.round(ch * (m.value - c.bid)))}`;
          if (c.bid > m.value) notes.push(`<span class="w">Bid is above his value to you ($${m.value}).</span>`);
          if (m.call === 'Skip' || m.call === 'Priced out') notes.push(`<span class="w">Model: ${esc(m.call)}${m.why ? ' (' + esc(m.why) + ')' : ''}.</span>`);
        } else {
          modelLine = `Model: <b>${esc(m.call)}</b> · free agent, $0 once waivers clear`;
          if (c.bid > 0) notes.push(`<span class="w">He's a free agent: after Wednesday's run he can be added for $0.</span>`);
        }
        if (m.drop_id && m.drop_id !== c.drop && m.drop) notes.push(`<span class="m">Model's drop: ${esc(m.drop)}.</span>`);
      }
      return `<div class="c"><div class="h"><div>${c.n}. ${nm(c.add)}</div><div><b>$${c.bid}</b></div></div>
        <div class="m">Drop: ${nm(c.drop)}</div><div>${modelLine}</div>${atYours ? `<div>${atYours}</div>` : ''}${notes.map(n => `<div>${n}</div>`).join('')}</div>`;
    }).join('');
    const claimed = new Set(claims.map(c => c.add));
    const missing = M.bids.filter(b => b.bid > 0 && !claimed.has(b.sleeper_id));
    const waivers = M.waivers_open ? `Waivers run ${esc(M.waivers)}.` : '<span class="w">No players are on waivers right now; claims wait for the next cut.</span>';
    show(`<h2>War Room vs your Sleeper claims</h2>
      <div class="m">Model data: ${esc(M.data_as_of)}. ${waivers}</div>
      <div style="margin:8px 0"><b>${claims.length}</b> pending claims · bids total <b>$${total}</b> · FAAB <b>$${faab}</b>${total > faab ? ' <span class="m">(fine if they can\'t all win; claims you can\'t afford when they process just fail)</span>' : ''}
      · model's bids total $${M.budget.recommended_bids_total} of $${M.budget.spendable} spendable</div>
      <div class="m">Listed in the order you entered them. If you reordered claims in Sleeper, its own list order is what counts.</div>
      <h3>Your claims</h3>${cards || '<p class="m">No pending claims.</p>'}
      ${missing.length ? `<h3>Model suggests, not in your claims</h3>` + missing.map(b => `<div class="c">${nm(b.sleeper_id)} · model bid <b>$${b.bid}</b> (${pct(b.win_chance)}) · drop ${esc(b.drop || '—')}</div>`).join('') : ''}
      <p class="m">Read-only: nothing here changes your claims or is saved anywhere.</p>`);
  } catch (e) {
    show(`<h2>War Room vs your Sleeper claims</h2><p class="b">${typeof e === 'string' ? e : esc(e && e.message || e)}</p>`);
  }
})();
