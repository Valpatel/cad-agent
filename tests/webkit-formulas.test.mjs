// The browser port of cadagent.formulas (src/cadagent/webkit/formulas.js) against the golden vectors the Python writes
// (tools/formula_vectors.py, checked for staleness by tests/test_formulas.py), so the site's demos compute exactly what
// agents get. Also: the demo's material table is the Python's, and the cantilever still is what the component draws.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import * as fx from '../src/cadagent/webkit/formulas.js';
import { MATERIALS } from '../src/cadagent/webkit/formulas-data.js';

const root = path.resolve(import.meta.dirname, '..');
const vectors = JSON.parse(await readFile(path.join(root, 'tests/fixtures/formula-vectors.json'), 'utf8'));
const { rel, abs } = vectors.tolerance;

const close = (got, want, where) => {
  if (typeof want === 'number') {
    assert.equal(typeof got, 'number', `${where}: not a number`);
    assert.ok(Math.abs(got - want) <= Math.max(abs, rel * Math.abs(want)), `${where}: ${got} != ${want}`);
  } else if (want && typeof want === 'object') {
    assert.deepEqual(Object.keys(got).sort(), Object.keys(want).sort(), `${where}: keys`);
    for (const k of Object.keys(want)) close(got[k], want[k], `${where}.${k}`);
  } else assert.equal(got, want, where);
};

test('every ported function reproduces the Python on every golden vector', () => {
  assert.ok(vectors.cases.length > 50, 'too few vectors');
  for (const [i, c] of vectors.cases.entries()) {
    assert.equal(typeof fx[c.js], 'function', `case ${i}: ${c.js} is not in formulas.js`);
    close(fx[c.js](...c.args), c.expected, `case ${i} ${c.js}(${c.args.join(', ')})`);
  }
});

test('the port has exactly the functions the vectors cover, no untested extras', () => {
  const exported = Object.entries(fx).filter(([, v]) => typeof v === 'function').map(([k]) => k).sort();
  assert.deepEqual(exported, [...vectors.ported].sort());
  for (const name of vectors.ported) assert.ok(vectors.cases.some(c => c.js === name), `no vectors for ${name}`);
});

test('the port refuses what the Python refuses', () => {
  assert.throws(() => fx.cantileverShape(1.2, 1), RangeError);
  assert.throws(() => fx.cantileverStrainProfile(-0.1, 2), RangeError);
  assert.throws(() => fx.snapRootStrain(0.02, 0.0016, 0.001, 4), RangeError);
});

test('the demo materials carry a source and a strain in range for both print directions', () => {
  assert.ok(MATERIALS.length >= 10);
  for (const m of MATERIALS) {
    assert.match(m.source, /TDS/, m.key);
    for (const d of ['along', 'across']) {
      assert.ok(m.modulus[d] > 1e8 && m.modulus[d] < 2e10, `${m.key} ${d} modulus`);
      assert.ok(m.allowable[d].single > 0.001 && m.allowable[d].single < 0.1, `${m.key} ${d} strain`);
      assert.ok(Math.abs(m.allowable[d].repeated - 0.6 * m.allowable[d].single) < 1e-15, `${m.key} ${d} repeated`);
    }
    assert.ok(m.allowable.across.single <= m.allowable.along.single + 1e-15, `${m.key}: across above along`);
  }
});


test('the cantilever still on docs/compliant is what the component draws for the page\'s attributes', () => {
  const out = execFileSync(process.execPath, ['tools/cantilever-still.mjs', '--check'], { cwd: root }).toString();
  assert.match(out, /current/);
});
