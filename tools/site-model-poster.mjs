/** Render each site model's still poster with the kit's own <cad-model> in headless Chrome: web/models/<name>.webp.
 *
 *   node tools/site-model-poster.mjs            # after tools/gyropup_showcase.py rewrites web/models/gyropup.json
 *
 * The poster is the element's first frame (its snapshot(), the model's own opening view), so the 3D view replaces it
 * without a jump. Square, 1200 px, WebP with transparency (the page's background shows through, as under the 3D
 * view). It serves this checkout's files as they are on disk. Software WebGL (SwiftShader) is fine.
 */
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const SIZE = 1200;
const MODELS = ['gyropup'];
const dir = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-poster-'));
await symlink(path.join(root, 'src/cadagent/webkit'), path.join(dir, 'kit'));
await symlink(path.join(root, 'web'), path.join(dir, 'web'));
await writeFile(path.join(dir, 'index.html'), '<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/kit/model.css">' +
  '<script type="module" src="/kit/model.js"></script><body style="margin:0"></body>');
const server = spawn(process.execPath, [path.join(root, 'tools/preview-site.mjs'), '--dir', dir, '--port', '0']);
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
try {
  const base = await new Promise((ok, fail) => {
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
    server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
  });
  const page = await browser.newPage({ viewport: { width: 700, height: 700 } });
  page.on('pageerror', e => { throw e; });
  await page.goto(base + '/', { waitUntil: 'load' });
  for (const name of MODELS) {
    const url = await page.evaluate(async ({ name, size }) => {
      document.body.replaceChildren();
      const el = Object.assign(document.createElement('cad-model'), { style: 'width:600px;aspect-ratio:1/1' });
      el.setAttribute('src', `/web/models/${name}.json`);
      el.setAttribute('loading', 'eager');
      el.setAttribute('turn', '0');
      document.body.append(el);
      await customElements.whenDefined('cad-model');
      await el.ready;
      if (el.dataset.state !== 'ready') throw new Error(`${name}: ${el.dataset.error}`);
      return el.snapshot(size, size, 'image/webp', 0.9);
    }, { name, size: SIZE });
    const bytes = Buffer.from(url.split(',')[1], 'base64');
    if (bytes.toString('latin1', 8, 12) !== 'WEBP') throw new Error(`${name}: the browser did not encode WebP`);
    await writeFile(path.join(root, 'web/models', `${name}.webp`), bytes);
    console.log(`web/models/${name}.webp: ${SIZE}x${SIZE}, ${bytes.length} bytes`);
  }
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}
