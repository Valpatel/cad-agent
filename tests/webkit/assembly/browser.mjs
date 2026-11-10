/** Real shared viewer, three distinct snapshots, independent CAD-frame expectations and owned cleanup. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '../../site/npm-context.mjs';
import { serveWebkit } from '../webkit-server.mjs';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const encode = value => Buffer.from(JSON.stringify(value));
function cube(origin, size) {
  const vertices = Array.from({ length: 8 }, (_, i) => origin.map((n, axis) => n + (i & (1 << axis) ? size[axis] : 0)));
  const faces = [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4], [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]];
  const bytes = Buffer.alloc(84 + 50 * faces.length); bytes.writeUInt32LE(faces.length, 80);
  faces.forEach((face, i) => face.forEach((vertex, j) => vertices[vertex].forEach((n, k) => bytes.writeFloatLE(n, 84 + 50 * i + 12 + j * 12 + k * 4))));
  return { bytes, bounds: [...origin, ...origin.map((n, i) => n + size[i])] };
}
const routes = new Map(), versions = ['v1', 'v2', 'wip'];
for (const [index, version] of versions.entries()) {
  const shapes = [cube([0, 0, 0], [40 + index * 10, 30, 8]), cube([8, 8, 8], [5, 5, 20]), cube([28, 8, 8], [5, 5, 20])];
  const names = ['base', 'screw#1', 'screw#2'];
  shapes.forEach((shape, i) => routes.set(`/${version}/${i}.stl`, (_, res) => res.end(shape.bytes)));
  const manifest = { title: version, units: 'mm', up: 'z', parts: shapes.map((shape, i) => ({ name: names[i], file: `${i}.stl`, sha256: hash(shape.bytes), bounds_mm: shape.bounds, color: ['#487ca8', '#eaa840', '#eaa840'][i] })) };
  const raw = encode(manifest); routes.set(`/${version}/view.json`, (_, res) => res.end(raw));
  const guide = { schema: 'cad-agent.assembly-guide/1', snapshot: { id: version, revision: version, status: version === 'wip' ? 'wip' : 'released', source_commit: String(index + 1).repeat(40) }, model: { file: 'view.json', sha256: hash(raw) },
    subassemblies: [{ id: 'frame', title: 'Frame', parts: names }], steps: [
      { id: 'base', title: 'Seat base', text: `Instruction ${version}: base only.`, subassembly: 'frame', parts: ['base'], highlight: ['base'], offsets_mm: {} },
      { id: 'screws', title: 'Add both screws', text: `Instruction ${version}: fit both screws.`, subassembly: 'frame', parts: names, highlight: names.slice(1), offsets_mm: { 'screw#1': [0, 0, 25 + index * 5], 'screw#2': [0, 0, 25 + index * 5] }, requires: ['base'], camera: { direction: [0, -1, 0] } },
    ] };
  routes.set(`/${version}/guide.json`, (_, res) => res.end(encode(guide)));
}
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-assembly-guide'; await mkdir(out, { recursive: true });
const site = await serveWebkit(routes); let browser;
const cases = [], errors = [];
const near = (actual, expected, tolerance = 1e-6) => actual.forEach((n, i) => assert.ok(Math.abs(n - expected[i]) < tolerance, `${actual} != ${expected}`));
try {
  browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
  const context = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  const visit = async (version, viewport = { width: 1100, height: 800 }) => {
    await page.setViewportSize(viewport);
    await page.goto(`${site.url}/kit/viewer.html?guide=${encodeURIComponent(`/${version}/guide.json`)}`);
    await page.waitForFunction(() => document.body.dataset.ready === '1', { timeout: 15000 });
  };
  const inspect = () => page.evaluate(async () => {
    const THREE = await import('/kit/vendor/three/three.module.min.js'), v = window.__viewer;
    v.stage.root.updateMatrixWorld(true);
    return v.parts.map(p => ({ name: p.name, visible: p.mesh.visible, offset: p.mesh.position.toArray(), world: p.mesh.getWorldPosition(new THREE.Vector3()).toArray(), opacity: p.mesh.material.opacity, transparent: p.mesh.material.transparent, depthWrite: p.mesh.material.depthWrite, wireframe: p.mesh.material.wireframe, emissive: p.mesh.material.emissive.getHex(), color: p.mesh.material.color.getHex(), uuid: p.mesh.uuid }));
  });
  const v1UUIDs = [];
  for (const [index, version] of versions.entries()) {
    await visit(version);
    assert.match(await page.locator('.guide-version').innerText(), new RegExp(`${version}.*${String(index + 1).repeat(10)}`));
    const before = await inspect(); assert.deepEqual(before.map(p => p.visible), [true, false, false]);
    if (!index) v1UUIDs.push(...before.map(p => p.uuid)); else assert.ok(before.every(p => !v1UUIDs.includes(p.uuid)));
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    const forward = await inspect(); assert.deepEqual(forward.map(p => p.visible), [true, true, true]);
    assert.deepEqual(forward.map(p => p.opacity), [0.2, 1, 1]); assert.deepEqual(forward.map(p => p.depthWrite), [false, true, true]);
    // Independent physical expectations, not read back from the guide: CAD +Z is stage +Y and mm -> m once.
    near(forward[1].world.map((n, axis) => n - before[1].world[axis]), [0, 0.025 + index * 0.005, 0]);
    assert.ok(forward[1].emissive > 0 && forward[2].emissive > 0 && forward[0].emissive === 0);
    await page.getByRole('button', { name: 'Previous', exact: true }).click();
    await page.getByLabel('Instruction step', { exact: true }).selectOption('screws');
    const direct = await inspect(); assert.deepEqual(direct.map(p => p.offset), forward.map(p => p.offset));
    await page.getByLabel('Instruction display', { exact: true }).selectOption('wireframe'); assert.ok((await inspect()).every(p => p.wireframe));
    await page.getByLabel('Instruction display', { exact: true }).selectOption('solid'); assert.ok((await inspect()).every(p => !p.wireframe && p.opacity === 1));
    await page.evaluate(() => { const v = window.__viewer; v.setSelection('screw#2'); v.applyState({ ...v.getState(), isolate: ['screw#2'] }); });
    assert.deepEqual((await inspect()).map(p => p.visible), [false, false, true]);
    await page.getByRole('button', { name: 'Assembled', exact: true }).click();
    const reset = await inspect(); assert.ok(reset.every(p => p.visible && p.offset.every(n => n === 0) && p.opacity === 1 && !p.wireframe && p.emissive === 0));
    assert.deepEqual(reset.map(p => p.color), before.map(p => p.color));
    // Real picking: project the visible base centre and click its canvas position.
    const point = await page.evaluate(async () => { const THREE = await import('/kit/vendor/three/three.module.min.js'), v = window.__viewer, p = v.parts[0]; const q = new THREE.Vector3(...p.center.toArray()); p.mesh.localToWorld(q); q.project(v.stage.camera); const r = v.stage.renderer.domElement.getBoundingClientRect(); return [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2]; });
    await page.mouse.click(...point); assert.ok(await page.evaluate(() => window.__viewer.getState().selected !== null));
    await page.screenshot({ path: `${out}/${engine.name()}-${version}.png` });
    cases.push({ version, snapshot: await page.evaluate(() => window.__guide.guide.snapshot), coordinateDelta: forward[1].world.map((n, axis) => n - before[1].world[axis]), reset: true });
  }
  // Fault controls prove the independent coordinate check detects 1000x units, wrong frame and doubled offsets.
  await visit('v1');
  const rejects = await page.evaluate(() => {
    const v = window.__viewer, guide = window.__guide.controller;
    const check = () => { const p = v.parts[1].mesh.position; return Math.abs(p.x) < 1e-9 && Math.abs(p.y) < 1e-9 && Math.abs(p.z - 25) < 1e-9; };
    const results = [];
    for (const offset of [[0, 0, 25000], [0, 25, 0], [0, 0, 50]]) { guide.applyStep('screws'); v.parts[1].mesh.position.fromArray(offset); results.push(!check()); }
    guide.applyStep('screws'); results.push(check()); return results;
  }); assert.deepEqual(rejects, [true, true, true, true]); cases.push({ wrongUnitFrameDoubleOffsetControls: rejects });
  // Legacy manifest path and API remain usable.
  await page.goto(`${site.url}/kit/viewer.html?manifest=/v1/view.json&explode=0.5&section=0.5`);
  await page.waitForFunction(() => document.body.dataset.ready === '1');
  assert.ok((await inspect()).some(p => p.offset.some(n => n !== 0))); await page.evaluate(() => window.__viewer.reset());
  assert.ok((await inspect()).every(p => p.offset.every(n => n === 0))); cases.push({ legacy: true });
  // Corrupted mesh or cancelled/late load never mounts a partial scene.
  await page.route('**/v1/1.stl', route => route.fulfill({ body: Buffer.from('wrong bytes') }));
  await page.goto(`${site.url}/kit/viewer.html?guide=/v1/guide.json`); await page.getByRole('button', { name: 'Retry model', exact: true }).waitFor();
  assert.equal(await page.locator('#app canvas').count(), 0); assert.match(await page.locator('#panel').innerText(), /SHA-256/);
  await page.unroute('**/v1/1.stl'); await page.getByRole('button', { name: 'Retry model', exact: true }).click(); await page.waitForFunction(() => document.body.dataset.ready === '1');
  const teardown = await page.evaluate(async () => {
    const v = window.__viewer; let geometries = 0, materials = 0;
    for (const p of v.parts) { p.mesh.geometry.addEventListener('dispose', () => geometries++); p.mesh.material.addEventListener('dispose', () => materials++); }
    v.dispose(); v.dispose(); let rejected = false; try { v.reset(); } catch { rejected = true; }
    const { createViewer } = await import('/kit/viewer.js'); const controller = new AbortController(); controller.abort();
    let cancelled = false; try { await createViewer({ app: document.querySelector('#app'), panel: document.querySelector('#panel'), manifestUrl: '/v1/view.json', signal: controller.signal }); } catch { cancelled = true; }
    return { geometries, materials, canvases: document.querySelectorAll('#app canvas').length, rejected, cancelled };
  }); assert.deepEqual(teardown, { geometries: 3, materials: 3, canvases: 0, rejected: true, cancelled: true }); cases.push({ teardown });
  for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
    await visit('v1', viewport); await page.getByRole('button', { name: 'Next', exact: true }).focus(); await page.keyboard.press('Enter');
    assert.equal(await page.getByLabel('Instruction step', { exact: true }).inputValue(), 'screws');
    assert.ok(await page.locator('#app canvas').isVisible());
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1); assert.equal(overflow, false);
    await page.screenshot({ path: `${out}/${engine.name()}-${viewport.width}.png` }); cases.push({ viewport, keyboard: true });
  }
  assert.deepEqual(errors, []);
  await writeFile(`${out}/${engine.name()}-report.json`, JSON.stringify({ passed: true, cases, errors }, null, 2));
  console.log(JSON.stringify({ passed: true, engine: engine.name(), cases: cases.length, out }));
} catch (error) {
  await writeFile(`${out}/${engine.name()}-failure.json`, JSON.stringify({ message: error.message, cases, errors }, null, 2)); throw error;
} finally { await browser?.close(); await site.close(); }
