// Ask Claude, two ways (Nov 14). Michael: "interact with claude directly when I am allowed to (i.e., on my personal
// computer) or, when on my work computer via github".
// - At work: a prefilled GitHub issue (label "ask"); .github/workflows/ask.yml answers it in a few minutes and the answer
//   shows under the box (docs/data/asks.json). PUBLIC: anyone can read GitHub issues.
// - At home: a new PRIVATE claude.ai chat with the question and this page's context filled in (claude.ai/new?q=, Anthropic's
//   documented prefill link); he taps send. claude.ai is blocked at work. The answer stays in that chat, not on the site.
// Used by pages without the Try-a-move box (Pool Picks, What's new). docs/lib/move.js has the same two buttons.
//   SHQASK.mount(el, {topic: "Pool Picks", context: () => "lines about what's on screen", placeholder: "..."})
(function () {
  const A = window.SHQASK = window.SHQASK || {};
  const REPO = "mbryan20/sports-hq", SITE = "https://mbryan20.github.io/sports-hq/";
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // the private chat starts with no memory of Sports HQ, so the prompt says where the public data is
  A.homeUrl = function (q, ctx) {
    const text = `Sports HQ question (private chat, from my personal computer).\n\n${q}\n\n---\n${ctx || ""}\n`
      + `Page: ${location.href.split("#")[0]}\nSports HQ is my public site ${SITE}; its data files are under ${SITE}data/ `
      + `(lineups.json, players_nfl.json, players.json, digest.json) and the pool picks are at ${SITE}picks/. Read what you need from there. `
      + `If you can read my Google Drive, my fantasy rules are in Claude Home > claude-audit > fantasy-rules.md: follow them. `
      + `Answer in plain English, short, with your reasoning, and say what you couldn't confirm.`;
    return "https://claude.ai/new?" + new URLSearchParams({ q: text.slice(0, 12000) });
  };
  A.workUrl = function (topic, q, ctx) {
    const body = `${q}\n\n---\nLeague: ${topic}\n${ctx || ""}Page: ${location.href.split("#")[0]}\n`;
    return `https://github.com/${REPO}/issues/new?` + new URLSearchParams({ title: `Ask: ${topic}: ${q.replace(/\s+/g, " ").slice(0, 70)}`, body, labels: "ask" });
  };
  A.PUBLIC_NOTE = "<b>At work (GitHub):</b> anyone can read GitHub questions, screenshots and answers, so sports only. Tap <b>Create</b> on the GitHub page; "
    + "screenshots: paste or drag them into GitHub's text box first. The answer shows here in a few minutes. "
    + "<b>At home (private):</b> opens a new claude.ai chat with your question and this page filled in; tap send. Only you see it; the answer stays in that chat (claude.ai is blocked at work).";
  const CSS = `.ska{display:grid;gap:6px;border:1px solid var(--line,#ccd);border-radius:8px;padding:10px;margin:12px 0}
.ska label{font-weight:650}.ska textarea{font:inherit;width:100%;padding:6px;border-radius:6px;border:1px solid var(--line,#ccd);background:transparent;color:inherit}
.ska .row{display:flex;flex-wrap:wrap;gap:6px}.ska button{font:inherit;font-weight:600;padding:6px 12px;border-radius:6px;border:1px solid var(--line,#ccd);background:transparent;color:inherit;cursor:pointer;min-height:36px}
.ska button.home{border-color:var(--acc,#0b5)}.ska .fine{font-size:11.5px;color:var(--mut,var(--muted,#667))}
.ska details{border:1px solid var(--line,#ccd);border-radius:6px;padding:4px 8px}.ska summary{font-weight:600;cursor:pointer}.ska .a{white-space:pre-wrap}`;
  A.mount = function (el, o) {
    if (!el) return;
    if (!document.getElementById("ska-css")) { const s = document.createElement("style"); s.id = "ska-css"; s.textContent = CSS; document.head.appendChild(s); }
    const id = "skq-" + Math.random().toString(36).slice(2, 8);
    el.innerHTML = `<div class="ska"><label for="${id}">Ask Claude about ${esc(o.topic)}</label>
      <textarea id="${id}" rows="2" placeholder="${esc(o.placeholder || "e.g. Why did we switch this pick?")}"></textarea>
      <div class="row"><button type="button" class="work">Ask at work (GitHub, public)</button><button type="button" class="home">Ask at home (private)</button></div>
      <p class="fine">${A.PUBLIC_NOTE}</p><div class="ans"></div></div>`;
    const ta = el.querySelector("textarea"), ctx = () => (typeof o.context === "function" ? o.context() : o.context) || "";
    const go = home => { const q = ta.value.trim(); if (!q) { ta.focus(); return; }
      window.open(home ? A.homeUrl(q, ctx()) : A.workUrl(o.topic, q, ctx()), "_blank", "noopener");
      if (!home) [20, 60, 180].forEach(s => setTimeout(answers, s * 1000)); };
    el.querySelector("button.work").onclick = () => go(false);
    el.querySelector("button.home").onclick = () => go(true);
    function answers() {
      fetch((o.base || "../") + "data/asks.json", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(all => {
        const done = ((all && all.leagues && all.leagues[o.topic]) || []).slice(0, 5);
        el.querySelector(".ans").innerHTML = done.map((x, k) => `<details${k ? "" : " open"}><summary>${esc(x.q)}</summary><div class="a">${esc(x.a)}</div>`
          + `<div class="fine">${x.issue ? `<a href="https://github.com/${REPO}/issues/${x.issue}" target="_blank" rel="noopener">thread</a>` : ""}</div></details>`).join("");
      }).catch(() => {});
    }
    answers();
  };
})();
