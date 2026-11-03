// The reference knowledge base on the site (#323 phase 3; tools/site-references.mjs). Checks:
// - the loader against the registry's own rules;
// - the built pages, JSON, llms.txt and Markdown twins against the committed records;
// - [ref:<id>] links;
// - that no record becomes a catalogue entry or reaches llms-full.txt;
// - docs/experts.md is the generator's output.
// The pages in a real browser (filters, both themes, walls of text): tests/site/website-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import YAML from 'yaml';
import { builtSite } from './built-site.mjs';
import {
  CORE, DIR, EXPERTS, LADDER, UNPLACED, areaOf, areaTree, barChart, expertsMarkdown, linkTags, loadReferences, mdTags, referenceModel,
  referenceJson, referenceSite,
} from '../../tools/site-references.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const ORIGIN = 'https://cad-agent.valpatel.com';
const git = (...a) => execFileSync('git', a, { cwd: root, maxBuffer: 1 << 28 }).toString();
const tracked = git('ls-tree', '-r', '-z', '--name-only', 'HEAD').split('\0').filter(Boolean);
const show = async f => git('show', `HEAD:${f}`);
const refs = await loadReferences({ files: tracked, read: show });
const model = referenceModel(refs, YAML.parse(await show('docs/areas.yaml')));
const site = await builtSite('cad-agent-references-');
const out = site.dir;
test.after(() => site.done());
const files = (await readdir(out, { recursive: true, withFileTypes: true })).filter(e => e.isFile())
  .map(e => path.relative(out, path.join(e.parentPath, e.name)).split(path.sep).join('/'));
const json = async f => JSON.parse(await readFile(path.join(out, f), 'utf8'));
const text = f => readFile(path.join(out, f), 'utf8');
// Records placed in no docs/areas.yaml area: this number may only fall (place them, do not add more).
const UNPLACED_MAX = 71;

// ----------------------------------------------------------------------------- the loader

/** A registry from a dictionary of files, for the loader's own rules. */
const fake = fs => loadReferences({ files: Object.keys(fs), read: async f => fs[f] });
const core = `schema: 1\nsources:\n  - {id: a-guide, title: A, org: A Co, areas: [fdm], used_for: [docs/x.md], verified: 2026-01-01 read}\nunverified:\n  - {id: b-later, title: B}\n`;

test('a shard extends a read source by the registry\'s rule: lists united, the core keeps its own values', async () => {
  const r = await fake({ [CORE]: core, [`${DIR}guides-x.yaml`]: 'schema: 2\nsources:\n  - {id: a-guide, extends: true, title: Changed, areas: [fdm, sheet-metal], evidence: {numbers: some}}\n' });
  const a = r.records.get('a-guide');
  assert.equal(a.title, 'A', 'a field both set keeps the core\'s value');
  assert.deepEqual(a.areas, ['fdm', 'sheet-metal']);
  assert.deepEqual(a.evidence, { numbers: 'some' }, 'a field the core lacks is added');
  assert.equal(a.status, 'source');
  assert.equal(r.others.get('b-later').status, 'unverified');
});

test('a shard record read at source is a source, and aliases of every entry resolve, as in the Python registry', async () => {
  const r = await fake({ [CORE]: core.replace('unverified:\n  - {id: b-later, title: B}', 'unverified:\n  - {id: b-later, title: B, aliases: [b]}'),
    [`${DIR}g.yaml`]: 'sources:\n  - {id: c-read, title: C, aliases: [c], evidence: {class: read}}\n  - {id: d-snip, title: D, evidence: {class: snippet-only}}\n  - {id: e-none, title: E, aliases: [a-guide]}\n' });
  assert.equal(r.records.get('c-read').status, 'source');
  assert.equal(r.records.get('d-snip').status, 'catalogued');
  assert.equal(r.records.get('e-none').status, 'catalogued');
  assert.equal(r.aliases.get('c'), 'c-read');
  assert.equal(r.aliases.get('b'), 'b-later');
  assert.equal(r.aliases.has('a-guide'), false, 'an alias never shadows an id');
});

test('the loader refuses an extension of nothing and a second record with one id', async () => {
  await assert.rejects(fake({ [CORE]: core, [`${DIR}g.yaml`]: 'sources:\n  - {id: b-later, extends: true}\n' }), /extends no read source/);
  await assert.rejects(fake({ [CORE]: core, [`${DIR}g.yaml`]: 'sources:\n  - {id: a-guide, title: Again}\n' }), /also in research\/references\.yaml/);
  const r = await fake({ [CORE]: core, [`${DIR}vocab.yaml`]: 'kind: {}\n', [`${DIR}coverage.yaml`]: 'rows: []\n', [`${DIR}sub/x.yaml`]: 'sources: [{id: z}]\n' });
  assert.deepEqual(r.shards, [], 'vocab, coverage and files in subfolders are not shards');
});

test('areas place a record as cadagent.review.references area_of does', () => {
  const tree = areaTree({ domains: [{ slug: 'd', title: 'D', areas: [{ slug: 'fasteners', title: 'F', topics: [{ slug: 'inserts' }] }] }] });
  assert.equal(areaOf('fasteners', tree), 'fasteners');
  assert.equal(areaOf('inserts', tree), 'fasteners');
  assert.equal(areaOf('fasteners/inserts', tree), 'fasteners');
  assert.equal(areaOf('other/inserts', tree), null);
  assert.equal(areaOf('pricing', tree), null);
  assert.equal(areaOf(7, tree), null);
});

// ----------------------------------------------------------------------------- what the site publishes

test('index.json counts every committed record once, and each area file lists exactly its records', async () => {
  // Counted from the YAML here, not through the module under test.
  const own = [];
  for (const f of tracked.filter(f => /^research\/references\/[^/]+\.yaml$/.test(f) && !/\/(vocab|coverage)\.yaml$/.test(f)))
    for (const r of YAML.parse(await show(f)).sources) if (!r.extends) own.push(r.id);
  const sources = YAML.parse(await show(CORE)).sources.map(s => s.id);
  const index = await json('catalog/references/index.json');
  assert.equal(index.schema, 'cad-agent-references/1');
  assert.equal(index.totals.records, own.length + sources.length);
  assert.equal(index.totals.catalogued, own.length);
  assert.equal(index.totals.sources, sources.length);
  assert.deepEqual(Object.keys(index.totals.by_evidence), LADDER.filter(k => index.totals.by_evidence[k] !== undefined));
  const seen = new Set();
  for (const a of index.areas) {
    const area = await json(`catalog/references/${a.slug}.json`);
    assert.equal(area.records.length, a.records, a.slug);
    assert.equal(area.count, a.records, a.slug);
    for (const r of area.records) {
      seen.add(r.id);
      assert.ok(r.placed.includes(a.slug), `${r.id} is in ${a.slug}.json but not placed there`);
      assert.equal(`/references/${r.placed[0]}#${r.id}`, model.home(r.id), `${r.id}: its row is in its first area`);
      assert.ok(['source', 'catalogued'].includes(r.status), r.id);
    }
    assert.ok(files.includes(`references/${a.slug}.html`) && files.includes(`references/${a.slug}.md`), a.slug);
  }
  assert.deepEqual([...seen].sort(), [...own, ...sources].sort(), 'every record is in some area file, once per area');
  // The whole base in one fetch (an offline mirror reads only index.json): each record once, with where it is.
  assert.deepEqual(index.records.map(r => r.id), [...own, ...sources].sort((a, b) => (a < b ? -1 : 1)));
  for (const r of index.records) {
    for (const k of Object.keys(index.record_fields)) if (k !== 'url' || !r.isbn) assert.ok(k in r, `${r.id}: no ${k}`);
    assert.ok(r.url === null || /^https?:\/\//.test(r.url), r.id);
    assert.ok(LADDER.includes(r.evidence), `${r.id}: evidence ${r.evidence}`);
    assert.equal(`/references/${r.areas[0]}#${r.id}`, model.home(r.id), 'the first area is where its row is');
  }
  assert.ok(index.totals.unplaced <= UNPLACED_MAX, `${index.totals.unplaced} records are not placed in an area (at most ${UNPLACED_MAX}): give them docs/areas.yaml slugs`);
  if (index.totals.unplaced < UNPLACED_MAX) console.log(`  ${index.totals.unplaced} unplaced: lower UNPLACED_MAX to it`);
  // A catalogued record is a snippet: its licence unread and nothing standing on it.
  for (const a of index.areas) for (const r of (await json(`catalog/references/${a.slug}.json`)).records.filter(r => r.status === 'catalogued')) {
    assert.equal(r.evidence_class, 'snippet-only', r.id);
    assert.equal(r.licence.read, false, r.id);
    assert.deepEqual(r.used_for, [], r.id);
  }
});

test('each area page charts its records and lists one row per record, which [ref:] links reach', async () => {
  for (const slug of model.pages) {
    const html = await text(`references/${slug}.html`), list = model.byArea.get(slug) || [];
    const rows = [...html.matchAll(/<tr id="([^"]+)" data-kind=/g)].map(m => m[1]);
    assert.deepEqual(rows, list.map(r => r.id), slug);
    if (list.length) {
      assert.ok((html.match(/<figure class="refs-chart/g) || []).length >= 4, `${slug}: the charts`);
      for (const k of ['evidence', 'confidence', 'kind', 'licence']) assert.match(html, new RegExp(`data-filter="${k}"`), `${slug}: ${k} chart`);
      assert.match(html, /<form class="refs-filters" role="search" hidden>/, `${slug}: the filters wait for the script`);
    }
    for (const row of model.coverageIn.get(slug) || []) assert.ok(html.includes(row.topic.replace(/&/g, '&amp;').replace(/'/g, '&#39;')), `${slug}: ${row.topic}`);
  }
  // The drafts the map wrote were never posted, and the pages say so.
  const drafted = model.rows.filter(r => r.draft_issue);
  assert.ok(drafted.length >= 1);
  for (const r of drafted) assert.match(await text(`references/${r.placed[0]}.html`), /Drafted issue, never posted/);
});

test('[ref:<id>] in a page links to the record and the source; code, links and unknown ids stay as written', async () => {
  const id = 'pem-handbook', home = model.home(id);
  assert.match(home, /^\/references\/[a-z0-9-]+#pem-handbook$/);
  const html = linkTags(`<p>See [ref:${id}].</p><pre><code>[ref:${id}]</code></pre><a href="/x">[ref:${id}]</a><p>[ref:no-such-id] [ref:b c]</p>`, model);
  assert.match(html, new RegExp(`<span class="ref-cite">\\[<a class="ref-key" href="${home}" title="[^"]+">${id}</a><a class="ref-out" href="https://`));
  assert.ok(html.includes(`<code>[ref:${id}]</code>`) && html.includes(`<a href="/x">[ref:${id}]</a>`) && html.includes('[ref:no-such-id] [ref:b c]'));
  const unread = [...refs.others.keys()][0];
  assert.match(linkTags(`<p>[ref:${unread}]</p>`, model), /class="ref-cite ref-unread"/);
  // In the site: a page that cites leaves no bare tag of a known record, and loads the style for its links.
  const page = await text('research/sheet-metal-joining.html');
  assert.match(page, /class="ref-cite"/);
  assert.match(page, /<link rel="stylesheet" href="\/web\/references\.css">/);
  const bare = [...page.replace(/<(code|pre)\b[\s\S]*?<\/\1>/g, '').matchAll(/\[ref:([a-z0-9-]+)\](?!<)/g)].map(m => m[1]).filter(k => model.home(k));
  assert.deepEqual(bare, []);
});

test('Markdown twins link [ref:] tags to the records\' pages; code is left alone', () => {
  const md = `A [ref:pem-handbook] rule.\n\n\`[ref:pem-handbook]\`\n\n\`\`\`\n[ref:pem-handbook]\n\`\`\`\n[ref:pem-handbook](kept)\n`;
  const page = model.home('pem-handbook').slice(1).split('#')[0];
  const twin = mdTags(md, 'research/x.md', model, { ORIGIN });
  assert.ok(twin.startsWith(`A [ref:pem-handbook](${path.posix.relative('research', page)}.md#pem-handbook) rule.`), twin);
  assert.ok(twin.includes('`[ref:pem-handbook]`') && twin.includes('```\n[ref:pem-handbook]\n```') && twin.includes('[ref:pem-handbook](kept)'));
  assert.ok(mdTags(md, 'research/x.md', model, { ORIGIN, absolute: true }).startsWith(`A [ref:pem-handbook](${ORIGIN}/${page}.md#pem-handbook)`));
});

test('records are not catalogue entries, and llms.txt has one line per area and no record', async () => {
  const catalogued = [...refs.records.values()].filter(r => r.status === 'catalogued');
  const catalog = await json('catalog.json');
  const itemIds = new Set(catalog.items.map(i => i.id));
  assert.deepEqual(catalogued.filter(r => itemIds.has(r.id)).map(r => r.id), []);
  assert.doesNotMatch(JSON.stringify(catalog), /\/references\/|snippet-only/);
  const llms = await text('llms.txt');
  const section = llms.split('\n## References\n')[1];
  assert.ok(section, 'llms.txt has a References section');
  const lines = section.split('\n').filter(l => l.startsWith('- '));
  assert.deepEqual(lines.map(l => l.match(/\/references\/([a-z0-9-]+)\.md\)/)?.[1]), model.pages);
  for (const r of catalogued) assert.ok(!llms.includes(r.url || '\0') && !llms.includes(`${r.id}`), `llms.txt names ${r.id}`);
  const full = await text('llms-full.txt');
  assert.doesNotMatch(full, /^Source: https:\/\/cad-agent\.valpatel\.com\/references/m, 'llms-full.txt carries no reference page');
  assert.ok(!full.includes('Catalogued records are search snippets'), 'llms-full.txt carries no reference page');
  const sitemap = await text('sitemap.xml');
  for (const slug of model.pages) assert.ok(sitemap.includes(`<loc>${ORIGIN}/references/${slug}</loc>`), slug);
});

test('docs/experts.md is what the generator writes from the committed registry', async () => {
  assert.equal(await show(EXPERTS), expertsMarkdown(model, { ORIGIN }), 'run node tools/site-references.mjs --experts and commit docs/experts.md');
  const md = expertsMarkdown(model, { ORIGIN });
  const sources = [...refs.records.values()].filter(r => r.status === 'source');
  assert.ok(md.includes(`${sources.length} read sources`));
  for (const r of sources.filter(r => /^https:\/\//.test(r.url || '')).slice(0, 50)) assert.ok(md.includes(r.url.replace(/[()\s]/g, encodeURIComponent)), r.id);
  for (const r of [...refs.records.values()].filter(r => r.status === 'catalogued')) assert.ok(!md.includes(r.id), `${r.id} is catalogued, not an expert's source yet`);
});

test('a hostile record is shown as text: no markup, script URL or broken table gets through', async () => {
  const evil = '<img src=x onerror=alert(1)>"\'&|*[x](javascript:alert(2))';
  const yaml = v => JSON.stringify(v);                               // JSON is YAML: the strings arrive as written
  const fs = {
    [CORE]: `sources:\n  - {id: z-core, title: ${yaml(evil)}, org: ${yaml(evil)}, authors: [${yaml(evil)}], url: "javascript:alert(3)", areas: [fdm], used_for: [docs/x.md], verified: ${yaml(evil)}}\n`,
    [`${DIR}g.yaml`]: `sources:\n  - {id: z-cat, title: ${yaml(evil)}, org: ${yaml(evil)}, url: "https://example.com/a|b<c>(d)", summary: ${yaml(evil)}, areas: [fdm], kind: ${yaml(evil)},
      licence: {class: ${yaml(evil)}, spdx: ${yaml(evil)}, read: false, note: ${yaml(evil)}}, evidence: {class: snippet-only, numbers: claimed},
      claims: [{text: ${yaml(evil)}, status: ${yaml(evil)}}], process_groups: [${yaml(evil)}], assessment: {role: ${yaml(evil)}, caveat: ${yaml(evil)}}}\n`,
    [`${DIR}coverage.yaml`]: `rows:\n  - {id: r1, number: '1', topic: ${yaml(evil)}, status: partly, areas: [fdm], gap: ${yaml(evil)}, draft_issue: {title: ${yaml(evil)}, posted: false}}\nwanted:\n  - {group: print, title: ${yaml(evil)}, areas: [fdm], text: ${yaml(evil)}}\n`,
  };
  const m = referenceModel(await fake(fs), { domains: [{ slug: 'manufacturing', title: 'Manufacturing', areas: [{ slug: '3d-printing', title: '3D printing', topics: [{ slug: 'fdm' }] }] }] });
  const s = referenceSite(m, { ORIGIN, revision: 'r', built: 'b', feedbackBox: () => '' });
  const html = s.pages.map(p => p.body).join('') + linkTags('<p>[ref:z-core] [ref:z-cat]</p>', m);
  assert.doesNotMatch(html, /<img|onerror=alert\(1\)>|<script/i, 'markup from a record is escaped');
  assert.doesNotMatch(html, /href="\s*javascript:/i, 'a script URL is never a link');
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;'));
  for (const [, text] of s.files) JSON.parse(text);
  for (const p of s.pages) for (const line of p.markdown.split('\n').filter(l => l.startsWith('| ') && !l.startsWith('| Record') && !l.startsWith('|---')))
    assert.equal(line.replace(/\\\|/g, '').split('|').length, 9, `${p.md}: a record row keeps its 7 cells: ${line}`);
  // In Markdown an escaped \< or \] is text; an unescaped one would be markup or a link.
  const live = /(?<!\\)<img|(?<!\\)\]\(javascript:/i;
  for (const p of s.pages) assert.doesNotMatch(p.markdown, live, p.md);
  const experts = expertsMarkdown(m, { ORIGIN });
  assert.doesNotMatch(experts, live);
  assert.ok(experts.includes('https://example.com/a%7Cb%3Cc%3E%28d%29') === false, 'a catalogued record is not an expert\'s source');
});

test('charts are drawn as links that filter, with what they show spoken', () => {
  const svg = barChart({ title: 'Evidence', filter: 'evidence', rows: [{ value: 'read', label: 'read', n: 3 }, { value: 'measured', label: 'measured', n: 0 }] });
  assert.match(svg, /aria-label="Evidence: read 3, measured 0"/);
  assert.match(svg, /<a href="\?evidence=read#records" data-filter="evidence" data-value="read">/);
  assert.equal((svg.match(/class="refs-chart-bar/g) || []).length, 1, 'an empty row draws no bar');
});

test('the reference pages\' stylesheet sets colours only through the site\'s tokens', async () => {
  const css = (await show('web/references.css')).replace(/\/\*[\s\S]*?\*\//g, '');
  assert.deepEqual(css.match(/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/gi) || [], [], 'use var(--token) from web/site.css, so both themes apply');
  const tokens = new Set([...(await show('web/site.css')).matchAll(/--([\w-]+):/g)].map(m => m[1]));
  const used = [...css.matchAll(/var\(--([\w-]+)/g)].map(m => m[1]);
  assert.deepEqual([...new Set(used.filter(t => !tokens.has(t)))], [], 'every token exists in web/site.css');
});
