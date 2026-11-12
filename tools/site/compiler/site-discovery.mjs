import {KINDS,catalogueAuditHTML} from './site-catalog.mjs';
import {topicTree,topicNodes,topicPlacement} from './site-explore-shell.mjs';
/** Derived shared discovery. Catalogue and reference feeds keep their own identities and semantics. */
import sanitizeHtml from 'sanitize-html';
import { unescapeHtml } from './site-diagrams.mjs';
import { evidenceOf, confidenceOf } from './site-references.mjs';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const text = html => unescapeHtml(sanitizeHtml(String(html ?? '').replace(/<pre\b[\s\S]*?<\/pre>/gi, ''), { allowedTags: [], allowedAttributes: {} })).replace(/\s+/g, ' ').trim();
const short = (s, n = 160) => { s = text(s); return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, '') + '…' : s; };
const slug = s => text(s).toLowerCase().replace(/[^\p{L}\p{N} -]/gu, '').replace(/\s+/g, '-').slice(0, 100);
const GROUPS = [ ['guides', 'Tools & guides'], ['lessons', 'Lessons & pitfalls'], ['references', 'References'], ['external', 'Outside tools'], ['demos', 'Demos'] ];
const safeLink = value => { try { const u = new URL(value, 'https://cad-agent.valpatel.com'); return /^https?:$/.test(u.protocol) && !u.username && !u.password ? value : null; } catch { return null; } };

/** Give existing pitfall rows real generated destinations; lesson headings already have authored/renderer anchors. */
export function prepareDiscoveryPage(page, html) {
  if (page.file !== 'docs/practice/common-issues.md') return html;
  const seen = new Map();
  return html.replace(/<tr>(\s*<td\b[^>]*>([\s\S]*?)<\/td>[\s\S]*?<\/tr>)/g, (whole, row, first) => {
    const title = first.match(/<strong>([\s\S]*?)<\/strong>/)?.[1] || first;
    const base = 'issue-' + slug(title), n = seen.get(base) || 0; seen.set(base, n + 1);
    return `<tr id="${esc(base + (n ? '-' + n : ''))}">${row}`;
  });
}

/** Sources are not deduplicated by URL: an external adoption decision and a source record are distinct roles. */
export function discoveryModel({ catalog, pages, references: m, ORIGIN, revision, pageURL }) {
  const items = [], byPage = new Map(pages.map(p => [ORIGIN + pageURL(p.file), p]));
  const add = item => { if (!safeLink(item.url)) throw new Error(`discovery: unsafe destination ${item.id}`); items.push(item); };
  for (const c of catalog.items) {
    const p = byPage.get(c.url), headings = p ? [...p.html.matchAll(/<h[234]\b[^>]*>([\s\S]*?)<\/h[234]>/g)].map(m => text(m[1])).join(' ') : '';
    const group = c.kind === 'demo' ? 'demos' : ['project', 'library', 'benchmark'].includes(c.kind) ? 'external' : c.kind === 'lesson' ? 'lessons' : 'guides';
    add({ id: 'catalogue:' + c.id, source_id: c.id, collection: 'catalogue', group, title: c.name, kind: c.kind,
      url: c.doc || c.url, summary: short(c.what || c.summary), areas: c.areas, adoption: c.status, area_maturity: c.maturity,
      cover: c.cover, search: text([c.notes, c.policy, c.license, headings].filter(Boolean).join(' ')) });
  }
  let sections = 0;
  for (const p of pages) {
    const owner = catalog.items.find(c => c.url === ORIGIN + pageURL(p.file));
    if (!owner) continue;
    if (p.section === 'lessons' && !p.file.endsWith('/README.md')) {
      const heads = [...p.html.matchAll(/<h3 id="([^"]+)">([\s\S]*?)<\/h3>/g)];
      for (let i = 0; i < heads.length; i++) {
        const h = heads[i], body = p.html.slice(h.index + h[0].length, heads[i + 1]?.index ?? p.html.length);
        add({ id: `section:${owner.id}:${h[1]}`, source_id: owner.id, collection: 'section', group: 'lessons', kind: 'Lesson entry',
          title: text(h[2]), summary: short(body.match(/<li[^>]*>\s*<strong>Rule:?<\/strong>\s*([\s\S]*?)<\/li>/i)?.[1] || body), url: owner.url + '#' + h[1], areas: owner.areas,
          search: text([p.title, short(body, 240)].join(' ')) }); sections++;
      }
    }
    if (p.file === 'docs/practice/common-issues.md') for (const row of p.html.matchAll(/<tr id="(issue-[^"]+)">\s*<td\b[^>]*>([\s\S]*?)<\/td>([\s\S]*?)<\/tr>/g)) {
      add({ id: `pitfall:${row[1]}`, source_id: owner.id, collection: 'section', group: 'lessons', kind: 'Review pitfall',
        title: short(row[2], 135), summary: short([...row[3].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)][1]?.[1] || row[3]), url: owner.url + '#' + row[1], areas: owner.areas,
        search: text([row[2], short(row[3], 240)].join(' ')) }); sections++;
    }
  }
  for (const r of m.refs.records.values()) {
    const aliases = [...m.refs.aliases].filter(([, id]) => id === r.id).map(([alias]) => alias);
    add({ id: 'reference:' + r.id, source_id: r.id, collection: 'reference', group: 'references', kind: 'Source record', title: r.title || r.id,
      summary: short(r.summary), url: ORIGIN + m.home(r.id), source_url: safeLink(r.url), areas: m.placed.get(r.id), aliases,
      evidence: evidenceOf(r) || 'snippet-only', confidence: confidenceOf(r).level, status: r.status,
      search: text([...aliases, r.org, short(r.summary, 160), ...(r.processes || [])].filter(Boolean).join(' ')) });
  }
  const ids = items.map(x => x.id); if (new Set(ids).size !== ids.length) throw new Error('duplicate discovery identity');
  return { schema: 'cad-agent-discovery/1', revision, origin: ORIGIN,
    search_fields: ['title', 'summary', 'source_id', 'search'],
    about: 'Derived search links, not new source records or independent evidence. Catalogue adoption, source evidence and area maturity remain separate.',
    source_counts: { catalogue_entries: catalog.items.length, reference_records: m.refs.records.size, lesson_and_pitfall_sections: sections }, items };
}

export function discoveryHTML(model, { areas, pages=[], pageURL=()=>'', catalog=null, legacy=false }) {
  const byCatalogue=new Map((catalog?.items||[]).map(x=>[x.id,x]));
  const kinds=Object.fromEntries(KINDS.map(k=>[k.kind,k.tab]));
  const groups=legacy?KINDS.map(k=>[k.tab,k.label]):GROUPS;
  const base=legacy?'/catalog':'/explore';
  if(legacy)model={...model,items:model.items.filter(x=>x.collection==='catalogue').map(x=>({...x,group:kinds[byCatalogue.get(x.source_id)?.kind]||'skills'}))};
  const titles = new Map(), domains = new Map();
  for (const d of areas.domains) { titles.set(d.slug, d.title); for (const a of d.areas || []) { titles.set(a.slug, a.title); domains.set(a.slug, d.slug); } }
  titles.set('unplaced', 'Not yet placed'); titles.set('cross-cutting', 'Across all areas');
  const placement=topicPlacement(areas,pages,pageURL);
  const topicsOf=item=>{
    const c=item.collection==='catalogue'?byCatalogue.get(item.source_id):null,pathname=new URL(item.url,model.origin).pathname;
    const cli=[...placement.nodes.values()].filter(n=>(n.cli||[]).some(cmd=>c?.id==='tool-'+cmd)).map(n=>n.slug);
    return placement.ancestors([...(item.areas||[]),...(placement.byPage.get(pathname)||[]),...cli]);
  };
  const localURL = value => { const u = new URL(value, model.origin); return u.origin === model.origin ? u.pathname + u.search + u.hash : u.href; };
  const label = item => item.collection === 'reference'
    ? `Source: ${item.status === 'catalogued' ? 'Not yet read' : 'Read'} · Evidence: ${item.evidence.replaceAll('-', ' ')} · Confidence: ${item.confidence}`
    : item.collection === 'section' ? item.kind : item.group === 'external' ? `${item.kind === 'project' ? 'Project' : item.kind} · Adoption: ${item.adoption}` : item.kind === 'tool' ? 'Command' : item.kind;
  const row = (item, i) => { const c=item.collection==='catalogue'?byCatalogue.get(item.source_id):null;return `<li data-item id="${esc(legacy?item.source_id:item.id)}"${c?` data-format="${esc(c.kind)}"${legacy?` data-type="${esc(c.type)}" data-status="${esc(c.status)}"`:''} data-licence="${esc(c.licence_family||'')}"${legacy?` data-maturity="${esc(c.maturity||'')}"`:''} data-sort-recent="${esc(c.updated||'')}"${c.stars!=null?` data-sort-stars="${esc(c.stars)}"`:''} data-demo="${c.demo?'1':''}"${legacy?` data-sort-maturity="${areas.maturity.findIndex(x=>x.level===c.maturity)+1}"`:''}`:''} data-area="${esc(topicsOf(item).join(' '))}"${item.evidence?` data-evidence="${esc(item.evidence)}"`:''}${item.adoption?` data-adoption="${esc(item.adoption)}"`:''} data-search-extra="${esc([item.search, ...(item.areas || []).map(a => titles.get(a))].join(' '))}"${i >= 2 ? ' data-over' : ''}><a href="${esc(localURL(item.url))}"${!legacy&&c?` id="${esc(c.id)}" class="anchor explore-anchor"`:""}><span class="result-title">${esc(item.title)}</span> ${item.collection === 'reference' ? '' : `<span class="result-summary">${esc(item.summary)}</span>`}</a> <span class="result-meta">${esc(label(item))}</span>${c&&!legacy?`<details class="result-details" data-catalogue-id="${esc(c.id)}"><summary>Details${c.license?' · '+esc(c.license):''}</summary></details>`:''}${c&&legacy?`<details class="result-details"><summary>Details${c.audit?' · review observations':''}${c.license?' · '+esc(c.license):''}</summary>${c.how?`<cad-copy text="${esc(c.how)}" label="Copy call"><code>${esc(c.how)}</code></cad-copy>`:''}${c.cover?`<a href="${esc(localURL(c.demo||c.doc||c.url))}"><img class="result-cover" src="${esc(localURL(c.cover))}" width="400" height="300" alt="Example for ${esc(c.name)}" loading="lazy"></a>`:''}${c.markdown?`<p><a href="${esc(localURL(c.markdown))}">Read Markdown</a></p>`:''}${c.mode?`<p>Example: ${esc(c.mode)}</p>`:''}${c.stars!=null?`<p>GitHub stars: ${Number(c.stars).toLocaleString('en-US')}</p>`:''}${catalogueAuditHTML(c.audit,c.notes,c.policy)}${c.related?.length?`<p>Related: ${c.related.map(id=>`<a href="/explore#${esc(id)}">${esc(id)}</a>`).join(', ')}</p>`:''}</details>`:''}</li>`; };
  const topic = (slug, title) => `<a href="/explore?area=${esc(slug)}" data-gallery-link data-facet="area" data-value="${esc(slug)}">${esc(title)} <span data-count></span></a>`;
  const tree = topicTree({areas,pages,pageURL,browse:true,sprite:false});
  const localCover = cover => { const u = new URL(cover, model.origin); if (u.origin !== model.origin) throw new Error('discovery: cover is not site-owned'); return u.pathname + u.search; };
  const demoItems = model.items.filter(x => x.group === 'demos').slice(0, 3);
  const option = (name, value, title) => `<label><input type="checkbox" name="${name}" value="${esc(value)}"> ${esc(title)} <span data-count></span></label>`;
  return `<cad-gallery data-revision="${esc(model.revision)}" class="catalog discovery" tab-param="kind" limit="3" browse-limit="2" item-noun="result" items-noun="results" data-open-groups search-ids sort-label=".result-title" data-overview>
<header class="discover-hero"><p class="eyebrow">Explore hardware knowledge</p><h1>Find the next useful step.</h1><p>Tools to try, practical lessons and the sources behind the design.</p>
<label class="discover-search" data-gallery-js><span>Search everything</span><input type="search" name="q" data-gallery-search placeholder="Counterbores, snap fits, a source ID…" autocomplete="off"></label>
<p class="discover-quick" data-gallery-js>Try ${['counterbores','disassembly','snap fits','PEM'].map(q => `<a href="/explore?q=${encodeURIComponent(q)}" data-gallery-link>${esc(q)}</a>`).join('')}</p>
<p class="discover-fallback">Browse a result group or open a deeper view below. Search and filters appear when available.</p>
<noscript><p>Open a result group below or use the deeper views. Search and topic filters need JavaScript; topic groups and reference tables remain available.</p></noscript></header>
<section class="discover-topics" data-gallery-js aria-label="Explore by topic">${areas.domains.map(d => `<a href="/explore?area=${esc(d.slug)}" data-gallery-link data-facet="area" data-value="${esc(d.slug)}" data-tone="${esc(d.slug)}"><svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><use href="/web/topic-icons.svg#g-${esc(d.slug)}"/></svg><b>${esc(d.title)}</b><span>${esc(short(d.scope, 100))}</span></a>`).join('')}</section>
<section class="discover-demos" aria-label="Try a working example">${demoItems.map(d => `<a href="${esc(localURL(d.url))}"><img src="${esc(localCover(d.cover))}" alt="" width="400" height="225" loading="lazy"><b>${esc(d.title)}</b><span>Try or watch →</span></a>`).join('')}</section>
<div class="discover-layout"><aside><details class="discover-refine" data-gallery-js open><summary>Topics and filters</summary><nav aria-label="Topics">${tree}</nav>
<details class="discover-filter-options" data-gallery-js><summary>Refine results</summary><form data-gallery-filters><fieldset><legend>Entry type</legend>${[...new Set((catalog?.items||[]).map(x=>x.kind))].map(x=>option('format',x,x)).join('')}${option('demo','1','Has a working example')}</fieldset><fieldset><legend>Licence</legend>${[['permissive','Permissive'],['copyleft','Copyleft'],['other','Restricted or unrecorded']].map(([v,t])=>option('licence',v,t)).join('')}</fieldset><fieldset><legend>Source evidence</legend>${['snippet-only','read','verified-at-source','encoded','measured'].map(x => option('evidence', x, x.replaceAll('-', ' '))).join('')}</fieldset><fieldset><legend>Outside-tool adoption</legend>${[...new Set((catalog?.items||[]).filter(x=>['project','library','benchmark'].includes(x.kind)).map(x=>x.status))].sort().map(x => option('adoption', x, x)).join('')}</fieldset>${legacy?`<div hidden>${[...new Set((catalog?.items||[]).map(x=>x.type))].map(x=>option('type',x,x)).join('')}${[...new Set((catalog?.items||[]).map(x=>x.status))].map(x=>option('status',x,x)).join('')}${areas.maturity.map(x=>option('maturity',x.level,'Saved area scope')).join('')}</div>`:''}</form></details></details><p class="discover-deeper">Deeper views<br><a href="/docs/toolkit">Command &amp; Python API manual</a><a href="/references">Reference evidence &amp; coverage</a><a href="/docs/common-issues">Review checklist</a><a href="/research/landscape">Tool landscape &amp; comparisons</a></p></aside>
<div id="discover-results" data-gallery-results><nav class="discover-tabs" data-gallery-js data-gallery-tabs aria-label="Result types"><a href="#discover-results" data-tab="">All</a>${groups.map(([key,title]) => `<a href="${base}?kind=${key}#discover-results" data-tab="${key}">${title} <span data-count></span></a>`).join('')}</nav>
<div class="discover-status"><p role="status" aria-live="polite" data-gallery-status>${model.items.length} search links</p><button type="button" data-gallery-clear data-gallery-js>Clear search and filters</button><label data-gallery-js>Sort <select data-gallery-sort><option value="featured">By type</option><option value="az">A–Z</option><option value="recent" data-dir="desc">Recently updated</option><option value="stars" data-dir="desc">Most stars</option>${legacy?'<option value="maturity" data-dir="desc" hidden>Saved area order</option>':''}</select></label></div><div data-gallery-chips aria-label="Active filters"></div><p data-gallery-empty hidden>No matches. Try fewer words or clear the filters.</p>
${groups.map(([key,title]) => { const list = model.items.filter(x => x.group === key); return `<details class="discover-group" id="${esc(key)}" data-group="${key}" data-more>${legacy?KINDS.filter(k=>k.tab===key&&k.anchor).map(k=>`<span id="${esc(k.anchor)}"></span>`).join(''):''}<summary><h2>${title} <span data-group-count>${list.length}</span></h2></summary><ul class="discover-results">${list.map(row).join('')}</ul><a href="${base}?kind=${key}" data-gallery-link data-gallery-more data-gallery-js>See all <span data-group-count>${list.length}</span> ${title.toLowerCase()} →</a></details>`; }).join('')}
<details class="discover-about"><summary>About these results</summary><p class="discover-scope">${model.source_counts.catalogue_entries} catalogue entries · ${model.source_counts.reference_records} reference records · ${model.source_counts.lesson_and_pitfall_sections} lesson and pitfall sections. These are search links with different roles, not additional independent sources.</p><p class="discover-scope">Adoption describes our use of an outside tool. Evidence describes checking of a source. <a href="/discovery.json">Discovery JSON</a> · <a href="/catalog.json">Complete entry metadata (JSON)</a></p></details></div></div></cad-gallery>`;
}
