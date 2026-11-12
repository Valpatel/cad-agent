/** Render each site model's still poster with the kit's own <cad-model> in headless Chrome: web/models/<name>.webp.
 *
 *   node tools/site/figures/site-model-poster.mjs            # after tools/gyropup_showcase.py rewrites web/models/gyropup.json
 *
 * The poster is the element's first frame (its snapshot(), the model's own opening view), so the 3D view replaces it
 * without a jump. Square, 1200 px, WebP with transparency (the page's background shows through, as under the 3D
 * view). It serves this checkout's files as they are on disk. Software WebGL (SwiftShader) is fine.
 *
 * Then docs/img/gyropup.jpg, the home page's Gyropup card: the same poster on a dark card with the project's words, in
 * the kit's own fonts (Inter, JetBrains Mono), 1600 x 733 JPEG. Its record (the model's Gyropup revision and how it was
 * made) is the "banner" entry of docs/img/gyropup/SOURCE.json; tools/gyropup_showcase.py keeps that entry.
 */
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../../..');
const SIZE = 1200;
const args = process.argv.slice(2);
if (args.length && !(args.length === 2 && args[0] === '--model' && ['gyropup','j501'].includes(args[1]))) throw new Error('Use --model gyropup or --model j501');
const MODELS = args.length ? [args[1]] : ['gyropup'];
const BANNER = { file: 'docs/img/gyropup.jpg', model: 'gyropup', width: 1600, height: 733, quality: 86 };
// The card's words are the project's own: Gyropup's README and gyropup.com (two five-bar legs on four RS-04s, the
// foam-ball turret, its print materials). Change them here when the project changes them.
const BANNER_HTML = `<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:Inter;src:url(/kit/vendor/fonts/inter.woff2) format('woff2');font-weight:100 900}
@font-face{font-family:'JetBrains Mono';src:url(/kit/vendor/fonts/jetbrains-mono.woff2) format('woff2');font-weight:100 800}
html,body{margin:0;width:${BANNER.width}px;height:${BANNER.height}px;overflow:hidden}
body{position:relative;background:radial-gradient(120% 140% at 70% 0%,#222c39 0%,#161d27 55%,#11161e 100%);font-family:Inter,sans-serif}
.floor{position:absolute;left:50px;right:-200px;top:430px;height:760px;border-radius:50%;
 background:repeating-radial-gradient(ellipse at 62% 30%,rgba(120,160,190,.05) 0 1px,transparent 1px 46px),#1a222c}
.words{position:absolute;left:100px;top:150px;color:#f2f5f8}
.eyebrow{font:500 22px 'JetBrains Mono',monospace;letter-spacing:.06em;color:#e8892b;margin:0 0 18px}
h1{font:800 104px/1 Inter,sans-serif;letter-spacing:-.02em;margin:0 0 30px}
.lede{font:400 29px/1.45 Inter,sans-serif;color:#c3cbd5;margin:0 0 30px}
.tag{font:500 22px 'JetBrains Mono',monospace;letter-spacing:.04em;color:#6fd3d8;margin:0}
img{position:absolute;left:700px;top:-10px;width:760px;height:760px}
</style><div class="floor"></div><div class="words"><p class="eyebrow">SELF-BALANCING &nbsp;·&nbsp; WHEEL-LEGGED</p><h1>Gyropup</h1>
<p class="lede">Two five-bar legs, four RS-04 actuators,<br>a foam-ball turret on top,<br>printed in PA6-CF, PETG and TPU.</p>
<p class="tag">DESIGNED · SIMULATED · CHECKED WITH CAD-AGENT</p></div><img alt="">`;
const dir = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-poster-'));
await symlink(path.join(root, 'software/cadagent/webkit'), path.join(dir, 'kit'));
await symlink(path.join(root, 'tools/site/assets'), path.join(dir, 'web'));
await writeFile(path.join(dir, 'index.html'), '<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/kit/model.css">' +
  '<script type="module" src="/kit/model.js"></script><body style="margin:0"></body>');
await writeFile(path.join(dir, 'banner.html'), BANNER_HTML);
const server = spawn(process.execPath, [path.join(root, 'tools/site/preview-site.mjs'), '--dir', dir, '--port', '0']);
let browser;
try {
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
  const base = await new Promise((ok, fail) => {
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
    server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
  });
  const page = await browser.newPage({ viewport: { width: 700, height: 700 } });
  page.on('pageerror', e => { throw e; });
  await page.goto(base + '/', { waitUntil: 'load' });
  const posters = {};
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
    await writeFile(path.join(root, 'tools/site/assets/models', `${name}.webp`), bytes);
    console.log(`web/models/${name}.webp: ${SIZE}x${SIZE}, ${bytes.length} bytes`);
    posters[name] = url;
    if (name === 'j501') {
      const file = path.join(root,'tools/site/assets/models/j501-source.json');
      const record = JSON.parse(await readFile(file,'utf8'));
      record.poster = {file:'tools/site/assets/models/j501.webp',sha256:createHash('sha256').update(bytes).digest('hex'),width:SIZE,height:SIZE,
        model_sha256:createHash('sha256').update(await readFile(path.join(root,'tools/site/assets/models/j501.json'))).digest('hex'),
        renderer_sha256:createHash('sha256').update(await readFile(path.join(root,'software/cadagent/webkit/model.js'))).digest('hex'),
        method:'shared cad-model snapshot at its recorded opening view, turn=0'};
      await writeFile(file,JSON.stringify(record,null,2)+'\n');
    }
  }
  if (MODELS.includes('gyropup')) {
  const card = await browser.newPage({ viewport: { width: BANNER.width, height: BANNER.height } });
  card.on('pageerror', e => { throw e; });
  await card.goto(base + '/banner.html', { waitUntil: 'load' });
  await card.evaluate(async url => {
    const img = document.querySelector('img');
    img.src = url;
    await img.decode();
    await document.fonts.ready;
    for (const family of ['Inter', 'JetBrains Mono'])
      if (![...document.fonts].some(f => f.family.replace(/"/g, '') === family && f.status === 'loaded')) throw new Error(`${family} did not load`);
  }, posters[BANNER.model]);
  const jpg = await card.screenshot({ type: 'jpeg', quality: BANNER.quality });
  await writeFile(path.join(root, BANNER.file), jpg);
  const model = JSON.parse(await readFile(path.join(root, 'tools/site/assets/models', `${BANNER.model}.json`), 'utf8'));
  const hash = bytes => createHash('sha256').update(bytes).digest('hex');
  const modelPath = `tools/site/assets/models/${BANNER.model}.json`;
  const posterPath = `tools/site/assets/models/${BANNER.model}.webp`;
  const binary = await readFile(path.join(root, 'tools/site/assets/models', model.bin));
  if (hash(binary) !== model.sha256) throw new Error('Model binary and source record disagree');
  const recordFile = path.join(root, 'docs/img/gyropup/SOURCE.json');
  const banner = { file: BANNER.file, made: 'node tools/site/figures/site-model-poster.mjs: the model\'s poster on a dark card with the project\'s words',
                  model: `web/models/${BANNER.model}.json`, revision: model.source.revision, width: BANNER.width, height: BANNER.height,
                  model_sha256: hash(await readFile(path.join(root, modelPath))), binary_sha256: model.sha256,
                  poster: posterPath, poster_sha256: hash(await readFile(path.join(root, posterPath))), sha256: hash(jpg) };
  // Spliced into the text tools/gyropup_showcase.py wrote, so its numbers keep Python's spelling (2.0 stays 2.0).
  const text = (await readFile(recordFile, 'utf8')).replace(/,\n "banner": \{[^}]*\}\n\}\n?$/, '\n}\n');
  if (!text.endsWith('\n}\n') || 'banner' in JSON.parse(text)) throw new Error(`${recordFile}: not the layout tools/gyropup_showcase.py writes (banner last)`);
  const spliced = text.slice(0, -3) + ',\n "banner": ' + JSON.stringify(banner, null, 1).replace(/\n/g, '\n ') + '\n}\n';
  JSON.parse(spliced);
  await writeFile(recordFile, spliced);
  console.log(`${BANNER.file}: ${BANNER.width}x${BANNER.height}, ${jpg.length} bytes (Gyropup ${model.source.revision.slice(0, 7)})`);
  }
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  if (server.exitCode === null && server.signalCode === null) await new Promise(resolve => server.once('exit',resolve));
  await rm(dir, { recursive: true, force: true });
}
