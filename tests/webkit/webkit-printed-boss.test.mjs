// <cad-printed-boss> (src/cadagent/webkit/printed-boss.js) without a browser: the demo passes the filament's strengths
// and the friction band to the port as cadagent.mechanical.bosses does, its verdict names every failing check, the
// figure stays inside its box, and the still on docs/screw-bosses is what the component draws for the page's
// attributes (tools/printed-boss-still.mjs --check).
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { readState, compute, summary, verdict, drawPrintedBoss, spread, minOutside, screwOf, CONTROLS, DEFAULTS, VIEW, PALETTES,
  AXES } from '../../src/cadagent/webkit/printed-boss.js';
import { screwBoss } from '../../src/cadagent/webkit/formulas.js';
import { MATERIALS, SCREWS } from '../../src/cadagent/webkit/formulas-data.js';

const root = path.resolve(import.meta.dirname, '../..');

test('the demo gives the port half the lowest strength across the layers, the hoop strength by axis, the friction band', () => {
  for (const m of MATERIALS) for (const axis of Object.keys(AXES)) {
    const s = { ...DEFAULTS, material: m.key, axis }, r = compute(s);
    assert.equal(r.shearStrength, 0.5 * m.strength.across);
    assert.equal(r.hoopStrength, m.strength[axis === 'upright' ? 'along' : 'across']);
    const want = screwBoss(0.003, screwOf('30').pitch, 0.006, 0.006, 0.3, r.shearStrength, r.hoopStrength, 0.2, 0.65);
    for (const k of Object.keys(want)) assert.deepEqual(r[k], want[k], `${m.key} ${axis}: ${k}`);
  }
  assert.deepEqual(SCREWS.friction, [0.2, 0.65]);
});

test('the page\'s lessons hold', () => {
  const at = s => compute({ ...DEFAULTS, ...s });
  const r = at({});
  assert.ok(r.passes && r.stripForce.toFixed(0) === '767' && r.torqueCeiling.toFixed(2) === '0.31');
  assert.deepEqual(at({ torque: 0.4 }).failing, ['torque']);
  assert.deepEqual(at({ outside: 4 }).failing, ['outside']);
  assert.deepEqual(at({ engagement: 3 }).failing, ['torque', 'engagement']);
  assert.ok(at({ material: 'copa-polymaker-dry' }).passes && !at({ material: 'petg-bambu-hf' }).passes);
  assert.equal(verdict(r), 'inside the guide and the torque window');
  assert.equal(verdict(at({ engagement: 3 })), 'tightened past half the strip torque +1 more');
  assert.equal(verdict(at({ engagement: 3 }), false), 'over-tightened +1');
  // the drive torque makes no clamp: unmeasured, the band's low end takes the most the window allows (T / 1.2)
  assert.match(summary(DEFAULTS, r), /clamp 22 to 374 N \(the low end if the drive torque, which makes no clamp, is the most the window allows\); /);
  assert.match(summary(DEFAULTS, r), /the thread strips at 767 N, at 0\.62 N·m to 1\.74 N·m over the drive torque, so tighten to at most 0\.31 N·m/);
  assert.match(summary(DEFAULTS, r), /A starting point to test, not a rating\.$/);
});

test('every screw and every corner of the controls draws inside the figure, in both themes and layouts', () => {
  let n = 0;
  for (const { key } of SCREWS.sizes) for (const axis of Object.keys(AXES))
    for (const outside of [CONTROLS.outside.min, CONTROLS.outside.max]) for (const engagement of [CONTROLS.engagement.min, CONTROLS.engagement.max])
      for (const torque of [CONTROLS.torque.min, CONTROLS.torque.max]) {
        const s = readState(a => ({ size: key, axis, outside: String(outside), engagement: String(engagement), torque: String(torque) })[a] ?? null);
        assert.ok(s.outside >= minOutside(key) && s.outside > screwOf(key).diameter * 1e3, `${key}: the boss is wider than the screw`);
        const r = compute(s);
        for (const compact of [false, true]) for (const palette of Object.values(PALETTES)) {
          const svg = drawPrintedBoss(s, r, { compact, palette });
          assert.doesNotMatch(svg, /NaN|Infinity|undefined/, JSON.stringify(s));
          for (const [, x, y] of svg.matchAll(/<text[^>]* x="(-?[\d.]+)" y="(-?[\d.]+)"/g))
            assert.ok(+x >= 0 && +x <= VIEW.width && +y >= 0 && +y <= VIEW.height, `${JSON.stringify(s)}: a label at ${x}, ${y}`);
          n++;
        }
      }
  assert.equal(n, SCREWS.sizes.length * 2 * 8 * 4);
});

test('the torque labels keep their order and their spacing inside the ladder', () => {
  assert.deepEqual(spread([10, 12, 50, 51], 10, 0, 100), [10, 20, 50, 60]);
  assert.deepEqual(spread([95, 96, 97], 10, 0, 100), [80, 90, 100]);
  assert.deepEqual(spread([30, 5], 10, 0, 100), [30, 5]);
});

test('attributes are read safely: unknown values fall back, numbers clamp, the boss stays wider than the screw', () => {
  const read = attrs => readState(n => attrs[n] ?? null);
  assert.deepEqual(read({}), { ...DEFAULTS });
  assert.deepEqual(read({ material: 'x', size: 'M3', axis: 'toString', torque: '99', engagement: '-1' }), { ...DEFAULTS, torque: 3, engagement: 1 });
  assert.equal(read({ size: '50', outside: '3' }).outside, 5.4);
  assert.deepEqual(SCREWS.sizes.map(x => minOutside(x.key)), [2.4, 2.9, 3.4, 3.9, 4.4, 5.4]);
  assert.equal(CONTROLS.outside.min, Math.min(...SCREWS.sizes.map(x => minOutside(x.key))));
});

test('the screw-boss still on docs/screw-bosses is what the component draws for the page\'s attributes', () => {
  const out = execFileSync(process.execPath, ['tools/printed-boss-still.mjs', '--check'], { cwd: root }).toString();
  assert.match(out, /current/);
});
