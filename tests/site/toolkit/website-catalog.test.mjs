import {createHash} from 'node:crypto';
// The catalogue (/catalog, /catalog.json, /catalog/index.json, /catalog/<area>.json), built from HEAD: every entry has
// a picture of our own and a place in the area map, the JSON files agree with each other and with the page, and the
// schema-1 fields and old links keep working. Behaviour in browsers: tests/site/toolkit/website-catalog-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { YAML } from '../npm-context.mjs';
import { TINT } from '../../../tools/site/compiler/catalog-art.mjs';
import { catalogueAudit, catalogueAuditHTML } from '../../../tools/site/compiler/site-catalog.mjs';
import { builtSite } from '../built-site.mjs';

const root = path.resolve(import.meta.dirname, '../../..');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-catalog-'));
const site = await builtSite('cad-agent-catalog-site-');         // CAD_AGENT_SITE, or a fresh build of HEAD
const out = site.dir;
test.after(() => Promise.all([rm(tmp, { recursive: true, force: true }), site.done()]));

const ORIGIN = 'https://cad-agent.valpatel.com';
const json = async f => JSON.parse(await readFile(path.join(out, f), 'utf8'));
const local = url => path.join(out, decodeURIComponent(new URL(url, ORIGIN).pathname.replace(/^\//, '')));
const catalog = await json('catalog.json');
const index = await json('catalog/index.json');
const page = await readFile(path.join(out, 'catalog.html'), 'utf8');
const areas = YAML.parse(execFileSync('git', ['show', 'HEAD:docs/areas.yaml'], { cwd: root }).toString());
const domainSlugs = areas.domains.map(d => d.slug);
const areaSlugs = areas.domains.flatMap(d => d.areas.map(a => a.slug));
const BUCKETS = ['cross-cutting', 'unplaced'];
const show = f => execFileSync('git', ['show', `HEAD:${f}`], { cwd: root }).toString();
const OUTSIDE = ['project', 'library', 'benchmark'];

const auditHeader = r => `# Supply-chain and resource report\n\nWhat cad-agent depends on, vendors and links to, checked on ${r.as_of} at revision \`${r.revision.slice(0, 12)}\` (online checks).`;
const auditFixture = (check = 'repo-archived', subject = 'url:https://github.com/owner/part') => ({
  schema: 'cad-agent-supply-chain/1', mode: 'online', as_of: '2024-02-29', revision: 'a'.repeat(40),
  findings: [{ check, subject, severity: 'medium', fp: '0123456789abcdef', title: 'Archived repository', evidence: 'last push 2023-01-01', accepted: 'Historical prior art only.' }],
});
const auditReader = r => catalogueAudit(r, auditHeader(r));

test('dated catalogue observations match identities, preserve decisions and retain accepted evidence', () => {
  const r = auditFixture(), get = auditReader(r);
  for (const kind of OUTSIDE) {
    const entry = { kind, url: 'https://github.com/OWNER/Part/tree/main', status: 'reference' }, before = structuredClone(entry);
    const audit = get(entry);
    assert.equal(audit.as_of, '2024-02-29', 'old observations retain their date, not the build date');
    assert.equal(audit.observations[0].label, 'Archived');
    assert.equal(audit.observations[0].accepted, 'Historical prior art only.', 'acceptance is disposition, not erasure');
    assert.deepEqual(entry, before, 'curated status and identity are untouched');
  }
  for (const url of ['https://github.com/other/part', 'https://github.com/owner/part-extra', 'https://github.com/owner-part',
    'https://github.com.evil.test/owner/part', 'https://github.com:444/owner/part', 'https://owner@github.com/owner/part',
    'https://example.test/?url=https://github.com/owner/part', 'javascript:alert(1)', 'invalid']) {
    assert.equal(get({ kind: 'project', name: 'owner/part', url }), null, url);
  }
  assert.equal(get({ kind: 'guide', url: 'https://github.com/owner/part' }), null, 'our guide is not the outside project');
  const stale = auditReader(auditFixture('repo-stale'))({ kind: 'benchmark', url: 'https://github.com/owner/part' });
  assert.equal(stale.observations[0].label, 'Activity needs review');
  assert.doesNotMatch(catalogueAuditHTML(stale), /unmaintained|abandoned/i);
});

test('page observations keep path/query identity and uncertain checks do not assert a move or disappearance', () => {
  for (const [check, label] of [['link-unverified', 'Check incomplete'], ['link-dead', 'Unavailable'], ['link-redirect-domain', 'Destination changed']]) {
    const get = auditReader(auditFixture(check, 'url:https://example.test/Part?version=2#section'));
    const at = url => get({ kind: 'library', url });
    assert.equal(at('https://example.test/Part?version=2#other').observations[0].label, label);
    for (const url of ['https://example.test/part?version=2', 'https://example.test/Part?version=3',
      'https://example.test/Part', 'http://example.test/Part?version=2', 'https://example.test/Part/?version=2']) assert.equal(at(url), null, url);
  }
});

test('missing, malformed, offline and mismatched reports cannot silently produce unflagged cards', () => {
  const r = auditFixture();
  for (const bad of [undefined, {}, { ...r, schema: 'future/2' }, { ...r, mode: 'offline' },
    { ...r, as_of: '2024-02-30' }, { ...r, as_of: '2024-99-99' }, { ...r, revision: 'main' },
    { ...r, revision: [r.revision] }, { ...r, revision: 1234 },
    { ...r, findings: null }, { ...r, findings: [null] }, { ...r, findings: [r.findings[0], r.findings[0]] },
    { ...r, findings: [{ ...r.findings[0], accepted: true }] }, { ...r, findings: [{ ...r.findings[0], evidence: {} }] },
    { ...r, findings: [{ ...r.findings[0], fp: 1234567890123456 }] }, { ...r, findings: [{ ...r.findings[0], fp: ['0123456789abcdef'] }] },
    { ...r, findings: [{ check: 'repo-stale', subject: 'vendor:bad', title: { malformed: true } }] },
    { ...r, findings: [{ ...r.findings[0], subject: 'url:javascript:alert(1)' }] }]) {
    assert.throws(() => catalogueAudit(bad, auditHeader(r)), /security-report\.json/);
  }
  for (const md of [undefined, {}, '', auditHeader({ ...r, as_of: '2024-02-28' }), auditHeader({ ...r, revision: 'b'.repeat(40) }),
    auditHeader(r).replace('online checks', 'offline checks')]) assert.throws(() => catalogueAudit(r, md), /Markdown date\/revision/);
  // A new check may be valid elsewhere in the report, but it must be classified before affecting a card.
  for (const check of ['new-url-check', 'repo-new-check', 'constructor', '__proto__']) {
    const get = auditReader(auditFixture(check));
    assert.equal(get({ kind: 'project', url: 'https://github.com/unrelated/part' }), null);
    assert.throws(() => get({ kind: 'project', url: 'https://github.com/owner/part' }), /unmapped check/);
  }
  const unrelated = auditReader(auditFixture('repo-stale', 'vendor:owner/part'));
  assert.equal(unrelated({ kind: 'project', url: 'https://github.com/owner/part' }), null, 'valid non-card evidence is not guessed from its name');
});

test('audit evidence is escaped text inside one dated notes fold', () => {
  const r = auditFixture(), bad = '<img src=x onerror=alert(1)><script>bad</script>';
  Object.assign(r.findings[0], { title: bad, evidence: bad, accepted: bad });
  const a = auditReader(r)({ kind: 'benchmark', url: 'https://github.com/owner/part' });
  const html = catalogueAuditHTML(a, bad, bad);
  assert.equal((html.match(/<details\b/g) || []).length, 1);
  assert.match(html, /<time datetime="2024-02-29">2024-02-29<\/time>/);
  assert.match(html, /href="\/research\/security-report"/);
  assert.match(html, /revision <code>aaaaaaaaaaaa<\/code>/);
  assert.match(html, /Recorded disposition:/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<img|<script/);
  assert.equal(catalogueAuditHTML(null), '');
  assert.match(catalogueAuditHTML(null, 'A plain note'), /<summary>Our notes<\/summary>/);
});

test('the committed report reaches HTML and JSON cards without rewriting curated status', () => {
  const report = JSON.parse(show('docs/research/security-report.json'));
  const get = catalogueAudit(report, show('docs/research/security-report.md'));
  for (const item of catalog.items) {
    const expected = get(item);
    const card = page.match(new RegExp(`<li data-item[^>]*id="${item.id}"[\\s\\S]*?</li>`))?.[0];
    assert.ok(card, item.id);
    if (!expected) {
      assert.equal(item.audit, undefined, item.id);
      assert.doesNotMatch(card, /class="card-notes card-audit"/, item.id);
    } else {
      assert.deepEqual(item.audit, { ...expected, report: ORIGIN + expected.report }, item.id);
      assert.ok(card.includes(catalogueAuditHTML(expected, item.notes, OUTSIDE.includes(item.kind) ? item.policy : '')), item.id);
      assert.ok(existsSync(local(item.audit.report + '.html')), 'the report link resolves in the same publication');
      assert.ok(card.includes(`data-status="${item.status}"`), item.id);
    }
  }
  assert.match(catalog.fields.audit, /Absence is not a safety verdict/);
});

test('every previously published page retains its public identity after source consolidation', async () => {
  const baseline = JSON.parse(await readFile(path.join(root, 'tests/fixtures/site-page-identities.json'), 'utf8'));
  assert.ok(baseline.pages.some(p => p.id === 'guide-index') && baseline.pages.some(p => p.id === 'research-index')
    && baseline.pages.some(p => p.id === 'lesson-index'), 'the recorded identity fixture covers all knowledge kinds');
  assert.equal(new Set(baseline.pages.map(p => p.id)).size, baseline.pages.length);
  for (const expected of baseline.pages) {
    const actual = catalog.items.find(i => i.id === expected.id);
    assert.ok(actual, `${expected.id} disappeared`);
    for (const key of ['kind', 'url', 'markdown']) assert.equal(actual[key], expected[key], `${expected.id}: ${key}`);
  }
});

test('schema 2 keeps every schema-1 field, with the same meaning', () => {
  assert.equal(catalog.schema, 'cad-agent-catalog/2');
  for (const k of ['origin', 'repo', 'revision', 'built', 'tagline', 'description']) assert.ok(catalog[k], `top-level ${k}`);
  assert.equal(catalog.index, `${ORIGIN}/catalog/index.json`);
  const TYPES = ['upstream', 'tool', 'doc', 'lesson', 'benchmark', 'library', 'research', 'skill', 'agent', 'demo'];
  for (const i of catalog.items) {
    for (const k of ['type', 'status', 'name', 'url', 'summary']) assert.equal(typeof i[k], 'string', `${i.id}: ${k}`);
    assert.ok(TYPES.includes(i.type), `${i.id}: type ${i.type}`);
    assert.ok(i.url.startsWith('https://'), `${i.id}: url`);
    for (const k of ['license', 'policy', 'how', 'last_push', 'source']) if (k in i) assert.ok(i[k] === null || typeof i[k] === 'string', `${i.id}: ${k}`);
    if ('stars' in i) assert.ok(i.stars === null || Number.isInteger(i.stars), `${i.id}: stars`);
    if (i.markdown) assert.ok(i.markdown.startsWith(ORIGIN) && existsSync(local(i.markdown)), `${i.id}: markdown ${i.markdown}`);
  }
  // Every entry schema 1 listed is still there under the same type and name (the demos are new).
  const upstreams = YAML.parse(execFileSync('git', ['show', 'HEAD:software/vendor/upstreams/registry.yaml'], { cwd: root }).toString());
  for (const u of upstreams) assert.ok(catalog.items.some(i => i.type === 'upstream' && i.name === u.name), u.name);
  const commands = catalog.items.filter(i => i.type === 'tool').length;
  assert.equal(commands, catalog.items.filter(i => i.kind === 'tool').length);
});

test('schema 2 lost gyropup in v0.10.0 but kept its schema value: fields.removed says so, and no entry has it', async () => {
  // Bumping to /3 would break every reader that checks for /2, so the removal is recorded in the file instead.
  assert.match(catalog.fields.removed, /gyropup: removed in v0\.10\.0\. Do not rely on it/);
  assert.match(catalog.fields.removed, /cad-agent-catalog\/2/);
  assert.ok(catalog.items.every(i => !('gyropup' in i)), 'a catalog.json entry has gyropup');
  const files = (await readdir(path.join(out, 'catalog'))).filter(f => f.endsWith('.json') && f !== 'index.json');
  assert.ok(files.length > 20, `only ${files.length} area files`);
  for (const f of files) {
    const area = await json(`catalog/${f}`);
    assert.ok(area.items.every(i => !('gyropup' in i)), `catalog/${f}: an entry has gyropup`);
    assert.doesNotMatch(JSON.stringify(area.fields), /gyropup/i, `catalog/${f}: its fields describe gyropup`);
  }
});

test('schema-1 fields keep their schema-1 values: summary, licence (null stays null), tool urls', () => {
  // Schema 1's builder, as it was (tools/site/build-site.mjs before catalogue v2), run over today's data.
  const landscape = JSON.parse(show('docs/research/landscape.json'));
  const upstreams = YAML.parse(show('software/vendor/upstreams/registry.yaml'));
  const notes = new Map(landscape.projects.map(p => [p.name, p.notes || '']));
  const want = [
    ...upstreams.map(u => ({ type: 'upstream', status: u.status, name: u.name, url: u.url, summary: notes.get(u.name) || u.what || u.policy,
      policy: u.policy, license: u.license, stars: u.stars, last_push: u.last_push })),
    ...landscape.libraries.map(l => ({ type: 'library', status: l.status || 'reference', name: l.name, url: l.url || `https://github.com/${l.name}`,
      license: l.license_spdx, stars: l.stars, last_push: l.last_push, summary: l.use || l.role || l.notes || '' })),
    ...landscape.benchmarks.map(b => ({ type: 'benchmark', status: b.status === 'unverified' ? 'unverified' : 'reference', name: b.name, url: b.url,
      license: b.license_spdx || b.license, summary: [b.tasks || b.notes, b.size, b.venue || b.paper].filter(Boolean).join(' · ')
        || (b.status === 'unverified' ? 'Listed from its paper or site; tasks, data and licence not yet checked.' : '') })),
  ].map(o => JSON.parse(JSON.stringify(o)));             // as schema 1 wrote them: undefined left out, null kept
  const S1 = ['type', 'status', 'name', 'url', 'summary', 'how', 'policy', 'license', 'stars', 'last_push', 'markdown', 'source'];
  const ADDED = { benchmark: ['stars'] };               // new where recorded; catalog.json fields.schema_1 says so
  for (const w of want) {
    const got = catalog.items.find(i => i.type === w.type && i.name === w.name);
    assert.ok(got, `${w.type} ${w.name} is missing`);
    for (const k of S1) {
      if (k in w) assert.deepEqual(got[k], w[k], `${w.name}: ${k}`);
      else if (!ADDED[w.type]?.includes(k)) assert.ok(!(k in got), `${w.name}: ${k} was not in schema 1`);
    }
  }
  // No entry has a null licence any more: #151 recorded "none" for the last one (CADPrompt), as the supply-chain
  // report's catalogue-no-licence check asks. The loop above still fails if schema 2 drops or changes a null.
  // Our own entries: schema 1 wrote these fields and no others; the additions are the ones fields.schema_1 lists.
  const OWN = { tool: ['summary', 'how'], doc: ['summary', 'markdown', 'source'] };
  const OWN_ADDED = { tool: ['license', 'markdown'], doc: ['license'] };
  const terms = [...(YAML.parse(show('docs/catalog.yaml')).license_overrides || [])].sort((a,b)=>b.prefix.length-a.prefix.length);
  for (const i of catalog.items.filter(i => !['upstream', 'library', 'benchmark', 'demo'].includes(i.type))) {
    const kind = i.type === 'tool' ? 'tool' : 'doc';
    const source = i.source?.split('/blob/dev/')[1] || '';
    const license = terms.find(t=>source.startsWith(t.prefix))?.license || 'MIT';
    for (const k of S1.slice(4)) {
      if (OWN[kind].includes(k)) assert.ok(k in i, `${i.id}: ${k} (schema 1 had it)`);
      else if (OWN_ADDED[kind].includes(k)) assert.ok(!(k in i) || (k === 'license' ? i.license === license : true), `${i.id}: ${k}`);
      else assert.ok(!(k in i), `${i.id}: ${k} was not in schema 1 for our own entries`);
    }
  }
  for (const k of ['markdown', 'stars', 'license "MIT"']) assert.ok(catalog.fields.schema_1.includes(k), `fields.schema_1 names the addition: ${k}`);
  for (const t of catalog.items.filter(i => i.type === 'tool')) {
    const cmd = t.name.replace(/^cad-agent /, '');
    assert.equal(t.url, `${ORIGIN}/docs/toolkit`, t.id);
    assert.equal(t.how, `cad-agent ${cmd} --help`, t.id);
    // New: the page that documents it, and that page's Markdown twin.
    assert.ok(t.doc?.startsWith(`${ORIGIN}/`), `${t.id}: doc ${t.doc}`);
    assert.ok(t.markdown && existsSync(local(t.markdown)) && t.markdown === `${t.doc.split('#')[0]}.md`, `${t.id}: markdown ${t.markdown} for ${t.doc}`);
  }
});

test("an outside entry's licence note reaches its card, benchmarks included", () => {
  const landscape = JSON.parse(show('docs/research/landscape.json'));
  const noted = [...landscape.projects.map(p => ['upstream', p]), ...landscape.libraries.map(l => ['library', l]),
    ...landscape.benchmarks.map(b => ['benchmark', b])].filter(([, e]) => e.license_note);
  assert.ok(noted.some(([type]) => type === 'benchmark'), 'a benchmark with a licence note to check');
  for (const [type, e] of noted) {
    const got = catalog.items.find(i => i.type === type && i.name === e.name);
    if (!got) continue;                                  // a landscape project that is not an upstream has no card
    assert.ok(got.notes?.includes(e.license_note.split(':')[0]), `${e.name}: notes ${got.notes}`);
    if (type === 'benchmark' && got.status === 'unverified') assert.ok(!/licence not yet checked/.test(got.notes), `${e.name}: ${got.notes}`);
  }
});

test('every cover is used once and no dense figure is a cover', async () => {
  const by = new Map();
  for (const i of catalog.items) by.set(i.cover, [...(by.get(i.cover) || []), i.id]);
  for (const [cover, ids] of by) assert.equal(ids.length, 1, `${cover} is the cover of ${ids.join(', ')}`);
  const data = YAML.parse(show('docs/catalog.yaml'));
  for (const f of data.dense || []) {
    const stem = path.basename(f).replace(/\.[a-z]+$/, '');
    for (const i of catalog.items) assert.ok(!i.cover.includes(stem) && !(i.cover_animated || '').includes(stem), `${i.id} uses the dense ${f}`);
  }
});

test('Toolkit is a native capability with package terms and the same catalogue identity', async () => {
  for(const id of ['scada-elements','scada-simulations']) {
    const entry=catalog.items.find(i=>i.id==='demo-'+id);
    assert.ok(entry,id);assert.equal(entry.kind,'demo');assert.equal(entry.status,'ours');assert.equal(entry.license,'MIT');
    assert.ok(entry.url.startsWith(ORIGIN+'/toolkit/scada/'));
  }
  const toolkit=await json('toolkit/scada/catalog.json');
  assert.equal(toolkit.schema,'cad-agent-scada-browser/1');
  assert.equal(toolkit.license,'MIT');
  assert.equal(toolkit.simulations[0].id,'wastewater-digester');
  for(const route of ['toolkit','toolkit/scada','toolkit/scada/elements','toolkit/scada/simulations','toolkit/models']) {
    const html=await readFile(path.join(out,route+'.html'),'utf8');
    assert.ok(html.includes(`<link rel="canonical" href="${ORIGIN}/${route}">`));
    assert.ok(html.includes('href="/toolkit" data-keep aria-current="page"'));
    assert.doesNotMatch(html,/<iframe\b|digester-insight|chatgpt\.site/);
    assert.doesNotMatch(html,/UNLICENSED|including the transferred SCADA libraries/);
    assert.ok((await readFile(path.join(out,route+'.md'),'utf8')).startsWith('# '));
  }
});

test('SCADA guides and skills resolve inside the published shared site frame',async()=>{
  const html=await readFile(path.join(out,'toolkit/scada.html'),'utf8');
  assert.doesNotMatch(html,/href="\/kit\/scada\/[^"#?]*\.md/);
  const destinations=new Set([...html.matchAll(/href="([^"#]+)"/g)].map(match=>match[1]).filter(href=>href.startsWith('/repo/folders/')||href.startsWith('/skills/scada-')||href.startsWith('/docs/practice/scada/')));
  assert.ok(destinations.size>=9,'library maps, local guide and all five domain skills are discoverable');
  for(const href of destinations) {
    const target=await readFile(local(href)+'.html','utf8');
    assert.match(target,/aria-label="Main"/);
    assert.match(target,/href="\/toolkit"/);
    assert.match(target,/href="\/docs\/agent-workflow"/);
    assert.match(target,/Valpatel Software LLC/);
  }
});

test('Toolkit working-example cards resolve to published local pages and complete owned assets', async () => {
  const overview=await readFile(path.join(out,'toolkit.html'),'utf8');
  const cards=[...overview.matchAll(/<article[^>]*data-toolkit-capability="([^"]+)"[^>]*>([\s\S]*?)<\/article>/g)];
  assert.equal(cards.length,7);
  for(const [,id,body] of cards) {
    const image=body.match(/<img[^>]*src="([^"]+)"/)[1];
    assert.ok(existsSync(local(image)),`${id} preview`);
    const href=body.match(/data-toolkit-launch href="([^"]+)"/)[1].replaceAll('&amp;','&');
    assert.ok(href.startsWith('/') && !href.startsWith('//'),`${id} must stay on the current site`);
    const route=local(href), target=existsSync(route)?route:route+'.html';
    assert.ok(existsSync(target),`${id} destination ${href}`);
    const url=new URL(href,ORIGIN);
    if(url.hash) assert.ok((await readFile(target,'utf8')).includes(`id="${url.hash.slice(1)}"`),`${id} destination anchor`);
    for(const key of ['guide','file']) if(url.searchParams.has(key)) assert.ok(existsSync(local(url.searchParams.get(key))),`${id} input asset`);
  }
  const guide=await json('web/toolkit/assembly/guide.json'),view=await json('web/toolkit/assembly/view.json');
  for(const binding of [guide.model,guide.assembly_plan,...view.parts]) {
    const bytes=await readFile(path.join(out,'web/toolkit/assembly',binding.file));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),binding.sha256,binding.file);
  }
  const model=await readFile(path.join(out,'toolkit/models.html'),'utf8');
  assert.match(model,/href="\/kit\/model\/model.css"/);
  assert.match(model,/<cad-model[^>]*src="\/web\/models\/gyropup.json"/);
});

test('compare draws what the tool printed: the front over every objective, the lower bound kept, labels clear', async () => {
  const data = JSON.parse(show('docs/img/explore/two-wheel-charts.json'));     // tools/explore_charts.py --check (pytest)
  const d = data.compare, svg = await readFile(local(catalog.items.find(i => i.id === 'tool-compare').cover), 'utf8');
  assert.ok(svg.includes(`FRONT (${d.front_over.join(', ').toUpperCase()})`), `the legend says the front is over ${d.front_over}`);
  assert.ok(!/<path d="M[^"]*L[^"]*" fill="none" stroke="#[0-9a-f]+" stroke-width="4"/.test(svg), 'front points are not joined (it is not a front on these two axes)');
  for (const p of d.points) assert.ok(svg.includes(`>${p.label}${p.lower_bound.length ? ' ≥ ' : '<'}`), `${p.label} is labelled${p.lower_bound.length ? ' with ≥' : ''}`);
  assert.ok(svg.includes('>Long range ≥ $1,682<'), 'the lower bound keeps its ≥ on the chart');
  assert.ok(d.points.some(p => p.lower_bound.includes('cost_usd')), 'the data still has a lower bound to keep');
  assert.match(svg, /aria-label="[^"]*Long range: at least \$1,682/, 'the label reads the lower bound as "at least"');
  // No label covers a mark or a lower-bound arrow (boxes as chartCover estimates them: 0.6 em per character).
  const marks = [...svg.matchAll(/<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"/g)].map(m => m.slice(1).map(Number))
    .filter(([, cy]) => cy > 60).map(([x, y, r]) => [x - r, y - r, x + r, y + r]);
  const arrows = [...svg.matchAll(/<path d="M([\d.]+) ([\d.]+)h16m-6-6 6 6-6 6"/g)].map(m => m.slice(1).map(Number)).map(([x, y]) => [x, y - 6, x + 16, y + 6]);
  const labels = [...svg.matchAll(/<text x="([\d.]+)" y="([\d.]+)" text-anchor="(start|end|middle)" font-family="[^"]*" font-size="(\d+)" font-weight="700" fill="[^"]*">([^<]+)</g)]
    .map(([, x, y, anchor, fs, t]) => { const w = t.length * fs * 0.6, x0 = anchor === 'start' ? +x : anchor === 'end' ? x - w : x - w / 2; return [t, [x0, y - fs + 3, x0 + w, +y + 3]]; });
  assert.equal(labels.length, d.points.length, 'one label per design');
  const hits = (b, c) => b[0] < c[2] && c[0] < b[2] && b[1] < c[3] && c[1] < b[3];
  for (const [t, box] of labels) {
    for (const m of [...marks, ...arrows]) assert.ok(!hits(box, m), `"${t}" covers a mark or arrow at ${m}`);
    for (const [u, other] of labels) if (u !== t) assert.ok(!hits(box, other), `"${t}" overlaps "${u}"`);
  }
  // Failing designs are drawn last, so a ring near a front point stays visible.
  assert.ok(svg.lastIndexOf('fill="none" stroke="') > svg.lastIndexOf('stroke="#fff" stroke-width="2.5"'), 'the failing ring is drawn above the filled marks');
  // A chart of a tool's result is a picture: it ranks like one in the overview (#185). catalog.json lists each kind in
  // featured order; the chart comes before every drawn call of the same maturity.
  const tools = catalog.items.filter(i => i.kind === 'tool'), c = tools.find(i => i.id === 'tool-compare');
  const drawn = tools.filter(t => /\/catalog\/covers\/tool-/.test(t.cover) && t !== c && t.maturity === c.maturity && !t.demo);
  assert.ok(drawn.length, 'there is a drawn call to rank against');
  for (const t of drawn) assert.ok(tools.indexOf(c) < tools.indexOf(t), `compare (a chart) is featured before ${t.id} (a drawn call)`);
});

test('a tool shares its demo\'s figure at another moment: the tool\'s result, not a second copy of the demo', async () => {
  const data = YAML.parse(show('docs/catalog.yaml'));
  for (const [cmd, t] of Object.entries(data.tools)) {
    if (t.still == null) continue;
    const tool = catalog.items.find(i => i.id === `tool-${cmd}`);
    const demo = catalog.items.find(i => i.kind === 'demo' && i.cover_animated && i.cover_animated === tool.cover_animated);
    assert.ok(demo, `${cmd}: its cover is a moment of a demo's figure`);
    assert.ok(data.demos.find(x => `demo-${x.id}` === demo.id).tools?.includes(cmd), `${cmd}: ${demo.id} names it in tools`);
    assert.notEqual(tool.cover, demo.cover, `${cmd}: not the demo's own still`);
    assert.notEqual(await readFile(local(tool.cover), 'utf8'), await readFile(local(demo.cover), 'utf8'), `${cmd}: a different moment`);
  }
  for (const cmd of ['gates', 'holes', 'optimise']) assert.ok(data.tools[cmd].still != null, `${cmd} shows its result`);
});

test('every entry has an id, a kind, our own cover and a place: areas from docs/areas.yaml, or a bucket', async () => {
  const ids = new Set();
  const KINDS = ['demo', 'tool', 'project', 'library', 'benchmark', 'guide', 'lesson', 'research', 'skill', 'agent'];
  for (const i of catalog.items) {
    assert.match(i.id, /^[a-z0-9][a-z0-9-]*$/, i.name);
    assert.ok(!ids.has(i.id), `duplicate id ${i.id}`);
    ids.add(i.id);
    assert.ok(KINDS.includes(i.kind), `${i.id}: kind ${i.kind}`);
    assert.ok(i.areas.length, `${i.id}: no areas`);
    for (const a of i.areas) assert.ok([...areaSlugs, ...domainSlugs, ...BUCKETS].includes(a), `${i.id}: unknown area ${a}`);
    if (i.areas.includes('unplaced')) assert.ok(OUTSIDE.includes(i.kind), `${i.id}: only outside entries wait to be placed`);
    assert.ok(i.cover?.startsWith(`${ORIGIN}/`), `${i.id}: cover ${i.cover}`);
    assert.ok(existsSync(local(i.cover)), `${i.id}: cover file ${i.cover}`);
    if (i.cover_animated) assert.ok(existsSync(local(i.cover_animated)), `${i.id}: ${i.cover_animated}`);
    assert.ok(typeof i.what === 'string' || i.what === null, `${i.id}: what`);
    assert.ok(['permissive', 'copyleft', 'other'].includes(i.licence_family), `${i.id}: licence_family ${i.licence_family}`);
    if (i.demo) assert.ok(i.demo.startsWith(ORIGIN), `${i.id}: demo ${i.demo}`);
  }
  for (const i of catalog.items) for (const r of i.related) assert.ok(ids.has(r) && r !== i.id, `${i.id}: related ${r}`);
  const unplaced = await json('catalog/unplaced.json');
  assert.deepEqual(unplaced.items.map(i => i.id).sort(), catalog.items.filter(i => i.areas.includes('unplaced')).map(i => i.id).sort());
});

test('no outside pictures: covers are our files, and the page and covers load nothing from elsewhere', async () => {
  for (const m of page.matchAll(/<img\b[^>]*>/g)) {
    const src = m[0].match(/\ssrc="([^"]+)"/)?.[1];
    assert.ok(src?.startsWith('/') && !src.startsWith('//'), `outside or missing image: ${m[0]}`);
    for (const attr of ['data-anim', 'srcset']) {
      const v = m[0].match(new RegExp(`\\s${attr}="([^"]+)"`))?.[1];
      if (v) assert.ok(v.startsWith('/') && !v.startsWith('//'), `${attr}: ${v}`);
    }
    assert.match(m[0], /\swidth="\d+"/, `no width: ${m[0]}`);
    assert.match(m[0], /\sheight="\d+"/, `no height: ${m[0]}`);
    assert.match(m[0], /\salt="[^"]*"/, `no alt: ${m[0]}`);
  }
  // Below the first screen every cover waits until it is near (the strip's first tiles may load at once).
  const cards = [...page.matchAll(/<li data-item[\s\S]*?<\/li>/g)].map(m => m[0]);
  for (const c of cards) assert.match(c, /<img [^>]*loading="lazy"/, c.slice(0, 120));
  const covers = (await readdir(path.join(out, 'catalog/covers'), { recursive: true })).filter(f => f.endsWith('.svg'));
  assert.ok(covers.length >= catalog.items.length / 2);
  for (const f of covers) {
    const svg = await readFile(path.join(out, 'catalog/covers', f), 'utf8');
    const refs = [...svg.matchAll(/\b(?:href|src)\s*=\s*"([^"]*)"|url\(\s*['"]?([^'")]+)/g)].map(m => m[1] ?? m[2]);
    for (const r of refs) assert.ok(r.startsWith('#') || r.startsWith('data:'), `${f} loads ${r}`);
    assert.doesNotMatch(svg, /<script|\son[a-z]+=|@import/i, f);
  }
});

test('the index and the area files agree with each other and with catalog.json', async () => {
  assert.equal(index.schema, 'cad-agent-catalog-index/1');
  assert.equal(index.count, catalog.items.length);
  const listed = [...index.domains.map(d => d.slug), ...index.domains.flatMap(d => d.areas.map(a => a.slug)), ...index.buckets.map(b => b.slug)];
  assert.deepEqual([...listed].sort(), [...domainSlugs, ...areaSlugs, ...BUCKETS].sort());
  const byId = new Map(catalog.items.map(i => [i.id, i]));
  const nodes = [...index.domains, ...index.domains.flatMap(d => d.areas), ...index.buckets];
  for (const n of nodes) {
    assert.equal(n.json, `${ORIGIN}/catalog/${n.slug}.json`);
    assert.equal(n.page, `${ORIGIN}/catalog?area=${n.slug}`);
    const file = await json(`catalog/${n.slug}.json`);
    assert.equal(file.schema, 'cad-agent-catalog-area/1');
    assert.equal(file.slug, n.slug);
    assert.equal(file.count, n.count, n.slug);
    assert.equal(file.items.length, n.count, n.slug);
    const expected = catalog.items.filter(i => i.areas.includes(n.slug) || (domainSlugs.includes(n.slug) && i.areas.some(a => areas.domains.find(d => d.slug === n.slug).areas.some(x => x.slug === a))));
    assert.deepEqual(file.items.map(i => i.id).sort(), expected.map(i => i.id).sort(), n.slug);
    for (const e of file.items) {
      const i = byId.get(e.id);
      for (const k of ['name', 'url', 'kind', 'cover', 'what', 'status', 'audit']) assert.deepEqual(e[k], i[k], `${n.slug}/${e.id}: ${k}`);
    }
  }
  for (const k of index.kinds) assert.equal(k.count, catalog.items.filter(i => k.kinds.includes(i.kind)).length, k.tab);
  assert.equal(index.kinds.reduce((n, k) => n + k.count, 0), catalog.items.length, 'every entry is under one kind tab');
  const llms = await readFile(path.join(out, 'llms.txt'), 'utf8');
  assert.match(llms, /catalog\/index\.json/);
  // A real direct path from llms must advertise each tool's actual guide, not merely a working catalogue index.
  const linked = new Set([...llms.matchAll(/https:\/\/[^\s)<>`]+/g)].map(m => m[0]));
  for (const tool of catalog.items.filter(i => i.kind === 'tool')) {
    assert.ok(linked.has(tool.markdown), `${tool.id}: its guide is missing from llms.txt: ${tool.markdown}`);
  }
  // Each file says what its fields mean.
  for (const k of ['count', 'kinds', 'maturity', 'domains', 'buckets']) assert.equal(typeof index.fields?.[k], 'string', `index.json fields.${k}`);
  for (const k of ['id', 'kind', 'areas', 'what', 'cover', 'doc', 'schema_1']) assert.equal(typeof catalog.fields?.[k], 'string', `catalog.json fields.${k}`);
  const area = await json('catalog/compliant-mechanisms.json');
  for (const k of ['level', 'items', 'kinds', 'count']) assert.equal(typeof area.fields?.[k], 'string', `area file fields.${k}`);
});

test('the page lists every entry once, grouped by kind, readable without script', () => {
  const cards = [...page.matchAll(/<li data-item[^>]*\bid="([^"]+)"[^>]*>/g)];
  assert.deepEqual(cards.map(m => m[1]).sort(), catalog.items.map(i => i.id).sort());
  for (const m of cards) assert.doesNotMatch(m[0], /\shidden\b/, `${m[1]} is hidden in the HTML`);
  assert.match(page, /<cad-gallery\b/);
  assert.match(page,/browse-limit="1"/,'legacy types use one compact preview each, with every entry still present');
  assert.match(page, /<script type="module" src="\/web\/site\.js"><\/script>/);
  assert.doesNotMatch(page, /<script>/, 'no inline script (CSP)');
  // Search, status and the existing browser test's hooks.
  assert.match(page, /<input [^>]*data-gallery-search/);
  assert.match(page, /data-gallery-status/);
  assert.match(page, /<label class="discover-search"[^>]*><span>Search everything<\/span>/);
});

test('old links still land: /catalog#tool style anchors, and every /catalog# link on the site', async () => {
  const pageIds = new Set([...page.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
  for (const old of ['tool', 'upstream', 'library', 'benchmark', 'docs', 'skills', 'agents', 'lessons', 'research']) assert.ok(pageIds.has(old), `#${old}`);
  const htmls = (await readdir(out, { recursive: true })).filter(f => f.endsWith('.html'));
  for (const f of htmls) {
    const html = await readFile(path.join(out, f), 'utf8');
    for (const m of html.matchAll(/href="\/catalog#([^"]+)"/g)) assert.ok(pageIds.has(m[1]), `${f} links /catalog#${m[1]}`);
  }
});

test('outside data cannot inject markup: a hostile registry entry is text on the page, in the JSON and in its cover', async () => {
  // A scratch worktree of HEAD whose registry has one entry with markup in every field the page shows.
  const wt = path.join(tmp, 'wt-hostile'), draft = path.join(tmp, 'draft-hostile');
  execFileSync('git', ['worktree', 'add', '--detach', '--quiet', wt, 'HEAD'], { cwd: root });
  let retained=null;
  try {
    const bad = n => `"><img src=x onerror=alert(${n})><script>alert(${n})</script>`;
    const entry = { name: `evil/${bad(1)}`, what: bad(2), areas: ['3d-printing'], url: 'https://github.com/evil/evil', license: bad(3),
      status: 'candidate', policy: bad(4), last_push: bad(5), stars: bad(6) };
    const registry = path.join(wt, 'software/vendor/upstreams/registry.yaml');
    await writeFile(registry, `${await readFile(registry, 'utf8')}\n${YAML.stringify([entry])}`);
    const landscapeFile=path.join(wt,'docs/research/landscape.json');
    const landscape=JSON.parse(await readFile(landscapeFile,'utf8'));
    landscape.projects.push({name:entry.name,url:entry.url,notes:bad(7),license_note:bad(8)});
    await writeFile(landscapeFile,JSON.stringify(landscape));
    // This is an HTML/text/attribute/JSON/cover security fixture, not diagram-renderer evidence.
    const fixtureLog=execFileSync(process.execPath, ['tools/site/build-site.mjs', '--root', wt, '--worktree', '--client-diagrams', '--out', draft], { cwd: root, stdio: 'pipe' }).toString();
    assert.match(fixtureLog,/0 drawn, \d+ left to the reader's browser/,'the fixture explicitly leaves diagrams to the client');
    const html = await readFile(path.join(draft, 'catalog.html'), 'utf8');
    const got = JSON.parse(await readFile(path.join(draft, 'catalog.json'), 'utf8')).items.find(i => i.type === 'upstream' && i.name === entry.name);
    assert.ok(got, 'the entry is in catalog.json');
    assert.equal(got.what, entry.what, 'JSON keeps the text as written');
    for(const key of ['name','license','policy','last_push','stars'])assert.equal(got[key],entry[key],`JSON preserves ${key}`);
    assert.equal(got.notes,bad(7)+' '+bad(8),'JSON keeps notes and licence notes as literal text');
    const card = html.match(new RegExp(`<li data-item[^>]*id="${got.id}"[\\s\\S]*?</li>`))?.[0];
    assert.ok(card, 'the entry has a card');
    // An event handler inside a tag, outside a quoted value, means the text broke out of its attribute.
    const handlers = text => [...text.matchAll(/<[a-zA-Z][^>]*>/g)].map(m => m[0].replace(/"[^"]*"/g, '""')).filter(t => /\son[a-z]+\s*=/i.test(t));
    for (const [where, text] of [['the page', html], ['its card', card]]) {
      assert.doesNotMatch(text, /<img src=x|<script>alert/, `raw markup in ${where}`);
      assert.deepEqual(handlers(text), [], `event handlers in ${where}`);
    }
    assert.match(card, /&lt;img src=x onerror=alert\(2\)&gt;/, 'the what line shows as text');
    assert.match(card, /&lt;img src=x onerror=alert\(1\)&gt;/, 'the name shows as text');
    for(const n of [3,4,7,8])assert.ok(card.includes(`&lt;img src=x onerror=alert(${n})&gt;`),`licence/policy/notes ${n} remain escaped text`);
    for(const [attribute,n] of [['data-sort-recent',5],['data-sort-stars',6]])assert.ok(card.includes(`${attribute}="&quot;&gt;&lt;img src=x onerror=alert(${n})&gt;&lt;script&gt;alert(${n})&lt;/script&gt;"`),`${attribute} retains the escaped literal inside quotes`);
    const cover = await readFile(path.join(draft, new URL(got.cover).pathname), 'utf8');
    assert.doesNotMatch(cover, /<img|<script/i, 'raw markup in the cover');
    assert.deepEqual(handlers(cover), [], 'event handlers in the cover');
    console.log(fixtureLog.split('\n').find(line=>line.includes('Diagrams:')));
    const evidence=process.env.CAD_AGENT_SECURITY_RECEIPT;
    if(evidence){
      assert.ok(path.isAbsolute(evidence)&&evidence.startsWith(path.join(os.tmpdir(),'cad604-security-evidence-')),'diagnostic evidence uses a new private temporary directory');
      await mkdir(evidence,{recursive:false});
      const documents={'catalogue.html':html,'row.html':card,'entry.json':JSON.stringify(got,null,2),'cover.svg':cover,'build.log':fixtureLog};
      const hashes={};for(const [name,body]of Object.entries(documents)){await writeFile(path.join(evidence,name),body);hashes[name]=createHash('sha256').update(body).digest('hex');}
      retained={directory:evidence,receipt:{status:'pass',head:null,hashes,clientDiagrams:true,securityAssertions:'literal name/what/notes/licence/policy/date/stars; page/row attributes and cover inert; canonical JSON exact',worktreeRemoved:false}};
      // The receipt is private opt-in evidence, not a substitute for the assertions above.
      retained.receipt.head=execFileSync('git',['rev-parse','HEAD'],{cwd:root}).toString().trim();
      await writeFile(path.join(evidence,'receipt.json'),JSON.stringify(retained.receipt,null,2));
    }
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
    if(retained){
      assert.ok(!existsSync(wt),'owned fixture checkout removed');
      assert.ok(!execFileSync('git',['worktree','list','--porcelain'],{cwd:root}).toString().split('\n').includes('worktree '+wt),'owned fixture registration removed');
      retained.receipt.worktreeRemoved=true;
      await writeFile(path.join(retained.directory,'receipt.json'),JSON.stringify(retained.receipt,null,2));
    }
  }
});

test('an outside cover names what the entry is built on: its structured fields first, its description last', async () => {
  // #185: the first free-text match used to win, so OpenFOAM was "Mesh", specify-core a "Parts library" and two
  // build123d projects that slice their output "Slicer".
  // A domain word in a name is a subject, not a kernel: sargo-devel/Cables is a FreeCAD workbench, not a harness tool.
  const want = { 'project-openfoam-opencfd-v2512': 'CFD', 'project-kd5ryn-b123d-print': 'build123d',
    'project-ballerabdude-agent-cad-works': 'build123d', 'project-pzfreo-specify-core': null, 'library-sargo-devel-cables': 'FreeCAD',
    'library-wireviz-wireviz': 'Harness' };
  for (const [id, family] of Object.entries(want)) {
    const it = catalog.items.find(i => i.id === id);
    assert.ok(it, `${id} is in the catalogue`);
    const label = (await readFile(local(it.cover), 'utf8')).match(/aria-label="([^"]*)"/)[1];
    if (family) assert.match(label, new RegExp(`: ${it.kind} on ${family},`), `${id}: ${label}`);
    else assert.doesNotMatch(label, /Parts library/, `${id}: ${label}`);
  }
});

test('outside covers drop their licence and status tags when drawn phone-size (the card repeats them)', async () => {
  for (const it of catalog.items.filter(i => OUTSIDE.includes(i.kind))) {
    const svg = await readFile(local(it.cover), 'utf8');
    assert.match(svg, /@media \(max-width:240px\)\{\.tags\{display:none\}\}/, `${it.id}: no narrow rule`);
    assert.ok(svg.includes('<g class="tags">'), `${it.id}: tags not grouped`);
  }
});

// WCAG 2 relative luminance and contrast ratio, for #rrggbb colours.
const luminance = hex => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

test('every domain and bucket has a tone: the covers\' tints, and an ink that shows on white and on both tints', () => {
  const css = show('tools/site/assets/catalog.css');
  const tones = Object.fromEntries([...css.matchAll(/\[data-tone=([\w-]+)\]\{([^}]*)\}/g)].map(([, slug, body]) =>
    [slug, Object.fromEntries([...body.matchAll(/--([\w-]+):(#[0-9a-f]{6})/g)].map(([, k, v]) => [k === 'tone-ink' ? 'tone' : k, v]))]));
  for (const slug of [...domainSlugs, ...BUCKETS]) {
    const t = tones[slug];
    assert.ok(t?.tone && t['tint-a'] && t['tint-b'], `web/catalog.css: [data-tone=${slug}] needs --tint-a, --tint-b and --tone-ink (a new domain in docs/areas.yaml needs a tone)`);
    assert.deepEqual([t['tint-a'], t['tint-b']], TINT[slug], `${slug}: the rail's tints and the covers' (TINT in tools/site/compiler/catalog-art.mjs) differ`);
    // The ink is a UI graphic (the hover bar, the glyph, the arrow): 3:1 against everything it sits on. In the dark theme
    // the tone and tints are mixed from it (checked in the browser: tests/site/toolkit/website-catalog-browser.mjs).
    for (const bg of ['#ffffff', t['tint-a'], t['tint-b']]) assert.ok(contrast(t.tone, bg) >= 3, `${slug}: --tone ${t.tone} on ${bg} is ${contrast(t.tone, bg).toFixed(2)}:1 (3 needed)`);
  }
  for(const slug of domainSlugs)assert.ok(page.includes(`data-topic="${slug}" data-tone="${slug}"`),slug);
  assert.ok(page.includes('data-topic="cross-cutting"'));

});

test('Explore taxonomy keeps nested domain/area/topic icons and removes maturity presentation', () => {
  assert.match(page, /data-topic-tree/);
  for(const d of areas.domains){
    assert.ok(page.includes(`data-topic="${d.slug}" data-tone="${d.slug}"`));
    for(const a of d.areas){assert.ok(page.includes(`data-topic="${a.slug}"`));for(const t of a.topics||[])assert.ok(page.includes(`data-topic="${t.slug}"`));}
  }
  assert.doesNotMatch(page,/class="(?:mat-dots|area-maturity|key-scale|tree-key)/);
  assert.doesNotMatch(page,/<legend>[^<]*[Mm]aturity/);
  const controls=page.match(/<div hidden>([\s\S]*?)<\/div>/)?.[1]||'';
  for(const m of areas.maturity)assert.ok(controls.includes(`name="maturity" value="${m.level}"`),'saved legacy maturity filter remains supported');
  assert.ok(page.includes('value="maturity" data-dir="desc" hidden>Saved area order'));
});

test('no project is singled out: no Gyropup flag, badge, filter, boost or field (cad-agent is a general toolkit)', () => {
  assert.ok(catalog.items.every(i => !('gyropup' in i)), 'catalog.json entries have a gyropup field');
  // Only the note that it was removed names it (schema test above).
  assert.doesNotMatch(JSON.stringify({ ...catalog.fields, removed: undefined }), /gyropup/i);
  assert.doesNotMatch(`${index.how} ${JSON.stringify(index.fields)}`, /gyropup/i, 'index.json still describes a gyropup filter or priority');
  // Areas list the real projects that used them (Gyropup among them, like the others), and priority is only `demo`.
  for (const d of index.domains) for (const a of d.areas) {
    assert.ok(Array.isArray(a.projects), `index.json ${a.slug}: no projects list`);
    assert.deepEqual(a.priority.filter(p => p !== 'demo'), [], `index.json ${a.slug}: priority ${a.priority}`);
  }
  for (const hook of ['class="gyro"', 'pill-gyropup', 'name="gyropup"', 'data-gyropup', 'Needed for Gyropup', 'needed for Gyropup']) assert.ok(!page.includes(hook), `the page still has ${hook}`);
  assert.doesNotMatch(show('tools/site/assets/catalog.css'), /gyro/i);
  for (const d of areas.domains) for (const n of [d, ...d.areas, ...d.areas.flatMap(a => a.topics || [])]) assert.ok(!(n.priority || []).includes('gyropup'), `docs/areas.yaml ${n.slug}: priority gyropup`);
});


test('folder maps retain distinct catalogue IDs alongside the existing root README', () => {
  const root = catalog.items.find(i => i.kind === 'guide' && i.markdown === `${ORIGIN}/README.md`);
  const docs = catalog.items.find(i => i.kind === 'guide' && i.markdown === `${ORIGIN}/docs/README.md`);
  const research = catalog.items.find(i => i.kind === 'research' && i.markdown === `${ORIGIN}/research/README.md`);
  assert.equal(root.id, 'guide-index', 'published root links stay stable');
  assert.equal(docs.id, 'guide-docs-index');
  assert.equal(research.id, 'research-index');
  assert.equal(new Set([root.id, docs.id, research.id]).size, 3);
});
