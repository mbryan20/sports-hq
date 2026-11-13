"use strict";
// Try a move + Ask Claude (Q-054). Michael, Nov 11: "a place where I can ask questions about particular moves ... for each
// team". On every league page (core.js mounts it lazily), the Try-a-move page (move/) and War Room v2:
// - Try a move: pick a player to add and one to drop (two moves at once at most) and get a verdict at once, no AI:
//   Guillotine = the War Room's own model (warroom/model.js tryMove: win odds, weeks alive, cut risk, claim price);
//   other football = best-lineup points this week and the next 4 weeks, rest-of-season per game, experts, byes, value;
//   basketball = the Players page's trade check (value per game above waiver level, fit to weak categories, dynasty).
// - Ask Claude: opens a prefilled GitHub issue (label "ask"; works where claude.ai is blocked); .github/workflows/ask.yml
//   answers it and writes docs/data/asks.json, which shows here under the league.
// The pure parts (nflEval, nbaEval, lineupTotal, fromWR) take plain data so tests/test_move_js.py runs them under Node.
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const SHQ = root.SHQ = root.SHQ || {};
  const M = SHQ.move = SHQ.move || {};
  const REPO = "mbryan20/sports-hq";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const sg = (x, d = 1) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d);
  const pct = x => (x > 0 && x < 0.005 ? "<1" : Math.round(x * 100)) + "%";
  const sum = (xs, f) => xs.reduce((a, x) => a + f(x), 0);
  M.WORD = { worth: "Worth it", not: "Not worth it", coin: "Coin flip", unavailable: "Not available" };

  // ---------- football: best lineup from the league's own slots ----------
  const ELIG = { QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"], K: ["K"], DEF: ["DEF"], "D/ST": ["DEF"], DST: ["DEF"],
    FLEX: ["RB", "WR", "TE"], "RB/WR/TE": ["RB", "WR", "TE"], "W/R/T": ["RB", "WR", "TE"], "WR/TE": ["WR", "TE"], "RB/WR": ["RB", "WR"],
    SUPER_FLEX: ["QB", "RB", "WR", "TE"], OP: ["QB", "RB", "WR", "TE"], "Q/W/R/T": ["QB", "RB", "WR", "TE"] };
  M.ELIG = ELIG;
  // most restrictive slots first, each takes the best player left who fits
  M.lineupTotal = function (players, slots, val) {
    const order = slots.map(s => ELIG[s]).filter(Boolean).sort((a, b) => a.length - b.length);
    const pool = players.map(p => ({ p, v: val(p) || 0 })).sort((a, b) => b.v - a.v), used = new Set();
    let tot = 0;
    for (const ok of order) {
      const c = pool.find(x => !used.has(x) && ok.includes(x.p.pos));
      if (c) { used.add(c); tot += c.v; }
    }
    return tot;
  };
  // projection i weeks out: 0 = this week (the league's own source), then Sleeper's (null = bye). K/DEF have no line
  // past this week, so they count this week only (0 for everyone later, so a K or DEF swap is a this-week call)
  const wkVal = i => p => i === 0 ? (p.proj || 0) : p.next && p.next.length > i ? (p.next[i] ?? 0) : 0;
  const byeOf = (p, week) => { if (p.opp === "BYE") return week; const i = (p.next || []).findIndex((x, j) => j > 0 && x === null); return i > 0 ? week + i : null; };
  const BADINJ = /^(O|OUT|IR|PUP|SUSP|NA|D)$/i;

  // L = players_nfl.json league ({week, players, partial, dynasty}); slots = lineups.json starter slots
  M.nflEval = function (L, slots, adds, drops) {
    const by = Object.fromEntries(L.players.map(p => [p.id, p]));
    const mine = L.players.filter(p => p.own === "me");
    const A = adds.map(i => by[i]).filter(Boolean);
    if (!A.length) return null;
    const have = A.filter(a => a.own === "me");
    if (have.length) return { verdict: "unavailable", head: "already on your roster", reasons: have.map(a => `${esc(a.name)} is already yours: pick a player you don't have.`), html: true, adds: A, drops: [] };
    const weeks = [0, 1, 2, 3];
    const tot = (ps, i) => M.lineupTotal(ps, slots, wkVal(i));
    const base = weeks.map(i => tot(mine, i));
    // a missing drop: the player whose loss (with the add in) costs the fewest points over the 4 weeks
    const D = [], auto = [];
    A.forEach((a, k) => {
      let d = by[drops[k]] && by[drops[k]].own === "me" && !D.includes(by[drops[k]]) ? by[drops[k]] : null;
      if (!d) {
        let best = null, bv = -1e9;
        for (const c of mine) {
          if (D.includes(c) || A.includes(c)) continue;
          // a K or DEF only counts this week here, so never offer one up for anyone but another K or DEF
          if ((c.pos === "K" || c.pos === "DEF") && a.pos !== c.pos) continue;
          const ps = mine.filter(x => x !== c && !D.includes(x)).concat(A);
          const v = sum(weeks, i => tot(ps, i)) - 0.01 * (c.ros || c.proj || 0);
          if (v > bv) { bv = v; best = c; }
        }
        d = best; if (d) auto.push(d);
      }
      if (d) D.push(d);
    });
    const after = mine.filter(p => !D.includes(p)).concat(A.filter(a => a.own !== "me"));
    const d = weeks.map(i => Math.round((tot(after, i) - base[i]) * 10) / 10);
    const w1 = d[0], w4 = sum(d, x => x);
    const dRos = sum(A, p => p.ros || 0) - sum(D, p => p.ros || 0);
    const dFc = sum(A, p => p.fc || 0) - sum(D, p => p.fc || 0);
    const owned = A.filter(a => a.own && a.own !== "me");
    let verdict = w4 >= 3 ? "worth" : w4 <= -3 ? "not" : dRos >= 2 ? "worth" : dRos <= -2 ? "not" : "coin";
    const R = [];
    if (L.dynasty && verdict === "worth" && dFc <= -1000) { verdict = "coin"; R.push(`Dynasty: you'd give up ${Math.round(-dFc).toLocaleString("en-US")} of FantasyCalc value for the points.`); }
    if (L.dynasty && verdict === "coin" && dFc >= 1000) { verdict = "worth"; R.push(`Dynasty: +${Math.round(dFc).toLocaleString("en-US")} FantasyCalc value, more than the points.`); }
    R.unshift(`Lineup: week ${L.week} ${sg(w1)} pts, next 4 weeks ${sg(w4)} pts (${d.map((x, i) => `wk ${L.week + i} ${sg(x)}`).join(", ")}).`);
    if (Math.abs(w4) < 3) R.splice(1, 0, `Your lineup barely changes, so it comes down to depth: ${sg(dRos)} pts per game rest of season.`);
    const line = p => {
      const bits = [`${p.ros != null ? p.ros.toFixed(1) + "/gm" : "no rest-of-season line"}${p.ros_rk ? ` (${p.pos}${p.ros_rk})` : ""}`,
        `this week ${(p.proj || 0).toFixed(1)}${p.opp ? " " + p.opp : ""}`];
      if (p.exp_wk || p.exp_lately) bits.push(`ESPN experts ${p.exp_wk ? p.pos + p.exp_wk + " this week" : "not ranked to play this week"}${p.exp_lately ? `, ${p.pos}${p.exp_lately} lately` : ""}`);
      const b = byeOf(p, L.week); if (b) bits.push(`bye week ${b}`);
      if (p.inj) bits.push(BADINJ.test(p.inj) ? `<b>${esc(p.inj)}</b>` : esc(p.inj));
      if (p.fc) bits.push(`value ${Math.round(p.fc).toLocaleString("en-US")}`);
      return bits.join(" · ");
    };
    for (const a of A) R.push(`<b>Add ${esc(a.name)}</b> (${a.pos} ${esc(a.team)}): ${line(a)}.`);
    for (const x of D) R.push(`<b>Drop ${esc(x.name)}</b> (${x.pos} ${esc(x.team)}): ${line(x)}${auto.includes(x) ? ". No drop picked, so this is the one that costs you least" : ""}.`);
    for (const a of owned) R.push(`${esc(a.name)} is on ${esc(a.own)}'s roster: this is a trade, not a waiver add.`);
    if (A.concat(D).some(p => p.pos === "K" || p.pos === "DEF")) R.push("Kickers and defenses have projections for this week only, so they count this week only.");
    for (const a of A) if (a.inj && BADINJ.test(a.inj)) R.push(`${esc(a.name)} is listed ${esc(a.inj)}: check the news before you move.`);
    if (L.partial) R.push("Other teams' rosters aren't readable in this league yet, so only free agents and your players show.");
    return { verdict, head: `${sg(w4)} lineup pts over 4 weeks`, reasons: R, html: true, adds: A, drops: D };
  };

  // ---------- basketball: same math as the Players page's trade check (shq/nba_trade.py trade()) ----------
  M.nbaEval = function (L, adds, drops) {
    const by = Object.fromEntries(L.players.map(p => [p.id, p]));
    const get = adds.map(i => by[i]).filter(Boolean);
    if (!get.length) return null;
    const have = get.filter(a => a.own === "me");
    if (have.length) return { verdict: "unavailable", head: "already on your roster", reasons: have.map(a => `${esc(a.name)} is already yours: pick a player you don't have.`), html: true, adds: get, drops: [] };
    const mine = L.players.filter(p => p.own === "me");
    const give = [];
    get.forEach((a, k) => {
      let d = by[drops[k]] && by[drops[k]].own === "me" && !give.includes(by[drops[k]]) ? by[drops[k]] : null;
      if (!d) d = mine.filter(p => !give.includes(p) && !get.includes(p)).sort((x, y) => (x.above || 0) - (y.above || 0) || x.v - y.v)[0] || null;
      if (d) give.push(d);
    });
    const t = L.trade || { weights: [], dynasty: false };
    const now = sum(get, p => p.above || 0) - sum(give, p => p.above || 0);
    const cats = L.cats.map((c, i) => sum(get.filter(p => p.above > 0), p => p.z[i]) - sum(give.filter(p => p.above > 0), p => p.z[i]));
    const w = t.weights && t.weights.length ? t.weights : cats.map(() => 1);
    const fit = now + cats.reduce((a, c, i) => a + (w[i] - 1) * c, 0);
    const dyn = t.dynasty ? sum(get, p => p.dyn || 0) - sum(give, p => p.dyn || 0) : null;
    const wk = sum(get, p => p.wk || 0) - sum(give, p => p.wk || 0);
    const score = dyn ?? fit;
    let verdict = Math.abs(score) < 0.5 ? "coin" : score > 0 ? "worth" : "not";
    const order = L.cats.map((c, i) => i).sort((a, b) => cats[b] - cats[a]), rk = t.ranks || [], n = Object.keys(t.profiles || {}).length;
    const named = i => `${L.cats[i]} ${sg(cats[i])}${rk[i] ? ` (you're ${rk[i]} of ${n})` : ""}`;
    const up = order.filter(i => cats[i] >= 0.3).slice(0, 3).map(named), down = order.filter(i => cats[i] <= -0.3).reverse().slice(0, 3).map(named);
    const R = [`Value per game above a waiver-level player ${sg(now)}; fit to your weak categories ${sg(fit)}${dyn != null ? `; dynasty value ${sg(dyn)}` : ""}.`,
      `This week ${sg(wk)} (value × games left).`, (up.length ? "Helps " + up.join(", ") : "Helps no category much") + (down.length ? "; hurts " + down.join(", ") : "") + "."];
    const line = p => [`value ${sg(p.v)}/g (#${p.rk})`, `${p.g ? p.g[0] : "?"} games left, ${p.g ? p.g[1] : "?"} next week`, `${p.min} min${p.dmin != null ? ` (${sg(p.dmin)} lately)` : ""}`,
      p.age ? `age ${Math.floor(p.age)}` : "", p.inj ? `<b>${esc(p.inj)}</b>` : "", p.pct != null ? `${p.pct}% rostered` : ""].filter(Boolean).join(" · ");
    for (const a of get) R.push(`<b>Add ${esc(a.name)}</b> (${esc(a.pos)} ${esc(a.team)}): ${line(a)}${a.own && a.own !== "me" ? `. On ${esc(a.own)}'s roster: a trade, not a waiver add` : ""}.`);
    for (const x of give) R.push(`<b>Drop ${esc(x.name)}</b> (${esc(x.pos)} ${esc(x.team)}): ${line(x)}.`);
    for (const a of get) if (a.out || /out|injur/i.test(a.inj || "")) R.push(`${esc(a.name)} is listed ${esc(a.inj || "out")}: his value assumes he plays, so check the news first.`);
    return { verdict, head: dyn != null ? `${sg(dyn)} dynasty value` : `${sg(fit)} fit, ${sg(now)}/g`, reasons: R, html: true, adds: get, drops: give };
  };

  // ---------- guillotine: War Room model result (tryMove) -> the same shape ----------
  M.fromWR = function (r) {
    if (!r) return null;
    return { verdict: r.verdict, head: `${sg(r.dWin * 100)} points of win odds`, reasons: r.reasons.map(esc), html: true,
      weeks: r.weeks, adds: r.adds, drops: r.drops };
  };

  // ---------- loading (browser only) ----------
  const BASE = (() => { try { return new URL("../", document.currentScript.src).href; } catch (e) { return ""; } })();
  const url = p => BASE + p;
  const getJSON = p => fetch(url(p) + "?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null);
  const once = {};
  const memo = (k, f) => once[k] || (once[k] = f().catch(e => { delete once[k]; throw e; }));
  // the War Room's model in a function scope, so its globals (S, ME, roster...) never meet the page's
  M.loadWR = () => memo("wr", async () => {
    const [D, src] = await Promise.all([getJSON("war-room-v2/data.json"),
      fetch(url("war-room-v2/model.js") + "?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.text() : null)]);
    if (!D || !src) throw new Error("War Room data not found");
    const api = new Function("D", src + "\n;return { tryMove, playerList, mine: () => roster(ME), S, D };")(D);
    return { list: () => api.playerList(), evaluate: (a, d) => M.fromWR(api.tryMove(a, d)), source: `War Room v2 model, data ${D.asof}` };
  });
  M.wrEngine = api => ({ list: () => api.playerList(), evaluate: (a, d) => M.fromWR(api.tryMove(a, d)), source: "this page's model" });
  M.engineFor = async function (name, lg) {
    if (lg && lg.advice && lg.advice.guillotine) return M.loadWR();
    if (lg && lg.sport === "nba") {
      const all = await memo("nba", () => getJSON("data/players.json")), L = all && all.leagues[name];
      if (!L) throw new Error("no player data for this league yet");
      return { list: () => L.players.map(p => ({ id: p.id, name: p.name, pos: p.pos, team: p.team, own: p.own, inj: p.inj })),
        evaluate: (a, d) => M.nbaEval(L, a, d), source: "category values from the Players page" };
    }
    const all = await memo("nfl", () => getJSON("data/players_nfl.json")), L = all && all.leagues[name];
    if (!L) throw new Error("no player data for this league yet");
    if (L.dynasty == null) L.dynasty = /FantasyCalc dynasty/.test(L.basis || "");
    const slots = (lg && lg.starters || []).map(p => p.slot);
    return { list: () => L.players.map(p => ({ id: p.id, name: p.name, pos: p.pos, team: p.team, own: p.own, inj: p.inj })),
      evaluate: (a, d) => M.nflEval(L, slots, a, d), source: "this week's projections and Sleeper's next 4 weeks" };
  };

  // ---------- UI ----------
  const CSS = `.mv{display:grid;gap:8px;font-size:13.5px}
.mv .mv-pair{display:grid;grid-template-columns:1fr 1fr;gap:6px;align-items:start}
@media (max-width:520px){.mv .mv-pair{grid-template-columns:1fr}}
.mv label{display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted,#667)}
.mv input,.mv select,.mv textarea{font:inherit;font-size:15px;width:100%;box-sizing:border-box;color:var(--text,var(--ink,inherit));background:var(--card2,var(--panel,#fff));border:1px solid var(--line,#ccd);border-radius:8px;padding:7px 8px;min-width:0}
.mv .mv-sug{display:grid;gap:2px;margin-top:3px}
.mv .mv-sug button{all:unset;cursor:pointer;padding:6px 8px;border-radius:6px;border:1px solid var(--line,#ccd);background:var(--card,var(--panel,#fff));font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mv .mv-sug button:hover,.mv .mv-sug button:focus-visible{border-color:var(--accent,#b07a12)}
.mv .mv-chip{display:flex;justify-content:space-between;gap:6px;align-items:center;border:1px solid var(--accent,#b07a12);border-radius:8px;padding:6px 8px;background:var(--accent-soft,transparent)}
.mv .mv-chip button{all:unset;cursor:pointer;color:var(--muted,#667);padding:0 4px;font-size:15px}
.mv .mv-tag{font-size:11px;color:var(--muted,#667)}
.mv .mv-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.mv .mv-btn{font:inherit;font-size:13px;font-weight:650;border:1px solid var(--line,#ccd);background:var(--card2,var(--panel,#fff));color:var(--text,var(--ink,inherit));border-radius:999px;padding:5px 12px;cursor:pointer}
.mv .mv-btn.go{background:var(--accent,#b07a12);border-color:var(--accent,#b07a12);color:#fff}
.mv .mv-out{border-left:4px solid var(--line,#ccd);padding:4px 0 4px 10px}
.mv .mv-out.worth{border-color:var(--good,#1f7a4d)} .mv .mv-out.not,.mv .mv-out.unavailable{border-color:var(--bad,#b3261e)} .mv .mv-out.coin{border-color:var(--warn,#a86a00)}
.mv .mv-v{font-weight:800;font-size:16px} .mv .worth .mv-v{color:var(--good,#1f7a4d)} .mv .not .mv-v,.mv .unavailable .mv-v{color:var(--bad,#b3261e)} .mv .coin .mv-v{color:var(--warn,#a86a00)}
.mv .mv-out ul{margin:4px 0 0;padding-left:18px} .mv .mv-out li{margin:2px 0}
.mv .mv-wk{display:flex;gap:4px;flex-wrap:wrap;margin:4px 0} .mv .mv-wk span{font-size:11.5px;border-radius:4px;padding:1px 5px;background:var(--chip-bg,rgba(127,127,127,.15))}
.mv .mv-wk .up{background:var(--good-soft,#dff1e7);color:var(--good,#1f7a4d)} .mv .mv-wk .dn{background:var(--bad-soft,#f9e0de);color:var(--bad,#b3261e)}
.mv .mv-fine{font-size:11.5px;color:var(--muted,#667);margin:0}
.mv .mv-ask{border-top:1px solid var(--line,#ccd);padding-top:8px;display:grid;gap:6px}
.mv .mv-ans{border:1px solid var(--line,#ccd);border-radius:8px;padding:6px 9px;background:var(--card2,transparent)}
.mv .mv-ans .q{font-weight:650} .mv .mv-ans .a{white-space:pre-wrap;margin-top:3px} .mv .mv-ans .m{font-size:11px;color:var(--muted,#667)}`;
  function style() {
    if (typeof document === "undefined" || document.getElementById("mv-css")) return;
    const s = document.createElement("style"); s.id = "mv-css"; s.textContent = CSS; document.head.appendChild(s);
  }
  const STATE = M.state = M.state || {};          // per league: survives the page's 5-minute re-render
  const fold = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, "");
  const ownTxt = p => p.own === "me" ? "yours" : p.own ? p.own : p.freed ? "on waivers" : "free agent";

  M.search = function (list, q, n = 8) {
    const f = fold(q).trim();
    if (f.length < 2) return [];
    const hits = list.filter(p => fold(p.name).includes(f) || fold(p.name).split(" ").some(w => w.startsWith(f)));
    return hits.sort((a, b) => (fold(a.name).startsWith(f) ? 0 : 1) - (fold(b.name).startsWith(f) ? 0 : 1) || (a.own ? 1 : 0) - (b.own ? 1 : 0)).slice(0, n);
  };

  // host: an element; name: league name; opts: {engine (promise or object), lg (lineups league), ask: true}
  M.mount = function (host, name, opts = {}) {
    style();
    const st = STATE[name] = STATE[name] || { pairs: [{ add: null, drop: "" }], q: ["", ""], draft: "" };
    let eng = null, list = [], mineL = [], err = "";
    host.innerHTML = `<div class="mv"><div class="mv-moves"><p class="mv-fine">Loading players…</p></div><div class="mv-out" hidden aria-live="polite"></div>${opts.ask === false ? "" : `<div class="mv-ask"></div>`}</div>`;
    const $m = host.querySelector(".mv-moves"), $o = host.querySelector(".mv-out"), $a = host.querySelector(".mv-ask");
    const byId = id => list.find(p => p.id === id);
    function draw() {
      if (err) { $m.innerHTML = `<p class="mv-fine">Try a move isn't available: ${esc(err)}</p>`; return; }
      const opt = (v, t, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(t)}</option>`;
      $m.innerHTML = st.pairs.map((pr, i) => {
        const a = pr.add && byId(pr.add);
        const add = a ? `<div class="mv-chip"><span><b>${esc(a.name)}</b> <span class="mv-tag">${esc(a.pos)} ${esc(a.team)} · ${esc(ownTxt(a))}${a.inj ? " · " + esc(a.inj) : ""}</span></span><button data-clear="${i}" aria-label="Change player">✕</button></div>`
          : `<input type="search" data-q="${i}" placeholder="Search a player" value="${esc(st.q[i] || "")}" autocomplete="off" enterkeyhint="search"><div class="mv-sug" data-sug="${i}"></div>`;
        const drop = `<select data-drop="${i}">${opt("", "Let the model pick", pr.drop)}${mineL.filter(p => !st.pairs.some((x, j) => j !== i && x.drop === p.id))
          .map(p => opt(p.id, `${p.name} (${p.pos}${p.team ? " " + p.team : ""})`, pr.drop)).join("")}</select>`;
        return `<div class="mv-pair"><div><label>${i ? "And add" : "Add"}</label>${add}</div><div><label>Drop</label>${drop}</div></div>`;
      }).join("") + `<div class="mv-row">${st.pairs.length < 2 ? `<button class="mv-btn" data-more>+ Two moves at once</button>` : `<button class="mv-btn" data-less>Remove the second move</button>`}
        ${st.pairs.some(p => p.add) ? `<button class="mv-btn" data-reset>Start over</button>` : ""}<span class="mv-fine">${esc(eng ? "Numbers: " + eng.source + ". Nothing is sent anywhere." : "")}</span></div>`;
      st.pairs.forEach((pr, i) => { if (!pr.add) sug(i); });
    }
    function sug(i) {
      const box = $m.querySelector(`[data-sug="${i}"]`);
      if (!box) return;
      const hits = M.search(list, st.q[i] || "");
      box.innerHTML = hits.map(p => `<button data-pick="${esc(p.id)}" data-i="${i}">${esc(p.name)} <span class="mv-tag">${esc(p.pos)} ${esc(p.team)} · ${esc(ownTxt(p))}${p.inj ? " · " + esc(p.inj) : ""}</span></button>`).join("")
        || (String(st.q[i] || "").trim().length >= 2 ? `<span class="mv-fine">No player by that name in this league's list.</span>` : "");
    }
    function run() {
      st.result = null;
      const adds = st.pairs.map(p => p.add).filter(Boolean);
      if (!eng || !adds.length) { $o.hidden = true; return; }
      $o.hidden = false; $o.className = "mv-out"; $o.innerHTML = `<span class="mv-fine">Working it out…</span>`;
      setTimeout(() => {   // let "Working" paint before the simulation runs
        let r;
        try { r = eng.evaluate(adds, st.pairs.filter(p => p.add).map(p => p.drop || null)); } catch (e) { r = null; $o.innerHTML = `<span class="mv-fine">Couldn't work that out: ${esc(e.message)}</span>`; return; }
        if (!r) { $o.hidden = true; return; }
        st.result = r;
        // the drops the engine chose show in the pickers (so the second move can't reuse them)
        st.pairs.filter(p => p.add).forEach((p, k) => { if (!p.drop && r.drops && r.drops[k]) p.autoDrop = r.drops[k].id; });
        const wk = r.weeks ? `<div class="mv-wk">${r.weeks.map(x => `<span class="${x.d >= 1 ? "up" : x.d <= -1 ? "dn" : ""}">wk ${x.w} ${sg(x.d)}</span>`).join("")}</div>` : "";
        $o.className = "mv-out " + r.verdict;
        $o.innerHTML = `<div><span class="mv-v">${M.WORD[r.verdict]}</span> · ${esc(r.head)}</div>${wk}<ul>${r.reasons.map(x => `<li>${r.html ? x : esc(x)}</li>`).join("")}</ul>`;
      }, 20);
    }
    host.addEventListener("input", e => {
      const i = e.target.dataset.q;
      if (i != null) { st.q[+i] = e.target.value; sug(+i); }
      if (e.target.dataset.askq != null) st.draft = e.target.value;
    });
    host.addEventListener("change", e => {
      const i = e.target.dataset.drop;
      if (i != null) { st.pairs[+i].drop = e.target.value; draw(); run(); }
    });
    host.addEventListener("click", e => {
      const t = e.target.closest("button");
      if (!t || !host.contains(t)) return;
      if (t.dataset.pick) { const i = +t.dataset.i; st.pairs[i].add = t.dataset.pick; st.q[i] = ""; draw(); run(); }
      else if (t.dataset.clear != null) { st.pairs[+t.dataset.clear].add = null; draw(); run(); setTimeout(() => { const q = $m.querySelector(`[data-q="${t.dataset.clear}"]`); q && q.focus(); }, 0); }
      else if (t.dataset.more != null) { st.pairs.push({ add: null, drop: "" }); draw(); }
      else if (t.dataset.less != null) { st.pairs.length = 1; st.q[1] = ""; draw(); run(); }
      else if (t.dataset.reset != null) { st.pairs = [{ add: null, drop: "" }]; st.q = ["", ""]; draw(); run(); }
      else if (t.dataset.ask != null) ask();
    });
    if ($a) askDraw();
    function askDraw() {
      $a.innerHTML = `<label for="mvq-${esc(SHQ.slug ? SHQ.slug(name) : name)}">Ask Claude about ${esc(name)}</label>
        <textarea id="mvq-${esc(SHQ.slug ? SHQ.slug(name) : name)}" data-askq rows="2" placeholder="e.g. Is he worth adding this week while nobody else wants him?">${esc(st.draft)}</textarea>
        <div class="mv-row"><button class="mv-btn go" data-ask>Ask</button><span class="mv-fine">For news and gut calls the numbers can't settle. Opens GitHub with your question filled in: tap <b>Create</b>. <b>Screenshots:</b> paste (Ctrl+V) or drag them into GitHub's text box before you tap Create (on a phone, use its attach button); Claude looks at each one. The answer shows here in a few minutes. Questions, screenshots and answers are public on GitHub, like Feedback: sports only.</span></div>
        <div class="mv-answers"></div>`;
      answers();
    }
    async function answers() {
      const box = $a.querySelector(".mv-answers");
      const [all, open] = await Promise.all([getJSON("data/asks.json"),
        fetch(`https://api.github.com/repos/${REPO}/issues?labels=ask&state=open&per_page=30`).then(r => r.ok ? r.json() : []).catch(() => [])]);
      const done = ((all && all.leagues && all.leagues[name]) || []).slice().sort((a, b) => String(b.answered).localeCompare(String(a.answered)));
      const doneIds = new Set(done.map(x => x.issue));
      const waiting = (Array.isArray(open) ? open : []).filter(i => (i.body || "").includes(`League: ${name}\n`) || (i.body || "").endsWith(`League: ${name}`))
        .filter(i => !doneIds.has(i.number));
      const when = iso => { try { return new Date(iso).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" }); } catch (e) { return ""; } };
      box.innerHTML = waiting.map(i => `<div class="mv-ans"><div class="q">${esc((i.body || "").replace(/!\[[^\]]*\]\([^)]*\)|<img[^>]*>/g, "").trim().split("\n\n")[0])}</div><div class="m">Asked ${esc(when(i.created_at))} · Claude is answering (a few minutes)</div></div>`).join("")
        + done.slice(0, 6).map((x, k) => `<details class="mv-ans"${k ? "" : " open"}><summary class="q">${esc(x.q)}</summary><div class="a">${esc(x.a)}</div>
          <div class="m">${esc(when(x.answered))}${x.shots ? ` · ${x.shots} screenshot${x.shots > 1 ? "s" : ""}` : ""}${x.issue ? ` · <a href="https://github.com/${REPO}/issues/${x.issue}" target="_blank" rel="noopener">thread</a>` : ""}</div></details>`).join("");
    }
    M.refreshAnswers = M.refreshAnswers || {};
    M.refreshAnswers[name] = () => $a && answers();
    function ask() {
      const q = String(st.draft || "").trim();
      if (!q) { const ta = $a.querySelector("textarea"); ta && ta.focus(); return; }
      const move = st.pairs.filter(p => p.add).map(p => { const a = byId(p.add), d = byId(p.drop || p.autoDrop); return `add ${a ? a.name : p.add}${d ? ", drop " + d.name : ""}`; }).join("; ");
      const verdict = st.result ? `${M.WORD[st.result.verdict]} (${st.result.head})` : "";
      const body = `${q}\n\n---\nLeague: ${name}\n` + (move ? `Move on screen: ${move}${verdict ? " → " + verdict : ""}\n` : "") + `Page: ${typeof location !== "undefined" ? location.href.split("#")[0] : ""}\n`;
      const title = `Ask: ${name}: ${q.replace(/\s+/g, " ").slice(0, 70)}`;
      const u = `https://github.com/${REPO}/issues/new?` + new URLSearchParams({ title, body, labels: "ask" });
      // the clipboard is left alone so a screenshot he just copied can be pasted on GitHub (Nov 12); only a question too
      // long for the link is copied there instead
      if (u.length > 7000) { try { navigator.clipboard && navigator.clipboard.writeText(`${title}\n\n${body}`).catch(() => {}); } catch (e) {} }
      window.open(u, "_blank", "noopener");
      st.draft = ""; const ta = $a.querySelector("textarea"); if (ta) ta.value = "";
      // GitHub takes a moment: look again for the new question a few times
      [20, 60, 180].forEach(s => setTimeout(answers, s * 1000));
    }
    Promise.resolve(typeof opts.engine === "function" ? opts.engine() : opts.engine || M.engineFor(name, opts.lg)).then(e => {
      eng = e; list = e.list(); mineL = list.filter(p => p.own === "me").sort((a, b) => a.pos.localeCompare(b.pos) || a.name.localeCompare(b.name));
      draw(); if (st.pairs.some(p => p.add)) run();
    }).catch(x => { err = x.message || String(x); draw(); });
  };
})();
