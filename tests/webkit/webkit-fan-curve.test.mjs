// <cad-fan-curve> (src/cadagent/webkit/fan-curve.js) without a browser: every setting of its controls gives a point on
// both curves, the stall warning agrees with the per-fan flow, the chart stays inside its figure, and the still on the
// pages is what the component draws for their attributes (tools/fan-curve-still.mjs --check).
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { readState, compute, verdict, summary, drawFanCurve, scales, readAt, CONTROLS, VOLTAGES, ARRANGEMENTS, VIEW,
  DEFAULTS, REFERENCE_FLOW, m3h } from '../../src/cadagent/webkit/fan-curve.js';
import { fanOperatingPoint, fanStallFlow } from '../../src/cadagent/webkit/formulas.js';

const root = path.resolve(import.meta.dirname, '../..');
const states = function* () {
  for (const fan of VOLTAGES) for (let system = CONTROLS.system.min; system <= CONTROLS.system.max; system++)
    for (let count = 1; count <= CONTROLS.count.max; count++) for (const arrangement of Object.keys(ARRANGEMENTS))
      yield { fan, system, count, arrangement };
};

test('every setting gives one operating point on both curves, inside the chart', () => {
  let n = 0, stalled = 0;
  for (const s of states()) {
    const r = compute(s), { flow: q, pressure: p } = r.op;
    n++;
    assert.ok(Math.abs(p - r.k * q * q) <= 1e-9 * p + 1e-12, `${JSON.stringify(s)}: off the system curve`);
    const at = readAt(r, q);
    assert.ok(at.fan !== null && Math.abs(at.fan - p) <= 1e-9 * p + 1e-9, `${JSON.stringify(s)}: off the fan curve`);
    assert.ok(Math.abs(r.k * REFERENCE_FLOW ** 2 - s.system) < 1e-9, 'k is the slider\'s pressure at 100 m³/h');
    // the warning is about one fan: in parallel each carries 1/n of the flow, in series all of it
    const each = s.arrangement === 'parallel' ? q / s.count : q;
    assert.equal(r.op.stall, each < r.stallEach, `${JSON.stringify(s)}: the stall flag is not one fan's`);
    if (r.op.stall) stalled++;
    const v = verdict(s, r);
    assert.equal(v.poor, r.op.stall || !r.op.stable);
    for (const compact of [false, true]) {
      const sc = scales(r, compact), x = sc.x(q), y = sc.y(p);
      assert.ok(x >= sc.x0 && x <= sc.x1 && y >= sc.y0 && y <= sc.y1, `${JSON.stringify(s)}: the point is off the plot`);
      const svg = drawFanCurve(s, r, { compact });
      for (const [, a, b] of svg.matchAll(/<(?:circle|text)[^>]* (?:cx|x)="(-?[\d.]+)"[^>]* (?:cy|y)="(-?[\d.]+)"/g))
        assert.ok(+a >= 0 && +a <= VIEW.width && +b >= 0 && +b <= VIEW.height, `${JSON.stringify(s)}: a mark at ${a}, ${b} is outside the figure`);
    }
  }
  assert.equal(n, VOLTAGES.length * 59 * 4 * 2);
  assert.ok(stalled > n / 10 && stalled < n * 0.9, `both verdicts are reachable (${stalled} of ${n} stalled)`);
});

test('the lessons the page states hold: a tight system stalls one fan, series beats parallel there, parallel wins when open', () => {
  const at = (system, count = 1, arrangement = 'parallel') => compute({ ...DEFAULTS, system, count, arrangement });
  assert.ok(!at(12).op.stall && at(25).op.stall);
  assert.ok(at(25, 2, 'parallel').op.stall && !at(25, 2, 'series').op.stall && at(25, 2, 'series').op.flow > at(25, 2, 'parallel').op.flow);
  assert.ok(at(4, 2, 'parallel').op.flow > at(4, 2, 'series').op.flow);
  assert.match(summary(DEFAULTS, at(12)), /delivers 150 m³\/h at 26\.9 Pa, clear of the stall region, which is below 132 m³\/h\.$/);
  assert.match(summary({ ...DEFAULTS, system: 25, count: 2 }, at(25, 2)), /each fan carries 70 m³\/h, in the stall region \(below 132 m³\/h for one fan\)/);
  assert.equal(m3h(186.46773978319908 / 3600), '186 m³/h');
});

test('a curve the system crosses three times reads "Unstable" (no datasheet fan here has so deep a dip)', () => {
  // the DIP curve of tools/formula_vectors.py, against the quadratic system its vectors cross three times
  const dip = [[0, 20], [0.004, 8], [0.005, 14], [0.010, 6], [0.012, 0]], k = 5.3e5;
  const op = fanOperatingPoint(dip, k), s = { ...DEFAULTS };
  const r = { fan: { name: 'a fan with a deep dip' }, single: dip, curve: dip, k, op, stall: fanStallFlow(dip), stallEach: fanStallFlow(dip),
    each: { flow: op.flow, pressure: op.pressure } };
  assert.equal(op.intersections.length, 3);
  assert.deepEqual(verdict(s, r), { text: 'Unstable', note: 'Crosses the curve 3 times', poor: true });
  assert.match(summary(s, r), /crosses the fan curve 3 times, so the fan can settle at any of them, and the highest flow is shown/);
  assert.match(drawFanCurve(s, r), /data-part="point"/);
});

test('attributes are read safely: unknown values fall back, numbers clamp to the controls', () => {
  const read = attrs => readState(n => attrs[n] ?? null);
  assert.deepEqual(read({}), { ...DEFAULTS });
  assert.deepEqual(read({ fan: '16', system: '999', count: '0', arrangement: 'series' }), { fan: '16', system: 60, count: 1, arrangement: 'series' });
  assert.deepEqual(read({ fan: '13', system: 'x', count: '2.6', arrangement: 'toString' }), { ...DEFAULTS, count: 3 });
});

test('the fan-curve still on its pages is what the component draws for the pages\' attributes', () => {
  const out = execFileSync(process.execPath, ['tools/fan-curve-still.mjs', '--check'], { cwd: root }).toString();
  assert.match(out, /current/);
});
