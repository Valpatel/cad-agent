/** Real extracted ZIP, pinned reader, 2 fixture releases + WIP; source tree removed. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir, mkdtemp, readFile, writeFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, webkit } from '../../site/npm-context.mjs';

const repo = fileURLToPath(new URL('../../../', import.meta.url));
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-assembly-release'; await mkdir(out, { recursive: true });
const work = await mkdtemp(path.join(out, 'fixture-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['tests/publish/assembly_release_fixture.py', '--out', work], {
  cwd: repo, encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: [path.join(repo, 'software'), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter) },
}));
const root = built.root, manifest = JSON.parse(await readFile(path.join(root, 'manifest.json')));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
for (const [name, expected] of Object.entries(manifest.files)) assert.equal(hash(await readFile(path.join(root, name))), expected, name);
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.wasm': 'application/wasm' };
const server = createServer(async (req, res) => {
  try {
    let file = path.resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://fixture/').pathname));
    if (file !== root && !file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    if ((await stat(file)).isDirectory()) file = path.join(file, 'index.html');
    res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
    res.setHeader('Cache-Control', 'no-store'); res.end(await readFile(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
let browser; const cases = [], errors = [], foreign = [];
try {
  browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
  const context = await browser.newContext({ viewport: { width: 1100, height: 800 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(base + '/') && !request.url().startsWith('data:')) foreign.push(request.url()); });
  for (const [index, entry] of manifest.assembly_guides.entries()) {
    await page.goto(base + '/' + entry.href);
    assert.match(await page.locator('main').innerText(), new RegExp(`Fixture ${entry.id}`));
    assert.equal(await page.locator('section img').count(), 2, 'Static no-script instructions retain both diagrams');
    const link = await page.getByRole('link', { name: 'Open interactive 3D instructions' }).getAttribute('href');
    assert.equal(new URL(link, page.url()).searchParams.get('sha256'), entry.sha256);
    await page.getByRole('link', { name: 'Open interactive 3D instructions' }).click();
    await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 20000 });
    assert.equal(await page.locator('canvas').count(), 1);
    const before = await page.evaluate(() => window.__viewer.parts.map(p => ({ visible: p.mesh.visible, position: p.mesh.position.toArray() })));
    assert.deepEqual(before.map(p => p.visible), [true, false, false]);
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    const after = await page.evaluate(async () => {
      const THREE = await import(new URL('./vendor/three/three.module.min.js', location.href).href);
      const v = window.__viewer; v.stage.root.updateMatrixWorld(true);
      return v.parts.map(p => ({ visible: p.mesh.visible, position: p.mesh.position.toArray(), world: p.mesh.getWorldPosition(new THREE.Vector3()).toArray(), opacity: p.mesh.material.opacity }));
    });
    assert.deepEqual(after.map(p => p.visible), [true, true, true]);
    assert.deepEqual(after[1].position, [0, 0, 25 + index * 5]);
    assert.equal(after[0].opacity, 0.2);
    await page.getByLabel('Instruction display', { exact: true }).selectOption('wireframe');
    assert.ok(await page.evaluate(() => window.__viewer.parts.every(p => p.mesh.material.wireframe)));
    await page.getByRole('button', { name: 'Assembled', exact: true }).click();
    assert.ok(await page.evaluate(() => window.__viewer.parts.every(p => p.mesh.position.lengthSq() === 0 && !p.mesh.material.wireframe)));
    await page.screenshot({ path: path.join(out, `${engine.name()}-extracted-${entry.id}.png`) });
    await page.getByRole('link', { name: 'Build guide', exact: true }).click();
    assert.equal(new URL(page.url()).pathname, '/' + entry.href);
    cases.push({ snapshot: entry.id, staticDiagrams: 2, exactEntryHash: true, realReader: true, noSourceFallback: true });
  }
  // Deliberately valid changed prose with the same model must fail the entry binding.
  const first = manifest.assembly_guides[0], file = path.join(root, first.guide);
  const original = await readFile(file), changed = JSON.parse(original); changed.steps[0].text += ' altered after packaging';
  await writeFile(file, JSON.stringify(changed));
  await page.goto(base + '/' + first.href); await page.getByRole('link', { name: 'Open interactive 3D instructions' }).click();
  await page.getByRole('button', { name: 'Retry model', exact: true }).waitFor();
  assert.equal(await page.locator('body').getAttribute('data-ready'), '0');
  assert.match(await page.getByRole('status').innerText(), /hash|SHA|digest/i);
  assert.equal(await page.locator('canvas').count(), 0);
  await writeFile(file, original);
  cases.push({ corruptGuideProseRejectedBeforeScene: true });
  const modelFile = path.join(path.dirname(file), 'view.json');
  for (const [name, asset] of [['model', modelFile], ['mesh', path.join(path.dirname(file), 'mesh-1.stl')]]) {
    const bytes = await readFile(asset); await writeFile(asset, 'corrupted after packaging');
    await page.goto(base + '/' + first.href); await page.getByRole('link', { name: 'Open interactive 3D instructions' }).click();
    await page.getByRole('button', { name: 'Retry model', exact: true }).waitFor();
    assert.equal(await page.locator('body').getAttribute('data-ready'), '0');
    assert.equal(await page.locator('canvas').count(), 0);
    assert.match(await page.getByRole('status').innerText(), /hash|SHA|digest/i);
    await writeFile(asset, bytes); cases.push({ corruptedDependencyRejectedBeforeScene: name });
  }
  const scriptless = await browser.newContext({ javaScriptEnabled: false });
  const plain = await scriptless.newPage(); await plain.goto(base + '/' + first.href);
  assert.match(await plain.locator('main').innerText(), /fit both screws/);
  assert.ok(await plain.locator('section img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)));
  await scriptless.close(); cases.push({ noScriptStaticFallback: true });
  assert.deepEqual(foreign, [], 'No source tree, current site, CDN or external runtime requests');
  assert.deepEqual(errors, []);
  await context.close();
  await writeFile(path.join(out, `${engine.name()}-result.json`), JSON.stringify({ engine: engine.name(), root, cases, errors, foreign }, null, 2));
  console.log(JSON.stringify({ engine: engine.name(), cases: cases.length, errors: errors.length, foreign: foreign.length }));
} finally {
  await browser?.close();
  server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
}
