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

// A case may carry its own tolerance (where the Python says why: a double root), and `angles` for results that are
// angles in rad: compared round the circle (pi and -pi are one position; a last-ulp difference picks either) and to
// the relative tolerance in rad, since an angle near 0 is no less certain in rad than one near pi.
const close = (got, want, where, tol = { rel, abs }, angles = false) => {
  if (typeof want === 'number') {
    assert.equal(typeof got, 'number', `${where}: not a number`);
    const diff = Math.abs(got - want), apart = angles ? Math.min(diff, Math.abs(diff - 2 * Math.PI)) : diff;
    const scale = angles ? Math.max(1, Math.abs(want)) : Math.abs(want);
    assert.ok(apart <= Math.max(tol.abs, tol.rel * scale), `${where}: ${got} != ${want}`);
  } else if (want && typeof want === 'object') {
    assert.ok(got && typeof got === 'object', `${where}: ${got} where the Python has ${JSON.stringify(want)}`);
    assert.deepEqual(Object.keys(got).sort(), Object.keys(want).sort(), `${where}: keys`);
    for (const k of Object.keys(want)) close(got[k], want[k], `${where}.${k}`, tol, angles);
  } else assert.equal(got, want, where);
};

test('every ported function reproduces the Python on every golden vector', () => {
  assert.ok(vectors.cases.filter(c => !c.raises).length > 50, 'too few vectors');
  for (const [i, c] of vectors.cases.entries()) {
    assert.equal(typeof fx[c.js], 'function', `case ${i}: ${c.js} is not in formulas.js`);
    if (c.raises) continue;
    close(fx[c.js](...c.args), c.expected, `case ${i} ${c.js}(${c.args.join(', ')})`, c.tolerance, c.angles);
  }
});

test('the four-bar vectors cover both branches, change points and the input limits, and loosen only there', () => {
  const four = vectors.cases.filter(c => c.js === 'fourbarAngles');
  assert.ok(four.some(c => c.args[5] === false) && four.some(c => c.args[5] === true), 'both branches');
  assert.ok(four.some(c => c.expected === null) && four.some(c => c.expected !== null), 'closing and not closing');
  const limits = vectors.cases.filter(c => c.js === 'fourbarInputLimits').map(c => c.expected);
  assert.ok(limits.some(l => l.fullTurn) && limits.some(l => l.folded !== null && l.stretched !== null) &&
    limits.some(l => l.folded === null && l.stretched !== null) && limits.some(l => !l.closes), 'every kind of input range');
  for (const kind of ['crank-rocker', 'double-crank', 'rocker-crank', 'double-rocker', 'triple-rocker', 'change-point'])
    assert.ok(vectors.cases.some(c => c.js === 'grashof' && c.expected.inversion === kind), kind);
  // every exact limit angle is a vector, on both branches
  for (const c of vectors.cases.filter(c => c.js === 'fourbarInputLimits'))
    for (const edge of [c.expected.folded, c.expected.stretched].filter(e => e !== null))
      assert.equal(four.filter(f => f.args.slice(0, 4).join() === c.args.join() && f.args[4] === edge).length, 2, `${c.args} at ${edge}`);
  const loose = vectors.cases.filter(c => c.tolerance);
  assert.ok(loose.length && loose.every(c => /double root/.test(c.tolerance.why) && c.tolerance.rel <= 1e-7 && c.tolerance.abs <= 1e-7));
  // 1e-7 only exactly where the branches meet; beside it, 1e-10
  const meets = loose.filter(c => c.tolerance.abs > 1e-10);
  assert.ok(meets.length && meets.length < loose.length && meets.every(c => /^where/.test(c.tolerance.why)), 'the widest tolerance is only at the meeting points');
  const positions = vectors.cases.filter(c => c.js === 'fourbarAngles' || c.js === 'transmissionAngle');
  assert.ok(positions.every(c => c.angles), 'four-bar results are compared as angles');
  assert.ok(loose.length < positions.length / 4, 'the double-root tolerance is for the few vectors where the branches meet');
});

test('the port has exactly the functions the vectors cover, no untested extras', () => {
  const exported = Object.entries(fx).filter(([, v]) => typeof v === 'function').map(([k]) => k).sort();
  assert.deepEqual(exported, [...vectors.ported].sort());
  for (const name of vectors.ported) assert.ok(vectors.cases.some(c => c.js === name), `no vectors for ${name}`);
});

test('the port refuses what the Python refuses', () => {
  // The Python's ValueError is the port's RangeError; tools/formula_vectors.py writes a case for each refusal.
  const refused = vectors.cases.filter(c => c.raises);
  assert.ok(refused.length >= 20, 'too few refusal vectors');
  for (const c of refused) {
    assert.equal(c.raises, 'ValueError');
    assert.throws(() => fx[c.js](...c.args), RangeError, `${c.js}(${c.args.map(a => JSON.stringify(a)).join(', ')}) did not throw`);
  }
  const rest = vectors.cases.filter(c => c.js === 'snapArm' && !c.raises && c.args[3] === 0);
  assert.equal(rest.length, 3, 'an arm at rest for each design');
  for (const c of rest) assert.ok(c.expected.stiffness > 0 && c.expected.force === 0, 'at rest: no force, the same stiffness');
});

test('the demo materials carry a source and a strain in range for both print directions', () => {
  assert.ok(MATERIALS.length >= 10);
  for (const m of MATERIALS) {
    // each data sheet read: its edition, the PDF's date, the page and the link (#156)
    assert.match(m.source, /Technical Data Sheet V\d+\.\d+ \(PDF of \d{4}-\d\d-\d\d\), p\. \d+[^;]*: https:\/\//, m.key);
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
