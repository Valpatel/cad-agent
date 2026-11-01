"""Review and evidence (docs/areas.yaml: practice / design-process and review-and-evidence): integrity gates (gates),
the design dossier (dossier), review packets (packet) and evidence hashes (evidence).

This module itself is the reusable in-page review workbench for PCBs, housings and multi-part assemblies
(``review_html``): it was the flat ``cadagent.review`` module, which became this package, so that path keeps working
as it was, like ``cadagent.geometry``. Old flat paths of the modules now inside (``cadagent.gates`` and so on) still
import until v0.7.0, see ``cadagent._moved``."""
from __future__ import annotations
from pathlib import Path
import html,json
from cadagent.review.evidence import hashes_are_current
from urllib.parse import quote

_SCRIPT = Path(__file__).resolve().parent.parent / 'webkit' / 'review.js'


def _local(root: Path, rel) -> Path | None:
    """The resolved file when ``rel`` names a regular file inside ``root``; None otherwise (missing, outside, symlink out)."""
    if not isinstance(rel, str) or not rel:
        return None
    base = Path(root).resolve()
    path = (base / rel).resolve()
    return path if base in path.parents and path.is_file() else None


def review_html(root: Path, manifest: dict, prefix: str = '../') -> str:
    """Render trusted project-local assets; unsupported/missing views stay visible as gaps.

    The page works as a static file: every panel is rendered visible and the inlined review script (webkit/review.js)
    turns them into tabs. Report and download files outside the project root are treated as missing.
    """
    e=lambda x:html.escape(str(x),quote=True)
    groups=manifest.get('groups',[])
    if not groups:return ''
    buttons=[];panels=[]
    for i,g in enumerate(groups):
        buttons.append(f'<button type="button" data-review-group="{i}" aria-pressed="{str(i==0).lower()}">{e(g.get("title","Design"))}</button>')
        tabs=[];views=[]
        for j,v in enumerate(g.get('views',[])):
            title=e(v.get('title','View'));rel=v.get('file','')
            valid=_local(root,rel) is not None
            kind=v.get('kind','image');url=e(prefix+str(rel))
            caption=e(v.get("caption",""))
            tabs.append(f'<button type="button" data-review-view="{j}" aria-pressed="{str(j==0).lower()}">{title}</button>')
            if kind=='model':
                url=e('/_cadagent/kit/viewer.html?manifest=/'+quote(str(rel),safe='/'))
                caption=(caption+' · ' if caption else '')+'The 3D viewer needs the local server (<code>cad-agent site --serve</code>)'
            if not valid:body=f'<p class="notice">Pending asset: {e(rel)}</p>'
            elif kind in {'image','svg'}:body=f'<img src="{url}" alt="{title}" loading="lazy">'
            elif kind in {'pdf','html','model'}:body=f'<iframe src="{url}" title="{title}" loading="lazy"></iframe>'
            else:body=f'<p class="notice">Unsupported view type: {e(kind)}</p>'
            views.append(f'<div class="review-view" data-review-panel="{j}">{body}<p>{caption} · <a href="{url}">Open full size / download</a></p></div>')
        reports=[]
        for report in g.get('reports',[]):
            rel=report.get('file','');path=_local(root,rel)
            try:
                if path is None:raise OSError(f'{rel} is missing or outside the project')
                data=json.loads(path.read_text());value=data
                for key in report.get('pass_key','pass').split('.'):value=value[key]
                state='PASS' if value is True else 'PENDING / FAIL'
                if 'report_sha256' in data:
                    from cadagent.electrical.pcb import evidence_is_current
                    if not evidence_is_current(root,data):state='STALE'
                if not hashes_are_current(root,data):state='STALE'
            except (OSError,ValueError,KeyError,TypeError):state='UNAVAILABLE'
            reports.append(f'<a class="review-report" href="{e(prefix+str(rel))}"><b>{e(report.get("title","Report"))}</b><span>{state}</span></a>')
        downloads=[]
        for d in g.get('downloads',[]):
            rel=d.get('file','') if isinstance(d,dict) else ''
            title=e((d.get('title') if isinstance(d,dict) else '') or Path(str(rel)).name or 'Download')
            if _local(root,rel) is None:downloads.append(f'<span class="notice">Pending download: {title} ({e(rel or "no file given")})</span>')
            else:downloads.append(f'<a href="{e(prefix+rel)}">{title}</a>')
        panels.append(f'<section data-review-group-panel="{i}"><p>{e(g.get("summary",""))}</p><nav class="review-tabs" aria-label="Views">{"".join(tabs)}</nav>{"".join(views)}<div class="review-reports">{"".join(reports)}</div><nav class="links">{"".join(downloads)}</nav></section>')
    return ('<section id="design-review" class="review-workbench"><h2>Design review</h2><nav class="review-tabs" aria-label="Design variants">'+''.join(buttons)+'</nav>'+''.join(panels)+'</section><script>'+_SCRIPT.read_text()+'</script>')

REVIEW_CSS='''
.review-workbench{margin:24px 0;padding:24px;background:var(--card,#fff);color:var(--ink,#202227);border:1px solid var(--line,#e4e0d7);border-radius:12px}
.review-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.review-tabs button{font:inherit;color:inherit;background:transparent;border:1px solid #647987;border-radius:6px;padding:10px 15px;cursor:pointer}.review-tabs button[aria-pressed=true]{background:#14635f;color:white;border-color:#57c7b6}
.review-view{background:#eff1ed;border-radius:8px;color:#14232d;overflow:hidden}.review-view img,.review-view iframe{display:block;width:100%;height:620px;object-fit:contain;border:0}.review-view p{padding:8px 16px;font-size:.85em}.review-view a{color:#07566b}.review-reports{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.review-report{border:1px solid #647987;border-radius:6px;padding:10px 14px;display:flex;gap:20px;align-items:center;text-decoration:none}.review-report span{font-size:.8em}.review-workbench [hidden]{display:none!important}@media(max-width:700px){.review-workbench{padding:12px}.review-view img,.review-view iframe{height:430px}}
'''
