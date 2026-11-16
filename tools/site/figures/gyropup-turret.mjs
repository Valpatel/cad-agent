#!/usr/bin/env node
/** Record Gyropup's turret browser playground ("Turret on the Orin AGX box") from a clean local Gyropup checkout.
 *
 *     node tools/site/figures/gyropup-turret.mjs --gyropup <checkout> --executable <chromium>
 *     node tools/site/figures/gyropup-turret.mjs --check
 *
 * The checkout is only read: its published paths are served from their sources through its own
 * tools/site/source-layout.json, so nothing is built or written there. The page is Gyropup's software/site/designer/sim.html
 * at ?design=turret-box. The script holds ARM (Space) and FIRE (F), as a reader would, and screenshots the stage. Frames are
 * the playground's own WebGL canvas; each lasts the playground time it covers (the stage clamps a step to 50 ms). Pillow encodes a looping WebP and a separate finished still for
 * reduced motion. docs/img/gyropup/SOURCE.json records the Gyropup commit, this script's hash, the browser and the outputs.
 *
 * Limits: this is a browser playground of an unqualified work-in-progress prototype. Its ball flight is the playground's
 * own simplified model, not a physics validation, and the picture proves nothing about the hardware.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { chromium } from '@playwright/test';

const root = path.resolve(import.meta.dirname, '../../..');
const generator = 'tools/site/figures/gyropup-turret.mjs';
const outDir = 'docs/img/gyropup';
const ANIMATION = 'turret-playground.webp', STILL = 'turret-playground-still.webp';
const VIEWPORT = { width: 960, height: 600 }, SIZE = [720];
const FRAMES = 72, STRIDE = 2, QUALITY = 62, ORBIT = [-35, -4], ZOOM_AT = [300, 320], ZOOM_STEPS = 2;
const CROP = { x: 0.03, y: 0.18, w: 0.92, h: 0.77 };            // of the stage canvas: the turret and the range, not the empty sky
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const args = process.argv.slice(2);
const opt = name => { const i = args.indexOf(name); return i < 0 ? undefined : args[i + 1]; };

const sourcePath = path.join(root, outDir, 'SOURCE.json');
const source = JSON.parse(await readFile(sourcePath, 'utf8'));
if (args.includes('--check')) {
  const rec = source.pictures['turret-playground'];
  assert(rec, 'no turret-playground record in SOURCE.json');
  assert.equal(rec.generator.sha256, hash(await readFile(path.join(root, generator))), 'Recapture after generator changes');
  for (const f of [rec.file, rec.still.file]) assert.equal(hash(await readFile(path.join(root, outDir, f))), f === rec.file ? rec.sha256 : rec.still.sha256, `Changed picture: ${f}`);
  console.log('Turret playground animation and still match their record.');
  process.exit(0);
}
const gyropup = opt('--gyropup'), executablePath = opt('--executable');
assert(gyropup && executablePath, 'Use --gyropup <clean checkout> --executable <chromium>, or --check');
const G = path.resolve(gyropup);
const git = (...a) => execFileSync('git', a, { cwd: G }).toString().trim();
assert.equal(git('status', '--porcelain'), '', 'The Gyropup checkout must be clean');
const revision = git('rev-parse', 'HEAD'), committed = git('show', '-s', '--format=%cI', 'HEAD');

// Serve published paths from their sources, as Gyropup's own build maps them; nothing outside the checkout.
const layout = JSON.parse(await readFile(path.join(G, 'tools/site/source-layout.json'), 'utf8'));
const exact = new Map(layout.files.map(r => [r.public, r.source]));
const toSource = p => {
  if (exact.has(p)) return exact.get(p);
  for (const r of layout.prefixes) if (p === r.public || p.startsWith(r.public + '/')) return r.source + p.slice(r.public.length);
  return p;
};
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.wasm': 'application/wasm', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2' };
const served = new Map();
const server = http.createServer(async (req, res) => {
  const pub = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '');
  const file = path.resolve(G, toSource(pub));
  if (!file.startsWith(G + path.sep)) return res.writeHead(404).end();
  try {
    const bytes = await readFile(file);
    if (!served.has(path.relative(G, file))) served.set(path.relative(G, file), hash(bytes));
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(bytes);
  } catch { res.writeHead(404).end(); }   // site/nav.json and the dev-server change poll exist only in Gyropup's built site
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const tmp = await mkdtemp(path.join(os.tmpdir(), 'turret-'));
let browser;
try {
  browser = await chromium.launch({ executablePath, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1, colorScheme: 'light' });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', r => new URL(r.request().url()).origin === origin ? r.continue() : r.abort());
  await page.goto(origin + '/designer/sim.html?design=turret-box');
  await page.waitForFunction(() => document.getElementById('sim-startup')?.hidden && document.querySelector('.tb-fire'), null, { timeout: 120000 });
  await page.waitForTimeout(6000);                                   // models and textures settle in software WebGL
  await page.getByRole('button', { name: /hide panel/i }).click().catch(() => {});
  // A fixed camera, set once by a reader's own gestures: orbit to the turret's side so the barrel, hopper and targets
  // line up, then two wheel steps closer. The stage eases its camera over many frames, so each gesture gets time to settle.
  await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2); await page.mouse.down();
  for (let i = 1; i <= 10; i++) { await page.mouse.move(VIEWPORT.width / 2 + ORBIT[0] * i / 10, VIEWPORT.height / 2 + ORBIT[1] * i / 10); await page.waitForTimeout(150); }
  await page.mouse.up(); await page.waitForTimeout(6000);
  await page.mouse.move(...ZOOM_AT);
  for (let i = 0; i < ZOOM_STEPS; i++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(600); }
  await page.waitForTimeout(8000);
  await page.evaluate(() => document.activeElement?.blur());          // keys on a focused button are ignored by the bench
  await page.waitForTimeout(1500);
  const hopper = () => page.evaluate(() => document.querySelector('.tb-reload')?.innerText.replace(/\s+/g, ' '));
  const before = await hopper();
  // Capture the WebGL canvas itself on rendered frames (it keeps its drawing buffer): a Playwright screenshot of a busy
  // software-WebGL page takes tens of seconds. The stage clamps each step to 50 ms of playground time, so every capture
  // records the playground time it covers, and the WebP plays that back: real playground time, not wall time.
  await page.evaluate(({ stride, width, crop }) => {
    const canvas = document.querySelector('#app canvas'), small = document.createElement('canvas');
    const sx = crop.x * canvas.width, sy = crop.y * canvas.height, sw = crop.w * canvas.width, sh = crop.h * canvas.height;
    small.width = width; small.height = Math.round(width * sh / sw);
    const cap = window.__cap = { frames: [], ms: [], on: false, pending: 0, n: 0 };
    let last = performance.now();
    const loop = now => {
      const step = Math.min(now - last, 50); last = now;
      if (cap.on) {
        cap.pending += step;
        if (++cap.n % stride === 0) {
          small.getContext('2d').drawImage(canvas, sx, sy, sw, sh, 0, 0, small.width, small.height);
          cap.frames.push(small.toDataURL('image/png')); cap.ms.push(Math.round(cap.pending)); cap.pending = 0;
        }
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }, { stride: STRIDE, width: SIZE[0], crop: CROP });
  const until = n => page.waitForFunction(n => window.__cap.frames.length >= n, n, { timeout: 0, polling: 500 });
  await page.evaluate(() => { window.__cap.on = true; });
  await until(4);                                                    // safe and idle: the loop starts here
  await page.keyboard.down(' ');                                     // ARM: the hold-to-run safety line
  await until(12);                                                   // flywheels spin up
  await page.keyboard.down('f');                                     // FIRE held: automatic
  await until(FRAMES - 12);
  await page.keyboard.up('f'); await page.keyboard.up(' ');
  await until(FRAMES);                                               // the last balls fly; ARM released
  await page.evaluate(() => { window.__cap.on = false; });
  const after = await hopper();
  assert.notEqual(after, before, `nothing was fired (hopper ${before} -> ${after})`);
  const cap = await page.evaluate(() => ({ frames: window.__cap.frames, ms: window.__cap.ms }));
  const frames = [];
  for (const [i, url] of cap.frames.entries()) {
    const f = path.join(tmp, `f${String(i).padStart(3, '0')}.png`);
    await writeFile(f, Buffer.from(url.split(',')[1], 'base64')); frames.push(f);
  }
  const stillIndex = Math.round(12 + (FRAMES - 24) * 0.75), still = frames[stillIndex];
  assert.deepEqual(errors, [], 'the playground raised errors');
  const durations = cap.ms.map(ms => Math.max(20, ms));
  durations[0] = 700;                                                // hold the idle start
  // Pillow (the repo's own dependency) writes the animated WebP and the still.
  execFileSync('python3', ['-I', '-c', `
import json, sys
from PIL import Image
spec = json.loads(sys.argv[1])
ims = [Image.open(f).convert('RGB') for f in spec['frames']]
ims[0].save(spec['out'], save_all=True, append_images=ims[1:], duration=spec['durations'], loop=0, quality=spec['q'], method=6)
Image.open(spec['still']).convert('RGB').save(spec['stillOut'], quality=80, method=6)
`, JSON.stringify({ frames, durations, size: SIZE, q: QUALITY, still, out: path.join(root, outDir, ANIMATION), stillOut: path.join(root, outDir, STILL) })]);
  const anim = await readFile(path.join(root, outDir, ANIMATION)), stillBytes = await readFile(path.join(root, outDir, STILL));
  source.pictures['turret-playground'] = {
    file: ANIMATION,
    page: 'software/site/designer/sim.html?design=turret-box',
    public: 'https://gyropup.com/designer/sim?design=turret-box',
    project: 'Valpatel/gyropup', revision, committed,
    generator: { path: generator, sha256: hash(await readFile(path.join(root, generator))) },
    browser: { engine: 'chromium', version: browser.version(), webgl: 'SwiftShader (software)' },
    actions: 'hold ARM (Space), then hold FIRE (F) for automatic fire, then release both',
    frames: frames.length, width: SIZE[0], viewport: VIEWPORT, crop: CROP, camera: { orbit_drag_px: ORBIT, zoom_at_px: ZOOM_AT, zoom_steps: ZOOM_STEPS }, duration_ms: durations.reduce((a, b) => a + b, 0),
    timing: `each frame lasts the playground time it covers (${STRIDE} rendered steps of at most 50 ms each), not wall time`,
    sha256: hash(anim),
    still: { file: STILL, frame: stillIndex, sha256: hash(stillBytes) },
    served_sources: served.size,
    served_sources_sha256: hash(JSON.stringify([...served].sort())),
    limits: 'A browser playground of an unqualified work-in-progress prototype (the page says PLAYGROUND - WIP). Ball flight is the playground\'s simplified model, not physics validation; no hardware was tested.',
  };
  await writeFile(sourcePath, JSON.stringify(source, null, 1) + '\n');
  console.log(`Recorded ${frames.length} frames from Gyropup ${revision.slice(0, 7)}: ${anim.length} + ${stillBytes.length} bytes.`);
} finally {
  await browser?.close(); server.close(); await rm(tmp, { recursive: true, force: true });
}
