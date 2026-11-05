/** The reference knowledge base on cad-agent.valpatel.com (#323 phase 3, #118 items 2 and 3).
 *
 * The site gets:
 * - /references: every area with records, charted by evidence;
 * - /references/<area>: charts of the area's records by evidence, confidence, kind, licence and process, a table you
 *   can filter, and the coverage rows. Each page has a Markdown twin;
 * - catalog/references/index.json (areas with counts) and catalog/references/<area>.json (the records);
 * - [ref:<id>] in any page, rendered as a link to the record's row and to the source;
 * - one llms.txt line per area;
 * - docs/experts.md.
 *
 * Records are not catalogue cards: catalog.json and llms-full.txt carry none. An agent reads index.json, then one
 * area's file. A record is listed in every area it is placed in. A record whose `areas` match no docs/areas.yaml slug
 * goes to /references/unplaced, as outside projects do in the catalogue.
 *
 * tools/build-site.mjs reads the committed registry: research/references.yaml, the shards in research/references/
 * and docs/areas.yaml. `node tools/site-references.mjs --experts` rewrites docs/experts.md from the working tree, and
 * `--experts --check` exits 1 when it is out of date. Every number and badge is computed from the records here, and
 * nothing is typed in by hand. Confidence is the record's own block, which `python -m cadagent.review.references
 * --check` holds equal to what its evidence gives.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import YAML from 'yaml';
import { safeUrl } from './site-html.mjs';

export const SCHEMA = 'cad-agent-references/1';
export const CORE = 'research/references.yaml';
export const DIR = 'research/references/';
export const EXPERTS = 'docs/experts.md';
const NOT_SHARDS = new Set(['vocab.yaml', 'coverage.yaml']);
/** The evidence ladder, lowest first (research/references/vocab.yaml `evidence_class`), and the confidence levels. */
export const LADDER = ['snippet-only', 'read', 'verified-at-source', 'encoded', 'measured'];
export const LEVELS = ['unknown', 'low', 'medium', 'high'];
export const UNPLACED = 'unplaced';
/** A tag in prose: `[ref:<kebab-case id>]`, not already a link (cadagent.review.references reads the same form). */
export const TAG = /\[ref:([a-z0-9]+(?:-[a-z0-9]+)*)\](?!\()/g;
// TAG in Markdown, less `[[ref:x]](url)`, where the tag is already the text of a link.
const MD_TAG = /(?<!\[)\[ref:([a-z0-9]+(?:-[a-z0-9]+)*)\](?!\()/g;
const STATUS_ORDER = { implemented: 0, partly: 1, missing: 2 };
const ROLE_ORDER = ['leader', 'reference', 'lessons', 'context'];

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const one = s => String(s ?? '').replace(/\s+/g, ' ').trim();
const isObj = v => v && typeof v === 'object' && !Array.isArray(v);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const byText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);      // code-unit order: the same on every machine
const plural = (n, word, many = word + 's') => `${n.toLocaleString('en-US')} ${n === 1 ? word : many}`;
/** A link only to http(s): a record's url comes from outside, and a page never links a `javascript:` one. */
const httpUrl = u => (typeof u === 'string' && /^https?:\/\//i.test(u.trim()) && safeUrl(u) !== '#' ? u.trim() : null);

// ----------------------------------------------------------------------------- reading

/** Merge a shard's `extends: true` record into its core read source, by the registry's own rule
 * (cadagent.review.references `_extend`): lists are united in order, fields the core lacks are added, and where both
 * set a field the core's value stands. */
function extend(base, ext, file) {
  const out = { ...base, extended_in: file };
  for (const [k, v] of Object.entries(ext)) {
    if (k === 'id' || k === 'extends') continue;
    const have = out[k];
    if (!(k in out) || have == null || have === '' || (Array.isArray(have) && !have.length) || (isObj(have) && !Object.keys(have).length)) out[k] = v;
    else if (Array.isArray(have) && Array.isArray(v)) out[k] = [...have, ...v.filter(x => !have.some(h => same(h, x)))];
  }
  return out;
}

/** The registry from committed (or on-disk) files: `files` lists the repo's paths, `read(path)` returns a file's
 * text. `records` holds the read sources (status `source`) and the shard records (status `catalogued`, or the read
 * source they extend); `others` holds the unverified and uncited keys, which have no page. */
export async function loadReferences({ files, read }) {
  const yaml = async f => YAML.parse(await read(f)) ?? {};
  const core = await yaml(CORE);
  const records = new Map(), aliases = new Map(), others = new Map();
  for (const s of core.sources || []) records.set(s.id, { ...s, status: 'source', file: CORE });
  for (const k of ['unverified', 'uncited']) for (const s of core[k] || []) others.set(s.id, { ...s, status: k });
  const has = f => files.includes(f);
  const vocab = has(DIR + 'vocab.yaml') ? await yaml(DIR + 'vocab.yaml') : {};
  const coverage = has(DIR + 'coverage.yaml') ? await yaml(DIR + 'coverage.yaml') : {};
  const shards = files.filter(f => f.startsWith(DIR) && f.endsWith('.yaml') && !f.slice(DIR.length).includes('/')
    && !NOT_SHARDS.has(f.slice(DIR.length))).sort();
  for (const f of shards) {
    for (const r of (await yaml(f)).sources || []) {
      if (r.extends === true) {
        const base = records.get(r.id);
        if (base?.status !== 'source') throw new Error(`${f}: ${r.id} extends no read source in ${CORE}`);
        records.set(r.id, extend(base, r, f));
      } else {
        if (records.has(r.id)) throw new Error(`${f}: ${r.id} is also in ${records.get(r.id).file}`);
        // A shard record someone has read (evidence `read` or higher) is a source, as in the Python registry.
        const read = isObj(r.evidence) && LADDER.indexOf(r.evidence.class) >= 1;
        records.set(r.id, { ...r, status: read ? 'source' : 'catalogued', file: f });
      }
    }
  }
  // Aliases of every entry, after every id (the registry's order): an alias never shadows an id.
  for (const e of [...records.values(), ...others.values()])
    for (const a of Array.isArray(e.aliases) ? e.aliases : [])
      if (typeof a === 'string' && !aliases.has(a) && !records.has(a) && !others.has(a)) aliases.set(a, e.id);
  return { records, aliases, others, vocab, coverage, shards };
}

/** docs/areas.yaml as the records use it: area slug -> {title, domain, ...}, topic slug -> its area. */
export function areaTree(areas) {
  const out = { areas: new Map(), topics: new Map(), domains: [] };
  for (const d of areas?.domains || []) {
    out.domains.push({ slug: d.slug, title: d.title });
    for (const a of d.areas || []) {
      out.areas.set(a.slug, { slug: a.slug, title: a.title, scope: a.scope, domain: d.slug, domainTitle: d.title });
      for (const t of a.topics || []) out.topics.set(t.slug, a.slug);
    }
  }
  return out;
}

/** The area an `areas` entry places a record in: an area slug, a topic's area, or `area/topic`; null for none
 * (cadagent.review.references `area_of`). */
export function areaOf(slug, tree) {
  if (typeof slug !== 'string') return null;
  const cut = slug.indexOf('/');
  if (cut >= 0) return tree.topics.get(slug.slice(cut + 1)) === slug.slice(0, cut) ? slug.slice(0, cut) : null;
  return tree.areas.has(slug) ? slug : tree.topics.get(slug) ?? null;
}

/** The ladder rung: `evidence.class`, else `read` for a core source. */
export const evidenceOf = r => (isObj(r.evidence) && r.evidence.class) || (r.status === 'source' ? 'read' : null);
/** The record's confidence block (#143), or unknown when it has none (not yet assessed). */
export const confidenceOf = r => (isObj(r.confidence) && LEVELS.includes(r.confidence.level) ? r.confidence
  : { level: 'unknown', estimate: null, sources: 0 });

// ----------------------------------------------------------------------------- the model every output shares

/** Everything the pages, the JSON, llms.txt and the experts page show, computed once from the records. */
export function referenceModel(refs, areasYaml) {
  const tree = areaTree(areasYaml);
  const placed = new Map(), byArea = new Map();
  for (const r of refs.records.values()) {
    const at = [...new Set((Array.isArray(r.areas) ? r.areas : []).map(a => areaOf(a, tree)).filter(Boolean))];
    placed.set(r.id, at.length ? at : [UNPLACED]);
    for (const a of placed.get(r.id)) (byArea.get(a) ?? byArea.set(a, []).get(a)).push(r);
  }
  // Read sources first, then by confidence, then by title: an objective order, the same for every project.
  const rank = r => [-LADDER.indexOf(evidenceOf(r)), -LEVELS.indexOf(confidenceOf(r).level)];
  for (const list of byArea.values()) list.sort((a, b) => {
    const [x, y] = [rank(a), rank(b)];
    return x[0] - y[0] || x[1] - y[1] || byText(String(a.title).toLowerCase(), String(b.title).toLowerCase()) || byText(a.id, b.id);
  });
  const rows = (refs.coverage.rows || []).map(row => ({ ...row, placed: [...new Set((row.areas || []).map(a => areaOf(a, tree)).filter(Boolean))] }));
  const coverageIn = new Map();
  for (const row of rows) for (const a of row.placed) (coverageIn.get(a) ?? coverageIn.set(a, []).get(a)).push(row);
  // Pages: every area with records or coverage rows, in docs/areas.yaml order, then the unplaced bucket.
  const pages = [...tree.areas.values()].filter(a => byArea.has(a.slug) || coverageIn.has(a.slug)).map(a => a.slug);
  if (byArea.has(UNPLACED)) pages.push(UNPLACED);
  const home = id => {
    const key = refs.records.has(id) ? id : refs.aliases.get(id);
    return key ? `/references/${placed.get(key)[0]}#${key}` : null;
  };
  const area = slug => slug === UNPLACED
    ? { slug, title: 'Not yet placed', domain: null, domainTitle: null,
      scope: 'Read sources whose `areas` are not docs/areas.yaml slugs yet. Placing each in an area moves it to that page.' }
    : tree.areas.get(slug);
  return { refs, tree, placed, byArea, rows, coverageIn, pages, home, area };
}

/** Counts of `list` by `key(record)` (a value or a list of values), in `order` first, then the rest by size. */
function countBy(list, key, order = []) {
  const n = new Map(order.map(k => [k, 0]));
  for (const r of list) for (const v of [key(r)].flat()) if (v != null && v !== '') n.set(v, (n.get(v) || 0) + 1);
  const rest = [...n].filter(([k]) => !order.includes(k)).sort((a, b) => b[1] - a[1] || byText(String(a[0]), String(b[0])));
  return [...order.filter(k => n.has(k)).map(k => [k, n.get(k)]), ...rest];
}
const kindOf = r => r.kind || 'source';
const licenceOf = r => (isObj(r.licence) && r.licence.class) || 'unrecorded';
const groupsOf = r => (Array.isArray(r.process_groups) ? r.process_groups : []);
/** The files that cite a record: its `used_for`, less `proposed: …` notes (a use not yet made). */
const citedBy = r => (Array.isArray(r.used_for) ? r.used_for : []).filter(u => typeof u === 'string' && !/^proposed:/i.test(u));
const roleOf = r => (isObj(r.assessment) && r.assessment.role) || null;

/** The vocabulary's short labels, with plain fallbacks for a word it lacks. */
function labels(vocab) {
  const word = (table, k, fallback) => {
    const v = vocab?.[table]?.[k];
    if (isObj(v)) return v.title || fallback;
    return typeof v === 'string' ? v : fallback;
  };
  return {
    kind: k => ({ source: 'Read source' }[k] || word('kind', k, k).replace(/ \(.*\)$/, '').replace(/^Design or manufacturing guide$/, 'Guide')),
    evidence: k => (k ? k.replace(/-/g, ' ') : 'not on the ladder'),
    evidenceMeans: k => word('evidence_class', k, ''),
    licence: k => (k === 'unrecorded' ? 'not recorded' : word('licence_class', k, k)),
    group: k => word('process_group', k, k),
    numbers: k => word('numbers', k, ''),
    claim: k => (k || '').replace(/-/g, ' '),
    claimMeans: k => word('claim_status', k, ''),
    role: k => word('role', k, k || '').split(':')[0],
    confidenceMeans: k => vocab?.confidence?.[k]?.means || '',
    coverage: k => word('coverage_status', k, k),
  };
}

// ----------------------------------------------------------------------------- JSON for agents

/** A record as the area files carry it: the registry's fields as written, plus where it is shown, and its link's
 * health when the build was given a health report. */
function recordJson(r, m, ORIGIN, health) {
  const { file, extended_in, ...data } = r;
  return { ...data, evidence_class: evidenceOf(r), confidence: confidenceOf(r), placed: m.placed.get(r.id),
    source_file: file, ...(extended_in ? { extended_in } : {}), ...(health?.has(r.id) ? { health: health.get(r.id) } : {}) };
}

export const HEALTH_SCHEMA = 'cad-agent-references-health/1';

/** The weekly link check's report (`tools/resource_audit.py references`, the workflow's references-health artifact;
 * #323 Q5: health is not kept in git) as id -> {status, checked, final_url?}, plus its date and counts. The status is
 * the effective one (an accepted soft-404 is ok). Null without a report; a report of another schema is an error. */
export function healthOf(report) {
  if (!report) return null;
  if (report.schema !== HEALTH_SCHEMA) throw new Error(`not a ${HEALTH_SCHEMA} report`);
  const byId = new Map(Object.entries(report.records || {}).sort(([a], [b]) => byText(a, b)).map(([id, e]) =>
    [id, { status: e.effective || e.status, checked: e.checked, ...(e.final_url ? { final_url: e.final_url } : {}) }]));
  return { byId, as_of: report.as_of, revision: report.revision, status: report.summary?.status || {} };
}

const FIELDS = {
  status: '`source`: read, with a dated `verified` note, and may be cited. `catalogued`: listed from a survey and not yet read; never cite one',
  kind: 'what the source is (research/references/vocab.yaml `kind`); a read source from before schema 2 has none',
  evidence_class: 'its rung on the evidence ladder, lowest first: ' + LADDER.join(', '),
  confidence: '#143: {level, estimate, sources}, derived from the evidence; `unknown` when the record has no evidence block',
  licence: '{spdx, class, read, note}: `read: false` means the licence text was not read, only stated by the survey',
  placed: 'the docs/areas.yaml areas the record is listed in (`unplaced` when its areas match none)',
  placed_note: 'its row on the site, which [ref:<id>] in any page links to, is /references/<first placed area>#<id>',
  vocab: `every coded value is explained in ${DIR}vocab.yaml`,
};

/** What each entry of index.json's `records` says (the area files carry every field of a record). */
const RECORD_FIELDS = {
  id: 'the record id, as [ref:<id>] cites it', title: 'as the source titles itself', url: 'where it is (https), or null; a book has `isbn`',
  status: FIELDS.status, kind: 'what the source is (vocab.yaml `kind`), `source` for a read source from before schema 2',
  licence: 'licence class (vocab.yaml `licence_class`), `unrecorded` when none is set', licence_read: 'false: the class is as the survey stated it, the licence text unread',
  evidence: 'its rung on the evidence ladder',
  areas: 'the docs/areas.yaml areas it is listed in (`unplaced` when none); its row on the site is /references/<first area>#<id>, '
    + 'and every field it has is in catalog/references/<area>.json',
};

/** catalog/references/index.json and one catalog/references/<area>.json per page. */
export function referenceJson(m, { ORIGIN, revision, built, health = null }) {
  const L = labels(m.refs.vocab), files = [], H = health?.byId;
  const all = [...m.refs.records.values()];
  const summary = list => ({
    records: list.length,
    sources: list.filter(r => r.status === 'source').length,
    catalogued: list.filter(r => r.status === 'catalogued').length,
    by_evidence: Object.fromEntries(countBy(list, evidenceOf, LADDER)),
    by_confidence: Object.fromEntries(countBy(list, r => confidenceOf(r).level, LEVELS)),
    by_kind: Object.fromEntries(countBy(list, kindOf)),
    by_licence: Object.fromEntries(countBy(list, licenceOf)),
    by_process_group: Object.fromEntries(countBy(list, groupsOf)),
  });
  const areas = m.pages.map(slug => {
    const a = m.area(slug), list = m.byArea.get(slug) || [];
    return { slug, title: a.title, domain: a.domain, ...summary(list), coverage: (m.coverageIn.get(slug) || []).length,
      page: `${ORIGIN}/references/${slug}`, markdown: `${ORIGIN}/references/${slug}.md`, json: `${ORIGIN}/catalog/references/${slug}.json` };
  });
  const index = {
    schema: SCHEMA, built, revision,
    about: 'The reference knowledge base: read sources the rules cite, and records catalogued from a survey (snippet-only: '
      + 'listed and linked, never cited until someone reads them). One file per area; a record is in each of its areas.',
    fields: { ...FIELDS, records: 'every record in one file (id, url, kind, licence, evidence, areas), for mirrors',
      ...(health ? { health: 'the link as the weekly check last saw it: {status (ok, moved, changed, blocked, gone, unreachable), checked, final_url}; not kept in git' } : {}) }, ladder: LADDER.map(k => ({ class: k, means: L.evidenceMeans(k) })),
    totals: { ...summary(all), unplaced: (m.byArea.get(UNPLACED) || []).length, areas: m.pages.filter(p => p !== UNPLACED).length },
    areas,
    coverage: { observed: m.refs.coverage.observed ?? null, note: m.refs.coverage.note ?? null,
      rows: m.rows.map(({ id, number, topic, status, placed }) => ({ id, number, topic, status, areas: placed })) },
    records: `${ORIGIN}/catalog/references/records.json`,
    ...(health ? { health: { as_of: health.as_of, revision: health.revision, status: health.status } } : {}),
  };
  files.push(['catalog/references/index.json', JSON.stringify(index, null, 2) + '\n']);
  // Every record in one fetch, for an offline mirror (val-ark), one per line in id order. Its own file, so the
  // index an agent reads first stays a few KB.
  const brief = [...m.refs.records.values()].sort((a, b) => byText(a.id, b.id)).map(r => '    ' + JSON.stringify({
    id: r.id, title: r.title ?? null, url: httpUrl(r.url), ...(r.isbn ? { isbn: String(r.isbn) } : {}), status: r.status,
    kind: kindOf(r), licence: licenceOf(r), licence_read: isObj(r.licence) ? r.licence.read ?? null : null,
    evidence: evidenceOf(r), areas: m.placed.get(r.id), ...(H?.has(r.id) ? { health: H.get(r.id).status } : {}) }));
  files.push(['catalog/references/records.json', JSON.stringify({ schema: SCHEMA, built, revision,
    about: 'Every record of the reference knowledge base, one per line: enough to mirror each source (its url or isbn) and '
      + 'to know what it is. Every field of a record is in catalog/references/<area>.json of its first area.',
    index: `${ORIGIN}/catalog/references/index.json`, fields: RECORD_FIELDS, count: brief.length, records: '\0' }, null, 2)
    .replace('"\\u0000"', () => `[\n${brief.join(',\n')}\n  ]`) + '\n']);
  for (const slug of m.pages) {
    const a = m.area(slug);
    // One record per line: small to fetch, and still easy to read and diff.
    const records = (m.byArea.get(slug) || []).map(r => '    ' + JSON.stringify(recordJson(r, m, ORIGIN, H)));
    files.push([`catalog/references/${slug}.json`, JSON.stringify({
      schema: SCHEMA, built, revision, area: { slug, title: a.title, domain: a.domain, scope: a.scope }, fields: FIELDS,
      index: `${ORIGIN}/catalog/references/index.json`, count: records.length,
      coverage: (m.coverageIn.get(slug) || []).map(({ placed, ...row }) => ({ ...row, placed })), records: '\0',
    }, null, 2).replace('"\\u0000"', () => (records.length ? `[\n${records.join(',\n')}\n  ]` : '[]')) + '\n']);
  }
  return files;
}

// ----------------------------------------------------------------------------- charts (SVG drawn here, themed by CSS)

/** A horizontal bar chart: one row per value, each a link that filters the table (web/references.js; without
 * script it opens the same view, unfiltered). `rows`: [{value, label, n, tone?, href?}]. */
export function barChart({ title, note = '', rows, filter = null, wide = false }) {
  const W = wide ? 640 : 360, ROW = 26, TOP = 6, LABEL = wide ? 230 : 136, NUM = 44, BAR = W - LABEL - NUM - 8;
  const max = Math.max(1, ...rows.map(r => r.n));
  const H = TOP * 2 + rows.length * ROW;
  const rowsSvg = rows.map((r, i) => {
    const y = TOP + i * ROW, w = r.n ? Math.max(3, Math.round(BAR * r.n / max)) : 0;
    const href = r.href ?? (filter ? `?${filter}=${encodeURIComponent(r.value)}#records` : null);
    const body = `<title>${esc(`${r.label}: ${r.n}`)}</title><text class="refs-chart-label" x="0" y="${y + 17}">${esc(r.label)}</text>`
      + `<rect class="refs-chart-track" x="${LABEL}" y="${y + 5}" width="${BAR}" height="15" rx="4"/>`
      + (w ? `<rect class="refs-chart-bar${r.tone ? ' tone-' + esc(r.tone) : ''}" x="${LABEL}" y="${y + 5}" width="${w}" height="15" rx="4"/>` : '')
      + `<text class="refs-chart-n" x="${W}" y="${y + 17}" text-anchor="end">${r.n.toLocaleString('en-US')}</text>`;
    return href ? `<a href="${esc(href)}"${filter ? ` data-filter="${esc(filter)}" data-value="${esc(r.value)}"` : ''}>${body}</a>` : `<g>${body}</g>`;
  }).join('');
  const spoken = `${title}: ${rows.map(r => `${r.label} ${r.n}`).join(', ')}`;
  return `<figure class="refs-chart${wide ? ' refs-chart-wide' : ''}" data-visual${wide ? ` ${SCROLLS(title)}` : ''}><figcaption><b>${esc(title)}</b>${note ? ` <span>${esc(note)}</span>` : ''}</figcaption>`
    + `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(spoken)}">${rowsSvg}</svg></figure>`;
}

/** A wide chart scrolls sideways on a phone (web/references.css): reachable by keyboard, and named. */
const SCROLLS = name => `tabindex="0" role="region" aria-label="${esc(name)}"`;

/** Stacked rows (index page): per area, read sources and catalogued records, grouped under their domain. */
function areaChart(m) {
  const W = 680, ROW = 26, HEAD = 26, LABEL = 236, NUM = 64, BAR = W - LABEL - NUM - 8;
  const groups = [];
  for (const slug of m.pages) {
    const a = m.area(slug), key = a.domainTitle || 'Not yet placed';
    if (!groups.length || groups.at(-1).title !== key) groups.push({ title: key, areas: [] });
    groups.at(-1).areas.push(slug);
  }
  const max = Math.max(1, ...m.pages.map(s => (m.byArea.get(s) || []).length));
  let y = 4, out = '', spoken = [];
  for (const g of groups) {
    out += `<text class="refs-chart-group" x="0" y="${y + 18}">${esc(g.title)}</text>`;
    y += HEAD;
    for (const slug of g.areas) {
      const list = m.byArea.get(slug) || [], read = list.filter(r => r.status === 'source').length, cat = list.length - read;
      const wr = read ? Math.max(3, Math.round(BAR * read / max)) : 0, wc = cat ? Math.max(3, Math.round(BAR * cat / max)) : 0;
      spoken.push(`${m.area(slug).title} ${read} read, ${cat} catalogued`);
      out += `<a href="/references/${esc(slug)}"><title>${esc(`${m.area(slug).title}: ${read} read, ${cat} catalogued`)}</title>`
        + `<text class="refs-chart-label refs-chart-link" x="12" y="${y + 17}">${esc(clipLabel(m.area(slug).title, 34))}</text>`
        + `<rect class="refs-chart-track" x="${LABEL}" y="${y + 5}" width="${BAR}" height="15" rx="4"/>`
        + (wr ? `<rect class="refs-chart-bar" x="${LABEL}" y="${y + 5}" width="${wr}" height="15" rx="4"/>` : '')
        + (wc ? `<rect class="refs-chart-bar tone-catalogued" x="${LABEL + wr}" y="${y + 5}" width="${wc}" height="15" rx="4"/>` : '')
        + `<text class="refs-chart-n" x="${W}" y="${y + 17}" text-anchor="end">${list.length}</text></a>`;
      y += ROW;
    }
  }
  return `<figure class="refs-chart refs-chart-wide" data-visual ${SCROLLS('Records by area')}><figcaption><b>Records by area</b> <span><i class="refs-key tone-read"></i>read sources <i class="refs-key tone-catalogued"></i>catalogued, not yet read</span></figcaption>`
    + `<svg viewBox="0 0 ${W} ${y + 4}" width="${W}" height="${y + 4}" role="img" aria-label="${esc('Records by area: ' + spoken.join('; '))}">${out}</svg></figure>`;
}

/** The coverage rows (index page): what cad-agent enforced per topic when the map was made. */
function coverageChart(m) {
  const L = labels(m.refs.vocab), W = 680, ROW = 26;
  const rows = [...m.rows].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || Number(a.number) - Number(b.number));
  const out = rows.map((row, i) => {
    const y = 4 + i * ROW, at = row.placed[0];
    const body = `<title>${esc(`${row.topic}: ${L.coverage(row.status)}`)}</title><rect class="refs-cov-dot cov-${esc(row.status)}" x="0" y="${y + 3}" width="70" height="19" rx="9.5"/>`
      + `<text class="refs-cov-word" x="35" y="${y + 17}" text-anchor="middle">${esc(L.coverage(row.status))}</text>`
      + `<text class="refs-chart-label${at ? ' refs-chart-link' : ''}" x="80" y="${y + 17}">${esc(clipLabel(row.topic, 84))}</text>`;
    return at ? `<a href="/references/${esc(at)}#coverage">${body}</a>` : `<g>${body}</g>`;
  }).join('');
  const H = 8 + rows.length * ROW;
  return `<figure class="refs-chart refs-chart-wide" data-visual ${SCROLLS('What cad-agent checks, by topic')}><figcaption><b>What cad-agent checks, by topic</b> <span>the map's coverage table, as observed ${esc(m.refs.coverage.observed || '')}</span></figcaption>`
    + `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc('Coverage: ' + rows.map(r => `${r.topic} ${r.status}`).join('; '))}">${out}</svg></figure>`;
}

// ----------------------------------------------------------------------------- HTML pages

const clipLabel = (s, n) => (s.length > n ? s.slice(0, n - 1).replace(/[\s,]+\S*$/, '') + '…' : s);
const badge = (cls, text, title = '') => `<span class="refs-badge ${cls}"${title ? ` title="${esc(title)}"` : ''}>${esc(text)}</span>`;

function recordRow(r, m, L) {
  const ev = evidenceOf(r), conf = confidenceOf(r), lic = licenceOf(r), groups = groupsOf(r), role = roleOf(r);
  const url = httpUrl(r.url), who = one(r.org || (Array.isArray(r.authors) ? r.authors.join(', ') : ''));
  const claims = (Array.isArray(r.claims) ? r.claims : []).filter(isObj);
  const text = one([r.title, who, r.summary, r.id, kindOf(r)].join(' ')).toLowerCase();
  const read = r.status === 'source' ? one(typeof r.verified === 'string' ? r.verified : '') : '';
  const used = citedBy(r);
  const numbers = isObj(r.evidence) && r.evidence.numbers === 'claimed' ? `<span class="refs-note">${esc(L.numbers('claimed'))}</span>` : '';
  const lict = isObj(r.licence) ? r.licence : {};
  return `<tr id="${esc(r.id)}" data-kind="${esc(kindOf(r))}" data-evidence="${esc(ev || '')}" data-confidence="${esc(conf.level)}" data-licence="${esc(lic)}" data-process="${esc(groups.join(' '))}" data-role="${esc(role || '')}" data-text="${esc(text)}">`
    + `<td class="refs-rec">${url ? `<a class="refs-title" href="${esc(url)}">${esc(r.title)}</a>` : `<span class="refs-title">${esc(r.title)}</span>${r.isbn ? ` <span class="refs-who">ISBN ${esc(r.isbn)}</span>` : ''}`}`
    + `${who || r.year ? `<span class="refs-who">${esc(who)}${who && r.year ? ' · ' : ''}${r.year ? esc(r.year) : ''}</span>` : ''}`
    + `${r.summary ? `<p class="refs-sum">${esc(one(r.summary))}</p>` : ''}`
    + `${read ? `<p class="refs-sum"><b>Read:</b> ${esc(read.length > 240 ? read.slice(0, 239) + '…' : read)}</p>` : ''}`
    + claims.map(c => `<p class="refs-claim">${badge(`cl-${esc(c.status)}`, L.claim(c.status), L.claimMeans(c.status))} ${esc(one(c.text))}</p>`).join('')
    + `${isObj(r.assessment) && r.assessment.caveat ? `<p class="refs-sum refs-caveat-row">${esc(one(r.assessment.caveat))}</p>` : ''}`
    + `<p class="refs-meta"><code>${esc(r.id)}</code>${used.length ? ` <span title="${esc(used.join('\n'))}">cited by ${plural(used.length, 'file')}</span>` : ''}</p></td>`
    + `<td>${esc(L.kind(kindOf(r)))}</td>`
    + `<td>${badge(`ev-${esc(ev || 'none')}`, L.evidence(ev), L.evidenceMeans(ev))}${numbers}</td>`
    + `<td>${badge(`conf-${esc(conf.level)}`, conf.estimate == null ? conf.level : `${conf.level} ${conf.estimate}`, L.confidenceMeans(conf.level))}`
    + `<span class="refs-meter" aria-hidden="true"><i style="width:${Math.round((conf.estimate || 0) * 100)}%"></i></span></td>`
    + `<td>${badge(`lic-${esc(lic)}`, L.licence(lic), one(lict.note || ''))}${lict.spdx ? `<span class="refs-note">${esc(lict.spdx)}</span>` : ''}${lict.read === false ? '<span class="refs-note">not read</span>' : ''}</td>`
    + `<td>${groups.map(g => `<span class="refs-group">${esc(L.group(g))}</span>`).join('') || '<span class="refs-note">none stated</span>'}</td>`
    + `<td>${role ? esc(L.role(role)) : '<span class="refs-note">not assessed</span>'}</td></tr>`;
}

function coverageCards(rows, L) {
  if (!rows.length) return '';
  return `<section class="refs-coverage" aria-labelledby="coverage"><h2 id="coverage">Coverage</h2>`
    + `<p class="refs-lede-small">What cad-agent checked for these topics when the map was made, and the gap it found. The issue it drafted for each gap was never posted.</p><ul class="refs-cov-cards">`
    + rows.map(row => `<li class="refs-cov-card cov-${esc(row.status)}"><p class="refs-cov-top">${badge(`cov-${esc(row.status)}`, L.coverage(row.status))}<b>${esc(row.topic)}</b></p>`
      + (row.gap ? `<p><b>Gap:</b> ${esc(one(row.gap))}</p>` : '')
      + (isObj(row.draft_issue) ? `<p class="refs-note-line">Drafted issue, never posted: “${esc(one(row.draft_issue.title))}”</p>` : '') + '</li>').join('')
    + '</ul></section>';
}

/** One area's page body (the frame, feedback box and crumbs are tools/build-site.mjs's). */
function areaBody(slug, m, { feedback }) {
  const L = labels(m.refs.vocab), a = m.area(slug), list = m.byArea.get(slug) || [], rows = m.coverageIn.get(slug) || [];
  const read = list.filter(r => r.status === 'source').length, cat = list.length - read;
  const opts = (key, pairs, label) => `<label><span>${esc(label)}</span><select data-key="${key}"><option value="">All</option>`
    + pairs.map(([v, n]) => `<option value="${esc(v)}">${esc(n[0])} (${n[1]})</option>`).join('') + '</select></label>';
  const lab = (pairs, fn) => pairs.map(([v, n]) => [v, [fn(v), n]]);
  const ev = countBy(list, evidenceOf, LADDER), conf = countBy(list, r => confidenceOf(r).level, [...LEVELS].reverse());
  const kinds = countBy(list, kindOf), lics = countBy(list, licenceOf), groups = countBy(list, groupsOf), roles = countBy(list, roleOf, ROLE_ORDER);
  const charts = list.length ? `<section class="refs-charts" aria-label="The records at a glance">`
    + barChart({ title: 'Evidence', note: 'how far each has been checked, lowest rung first', filter: 'evidence',
      rows: LADDER.map(k => ({ value: k, label: L.evidence(k), n: ev.find(([v]) => v === k)?.[1] || 0, tone: k === 'snippet-only' ? 'catalogued' : 'read' })) })
    + barChart({ title: 'Confidence', note: '#143, derived from the evidence', filter: 'confidence',
      rows: [...LEVELS].reverse().map(k => ({ value: k, label: k, n: conf.find(([v]) => v === k)?.[1] || 0, tone: k === 'unknown' ? 'catalogued' : 'read' })) })
    + barChart({ title: 'Kind', filter: 'kind', rows: kinds.map(([k, n]) => ({ value: k, label: L.kind(k), n })) })
    + barChart({ title: 'Licence class', note: 'as stated; most not yet read', filter: 'licence', rows: lics.map(([k, n]) => ({ value: k, label: L.licence(k), n })) })
    + (groups.length ? barChart({ title: 'Process', filter: 'process', rows: groups.map(([k, n]) => ({ value: k, label: L.group(k), n })) }) : '')
    + '</section>' : '';
  const table = list.length ? `<section class="refs-records" aria-labelledby="records"><h2 id="records">Records</h2>`
    + `<form class="refs-filters" role="search" hidden><label class="refs-q"><span>Search</span><input type="search" data-key="q" placeholder="Title, publisher, words" aria-label="Search the records"></label>`
    + opts('evidence', lab(ev, L.evidence), 'Evidence') + opts('confidence', lab(conf, k => k), 'Confidence') + opts('kind', lab(kinds, L.kind), 'Kind')
    + opts('licence', lab(lics, L.licence), 'Licence') + (groups.length ? opts('process', lab(groups, L.group), 'Process') : '')
    + (roles.length ? opts('role', lab(roles, L.role), 'Role') : '')
    + `<button type="reset" class="refs-clear">Clear</button></form>`
    + `<p class="refs-count" role="status" data-total="${list.length}">${plural(list.length, 'record')}</p>`
    + `<div class="refs-table-wrap" tabindex="0" role="region" aria-label="${esc(a.title)} records"><table class="refs-table"><thead><tr><th scope="col">Record</th><th scope="col">Kind</th><th scope="col">Evidence</th><th scope="col">Confidence</th><th scope="col">Licence</th><th scope="col">Process</th><th scope="col">Role</th></tr></thead><tbody>`
    + list.map(r => recordRow(r, m, L)).join('') + '</tbody></table></div>'
    + `<p class="refs-note-line">Role is the survey's judgement of a record within its class (leader, reference, lessons, context): not a quality grade. ${esc(L.confidenceMeans('low'))} is what “low” means.</p></section>` : '';
  return `<div class="refs-page"><p class="crumbs"><a href="/references">References</a> · <a href="${slug === UNPLACED ? '/catalog' : `/catalog?area=${esc(slug)}`}">${slug === UNPLACED ? 'Catalogue' : esc(a.title) + ' in the catalogue'}</a> · <a href="/references/${esc(slug)}.md">Markdown</a> · <a href="/catalog/references/${esc(slug)}.json">JSON</a></p>`
    + `<header class="refs-head"><p class="eyebrow">${esc(a.domainTitle ? `References · ${a.domainTitle}` : 'References')}</p><h1>${esc(a.title)}</h1>`
    + `<p class="refs-lede">${list.length ? `${plural(list.length, 'record')}: ${plural(read, 'read source')} that cad-agent's rules and checks may cite, and ${plural(cat, 'record')} catalogued from the Reference Map, not yet read.` : 'No records yet, only the coverage below.'} ${esc(one(a.scope || ''))}</p>`
    + (cat ? `<p class="refs-caveat">Catalogued records are search snippets: their numbers are the authors' claims and their licences are as the map states them, unread. Cite one only after reading the source and promoting it (<a href="https://github.com/Valpatel/cad-agent/blob/dev/research/references/README.md">how</a>).</p>` : '')
    + '</header>' + coverageCards(rows, L) + charts + table + feedback + '</div>';
}

function indexBody(m, { feedback }) {
  const all = [...m.refs.records.values()], read = all.filter(r => r.status === 'source').length;
  const unplaced = (m.byArea.get(UNPLACED) || []).length, wanted = Array.isArray(m.refs.coverage.wanted) ? m.refs.coverage.wanted : [];
  const L = labels(m.refs.vocab);
  return `<div class="refs-page"><p class="crumbs"><a href="/catalog">Catalogue</a> · <a href="/references.md">Markdown</a> · <a href="/catalog/references/index.json">JSON</a> · <a href="/catalog/references/records.json">All records (JSON)</a> · <a href="/docs/experts">Experts</a></p>`
    + `<header class="refs-head"><p class="eyebrow">Reference knowledge base</p><h1>References</h1>`
    + `<p class="refs-lede">${plural(all.length, 'record')} in ${plural(m.pages.filter(p => p !== UNPLACED).length, 'area')}: ${plural(read, 'read source')} that the rules and checks cite, and ${plural(all.length - read, 'record')} catalogued from the Reference Map (open projects and design guides), not yet read. Open an area for its charts and a table you can filter.</p>`
    + `<p class="refs-caveat">A catalogued record is a search snippet: listed and linked, never cited until someone reads the source. Its numbers are the authors' claims and its licence is as the map states it.</p></header>`
    + `<section class="refs-charts refs-charts-wide" aria-label="All areas">${areaChart(m)}${m.rows.length ? coverageChart(m) : ''}</section>`
    + (wanted.length ? `<section aria-labelledby="wanted"><h2 id="wanted">Sources still wanted</h2><ul class="refs-cov-cards">`
      + wanted.map(w => {
        const at = (w.areas || []).map(a => areaOf(a, m.tree)).find(a => a && m.pages.includes(a));
        const name = esc(w.title || L.group(w.group || ''));
        return `<li class="refs-cov-card"><p class="refs-cov-top"><b>${at ? `<a href="/references/${esc(at)}">${name}</a>` : name}</b></p><p>${esc(one(w.text || ''))}</p></li>`;
      }).join('') + '</ul></section>' : '')
    + (unplaced ? `<p class="refs-note-line"><a href="/references/${UNPLACED}">${plural(unplaced, 'read source')}</a> name areas that are not docs/areas.yaml slugs yet, so they are not placed in an area.</p>` : '')
    + feedback + '</div>';
}

// ----------------------------------------------------------------------------- Markdown twins and llms.txt

const mdText = s => one(s).replace(/([\\|[\]*_`<>])/g, '\\$1');
const mdUrl = u => u.replace(/[()\s|<>]/g, c => encodeURIComponent(c));

function areaMd(slug, m, ORIGIN) {
  const L = labels(m.refs.vocab), a = m.area(slug), list = m.byArea.get(slug) || [], rows = m.coverageIn.get(slug) || [];
  const read = list.filter(r => r.status === 'source').length;
  const out = [`# ${a.title}: references`, '',
    `${plural(list.length, 'record')}: ${plural(read, 'read source')} that the rules and checks may cite, and ${plural(list.length - read, 'record')} catalogued from the Reference Map, not yet read. ${one(a.scope || '')}`, '',
    'Catalogued records are search snippets: their numbers are the authors\' claims and their licences are as the map states them, unread. Cite one only after reading it.', '',
    `The same records as JSON: ${ORIGIN}/catalog/references/${slug}.json. All areas: [references](../references.md).`, ''];
  if (rows.length) {
    out.push('## Coverage', '', 'What cad-agent checked when the map was made; each drafted issue was never posted.', '');
    for (const row of rows) out.push(`- **${mdText(row.topic)}** (${L.coverage(row.status)}): ${mdText(row.gap || '')}${isObj(row.draft_issue) ? ` Drafted issue, never posted: "${mdText(row.draft_issue.title)}".` : ''}`);
    out.push('');
  }
  if (list.length) {
    out.push('## Records', '', '| Record | Kind | Evidence | Confidence | Licence | Process | Role |', '|---|---|---|---|---|---|---|');
    for (const r of list) {
      const url = httpUrl(r.url), conf = confidenceOf(r), lic = isObj(r.licence) ? r.licence : {};
      const who = one(r.org || (Array.isArray(r.authors) ? r.authors.join(', ') : ''));
      const cells = [
        `${url ? `[${mdText(r.title)}](${mdUrl(url)})` : mdText(r.title)}${who ? ` · ${mdText(who)}` : ''} · \`${r.id}\``,
        mdText(L.kind(kindOf(r))),
        mdText(L.evidence(evidenceOf(r))) + (isObj(r.evidence) && r.evidence.numbers === 'claimed' ? ' (authors\' claim)' : ''),
        mdText(`${conf.level}${conf.estimate == null ? '' : ' ' + conf.estimate}`),
        mdText(`${L.licence(licenceOf(r))}${lic.spdx ? ' ' + lic.spdx : ''}${lic.read === false ? ', not read' : ''}`),
        mdText(groupsOf(r).map(L.group).join(', ')), mdText(roleOf(r) ? L.role(roleOf(r)) : ''),
      ];
      out.push(`| ${cells.join(' | ')} |`);
    }
    out.push('');
  }
  return out.join('\n');
}

function indexMd(m, ORIGIN) {
  const all = [...m.refs.records.values()], read = all.filter(r => r.status === 'source').length, L = labels(m.refs.vocab);
  return [`# References`, '', `${plural(all.length, 'record')}: ${plural(read, 'read source')} that the rules and checks cite, and ${plural(all.length - read, 'record')} catalogued from the Reference Map, not yet read (snippet-only: listed and linked, never cited).`, '',
    `Counts per area as JSON: ${ORIGIN}/catalog/references/index.json; every record in brief, for a mirror: ${ORIGIN}/catalog/references/records.json`, '', '## Areas', '',
    ...m.pages.map(slug => { const list = m.byArea.get(slug) || []; const r = list.filter(x => x.status === 'source').length; return `- [${m.area(slug).title}](references/${slug}.md): ${list.length} (${r} read, ${list.length - r} catalogued)`; }),
    '', ...(m.rows.length ? ['## Coverage', '', ...m.rows.map(row => `- ${mdText(row.topic)}: ${L.coverage(row.status)}`), ''] : [])].join('\n');
}

/** The llms.txt section: one line per area, and how to read them. No record lines. */
export function llmsSection(m, ORIGIN) {
  const all = [...m.refs.records.values()], read = all.filter(r => r.status === 'source').length;
  return ['## References', '',
    `The reference knowledge base: ${all.length} records, ${read} read sources that rules and checks cite and ${all.length - read} catalogued from a survey (snippet-only: listed and linked, never cited until read). Counts per area: ${ORIGIN}/catalog/references/index.json; one area's records: ${ORIGIN}/catalog/references/<area>.json; every record in brief (for a mirror): ${ORIGIN}/catalog/references/records.json. \`[ref:<id>]\` in any page links to its record. The people and organisations behind the read sources: ${ORIGIN}/docs/experts.md`, '',
    ...m.pages.map(slug => {
      const list = m.byArea.get(slug) || [], r = list.filter(x => x.status === 'source').length;
      return `- [${m.area(slug).title}](${ORIGIN}/references/${slug}.md): ${plural(list.length, 'record')} (${r} read, ${list.length - r} catalogued); ${ORIGIN}/catalog/references/${slug}.json`;
    })].join('\n');
}

// ----------------------------------------------------------------------------- [ref:] tags

/** `[ref:<id>]` in a page's HTML (outside code, pre and links) as a link to the record's row and to the source. An
 * id the registry lists as unverified or uncited stays text, marked; an unknown id is left as written (the registry
 * check reports it). */
export function linkTags(html, m) {
  let inside = 0;
  return html.split(/(<[^>]+>)/).map(part => {
    if (part.startsWith('<')) {
      const t = part.match(/^<(\/?)(code|pre|a|script|style|textarea|svg)\b/i);
      if (t) inside = Math.max(0, inside + (t[1] ? -1 : 1));
      return part;
    }
    return inside ? part : part.replace(TAG, (all, id) => cite(id, m) ?? all);
  }).join('');
}
function cite(id, m) {
  const key = m.refs.records.has(id) ? id : m.refs.aliases.get(id);
  const r = key && m.refs.records.get(key);
  if (r) {
    const who = one(r.org || (Array.isArray(r.authors) ? r.authors.join(', ') : '')), url = httpUrl(r.url);
    const title = `${one(r.title)}${who ? ', ' + who : ''} (${(evidenceOf(r) || '').replace(/-/g, ' ')})`;
    return `<span class="ref-cite">[<a class="ref-key" href="${esc(m.home(key))}" title="${esc(title)}">${esc(id)}</a>`
      + `${url ? `<a class="ref-out" href="${esc(url)}" aria-label="${esc('Open the source: ' + one(r.title))}">↗</a>` : ''}]</span>`;
  }
  const o = m.refs.others.get(id) ?? m.refs.others.get(m.refs.aliases.get(id));
  return o ? `<span class="ref-cite ref-unread" title="${esc(`${o.status}: not yet read`)}">[${esc(id)}]</span>` : null;
}

/** `[ref:<id>]` in a Markdown twin (outside code spans and fences) as a Markdown link to the record's page: relative
 * to `file`, or absolute (llms-full.txt). */
export function mdTags(md, file, m, { ORIGIN, absolute = false }) {
  // Code fences, code spans and links whose text holds a tag ([see [ref:x]](url)) are left as written.
  return md.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|\[(?:[^[\]\n]|\[[^[\]\n]*\])*\]\([^)\s]*\))/).map((chunk, i) => i % 2 ? chunk : chunk.replace(MD_TAG, (all, id) => {
    const home = m.home(id);
    if (!home) return all;
    const [page, hash] = home.slice(1).split('#');
    const target = absolute ? `${ORIGIN}/${page}.md` : path.posix.relative(path.posix.dirname(file), `${page}.md`);
    return `[ref:${id}](${target}#${hash})`;
  })).join('');
}

// ----------------------------------------------------------------------------- docs/experts.md

/** docs/experts.md: the people and organisations whose read sources cad-agent stands on (#118 item 3), grouped by
 * publisher, with what each contributed and the files that cite it. Catalogued records are counted, not listed:
 * nothing stands on them yet. */
export function expertsMarkdown(m, { ORIGIN }) {
  const sources = [...m.refs.records.values()].filter(r => r.status === 'source');
  const catalogued = [...m.refs.records.values()].filter(r => r.status === 'catalogued');
  const groups = new Map();
  for (const r of sources) {
    const key = one(r.org || (Array.isArray(r.authors) ? r.authors.join(', ') : '') || 'Unattributed');
    (groups.get(key) ?? groups.set(key, []).get(key)).push(r);
  }
  const rows = [...groups].sort((a, b) => b[1].length - a[1].length || byText(a[0].toLowerCase(), b[0].toLowerCase()));
  const files = new Set(sources.flatMap(citedBy));
  const publishers = new Set(catalogued.map(r => one(r.org || '')).filter(Boolean));
  const people = new Set(sources.flatMap(r => (Array.isArray(r.authors) ? r.authors : []).map(one)).filter(Boolean));
  const cell = s => mdText(s);
  const lines = [
    `<!-- Generated by tools/site-references.mjs from ${CORE} and ${DIR}*.yaml. Do not edit: change a record, then run \`node tools/site-references.mjs --experts\` (also to settle a merge conflict here). -->`,
    '# Experts and sources', '',
    `The people and organisations whose published work cad-agent's rules and checks stand on: ${plural(rows.length, 'publisher')} and ${plural(people.size, 'named author')}, in ${plural(sources.length, 'read source')}. They did the work. cad-agent cites it by name and never copies it. A rule, check or page that relies on a source names it by id: a \`[ref:<id>]\` tag in text (which the site links to the source), a module's source table, a material's \`source\` or a process rule's \`source\`.`, '',
    '```mermaid', 'flowchart TD',
    `  P["${rows.length} publishers, ${people.size} named authors"] -->|published| S["${sources.length} read sources"]`,
    `  S -->|cited by| U["${files.size} files: rules, checks and pages"]`,
    `  C["${catalogued.length} catalogued records, not yet read"] -.->|read, then promote| S`,
    '  class S here', '```', '',
    '## Who they are', '',
    'Each row is one publisher (or the authors, where a source names no organisation), largest first. Areas link to the record on the site.', '',
    '| Publisher | People | Contributed | Areas | Cited by |', '|---|---|---|---|---|',
    ...rows.map(([who, list]) => {
      const authors = [...new Set(list.flatMap(r => (Array.isArray(r.authors) ? r.authors : []).map(one)).filter(Boolean))];
      const works = list.map(r => { const url = httpUrl(r.url); return url ? `[${cell(r.title)}](${mdUrl(url)})` : `${cell(r.title)}${r.isbn ? ` (ISBN ${cell(r.isbn)})` : ''}`; });
      const areas = [...new Set(list.flatMap(r => m.placed.get(r.id)))].map(a => `[${cell(m.area(a).title)}](${ORIGIN}/references/${a})`);
      const used = [...new Set(list.flatMap(citedBy))].sort();
      return `| ${cell(who)} | ${authors.map(cell).join(', ')} | ${works.join('; ')} | ${areas.join(', ')} | ${used.length} file${used.length === 1 ? '' : 's'}: ${used.map(u => `\`${u}\``).join(', ')} |`;
    }), '',
    '## Catalogued, not yet read', '',
    `${plural(catalogued.length, 'more record')}, from ${plural(publishers.size, 'publisher')}, are catalogued from the Reference Map: open projects and design guides seen in search snippets. They join the table above when someone reads one and a rule or check relies on it. Browse them by area on the [references pages](${ORIGIN}/references).`, ''];
  return lines.join('\n');
}

// ----------------------------------------------------------------------------- the site build's entry point

/** What tools/build-site.mjs writes: the pages (bodies for its frame), their twins, the JSON files, the llms.txt
 * section and the sitemap's URLs. `feedbackBox(title, url)` is the build's feedback box. */
export function referenceSite(m, { ORIGIN, revision, built, feedbackBox, health = null }) {
  const pages = [{ file: 'references.html', md: 'references.md', url: '/references', title: 'References',
    description: `The reference knowledge base: ${m.refs.records.size} sources and catalogued records by area of hardware design, with their evidence, confidence and licence.`,
    body: indexBody(m, { feedback: feedbackBox('References', '/references') }), markdown: indexMd(m, ORIGIN) }];
  for (const slug of m.pages) {
    const a = m.area(slug), url = `/references/${slug}`;
    pages.push({ file: `references/${slug}.html`, md: `references/${slug}.md`, url, title: `${a.title} references`,
      description: `${(m.byArea.get(slug) || []).length} references for ${a.title.toLowerCase()}: evidence, confidence, licence and process, with a table you can filter.`,
      body: areaBody(slug, m, { feedback: feedbackBox(`${a.title} references`, url) }), markdown: areaMd(slug, m, ORIGIN) });
  }
  return { pages, files: referenceJson(m, { ORIGIN, revision, built, health }), llms: llmsSection(m, ORIGIN), urls: pages.map(p => p.url) };
}

// ----------------------------------------------------------------------------- command line

/** `node tools/site-references.mjs --experts [--check]`: write docs/experts.md from the working tree's registry. */
if (import.meta.url === `file://${process.argv[1]}`) {
  const root = path.resolve(import.meta.dirname, '..');
  if (!process.argv.includes('--experts')) {
    console.error('usage: node tools/site-references.mjs --experts [--check]');
    process.exit(2);
  }
  const files = execFileSync('git', ['ls-files', '-z'], { cwd: root }).toString().split('\0').filter(Boolean);
  const read = f => readFile(path.join(root, f), 'utf8');
  const m = referenceModel(await loadReferences({ files, read }), YAML.parse(await read('docs/areas.yaml')));
  const text = expertsMarkdown(m, { ORIGIN: 'https://cad-agent.valpatel.com' });
  const have = await read(EXPERTS).catch(() => '');
  if (process.argv.includes('--check')) {
    if (have !== text) { console.error(`${EXPERTS} is out of date: run node tools/site-references.mjs --experts`); process.exit(1); }
    console.log(`${EXPERTS} is current`);
  } else if (have !== text) { await writeFile(path.join(root, EXPERTS), text); console.log(`wrote ${EXPERTS}`); }
  else console.log(`${EXPERTS} is current`);
}
