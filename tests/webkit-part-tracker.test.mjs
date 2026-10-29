import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../src/cadagent/webkit/part-tracker.js', import.meta.url), 'utf8');
const { createPartTracker } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const memory = () => { const values = new Map(); return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }; };

test('statuses survive revisits, remain project-scoped, and import merges by stable identity', () => {
  const storage = memory(), tracker = createPartTracker({ project: 'fixture', storage });
  tracker.set('bracket', 'ordered', true); tracker.set('plate', 'inHand', true);
  const same = createPartTracker({ project: 'fixture', storage });
  assert.equal(same.get('bracket', 'ordered'), true);
  assert.equal(createPartTracker({ project: 'another', storage }).get('bracket', 'ordered'), false);
  const imported = createPartTracker({ project: 'fixture', storage: memory() });
  imported.set('rod', 'printed', true);
  assert.equal(imported.import(tracker.export()), 2);
  assert.equal(imported.get('rod', 'printed'), true);
  assert.equal(imported.get('plate', 'inHand'), true);
  tracker.set('bracket', 'ordered', false); imported.import(tracker.export());
  assert.equal(imported.get('bracket', 'ordered'), false);
});

test('invalid imports are atomic, project/version checked, and reject unsupported keys/types', () => {
  const tracker = createPartTracker({ project: 'fixture', storage: memory() }); tracker.set('known', 'ordered', true);
  const before = tracker.export();
  for (const bad of [
    '<html>not JSON</html>',
    JSON.stringify({ version: 2, project: 'fixture', parts: {} }),
    JSON.stringify({ version: 1, project: 'another', parts: {} }),
    JSON.stringify({ version: 1, project: 'fixture', parts: { known: { ordered: false }, later: { paid: true } } }),
    JSON.stringify({ version: 1, project: 'fixture', parts: { known: { ordered: 'yes' } } }),
    '{"version":1,"project":"fixture","parts":{"__proto__":{"ordered":true}}}',
  ]) { assert.throws(() => tracker.import(bad)); assert.equal(tracker.export(), before); }
  assert.throws(() => tracker.set('__proto__', 'ordered', true));
  assert.throws(() => tracker.set('known', 'paid', true));
  assert.throws(() => tracker.set('known', 'ordered', 1));
});

test('storage denial keeps useful in-tab state and an export without claiming persistence', () => {
  const denied = { getItem() { throw new Error('Denied'); }, setItem() { throw new Error('Quota exceeded'); } };
  const tracker = createPartTracker({ project: 'fixture', storage: denied }); let updates = 0;
  const unsubscribe = tracker.subscribe(() => updates++);
  tracker.set('bracket', 'ordered', true);
  assert.equal(tracker.persistent, false); assert.match(tracker.warning, /export/i);
  assert.equal(tracker.get('bracket', 'ordered'), true); assert.equal(updates, 1);
  const restored = createPartTracker({ project: 'fixture', storage: memory() }); restored.import(tracker.export());
  assert.equal(restored.get('bracket', 'ordered'), true); unsubscribe(); tracker.set('bracket', 'inHand', true); assert.equal(updates, 1);
});

test('a valid cross-tab update synchronizes; corrupt updates retain current progress', () => {
  const events = new EventTarget(), storage = memory(), tracker = createPartTracker({ project: 'fixture', storage, events });
  const update = newValue => { const event = new Event('storage'); Object.assign(event, { key: tracker.key, storageArea: storage, newValue }); events.dispatchEvent(event); };
  update(JSON.stringify({ version: 1, project: 'fixture', parts: { plate: { inHand: true } } }));
  assert.equal(tracker.get('plate', 'inHand'), true);
  update('bad'); assert.equal(tracker.get('plate', 'inHand'), true); assert.match(tracker.warning, /another tab/);
  update(null); assert.equal(tracker.get('plate', 'inHand'), false);
  tracker.dispose(); update(JSON.stringify({ version: 1, project: 'fixture', parts: { plate: { inHand: true } } }));
  assert.equal(tracker.get('plate', 'inHand'), false);
});

test('merging valid files cannot create progress too large to import again', () => {
  const tracker = createPartTracker({ project: 'fixture', storage: memory() }); tracker.set('existing', 'ordered', true);
  const incoming = JSON.stringify({ version: 1, project: 'fixture', parts: Object.fromEntries(Array.from({ length: 10000 }, (_, i) => [`part-${i}`, { ordered: false }])) });
  const before = tracker.export(); assert.throws(() => tracker.import(incoming), /too large/); assert.equal(tracker.export(), before);
});
