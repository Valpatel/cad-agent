// The catalogue (/catalog, /catalog.json, /catalog/index.json, /catalog/<area>.json), built from HEAD: every entry has
// a picture of our own and a place in the area map, the JSON files agree with each other and with the page, and the
// schema-1 fields and old links keep working. Behaviour in browsers: tests/website-catalog-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import YAML from 'yaml';

const root = path.resolve(import.meta.dirname, '..');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-catalog-'));
const out = path.join(tmp, 'site');
execFileSync(process.execPath, ['tools/build-site.mjs', '--out', out], { cwd: root });
test.after(() => rm(tmp, { recursive: true, force: true }));

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
  const upstreams = YAML.parse(execFileSync('git', ['show', 'HEAD:upstreams/registry.yaml'], { cwd: root }).toString());
  for (const u of upstreams) assert.ok(catalog.items.some(i => i.type === 'upstream' && i.name === u.name), u.name);
  const commands = catalog.items.filter(i => i.type === 'tool').length;
  assert.equal(commands, catalog.items.filter(i => i.kind === 'tool').length);
});

test('schema-1 fields keep their schema-1 values: summary, licence (null stays null), tool urls', () => {
  // Schema 1's builder, as it was (tools/build-site.mjs before catalogue v2), run over today's data.
  const landscape = JSON.parse(show('research/landscape.json'));
  const upstreams = YAML.parse(show('upstreams/registry.yaml'));
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
  assert.ok(want.some(w => w.license === null), 'the data still has a null licence to keep');
  // Our own entries: schema 1 wrote these fields and no others; the additions are the ones fields.schema_1 lists.
  const OWN = { tool: ['summary', 'how'], doc: ['summary', 'markdown', 'source'] };
  const OWN_ADDED = { tool: ['license', 'markdown'], doc: ['license'] };
  for (const i of catalog.items.filter(i => !['upstream', 'library', 'benchmark', 'demo'].includes(i.type))) {
    const kind = i.type === 'tool' ? 'tool' : 'doc';
    for (const k of S1.slice(4)) {
      if (OWN[kind].includes(k)) assert.ok(k in i, `${i.id}: ${k} (schema 1 had it)`);
      else if (OWN_ADDED[kind].includes(k)) assert.ok(!(k in i) || (k === 'license' ? i.license === 'MIT' : true), `${i.id}: ${k}`);
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

test('compare and optimise draw what the tools printed: the front over every objective, lower bounds kept', async () => {
  const data = JSON.parse(show('docs/img/explore/two-wheel-charts.json'));     // tools/explore_charts.py --check (pytest)
  for (const cmd of ['compare', 'optimise']) {
    const it = catalog.items.find(i => i.id === `tool-${cmd}`);
    const svg = await readFile(local(it.cover), 'utf8');
    const d = data[cmd];
    assert.ok(svg.includes(`FRONT (${d.front_over.join(', ').toUpperCase()})`), `${cmd}: the legend says the front is over ${d.front_over}`);
    assert.ok(!/<path d="M[^"]*L[^"]*" fill="none" stroke="#[0-9a-f]+" stroke-width="4"/.test(svg), `${cmd}: front points are not joined (it is not a front on these two axes)`);
    const front = d.points.filter(p => p.front);
    assert.equal((svg.match(/<circle [^>]*r="(?:10|8)" fill="#[0-9a-f]+" stroke="#fff"/g) || []).length >= front.length, true, `${cmd}: a filled mark per front point`);
    for (const p of front) assert.ok(svg.includes(`>${p.label}${p.lower_bound.length ? ' ≥ ' : '<'}`), `${cmd}: ${p.label} is labelled`);
  }
  const compare = await readFile(local(catalog.items.find(i => i.id === 'tool-compare').cover), 'utf8');
  for (const p of data.compare.points) {
    assert.ok(compare.includes(`>${p.label}${p.lower_bound.length ? ' ≥ ' : '<'}`), `compare labels ${p.label}${p.lower_bound.length ? ' with ≥' : ''}`);
  }
  assert.ok(compare.includes('>Long range ≥ $1,682<'), 'the lower bound keeps its ≥ on the chart');
  assert.ok(data.compare.points.some(p => p.lower_bound.includes('cost_usd')), 'the data still has a lower bound to keep');
  assert.match(compare, /aria-label="[^"]*Long range: at least \$1,682/, 'the label reads the lower bound as "at least"');
  // A chart of a tool's result is a picture: it ranks like one in the overview (#185).
  // catalog.json lists each kind in featured order; a chart outranks a drawn call of the same maturity.
  const tools = catalog.items.filter(i => i.kind === 'tool');
  const charts = ['tool-compare', 'tool-optimise'];
  for (const id of charts) {
    const c = tools.find(i => i.id === id);
    for (const t of tools.filter(t => /\/catalog\/covers\/tool-/.test(t.cover) && !charts.includes(t.id) && t.maturity === c.maturity && !t.demo && !c.demo))
      assert.ok(tools.indexOf(c) < tools.indexOf(t), `${id} (a chart) is featured before ${t.id} (a drawn call)`);
  }
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
  const cards = [...page.matchAll(/<li class="card cat-card[\s\S]*?<\/li>/g)].map(m => m[0]);
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
      for (const k of ['name', 'url', 'kind', 'cover', 'what', 'status']) assert.deepEqual(e[k], i[k], `${n.slug}/${e.id}: ${k}`);
    }
  }
  for (const k of index.kinds) assert.equal(k.count, catalog.items.filter(i => k.kinds.includes(i.kind)).length, k.tab);
  assert.equal(index.kinds.reduce((n, k) => n + k.count, 0), catalog.items.length, 'every entry is under one kind tab');
  const llms = await readFile(path.join(out, 'llms.txt'), 'utf8');
  assert.match(llms, /catalog\/index\.json/);
  // Each file says what its fields mean.
  for (const k of ['count', 'kinds', 'maturity', 'domains', 'buckets']) assert.equal(typeof index.fields?.[k], 'string', `index.json fields.${k}`);
  for (const k of ['id', 'kind', 'areas', 'what', 'cover', 'doc', 'schema_1']) assert.equal(typeof catalog.fields?.[k], 'string', `catalog.json fields.${k}`);
  const area = await json('catalog/compliant-mechanisms.json');
  for (const k of ['level', 'items', 'kinds', 'count']) assert.equal(typeof area.fields?.[k], 'string', `area file fields.${k}`);
});

test('the page lists every entry once, grouped by kind, readable without script', () => {
  const cards = [...page.matchAll(/<li class="card cat-card"[^>]*\bid="([^"]+)"[^>]*>/g)];
  assert.deepEqual(cards.map(m => m[1]).sort(), catalog.items.map(i => i.id).sort());
  for (const m of cards) assert.doesNotMatch(m[0], /\shidden\b/, `${m[1]} is hidden in the HTML`);
  assert.match(page, /<cad-gallery\b/);
  assert.match(page, /<script type="module" src="\/kit\/gallery\.js"><\/script>/);
  assert.doesNotMatch(page, /<script>/, 'no inline script (CSP)');
  // Search, status and the existing browser test's hooks.
  assert.match(page, /<input [^>]*id="q"/);
  assert.match(page, /id="filter-status"/);
  assert.match(page, /<label class="sr" for="q">/);
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
  try {
    const bad = n => `"><img src=x onerror=alert(${n})><script>alert(${n})</script>`;
    const entry = { name: `evil/${bad(1)}`, what: bad(2), areas: ['3d-printing'], url: 'https://github.com/evil/evil', license: bad(3),
      status: 'candidate', policy: bad(4), last_push: bad(5), stars: bad(6) };
    const registry = path.join(wt, 'upstreams/registry.yaml');
    await writeFile(registry, `${await readFile(registry, 'utf8')}\n${YAML.stringify([entry])}`);
    execFileSync(process.execPath, ['tools/build-site.mjs', '--root', wt, '--worktree', '--out', draft], { cwd: root, stdio: 'pipe' });
    const html = await readFile(path.join(draft, 'catalog.html'), 'utf8');
    const got = JSON.parse(await readFile(path.join(draft, 'catalog.json'), 'utf8')).items.find(i => i.type === 'upstream' && i.name === entry.name);
    assert.ok(got, 'the entry is in catalog.json');
    assert.equal(got.what, entry.what, 'JSON keeps the text as written');
    const card = html.match(new RegExp(`<li class="card cat-card"[^>]*id="${got.id}"[\\s\\S]*?</li>`))?.[0];
    assert.ok(card, 'the entry has a card');
    // An event handler inside a tag, outside a quoted value, means the text broke out of its attribute.
    const handlers = text => [...text.matchAll(/<[a-zA-Z][^>]*>/g)].map(m => m[0].replace(/"[^"]*"/g, '""')).filter(t => /\son[a-z]+\s*=/i.test(t));
    for (const [where, text] of [['the page', html], ['its card', card]]) {
      assert.doesNotMatch(text, /<img src=x|<script>alert/, `raw markup in ${where}`);
      assert.deepEqual(handlers(text), [], `event handlers in ${where}`);
    }
    assert.match(card, /&lt;img src=x onerror=alert\(2\)&gt;/, 'the what line shows as text');
    assert.match(card, /&lt;img src=x onerror=alert\(1\)&gt;/, 'the name shows as text');
    const cover = await readFile(path.join(draft, new URL(got.cover).pathname), 'utf8');
    assert.doesNotMatch(cover, /<img|<script/i, 'raw markup in the cover');
    assert.deepEqual(handlers(cover), [], 'event handlers in the cover');
  } finally {
    execFileSync('git', ['worktree', 'remove', '--force', wt], { cwd: root });
  }
});

test('an outside cover names what the entry is built on: its structured fields first, its description last', async () => {
  // #185: the first free-text match used to win, so OpenFOAM was "Mesh", specify-core a "Parts library" and two
  // build123d projects that slice their output "Slicer".
  const want = { 'project-openfoam-opencfd-v2512': 'CFD', 'project-kd5ryn-b123d-print': 'build123d',
    'project-ballerabdude-agent-cad-works': 'build123d', 'project-pzfreo-specify-core': null };
  for (const [id, family] of Object.entries(want)) {
    const it = catalog.items.find(i => i.id === id);
    assert.ok(it, `${id} is in the catalogue`);
    const label = (await readFile(local(it.cover), 'utf8')).match(/aria-label="([^"]*)"/)[1];
    if (family) assert.match(label, new RegExp(`: project on ${family},`), `${id}: ${label}`);
    else assert.doesNotMatch(label, /Parts library/, `${id}: ${label}`);
  }
});
