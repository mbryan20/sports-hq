"use strict";
const TZ = "America/Chicago";
const TABS = ["Kosmonauts", "Domo Arigato", "weekly"];
let data = { lineups: null, weekly: null, status: null };
let tab = localGet("tab") || TABS[0];

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
    <div class="proj">${p.proj?.toFixed ? p.proj.toFixed(1) : ""}</div></div>`;
}

function lineup(name) {
  const lg = data.lineups?.leagues?.[name];
  if (!lg) return `<div class="card"><p class="note">No data yet.</p></div>`;
  if (lg.pending) return `<div class="card"><h2>${esc(name)}</h2><p class="note"><b>Yahoo access pending.</b><br>${esc(lg.message)}<br><br>This tab fills in automatically once Yahoo approves the app.</p></div>`;
  const stale = lg.stale ? `<p class="note"><b>Showing last good data</b> — latest refresh failed.</p>` : "";
  const opp = lg.roster_synced ? `Roster synced ${esc(kick(lg.roster_synced))} (Yahoo API pending)`
    : lg.opponent ? `vs ${esc(lg.opponent)}` : "No opponent found";
  const oppScore = lg.opp_proj != null ? ` <span class="opp">– ${lg.opp_proj.toFixed(1)}</span>` : "";
  return `<div class="card">${stale}
    <div class="summary"><div><div class="name">${esc(name)} · Wk ${lg.week}</div><div class="vs">${opp}</div></div>
      <div class="score">${(lg.proj ?? 0).toFixed(1)}${oppScore}</div></div>
    <div class="section">Starters</div>${lg.starters.map(row).join("")}
    <div class="section">Bench</div>${lg.bench.length ? lg.bench.map(row).join("") : `<p class="note">Empty</p>`}
  </div>`;
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
  btn.textContent = `Last run ${ago(s.last_run)}`;
  btn.className = "pill " + (!s.ok ? "bad" : mins > 150 ? "warn" : "ok");
  const bits = [`Last run ${kick(s.last_run)}`, `Week ${s.week}`];
  if (s.next_kickoff) bits.push(`next kickoff ${kick(s.next_kickoff)}`);
  if (s.watch_active) bits.push("injury watch ON");
  const errs = (s.errors || []).map(e => `<div class="err">${esc(e)}</div>`).join("");
  return `<div>${bits.join(" · ")}</div>${errs}`;
}

function render() {
  document.querySelectorAll("nav button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab));
  document.getElementById("main").innerHTML = tab === "weekly" ? weekly() : lineup(tab);
  document.getElementById("foot").innerHTML = footer();
}

async function load() {
  const t = Date.now();
  const get = f => fetch(`data/${f}.json?t=${t}`, { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null);
  const [lineups, weekly, status] = await Promise.all([get("lineups"), get("weekly"), get("status")]);
  data = { lineups: lineups || data.lineups, weekly: weekly || data.weekly, status: status || data.status };
  render();
}

document.querySelectorAll("nav button").forEach(b => b.addEventListener("click", () => { tab = b.dataset.tab; localSet("tab", tab); render(); }));
document.getElementById("refresh").addEventListener("click", load);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
if (!TABS.includes(tab)) tab = TABS[0];
load();
setInterval(load, 5 * 60 * 1000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
