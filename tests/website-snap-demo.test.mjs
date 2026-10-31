// The landing page's snap-fit animation must show a real engagement: contact on the way in, a hook that drops in
// behind the catch, and a retaining face that holds when the part is pulled back. tools/snap-demo.mjs computes it.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ARM, RIB, clear, liftAt, pullStop, snapOffset, timeline, snapDemo } from '../tools/snap-demo.mjs';

const hookTipY = Math.max(...ARM.map(p => p[1]));
const ribTopY = Math.min(...RIB.map(p => p[1]));

test('at rest the hook sits behind the catch, overlapping it in depth', () => {
  assert.ok(clear(0, 0), 'engaged parts overlap');
  assert.ok(hookTipY - ribTopY >= 10, `hook engages the catch by ${hookTipY - ribTopY} units`);
});

test('pulling back is stopped by the retaining faces within a small clearance', () => {
  const stop = pullStop();
  assert.ok(stop > 0.5 && stop < 4, `free play ${stop}`);
  assert.ok(!clear(0, stop + 0.5), 'the hook would pass the catch without lifting');
});

test('insertion lifts the arm by the interference and the hook stays in contact', () => {
  const { rows, maxLift } = timeline();
  const radius = Math.hypot(286 - 64, 154 - 121);
  const needed = (hookTipY - ribTopY) / radius * 180 / Math.PI;
  assert.ok(Math.abs(maxLift - needed) < 0.6, `max lift ${maxLift}°, interference needs ≈${needed}°`);
  let touching = 0;
  for (const [pct, offset, lift] of rows) {
    assert.ok(clear(lift, offset), `outlines overlap at ${pct}%`);
    if (lift > 0.05 && offset > snapOffset()) {
      assert.ok(!clear(lift - 0.05, offset), `hook floats above the catch at ${pct}% (lift ${lift})`);
      touching++;
    }
  }
  assert.ok(touching >= 10, `only ${touching} contact frames`);
});

test('the lead-in is on the catch side that meets the hook first', () => {
  // Sliding in (offset decreasing), the arm starts to lift gradually on the ramps, not in one step.
  const lifts = [40, 36, 32, 28].map(liftAt);
  assert.ok(lifts.some(l => l > 0 && l < Math.max(...lifts)), lifts.join(', '));
});

test('the generated CSS animates catch, arm, root and label together', () => {
  const { css, svg } = snapDemo();
  for (const name of ['snap-catch', 'snap-arm', 'snap-strain', 'snap-click']) assert.match(css, new RegExp(`@keyframes ${name}\\{`));
  assert.match(css, /prefers-reduced-motion/);
  for (const cls of ['catch', 'arm', 'root', 'click']) assert.match(svg, new RegExp(`class="${cls}"`));
});
