/** kit/model.js, the <cad-model> element's decoder, against the reference (cadagent.publish.view.unpack_model): the packed
 * fixture decodes to what Python decodes, and the site's committed Gyropup model decodes whole and in place (#179). */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { decodeModel, inflate, partLabel } from '../src/cadagent/webkit/model.js';

const root = path.resolve(import.meta.dirname, '..');
const load = async (json) => {
  const model = JSON.parse(await readFile(path.join(root, json), 'utf8'));
  const packed = await readFile(path.join(path.dirname(path.join(root, json)), model.bin));
  return { model, packed, parts: decodeModel(model, await inflate(packed)) };
};

test('decodeModel reads the fixture exactly as unpack_model does', async () => {
  const { parts } = await load('tests/fixtures/model/two-parts.json');
  const want = JSON.parse(await readFile(path.join(root, 'tests/fixtures/model/two-parts.decoded.json'), 'utf8'));
  assert.equal(parts.length, want.length);
  for (const [i, part] of parts.entries()) {
    assert.deepEqual([...part.index], want[i].triangles.flat(), `${want[i].name}: triangles`);
    const got = [...part.positions], flat = want[i].vertices.flat();
    assert.equal(got.length, flat.length);
    // float32 in the browser against float64 in numpy: well under the 0.0008 mm quantisation step here
    for (let k = 0; k < got.length; k++) assert.ok(Math.abs(got[k] - flat[k]) < 1e-4, `${want[i].name}[${k}]: ${got[k]} vs ${flat[k]}`);
  }
});

test('the site\'s Gyropup model decodes whole, matches its checksum and sits where its parts were exported', async () => {
  const { model, packed, parts } = await load('web/models/gyropup.json');
  assert.equal(model.schema, 'cad-agent-model/1');
  assert.equal(packed.length, model.bytes);
  assert.equal(createHash('sha256').update(packed).digest('hex'), model.sha256);
  assert.ok(model.bytes < 400 * 1024, `the home page's model stays small: ${model.bytes} bytes`);
  assert.equal(parts.reduce((n, p) => n + p.index.length / 3, 0), model.triangles);
  for (const [i, part] of parts.entries()) {
    const meta = model.parts[i], n = part.positions.length / 3;
    assert.equal(n, meta.vertices, meta.name);
    assert.ok(part.index.every(v => v < n), `${meta.name}: an index past its vertices`);
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (let k = 0; k < part.positions.length; k++) { lo[k % 3] = Math.min(lo[k % 3], part.positions[k]); hi[k % 3] = Math.max(hi[k % 3], part.positions[k]); }
    // Inside the box the export measured on the STEP solid (to 0.02 mm: rounding and one 16-bit step) and filling it
    // to within 1 mm (that box is OpenCascade's, a little loose on curved faces, and a 0.3 mm chord cuts inside them).
    [...lo, ...hi].forEach((v, k) => {
      const inward = k < 3 ? v - meta.bounds_mm[k] : meta.bounds_mm[k] - v;
      assert.ok(inward > -0.02 && inward < 1, `${meta.name}: bound ${k} is ${v.toFixed(3)}, exported ${meta.bounds_mm[k]}`);
    });
  }
});

test('part labels read as words, with a side spelled out', () => {
  assert.equal(partLabel('wheel_link'), 'wheel link');
  assert.equal(partLabel('thigh_l'), 'thigh (left)');
  assert.equal(partLabel('hip_motor_r'), 'hip motor (right)');
});
