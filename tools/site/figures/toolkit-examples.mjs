#!/usr/bin/env node
// Capture the toolkit cards' previews from the shipped viewers; the build-guide card shows the featured example.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { chromium } from '@playwright/test';

const root = path.resolve(import.meta.dirname, '../../..');
// The featured build guide (#811): Gyropup's authored turret order, converted by docs/examples/build-guide/.
// The synthetic rail bench stays a test fixture (tests/fixtures/assembly-plan/) and is not published.
const example = 'software/cadagent/webkit/assembly/examples/gyropup-turret';
const exampleRoute = '/kit/assembly/examples/gyropup-turret/guide.json';
const previewStep = 'step-11';          // barrel, hopper and lid arriving over the ghosted turret
const output = 'tools/site/assets/toolkit';
const generator = 'tools/site/figures/toolkit-examples.mjs';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const bytesAt = name => readFile(path.join(root, name));
const args = process.argv.slice(2), check = args.includes('--check');
const executableIndex = args.indexOf('--executable');
const executablePath = executableIndex < 0 ? undefined : args[executableIndex + 1];
assert(args.every((arg, i) => arg === '--check' || arg === '--chromium' || arg === '--executable' || i === executableIndex + 1 && executableIndex >= 0), 'Use --check, --chromium (installed Playwright Chromium), or --executable /path/to/chromium');
assert(check || Boolean(executablePath) !== args.includes('--chromium'), 'Capture requires exactly one explicit browser selection');
if (executableIndex >= 0) assert(executablePath && !executablePath.startsWith('--'), '--executable needs a browser path');

// The example is closed over its own bindings: guide -> view -> every mesh, and its receipt names every byte.
const guideBytes = await bytesAt(`${example}/guide.json`);
const guide = JSON.parse(guideBytes), receipt = JSON.parse(await bytesAt(`${example}/receipt.json`));
assert.equal(guide.snapshot.status, 'wip', 'The featured guide is a work-in-progress example');
assert.equal(guide.snapshot.source_commit, receipt.revision, 'Guide and receipt name the same source revision');
assert.match(guide.source?.qualification || '', /not a verified build procedure/, 'The guide states what it is not');
const view = JSON.parse(await bytesAt(`${example}/${guide.model.file}`));
// A packed model (cad-agent-model/1) binds every mesh through its one binary; an STL manifest binds each file.
const meshBindings = view.schema === 'cad-agent-model/1' ? [{ file: view.bin, sha256: view.sha256 }] : view.parts;
for (const binding of [guide.model, ...meshBindings]) assert.equal(hash(await bytesAt(`${example}/${binding.file}`)), binding.sha256, `Stale binding: ${binding.file}`);
for (const [name, expected] of Object.entries(receipt.artifacts)) assert.equal(hash(await bytesAt(`${example}/${name}`)), expected, `Stale example: ${name}`);
// What the preview shows: the guide and its model, not the converter's receipt (which also hashes the converter).
const featured = { path: example, route: exampleRoute, revision: receipt.revision, steps: guide.steps.length, parts: view.parts.length,
  guide: hash(guideBytes), view: guide.model.sha256 };
if (check) {
  const record = JSON.parse(await bytesAt(`${output}/SOURCE.json`));
  assert.deepEqual(record.featured, featured, 'Recapture after the featured example changes');
  assert.equal(record.generator.sha256, hash(await bytesAt(generator)), 'Recapture after generator changes');
  for (const capture of Object.values(record.captures)) {
    assert.equal(hash(await bytesAt(`${output}/${capture.file}`)), capture.sha256, 'Changed preview');
    for (const [name, expected] of Object.entries(capture.runtimeInputs)) assert.equal(hash(await bytesAt(name)), expected, `Recapture after runtime change: ${name}`);
  }
  console.log('Featured build guide closure and both source-bound previews match.');
  process.exit(0);
}

const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.stl': 'application/octet-stream' };
const served = new Map();
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const base = pathname.startsWith('/kit/') ? 'software/cadagent/webkit' : null;
    if (!base) { res.writeHead(404).end(); return; }
    const owner = path.join(root, base), target = path.resolve(owner, '.' + pathname.slice(4));
    if (!target.startsWith(owner + path.sep)) { res.writeHead(404).end(); return; }
    const bytes = await readFile(target);
    served.set(path.relative(root, target), hash(bytes));
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' }).end(bytes);
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch(executablePath ? { executablePath } : {});
  const context = await browser.newContext({ viewport: { width: 960, height: 640 }, deviceScaleFactor: 1, colorScheme: 'dark', reducedMotion: 'reduce' });
  const captures = {};
  for (const kind of ['assembly', 'file-review']) {
    served.clear();
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${new URL(response.url()).pathname}`); });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    const route = kind === 'assembly' ? `/kit/model/viewer.html?guide=${exampleRoute}` : '/kit/files/file-viewer.html?file=/kit/host/example.stl';
    await page.goto(origin + route);
    await page.waitForFunction(kind => kind === 'assembly' ? document.body.dataset.ready === '1' : window.__fileViewer?.root.dataset.state === 'ready', kind);
    if (kind === 'assembly') await page.getByRole('combobox', { name: 'Instruction step', exact: true }).selectOption(previewStep);
    else await page.evaluate(() => window.__fileViewer.fit('iso'));
    await page.evaluate(() => document.fonts.ready);
    const scene = await page.evaluate(async kind => {
      const viewer = kind === 'assembly' ? window.__viewer : window.__fileViewer, stage = viewer.stage;
      // Let the existing damped controls finish, then require identical camera state for consecutive painted frames.
      let previous = '', stable = 0;
      for (let i = 0; i < 180 && stable < 5; i++) {
        await new Promise(requestAnimationFrame);
        stage.controls.update(); stage.renderer.render(stage.scene, stage.camera);
        const current = [...stage.camera.position.toArray(), ...stage.controls.target.toArray()].map(n => n.toFixed(7)).join(',');
        stable = current === previous ? stable + 1 : 0; previous = current;
      }
      if (stable < 5 || stage.renderer.info.render.triangles < 1) throw new Error('Viewer has not painted a stable mesh scene');
      return { triangles: stage.renderer.info.render.triangles, camera: stage.camera.position.toArray(), target: stage.controls.target.toArray(), ...(kind === 'assembly' ? { parts: viewer.parts.map(part => part.name), instruction: window.__guide.controller.current, display: viewer.getState().mode } : { source: viewer.info.sourceName }) };
    }, kind);
    assert.deepEqual(errors, [], `Viewer failed: ${kind}`);
    if (kind === 'assembly') assert.deepEqual(scene.parts.slice().sort(), view.parts.map(part => part.name).sort());
    if (kind === 'assembly') assert.deepEqual([scene.instruction, scene.display], [previewStep, 'ghost']);
    const png = await page.screenshot({ type: 'png', animations: 'disabled' });
    // The turret preview has far more detail than the old rail bench; a lower quality keeps the home page's lazy card
    // within a small still of its former bytes (#811). The file-review preview keeps its quality and bytes.
    const quality = kind === 'assembly' ? .8 : .9;
    const encoded = await page.evaluate(async ([png, quality]) => {
      const image = new Image(); image.src = `data:image/png;base64,${png}`; await image.decode();
      const canvas = Object.assign(document.createElement('canvas'), { width: image.width, height: image.height });
      canvas.getContext('2d').drawImage(image, 0, 0);
      return canvas.toDataURL('image/webp', quality).split(',')[1];
    }, [png.toString('base64'), quality]);
    const bytes = Buffer.from(encoded, 'base64'), file = `${kind}.webp`;
    await writeFile(path.join(root, output, file), bytes);
    captures[kind] = { file, route, sha256: hash(bytes), bytes: bytes.length, webpQuality: quality, viewport: { width: 960, height: 640 }, deviceScaleFactor: 1, colorScheme: 'dark', reducedMotion: 'reduce', scene, runtimeInputs: Object.fromEntries([...served].sort(([a], [b]) => a.localeCompare(b))) };
    await page.close();
  }
  const receipt = {
    schema: 'cad-agent.toolkit-examples/1',
    scope: 'Actual viewer previews of the featured build guide and the original-file example; no physical or project qualification.',
    sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    generator: { path: generator, sha256: hash(await bytesAt(generator)) },
    browser: { engine: 'chromium', version: browser.version(), selection: executablePath ? `executable:${path.basename(executablePath)}` : 'installed-playwright-chromium' },
    featured, captures
  };
  await writeFile(path.join(root, output, 'SOURCE.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(`Wrote ${output}: 2 actual viewer previews; featured guide ${featured.revision.slice(0, 7)}.`);
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
