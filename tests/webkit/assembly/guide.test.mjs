import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { validateGuide, validateView, validateState, stepState, createGuideController, assetURL, viewAssetURL, readAsset, loadGuide, sha256 } from '../../../software/cadagent/webkit/assembly/guide.js';
const H = '1'.repeat(64);
const fixture = () => ({
  manifest: { units: 'mm', up: 'z', parts: ['base', 'screw#1', 'screw#2'].map((name, i) => ({ name, file: `part-${i}.stl`, color: '#123456', sha256: H, bounds_mm: [0, 0, 0, 10, 20, 30] })) },
  guide: { schema: 'cad-agent.assembly-guide/1', snapshot: { id: 'v1', revision: '1.0', status: 'released', source_commit: 'a'.repeat(40) },
    model: { file: '../view.json', sha256: H }, subassemblies: [{ id: 'frame', title: 'Frame', parts: ['base', 'screw#1', 'screw#2'] }],
    steps: [{ id: 'base', title: 'Base', text: 'Seat the base.', subassembly: 'frame', parts: ['base'], highlight: ['base'], offsets_mm: {} },
      { id: 'screws', title: 'Screws', text: 'Fit both screws.', subassembly: 'frame', parts: ['base', 'screw#1', 'screw#2'], highlight: ['screw#1', 'screw#2'], offsets_mm: { 'screw#1': [0, 0, 25], 'screw#2': [0, 0, 25] }, camera: { direction: [1, -1, 1] }, requires: ['base'] }] }
});
test('ordinary manifests keep optional mesh hashes; guide frame and every instance hash are mandatory', () => {
  const { guide, manifest } = fixture(); assert.equal(validateGuide(guide, manifest), guide);
  const legacy = structuredClone(manifest); delete legacy.units; delete legacy.up; delete legacy.parts[0].sha256;
  assert.equal(validateView(legacy), legacy); assert.throws(() => validateGuide(guide, legacy));
});
const bad = [
  g => g.extra = true, g => g.snapshot.status = 'approved', g => g.snapshot.source_commit = 'main',
  g => g.subassemblies.push(g.subassemblies[0]), g => g.steps.push(g.steps[0]),
  g => g.steps[1].parts.push('missing'), g => g.steps[1].parts.push('screw#1'),
  g => g.steps[0].highlight.push('screw#2'), g => g.steps[0].requires = ['screws'],
  g => g.steps[1].requires = ['screws'], g => g.steps[0].offsets_mm.base = [0, NaN, 0],
  g => g.steps[0].offsets_mm.future = [0, 0, 1], g => g.steps[0].camera = { direction: [0, 0, 0] },
  g => g.model.file = 'https://other.invalid/view.json', g => g.model.file = '/current/view.json',
  g => g.model.file = 'view.json#old', g => g.model.sha256 = 'bad', g => g.steps[0].poster = { file: 'poster.png', sha256: 'bad' },
  g => g.steps[0].opacity = 0.2,
];
for (const [i, mutate] of bad.entries()) test(`invalid guide ${i} fails closed`, () => {
  const { guide, manifest } = fixture(); mutate(guide); assert.throws(() => validateGuide(guide, manifest));
});
test('duplicate mesh names, bad frame/bounds/hash and unknown state names reject', () => {
  for (const mutate of [m => m.parts.push(m.parts[0]), m => m.units = 'm', m => m.up = 'y', m => m.parts[0].bounds_mm[3] = -1, m => m.parts[0].sha256 = 'bad']) {
    const { guide, manifest } = fixture(); mutate(manifest); assert.throws(() => validateGuide(guide, manifest));
  }
  const { guide } = fixture(), state = stepState(guide, 'base');
  for (const patch of [{ selected: 'screw#1' }, { mode: 'xray' }, { isolate: true }, { isolate: ['unknown'] }, { offsets_mm: { bad: [0, 0, 0] } }])
    assert.throws(() => validateState({ ...state, ...patch }, ['base', 'screw#1', 'screw#2']));
});
test('absolute states jump/back without accumulating authored millimetres or losing repeated instances', () => {
  const { guide, manifest } = fixture(), states = [];
  const viewer = { parts: manifest.parts, applyState: state => states.push(structuredClone(state)), frameParts() {}, reset() {}, dispose() {} };
  const c = createGuideController(viewer, guide); c.applyStep('screws'); c.applyStep('base'); c.applyStep('screws');
  assert.deepEqual(states[0], states[2]); assert.deepEqual(states[1].visible, ['base']);
  assert.deepEqual(states[2].offsets_mm['screw#2'], [0, 0, 25]);
  assert.deepEqual(stepState(guide, 'screws', { explode: 0 }).offsets_mm['screw#1'], [0, 0, 0]);
  assert.throws(() => c.applyStep('unknown')); assert.throws(() => stepState(guide, 'base', { explode: 1000 }));
});
test('relative assets remain local and can be bounded to a release root', () => {
  assert.equal(assetURL('../view.json', 'https://host/bundle/docs/guide.json', 'https://host/bundle/').pathname, '/bundle/view.json');
  for (const path of ['../../secret', '//other/view', 'file:///tmp/x', 'data:abc', '%2e%2e/x', 'x?token=abc', 'a\\b'])
    assert.throws(() => assetURL(path, 'https://host/bundle/docs/guide.json', 'https://host/bundle/'));
});
test('download rejects non-200, byte limits, corrupt hashes, body stall, and pre-aborted loads', async () => {
  const bytes = new TextEncoder().encode('ok'), hash = await sha256(bytes);
  assert.equal(new TextDecoder().decode(await readAsset('https://host/a', { expectedHash: hash, fetcher: async () => new Response(bytes) })), 'ok');
  for (const options of [
    { fetcher: async () => new Response('missing', { status: 404 }) },
    { maxBytes: 1, fetcher: async () => new Response(bytes) },
    { expectedHash: H, fetcher: async () => new Response(bytes) },
    { timeoutMs: 20, fetcher: async () => new Response(new ReadableStream({ start(c) { c.enqueue(bytes); } })) },
    { signal: AbortSignal.abort(), fetcher: async () => { throw new Error('must not fetch'); } },
  ]) await assert.rejects(readAsset('https://host/a', options));
});
test('loadGuide binds exact manifest; no failed/missing version is filled from another snapshot', async () => {
  const { guide, manifest } = fixture(), raw = JSON.stringify(manifest);
  guide.model.sha256 = await sha256(new TextEncoder().encode(raw));
  const fetcher = async url => new Response(String(url).endsWith('guide.json') ? JSON.stringify(guide) : raw);
  const loaded = await loadGuide('https://host/bundle/docs/guide.json', { fetcher, assetRoot: 'https://host/bundle/' });
  assert.equal(loaded.manifestUrl, 'https://host/bundle/view.json');
  const guideHash = await sha256(new TextEncoder().encode(JSON.stringify(guide)));
  await loadGuide('https://host/bundle/docs/guide.json', { fetcher, expectedHash: guideHash });
  const changedGuide = structuredClone(guide); changedGuide.steps[0].text = 'Changed instructions, same meshes';
  await assert.rejects(loadGuide('https://host/bundle/docs/guide.json', { expectedHash: guideHash, fetcher: async url => new Response(String(url).endsWith('guide.json') ? JSON.stringify(changedGuide) : raw) }), /SHA-256/);
  await assert.rejects(loadGuide('https://host/bundle/docs/guide.json', { fetcher: async url => String(url).endsWith('guide.json') ? new Response(JSON.stringify(guide)) : new Response('{}'), assetRoot: 'https://host/bundle/' }), /SHA-256/);
});

test('real Gyropup twelve-step guide retains earlier chapters as visible context', async () => {
  const guide = JSON.parse(await readFile(new URL('../../fixtures/assembly-guide/guide.json', import.meta.url)));
  const manifestBytes = await readFile(new URL('../../fixtures/assembly-guide/view.json', import.meta.url));
  const manifest = JSON.parse(manifestBytes);
  assert.equal(await sha256(manifestBytes), guide.model.sha256);
  validateGuide(guide, manifest);
  assert.equal(guide.steps.length, 12); assert.equal(manifest.parts.length, 55);
  const crossChapter = guide.steps.filter(s => s.parts.some(name => !guide.subassemblies.find(g => g.id === s.subassembly).parts.includes(name)));
  assert.ok(crossChapter.length > 0, 'actual prior-subassembly context is retained');
  const bad = structuredClone(guide), step = bad.steps.find(s => s.parts.some(name => !bad.subassemblies.find(g => g.id === s.subassembly).parts.includes(name)));
  const members = bad.subassemblies.find(g => g.id === step.subassembly).parts;
  step.highlight = [step.parts.find(name => !members.includes(name))];
  assert.throws(() => validateGuide(bad, manifest), /Highlighted subassembly/);
});

test('legacy filenames with spaces and CSS colour names retain their original URL/material contract', () => {
  const { guide, manifest } = fixture();
  manifest.parts[0].file = 'small part.stl'; manifest.parts[0].color = 'steelblue';
  assert.equal(validateView(manifest), manifest);
  assert.throws(() => validateGuide(guide, manifest), /relative local path|color/);
});

test('ordinary viewer URL resolution preserves relative/root/absolute HTTP and external CORS paths', () => {
  const base = 'https://product.invalid/previews/view.json';
  for (const [file, expected] of [['small part.stl', 'https://product.invalid/previews/small%20part.stl'], ['/exports/part.stl', 'https://product.invalid/exports/part.stl'], ['https://product.invalid/exports/part.stl', 'https://product.invalid/exports/part.stl'], ['https://cdn.invalid/part.stl?v=1', 'https://cdn.invalid/part.stl?v=1']]) {
    const { manifest, guide } = fixture(); manifest.parts[0].file = file;
    assert.equal(validateView(manifest), manifest);
    assert.equal(viewAssetURL(file, base).href, expected);
    assert.throws(() => validateGuide(guide, manifest), /relative local path/);
  }
  assert.throws(() => viewAssetURL('https://cdn.invalid/part.stl', base, { assetRoot: 'https://product.invalid/' }), /escapes/);
  assert.throws(() => viewAssetURL('/private/part.stl', base, { assetRoot: 'https://product.invalid/previews/' }), /escapes/);
});
test('only ordinary fetches opt into redirects; guide loading stays fail-closed', async () => {
  let policy;
  await readAsset('https://product.invalid/a', { redirect: 'follow', fetcher: async (_, options) => { policy = options; return new Response('ok'); } });
  assert.equal(policy.redirect, 'follow'); assert.equal(policy.credentials, undefined);
  const { guide, manifest } = fixture(), raw = JSON.stringify(manifest);
  guide.model.sha256 = await sha256(new TextEncoder().encode(raw));
  const seen = [];
  await loadGuide('https://product.invalid/guide.json', { redirect: 'follow', fetcher: async (url, options) => { seen.push(options.redirect); return new Response(String(url).endsWith('guide.json') ? JSON.stringify(guide) : raw); } });
  assert.deepEqual(seen, ['error', 'error']);
});
