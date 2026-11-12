// Picks page: "What changed this week" (every posted card version side by side, per pool) and line movement charts.
// Data: changes.json (pp.history, rebuilt with every card) and ../data/pick_line_history/<season>-wNN.json
// (pp.lines appends each stale-line scan, Wed-Sat). Inline SVG only. Loaded by pp.cards.render (one <script> tag).
(function () {
  "use strict";
  var POOL = { bto: "BTO", cfp: "CFP", yahoo: "Yahoo", survivor: "Survivor" };
  var CSS = [
    ":root{--ch-mkt:#2a78d6;--ch-pool:#eb6834;--ch-grid:#e6e6e3;--ch-chip:#f2f4f3}",
    "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ch-mkt:#3987e5;--ch-pool:#d95926;--ch-grid:#2c2c2a;--ch-chip:#1f2221}}",
    ":root[data-theme=dark]{--ch-mkt:#3987e5;--ch-pool:#d95926;--ch-grid:#2c2c2a;--ch-chip:#1f2221}",
    "#chg h2{margin-bottom:4px}.ch-top{margin:2px 0 6px}.ch-top a{font-weight:600}",
    ".ch-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}",
    ".ch-tab{font:inherit;font-size:12px;padding:5px 10px;border-radius:14px;border:1px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer;min-height:30px}",
    ".ch-tab[aria-selected=true]{background:var(--fg);color:var(--bg);border-color:var(--fg);font-weight:700}",
    ".ch-wk{font:inherit;font-size:12px;padding:4px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px}",
    ".ch-tl{display:flex;gap:4px;overflow-x:auto;padding:2px 0 6px;margin:0;list-style:none}",
    ".ch-tl li{flex:0 0 auto;background:var(--ch-chip);border-radius:6px;padding:4px 7px;font-size:11px;line-height:1.3;margin:0}",
    ".ch-tl li b{display:block;font-size:11.5px}.ch-tl li.on{outline:2px solid var(--red)}",
    ".ch-log{margin:4px 0 8px;font-size:12px}.ch-log b{font-size:12px}.ch-log ul{margin:2px 0 6px}",
    ".ch-gs{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px 14px;margin-top:6px}",
    ".ch-g{border-top:1px solid var(--line);padding-top:6px;min-width:0}.ch-g h3{font-size:13px;margin:0 0 2px}",
    ".ch-w{overflow-x:auto}.ch-t{table-layout:auto;width:auto;min-width:100%}",
    ".ch-t th,.ch-t td{width:auto!important;padding:3px 6px 3px 0;white-space:nowrap;font-size:11.5px}",
    ".ch-t th{font-weight:600}.ch-t td:first-child{color:var(--mut);font-size:10.5px}",
    ".ch-t td.chg{background:var(--chg);color:var(--red);font-weight:700}.ch-t td.na{color:var(--mut)}",
    ".ch-c{display:block;width:100%;max-width:420px;height:auto;margin:2px 0;touch-action:pan-y}",
    ".ch-cap{font-size:11px;color:var(--mut);min-height:15px}",
    ".ch-key{font-size:11px;color:var(--mut);margin:4px 0}.ch-key i{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin:0 3px 0 6px}",
    ".ch-sp{display:block;margin-top:2px}.ch-sp svg{vertical-align:middle}.ch-sp span{font-size:10.5px;color:var(--mut);margin-left:3px}",
    ".ch-more{font:inherit;font-size:12px;margin:8px 0;padding:5px 10px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--acc);cursor:pointer}"
  ].join("");

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } }
  function fmt(v) { return v == null ? "—" : v === 0 ? "PK" : (v > 0 ? "+" : "") + v; }
  function pct(p) { return p == null ? "—" : Math.round(p * 100) + "%"; }
  function ts(iso) { var t = Date.parse(iso); return isNaN(t) ? null : t; }
  function when(t) { return new Date(t).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }); }
  function norm(g) { return String(g || "").replace(/[▸★]/g, "").replace(/\s+/g, " ").trim(); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  var H = null, LINES = {}, state = { week: null, pool: get("ch-pool") || "bto", all: false };

  // ---- line series ----
  function teamSide(g, team) { return team && g && team === g.away ? -1 : 1; }  // stored as the home team's spread
  function series(g, sign, pid) {
    var m = (g.market || []).map(function (p) { return [ts(p[0]), sign * p[1]]; });
    var pools = g.pools || {};
    var pl = pid && pools[pid] ? pools[pid] : null;  // Yahoo is straight-up: no pool line
    return { market: m, pool: (pl || []).map(function (p) { return [ts(p[0]), sign * p[1]]; }),
             open: g.open == null ? null : sign * g.open, seen: ts(g.seen) };
  }
  function at(pts, t) { var v = null; for (var i = 0; i < pts.length; i++) { if (pts[i][0] <= t) v = pts[i][1]; } return v; }
  function moved(s) { return s.market.length > 1 || (s.open != null && s.market.length && s.open !== s.market[s.market.length - 1][1]); }

  function stepPath(pts, x, y, tEnd) {
    if (!pts.length) return "";
    var d = "M" + x(pts[0][0]).toFixed(1) + " " + y(pts[0][1]).toFixed(1);
    for (var i = 1; i < pts.length; i++) d += "H" + x(pts[i][0]).toFixed(1) + "V" + y(pts[i][1]).toFixed(1);
    return d + "H" + x(Math.max(tEnd, pts[pts.length - 1][0])).toFixed(1);
  }

  // big = history view chart (axes, version ticks, hover); else the card's sparkline
  function chart(s, opt) {
    var big = opt.big, W = big ? 320 : 76, Hh = big ? 118 : 22;
    var L = big ? 30 : 2, R = big ? 44 : 2, T = big ? 14 : 3, B = big ? 16 : 3;
    var times = s.market.concat(s.pool).map(function (p) { return p[0]; }).filter(Boolean);
    if (!times.length) return null;
    var vt = (opt.versions || []).map(function (v) { return ts(v.posted); }).filter(Boolean);
    // the span the lines were watched; card versions outside it get no tick
    var t0 = Math.min.apply(null, times);
    var t1 = Math.max.apply(null, times.concat(s.seen ? [s.seen] : []));
    if (t1 - t0 < 36e5) t1 = t0 + 36e5;
    var vals = s.market.concat(s.pool).map(function (p) { return p[1]; }).concat(s.open == null ? [] : [s.open]);
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi - lo < 1) { lo -= (1 - (hi - lo)) / 2; hi = lo + 1; }
    lo -= 0.25; hi += 0.25;
    var x = function (t) { return L + (t - t0) / (t1 - t0) * (W - L - R); };
    var y = function (v) { return T + (hi - v) / (hi - lo) * (Hh - T - B); };  // higher spread (more points) on top
    var o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + " " + Hh + '" width="' + (big ? "100%" : W) + '"' +
             (big ? ' class="ch-c"' : ' height="' + Hh + '"') + ' role="img" aria-label="' + esc(opt.aria) + '">'];
    if (big) {
      [lo + 0.25, hi - 0.25].forEach(function (v) {
        var r = Math.round(v * 2) / 2;
        o.push('<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(r).toFixed(1) + '" y2="' + y(r).toFixed(1) + '" stroke="var(--ch-grid)" stroke-width="1"/>');
        o.push('<text x="' + (L - 4) + '" y="' + (y(r) + 3.5).toFixed(1) + '" text-anchor="end" font-size="9" fill="var(--mut)">' + esc(fmt(r)) + "</text>");
      });
      var d = new Date(t0); d.setHours(24, 0, 0, 0);
      for (; d.getTime() < t1; d.setDate(d.getDate() + 1)) {
        var xd = x(d.getTime()).toFixed(1);
        o.push('<line x1="' + xd + '" x2="' + xd + '" y1="' + T + '" y2="' + (Hh - B) + '" stroke="var(--ch-grid)" stroke-width="1"/>');
        o.push('<text x="' + xd + '" y="' + (Hh - 4) + '" text-anchor="middle" font-size="9" fill="var(--mut)">' +
               esc(d.toLocaleDateString([], { weekday: "short" })) + "</text>");
      }
      vt.forEach(function (t, i) {
        if (t < t0 || t > t1) return;
        var xv = x(t).toFixed(1), st = (opt.versions[i].stage || "?").charAt(0).toUpperCase();
        o.push('<line x1="' + xv + '" x2="' + xv + '" y1="' + (T - 2) + '" y2="' + (Hh - B) + '" stroke="var(--mut)" stroke-width="1" stroke-dasharray="1 2"/>');
        o.push('<text x="' + xv + '" y="9" text-anchor="middle" font-size="8.5" fill="var(--mut)">' + esc(st) + "</text>");
      });
    }
    if (s.pool.length) o.push('<path d="' + stepPath(s.pool, x, y, t1) + '" fill="none" stroke="var(--ch-pool)" stroke-width="2" stroke-dasharray="4 3" stroke-linecap="round"/>');
    if (s.market.length) o.push('<path d="' + stepPath(s.market, x, y, t1) + '" fill="none" stroke="var(--ch-mkt)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');
    if (s.open != null) o.push('<circle cx="' + x(t0).toFixed(1) + '" cy="' + y(s.open).toFixed(1) + '" r="' + (big ? 4 : 2.5) + '" fill="var(--bg)" stroke="var(--ch-mkt)" stroke-width="1.5"/>');
    if (big) {
      var lm = s.market.length ? s.market[s.market.length - 1][1] : null, lp = s.pool.length ? s.pool[s.pool.length - 1][1] : null;
      var ym = lm == null ? null : y(lm), yp = lp == null ? null : y(lp);
      if (ym != null && yp != null && Math.abs(ym - yp) < 10) { if (ym <= yp) { ym -= 5; yp += 5; } else { ym += 5; yp -= 5; } }
      if (ym != null) o.push('<text x="' + (W - R + 4) + '" y="' + (ym + 3.5).toFixed(1) + '" font-size="9.5" font-weight="700" fill="var(--fg)">mkt ' + esc(fmt(lm)) + "</text>");
      if (yp != null) o.push('<text x="' + (W - R + 4) + '" y="' + (yp + 3.5).toFixed(1) + '" font-size="9.5" fill="var(--mut)">pool ' + esc(fmt(lp)) + "</text>");
      o.push('<line class="ch-x" x1="0" x2="0" y1="' + T + '" y2="' + (Hh - B) + '" stroke="var(--fg)" stroke-width="1" visibility="hidden"/>');
      o.push('<rect x="' + L + '" y="0" width="' + (W - L - R) + '" height="' + Hh + '" fill="transparent"/>');
    }
    o.push("</svg>");
    return { svg: o.join(""), x0: L, x1: W - R, W: W, t: function (px) { return t0 + (px - L) / (W - L - R) * (t1 - t0); }, x: x };
  }

  function summary(s) {
    if (!s.market.length) return "";
    var a = s.market[0][1], b = s.market[s.market.length - 1][1];
    return "Market " + (a === b ? fmt(b) + ", no move" : fmt(a) + " → " + fmt(b)) + " since " + when(s.market[0][0]) +
           (s.open != null ? " (opened " + fmt(s.open) + ")" : "") + (s.pool.length ? "; pool " + fmt(s.pool[s.pool.length - 1][1]) : "");
  }

  function bigChart(host, s, versions, label) {
    var c = chart(s, { big: true, versions: versions, aria: label + ": " + summary(s) });
    if (!c) return;
    var box = el("div"); box.innerHTML = c.svg; host.appendChild(box);
    var cap = el("div", "ch-cap", summary(s)); host.appendChild(cap);
    var svg = box.firstChild, xl = svg.querySelector(".ch-x");
    function move(ev) {
      var r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) / r.width * c.W;
      if (px < c.x0 || px > c.x1) return;
      var t = c.t(px), m = at(s.market, t), p = at(s.pool, t);
      xl.setAttribute("x1", px); xl.setAttribute("x2", px); xl.setAttribute("visibility", "visible");
      cap.textContent = when(t) + " · market " + fmt(m) + (s.pool.length ? " · pool " + fmt(p) : "");
    }
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", function () { xl.setAttribute("visibility", "hidden"); cap.textContent = summary(s); });
  }

  // ---- history view ----
  function weekData() { for (var i = 0; i < H.weeks.length; i++) if (H.weeks[i].week === state.week) return H.weeks[i]; return H.weeks[0]; }
  function linesFor(week) {
    if (LINES[week]) return Promise.resolve(LINES[week]);
    return fetch("../data/pick_line_history/" + (H.season || 2026) + "-w" + pad(week) + ".json?t=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : { games: {} }; })
      .catch(function () { return { games: {} }; })
      .then(function (d) { LINES[week] = d || { games: {} }; return LINES[week]; });
  }
  function shortLabel(v) { var m = /^(\w+ [\d:]+ [AP]M) (.*)$/.exec(v.label || ""); return m ? [m[1], m[2]] : [v.label || "", ""]; }
  function changedKeys(chs) { var o = {}; (chs || []).forEach(function (c) { if (c.key) o[c.key] = c.fields; }); return o; }

  function gameTable(pool, row, wk) {
    var ats = pool.id === "bto" || pool.id === "cfp";
    var marks = pool.changes.map(changedKeys);
    var cells = row.cells, lines = LINES[wk.week] || { games: {} };
    var name = (cells.filter(Boolean)[0] || {}).game || row.key;
    var g = lines.games[name], last = cells.filter(Boolean).slice(-1)[0] || {};
    var spec = [["Pick", "pick", function (c) { return c.team || c.pick; }]];
    if (ats) spec.push(["Line", "line", function (c) { return c.line || "—"; }]);
    if (ats) spec.push(["Market", "mkt", function (c, i) {
      if (c.mkt != null) return fmt(c.mkt);
      if (!g) return "—";
      var v = at(series(g, teamSide(g, c.team), pool.id).market, ts(wk.versions[pool.cols[i]].posted));
      return v == null ? "—" : fmt(v);
    }]);
    spec.push([ats ? "Cover %" : "Win %", "p", function (c) { return pct(c.p); }]);
    if (!ats) spec.push(["Market win", "pm", function (c) { return pct(c.pm); }]);
    if (ats) spec.push(["Wager", "wager", function (c) { return c.wager || "—"; }]);
    // room for public betting / pick % once a source is chosen: cells carrying "pub" get their own row
    if (cells.some(function (c) { return c && c.pub != null; })) spec.push(["Public %", "pub", function (c) { return c.pub == null ? "—" : pct(c.pub); }]);
    var h = ['<div class="ch-w"><table class="ch-t"><thead><tr><th></th>'];
    pool.cols.forEach(function (vi) { var l = shortLabel(wk.versions[vi]); h.push("<th>" + esc(l[0]) + "<br><span class='mk'>" + esc(l[1]) + "</span></th>"); });
    h.push("</tr></thead><tbody>");
    spec.forEach(function (sp) {
      h.push("<tr><td>" + esc(sp[0]) + "</td>");
      cells.forEach(function (c, i) {
        if (!c) { h.push("<td class='na'>" + (i && cells[i - 1] ? "dropped" : "—") + "</td>"); return; }
        var f = marks[i][row.key] || [], hit = i > 0 && (f.indexOf(sp[1]) >= 0 || f.indexOf("added") >= 0 ||
                 (sp[1] === "line" && f.indexOf("pick") >= 0));
        h.push("<td" + (hit ? " class='chg'" : "") + ">" + esc(sp[2](c, i)) + "</td>");
      });
      h.push("</tr>");
    });
    h.push("</tbody></table></div>");
    var box = el("div", "ch-g");
    box.appendChild(el("h3", null, name));
    if (g) { var s = series(g, teamSide(g, last.team), pool.id); if (s.market.length || s.pool.length) bigChart(box, s, wk.versions, name); }
    var t = el("div"); t.innerHTML = h.join(""); box.appendChild(t);
    return box;
  }

  function renderPool(body, wk, pool) {
    body.innerHTML = "";
    var tl = el("ol", "ch-tl");
    pool.cols.forEach(function (vi, i) {
      var n = i ? pool.changes[i].length : 0, li = el("li", n ? "on" : "");
      li.appendChild(el("b", null, wk.versions[vi].label));
      li.appendChild(document.createTextNode(i === 0 ? "first card" : n ? n + (n === 1 ? " change" : " changes") : "no change"));
      tl.appendChild(li);
    });
    body.appendChild(tl);
    if (pool.hidden) body.appendChild(el("p", "meta", pool.hidden + " other build" + (pool.hidden === 1 ? "" : "s") + " made no change to this pool (hidden)."));
    var any = false;
    pool.cols.forEach(function (vi, i) {
      if (!i || !pool.changes[i].length) return;
      any = true;
      var d = el("div", "ch-log"), ul = el("ul");
      d.appendChild(el("b", null, wk.versions[vi].label));
      pool.changes[i].forEach(function (c) { ul.appendChild(el("li", null, c.text)); });
      d.appendChild(ul); body.appendChild(d);
    });
    if (!any) body.appendChild(el("p", "meta", pool.cols.length > 1 ? "No changes to this pool since the first card." :
      "Only one card so far (" + wk.versions[pool.cols[0]].label + "). Later versions show here side by side, changes in red."));
    if (pool.id === "survivor") {
      var ul2 = el("ul");
      pool.cols.forEach(function (vi, i) { ul2.appendChild(el("li", null, wk.versions[vi].label + ": " + (pool.status[i] || "no picks"))); });
      body.appendChild(ul2);
      return;
    }
    var rows = pool.rows.filter(function (r) { return !(r.cells.filter(Boolean)[0] || {}).tb; });
    var tbs = pool.rows.filter(function (r) { return (r.cells.filter(Boolean)[0] || {}).tb; });
    var touched = {};
    pool.changes.forEach(function (chs, i) { if (i) chs.forEach(function (c) { touched[c.key] = 1; }); });
    var show = rows;
    if (pool.id === "yahoo" && !state.all) show = rows.filter(function (r) { return touched[r.key]; });
    var gs = el("div", "ch-gs");
    show.forEach(function (r) { gs.appendChild(gameTable(pool, r, wk)); });
    body.appendChild(gs);
    if (show.length < rows.length) {
      var b = el("button", "ch-more", (show.length ? "Show the other " + (rows.length - show.length) : "Show all " + rows.length) + " games (no change)");
      b.type = "button";
      b.onclick = function () { state.all = true; renderPool(body, wk, pool); };
      body.appendChild(b);
    }
    if (tbs.length) {
      var h = ['<h3 style="font-size:13px;margin:10px 0 2px">Tiebreakers</h3><div class="ch-w"><table class="ch-t"><thead><tr><th></th>'];
      var marks = pool.changes.map(changedKeys);
      pool.cols.forEach(function (vi) { var l = shortLabel(wk.versions[vi]); h.push("<th>" + esc(l[0]) + "<br><span class='mk'>" + esc(l[1]) + "</span></th>"); });
      h.push("</tr></thead><tbody>");
      tbs.forEach(function (r) {
        h.push("<tr><td>" + esc(r.key) + "</td>");
        r.cells.forEach(function (c, i) { h.push("<td" + (i && marks[i][r.key] ? " class='chg'" : "") + ">" + esc(c ? c.pick : "—") + "</td>"); });
        h.push("</tr>");
      });
      h.push("</tbody></table></div>");
      var t = el("div"); t.innerHTML = h.join(""); body.appendChild(t);
    }
  }

  function render(sec) {
    var wk = weekData(), bar = sec.querySelector(".ch-bar"), body = sec.querySelector(".ch-body");
    bar.innerHTML = "";
    var pools = wk.pools;
    if (!pools.some(function (p) { return p.id === state.pool; })) state.pool = pools.length ? pools[0].id : "bto";
    pools.forEach(function (p) {
      var n = p.changes.reduce(function (a, c, i) { return a + (i ? c.length : 0); }, 0);
      var b = el("button", "ch-tab", (POOL[p.id] || p.id) + (n ? " · " + n : ""));
      b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", p.id === state.pool ? "true" : "false");
      b.onclick = function () { state.pool = p.id; state.all = false; put("ch-pool", p.id); render(sec); };
      bar.appendChild(b);
    });
    if (H.weeks.length > 1) {
      var s = el("select", "ch-wk"); s.setAttribute("aria-label", "Week");
      H.weeks.forEach(function (w) { var o = el("option", null, "Week " + w.week + (w.label ? " (" + w.label.replace(/^Week of /, "").replace(/, \d{4}$/, "") + ")" : "")); o.value = w.week; if (w.week === wk.week) o.selected = true; s.appendChild(o); });
      s.onchange = function () { state.week = +s.value; state.all = false; linesFor(state.week).then(function () { render(sec); }); };
      bar.appendChild(s);
    }
    var pool = pools.filter(function (p) { return p.id === state.pool; })[0];
    if (pool) renderPool(body, wk, pool); else body.textContent = "No cards this week yet.";
  }

  // ---- card sparklines ----
  function sparklines(wk, lines) {
    var titles = {};
    wk.pools.forEach(function (p) { titles[p.title] = p; });
    var secs = document.querySelectorAll("section");
    for (var i = 0; i < secs.length; i++) {
      var h2 = secs[i].querySelector("h2"), pool = h2 && titles[h2.textContent.trim()];
      if (!pool || pool.id === "survivor") continue;
      var teams = {};
      pool.rows.forEach(function (r) { var c = r.cells[r.cells.length - 1] || r.cells.filter(Boolean).slice(-1)[0]; if (c) teams[c.game] = c.team; });
      var trs = secs[i].querySelectorAll("table > tbody > tr");
      for (var j = 0; j < trs.length; j++) {
        var tds = trs[j].children;
        if (tds.length < 2 || trs[j].classList.contains("bdr")) continue;
        var name = norm(tds[0].textContent), g = lines.games[name];
        if (!g) continue;
        var s = series(g, teamSide(g, teams[name]), pool.id);
        if (!s.market.length || (pool.id === "yahoo" && !moved(s))) continue;
        var c = chart(s, { aria: summary(s) });
        if (!c) continue;
        var a = s.market[0][1], b = s.market[s.market.length - 1][1];
        var sp = el("span", "ch-sp"); sp.title = summary(s);
        sp.innerHTML = c.svg + "<span>mkt " + esc(a === b ? fmt(b) : fmt(a) + "→" + fmt(b)) + "</span>";
        tds[1].appendChild(sp);
      }
    }
  }

  function init(d) {
    H = d;
    if (!H || !H.weeks || !H.weeks.length) return;
    var st = el("style"); st.textContent = CSS; document.head.appendChild(st);
    var wk = H.weeks[0];
    state.week = wk.week;
    var sec = el("section"); sec.id = "chg";
    sec.appendChild(el("h2", null, "What changed this week"));
    sec.appendChild(el("p", "meta", "Every posted card this week, oldest to newest. Red = changed from the version before. " +
      "Charts: market spread (blue, DraftKings via ESPN, checked every 2h Wed-Sat) and pool line (orange dashed), from the picked team's side; " +
      "D/F/R marks when each draft/final/refresh posted; hollow dot = opening line. Tap a chart for the line at that time."));
    var key = el("p", "ch-key"); key.innerHTML = '<i style="color:var(--ch-mkt)"></i>market <i style="color:var(--ch-pool);border-top-style:dashed"></i>pool line';
    sec.appendChild(key);
    sec.appendChild(el("div", "ch-bar"));
    sec.appendChild(el("div", "ch-body"));
    var anchor = document.getElementById("gaps") || document.getElementById("allg");
    if (anchor) anchor.parentNode.insertBefore(sec, anchor); else document.body.appendChild(sec);
    // one line near the top: how much changed, with a jump link
    var n = 0;
    wk.pools.forEach(function (p) { p.changes.forEach(function (c, i) { if (i) n += c.length; }); });
    var v = wk.versions, top = el("p", "meta ch-top"), a = el("a");
    a.href = "#chg";
    a.textContent = v.length > 1 ? "What changed this week: " + n + " change" + (n === 1 ? "" : "s") + " across " + v.length + " versions (" +
      v[0].label + " → " + v[v.length - 1].label + ")" : "What changed this week: first card (" + v[0].label + "); line charts below";
    top.appendChild(a);
    var ck = document.querySelector("p.ck") || document.querySelector("h1");
    if (ck && ck.parentNode) ck.parentNode.insertBefore(top, ck.nextSibling);
    render(sec);
    linesFor(wk.week).then(function (lines) { render(sec); sparklines(wk, lines); });
  }

  fetch("changes.json?t=" + Date.now()).then(function (r) { return r.json(); }).then(init).catch(function () { /* page works without it */ });
})();
