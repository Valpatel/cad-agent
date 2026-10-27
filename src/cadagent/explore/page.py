"""The comparison as one standalone HTML page: inline CSS (light and dark), no external files, opens from file://.

Sections: the objectives and the honesty notes; a trade-off chart of the first two objectives (the Pareto front in
the accent colour, other feasible designs grey, infeasible ones hollow); the leaderboard (sortable; the chart's table
view); and per design its checks, bill of materials, parameters and one-part swaps.
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from cadagent.explore import metrics as M
from cadagent.explore.catalogue import json_default, link_url
from cadagent.explore.compare import anchor, describe_choice

MAX_ROWS = 300          # leaderboard rows on the page (all of them stay in the JSON)
MAX_DETAILS = 40        # designs with a detail section
MAX_LABELS = 8          # direct labels on the chart's Pareto points
MAX_SWAPS = 30          # swap rows per design (the most useful first; all of them stay in the JSON)

_CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--axis:#c3c2b7;--line:rgba(11,11,11,.10);--accent:#2a78d6;--good:#0ca30c;--warning:#fab219;--critical:#d03b3b;
--row:#f2f1ec;--wash:rgba(42,120,214,.08)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--line:rgba(255,255,255,.10);
--accent:#3987e5;--row:#232321;--wash:rgba(57,135,229,.12)}}
:root[data-theme=dark]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--line:rgba(255,255,255,.10);--accent:#3987e5;--row:#232321;--wash:rgba(57,135,229,.12)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
.wrap{padding:24px 32px 48px;max-width:1600px}
h1{margin:0 0 4px;font-size:26px;line-height:1.25}.kicker{margin:0;color:var(--muted);font-size:13px;font-weight:600;
letter-spacing:.06em;text-transform:uppercase}h2{font-size:19px;margin:30px 0 10px}h3{font-size:16px;margin:16px 0 6px}
.meta{color:var(--ink2);margin:0;font-size:14px}.chips{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}
.chip{border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--ink2)}
.chip b{color:var(--ink);font-weight:600}
.note{margin:16px 0 0;padding:10px 14px;border:1px solid var(--line);border-left:4px solid var(--warning);border-radius:8px;
background:var(--surface);color:var(--ink2);font-size:14px}.note p{margin:4px 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.tablewrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}td.txt{white-space:normal;min-width:16em}
tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:var(--row)}
th{color:var(--ink2);font-weight:600;font-size:13px}th button{all:unset;cursor:pointer}th button:focus-visible{outline:2px solid var(--accent)}
th[aria-sort=ascending] button::after{content:" ▲";color:var(--muted)}th[aria-sort=descending] button::after{content:" ▼";color:var(--muted)}
.goal{color:var(--muted);font-weight:400}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;
color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:1px 8px;background:var(--surface)}
.pill i{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--muted)}
.pill.ok i{background:var(--good)}.pill.warn i{background:var(--warning)}.pill.fail i,.pill.error i{background:var(--critical)}
.front{color:var(--accent);font-weight:700}td.lvl-fail{box-shadow:inset -3px 0 0 var(--critical);font-weight:600}
.dim{color:var(--muted)}.est{color:var(--muted);font-size:12px}
ul.checks{list-style:none;padding:0;margin:6px 0}ul.checks li{display:flex;gap:8px;align-items:baseline;padding:2px 0}
details.design{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 16px;margin:10px 0}
details.design>summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:10px;align-items:baseline}
details.design>summary h3{display:inline;margin:0}
details.design:target{border-color:var(--accent)}
pre{background:var(--page);border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow-x:auto;font-size:12.5px}
figure.chart{margin:0;position:relative}.chart .scroll{overflow-x:auto}
.chart svg{display:block;width:100%;height:auto;max-width:880px;min-width:600px}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--ink2);margin:0 0 6px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{width:10px;height:10px;border-radius:50%;display:inline-block}
.key.front{background:var(--accent)}.key.other{background:var(--muted)}.key.bad{border:2px solid var(--muted)}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;
padding:6px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;min-width:150px}
.tip b{font-weight:600;font-variant-numeric:tabular-nums}.tip .t{color:var(--ink2);margin-bottom:2px}
.tip .r{display:flex;justify-content:space-between;gap:12px}.tip .r span{color:var(--muted)}
svg .gridline{stroke:var(--grid);stroke-width:1}svg .axisline{stroke:var(--axis);stroke-width:1}
svg text{fill:var(--muted);font:12px system-ui,-apple-system,"Segoe UI",sans-serif}
svg text.lab{fill:var(--ink2)}svg text.title{fill:var(--ink2);font-weight:600}
svg .frontline{stroke:var(--accent);stroke-width:2;fill:none;stroke-linejoin:round;stroke-linecap:round}
svg circle.front{fill:var(--accent);stroke:var(--surface);stroke-width:2}
svg circle.other{fill:var(--muted);stroke:var(--surface);stroke-width:2}
svg circle.bad{fill:var(--surface);stroke:var(--muted);stroke-width:2}
svg circle.hit{fill:transparent;stroke:none}svg a.pt:focus{outline:none}svg a.pt:focus circle.hit,svg a.pt:hover circle.hit{fill:var(--wash)}
footer{color:var(--muted);font-size:13px;margin-top:30px}
@media (max-width:640px){.wrap{padding:16px 16px 32px}h1{font-size:22px}}
"""

_JS = """
(() => {
  // sortable leaderboard: click a column header; numbers sort by data-v, text by its content
  document.querySelectorAll('table.sortable').forEach((table) => {
    const heads = [...table.tHead.rows[0].cells];
    heads.forEach((th, col) => {
      const b = th.querySelector('button'); if (!b) return;
      b.addEventListener('click', () => {
        const dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        heads.forEach((h) => h.hasAttribute('aria-sort') && h.setAttribute('aria-sort', 'none'));
        th.setAttribute('aria-sort', dir);
        const rows = [...table.tBodies[0].rows];
        const key = (r) => { const c = r.cells[col]; const v = c.dataset.v;
          return v === undefined ? c.textContent.trim().toLowerCase() : (v === '' ? null : Number(v)); };
        rows.sort((a, b) => { const x = key(a), y = key(b);
          if (x === null) return 1; if (y === null) return -1;
          const s = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
          return dir === 'ascending' ? s : -s; });
        rows.forEach((r) => table.tBodies[0].appendChild(r));
      });
    });
  });
  // chart tooltip: the values lead, the design name sits above them
  document.querySelectorAll('figure.chart').forEach((fig) => {
    const tip = fig.querySelector('.tip');
    const show = (pt) => {
      tip.replaceChildren();
      const t = document.createElement('div'); t.className = 't'; t.textContent = pt.dataset.name; tip.appendChild(t);
      for (const [v, l] of [[pt.dataset.xv, pt.dataset.xl], [pt.dataset.yv, pt.dataset.yl], [pt.dataset.state, '']]) {
        if (!v) continue;
        const r = document.createElement('div'); r.className = 'r';
        const b = document.createElement('b'); b.textContent = v; const s = document.createElement('span'); s.textContent = l;
        r.append(b, s); tip.appendChild(r);
      }
      const box = fig.getBoundingClientRect(), p = pt.getBoundingClientRect();
      tip.style.display = 'block';
      const x = p.left - box.left + p.width / 2 + 12, y = p.top - box.top - 8;
      tip.style.left = Math.min(x, box.width - tip.offsetWidth - 4) + 'px';
      tip.style.top = Math.max(0, y - tip.offsetHeight) + 'px';
    };
    const hide = () => { tip.style.display = 'none'; };
    fig.querySelectorAll('a.pt').forEach((pt) => {
      pt.addEventListener('pointerenter', () => show(pt)); pt.addEventListener('focus', () => show(pt));
      pt.addEventListener('pointerleave', hide); pt.addEventListener('blur', hide);
    });
  });
})();
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _value(ev: Dict[str, Any], name: str) -> Optional[float]:
    v = ((ev.get("metrics") or {}).get(name) or {}).get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fmt(metric: Optional[Dict[str, Any]], col: Dict[str, Any], with_unit: bool = True) -> str:
    if not metric:
        return "—"
    return M.format_value(metric.get("value"), col.get("unit", ""), col.get("digits"), bool(metric.get("estimate")),
                          bool(metric.get("incomplete")), with_unit)


def _pill(level: str) -> str:
    return f'<span class="pill {_e(level)}"><i></i>{_e(level)}</span>'


# ----------------------------------------------------------------------------- the trade-off chart

def _nice_ticks(lo: float, hi: float, n: int = 5) -> Tuple[float, float, List[float]]:
    if not math.isfinite(lo) or not math.isfinite(hi):
        return 0.0, 1.0, [0.0, 1.0]
    if hi - lo < 1e-12:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if (hi - lo) / (m * mag) <= n)
    start, end = math.floor(lo / step) * step, math.ceil(hi / step) * step
    count = int(round((end - start) / step))
    return start, end, [start + i * step for i in range(count + 1)]


def _decimals(step: float) -> int:
    """Decimals that show every multiple of ``step`` exactly (2.5 needs one, 0.25 two)."""
    text = f"{abs(step):.10g}"
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


def _tick_label(v: float, step: float) -> str:
    """``2.5K``, ``7.5``, ``0.25``: the step decides the decimals; trailing zeros go."""
    def trim(text: str) -> str:
        return text.rstrip("0").rstrip(".") if "." in text else text
    if abs(v) >= 1000:
        return trim(f"{v / 1000:,.{_decimals(step / 1000)}f}") + "K"
    return trim(f"{v:,.{_decimals(step)}f}")


def _place_label(text: str, px: float, py: float, marks: List[Tuple[float, float]],
                 placed: List[Tuple[float, float, float, float]], plot: Tuple[float, float, float, float]) -> str:
    """A direct label beside a point: the first of four spots (right-above, right-below, left-above, left-below) that
    stays inside the plot and clear of other points and labels; none when all four collide (the tooltip and the
    leaderboard still carry the name)."""
    w, h = 7.0 * len(text) + 4, 14.0
    for dx, dy, end in ((9, -8, False), (9, 16, False), (-9, -8, True), (-9, 16, True)):
        x0 = px + dx - (w if end else 0)
        box = (x0, py + dy - 11, x0 + w, py + dy - 11 + h)
        inside = plot[0] <= box[0] and box[2] <= plot[2] and plot[1] <= box[1] and box[3] <= plot[3]
        hits_mark = any(box[0] - 6 <= mx <= box[2] + 6 and box[1] - 6 <= my <= box[3] + 6
                        for mx, my in marks if (mx, my) != (px, py))
        hits_label = any(not (box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]) for b in placed)
        if inside and not hits_mark and not hits_label:
            placed.append(box)
            return (f'<text class="lab" x="{px + dx:.1f}" y="{py + dy:.1f}" text-anchor="{"end" if end else "start"}">'
                    f'{_e(text)}</text>')
    return ""


def _chart(comp: Dict[str, Any]) -> str:
    objectives = comp.get("objectives") or []
    if len(objectives) < 2:
        return ""
    ox, oy = objectives[0], objectives[1]
    cols = comp["metrics"]
    cx, cy = cols.get(ox["metric"], {}), cols.get(oy["metric"], {})
    pts = [(ev, _value(ev, ox["metric"]), _value(ev, oy["metric"])) for ev in comp["designs"]]
    pts = [(ev, x, y) for ev, x, y in pts if x is not None and y is not None]
    if len(pts) < 2:
        return ""
    W, H, L, R, T, B = 760, 380, 70, 20, 16, 52
    x0, x1, xt = _nice_ticks(min(p[1] for p in pts), max(p[1] for p in pts))
    y0, y1, yt = _nice_ticks(min(p[2] for p in pts), max(p[2] for p in pts))
    sx = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)                       # noqa: E731
    sy = lambda v: H - B - (v - y0) / (y1 - y0) * (H - T - B)                   # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="chart-title">'
           f'<title id="chart-title">{_e(cx.get("label"))} against {_e(cy.get("label"))} for {len(pts)} designs; '
           f'the Pareto front is highlighted</title>']
    xstep, ystep = (xt[1] - xt[0]) if len(xt) > 1 else 1, (yt[1] - yt[0]) if len(yt) > 1 else 1
    for v in yt:
        out.append(f'<line class="gridline" x1="{L}" x2="{W - R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}"/>'
                   f'<text x="{L - 8}" y="{sy(v) + 4:.1f}" text-anchor="end">{_e(_tick_label(v, ystep))}</text>')
    for v in xt:
        out.append(f'<line class="gridline" x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{T}" y2="{H - B}"/>'
                   f'<text x="{sx(v):.1f}" y="{H - B + 18}" text-anchor="middle">{_e(_tick_label(v, xstep))}</text>')
    out.append(f'<line class="axisline" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>'
               f'<line class="axisline" x1="{L}" x2="{L}" y1="{T}" y2="{H - B}"/>')
    better = {"min": "lower is better", "max": "higher is better"}
    unit = lambda c: f" ({c['unit']})" if c.get("unit") else ""                  # noqa: E731
    out.append(f'<text class="title" x="{(L + W - R) / 2:.1f}" y="{H - 10}" text-anchor="middle">'
               f'{_e(cx.get("label"))}{_e(unit(cx))}, {better[ox["goal"]]}</text>'
               f'<text class="title" transform="translate(16 {(T + H - B) / 2:.1f}) rotate(-90)" text-anchor="middle">'
               f'{_e(cy.get("label"))}{_e(unit(cy))}, {better[oy["goal"]]}</text>')
    front = sorted([p for p in pts if p[0].get("pareto")], key=lambda p: p[1])
    if len(objectives) == 2 and len(front) > 1:
        out.append('<polyline class="frontline" points="'
                   + " ".join(f"{sx(x):.1f},{sy(y):.1f}" for _, x, y in front) + '"/>')
    layers = ([p for p in pts if not p[0].get("feasible")], [p for p in pts if p[0].get("feasible") and not p[0].get("pareto")], front)
    for cls, layer in zip(("bad", "other", "front"), layers):
        for ev, x, y in layer:
            state = "Pareto front" if cls == "front" else "feasible" if cls == "other" else f"infeasible ({ev.get('verdict')})"
            if ev.get("lower_bounds") and cls != "bad":
                state += ", ranked on a lower bound"
            xv, yv = _fmt(ev["metrics"][ox["metric"]], cx), _fmt(ev["metrics"][oy["metric"]], cy)
            out.append(f'<a class="pt" href="#{_e(anchor(ev["id"]))}" data-name="{_e(ev.get("name"))}" '
                       f'data-xv="{_e(xv)}" data-xl="{_e(cx.get("label"))}" data-yv="{_e(yv)}" data-yl="{_e(cy.get("label"))}" '
                       f'data-state="{_e(state)}" aria-label="{_e(ev.get("name"))}: {_e(xv)}, {_e(yv)}, {_e(state)}">'
                       f'<circle class="hit" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="12"/>'
                       f'<circle class="{cls}" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{5 if cls == "front" else 4.5}"/></a>')
    if len(front) <= MAX_LABELS:
        marks = [(sx(x), sy(y)) for _, x, y in pts]
        placed: List[Tuple[float, float, float, float]] = []
        for ev, x, y in front:
            label = _place_label(str(ev.get("name")), sx(x), sy(y), marks, placed, (L, T, W - R, H - B))
            if label:
                out.append(label)
    out.append("</svg>")
    legend = ('<div class="legend"><span><i class="key front"></i>Pareto front</span>'
              '<span><i class="key other"></i>feasible</span><span><i class="key bad"></i>infeasible</span></div>')
    return (f'<h2 id="trade-off">Trade-off</h2><div class="card"><figure class="chart">{legend}'
            f'<div class="scroll">{"".join(out)}</div>'
            f'<div class="tip" role="status"></div></figure><p class="meta">The first two objectives. '
            f'Select a point to open its design; every value is also in the leaderboard below.</p></div>')


# ----------------------------------------------------------------------------- leaderboard and details

def _leaderboard(comp: Dict[str, Any]) -> str:
    cols = comp["metrics"]
    goals = {o["metric"]: o["goal"] for o in comp.get("objectives") or []}
    designs = comp["designs"][:MAX_ROWS]
    head = ['<th aria-sort="none" class="num"><button>#</button></th>', '<th aria-sort="none"><button>Design</button></th>',
            '<th aria-sort="none"><button>Verdict</button></th>']
    for name, col in cols.items():
        unit = f" ({col['unit']})" if col.get("unit") else ""
        goal = f' <span class="goal">· {goals[name]}</span>' if name in goals else ""
        title = f' title="objective: {"lower" if goals[name] == "min" else "higher"} is better"' if name in goals else ""
        head.append(f'<th aria-sort="none" class="num"{title}><button>{_e(col["label"])}{_e(unit)}{goal}</button></th>')
    head.append('<th aria-sort="none" class="num"><button>Checks</button></th>')
    rows = []
    for ev in designs:
        rank = ev.get("rank")
        bound = ""
        if rank and ev.get("lower_bounds"):
            names = ", ".join(cols.get(m, {}).get("label", m) for m in ev["lower_bounds"])
            bound = f' <span class="dim" title="ranked on a lower bound: the {_e(names)} total leaves out parts">≥</span>'
        rank_cell = (f'<td class="num" data-v="{rank}"><span class="{"front" if ev.get("pareto") else ""}">'
                     f'{"★ " if ev.get("pareto") else ""}{rank}</span>{bound}</td>' if rank else '<td class="num" data-v="">—</td>')
        choice = ev.get("choice")
        sub = f'<br><span class="dim">{_e(describe_choice(choice))}</span>' if isinstance(choice, dict) and choice else ""
        cells = [rank_cell, f'<td data-v="{_e(str(ev.get("name")).lower())}"><a href="#{_e(anchor(ev["id"]))}">{_e(ev.get("name"))}</a>{sub}</td>',
                 f'<td data-v="{["ok", "warn", "fail", "error"].index(ev.get("verdict", "error")) if ev.get("verdict") in ("ok", "warn", "fail", "error") else 9}">'
                 f'{_pill(ev.get("verdict", "error"))}</td>']
        for name, col in cols.items():
            m = (ev.get("metrics") or {}).get(name)
            v = _value(ev, name)
            lvl = ' class="num lvl-fail" title="constraint not met"' if m and m.get("level") == "fail" else ' class="num"'
            cells.append(f'<td{lvl} data-v="{"" if v is None else v}">{_e(_fmt(m, col, with_unit=False))}</td>')
        c = ev.get("counts") or {}
        cells.append(f'<td class="num" data-v="{c.get("fail", 0) * 1000 + c.get("warn", 0)}">'
                     f'{c.get("ok", 0)} ok · {c.get("warn", 0)} warn · {c.get("fail", 0)} fail</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    more = len(comp["designs"]) - len(designs)
    tail = f'<p class="meta">{more} more in the JSON.</p>' if more > 0 else ""
    return (f'<h2 id="leaderboard">Leaderboard</h2><div class="tablewrap"><table class="sortable"><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>{tail}'
            '<p class="meta">★ the Pareto front (rank 1): no feasible design is at least as good on every objective and better on one. '
            '≥ marks a total that leaves out parts without a price or mass. Such a total is a lower bound and never counts as '
            'better than a value it might exceed (unless both leave out the same parts), so a ≥ beside a rank means the rank '
            'rests on one. est. marks a value that rests on estimates.</p>')


def _source(url: Any) -> str:
    """A link for an http(s) source; anything else (``javascript:``, a reference such as "datasheet p. 4") as text."""
    if not url:
        return ""
    href = link_url(url)
    if href:
        return f'<a href="{_e(href)}" rel="noopener noreferrer">source</a>'
    return f'source: {_e(str(url)[:120])}'


def _bom(ev: Dict[str, Any], currency: str) -> str:
    b = ev.get("bom")
    if not b:
        return ""
    cur = currency.upper()
    rows = []
    for l in b["lines"]:
        price = "—" if l["line_price"] is None else M.format_value(l["line_price"], "", 2, l["price_estimate"])
        unit = "—" if l["unit_price"] is None else M.format_value(l["unit_price"], "", 2)
        mass = "—" if l["line_mass_g"] is None else M.format_value(l["line_mass_g"], "g", 0, l["mass_estimate"])
        packs = f' ({l["packs"]} × {l["pack_qty"]})' if l.get("pack_qty", 1) > 1 else ""
        src = _source(l.get("source"))
        info = " · ".join(x for x in (_e(l.get("confidence") or ""), f'checked {_e(l["price_checked"])}' if l.get("price_checked") else "",
                                       "custom" if l.get("custom") and not l.get("from_evaluator") else "",
                                       "from the evaluator" if l.get("from_evaluator") else "",
                                       "out of stock" if l.get("in_stock") is False else "", src) if x)
        rows.append(f'<tr><td>{_e(l["slot"])}</td><td class="txt">{_e(l["name"])}</td><td class="num">{_e(l["qty"])}{_e(packs)}</td>'
                    f'<td class="num">{_e(unit)}</td><td class="num">{_e(price)}</td><td class="num">{_e(mass)}</td>'
                    f'<td class="txt dim">{info}</td></tr>')
    t = b["totals"]
    groups = "".join(f'<span class="chip">{_e(g or "parts")} <b>{_e(M.format_value(v, cur, 2))}</b></span>'
                     for g, v in t["groups"].items()) if len(t["groups"]) > 1 else ""
    total = (f'<tr><td></td><td><b>Total</b></td><td></td><td></td>'
             f'<td class="num"><b>{_e(M.format_value(t["cost"], "", 2, t["cost_estimate"], not t["cost_complete"]))}</b></td>'
             f'<td class="num"><b>{_e(M.format_value(t["mass_kg"], "kg", 3, t["mass_estimate"], not t["mass_complete"]))}</b></td><td></td></tr>')
    return (f'<h3>Bill of materials ({_e(cur)})</h3><div class="tablewrap"><table><thead><tr><th>Slot</th><th>Part</th>'
            f'<th class="num">Qty</th><th class="num">Each</th><th class="num">Line</th><th class="num">Mass</th><th>Basis</th>'
            f'</tr></thead><tbody>{"".join(rows)}{total}</tbody></table></div>'
            + (f'<div class="chips">{groups}</div>' if groups else ""))


def _swaps(ev: Dict[str, Any], comp: Dict[str, Any]) -> str:
    sw = ev.get("swaps")
    if sw is None:
        return ""
    if not sw:
        return '<h3>One-part swaps</h3><p class="meta">No other catalogue part fits any slot.</p>'
    cols = comp["metrics"]
    objs = [o["metric"] for o in comp.get("objectives") or []]
    head = "".join(f'<th class="num">Δ {_e(cols.get(m, {}).get("label", m))}</th>' for m in objs)
    rows = []
    for s in sw[:MAX_SWAPS]:
        deltas = []
        for m in objs:
            d = s["delta"].get(m)
            cls = "front" if m in s["better"] else "dim" if m in s.get("unsure", []) else ""
            txt = "—" if d is None else ("+" if d > 0 else "") + M.format_value(d, cols.get(m, {}).get("unit", ""), cols.get(m, {}).get("digits"))
            if m in s.get("unsure", []):
                txt += " ?"
            title = ' title="cannot tell: one of the totals leaves out a part without a value"' if m in s.get("unsure", []) else ""
            deltas.append(f'<td class="num"><span class="{cls}"{title}>{_e(txt)}</span></td>')
        tag = "Better on every objective." if s["dominates"] else " ".join(s["problems"])
        rows.append(f'<tr><td>{_e(s["slot"])}</td><td class="txt">{_e(s["name"])} <span class="dim">{_e(s["to"])}</span></td>'
                    f'<td>{_pill(s["verdict"])}</td>{"".join(deltas)}<td class="txt dim">{_e(tag)}</td></tr>')
    more = (f'<p class="meta">The {MAX_SWAPS} most useful of {len(sw)} swaps: the other {len(sw) - MAX_SWAPS} are in the JSON.</p>'
            if len(sw) > MAX_SWAPS else "")
    return (f'<h3>One-part swaps</h3><p class="meta">Each row changes one slot to another catalogue part of its category and '
            f're-evaluates the design: swaps that beat it on every objective first, then feasible ones, then by how many '
            f'objectives improve. Highlighted deltas are improvements; a ? marks a change that cannot be told because a total '
            f'leaves out a part without a value.</p><div class="tablewrap"><table><thead><tr>'
            f'<th>Slot</th><th>Swap in</th><th>Verdict</th>{head}<th>Notes</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            + more)


def _details(comp: Dict[str, Any]) -> str:
    out = []
    order = {"fail": 0, "warn": 1, "ok": 2}
    for ev in comp["designs"][:MAX_DETAILS]:
        checks = sorted(ev.get("checks") or [], key=lambda c: order.get(c["level"], 0))
        check_list = "".join(f'<li>{_pill(c["level"])}<span>{_e(c["text"])}</span></li>' for c in checks)
        params = ev.get("params") or {}
        rank = f'rank {ev["rank"]}' + (" · Pareto front" if ev.get("pareto") else "") if ev.get("rank") else "not ranked (infeasible)"
        out.append(
            f'<details class="design" id="{_e(anchor(ev["id"]))}"{" open" if ev.get("pareto") and len(comp["designs"]) <= 12 else ""}>'
            f'<summary>{_pill(ev.get("verdict", "error"))}<h3>{_e(ev.get("name"))}</h3><span class="dim">{_e(rank)}'
            + (f' · <code>{_e(ev["file"])}</code>' if ev.get("file") else "") + "</span></summary>"
            + (f'<p>{_e(ev["summary"])}</p>' if ev.get("summary") else "")
            + (f'<p class="dim">{_e(ev["notes"])}</p>' if ev.get("notes") else "")
            + (f'<h3>Checks</h3><ul class="checks">{check_list}</ul>' if check_list else "")
            + _bom(ev, comp.get("currency", "usd"))
            + (f'<h3>Parameters</h3><pre>{_e(json.dumps(params, indent=1, default=json_default))}</pre>' if params else "")
            + _swaps(ev, comp) + "</details>")
    more = len(comp["designs"]) - min(len(comp["designs"]), MAX_DETAILS)
    tail = f'<p class="meta">Details for the first {MAX_DETAILS}; the other {more} are in the JSON.</p>' if more > 0 else ""
    return '<h2 id="designs">Designs</h2>' + "".join(out) + tail


def render_page(comp: Dict[str, Any]) -> str:
    s = comp["summary"]
    cols = comp["metrics"]
    objs = "".join(f'<span class="chip">{"minimise" if o["goal"] == "min" else "maximise"} '
                   f'<b>{_e(cols.get(o["metric"], {}).get("label", o["metric"]))}</b></span>' for o in comp.get("objectives") or [])
    cons = "".join(f'<span class="chip">require <b>{_e(c["metric"])}</b>'
                   + (f' ≥ {c["min"]:g}' if c.get("min") is not None else "") + (f' ≤ {c["max"]:g}' if c.get("max") is not None else "")
                   + "</span>" for c in comp.get("constraints") or [])
    what = "distinct trials" if comp.get("kind") == "search" else "designs"
    kicker = "Search leaderboard" if comp.get("kind") == "search" else "Design comparison"
    repeats = f' ({s["repeats"]} repeated combinations left out)' if s.get("repeats") else ""
    head = (f'<header><p class="kicker">{kicker}</p><h1>{_e(comp["title"])}</h1>'
            f'<p class="meta">{s["designs"]} {what}{repeats} · {s["feasible"]} feasible · '
            f'{s["pareto"]} on the Pareto front' + (f' · {s["errors"]} could not be evaluated' if s.get("errors") else "")
            + f' · evaluator: <code>{_e(comp.get("evaluator"))}</code> · {_e(comp.get("generated"))}</p>'
            f'<div class="chips">{objs}{cons}</div>'
            f'<div class="note">{"".join(f"<p>{_e(n)}</p>" for n in comp.get("notes") or [])}</div></header>')
    body = head + _chart(comp) + _leaderboard(comp) + _details(comp)
    source = "the optimiser's trials" if comp.get("kind") == "search" else "the project's designs"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{kicker} · {_e(comp["title"])}</title><style>{_CSS}</style></head>'
            f'<body><div class="wrap">{body}<footer>Written by cad-agent (cadagent.explore) from {source}.</footer></div>'
            f'<script>{_JS}</script></body></html>\n')
