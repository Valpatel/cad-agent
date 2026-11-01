// <cad-gallery>'s pure parts: the URL state, search matching, facets and sorting (src/cadagent/webkit/gallery.js).
// The element itself is driven in real browsers by tests/website-catalog-browser.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { compareBy, matches, parseState, searchPatterns, stateToSearch } from '../src/cadagent/webkit/gallery.js';

const opts = { tabParam: 'kind', facets: ['area', 'status', 'licence'], single: ['area'], defaultSort: 'featured' };

test('the view round-trips through the query string, in a fixed order', () => {
  const s = parseState('?licence=permissive,copyleft&kind=tools&q=snap+fit&area=gears&sort=stars&other=1', opts);
  assert.deepEqual(s, { tab: 'tools', q: 'snap fit', sort: 'stars', facets: { area: ['gears'], licence: ['permissive', 'copyleft'] } });
  assert.equal(stateToSearch(s, opts), '?kind=tools&area=gears&q=snap+fit&licence=permissive,copyleft&sort=stars');
  assert.deepEqual(parseState(stateToSearch(s, opts), opts), s);
});

test('defaults stay out of the URL, and repeated or empty values are dropped', () => {
  assert.equal(stateToSearch({ tab: '', q: '  ', sort: 'featured', facets: {} }, opts), '');
  assert.deepEqual(parseState('?status=,adopted,adopted,&area=', opts).facets, { status: ['adopted'] });
});

test('each search word matches the start of a word, so "mit" finds MIT but not "commit"', () => {
  const p = searchPatterns('mit');
  assert.ok(p[0].test('licence mit'));
  assert.ok(!p[0].test('every commit'));
  assert.ok(searchPatterns('snap fit').every(r => r.test('a cantilever snap-fit arm')));
  assert.ok(searchPatterns('a.b (c').every(r => r instanceof RegExp), 'search text is escaped');
  assert.ok(searchPatterns('3d').every(r => r.test('[3d printing]')));
});

test('facets combine with AND, values within one facet with OR, and one can be left out for its own counts', () => {
  const item = { tab: 'projects', text: 'kicad mcp server', facets: { area: new Set(['circuit-boards', 'electrical']), status: new Set(['trial']), licence: new Set(['permissive']) } };
  const st = (facets, tab = '') => ({ tab, q: '', sort: '', facets });
  assert.ok(matches(item, st({ area: ['electrical'], status: ['trial', 'adopted'] }), []));
  assert.ok(!matches(item, st({ area: ['electrical'], status: ['adopted'] }), []));
  assert.ok(matches(item, st({ area: ['electrical'], status: ['adopted'] }), [], 'status'), 'counting status ignores the status filter');
  assert.ok(!matches(item, st({}, 'tools'), []));
  assert.ok(matches(item, st({}, 'tools'), [], 'tab'));
  assert.ok(!matches(item, st({}), searchPatterns('cad')), '"cad" is not the start of a word in "kicad"');
});

test('sorting: numbers and text, either direction, empty values last, ties in the page order', () => {
  const it = (index, v) => ({ index, sort: v === undefined ? {} : { stars: v } });
  const list = [it(0, '10'), it(1), it(2, '200'), it(3, '10'), it(4, '')];
  assert.deepEqual([...list].sort(compareBy('stars', 'desc')).map(x => x.index), [2, 0, 3, 1, 4]);
  assert.deepEqual([...list].sort(compareBy('stars', 'asc')).map(x => x.index), [0, 3, 2, 1, 4]);
  assert.deepEqual([...list].reverse().sort(compareBy('')).map(x => x.index), [0, 1, 2, 3, 4]);
  const names = ['beta', 'Alpha', 'gamma'].map((v, index) => ({ index, sort: { name: v } }));
  assert.deepEqual(names.sort(compareBy('name')).map(x => x.sort.name), ['Alpha', 'beta', 'gamma']);
});
