/** Derived shared discovery. Catalogue and reference feeds keep their own identities and semantics. */
import sanitizeHtml from 'sanitize-html';
import { unescapeHtml } from './site-diagrams.mjs';
import { evidenceOf, confidenceOf } from './site-references.mjs';
import { glyphSprite } from './catalog-art.mjs';

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
      search: text([r.id, ...aliases, r.org, short(r.summary, 160), ...(r.processes || [])].filter(Boolean).join(' ')) });
  }
  const ids = items.map(x => x.id); if (new Set(ids).size !== ids.length) throw new Error('duplicate discovery identity');
  return { schema: 'cad-agent-discovery/1', revision, origin: ORIGIN,
    about: 'Derived search links, not new source records or independent evidence. Catalogue adoption, source evidence and area maturity remain separate.',
    source_counts: { catalogue_entries: catalog.items.length, reference_records: m.refs.records.size, lesson_and_pitfall_sections: sections }, items };
}

export function discoveryHTML(model, { areas }) {
  const titles = new Map(), domains = new Map();
  for (const d of areas.domains) { titles.set(d.slug, d.title); for (const a of d.areas || []) { titles.set(a.slug, a.title); domains.set(a.slug, d.slug); } }
  titles.set('unplaced', 'Not yet placed'); titles.set('cross-cutting', 'Across all areas');
  const topicsOf = item => [...new Set([...(item.areas || []), ...(item.areas || []).map(a => domains.get(a)).filter(Boolean)])];
  const label = item => item.collection === 'reference'
    ? `Source: ${item.status === 'catalogued' ? 'Not yet read' : 'Read'} · Evidence: ${item.evidence.replaceAll('-', ' ')} · Confidence: ${item.confidence}`
    : item.collection === 'section' ? item.kind : item.group === 'external' ? `${item.kind === 'project' ? 'Project' : item.kind} · Adoption: ${item.adoption}` : item.kind === 'tool' ? 'Command' : item.kind;
  const row = (item, i) => `<li data-item id="${esc(item.id)}" data-area="${esc(topicsOf(item).join(' '))}" data-evidence="${esc(item.evidence || '')}" data-adoption="${esc(item.adoption || '')}" data-sort-az="${esc(item.title.toLowerCase())}" data-search-extra="${esc([item.search, ...(item.areas || []).map(a => titles.get(a))].join(' '))}"${i >= 3 ? ' data-over' : ''}><a href="${esc(item.url)}"><span class="result-title">${esc(item.title)}</span> ${item.collection === 'reference' ? '' : `<span class="result-summary">${esc(item.summary)}</span>`}</a> <span class="result-meta">${esc(label(item))}</span></li>`;
  const topic = (slug, title) => `<a href="/explore?area=${esc(slug)}" data-gallery-link data-facet="area" data-value="${esc(slug)}">${esc(title)} <span data-count></span></a>`;
  const topicTree = areas.domains.map(d => `<details><summary>${esc(d.title)}</summary>${topic(d.slug, 'All ' + d.title)}${(d.areas || []).map(a => topic(a.slug, a.title)).join('')}</details>`).join('');
  const localCover = cover => { const u = new URL(cover, model.origin); if (u.origin !== model.origin) throw new Error('discovery: cover is not site-owned'); return u.pathname + u.search; };
  const demoItems = model.items.filter(x => x.group === 'demos').slice(0, 3);
  const option = (name, value, title) => `<label><input type="checkbox" name="${name}" value="${esc(value)}"> ${esc(title)} <span data-count></span></label>`;
  return `${glyphSprite(areas.domains.map(d => d.slug))}<cad-gallery class="catalog discovery" tab-param="kind" limit="3" item-noun="result" items-noun="results" data-open-groups data-overview>
<header class="discover-hero"><p class="eyebrow">Explore hardware knowledge</p><h1>Find the next useful step.</h1><p>Tools to try, practical lessons and the sources behind the design.</p>
<label class="discover-search" data-gallery-js><span>Search everything</span><input type="search" name="q" data-gallery-search placeholder="Counterbores, snap fits, a source ID…" autocomplete="off"></label>
<p class="discover-quick" data-gallery-js>Try ${['counterbores','disassembly','snap fits','PEM'].map(q => `<a href="/explore?q=${encodeURIComponent(q)}" data-gallery-link>${esc(q)}</a>`).join('')}</p>
<p class="discover-fallback">Interactive search is unavailable. Browse the full catalogue or reference tables in the deeper views below.</p>
<noscript><p>Open a result group below or use the deeper views. Search and topic filters need JavaScript; the full catalogue and reference tables remain available.</p></noscript></header>
<section class="discover-topics" data-gallery-js aria-label="Explore by topic">${areas.domains.map(d => `<a href="/explore?area=${esc(d.slug)}" data-gallery-link data-facet="area" data-value="${esc(d.slug)}" data-tone="${esc(d.slug)}"><svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><use href="#g-${esc(d.slug)}"/></svg><b>${esc(d.title)}</b><span>${esc(short(d.scope, 100))}</span></a>`).join('')}</section>
<section class="discover-demos" aria-label="Try a working example">${demoItems.map(d => `<a href="${esc(d.url)}"><img src="${esc(localCover(d.cover))}" alt="" width="400" height="225" loading="lazy"><b>${esc(d.title)}</b><span>Try or watch →</span></a>`).join('')}</section>
<div class="discover-layout"><aside><details class="discover-refine" data-gallery-js><summary>Topics and filters</summary><nav aria-label="Topics">${topicTree}${topic('unplaced', 'Not yet placed')}${topic('cross-cutting', 'Across all areas')}</nav>
<form data-gallery-filters><fieldset><legend>Source evidence</legend>${['snippet-only','read','verified-at-source','encoded','measured'].map(x => option('evidence', x, x.replaceAll('-', ' '))).join('')}</fieldset><fieldset><legend>Outside-tool adoption</legend>${[...new Set(model.items.filter(x => x.group === 'external').map(x => x.adoption))].sort().map(x => option('adoption', x, x)).join('')}</fieldset></form></details><p class="discover-deeper">Deeper views<br><a href="/catalog">Full catalogue</a><a href="/docs/toolkit">Command &amp; Python API manual</a><a href="/references">Reference evidence &amp; coverage</a><a href="/docs/common-issues">Review checklist</a><a href="/research/landscape">Tool landscape &amp; comparisons</a></p></aside>
<div id="discover-results" data-gallery-results><nav class="discover-tabs" data-gallery-js data-gallery-tabs aria-label="Result types"><a href="#discover-results" data-tab="">All</a>${GROUPS.map(([key,title]) => `<a href="?kind=${key}#discover-results" data-tab="${key}">${title} <span data-count></span></a>`).join('')}</nav>
<div class="discover-status"><p role="status" aria-live="polite" data-gallery-status>${model.items.length} search links</p><button type="button" data-gallery-clear data-gallery-js>Clear search and filters</button><label data-gallery-js>Sort <select data-gallery-sort><option value="featured">By type</option><option value="az">A–Z</option></select></label></div><div data-gallery-chips aria-label="Active filters"></div><p data-gallery-empty hidden>No matches. Try fewer words or clear the filters.</p>
${GROUPS.map(([key,title]) => { const list = model.items.filter(x => x.group === key); return `<details class="discover-group" data-group="${key}" data-more><summary><h2>${title} <span data-group-count>${list.length}</span></h2></summary><ul class="discover-results">${list.map(row).join('')}</ul><a href="/explore?kind=${key}" data-gallery-link data-gallery-more data-gallery-js>See all <span data-group-count>${list.length}</span> ${title.toLowerCase()} →</a></details>`; }).join('')}
<details class="discover-about"><summary>About these results</summary><p class="discover-scope">${model.source_counts.catalogue_entries} catalogue entries · ${model.source_counts.reference_records} reference records · ${model.source_counts.lesson_and_pitfall_sections} lesson and pitfall sections. These are search links with different roles, not additional independent sources.</p><p class="discover-scope">Adoption describes our use of an outside tool. Evidence describes checking of a source. Area maturity describes a topic, not a validation of each result. <a href="/discovery.json">Discovery JSON</a></p></details></div></div></cad-gallery>`;
}
