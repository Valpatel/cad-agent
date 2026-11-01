// <cad-torsion-snap> (src/cadagent/webkit/torsion-snap.js) without a browser: every bar it can show gives the port's
// numbers, the strain scales as Saint-Venant says, the figure stays inside its box, and the still on docs/compliant is
// what the component draws for the page's attributes (tools/torsion-snap-still.mjs --check).
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { readState, compute, summary, drawTorsionSnap, strainColour, CONTROLS, DEFAULTS, VIEW, PALETTES } from '../src/cadagent/webkit/torsion-snap.js';
import { torsionShearStrainRect } from '../src/cadagent/webkit/formulas.js';
import { MATERIALS } from '../src/cadagent/webkit/formulas-data.js';

const root = path.resolve(import.meta.dirname, '..');
const DEG = Math.PI / 180;

test('the demo takes the filament across the layers and its highest modulus, and passes them to the port', () => {
  for (const m of MATERIALS) for (const repeated of [false, true]) {
    const r = compute({ ...DEFAULTS, material: m.key, repeated });
    assert.equal(r.allowable, m.allowable.across[repeated ? 'repeated' : 'single']);
    assert.equal(r.modulus, m.modulus.along, `${m.key}: the force is an upper bound, from the higher modulus`);
    assert.ok(Math.abs(r.allowableShearStrain - 1.35 * r.allowable) < 1e-15);
    assert.ok(Math.abs(r.shearStrain - torsionShearStrainRect(8 * DEG, 0.015, 0.004, 0.0012)) < 1e-15);
  }
  const one = compute({ ...DEFAULTS, bars: 1 }), two = compute(DEFAULTS);
  assert.ok(Math.abs(two.force - 2 * one.force) < 1e-12 && two.shearStrain === one.shearStrain, 'two bars: twice the force, the same strain');
  const long = compute({ ...DEFAULTS, length: 30 });
  assert.ok(Math.abs(long.shearStrain - two.shearStrain / 2) < 1e-15 && Math.abs(long.force - two.force / 2) < 1e-12);
  assert.ok(Math.abs(two.permissibleTwist / DEG - 8 / two.ratio) < 1e-9, 'the limit twist is where the ratio reaches 1');
});

test('the page\'s lessons hold: 86 % at 8°, fails past 9.3°, opened often it fails, PETG passes and CoPA fails', () => {
  const at = s => compute({ ...DEFAULTS, ...s });
  assert.equal(Math.round(at({}).ratio * 100), 86);
  assert.equal((at({}).permissibleTwist / DEG).toFixed(1), '9.3');
  assert.ok(!at({ repeated: true }).passes && Math.round(at({ repeated: true }).ratio * 100) === 144);
  assert.ok(at({ material: 'petg-polymaker' }).passes && !at({ material: 'copa-polymaker-dry' }).passes);
  assert.match(summary(DEFAULTS, at({})), /^Torsion-snap explorer: two bars of Bambu PLA Basic, each 15 mm long, 4 × 1\.2 mm, twisted 8° by a 10 mm lever: peak shear strain 1\.11 %/);
  assert.match(summary({ ...DEFAULTS, bars: 1 }, at({ bars: 1 })), /^Torsion-snap explorer: one bar of Bambu PLA Basic, 15 mm long/);
  // twisted far, a wide thin bar's trapeze effect is flagged (the page's 30 × 12 × 0.6 mm bar at 30°); the default is not
  assert.ok(at({}).smallTwist && !/trapeze/.test(summary(DEFAULTS, at({}))));
  const far = { ...DEFAULTS, length: 30, width: 12, thickness: 0.6, twist: 30 };
  assert.ok(!at(far).smallTwist);
  assert.match(summary(far, at(far)), /Twisted far: the edges stretch \(the trapeze effect\), adding 41 % to the torque and 0\.37 % strain along them\./);
});

test('every corner of the controls draws inside the figure, in both themes and layouts', () => {
  const corners = Object.entries(CONTROLS).map(([k, c]) => [k, [c.min, c.max]]);
  let n = 0;
  const walk = (i, s) => {
    if (i === corners.length) {
      for (const bars of [1, 2]) {
        const st = { ...s, bars }, r = compute(st);
        assert.ok(Number.isFinite(r.shearStrain) && Number.isFinite(r.force) && r.force >= 0, JSON.stringify(st));
        for (const compact of [false, true]) for (const palette of Object.values(PALETTES)) {
          const svg = drawTorsionSnap(st, r, { compact, palette });
          assert.doesNotMatch(svg, /NaN|Infinity|undefined/, JSON.stringify(st));
          for (const [, x, y] of svg.matchAll(/<text[^>]* x="(-?[\d.]+)" y="(-?[\d.]+)"/g))
            assert.ok(+x >= 0 && +x <= VIEW.width && +y >= 0 && +y <= VIEW.height, `${JSON.stringify(st)}: a label at ${x}, ${y}`);
          n++;
        }
      }
      return;
    }
    for (const v of corners[i][1]) walk(i + 1, { ...s, [corners[i][0]]: v });
  };
  walk(0, { ...DEFAULTS });
  assert.equal(n, 2 ** corners.length * 2 * 4);
});

test('strain colours run from mist through peach to rust, in both palettes', () => {
  for (const P of Object.values(PALETTES)) {
    assert.equal(strainColour(0, P), P.mist);
    assert.equal(strainColour(0.7, P), P.peach);
    assert.equal(strainColour(1, P), P.rust);
    assert.equal(strainColour(3, P), P.rust);
  }
});

test('attributes are read safely: unknown values fall back, numbers clamp to the controls', () => {
  const read = attrs => readState(n => attrs[n] ?? null);
  assert.deepEqual(read({}), { ...DEFAULTS });
  assert.deepEqual(read({ material: 'nope', bars: '3', length: '999', twist: '-4', lever: 'x', thickness: '1.234' }),
    { ...DEFAULTS, length: 30, twist: 0, thickness: 1.2 });
  assert.equal(read({ repeated: '' }).repeated, true);
  assert.equal(read({ repeated: 'false' }).repeated, false);
  assert.equal(read({ bars: '1', material: 'copa-polymaker-dry' }).material, 'copa-polymaker-dry');
});

test('the torsion-snap still on docs/compliant is what the component draws for the page\'s attributes', () => {
  const out = execFileSync(process.execPath, ['tools/torsion-snap-still.mjs', '--check'], { cwd: root }).toString();
  assert.match(out, /current/);
});
