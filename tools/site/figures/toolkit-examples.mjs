#!/usr/bin/env node
// Publish the existing synthetic guide closure; capture only the actual shipped viewers.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { chromium } from '@playwright/test';

const root = path.resolve(import.meta.dirname, '../../..');
const source = 'tests/fixtures/assembly-plan';
const output = 'tools/site/assets/toolkit';
const generator = 'tools/site/figures/toolkit-examples.mjs';
const names = ['guide.json', 'view.json', 'plan.json', 'base.stl', 'rail.stl', 'plate.stl', 'fastener.stl', 'lid.stl'];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const bytesAt = name => readFile(path.join(root, name));
const args = process.argv.slice(2), check = args.includes('--check');
const executableIndex = args.indexOf('--executable');
const executablePath = executableIndex < 0 ? undefined : args[executableIndex + 1];
assert(args.every((arg, i) => arg === '--check' || arg === '--chromium' || arg === '--executable' || i === executableIndex + 1 && executableIndex >= 0), 'Use --check, --chromium (installed Playwright Chromium), or --executable /path/to/chromium');
assert(check || Boolean(executablePath) !== args.includes('--chromium'), 'Capture requires exactly one explicit browser selection');
if (executableIndex >= 0) assert(executablePath && !executablePath.startsWith('--'), '--executable needs a browser path');

const inputs = new Map(await Promise.all(names.map(async name => [name, await bytesAt(`${source}/${name}`)])));
const guide = JSON.parse(inputs.get('guide.json')), view = JSON.parse(inputs.get('view.json')), plan = JSON.parse(inputs.get('plan.json'));
assert.equal(guide.snapshot.source_commit, '1'.repeat(40), 'Keep the synthetic fixture identity explicit');
assert.equal(plan.source.revision, guide.snapshot.source_commit);
for (const binding of [guide.model, guide.assembly_plan, ...view.parts]) {
  assert(inputs.has(binding.file), `Bundle is not closed: ${binding.file}`);
  assert.equal(hash(inputs.get(binding.file)), binding.sha256, `Stale binding: ${binding.file}`);
}
const copies = Object.fromEntries([...inputs].map(([name, bytes]) => [name, { source: `${source}/${name}`, sha256: hash(bytes), bytes: bytes.length }]));
if (check) {
  const receipt = JSON.parse(await bytesAt(`${output}/SOURCE.json`));
  assert.deepEqual(receipt.copies, copies);
  assert.equal(receipt.generator.sha256, hash(await bytesAt(generator)), 'Recapture after generator changes');
  for (const [name, bytes] of inputs) assert.deepEqual(await bytesAt(`${output}/assembly/${name}`), bytes, `Changed bundle: ${name}`);
  for (const capture of Object.values(receipt.captures)) {
    assert.equal(hash(await bytesAt(`${output}/${capture.file}`)), capture.sha256, 'Changed preview');
    for (const [name, expected] of Object.entries(capture.runtimeInputs)) assert.equal(hash(await bytesAt(name)), expected, `Recapture after runtime change: ${name}`);
  }
  console.log('Toolkit example closure and both source-bound previews match.');
  process.exit(0);
}

await mkdir(path.join(root, output, 'assembly'), { recursive: true });
for (const [name, bytes] of inputs) await writeFile(path.join(root, output, 'assembly', name), bytes);
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.stl': 'application/octet-stream' };
const served = new Map();
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const base = pathname.startsWith('/kit/') ? 'software/cadagent/webkit' : pathname.startsWith('/web/') ? 'tools/site/assets' : null;
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
    const route = kind === 'assembly' ? '/kit/model/viewer.html?guide=/web/toolkit/assembly/guide.json' : '/kit/files/file-viewer.html?file=/kit/host/example.stl';
    await page.goto(origin + route);
    await page.waitForFunction(kind => kind === 'assembly' ? document.body.dataset.ready === '1' : window.__fileViewer?.root.dataset.state === 'ready', kind);
    if (kind === 'assembly') await page.getByRole('combobox', { name: 'Instruction display', exact: true }).selectOption('solid');
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
    if (kind === 'assembly') assert.deepEqual(scene.parts.slice().sort(), ['base', 'fastener', 'lid', 'plate', 'rail']);
    const png = await page.screenshot({ type: 'png', animations: 'disabled' });
    const encoded = await page.evaluate(async png => {
      const image = new Image(); image.src = `data:image/png;base64,${png}`; await image.decode();
      const canvas = Object.assign(document.createElement('canvas'), { width: image.width, height: image.height });
      canvas.getContext('2d').drawImage(image, 0, 0);
      return canvas.toDataURL('image/webp', .9).split(',')[1];
    }, png.toString('base64'));
    const bytes = Buffer.from(encoded, 'base64'), file = `${kind}.webp`;
    await writeFile(path.join(root, output, file), bytes);
    captures[kind] = { file, route, sha256: hash(bytes), bytes: bytes.length, viewport: { width: 960, height: 640 }, deviceScaleFactor: 1, colorScheme: 'dark', reducedMotion: 'reduce', scene, runtimeInputs: Object.fromEntries([...served].sort(([a], [b]) => a.localeCompare(b))) };
    await page.close();
  }
  const receipt = {
    schema: 'cad-agent.toolkit-examples/1',
    scope: 'Actual viewer previews and byte-identical synthetic assembly fixture; no physical or project qualification.',
    sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    fixtureRevision: guide.snapshot.source_commit,
    generator: { path: generator, sha256: hash(await bytesAt(generator)) },
    browser: { engine: 'chromium', version: browser.version(), selection: executablePath ? `executable:${path.basename(executablePath)}` : 'installed-playwright-chromium' },
    copies, captures
  };
  await writeFile(path.join(root, output, 'SOURCE.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(`Wrote ${output}: 8 unchanged fixture inputs and 2 actual viewer previews.`);
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
