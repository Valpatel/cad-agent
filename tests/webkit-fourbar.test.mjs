// <cad-fourbar>'s pure parts (src/cadagent/webkit/fourbar.js) in Node: the state it reads from attributes, what it
// computes from the tested port (kit/formulas.js), that its animation never asks the links for a position they cannot
// reach (a dead point stops the crank instead of making it jump), and that its still is what it draws.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { readState, compute, angleAt, drawFourbar, drawChart, summary, travelText, className, pill, chartMarker, DEFAULTS, CONTROLS }
  from '../src/cadagent/webkit/fourbar.js';
import { fourbarAngles, fourbarInputLimits, grashof, transmissionAngle } from '../src/cadagent/webkit/formulas.js';

const root = path.resolve(import.meta.dirname, '..');
const RAD = Math.PI / 180;
const state = (attrs = {}) => readState(n => attrs[n] ?? null);

test('attributes: numbers clamp, unknown values fall back, the angle wraps to (-180, 180]', () => {
  assert.deepEqual(state(), { ...DEFAULTS });
  const s = state({ crank: '5', coupler: '400', rocker: 'x', ground: '60.5', branch: 'crossed', angle: '540' });
  assert.deepEqual([s.crank, s.coupler, s.rocker, s.ground, s.branch, s.angle], [CONTROLS.crank.min, CONTROLS.coupler.max, DEFAULTS.rocker, 60.5, 'crossed', 180]);
  assert.equal(state({ branch: 'toString' }).branch, 'open', 'an inherited key is not a branch');
  assert.equal(state({ angle: '-180' }).angle, 180);
  assert.equal(state({ angle: '-90' }).angle, -90);
});

test("the default is Norton's Example 4-1: a crank-rocker that turns fully, its transmission angle lowest at 0 degrees", () => {
  const s = state(), r = compute(s);
  assert.equal(className(r), 'Crank-rocker');
  assert.deepEqual(r.grashof, grashof(40, 120, 80, 100));
  assert.equal(r.travel.kind, 'turn');
  assert.equal(r.low.t, 0);
  assert.equal(r.low.mu, transmissionAngle(40, 120, 80, 100, 0));
  assert.equal(Number((r.low.mu / RAD).toFixed(1)), 26.4);
  assert.match(pill(r).text, /^Crank-rocker · lowest μ 26\.4° < 40°$/);
  assert.match(summary(s, r), /lowest transmission angle 26\.4° at 0°, below the 40° guideline/);
});

test('a rocking input: the travel is the port\'s limits, the start moves into it, and the chart runs through its middle', () => {
  const tri = compute(state({ crank: '100', coupler: '80', rocker: '70', ground: '60' }));
  const lim = fourbarInputLimits(100, 80, 70, 60);
  assert.deepEqual([tri.travel.lo, tri.travel.hi], [-lim.stretched, lim.stretched]);
  assert.equal(travelText(tri), '±137.9°');
  assert.equal(pill(tri).text, 'Triple rocker · locks at ±137.9°');
  assert.equal(tri.axis, -Math.PI);
  // a double rocker has two ranges, one each side of the ground: the start (40) moves to the nearer end of the upper
  const dr = compute(state({ crank: '80', coupler: '40', rocker: '120', ground: '100' }));
  const dl = fourbarInputLimits(80, 40, 120, 100);
  assert.deepEqual([dr.travel.lo, dr.travel.hi, dr.travel.mirror], [dl.folded, dl.stretched, true]);
  assert.equal(dr.start, dl.folded);
  const below = compute(state({ crank: '80', coupler: '40', rocker: '120', ground: '100', angle: '-100' }));
  assert.deepEqual([below.travel.lo, below.travel.hi], [-dl.stretched, -dl.folded]);
  // limits only on the folded side: the travel runs through 180 degrees and the chart's axis is 0..360
  const rc = compute(state({ crank: '40', coupler: '100', rocker: '30', ground: '50', angle: '-170' }));
  assert.ok(rc.travel.hi > Math.PI && rc.axis === 0 && rc.start > Math.PI, JSON.stringify(rc.travel));
  // links that cannot make a loop: no travel, nothing to animate
  const none = compute(state({ crank: '150', coupler: '10', rocker: '10', ground: '20' }));
  assert.equal(none.travel, null);
  assert.equal(className(none), 'No loop');
});

test('every slider setting: the animation stays where the links close, stops at the limits, and the figure draws', () => {
  const values = [10, 30, 50, 70, 90, 110, 130, 150];
  let rocking = 0, turning = 0, open = 0;
  for (const crank of values) for (const coupler of values) for (const rocker of values) for (const ground of values) {
    const s = { ...DEFAULTS, crank, coupler, rocker, ground }, r = compute(s);
    const lim = fourbarInputLimits(crank, coupler, rocker, ground);
    if (!r.travel) { open++; assert.ok(!lim.closes); continue; }
    if (r.travel.kind === 'turn') turning++; else rocking++;
    for (const branch of ['open', 'crossed']) {
      // a cycle and a half, every 37 ms: the input is always inside its travel and the links close there
      const crossed = branch === 'crossed';
      let seenLo = false, seenHi = false;
      for (let t = 0; t <= 14000; t += 37) {
        const t2 = angleAt(r, t);
        assert.ok(fourbarAngles(crank, coupler, rocker, ground, t2, crossed), `${[crank, coupler, rocker, ground]} ${branch} at ${t} ms: ${t2}`);
        if (r.travel.kind === 'rock') {
          assert.ok(t2 >= r.travel.lo && t2 <= r.travel.hi);
          seenLo ||= t2 === r.travel.lo; seenHi ||= t2 === r.travel.hi;
        }
      }
      if (r.travel.kind === 'rock') assert.ok(seenLo && seenHi, `${[crank, coupler, rocker, ground]}: the crank never rests at a limit`);
    }
    assert.equal(r.travel.kind === 'turn', lim.fullTurn);
  }
  assert.ok(rocking > 500 && turning > 200 && open > 100, `${rocking} rocking, ${turning} turning, ${open} open`);
  // the drawings, for a spread of them: no NaN, no undefined
  for (const crank of [10, 70, 150]) for (const coupler of [10, 90, 150]) for (const branch of ['open', 'crossed']) {
    const s = { ...DEFAULTS, crank, coupler, branch }, r = compute(s);
    for (const svg of [drawFourbar(s, r), drawFourbar(s, r, { compact: true }), drawChart(s, r)])
      assert.doesNotMatch(svg, /NaN|undefined|Infinity/, `${crank} ${coupler} ${branch}`);
  }
});

test('the first frame is the start angle exactly, so the live figure takes over from the still without a jump', () => {
  for (const attrs of [{}, { crank: '100', coupler: '80', rocker: '70', ground: '60', angle: '120' }, { crank: '80', coupler: '40', rocker: '120', ground: '100' }]) {
    const r = compute(state(attrs));
    assert.equal(angleAt(r, 0), r.start);
    assert.ok(Math.abs(angleAt(r, 1) - r.start) < 2e-3, 'and moves on smoothly');
  }
});

test('the chart marker sits on the transmission angle the port gives', () => {
  const s = state(), r = compute(s);
  for (const deg of [-170, -90, 0, 40, 135]) {
    const m = chartMarker(s, r, deg * RAD), mu = transmissionAngle(40, 120, 80, 100, deg * RAD);
    assert.ok(m.closes);
    assert.ok(Math.abs(m.y - (116 - 102 * (mu / RAD) / 90)) < 0.01, `${deg}: ${m.y}`);
  }
});

test('the four-bar still on its pages is what the component draws for their attributes', () => {
  const out = execFileSync(process.execPath, ['tools/fourbar-still.mjs', '--check'], { cwd: root }).toString();
  assert.match(out, /current/);
});
