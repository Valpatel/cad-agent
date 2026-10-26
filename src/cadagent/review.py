"""Reusable in-page review workbench for PCBs, housings and multi-part assemblies."""
from pathlib import Path
import html,json,hashlib
from urllib.parse import quote

def review_html(root: Path, manifest: dict, prefix: str = '../') -> str:
    """Render trusted project-local assets; unsupported/missing views stay visible as gaps."""
    e=lambda x:html.escape(str(x),quote=True)
    groups=manifest.get('groups',[])
    if not groups:return ''
    buttons=[];panels=[]
    for i,g in enumerate(groups):
        buttons.append(f'<button type="button" data-review-group="{i}" aria-pressed="{str(i==0).lower()}">{e(g.get("title","Design"))}</button>')
        tabs=[];views=[]
        for j,v in enumerate(g.get('views',[])):
            title=e(v.get('title','View'));rel=v.get('file','');path=(root/rel).resolve()
            valid=root.resolve() in path.parents and path.is_file()
            kind=v.get('kind','image');url=e(prefix+rel)
            tabs.append(f'<button type="button" data-review-view="{j}" aria-pressed="{str(j==0).lower()}">{title}</button>')
            if kind=='model':url=e('/_cadagent/kit/viewer.html?manifest=/'+quote(rel,safe='/'))
            if not valid:body=f'<p class="notice">Pending asset: {e(rel)}</p>'
            elif kind in {'image','svg'}:body=f'<img src="{url}" alt="{title}" loading="lazy">'
            elif kind in {'pdf','html','model'}:body=f'<iframe src="{url}" title="{title}" loading="lazy"></iframe>'
            else:body=f'<p class="notice">Unsupported view type: {e(kind)}</p>'
            views.append(f'<div class="review-view" data-review-panel="{j}" {"hidden" if j else ""}>{body}<p>{e(v.get("caption",""))} · <a href="{url}">Open full size / download</a></p></div>')
        reports=[]
        for report in g.get('reports',[]):
            rel=report.get('file','');path=root/rel
            try:
                data=json.loads(path.read_text());value=data
                for key in report.get('pass_key','pass').split('.'):value=value[key]
                state='PASS' if value is True else 'PENDING / FAIL'
                if 'source_sha256' in data:
                    from cadagent.pcb import evidence_is_current
                    if not evidence_is_current(root,data):state='STALE'
                for source, expected in data.get('mechanical_sources', {}).items():
                    source_path=(root/source).resolve()
                    if root.resolve() not in source_path.parents or not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest()!=expected:
                        state='STALE'
            except (OSError,ValueError,KeyError,TypeError):state='UNAVAILABLE'
            reports.append(f'<a class="review-report" href="{e(prefix+rel)}"><b>{e(report.get("title","Report"))}</b><span>{state}</span></a>')
        downloads=''.join(f'<a href="{e(prefix+d["file"])}">{e(d.get("title",Path(d["file"]).name))}</a>' for d in g.get('downloads',[]))
        panels.append(f'<section data-review-group-panel="{i}" {"hidden" if i else ""}><p>{e(g.get("summary",""))}</p><nav class="review-tabs" aria-label="Views">{"".join(tabs)}</nav>{"".join(views)}<div class="review-reports">{"".join(reports)}</div><nav class="links">{downloads}</nav></section>')
    return ('<section class="review-workbench"><h2>Design review</h2><nav class="review-tabs" aria-label="Design variants">'+''.join(buttons)+'</nav>'+''.join(panels)+'</section><script type="module" src="/_cadagent/kit/review.js"></script>')

REVIEW_CSS='''
.review-workbench{margin:24px 0;padding:24px;background:var(--panel,#14232d);border:1px solid #47606d;border-radius:12px}
.review-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.review-tabs button{font:inherit;color:inherit;background:transparent;border:1px solid #647987;border-radius:6px;padding:10px 15px;cursor:pointer}.review-tabs button[aria-pressed=true]{background:#14635f;color:white;border-color:#57c7b6}
.review-view{background:#eff1ed;border-radius:8px;color:#14232d;overflow:hidden}.review-view img,.review-view iframe{display:block;width:100%;height:620px;object-fit:contain;border:0}.review-view p{padding:8px 16px;font-size:.85em}.review-view a{color:#07566b}.review-reports{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.review-report{border:1px solid #647987;border-radius:6px;padding:10px 14px;display:flex;gap:20px;align-items:center;text-decoration:none}.review-report span{font-size:.8em}.review-workbench [hidden]{display:none!important}@media(max-width:700px){.review-workbench{padding:12px}.review-view img,.review-view iframe{height:430px}}
'''
