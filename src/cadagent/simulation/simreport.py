"""A standalone HTML page for simulation and optimisation results: before/after metrics, figures, videos, limits.

    from cadagent.simulation.simreport import write_report, metric
    write_report('preview/simulation.html', 'J501 Rev 0.8: material, strength, airflow', sections=[
        {'id': 'material', 'title': 'Filament', 'summary': '...',
         'metrics': [metric('Lid', 164.4, 92.1, 'g', better='lower')],
         'figures': [{'src': 'structure-lid.png', 'caption': '...'}],
         'videos': [{'src': 'thermal-flow.mp4', 'caption': '...'}],
         'limits': ['linear elastic, ...']},
    ], meta={'Revision': '0.8', 'Generated': '2026-10-26'})

The page carries its CSS inline and only relative links (it opens from file:// and from a static server), follows
the light/dark colour scheme, and is readable at phone width. A metric's change is shown with an arrow and a word
(better / worse / same), never colour alone.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from cadagent.project import source_stamp

_CSS = """
:root{color-scheme:light dark;--bg:#f4f6f8;--surface:#fff;--surface-2:#eef2f5;--text:#16212b;--muted:#5a6873;
--line:#dde5eb;--accent:#1f5f8b;--good:#1d7a3e;--good-bg:#e3f4e8;--bad:#b3261e;--bad-bg:#fbe5e3;--same:#5a6873;
--header:#15303b;--header-text:#fff;--header-muted:#b8c7cf}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1418;--surface:#171e24;--surface-2:#1f2830;
--text:#e4eaef;--muted:#9aa8b3;--line:#2b3640;--accent:#7db7e0;--good:#6fd394;--good-bg:#173523;--bad:#ff8a80;
--bad-bg:#3d1a18;--same:#9aa8b3;--header:#0b1a20}}
:root[data-theme="dark"]{--bg:#0f1418;--surface:#171e24;--surface-2:#1f2830;--text:#e4eaef;--muted:#9aa8b3;
--line:#2b3640;--accent:#7db7e0;--good:#6fd394;--good-bg:#173523;--bad:#ff8a80;--bad-bg:#3d1a18;--same:#9aa8b3;--header:#0b1a20}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}header.top{background:var(--header);color:var(--header-text);padding:28px 16px 22px}
header.top .in,main{max-width:1180px;margin:0 auto}header.top h1{margin:0 0 6px;font-size:1.7rem;line-height:1.2;font-weight:600}
header.top p{margin:0;color:var(--header-muted)}.meta{display:flex;flex-wrap:wrap;gap:4px 16px;margin:12px 0 0;padding:0;list-style:none;color:var(--header-muted);font-size:.88rem}
.meta b{color:var(--header-text);font-weight:600}main{padding:20px 16px 48px}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}nav.toc a{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:4px 12px;text-decoration:none;font-size:.9rem}
section.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px 20px 16px;margin:0 0 20px}
section.card h2{margin:0 0 6px;font-size:1.3rem}section.card .summary{margin:0 0 14px;color:var(--text)}
.callout{border-left:4px solid var(--accent);background:var(--surface-2);padding:10px 14px;border-radius:6px;margin:0 0 14px}
.callout.warn{border-color:#c98500}
table.metrics{width:100%;border-collapse:collapse;margin:4px 0 16px;font-variant-numeric:tabular-nums}
table.metrics th,table.metrics td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.metrics th:first-child,table.metrics td:first-child{text-align:left;white-space:normal}
table.metrics thead th{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
.chg{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.85rem}
.chg.better{color:var(--good);background:var(--good-bg)}.chg.worse{color:var(--bad);background:var(--bad-bg)}.chg.same{color:var(--same)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:14px;margin:6px 0 10px}
figure{margin:0;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;overflow:hidden}
figure img,figure video{display:block;width:100%;height:auto;background:#eef2f5}
figcaption{padding:8px 12px;font-size:.88rem;color:var(--muted)}
details.limits{margin-top:6px;color:var(--muted);font-size:.9rem}details.limits summary{cursor:pointer;color:var(--text)}
.table-wrap{overflow-x:auto}footer{color:var(--muted);font-size:.85rem;max-width:1180px;margin:0 auto;padding:0 16px 32px}
"""


def metric(label: str, before, after, unit: str = '', better: Optional[str] = 'lower', digits: int = 1, note: str = '') -> dict:
    """One row of a comparison table. ``better``: 'lower', 'higher' or None (no judgement)."""
    return {'label': label, 'before': before, 'after': after, 'unit': unit, 'better': better, 'digits': digits, 'note': note}


def _fmt(v, digits):
    if v is None:
        return '–'
    if isinstance(v, (int, float)):
        return f'{v:,.{digits}f}'
    return html.escape(str(v))


def _change(m) -> str:
    b, a = m['before'], m['after']
    if not isinstance(b, (int, float)) or not isinstance(a, (int, float)):
        return ''
    d = a - b
    pct = f' ({d / b * 100:+.0f} %)' if b else ''
    if abs(d) < 10 ** -m['digits'] / 2:
        return '<span class="chg same">= same</span>'
    arrow = '▲' if d > 0 else '▼'
    if m['better'] is None:
        return f'<span class="chg same">{arrow} {d:+,.{m["digits"]}f}{pct}</span>'
    good = (d < 0) == (m['better'] == 'lower')
    word = 'better' if good else 'worse'
    return f'<span class="chg {word}">{arrow} {d:+,.{m["digits"]}f}{pct} · {word}</span>'


def _metrics(rows: Sequence[dict], heads=('Before', 'After')) -> str:
    out = [f'<div class="table-wrap"><table class="metrics"><thead><tr><th>Measure</th><th>{heads[0]}</th><th>{heads[1]}</th>'
           '<th>Change</th></tr></thead><tbody>']
    for m in rows:
        u = f' {html.escape(m["unit"])}' if m['unit'] else ''
        note = f'<br><small style="color:var(--muted)">{html.escape(m["note"])}</small>' if m.get('note') else ''
        out.append(f'<tr><td>{html.escape(m["label"])}{note}</td><td>{_fmt(m["before"], m["digits"])}{u}</td>'
                   f'<td>{_fmt(m["after"], m["digits"])}{u}</td><td>{_change(m)}</td></tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


def _media(items, video=False):
    if not items:
        return ''
    out = ['<div class="grid">']
    for it in items:
        src, cap = html.escape(it['src']), html.escape(it.get('caption', ''))
        if video:
            poster = f' poster="{html.escape(it["poster"])}"' if it.get('poster') else ''
            body = f'<video src="{src}" controls loop muted playsinline preload="metadata"{poster}></video>'
        else:
            body = f'<a href="{src}"><img src="{src}" alt="{cap}" loading="lazy"></a>'
        out.append(f'<figure>{body}<figcaption>{cap}</figcaption></figure>')
    out.append('</div>')
    return ''.join(out)


def render(title: str, sections: List[dict], subtitle: str = '', meta: Optional[Dict[str, str]] = None, footer: str = '',
           written_to: Optional[Path] = None) -> str:
    """The page. Without a ``Generated`` entry in ``meta`` it is dated by ``cadagent.project.source_stamp`` for the
    current folder (the project, when the script runs from its root): ``SOURCE_DATE_EPOCH``, else the last commit
    that changed the folder other than ``written_to``, never the wall clock, so a rebuild writes the same bytes (#150)."""
    meta = dict(meta or {})
    if 'Generated' not in meta:
        meta['Generated'] = source_stamp(Path.cwd(), outputs=[written_to] if written_to else ())
    li = ''.join(f'<li><b>{html.escape(k)}</b> {html.escape(str(v))}</li>' for k, v in meta.items())
    toc = ''.join(f'<a href="#{html.escape(s["id"])}">{html.escape(s["title"])}</a>' for s in sections)
    body = []
    for s in sections:
        parts = [f'<section class="card" id="{html.escape(s["id"])}"><h2>{html.escape(s["title"])}</h2>']
        if s.get('summary'):
            parts.append(f'<p class="summary">{s["summary"]}</p>')       # trusted HTML from the project script
        for c in s.get('callouts', []):
            parts.append(f'<div class="callout{" warn" if c.get("warn") else ""}">{c["html"]}</div>')
        if s.get('metrics'):
            parts.append(_metrics(s['metrics'], s.get('heads', ('Before', 'After'))))
        parts.append(_media(s.get('figures')))
        parts.append(_media(s.get('videos'), video=True))
        if s.get('limits'):
            items = ''.join(f'<li>{html.escape(x)}</li>' for x in s['limits'])
            parts.append(f'<details class="limits"><summary>Assumptions and limits</summary><ul>{items}</ul></details>')
        parts.append('</section>')
        body.append(''.join(parts))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>'
            f'<header class="top"><div class="in"><h1>{html.escape(title)}</h1>'
            f'{f"<p>{html.escape(subtitle)}</p>" if subtitle else ""}<ul class="meta">{li}</ul></div></header>'
            f'<main><nav class="toc">{toc}</nav>{"".join(body)}</main>'
            f'<footer>{footer or "Written by cad-agent (cadagent.simulation.simreport). Simulation is evidence for a design decision, not proof: test the printed part."}</footer>'
            '</body></html>')


def write_report(path, title: str, sections: List[dict], subtitle: str = '', meta: Optional[Dict[str, str]] = None, footer: str = '') -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(title, sections, subtitle, meta, footer, written_to=p))
    return p
