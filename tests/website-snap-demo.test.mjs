// The landing page's snap-fit animation must show a real engagement: contact on the way in, a hook that drops in
// behind the catch, and a retaining face that holds when the part is pulled back. tools/snap-demo.mjs computes it.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ARM, RIB, PARTS, ARC_DEG, UNDERCUT_DEG, clear, liftAt, lockMoment, pullStop, snapOffset, timeline, snapDemo } from '../tools/snap-demo.mjs';

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
    if (lift > 0.05 && offset > snapOffset()) {        // drawn on the lowest pose the swing can reach, which touches
      const low = liftAt(offset);
      assert.ok(lift - low < 0.05 && !clear(low - 0.01, offset), `hook floats above the catch at ${pct}% (lift ${lift})`);
      touching++;
    }
  }
  assert.ok(touching >= 10, `only ${touching} contact frames`);
});

test('the catch\'s own lead-in lifts the arm gradually', () => {
  // With the hook's ramp squared off, only the rib's chamfer can ease the arm up; without it the lift is one step.
  const squareHook = ARM.map(p => (p[0] === 290 && p[1] === Math.max(...ARM.map(q => q[1])) ? [318, p[1]] : p));
  const biggestStep = parts => {                       // largest lift change between samples 1.5 units apart
    const lifts = [...Array(40).keys()].map(i => liftAt(90 - i * 1.5, parts));
    return Math.max(...lifts.slice(1).map((l, i) => Math.abs(l - lifts[i])));
  };
  const eased = biggestStep({ ...PARTS, arm: squareHook });
  assert.ok(eased < 0.6, `the rib lead-in does not ease the arm up (steps of ${eased}°)`);
  const squareRib = RIB.map((p, i) => (i === 1 ? [246, RIB[2][1]] : p)).filter((p, i) => i !== 2);
  const stepped = biggestStep({ ...PARTS, arm: squareHook, rib: squareRib });
  assert.ok(stepped > 2, `control: a square rib should lift in one step (got ${stepped}°)`);
});

test('the retaining faces lock: a pull-back turns the hook into the catch, not out of it', () => {
  assert.ok(UNDERCUT_DEG > ARC_DEG, `faces lean ${UNDERCUT_DEG}°, the hook's arc ${ARC_DEG}°`);
  assert.ok(lockMoment() > 0, `moment ${lockMoment()} (needs > 0: the joint would hold by friction only)`);
  const squareFace = RIB.map((p, i) => (i === 4 ? [RIB[3][0], p[1]] : p));
  assert.ok(lockMoment(squareFace) < 0, 'control: a square face below the pivot should cam out');
  const chamfered = RIB.map((p, i) => (i === 3 ? [RIB[3][0] - 8, p[1]] : i === 4 ? [RIB[3][0] + 6, p[1]] : p));
  assert.ok(lockMoment(chamfered) < 0, 'control: a chamfered face should cam out');
});

test('every in-between pose the browser draws is clear, read back from the emitted CSS', () => {
  // Both tracks are parsed out of the stylesheet (the catch's slide and the arm's swing), so a change to either
  // one's emitted values is checked, and each segment is sampled finely enough to catch a sub-millisecond overlap.
  const { rows } = timeline();
  const { css } = snapDemo();
  const frames = name => [...css.match(new RegExp(`@keyframes ${name}\\{(.*?)\\}\\}`))[1].matchAll(/([\d.,%]+)\{([^}]*)/g)]
    .flatMap(([, pcts, body]) => pcts.split(',').map(p => [parseFloat(p), body]));
  const slide = frames('snap-catch').map(([p, b]) => [p, parseFloat(b.match(/translateX\(([-\d.]+)px/)[1]), parseFloat(b.match(/opacity:([\d.]+)/)[1])]);
  const swing = frames('snap-arm').map(([p, b]) => [p, 0 - parseFloat(b.match(/rotate\(([-\d.]+)deg/)[1])]);   // 0 - x: no -0
  assert.deepEqual(slide.map(r => r[0]), swing.map(r => r[0]), 'the two tracks have different keyframe times');
  assert.deepEqual(slide.map((r, i) => [r[0], r[1], swing[i][1], r[2]]), rows.map(r => [r[0], r[1], r[2] || 0, r[3]]), 'emitted keyframes differ from the timeline');
  for (let i = 1; i < slide.length; i++) assert.ok(slide[i][0] > slide[i - 1][0], `keyframe times not increasing at ${slide[i][0]}%`);
  for (let i = 1; i < slide.length; i++) for (let k = 1; k < 500; k++) {
    const t = k / 500, a = slide[i - 1], b = slide[i];
    if (!a[2] && !b[2]) continue;                      // the reset jump, while the part is invisible
    const offset = a[1] + (b[1] - a[1]) * t, lift = swing[i - 1][1] + (swing[i][1] - swing[i - 1][1]) * t;
    assert.ok(clear(lift, offset), `overlap between ${a[0]}% and ${b[0]}% (t=${t}, offset ${offset}, lift ${lift})`);
  }
});

test('the hook drops in only once its whole swing to rest is clear', () => {
  const snap = snapOffset();
  for (let l = 0; l <= 4; l += 0.02) assert.ok(clear(l, snap - 0.01), `the drop at ${snap} hits the catch at lift ${l}`);
  assert.ok(liftAt(snap + 0.01) > 3, 'just before the drop the hook still rides the corner');
});

test('the generated CSS animates catch, arm, root and label together', () => {
  const { css, svg } = snapDemo();
  for (const name of ['snap-catch', 'snap-arm', 'snap-strain', 'snap-click']) assert.match(css, new RegExp(`@keyframes ${name}\\{`));
  assert.match(css, /prefers-reduced-motion/);
  for (const cls of ['catch', 'arm', 'root', 'click']) assert.match(svg, new RegExp(`class="${cls}"`));
});
