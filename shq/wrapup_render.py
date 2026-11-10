"""Draws a weekend wrap-up (the model from shq/wrapup.py) as a phone-sized PDF (reportlab) and a web page, plus the
archive page. Both show the same text; nothing here computes anything.

The PDF page is 4.25 x 7.5 in, so a phone's PDF viewer shows it at about 1.3x with no zooming. Helvetica keeps the
file small and needs no font files; text is mapped to its Windows-1252 character set."""
import html as H
import io
import re

from .config import SITE_URL

PAGE_W, PAGE_H = 306, 540          # points: 4.25 x 7.5 in
MARGIN = 16
INK, MUTED, RULE, ACCENT, CUT, BAR, SOFT = "#16181d", "#5f6672", "#d9dce1", "#2458c6", "#b4441a", "#b9bec7", "#f2f4f7"
RESULT_WORD = {"W": "Won", "L": "Lost", "T": "Tied", "leading": "Leading", "trailing": "Trailing", "even": "Even",
               "survived": "Survived", "cut": "Cut"}


def title_of(m):
    return f"Weekend wrap-up: NFL week {m['week']}, college week {m['cfb_week']}"


def edition_of(m):
    if m["edition"] == "sunday":
        return "Sunday edition: Monday night still to play. The final comes Tuesday morning."
    return "Final" + (", with your graded pool entries." if m["pools"].get("entries") else ".")


def _tone(result):
    return {"W": "good", "survived": "good", "leading": "good", "L": "bad", "cut": "bad", "trailing": "bad"}.get(result, "")


# ---------- HTML ----------

CSS = """
:root{--ink:#16181d;--muted:#5f6672;--rule:#d9dce1;--bg:#ffffff;--card:#f6f7f9;--accent:#2458c6;--good:#1d7a46;--bad:#b4441a;--bar:#b9bec7}
@media (prefers-color-scheme:dark){:root{--ink:#e8eaee;--muted:#a2a9b5;--rule:#353a43;--bg:#111317;--card:#1a1d23;--accent:#7aa2ff;--good:#5cc98a;--bad:#ff8a5c;--bar:#4a505b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%}
main{max-width:680px;margin:0 auto;padding:16px 16px 40px}
a{color:var(--accent)}
h1{font-size:22px;line-height:1.2;margin:4px 0 2px}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:26px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--rule)}
h3{font-size:16px;margin:0 0 4px;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.meta{color:var(--muted);font-size:13px}
.top{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0}
.btn{display:inline-block;padding:7px 12px;border:1px solid var(--rule);border-radius:10px;text-decoration:none;font-size:14px;font-weight:600}
ul{margin:6px 0;padding-left:18px}li{margin:3px 0}
.short li{margin:5px 0}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:12px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--rule);padding:4px 6px 4px 0}
td{padding:6px 6px 6px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.lg{background:var(--card);border-radius:12px;padding:12px 14px;margin:10px 0}
.chip{font-size:12px;font-weight:700;padding:2px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.good{color:var(--good)}.bad{color:var(--bad)}
.row{margin:4px 0}.lbl{color:var(--muted);font-size:13px}
.src{color:var(--muted);font-size:12px}
.chart{margin:8px 0 4px}.chart svg{width:100%;height:auto;display:block}
footer{margin-top:28px;color:var(--muted);font-size:12px}
"""


def _e(s):
    return H.escape(str(s or ""))


LABEL_MAX = 32   # "Team name (username)" labels (Q-047): the label column grows to fit instead of cutting at 16


def _short(s, n=LABEL_MAX):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _chart_svg(c):
    bars = c["bars"]
    longest = max((len(_short(b["label"])) for b in bars), default=0)
    # drawn at about phone width, so 12px text stays 12px (~6.3px a character)
    w, row, lab = 360, 20, int(min(200, max(112, 6.3 * longest + 12)))
    top = max(b["value"] for b in bars) or 1
    h = row * len(bars) + 6
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{_e(c["title"])}">']
    for i, b in enumerate(bars):
        y = 3 + i * row
        bw = max(2, (w - lab - 44) * b["value"] / top)
        fill = "var(--accent)" if b["me"] else "var(--bad)" if b["low"] else "var(--bar)"
        name = b["label"] + (" (you)" if b["me"] else " (lowest)" if b["low"] else "")
        weight = ' font-weight="700"' if b["me"] else ""
        out.append(f'<g><title>{_e(name)}: {b["value"]:.1f}</title>'
                   f'<text x="{lab - 8}" y="{y + 14}" text-anchor="end" font-size="12" fill="var(--ink)"'
                   f'{weight}>{_e(_short(b["label"]))}</text>'
                   f'<rect x="{lab}" y="{y + 3}" width="{bw:.1f}" height="{row - 6}" rx="4" fill="{fill}"/>'
                   f'<text x="{lab + bw + 6:.1f}" y="{y + 14}" font-size="11" fill="var(--muted)">{b["value"]:.1f}</text></g>')
    out.append("</svg>")
    return "".join(out)


def _league_html(l):
    tone = _tone(l.get("result"))
    chip = f'<span class="chip {tone}">{_e(RESULT_WORD.get(l.get("result"), ""))}</span>' if l.get("result") else ""
    parts = [f'<div class="lg"><h3><span>{_e(l["name"])}</span>{chip}</h3>', f'<div class="row">{_e(l.get("line"))}</div>']
    if l.get("standing"):
        parts.append(f'<div class="row"><span class="lbl">Standing:</span> {_e(l["standing"])}</div>')
    if l.get("bench"):
        parts.append(f'<div class="row"><span class="lbl">Bench:</span> {_e(l["bench"])}</div>')
    if l.get("boom"):
        parts.append(f'<div class="row"><span class="lbl">Boomed:</span> {_e("; ".join(l["boom"]))}</div>')
    if l.get("bust"):
        parts.append(f'<div class="row"><span class="lbl">Busted:</span> {_e("; ".join(l["bust"]))}</div>')
    if l.get("chart"):
        parts.append(f'<div class="chart"><div class="lbl">{_e(l["chart"]["title"])}</div>{_chart_svg(l["chart"])}</div>')
    if l.get("injuries"):
        parts.append('<div class="row"><span class="lbl">Injuries to watch:</span><ul>' + "".join(
            f'<li>{_e(i["text"])} <span class="src">[<a href="{_e(i["url"])}">{_e(i["source"])}</a>]</span></li>' if i.get("url")
            else f'<li>{_e(i["text"])} <span class="src">[{_e(i["source"])}]</span></li>' for i in l["injuries"]) + "</ul></div>")
    if l.get("note"):
        parts.append(f'<div class="src">{_e(l["note"])}</div>')
    parts.append("</div>")
    return "".join(parts)


def html(m):
    pdf = f"{m['season']}-w{m['week']:02d}.pdf"
    p = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>Wrap-up: NFL week {m["week"]}</title><style>{CSS}</style></head><body><main>',
         '<div class="meta"><a href="../">Sports HQ</a> / <a href="./">Wrap-ups</a></div>',
         f'<h1>{_e(title_of(m))}</h1><div class="meta">{_e(edition_of(m))} Built {_e(m["generated_label"])}.</div>',
         f'<div class="top"><a class="btn" href="{pdf}">Open the PDF</a><a class="btn" href="./">Past weeks</a></div>',
         '<h2>The short version</h2><ul class="short">' + "".join(f"<li>{_e(x)}</li>" for x in m["headline"]) + "</ul>",
         '<h2>Scoreboard</h2><table><tr><th>League</th><th>Result</th><th>Score</th><th>Standing</th></tr>']
    for l in m["leagues"]:
        r = l.get("result")
        p.append(f'<tr><td>{_e(l["name"])}</td><td class="{_tone(r)}">{_e(RESULT_WORD.get(r, "-"))}</td>'
                 f'<td>{_e(l.get("score") or "-")}</td><td>{_e((l.get("standing") or "-").split(" (")[0])}</td></tr>')
    p.append("</table><h2>League by league</h2>")
    p += [_league_html(l) for l in m["leagues"]]
    p.append("<h2>Next week</h2>")
    for l in m["leagues"]:
        if l.get("next"):
            p.append(f'<div class="row"><strong>{_e(l["name"])}</strong><ul>' + "".join(f"<li>{_e(x)}</li>" for x in l["next"]) + "</ul></div>")
    p.append(_pools_html(m["pools"]))
    if m.get("warroom"):
        p.append("<h2>Guillotine bids (War Room v2)</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in m["warroom"]["lines"]) +
                 f'</ul><div class="src">Source: <a href="../war-room-v2/">{_e(m["warroom"]["source"])}</a></div>')
    if m.get("numbers"):
        p.append("<h2>What the numbers say</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in m["numbers"]) + "</ul>")
    p.append(f'<footer>{_e(SOURCES)}</footer></main></body></html>')
    return "".join(p)


def _pools_html(pools):
    p = ["<h2>Pools</h2>"]
    if pools.get("pools"):
        p.append("<table><tr><th>Pool</th><th>Card</th><th>Entered</th><th>Before / after</th></tr>")
        for x in pools["pools"]:
            card = "-" if x.get("card") is None else x["card"] + (f" ({x['net']:+,.0f})" if x.get("net") is not None else "") + \
                (f", {x['open']} open" if x.get("open") else "")
            ba = " / ".join(v for v in (x.get("before"), x.get("after")) if v) or "-"
            p.append(f'<tr><td>{_e(x["title"])}</td><td>{_e(card)}</td><td>{_e(x.get("entered") or "Tue night")}</td><td>{_e(ba)}</td></tr>')
        p.append("</table>")
        for x in pools["pools"]:
            if x.get("picks"):
                p.append(f'<div class="row"><span class="lbl">{_e(x["title"])}:</span> ' +
                         _e("; ".join(f"{k['pick']} {k['result']}" for k in x["picks"])) + "</div>")
    if pools.get("note"):
        p.append(f'<div class="src">{_e(pools["note"])}</div>')
    elif pools.get("pools") and not pools.get("entries"):
        p.append('<div class="src">Card as posted ("if entered as posted" for BTO/CFP money). Your actual entries are read and graded at the Tuesday 8pm postmortem; this page updates then.</div>')
    return "".join(p)


SOURCES = ("Sources: Sleeper and ESPN fantasy APIs (scores, projections), ESPN's injury report (dated notes, linked), "
           "ESPN scoreboards (pool results), FantasyCalc (trade values), War Room v2. Kosmonauts points are Sleeper stats "
           "with league scoring until Yahoo's API is approved. Built by GitHub Actions from templates; no AI.")


def short(text, n=220):
    """At most n characters for the archive's short-version column, never cut mid-word: up to the last whole
    sentence that fits, or (when the first sentence alone is longer) the last whole word plus an ellipsis."""
    s = " ".join(str(text or "").split())
    if len(s) <= n:
        return s
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", s[:n + 1]) if m.end() <= n]
    if ends:
        return s[:ends[-1]]
    head = s[:n].rsplit(" ", 1)[0] if " " in s[:n] else s[:n - 1]
    return head.rstrip(" ,;:-(") + "…"


def archive(issues):
    pdf_link = lambda i: f'<a href="{_e(i["pdf"])}">PDF</a>' if i.get("pdf") else ""
    rows = "".join(
        f'<tr><td><a href="{_e(i["html"])}">NFL week {i["week"]}</a><div class="src">college week {i["cfb_week"]}, '
        f'{"final" if i["edition"] == "final" else "Sunday edition"}</div></td>'
        f'<td>{pdf_link(i)}</td>'
        f'<td class="src">{_e(short(" ".join(i.get("headline") or [])))}</td></tr>' for i in issues)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Weekend wrap-ups</title><style>{CSS}</style></head><body><main><div class="meta"><a href="../">Sports HQ</a></div>'
            f'<h1>Weekend wrap-ups</h1><div class="meta">Sunday night after the late games, final Tuesday morning after Monday night.</div>'
            f'<table><tr><th>Week</th><th></th><th>Short version</th></tr>{rows}</table></main></body></html>')


# ---------- PDF ----------

def _t(s):
    """Text for a reportlab Paragraph: escaped, in Helvetica's Windows-1252 set."""
    s = str(s or "").replace("→", "->").replace("★", "*").replace("≥", ">=").replace("≤", "<=").replace("✓", "")
    s = s.encode("cp1252", "replace").decode("cp1252")
    return H.escape(s, quote=False)


def pdf(m):
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    c = colors.HexColor
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, leading=11.2, textColor=c(INK), alignment=TA_LEFT)
    small = ParagraphStyle("s", parent=base, fontSize=7.2, leading=9.2, textColor=c(MUTED))
    cell = ParagraphStyle("c", parent=base, fontSize=7.6, leading=9.4)
    bullet = ParagraphStyle("li", parent=base, leftIndent=9, bulletIndent=0, spaceBefore=1.5)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=c(MUTED), spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=12.5, spaceBefore=6)
    tone_hex = {"good": "#1d7a46", "bad": CUT}

    def P(text, st=base):
        return Paragraph(text, st)

    def li(text):
        return Paragraph(text, bullet, bulletText="•")

    def label(name, text):
        return P(f'<font color="{MUTED}">{name}</font> {_t(text)}')

    def section(name):
        return [CondPageBreak(60), P(name.upper(), h2),
                Drawing(PAGE_W - 2 * MARGIN, 1, Line(0, 0.5, PAGE_W - 2 * MARGIN, 0.5, strokeColor=c(RULE), strokeWidth=0.6))]

    W = PAGE_W - 2 * MARGIN
    story = [P(_t(title_of(m)), h1), Spacer(1, 2), P(_t(f"{edition_of(m)} Built {m['generated_label']}."), small), Spacer(1, 2),
             P(f'<a href="{SITE_URL}wrapups/{m["season"]}-w{m["week"]:02d}.html" color="{ACCENT}">Web version</a>', small)]
    story += section("The short version") + [li(_t(x)) for x in m["headline"]]

    story += section("Scoreboard")
    data = [[P("<b>League</b>", cell), P("<b>Result</b>", cell), P("<b>Score</b>", cell), P("<b>Standing</b>", cell)]]
    for l in m["leagues"]:
        r = l.get("result")
        word = RESULT_WORD.get(r, "-")
        col = tone_hex.get(_tone(r))
        data.append([P(_t(l["name"]), cell), P(f'<font color="{col}">{_t(word)}</font>' if col else _t(word), cell),
                     P(_t(l.get("score") or "-"), cell), P(_t((l.get("standing") or "-").split(" (")[0]), cell)])
    t = Table(data, colWidths=[W * .27, W * .2, W * .28, W * .25])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, c(RULE)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story.append(t)

    story += section("League by league")
    for l in m["leagues"]:
        r = l.get("result")
        col = tone_hex.get(_tone(r), MUTED)
        # only the name and result line stay together; the rest flows, so a league never leaves half a page blank
        story.append(KeepTogether([P(f'{_t(l["name"])}' + (f'  <font size="7.5" color="{col}">{_t(RESULT_WORD.get(r, "").upper())}</font>' if r else ""), h3),
                                   P(_t(l.get("line")))]))
        block = []
        if l.get("standing"):
            block.append(label("Standing:", l["standing"]))
        if l.get("bench"):
            block.append(label("Bench:", l["bench"]))
        if l.get("boom"):
            block.append(label("Boomed:", "; ".join(l["boom"])))
        if l.get("bust"):
            block.append(label("Busted:", "; ".join(l["bust"])))
        if l.get("chart"):
            block.append(KeepTogether([Spacer(1, 3), P(_t(l["chart"]["title"]), small), _chart_drawing(l["chart"], W, Drawing, Rect, String, c)]))
        for i in l.get("injuries") or []:
            src = (f'<a href="{H.escape(i["url"])}" color="{ACCENT}">{_t(i["source"])}</a>' if i.get("url") else _t(i["source"]))
            block.append(Paragraph(f'{_t(i["text"])} <font color="{MUTED}">[{src}]</font>', ParagraphStyle("inj", parent=bullet, fontSize=7.8, leading=10)))
        if l.get("note"):
            block.append(P(_t(l["note"]), small))
        story += block

    story += section("Next week")
    for l in m["leagues"]:
        if l.get("next"):
            story += [KeepTogether([P(f"<b>{_t(l['name'])}</b>"), li(_t(l["next"][0]))])] + [li(_t(x)) for x in l["next"][1:]]

    pools = m["pools"]
    story += section("Pools")
    if pools.get("pools"):
        data = [[P(x, cell) for x in ("<b>Pool</b>", "<b>Card</b>", "<b>Entered</b>", "<b>Before / after</b>")]]
        for x in pools["pools"]:
            card = "-" if x.get("card") is None else x["card"] + (f" ({x['net']:+,.0f})" if x.get("net") is not None else "") + \
                (f", {x['open']} open" if x.get("open") else "")
            ba = " / ".join(v for v in (x.get("before"), x.get("after")) if v) or "-"
            data.append([P(_t(x["title"]), cell), P(_t(card), cell), P(_t(x.get("entered") or "Tue night"), cell), P(_t(ba), cell)])
        t = Table(data, colWidths=[W * .24, W * .2, W * .18, W * .38])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, c(RULE)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(t)
        for x in pools["pools"]:
            if x.get("picks"):
                story.append(P(f'<font color="{MUTED}">{_t(x["title"])}:</font> ' +
                               _t("; ".join(f"{k['pick']} {k['result']}" for k in x["picks"])), cell))
    if pools.get("note"):
        story.append(P(_t(pools["note"]), small))
    elif pools.get("pools") and not pools.get("entries"):
        story.append(P(_t("Card as posted (BTO/CFP money if entered as posted). Your actual entries are graded at the "
                          "Tuesday 8pm postmortem; the web page and PDF update then."), small))

    if m.get("warroom"):
        story += section("Guillotine bids (War Room v2)") + [li(_t(x)) for x in m["warroom"]["lines"]]
        story.append(P(_t("Source: " + m["warroom"]["source"]), small))
    if m.get("numbers"):
        story += section("What the numbers say") + [li(_t(x)) for x in m["numbers"]]
    story += [Spacer(1, 8), P(_t(SOURCES), small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(c(MUTED))
        canvas.drawString(MARGIN, 9, f"Sports HQ wrap-up, NFL week {m['week']}")
        canvas.drawRightString(PAGE_W - MARGIN, 9, f"page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16, bottomMargin=20,
                            title=title_of(m), author="Sports HQ", subject="Weekend wrap-up")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _chart_drawing(ch, width, Drawing, Rect, String, c):
    """Horizontal bars, one per team: me in the accent color, the lowest (cut) team in the alert color, the rest gray,
    each directly labeled (single series: no legend)."""
    bars = ch["bars"]
    longest = max((len(_short(b["label"])) for b in bars), default=0)
    row, val = 10.5, 26
    lab = min(width * 0.42, max(74, 3.4 * longest + 6))   # 6.6pt Helvetica: ~3.4pt a character
    top = max(b["value"] for b in bars) or 1
    h = row * len(bars) + 2
    d = Drawing(width, h)
    for i, b in enumerate(bars):
        y = h - (i + 1) * row
        bw = max(1.5, (width - lab - val) * b["value"] / top)
        fill = ACCENT if b["me"] else CUT if b["low"] else BAR
        name = _t(_short(b["label"]))
        d.add(String(lab - 4, y + 2.4, name, fontName="Helvetica-Bold" if b["me"] else "Helvetica", fontSize=6.6,
                     fillColor=c(INK), textAnchor="end"))
        d.add(Rect(lab, y + 1.2, bw, row - 2.6, rx=2, ry=2, fillColor=c(fill), strokeColor=None))
        d.add(String(lab + bw + 3, y + 2.4, f"{b['value']:.1f}", fontName="Helvetica", fontSize=6.4, fillColor=c(MUTED)))
    return d
