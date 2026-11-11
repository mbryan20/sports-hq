"use strict";
// Shared core for every Sports HQ layout: data loading (one place, so a future passphrase lock only touches
// SHQ.load), summaries, the league detail view, the drawer, theme and the feedback sheet.
// Layouts call SHQ.start(render) and read SHQ.data / SHQ.leagues() / SHQ.feed().
(function () {
  const TZ = "America/Chicago";
  const BASE = new URL("../", document.currentScript.src);   // docs/ (this file is docs/lib/core.js)
  const REPO = "mbryan20/sports-hq";
  const FILES = ["lineups", "weekly", "status", "digest", "pick_lines"];
  const BAD = { OUT: "bad", IR: "bad", PUP: "bad", SUSP: "bad", NA: "bad", INACTIVE: "bad", EMPTY: "bad", "NO TEAM": "bad", D: "d", Q: "q", BYE: "bye", "NO GAME": "off" };

  const S = window.SHQ = { data: {}, url: p => new URL(p, BASE).href, TZ, REPO };
  const openTab = window.open.bind(window);   // kept before any layout script can shadow the global open()

  // ---------- helpers ----------
  const esc = S.esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  S.get = k => { try { return localStorage.getItem(k); } catch { return null; } };
  S.set = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  const kick = S.kick = iso => {
    if (!iso) return "";
    const d = new Date(iso);
    const day = d.toLocaleDateString("en-US", { weekday: "short", timeZone: TZ });
    const t = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ }).replace(" AM", "a").replace(" PM", "p");
    return `${day} ${t}`;
  };
  S.time = iso => kick(iso).split(" ")[1] || "";
  S.dayKey = iso => new Date(iso).toLocaleDateString("en-CA", { timeZone: TZ });
  const newsDate = iso => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: TZ }) + " " + S.time(iso);
  const ago = S.ago = iso => {
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    return h < 24 ? `${h}h ${m % 60}m ago` : `${Math.floor(h / 24)}d ago`;
  };
  const pct = S.pct = x => x > 0 && x < 0.005 ? "<1%" : `${Math.round(x * 100)}%`;
  const chip = S.chip = f => `<span class="chip ${BAD[f] || ""}">${esc(f)}</span>`;
  const n0 = v => Number(v).toLocaleString("en-US");
  const signed = v => (v > 0 ? "+" : "") + v;
  S.slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-");
  S.PLAYERS_SPORTS = ["nba", "nfl"];   // leagues on the Players page (players/; data/players.json, players_nfl.json)

  // ---------- data: the only place that fetches ----------
  // one data file on demand (the Players page's players.json is too big to load on every page)
  S.loadFile = f => fetch(S.url(`data/${f}.json?t=${Date.now()}`), { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null);
  S.load = async function () {
    const got = await Promise.all(FILES.map(S.loadFile));
    FILES.forEach((f, i) => { if (got[i]) S.data[f] = got[i]; });
    return S.data;
  };
  S.start = function (render) {
    const go = () => S.load().then(() => { render(S.data); paintStatus(); });
    S.reload = go;
    document.addEventListener("visibilitychange", () => { if (!document.hidden) go(); });
    setInterval(go, 5 * 60 * 1000);
    document.addEventListener("click", e => { if (e.target.closest("[data-reload]")) go(); });
    go();
    if ("serviceWorker" in navigator) navigator.serviceWorker.register(S.url("sw.js")).catch(() => {});
  };

  // ---------- summaries ----------
  const realAdds = list => (list || []).filter(t => !/^(No free agent|FA adds need)/i.test(t));
  const offerText = o => `Give ${o.give.join(" + ")} → get ${o.get.join(" + ")} (to ${o.team}, you +${o.my_gain}/gm)`;
  // One guillotine bid line, call first. Rows from War Room v2 (b.v2: shq/guillotine.py v2_rows) carry its
  // call, bid, drop, why and win chance; the dashboard model's own rows (the fallback) carry a likely price.
  const bidText = S.bidText = b => {
    const pts = b.gain > 0 ? `+${b.gain} pts` : b.gain_ros > 0 ? `+${b.gain_ros} pts rest of season` : "";
    const who = `${b.name} (${[b.pos, b.pos === "DEF" ? "" : b.team || "FA"].filter(Boolean).join(" ")}${pts ? ", " + pts : ""}${b.injury ? ", " + b.injury : ""})`;
    const money = b.price > 0 ? `bid $${b.price}` : "claim at $0";
    if (b.v2) {
      const head = { bid: money[0].toUpperCase() + money.slice(1), "coin flip": `Coin flip, ${money}`, "add free": "Add free",
        "priced out": "Priced out", skip: "Skip" }[b.call] || b.call;
      const extra = [b.drop && b.call !== "priced out" && b.call !== "skip" ? `drop ${b.drop}` : "",
        b.win_chance != null && (b.call === "bid" || b.call === "coin flip") ? `${pct(b.win_chance)} to win` : "",
        b.why && b.why !== "free agent" ? b.why : ""].filter(Boolean);
      return `${head}: ${who}${extra.length ? " · " + extra.join(" · ") : ""}`;
    }
    if (b.call === "add free") return `Add free: ${who} · free agent, no bid needed`;
    if (b.call === "bid") return `${b.price > 0 ? `Bid $${b.price}${b.max > b.price ? "–" + b.max : ""}` : `Claim at $0${b.max > 0 ? ` (up to $${b.max})` : ""}`}: ${who}`;
    const limit = b.max > 0 ? `you'd stop at $${b.max}` : "over your reserve";
    return `${b.call[0].toUpperCase() + b.call.slice(1)}: ${who} · rivals may go $${b.price}, ${limit}`;
  };
  // the bids worth acting on (priced-out players stay on the league page only)
  const actBids = g => (g?.bids || []).filter(b => b.call !== "priced out" && b.call !== "skip");
  S.offerText = offerText;

  S.leagues = function (d = S.data) {
    const out = [];
    for (const [name, lg] of Object.entries(d.lineups?.leagues || {})) {
      const a = lg.advice || {};
      const g = a.guillotine, c = a.cats;
      const fixes = a.fixes || [], moves = a.moves || [], adds = realAdds(a.adds), offers = a.trades?.offers || [];
      const chase = (c?.chase || []).filter(t => !/^No category/i.test(t));
      const starters = lg.starters || [];
      const open = starters.filter(p => !p.started && p.kickoff).map(p => p.kickoff).sort();
      let score;
      if (g) score = { kind: "guillotine", survive: g.survive, cut: g.cut, rank: g.rank, n: g.n, proj: g.proj };
      else if (lg.sport === "nba" && c) score = { kind: "cats", now: c.now, proj: c.proj, close: c.close };
      // category leagues have no points: never a "0.0 projected", just a note until the category table fills in
      else if (lg.sport === "nba") score = { kind: "cats", pending: true, now: "–", proj: "–", close: 0 };
      else score = { kind: "points", me: lg.proj, opp: lg.opp_proj };
      const losing = score.kind === "points" && score.opp != null && score.me < score.opp;
      const state = lg.pending ? "pending"
        : fixes.length || a.danger || (g && g.cut > 0.2) ? "bad"
        : moves.length || losing || chase.length ? "warn" : "ok";
      const bid0 = actBids(g)[0];
      // a chase line ("Keep in the lineup: …") changes nothing, so it's a "keep", never a move, and comes after the adds
      const top = fixes[0] ? { kind: "fix", text: fixes[0] } : moves[0] ? { kind: "move", text: moves[0] }
        : bid0 ? { kind: "add", text: bidText(bid0) } : adds[0] ? { kind: "add", text: adds[0] }
        : chase[0] ? { kind: "keep", text: chase[0] } : offers[0] ? { kind: "trade", text: offerText(offers[0]) } : null;
      out.push({
        name, lg, a, g, c, state, score, top, fixes, moves, adds, offers, chase,
        sport: lg.sport, platform: lg.platform, week: lg.week, opponent: lg.opponent,
        headline: a.matchup || lg.message || "", nextLock: open[0] || null,
        locked: starters.filter(p => p.started).length, total: starters.length,
        meta: [PLAT[lg.platform] || lg.platform, (lg.sport || "").toUpperCase(), lg.week ? `Wk ${lg.week}` : ""].filter(Boolean).join(" · "),
      });
    }
    return out;
  };
  const PLAT = { espn: "ESPN", yahoo: "Yahoo", sleeper: "Sleeper" };

  // stale-line gaps still open (picks/pp/lines.py)
  S.pickGaps = function (d = S.data) {
    const pl = d.pick_lines;
    if (!pl?.rows) return [];
    const now = Date.now();
    return pl.rows.filter(r => r.flag && new Date(r.closes) > now && new Date(r.kick) > now).map(r => ({
      ...r, big: r.gap >= (pl.alert_gap || 1.5),
      text: `${r.side} ${signed(r.pool_line)} (${r.pool.toUpperCase()}): pool ${signed(r.pool_line)} vs market ${signed(r.market_line)}${r.keys?.length ? `, crosses ${r.keys.join(", ")}` : ""}`,
    }));
  };

  // today's digest only counts if it was built today (CT)
  S.digestToday = function (d = S.data) {
    const g = d.digest;
    if (!g?.items) return null;
    return S.dayKey(g.generated) === S.dayKey(new Date()) ? g : null;
  };

  // One ranked list of everything to do, across leagues.
  // "keep": a category chase line, informational, so no "Lineup moves" / "Move" / "Do now" count includes it
  const RANK = { fix: 0, pick: 1, risk: 1, move: 2, add: 3, trade: 4, keep: 5 };
  S.KINDS = { fix: "Fix", pick: "Picks", risk: "Risk", move: "Move", add: "Add", trade: "Trade", keep: "Keep" };
  S.feed = function (d = S.data) {
    const items = [];
    for (const L of S.leagues(d)) {
      const push = (kind, text, extra = {}) => items.push({ kind, text, league: L.name, state: L.state, ...extra });
      L.fixes.forEach(t => push("fix", t));
      if (L.g && L.g.cut > 0.2) push("risk", `Cut risk ${pct(L.g.cut)}: rank ${L.g.rank} of ${L.g.n}`);
      L.moves.forEach(t => push("move", t));
      L.chase.forEach(t => push("keep", t));
      actBids(L.g).slice(0, 5).forEach(b => push("add", bidText(b)));
      // War Room v2's calls cover the guillotine's adds (with its drops); the generic add ideas stay on the league page
      if (!L.g?.bid_source?.url) L.adds.slice(0, 2).forEach(t => push("add", t));
      L.offers.slice(0, 1).forEach(o => push("trade", offerText(o)));
    }
    S.pickGaps(d).filter(r => r.big).forEach(r => items.push({ kind: "pick", league: "Picks", text: r.text + `. Closes ${kick(r.closes)}`, href: S.url("picks/") }));
    const dg = S.digestToday(d);
    (dg?.items || []).filter(i => i.league === "Picks" && i.urgent).forEach(i => items.push({ kind: "pick", league: "Picks", text: i.text, href: S.url("picks/") }));
    return items.sort((x, y) => RANK[x.kind] - RANK[y.kind]);
  };

  // ---------- small render pieces ----------
  S.scoreHTML = function (L, big) {
    const s = L.score;
    if (L.lg.pending) return `<div class="score-line muted">${esc(L.lg.message || "Waiting for data")}</div>`;
    if (s.kind === "guillotine") return `<div class="score-line"><span class="num ${s.cut > 0.2 ? "bad" : "good"}">${pct(s.survive)}</span><span class="lbl">survive · rank ${s.rank}/${s.n}</span></div>
      <div class="meter"><i style="width:${Math.round(s.survive * 100)}%" class="${s.cut > 0.2 ? "bad" : "good"}"></i></div>`;
    if (s.kind === "cats" && s.pending) return `<div class="score-line"><span class="lbl">Category outlook fills in with this week's matchup data${L.opponent ? " · vs " + esc(L.opponent) : ""}</span></div>`;
    if (s.kind === "cats") {
      const [w, l] = String(s.now).split("-").map(Number);
      return `<div class="score-line"><span class="num">${esc(s.now)}</span><span class="lbl">cats now · on course ${esc(s.proj)}${s.close ? ` · ${s.close} close` : ""}</span></div>
      <div class="meter split"><i style="width:${Math.round(w / Math.max(1, w + l) * 100)}%" class="${w >= l ? "good" : "bad"}"></i></div>`;
    }
    if (s.opp == null) return `<div class="score-line"><span class="num">${(s.me ?? 0).toFixed(1)}</span><span class="lbl">projected${L.opponent ? " · vs " + esc(L.opponent) : ""}</span></div>`;
    const share = s.me / Math.max(1, s.me + s.opp);
    const cls = s.me >= s.opp ? "good" : "bad";
    return `<div class="score-line"><span class="num ${cls}">${s.me.toFixed(1)}</span><span class="vsx">–</span><span class="num opp">${s.opp.toFixed(1)}</span>
      <span class="lbl">${big ? "projected · vs " + esc(L.opponent || "") : signed((s.me - s.opp).toFixed(1))}</span></div>
      <div class="meter split"><i style="width:${Math.round(share * 100)}%" class="${cls}"></i></div>`;
  };
  S.badges = function (L) {
    const b = [];
    if (L.fixes.length) b.push(`<span class="badge bad">${L.fixes.length} fix${L.fixes.length > 1 ? "es" : ""}</span>`);
    if (L.g && L.g.cut > 0.2) b.push(`<span class="badge bad">cut risk ${pct(L.g.cut)}</span>`);
    if (L.moves.length) b.push(`<span class="badge warn">${L.moves.length} move${L.moves.length > 1 ? "s" : ""}</span>`);
    if (L.adds.length) b.push(`<span class="badge">${L.adds.length} add${L.adds.length > 1 ? "s" : ""}</span>`);
    if (L.offers.length) b.push(`<span class="badge">${L.offers.length} trade${L.offers.length > 1 ? "s" : ""}</span>`);
    if (!b.length && !L.lg.pending) b.push(`<span class="badge good">all set</span>`);
    return b.join("");
  };
  S.dot = state => `<span class="dot ${state}" aria-hidden="true"></span>`;
  S.lockText = L => L.nextLock ? `Next lock ${kick(L.nextLock)} · ${L.locked}/${L.total} locked` : L.total && L.locked === L.total ? "All starters locked" : "";

  // ---------- league detail (shared by every layout) ----------
  function prow(p) {
    const sub = [p.team && p.opp ? `${p.team} ${p.opp}` : p.team, p.started ? "Locked" : kick(p.kickoff), p.why].filter(Boolean).join(" · ");
    const chips = p.flags?.length ? `<span class="chips">${p.flags.map(chip).join("")}</span>` : "";
    // the dated ESPN injury-report note behind any status, linked to his ESPN player card
    const news = p.news ? `<div class="sub news"><a href="${esc(p.news.url)}" target="_blank" rel="noopener">ESPN${p.news.at ? " " + esc(newsDate(p.news.at)) : ""}</a>: ${esc(p.news.note)}</div>` : "";
    // NBA category leagues: value per game and rank (shq/nba_values.py) instead of a points projection
    const v = p.cv;   // NBA only (football rows don't have it)
    const val = v ? `<div class="sub">Value #${v.rk} · ${signed(v.v.toFixed(1))}/g · this week ${signed(v.wk.toFixed(1))} · ${esc(v.src)}</div>` : "";
    return `<div class="prow${p.started ? " locked" : ""}"><div class="slot">${esc(p.slot === "SUPER_FLEX" ? "SF" : p.slot)}</div>
      <div class="who"><div class="pname">${esc(p.name)}${chips}</div><div class="sub">${esc(sub)}</div>${val}${news}</div>
      <div class="proj">${v ? `<span title="Category value rank">#${v.rk}</span>` : p.proj ? p.proj.toFixed(1) : ""}</div></div>`;
  }
  const li = t => `<li>${esc(t)}</li>`;
  const sec = (title, body, { open = true, cls = "", count = "" } = {}) => body ? `<details class="sec ${cls}"${open ? " open" : ""}>
    <summary><span>${title}</span>${count !== "" ? `<span class="count">${count}</span>` : ""}</summary>${body}</details>` : "";
  const ul = (items, cls = "") => items?.length ? `<ul class="tips ${cls}">${items.map(li).join("")}</ul>` : "";

  function guillotineHTML(g) {
    if (!g) return "";
    const bid = b => bidText(b) + (b.cut_with != null ? `, cut risk ${pct(g.cut)} → ${pct(b.cut_with)}` : "");
    const v2 = g.bid_source?.url;
    const risk = g.teams.filter(t => !t.me).slice(0, 3).map(t => `${t.name}: ${pct(t.cut)} cut risk (${t.proj.toFixed(1)} proj, $${t.faab} FAAB)`);
    const freed = g.freed?.players?.length ? `<div class="subhead">If ${esc(g.freed.team)} is cut (${pct(g.freed.cut)}), their best for you</div>${ul(g.freed.players.map(bid))}` : "";
    return sec(`Survival · week ${g.week}`, `<ul class="tips"><li class="${g.cut > 0.2 ? "bad" : "ok"}"><b>Survive ${pct(g.survive)}</b> · rank ${g.rank} of ${g.n} (${g.proj.toFixed(1)} proj) · cut risk ${pct(g.cut)}</li>${risk.map(li).join("")}</ul>`)
      + sec(`Bids · waivers ${esc(g.waivers)} CT`, ul(g.bids.length ? g.bids.map(bid) : [v2 ? "War Room v2 has no claims to make this week." : "No free agent adds a point to your lineup."]) + freed
        + `<p class="basis">${v2 ? `Calls from <a href="${esc(S.url(g.bid_source.url))}">War Room v2</a>${g.bid_source.as_of ? " (" + esc(g.bid_source.as_of) + ")" : ""}. ` : ""}`
        + `You have $${g.faab} FAAB${g.reserve != null ? `, keeping $${g.reserve} in reserve` : ""}. Most left: ${esc(g.rich.map(r => `${r.name} $${r.faab}`).join(", "))}. `
        + (v2 ? `Survival: ${g.sims} simulated weeks, best lineups. It only recommends.` : `War Room v2's bids aren't current, so these are the dashboard model's: ${g.sims} simulated weeks, best lineups; it only recommends.`) + `</p>`);
  }
  function catsHTML(c) {
    if (!c?.rows?.length) return "";
    const word = { win: "Win", lose: "Lose", close: "Close", tie: "Tie" };
    const rows = c.rows.map(r => `<tr><td>${esc(r.cat)}</td><td class="${r.now === "W" ? "lead" : ""}">${esc(r.me)}</td>
      <td class="${r.now === "L" ? "lead" : ""}">${esc(r.opp)}</td><td class="${esc(r.outlook)}">${esc(word[r.outlook] || r.outlook)}</td></tr>`).join("");
    return sec(`Categories · now ${esc(c.now)} · on course ${esc(c.proj)}${c.close ? `, ${c.close} close` : ""}`,
      `<table class="cats"><thead><tr><th>Cat</th><th>Me</th><th>Opp</th><th>Outlook</th></tr></thead><tbody>${rows}</tbody></table>
       <p class="basis">Games left this week (best lineup each day): you ${c.games_left[0]}, them ${c.games_left[1]}</p>`)
      + sec("Chase", ul(c.chase)) + sec("Category adds", ul(c.adds));
  }
  // NBA games grid and streamers (shq/nba_games.py)
  function gamesHTML(g) {
    if (!g) return "";
    const m = g.mine || {};
    const week = (w, title) => w?.groups?.length ? `<div class="subhead">${title}${w.span ? " · " + esc(w.span) : ""}</div><ul class="tips">${
      w.groups.map(([n, ts]) => `<li><b>${n} game${n === 1 ? "" : "s"}:</b> ${esc(ts.map(t => w.b2b.includes(t) ? t + "²" : t).join(", "))}</li>`).join("")}</ul>` : "";
    const mine = `<ul class="tips"><li>Games left this week: <b>you ${m.now ?? "?"}</b>${m.opp != null ? `, them ${m.opp}` : ""}${m.next != null ? ` · next week: you ${m.next}` : ""}</li></ul>`;
    return sec("Games &amp; streamers", mine + (g.streamers?.length ? `<div class="subhead">Streamers</div>${ul(g.streamers)}` : "")
      + week(g.now, "Rest of this week") + week(g.next, "Next week")
      + `<p class="basis">² = back-to-back. ${esc(g.basis)} Ideas only: nothing is sent.</p>`, { open: false, count: g.streamers?.length || "" });
  }
  // NBA trend radar (shq/radar.py): rising free agents and bench players, shrinking roles, injured starters' minutes
  function radarHTML(r) {
    if (!r) return "";
    const src = i => i.links?.length ? `<div class="sub-wrap">${i.links.map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`).join(" · ")}</div>` : "";
    const list = (title, xs) => xs?.length ? `<div class="subhead">${title}</div><ul class="tips">${xs.map(i => `<li>${esc(i.text)}${src(i)}</li>`).join("")}</ul>` : "";
    const body = list("Rising", r.rising) + list("Your shrinking roles", r.shrinking) + list("Injured: who gets the minutes", r.injuries);
    return sec("Trend radar", (body || `<ul class="tips"><li class="ok">No clear role change among free agents or your bench.</li></ul>`)
      + `<p class="basis">${r.need?.length ? `Ranked for ${esc(r.need.join(", "))}. ` : ""}${esc(r.basis)}</p>`, { count: r.rising?.length || "" });
  }
  function tradesHTML(t) {
    if (!t || !(t.offers?.length || t.lines?.length)) return "";
    const offer = o => {
      const p = Math.round((o.get_value - o.give_value) / Math.max(o.give_value, o.get_value) * 100);
      return `<li class="offer"><div><b>Give</b> ${esc(o.give.join(" + "))} <b>→ get</b> ${esc(o.get.join(" + "))}</div>
        <div class="sub-wrap">to ${esc(o.team)} · value ${n0(o.give_value)} for ${n0(o.get_value)} (${p > 0 ? "+" : ""}${p}%) · your lineup <b class="good">+${o.my_gain}/gm</b>, theirs +${o.their_gain}/gm</div>
        <div class="sub-wrap">${esc(o.why)}${o.cut ? ". You'd cut your worst bench player." : ""}</div></li>`;
    };
    return sec("Trade ideas", (t.offers?.length ? `<ul class="tips offers">${t.offers.map(offer).join("")}</ul>` : "") + ul(t.lines, "muted")
      + (t.basis ? `<p class="basis">${esc(t.basis)}. Ideas only: nothing is sent.</p>` : ""), { count: t.offers?.length || "" });
  }

  S.detail = function (name, d = S.data) {
    const L = S.leagues(d).find(x => x.name === name);
    if (!L) return `<p class="note">No data yet.</p>`;
    const lg = L.lg, a = L.a;
    const fb = (S.PLAYERS_SPORTS.includes(lg.sport) ? `<a class="pill" href="${esc(S.url("players/"))}#${S.slug(name)}">Players</a> ` : "")
      + S.fbButtons(`${name} detail`);
    if (lg.pending) return `<div class="detail"><div class="dhead"><h2>${esc(name)}</h2>${fb}</div><p class="note">${esc(lg.message)}<br>This fills in automatically.</p></div>`;
    const src = lg.roster_synced ? `roster read ${kick(lg.roster_synced)}` : lg.snapshot ? `ESPN read ${kick(lg.snapshot)}` : "";
    const stale = lg.stale ? `<p class="note"><b>Showing last good data</b>: the latest refresh failed.</p>` : "";
    const fixes = L.fixes.length ? ul(L.fixes, "fix") : `<ul class="tips"><li class="ok">Lineup is set, nothing to fix.</li></ul>`;
    const todo = sec("Fix now", fixes, { cls: L.fixes.length ? "hot" : "", count: L.fixes.length || "" })
      + guillotineHTML(L.g) + catsHTML(L.c) + gamesHTML(a.games) + radarHTML(a.radar) + sec("Lineup moves", ul(L.moves), { count: L.moves.length || "" })
      + sec("Waiver adds", ul(a.adds), { count: L.adds.length || "" }) + tradesHTML(a.trades)
      + (a.assets ? sec("Dynasty assets", ul(a.assets.lines) + `<p class="basis">${esc(a.assets.source)}</p>`, { open: false }) : "")
      + sec("Notes", ul(a.notes, "muted"), { open: false, count: a.notes?.length || "" });
    const roster = sec("Starters", lg.starters.map(prow).join(""), { count: L.total ? `${L.locked}/${L.total} locked` : "" })
      + sec("Bench", lg.bench.length ? lg.bench.map(prow).join("") : `<p class="note">Empty</p>`, { open: false, count: lg.bench.length });
    return `<div class="detail">${stale}
      <div class="dhead"><div><h2>${S.dot(L.state)}${esc(name)}</h2><div class="meta">${esc(L.meta)}${src ? " · " + esc(src) : ""} · built ${esc(a.built || "")}</div></div>${fb}</div>
      <div class="dscore">${S.scoreHTML(L, true)}<div class="headline ${a.danger ? "bad" : ""}">${esc(L.headline)}</div></div>
      <div class="dcols"><div class="dcol">${todo}</div><div class="dcol">${roster}</div></div></div>`;
  };

  S.todayHTML = function (d = S.data) {
    const g = d.digest;
    if (!g?.items) return `<p class="note">The daily check posts at 8am CT.</p>`;
    const items = g.items.length ? g.items : [{ league: "All leagues", text: "Every lineup looks set.", urgent: false }];
    const old = !S.digestToday(d);
    const upd = g.updated && !old ? ` · updated ${kick(g.updated)} to match the league pages` : "";
    return `<div class="meta">${esc(g.title)} · ${esc(kick(g.generated))}${esc(upd)}${old ? " · <b>not from today</b>" : ""}</div><ul class="tips">${
      items.map(i => `<li class="${i.urgent ? "hotli" : ""}"><b>${esc(i.league)}:</b> ${esc(i.text)}</li>`).join("")}</ul>`;
  };
  S.weeklyHTML = function (d = S.data) {
    const w = d.weekly;
    if (!w?.leagues?.length) return `<p class="note">The weekly plan posts Tuesdays at 7am CT.</p>`;
    const upd = w.start_sit_updated ? ` · start/sit and adds updated ${kick(w.start_sit_updated)}` : "";
    // adds follow the league page (Q-048); Tuesday's lines it no longer makes are noted under them
    const was = l => l.plan_changed?.length ? `<div class="note">Tuesday's plan had: ${l.plan_changed.map(esc).join(" · ")}</div>` : "";
    return `<div class="meta">Week ${w.week} · generated ${esc(kick(w.generated))}${esc(upd)}</div><div class="wgrid">` +
      w.leagues.map(l => `<div class="wcard"><h3>${esc(l.name)}</h3><div class="subhead">Start / sit</div>${ul(l.start_sit)}<div class="subhead">Top FA adds</div>${ul(l.adds)}${was(l)}</div>`).join("") + "</div>";
  };

  // ---------- status pill + footer ----------
  function paintStatus() {
    const s = S.data.status;
    if (!s) return;
    const mins = (Date.now() - new Date(s.last_run)) / 60000;
    document.querySelectorAll("[data-reload]").forEach(b => {
      b.textContent = `↻ ${ago(s.last_run).replace(" ago", "")}`;
      b.title = `Last cloud run ${kick(s.last_run)} · tap to reload`;
      b.classList.remove("ok", "warn", "bad");
      b.classList.add(!s.ok ? "bad" : mins > 150 ? "warn" : "ok");
    });
    document.querySelectorAll("[data-foot]").forEach(f => { f.innerHTML = S.footHTML(); });
  }
  // Picks cards are built only Wed 9pm, Thu 8pm, Fri 9pm and Sat 8am CT (picks/RUNBOOK.md), so a 30-hour rule turns
  // them amber every Tue/Wed. Instead: amber only when the latest slot passed 3+ hours ago and no card was built
  // since 2 hours before it (the same "fresh" window picks-backup.yml uses).
  S.PICK_SLOTS = { 3: [21], 4: [20], 5: [21], 6: [8] };        // CT weekday (0 = Sunday) -> slot hours
  const CTF = new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", hourCycle: "h23" });
  const ctParts = t => Object.fromEntries(CTF.formatToParts(new Date(t)).map(p => [p.type, p.value]));
  const ctWall = (y, mo, d, h) => {                              // UTC ms of a Central wall-clock time
    const guess = Date.UTC(y, mo - 1, d, h), p = ctParts(guess);
    return guess - (Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute) - guess);
  };
  S.picksStale = function (last, now = Date.now()) {
    const t = ctParts(now), made = last ? new Date(last).getTime() : NaN;
    for (let back = 0; back < 8; back++) {
      const c = new Date(Date.UTC(+t.year, +t.month - 1, +t.day - back));
      const hours = (S.PICK_SLOTS[c.getUTCDay()] || []).slice().sort((a, b) => b - a);
      for (const h of hours) {
        const slot = ctWall(c.getUTCFullYear(), c.getUTCMonth() + 1, c.getUTCDate(), h);
        if (slot + 3 * 3600000 <= now) return !(made >= slot - 2 * 3600000);
      }
    }
    return !(made > 0);
  };
  S.footHTML = function () {
    const s = S.data.status;
    if (!s) return "";
    const bits = [`Last run ${kick(s.last_run)}`, `Week ${s.week}`];
    if (s.next_kickoff) bits.push(`next kickoff ${kick(s.next_kickoff)}`);
    if (s.watch_active) bits.push("injury watch ON");
    const errs = (s.errors || []).map(e => `<div class="err">${esc(e)}</div>`).join("");
    const jobs = (s.jobs || []).map(j => {
      const stale = /^Picks cards/.test(j.job) ? S.picksStale(j.last) : !j.last || (Date.now() - new Date(j.last)) / 3600000 > 30;
      return `<span class="${stale ? "stale" : ""}">${esc(j.job.replace(/ \(laptop.*\)/, ""))}: ${j.last ? esc(ago(j.last)) : "not yet"}</span>`;
    }).join("");
    return `<div>${bits.join(" · ")}</div>${errs}<div class="jobs">${jobs}</div>`;
  };

  // ---------- drawer (detail over the layout) ----------
  S.drawer = {
    open(html, key) {
      let el = document.getElementById("drawer");
      if (!el) {
        el = document.createElement("div");
        el.id = "drawer";
        el.innerHTML = `<div class="scrim" data-close></div><aside class="panel" role="dialog" aria-modal="true"><button class="x" data-close aria-label="Close">✕</button><div class="body"></div></aside>`;
        document.body.appendChild(el);
        el.addEventListener("click", e => { if (e.target.closest("[data-close]")) S.drawer.close(); });
      }
      el.querySelector(".body").innerHTML = html;
      el.classList.add("on");
      document.documentElement.classList.add("noscroll");
      if (key && location.hash !== "#" + key) history.pushState({ drawer: key }, "", "#" + key);
      el.querySelector(".panel").scrollTop = 0;
    },
    close(fromPop) {
      const el = document.getElementById("drawer");
      if (!el?.classList.contains("on")) return;
      el.classList.remove("on");
      document.documentElement.classList.remove("noscroll");
      if (!fromPop && location.hash) history.back();
    },
    isOpen: () => !!document.getElementById("drawer")?.classList.contains("on"),
  };
  window.addEventListener("popstate", () => { if (!location.hash) S.drawer.close(true); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { S.drawer.close(); fbClose(); } });

  // ---------- theme ----------
  const applyTheme = t => { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; };
  applyTheme(S.get("theme"));
  S.themeButton = () => `<button class="pill icon" data-theme-toggle aria-label="Switch light or dark">◐</button>`;
  document.addEventListener("click", e => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const t = dark ? "light" : "dark";
    applyTheme(t); S.set("theme", t);
  });

  // ---------- layout menu: every layout has [data-picker] in its header; A (Scoreboard) is the main page ----------
  const LAYOUTS = S.LAYOUTS = [
    { id: "a", name: "Scoreboard", path: "", desc: "A tile per league: projected score, what needs fixing and the top move. Tap a tile for the full league." },
    { id: "b", name: "Command center", path: "lab/b/", desc: "One to-do list across every league and pool, most urgent first, with filters. Leagues in a side rail." },
    { id: "c", name: "Deck", path: "lab/c/", desc: "One full card per league. Swipe between them on a phone; side-by-side columns on a laptop." },
    { id: "d", name: "Game day", path: "lab/d/", desc: "What to do first, then your starters across all leagues by kickoff time, with a scoreboard alongside." },
  ];
  const view = () => document.body.dataset.view || "";
  function pickerFill() {
    const cur = LAYOUTS.find(l => l.id === view());
    document.querySelectorAll("[data-picker]").forEach(el => {
      el.innerHTML = `<button class="pill picker-btn" aria-haspopup="menu" aria-expanded="false" title="Switch layout"><span class="pk-ico" aria-hidden="true">▦</span>${esc(cur ? cur.name : "Layouts")}<span class="pk-car" aria-hidden="true">▾</span></button>`;
    });
  }
  function menuOpen(btn) {
    let m = document.getElementById("laymenu");
    if (!m) {
      m = document.createElement("div");
      m.id = "laymenu";
      m.setAttribute("role", "menu");
      m.innerHTML = `<div class="lm-h">Layout</div>` + LAYOUTS.map(l => `<a role="menuitemradio" aria-checked="${l.id === view()}" href="${esc(S.url(l.path))}">
          <span class="lm-letter">${l.id.toUpperCase()}</span><span class="lm-tx"><b>${esc(l.name)}</b>${l.id === "a" ? `<span class="lm-def">main page</span>` : ""}<span class="lm-d">${esc(l.desc)}</span></span>
          <span class="lm-tick" aria-hidden="true">${l.id === view() ? "✓" : ""}</span></a>`).join("")
        + `<div class="lm-f"><a href="${esc(S.url("players/"))}">Players</a><a href="${esc(S.url("war-room-v2/"))}">War Room</a><a href="${esc(S.url("wrapups/"))}">Wrap-up</a><a href="${esc(S.url("lab/"))}">Layouts lab</a></div>`;
      document.body.appendChild(m);
    }
    const r = btn.getBoundingClientRect(), w = Math.min(360, innerWidth - 24);
    m.style.width = w + "px";
    m.style.top = Math.round(r.bottom + 6) + "px";
    m.style.left = Math.round(Math.max(12, Math.min(r.left, innerWidth - w - 12))) + "px";
    m.classList.add("on");
    btn.setAttribute("aria-expanded", "true");
  }
  function menuClose() {
    document.getElementById("laymenu")?.classList.remove("on");
    document.querySelectorAll(".picker-btn").forEach(b => b.setAttribute("aria-expanded", "false"));
  }
  pickerFill();
  document.addEventListener("click", e => {
    const b = e.target.closest(".picker-btn");
    if (b) { document.getElementById("laymenu")?.classList.contains("on") ? menuClose() : menuOpen(b); return; }
    if (!e.target.closest("#laymenu")) menuClose();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") menuClose(); });
  addEventListener("resize", menuClose);

  // ---------- feedback: a prefilled GitHub issue; .github/workflows/feedback.yml logs it to FEEDBACK.md ----------
  const LAYOUT = () => document.body.dataset.layout || "current site";
  S.fbButtons = spot => `<span class="fb" data-spot="${esc(spot)}"><button data-fb="like" aria-label="Like this">👍</button><button data-fb="dislike" aria-label="Dislike this">👎</button></span>`;
  S.fbLink = (spot, label = "Feedback") => `<button class="pill" data-fb="idea" data-spot="${esc(spot)}">${esc(label)}</button>`;
  const MOODS = { like: "👍 Like", dislike: "👎 Dislike", idea: "💡 Idea / want" };
  let fb = { mood: "idea", spot: "" };
  function fbOpen(mood, spot) {
    fb = { mood, spot };
    let el = document.getElementById("fbsheet");
    if (!el) {
      el = document.createElement("div");
      el.id = "fbsheet";
      el.innerHTML = `<div class="scrim" data-fbclose></div><form class="sheet" autocomplete="off">
        <div class="sheet-h"><b>Feedback</b><button type="button" class="x" data-fbclose aria-label="Close">✕</button></div>
        <div class="fbspot"></div>
        <div class="moods">${Object.entries(MOODS).map(([k, v]) => `<button type="button" data-mood="${k}">${v}</button>`).join("")}</div>
        <textarea name="text" rows="4" placeholder="What do you like, dislike, or want changed? (optional)"></textarea>
        <button type="submit" class="send">Send via GitHub</button>
        <p class="fine">Opens GitHub with this filled in; tap <b>Create</b> there. It's logged in FEEDBACK.md within a minute and the next Claude session picks it up. The text is also copied, in case GitHub opens blank.</p>
      </form>`;
      document.body.appendChild(el);
      el.addEventListener("click", e => {
        if (e.target.closest("[data-fbclose]")) fbClose();
        const m = e.target.closest("[data-mood]");
        if (m) { fb.mood = m.dataset.mood; paintMood(); }
      });
      el.querySelector("form").addEventListener("submit", e => { e.preventDefault(); fbSend(el.querySelector("textarea").value.trim()); });
    }
    el.querySelector(".fbspot").textContent = `${LAYOUT()} · ${spot || "whole page"}`;
    el.querySelector("textarea").value = "";
    paintMood();
    el.classList.add("on");
    setTimeout(() => el.querySelector("textarea").focus({ preventScroll: true }), 50);
  }
  function paintMood() { document.querySelectorAll("#fbsheet [data-mood]").forEach(b => b.setAttribute("aria-pressed", b.dataset.mood === fb.mood)); }
  function fbClose() { document.getElementById("fbsheet")?.classList.remove("on"); }
  S.feedbackURL = function (mood, spot, text) {
    const theme = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const head = text ? text.replace(/\s+/g, " ").slice(0, 60) : "";
    const title = `Feedback: ${MOODS[mood]} · ${LAYOUT()} · ${spot || "whole page"}${head ? " · " + head : ""}`;
    const body = `${text || "(no comment)"}\n\n---\nMood: ${MOODS[mood]}\nLayout: ${LAYOUT()}\nSpot: ${spot || "whole page"}\nScreen: ${innerWidth}px, ${theme}\nPage: ${location.href.split("#")[0]}\n`;
    const q = new URLSearchParams({ title, body, labels: "feedback" });
    return { url: `https://github.com/${REPO}/issues/new?${q}`, title, body };
  };
  function fbSend(text) {
    const f = S.feedbackURL(fb.mood, fb.spot, text);
    try { navigator.clipboard?.writeText(`${f.title}\n\n${f.body}`).catch(() => {}); } catch {}
    openTab(f.url, "_blank", "noopener");
    fbClose();
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-fb]");
    if (!b) return;
    e.stopPropagation();
    e.preventDefault();
    const spot = b.dataset.spot || b.closest("[data-spot]")?.dataset.spot || "";
    fbOpen(b.dataset.fb, spot);
  }, true);
})();
