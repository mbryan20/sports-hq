// Moves Michael skipped on HQ's fantasy cards (docs/data/decisions.json, written by HQ's Go runner; Nov 14).
// Same MATCHING RULE as shq/decisions.py (tests/test_decisions.py runs both on the same lines): league name without case
// or spaces, and the move reduced to its action and players ("start|a|b", "add|a|b"), so numbers, slots and times never
// matter. SHQSKIP.load(url) reads the file once; SHQSKIP.match(league, text) gives the entry or null; SHQSKIP.tag(entry)
// gives "You skipped this (Not worth it, Nov 14)".
(function () {
  const REASONS = { bad: 'Bad advice', handled: 'Already handled', notworth: 'Not worth it', notnow: 'Not now', other: 'Skipped' };
  const nm = s => String(s || '').trim().toLowerCase().replace(/\.+$/, '').replace(/\s+(jr|sr|ii|iii|iv|v)\.?$/, '').replace(/[^a-z]/g, '');
  // the apps' own league names -> Sports HQ's; 3-Ball is one name for two sports (same table as shq/decisions.py)
  const ALIAS = { sundaysbest: 'domoarigato', stempakfamilyandfriends2026: 'stempak', stempakfamilyandfriends: 'stempak', weplayinbasketball: 'ballislife' };
  const SPORT = { football: 'fb', nfl: 'fb', basketball: 'bb', nba: 'bb' };
  const lg = (s, sport) => {
    const k = String(s || '').toLowerCase().replace(/[^a-z0-9]/g, ''), sp = SPORT[String(sport || '').toLowerCase()];
    if (k.includes('guill')) return 'guillotine';
    if (k.startsWith('3balldynasty') && sp) return '3ball' + sp;
    return ALIAS[k] || k;
  };
  function key(text) {
    const raw = String(text || '').toLowerCase();
    const arrow = raw.indexOf(' → ');
    if (arrow >= 0) {
      const head = raw.slice(0, arrow), tail = raw.slice(arrow + 3);
      const m = tail.match(/^\s*(?:start|play) (.+?)(?: \(| at |,|$)/), who = head.match(/^\s*(.+?) \(/);
      if (m && who) return `start|${nm(m[1])}|${nm(who[1])}`;
    }
    let t = raw.replace(/\([^)]*\)|\[[^\]]*\]/g, ' ').replace(/^\s*first move .+?; then /, '');
    t = t.split(/ → |: | — | -- |, \+|\bbefore\b|; /)[0].replace(/\s+/g, ' ').replace(/^[ .,]+|[ .,]+$/g, '');
    let m = t.match(/^(?:move|activate) (.+?)(?: (?:out of|from|off) (?:the )?ir\b.*|,.*| and .*)?$/);
    if (m && (t.includes(' ir') || t.startsWith('activate '))) return `ir|${nm(m[1])}`;
    m = t.match(/^(?:start|play) (.+?) over (.+?)(?: at .*|,.*| and .*| then .*)?$/);
    if (m) return `start|${nm(m[1])}|${nm(m[2])}`;
    m = t.match(/^add (.+?)(?:,| and)? (?:drop|for) (.+?)(?:,| and | then | to |$)/) || t.match(/^(?:pick up|claim) (.+?)(?:,| and)? drop (.+?)(?:,| and | then | to |$)/);
    if (m) return `add|${nm(m[1])}|${nm(m[2])}`;
    m = t.match(/^drop (.+?)(?:,| and)? (?:add|for|pick up|claim) (.+?)(?:,| and | then | to |$)/);
    if (m) return `add|${nm(m[2])}|${nm(m[1])}`;
    return t.replace(/[^a-z]+/g, ' ').trim();
  }
  let active = new Map();
  function set(list, now = Date.now()) {
    active = new Map();
    for (const e of Array.isArray(list) ? list : (list && list.items) || []) {
      if (!e || !e.league || !e.move) continue;
      if (e.until && Date.parse(e.until) <= now) continue;
      active.set(lg(e.league, e.sport) + '|' + key(e.move), e);
    }
    return active.size;
  }
  function load(url) {
    return fetch(url + (url.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' })
      .then(r => r.ok ? r.json() : []).then(set).catch(() => 0);
  }
  const match = (league, text) => active.get(lg(league) + '|' + key(text)) || null;
  function tag(e) {
    const d = e && e.at ? new Date(e.at) : null;
    const day = d && !isNaN(d) ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : '';
    return `You skipped this (${REASONS[e && e.reason] || 'Skipped'}${day ? ', ' + day : ''})`;
  }
  window.SHQSKIP = { key, set, load, match, tag };
})();
