"use strict";
const TZ = "America/Chicago";
let data = { lineups: null, weekly: null, status: null, digest: null };
let tab = localGet("tab") || "today";
const tabNames = () => ["today", ...Object.keys(data.lineups?.leagues || {}), "weekly"];

function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch {} }
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function kick(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-US", { weekday: "short", timeZone: TZ });
  const t = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ }).replace(" AM", "a").replace(" PM", "p");
  return `${day} ${t}`;
}
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h ${m % 60}m ago` : `${Math.floor(h / 24)}d ago`;
}
function chip(f) {
  const cls = { OUT: "bad", IR: "bad", PUP: "bad", SUSP: "bad", NA: "bad", INACTIVE: "bad", EMPTY: "bad", "NO TEAM": "bad", D: "d", Q: "q", BYE: "bye" }[f] || "";
  return `<span class="chip ${cls}">${esc(f)}</span>`;
}

function row(p) {
  const sub = [p.team && p.opp ? `${p.team} ${p.opp}` : p.team, p.started ? "Locked" : kick(p.kickoff), p.why].filter(Boolean).join(" · ");
  const chips = p.flags?.length ? `<span class="chips">${p.flags.map(chip).join("")}</span>` : "";
  return `<div class="row${p.started ? " locked" : ""}">
    <div class="slot">${esc(p.slot === "SUPER_FLEX" ? "SF" : p.slot)}</div>
    <div class="who"><div class="name">${esc(p.name)}${chips}</div><div class="sub">${esc(sub)}</div></div>
    <div class="proj">${p.proj ? p.proj.toFixed(1) : ""}</div></div>`;
}

function lineup(name) {
  const lg = data.lineups?.leagues?.[name];
  if (!lg) return `<div class="card"><p class="note">No data yet.</p></div>`;
  if (lg.pending) return `<div class="card"><h2>${esc(name)}</h2><p class="note">${esc(lg.message)}<br><br>This tab fills in automatically.</p></div>`;
  const stale = lg.stale ? `<p class="note"><b>Showing last good data</b> — latest refresh failed.</p>` : "";
  const src = lg.roster_synced ? ` · roster read ${esc(kick(lg.roster_synced))}` : lg.snapshot ? ` · ESPN read ${esc(kick(lg.snapshot))}` : "";
  const opp = (lg.format === "guillotine" ? "Survive the week" : lg.opponent ? `vs ${esc(lg.opponent)}` : "No opponent listed") + src;
  const cats = lg.sport === "nba";
  const oppScore = lg.opp_proj != null ? ` <span class="opp">– ${lg.opp_proj.toFixed(1)}</span>` : "";
  return actions(lg) + `<div class="card">${stale}
    <div class="summary"><div><div class="name">${esc(name)} · Wk ${lg.week}</div><div class="vs">${opp}</div></div>
      <div class="score">${cats ? (lg.league || "") : (lg.proj ?? 0).toFixed(1) + oppScore}</div></div>
    <div class="section">Starters</div>${lg.starters.map(row).join("")}
    <div class="section">Bench</div>${lg.bench.length ? lg.bench.map(row).join("") : `<p class="note">Empty</p>`}
  </div>`;
}

function actions(lg) {
  const a = lg.advice;
  if (!a) return "";
  const list = (title, items, cls = "") => items?.length
    ? `<div class="section">${title}</div><ul class="tips ${cls}">${items.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : "";
  const fixes = a.fixes?.length ? list("Fix now", a.fixes, "fix")
    : `<div class="section">Fix now</div><ul class="tips"><li class="ok">Lineup is set, nothing to fix.</li></ul>`;
  return `<div class="card actions">
    <div class="summary"><div><div class="name">What to do</div>${a.matchup ? `<div class="vs ${a.danger ? "danger" : ""}">${esc(a.matchup)}</div>` : ""}</div>
      <div class="muted small">${esc(a.built)}</div></div>
    ${fixes}${list("Lineup moves", a.moves)}${list("Waiver adds", a.adds)}${trades(a.trades)}${list("Notes", a.notes, "muted")}
  </div>`;
}

function trades(t) {
  if (!t || !(t.offers?.length || t.lines?.length)) return "";
  const n = v => Number(v).toLocaleString("en-US");
  const offer = o => {
    const pct = Math.round((o.get_value - o.give_value) / Math.max(o.give_value, o.get_value) * 100);
    return `<li class="offer"><div><b>Give</b> ${esc(o.give.join(" + "))} <b>→ get</b> ${esc(o.get.join(" + "))}</div>
      <div class="sub-wrap">to ${esc(o.team)} · value ${n(o.give_value)} for ${n(o.get_value)} (${pct > 0 ? "+" : ""}${pct}%) ·
      your lineup <b class="gain">+${o.my_gain}/gm</b>, theirs +${o.their_gain}/gm</div>
      <div class="sub-wrap">${esc(o.why)}${o.cut ? ". You'd cut your worst bench player." : ""}</div></li>`;
  };
  const offers = t.offers?.length ? `<ul class="tips offers">${t.offers.map(offer).join("")}</ul>` : "";
  const lines = t.lines?.length ? `<ul class="tips muted">${t.lines.map(l => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  const basis = t.basis ? `<p class="basis">${esc(t.basis)}. Ideas only: nothing is sent.</p>` : "";
  return `<div class="section" id="trades">Trade ideas</div>${offers}${lines}${basis}`;
}

function today() {
  const d = data.digest;
  if (!d?.items) return `<div class="card"><p class="note">The daily check posts at 8am CT.</p></div>`;
  const items = d.items.length ? d.items : [{ league: "All leagues", text: "Every lineup looks set.", urgent: false }];
  const groups = {};
  items.forEach(i => (groups[i.league] = groups[i.league] || []).push(i));
  return `<p class="muted" style="margin:0 0 10px">${esc(d.title)} · ${esc(kick(d.generated))}</p>` +
    Object.entries(groups).map(([lg, list]) => `<div class="card"><h2>${esc(lg)}</h2><ul class="tips">${
      list.map(i => `<li>${i.urgent ? "<b>⚠ " + esc(i.text) + "</b>" : esc(i.text)}</li>`).join("")}</ul></div>`).join("");
}

function weekly() {
  const w = data.weekly;
  if (!w?.leagues?.length) return `<div class="card"><p class="note">The weekly plan posts Tuesdays at 7am CT.</p></div>`;
  const pending = data.lineups?.leagues?.Kosmonauts?.pending && !w.leagues.some(l => l.name === "Kosmonauts")
    ? `<div class="card"><h2>Kosmonauts</h2><p class="note">Waiting on Yahoo API approval.</p></div>` : "";
  return `<p class="muted" style="margin:0 0 10px">Week ${w.week} · generated ${esc(kick(w.generated))}</p>` +
    w.leagues.map(l => `<div class="card"><h2>${esc(l.name)}</h2>
      <div class="section" style="border:0">Start / sit</div><ul class="tips">${l.start_sit.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      <div class="section">Top FA adds</div><ul class="tips">${l.adds.map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>`).join("") + pending;
}

function footer() {
  const s = data.status;
  if (!s) return "";
  const btn = document.getElementById("refresh");
  const mins = (Date.now() - new Date(s.last_run)) / 60000;
  btn.textContent = `↻ ${ago(s.last_run)}`;
  btn.title = `Last run ${kick(s.last_run)} · tap to reload`;
  btn.className = "pill " + (!s.ok ? "bad" : mins > 150 ? "warn" : "ok");
  const bits = [`Last run ${kick(s.last_run)}`, `Week ${s.week}`];
  if (s.next_kickoff) bits.push(`next kickoff ${kick(s.next_kickoff)}`);
  if (s.watch_active) bits.push("injury watch ON");
  const errs = (s.errors || []).map(e => `<div class="err">${esc(e)}</div>`).join("");
  const jobs = (s.jobs || []).map(j => {
    const age = j.last ? (Date.now() - new Date(j.last)) / 3600000 : null;
    return `<div class="${age === null || age > 30 ? "stale" : ""}">${esc(j.job)}: ${j.last ? esc(ago(j.last)) : "not yet"}</div>`;
  }).join("");
  return `<div>${bits.join(" · ")}</div>${errs}<div class="jobs">${jobs}</div>`;
}

function renderTabs() {
  const names = tabNames();
  if (!names.includes(tab)) tab = names[0];
  document.getElementById("tabs").innerHTML = names.map(n =>
    `<button role="tab" data-tab="${esc(n)}">${esc(n === "weekly" ? "Weekly" : n === "today" ? "Today" : n)}</button>`).join("");
}

function render() {
  renderTabs();
  document.querySelectorAll("nav button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab));
  document.getElementById("main").innerHTML = tab === "weekly" ? weekly() : tab === "today" ? today() : lineup(tab);
  document.getElementById("foot").innerHTML = footer();
}

async function load() {
  const t = Date.now();
  const get = f => fetch(`data/${f}.json?t=${t}`, { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null);
  const [lineups, weekly, status, digest] = await Promise.all([get("lineups"), get("weekly"), get("status"), get("digest")]);
  data = { lineups: lineups || data.lineups, weekly: weekly || data.weekly, status: status || data.status, digest: digest || data.digest };
  render();
}

document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest("button[data-tab]");
  if (b) { tab = b.dataset.tab; localSet("tab", tab); render(); }
});
document.getElementById("refresh").addEventListener("click", load);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
load();
setInterval(load, 5 * 60 * 1000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
