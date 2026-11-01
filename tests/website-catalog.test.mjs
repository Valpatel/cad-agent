// The catalogue (/catalog, /catalog.json, /catalog/index.json, /catalog/<area>.json), built from HEAD: every entry has
// a picture of our own and a place in the area map, the JSON files agree with each other and with the page, and the
// schema-1 fields and old links keep working. Behaviour in browsers: tests/website-catalog-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
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
