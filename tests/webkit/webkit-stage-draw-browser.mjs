/** The shared 3D stage draws on demand (#822): no draws while idle, and no stale picture after any change.
 *
 * For each interaction that changes the picture, the check lets the stage settle in its on-demand mode, freezes its
 * frame loop, and compares the canvas on screen with the same frozen state drawn afresh, which is what drawing every
 * frame would show. A missed draw leaves the old picture on screen and fails the comparison; a planted missed draw
 * (the stage's next draw swallowed) proves the check reports one. Each check also requires the fresh picture after
 * the interaction to differ from the one before, so a check of an interaction that changed nothing cannot pass.
 * The idle check counts the frame loop's draws over two seconds with a model loaded (zero), with a planted control
 * (stageDiagnostics.alwaysDraw) that it must report. Off screen, a change draws nothing until the stage scrolls back,
 * which draws once.
 * Limits: Chromium or WebKit (PLAYWRIGHT_BROWSER) with whatever WebGL the runner has (software GL in CI), not devices;
 * a hidden tab is not exercised (browsers stop animation frames there); there is no 3D text, so no font arrival.
 */
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '../site/npm-context.mjs';
import { serveWebkit } from './webkit-server.mjs';

// Two boxes as binary STL parts, side by side, so explode, visibility and colour each show.
function boxSTL([x0, y0, z0], [sx, sy, sz]) {
  const v = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]].map(([a, b, c]) => [x0 + a * sx, y0 + b * sy, z0 + c * sz]);
  const faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]];
  const bytes = new Uint8Array(84 + faces.length * 50), view = new DataView(bytes.buffer);
  view.setUint32(80, faces.length, true);
  faces.forEach((face, i) => face.forEach((corner, j) => v[corner].forEach((n, k) => view.setFloat32(84 + i * 50 + 12 + j * 12 + k * 4, n, true))));
  return bytes;
}
const parts = [['left box', [0, 0, 0], [20, 30, 40], '#4bb9cc'], ['right box', [30, 0, 0], [20, 20, 25], '#d98b3a']];
const manifest = { parts: parts.map(([name, at, size, color]) => ({ name, file: `${name.replace(' ', '-')}.stl`, color, bounds_mm: [...at, ...at.map((n, i) => n + size[i])] })) };
const bare = `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stage draws</title>
<style>body{margin:0;background:#0b1018}#stage{width:100vw;height:70vh}#below{height:300vh}</style>
<script type="importmap">{"imports":{"three":"/kit/vendor/three/three.module.min.js","three/addons/":"/kit/vendor/three/addons/"}}</script>
<div id="stage"></div><div id="below"></div><script type="module">
import * as THREE from 'three';import {createStage,stageDiagnostics} from '/kit/model/stage.js';
window.THREE=THREE;window.stageDiagnostics=stageDiagnostics;
window.stage=createStage(document.querySelector('#stage'),{height:.05});
window.box=new THREE.Mesh(new THREE.BoxGeometry(.02,.03,.02),new THREE.MeshStandardMaterial({color:'#4bb9cc'}));
box.position.y=.015;box.castShadow=true;stage.root.add(box);stage.start();window.ready=true;
</script></html>`;
// A 2×2 PNG, red, decoded by the browser after the material already uses its texture.
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR42mP8z8DwnwEJMDGgAcYCBAEAWPEBBVXk0twAAAAASUVORK5CYII=', 'base64');
// The FEA viewer's synthetic one-triangle fixture (as in webkit-fea-browser.mjs): not a physical result.
const pack = (dtype, values) => ({ dtype, b64: Buffer.from(({ float32: Float32Array, uint32: Uint32Array, uint8: Uint8Array })[dtype].from(values).buffer).toString('base64') });
const fea = { format: 'cadagent-fea-viewer', name: 'Draw fixture', size_mm: 100, bounds_mm: [[0, 0, 0], [100, 20, 10]],
  material: { name: 'Illustrative', strength_mpa: 10 }, result: { safety_factor: 2 }, failure: { design_stress_mpa: 5, first_failure_factor: 2, max_load_factor: 3 },
  surface: { vertices: 3, triangles: 1, positions: pack('float32', [0, 0, 0, 100, 0, 0, 0, 20, 10]), index: pack('uint32', [0, 1, 2]),
    displacement: pack('float32', [0, 0, 0, 0, 0, -10, 0, 0, -5]), von_mises: pack('float32', [1, 5, 9]), tri_von_mises: pack('float32', [5]), flags: pack('uint8', [1, 0, 0]) },
  hot_spots: [{ position: [20, 5, 2.5], normal: [0, 0, 1], stress_mpa: 5, of_strength: .5, fails_at: 2, hint: 'Illustrative sample' }],
  assumptions: 'Synthetic rendering fixture, not a physical result.' };
const routes = new Map([
  ['/fea.json', (_, res) => res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify(fea))],
  ['/favicon.ico', (_, res) => res.writeHead(204).end()],
  ['/bare.html', (_, res) => res.writeHead(200, { 'Content-Type': 'text/html' }).end(bare)],
  ['/red.png', (_, res) => setTimeout(() => res.writeHead(200, { 'Content-Type': 'image/png' }).end(png), 300)],
  ['/m/view.json', (_, res) => res.end(JSON.stringify(manifest))],
  ['/block.stl', (_, res) => res.end(boxSTL([0, 0, 0], [10, 20, 30]))],
  ['/wide.stl', (_, res) => res.end(boxSTL([0, 0, 0], [60, 10, 15]))],
  ...parts.map(([name, at, size]) => [`/m/${name.replace(' ', '-')}.stl`, (_, res) => res.end(boxSTL(at, size))]),
]);
const site = await serveWebkit(routes);
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-stage-draw'; await mkdir(out, { recursive: true });
const cases = [], errors = [];

/** Run `fn(stage)` in the page, where `stage` is the stage that `which` names (a window path). */
const onStage = (page, which, fn, arg) => page.evaluate(([which, source, arg]) => {
  const stage = which.split('.').reduce((o, k) => o[k], window);
  return (0, eval)(`(${source})`)(stage, arg);
}, [which, fn.toString(), arg]);
/** Wait until the stage has run `quiet` frames in a row without drawing. */
async function settle(page, which, quiet = 20) {
  await page.waitForFunction(([which, quiet]) => {
    const stage = which.split('.').reduce((o, k) => o[k], window), s = (window.__settle ??= new Map()), last = s.get(stage);
    if (!last || last.draws !== stage.draws) { s.set(stage, { draws: stage.draws, frames: stage.frames }); return false; }
    return stage.frames - last.frames >= quiet;
  }, [which, quiet], { timeout: 120000, polling: 50 });
  await page.evaluate(() => window.__settle?.clear());
}
const canvasOf = (page, which) => onStage(page, which, stage => { stage.renderer.domElement.dataset.drawCheck = '1'; }).then(() => page.locator('canvas[data-draw-check="1"]'));
/** The canvas as on screen after settling, and the same frozen state drawn afresh. */
async function pictures(page, which) {
  await settle(page, which);
  const canvas = await canvasOf(page, which);
  await onStage(page, which, stage => { stage.stop(); });
  const shown = await canvas.screenshot();
  await onStage(page, which, stage => new Promise(done => { stage.renderer.render(stage.scene, stage.camera); requestAnimationFrame(() => requestAnimationFrame(done)); }));
  const fresh = await canvas.screenshot();
  await onStage(page, which, stage => { stage.start(); });
  await page.evaluate(() => document.querySelectorAll('[data-draw-check]').forEach(node => delete node.dataset.drawCheck));
  return { shown, fresh };
}
/** Throws if the picture on screen after `act` is stale, or if `act` changed nothing. */
async function check(page, which, name, act, { changes = true } = {}) {
  const before = await pictures(page, which);
  const draws = await onStage(page, which, stage => stage.draws);
  await act();
  const after = await pictures(page, which);
  const drew = await onStage(page, which, stage => stage.draws) - draws;
  if (changes && after.fresh.equals(before.fresh)) throw new Error(`${name}: the interaction did not change the picture, so the check proves nothing`);
  if (!after.shown.equals(after.fresh)) {
    await writeFile(`${out}/${engine.name()}-${name.replace(/\W+/g, '-')}-stale.png`, after.shown);
    await writeFile(`${out}/${engine.name()}-${name.replace(/\W+/g, '-')}-fresh.png`, after.fresh);
    throw new Error(`${name}: the stage shows a stale picture (${drew} draws after the interaction)`);
  }
  cases.push({ name, draws: drew });
}
/** Swallow the stage's next draw, as a missed invalidation would. */
const plantMissedDraw = (page, which) => onStage(page, which, stage => {
  const renderer = stage.renderer, render = renderer.render;
  renderer.render = function () { renderer.render = render; };
});
const idleDraws = (page, which, ms = 2000) => onStage(page, which, (stage, ms) => new Promise(done => {
  const start = stage.draws; setTimeout(() => done(stage.draws - start), ms);
}), ms);
const drag = async (page, which, dx, dy) => {
  const box = await (await canvasOf(page, which)).boundingBox(), x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 4 }); await page.mouse.move(x + dx, y + dy, { steps: 4 }); await page.mouse.up();
  await page.evaluate(() => document.querySelectorAll('[data-draw-check]').forEach(node => delete node.dataset.drawCheck));
};

try {
  const context = await browser.newContext({ viewport: { width: 900, height: 640 } });

  // Assembly viewer: camera, standard views, explode, assembly steps, section, selection, highlight, visibility,
  // colour, ghosting, light dimmer, palette, resize, device pixel ratio and reset.
  {
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${site.url}/kit/model/viewer.html?manifest=/m/view.json`);
    await page.waitForFunction(() => document.body.dataset.ready === '1');
    const V = '__viewer.stage';
    await settle(page, V);
    const idle = await idleDraws(page, V);
    assert.equal(idle, 0, `an idle assembly viewer drew ${idle} frames in 2 s`); cases.push({ idleAssemblyDraws: idle });
    await check(page, V, 'orbit drag and damping tail', () => drag(page, V, 60, 20));
    await check(page, V, 'wheel zoom', async () => { await page.mouse.wheel(0, 240); });
    await check(page, V, 'standard view button', () => page.getByRole('button', { name: 'TOP', exact: true }).click());
    await check(page, V, 'explode', () => page.evaluate(() => __viewer.setExplode(0.7)));
    await check(page, V, 'assembly step pose', () => page.evaluate(() => { const s = __viewer.getState(); __viewer.applyState({ ...s, offsets_mm: { 'right box': [0, 0, 25] }, highlight: ['right box'] }); }));
    await check(page, V, 'section cut', () => page.evaluate(() => __viewer.setSection(0.4)));
    await page.evaluate(() => __viewer.setSection(1));
    await check(page, V, 'selection', () => page.evaluate(() => __viewer.setSelection('left box')));
    await check(page, V, 'highlight', () => page.evaluate(() => { const s = __viewer.getState(); __viewer.applyState({ ...s, selected: null, highlight: ['left box'] }); }));
    await check(page, V, 'ghost mode', () => page.evaluate(() => { const s = __viewer.getState(); __viewer.applyState({ ...s, mode: 'ghost' }); }));
    await check(page, V, 'part visibility', () => page.getByRole('checkbox', { name: 'Show right box', exact: true }).uncheck());
    await check(page, V, 'part colour', () => page.getByLabel('Colour of left box', { exact: true }).fill('#ff00aa'));
    await check(page, V, 'light dimmer', () => page.evaluate(() => __viewer.stage.setSceneLight(0.3)));
    await check(page, V, 'stage palette', () => page.evaluate(() => __viewer.stage.setPalette({ accent: '#ff3300', grid: '#336600', glow: '#ffcc00', background: '#203040' })));
    await check(page, V, 'resize', () => page.setViewportSize({ width: 700, height: 560 }));
    if (engine === chromium) {
      const cdp = await context.newCDPSession(page);
      await check(page, V, 'device pixel ratio', () => cdp.send('Emulation.setDeviceMetricsOverride', { width: 700, height: 560, deviceScaleFactor: 2, mobile: false }), { changes: false });
      await cdp.send('Emulation.clearDeviceMetricsOverride'); await cdp.detach();
    }
    await check(page, V, 'reset', () => page.evaluate(() => __viewer.reset()));
    // Planted control: the same colour change with the stage's next draw swallowed must be reported as stale.
    const planted = await check(page, V, 'planted missed draw', async () => { await plantMissedDraw(page, V); await page.getByLabel('Colour of left box', { exact: true }).fill('#00ff44'); }).then(() => null, error => error.message);
    assert.match(planted ?? 'not reported', /stale picture/, 'a swallowed draw after a colour change must be reported'); cases.push({ plantedMissedDraw: 'reported' });
    // Planted control for the idle check: drawing every frame must be counted.
    const always = await page.evaluate(async () => { const { stageDiagnostics } = await import('/kit/model/stage.js'); stageDiagnostics.alwaysDraw = true; return stageDiagnostics.live.size; });
    assert.ok(always >= 1, 'the page and the test share the stage module');
    const forced = await idleDraws(page, V);
    await page.evaluate(async () => { (await import('/kit/model/stage.js')).stageDiagnostics.alwaysDraw = false; });
    assert.ok(forced > 3, `a stage drawing every frame must be reported by the idle check (${forced} draws)`); cases.push({ plantedAlwaysDraw: forced });
    await page.close();
  }

  // File viewer: model load, unit reinterpretation and theme.
  {
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${site.url}/kit/files/file-viewer.html?file=/block.stl&back=/parts`);
    await page.waitForFunction(() => window.__fileViewer?.root.dataset.state === 'ready');
    const F = '__fileViewer.stage';
    await settle(page, F);
    const idle = await idleDraws(page, F);
    assert.equal(idle, 0, `an idle file viewer drew ${idle} frames in 2 s`); cases.push({ idleFileViewerDraws: idle });
    await check(page, F, 'model load', async () => { await page.evaluate(() => window.__fileViewer.load('/wide.stl')); });
    await check(page, F, 'STL unit change', async () => { await page.getByLabel('STL units', { exact: true }).selectOption('inch'); await page.waitForFunction(() => window.__fileViewer.root.dataset.state === 'ready'); });
    await check(page, F, 'theme change', () => page.evaluate(() => window.__fileViewer.setTheme('light')));
    await page.close();
  }

  // Recorded replay: playback, seeking and a host view-state restore.
  {
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${site.url}/kit/simulation/viewer.html`);
    await page.waitForFunction(() => document.body.dataset.ready === '1');
    const R = '__replay.stage';
    await page.evaluate(() => { __replay.playback.pause(); __replay.playback.seek(0); });
    await settle(page, R);
    const idle = await idleDraws(page, R);
    assert.equal(idle, 0, `a paused replay drew ${idle} frames in 2 s`); cases.push({ idlePausedReplayDraws: idle });
    await check(page, R, 'seek', () => page.evaluate(() => __replay.playback.seek(__replay.playback.state().duration * 0.6)));
    await check(page, R, 'play then pause', async () => {
      await page.evaluate(() => __replay.playback.play());
      await page.waitForFunction(start => __replay.playback.state().time > start + 0.3, await page.evaluate(() => __replay.playback.state().time));
      await page.evaluate(() => __replay.playback.pause());
    });
    const saved = await page.evaluate(() => __replay.getViewState());
    await drag(page, R, -80, 0); await settle(page, R);
    await check(page, R, 'host view-state restore', () => page.evaluate(state => __replay.restoreViewState(state), saved));
    await page.close();
  }

  // FEA viewer: result field, deformation scale, section clip and load playback.
  {
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${site.url}/kit/fea/fea.html?case=/fea.json&nav=0&title=Draws`);
    await page.waitForFunction(() => window.__fea?.stage);
    const E = '__fea.stage';
    await page.evaluate(() => __fea.fit('top'));
    await settle(page, E);
    const idle = await idleDraws(page, E);
    assert.equal(idle, 0, `an idle FEA viewer drew ${idle} frames in 2 s`); cases.push({ idleFeaDraws: idle });
    await check(page, E, 'FEA result field', () => page.evaluate(() => __fea.setField('disp')));
    await check(page, E, 'FEA deformation scale', () => page.evaluate(() => __fea.setExaggeration(5)));
    await check(page, E, 'FEA section clip', () => page.evaluate(() => __fea.setClip('x', 0.5, false)));
    await check(page, E, 'FEA load playback', async () => { await page.evaluate(() => __fea.play(true)); await page.waitForTimeout(700); await page.evaluate(() => __fea.play(false)); });
    await page.close();
  }

  // A bare stage: texture arrival, and off-screen stages.
  {
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${site.url}/bare.html`); await page.waitForFunction(() => window.ready);
    const S = 'stage';
    await check(page, S, 'texture arrival', async () => {
      await page.evaluate(() => new Promise(done => { box.material.map = new THREE.TextureLoader().load('/red.png', () => done()); box.material.needsUpdate = true; }));
    });
    // Off screen: a change draws nothing; coming back draws once, and shows the change.
    await settle(page, S);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const away = await page.evaluate(async () => {
      await new Promise(done => setTimeout(done, 200));
      const draws = stage.draws, frames = stage.frames; box.material.color.set('#ffaa00'); box.rotation.y = 0.7;
      await new Promise(done => setTimeout(done, 1000));
      return { draws: stage.draws - draws, frames: stage.frames - frames };
    });
    assert.equal(away.draws, 0, 'an off-screen stage must not draw'); assert.ok(away.frames > 5, 'its frame loop keeps running');
    const back = await page.evaluate(async () => {
      const draws = stage.draws; window.scrollTo(0, 0);
      await new Promise(done => setTimeout(done, 1000));
      return stage.draws - draws;
    });
    assert.equal(back, 1, 'coming back on screen draws exactly once');
    const returned = await pictures(page, S);
    assert.ok(returned.shown.equals(returned.fresh), 'the returning draw shows the change made off screen');
    cases.push({ offScreen: { draws: away.draws, framesRun: away.frames }, backOnScreenDraws: back });
    // invalidate() is the documented request for a change the stage cannot see: it draws exactly once.
    await settle(page, S);
    const requested = await page.evaluate(async () => { const draws = stage.draws; stage.invalidate(); await new Promise(done => setTimeout(done, 600)); return stage.draws - draws; });
    assert.equal(requested, 1, 'invalidate() draws once'); cases.push({ invalidateDraws: requested });
    await page.close();
  }
  assert.deepEqual(errors, []);
  await writeFile(`${out}/${engine.name()}-stage-draw.json`, JSON.stringify({ passed: true, cases }, null, 2));
  console.log(JSON.stringify({ passed: true, engine: engine.name(), cases: cases.length, out }));
} finally { await browser.close(); await site.close(); }
