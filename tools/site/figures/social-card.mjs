/** Draw the site's link card and touch icon from its own assets, in headless Chrome (#804):
 *
 *   node tools/site/figures/social-card.mjs            # draw both and rewrite their record
 *   node tools/site/figures/social-card.mjs --check    # no browser: the record still matches the inputs and the files
 *
 * - web/social-card.png, 1200 x 630: the picture every page's og:image and twitter:card name (the size the build checks,
 *   tools/site/compiler/site-checks.mjs). The project emblem (web/icon.svg), the name, what it is in the home page's
 *   own words, and the home page's Gyropup poster (web/models/gyropup.webp, drawn by site-model-poster.mjs), in the
 *   kit's own fonts (Inter, JetBrains Mono) and the light theme's colours.
 * - web/apple-touch-icon.png, 180 x 180: the emblem, full bleed on the page colour (iOS rounds the corners itself).
 *
 * The record (web/social-card-source.json) names every input with its SHA-256, the browser that drew the pictures and
 * the pictures' own hashes. A redraw with another browser version can differ in anti-aliasing; --check says when an input
 * changed, so the pictures are drawn again rather than edited by hand. Words change here, with the home page's. */
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../../..');
const ASSETS = 'tools/site/assets';
const GENERATOR = 'tools/site/figures/social-card.mjs';
const RECORD = `${ASSETS}/social-card-source.json`;
const INPUTS = [GENERATOR, `${ASSETS}/icon.svg`, `${ASSETS}/models/gyropup.webp`,
  'software/cadagent/webkit/vendor/fonts/inter.woff2', 'software/cadagent/webkit/vendor/fonts/jetbrains-mono.woff2'];
const OUTPUTS = { card: { file: `${ASSETS}/social-card.png`, width: 1200, height: 630 },
  icon: { file: `${ASSETS}/apple-touch-icon.png`, width: 180, height: 180 } };
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const at = f => path.join(root, f);
const args = process.argv.slice(2);
if (args.some(a => a !== '--check')) throw new Error('Use no arguments to draw, or --check');

const inputs = Object.fromEntries(await Promise.all(INPUTS.map(async f => [f, hash(await readFile(at(f)))])));
if (args.includes('--check')) {
  const record = JSON.parse(await readFile(at(RECORD), 'utf8'));
  const problems = [];
  for (const [f, h] of Object.entries(inputs)) if (record.inputs[f] !== h) problems.push(`${f} changed since the pictures were drawn`);
  for (const f of Object.keys(record.inputs)) if (!(f in inputs)) problems.push(`${f} is no longer an input`);
  for (const [k, o] of Object.entries(OUTPUTS)) {
    const r = record.outputs[k];
    if (!r || r.file !== o.file || r.width !== o.width || r.height !== o.height) problems.push(`${o.file}: the record does not describe it`);
    else if (hash(await readFile(at(o.file))) !== r.sha256) problems.push(`${o.file} is not the picture the record names`);
  }
  if (problems.length) { console.error(`${problems.join('\n')}\nDraw again: node ${GENERATOR}`); process.exit(1); }
  console.log('The link card and touch icon match their record.');
  process.exit(0);
}

const FONTS = `@font-face{font-family:Inter;src:url(/kit/vendor/fonts/inter.woff2) format('woff2');font-weight:100 900}
@font-face{font-family:'JetBrains Mono';src:url(/kit/vendor/fonts/jetbrains-mono.woff2) format('woff2');font-weight:100 800}`;
// The light theme's tokens (software/cadagent/webkit/ui/theme.css): page, ink, muted text, line, orange, sky.
const CARD_HTML = `<!doctype html><meta charset="utf-8"><style>${FONTS}
html,body{margin:0;width:1200px;height:630px;overflow:hidden}
body{position:relative;background:#fffbf3;font-family:Inter,sans-serif;color:#1d2350}
.grid{position:absolute;inset:0;background-image:linear-gradient(#ebe4d4 1px,transparent 1px),linear-gradient(90deg,#ebe4d4 1px,transparent 1px);
 background-size:42px 42px;background-position:-1px -1px;opacity:.55;-webkit-mask-image:linear-gradient(90deg,transparent 0,#000 55%)}
.sky{position:absolute;right:-120px;top:-60px;width:760px;height:760px;border-radius:50%;background:radial-gradient(circle at 45% 45%,#e4f4ff 0,#b5dcfb 62%,#e4f4ff 63%,transparent 64%)}
.model{position:absolute;right:-6px;top:28px;width:600px;height:600px}
.words{position:absolute;left:72px;top:58px;width:620px}
.mark{display:flex;align-items:center;gap:18px;font:850 74px/1 Inter,sans-serif;letter-spacing:-3px}
.mark img{width:84px;height:84px}.mark b{color:#b43c0b;margin-left:-14px}
.eyebrow{margin:36px 0 14px;font:600 19px 'JetBrains Mono',monospace;letter-spacing:.08em;color:#b43c0b}
h1{margin:0;font:800 44px/1.12 Inter,sans-serif;letter-spacing:-1.2px}
.lede{margin:18px 0 0;font:400 21px/1.45 Inter,sans-serif;color:#4a5172;width:540px}
.url{position:absolute;left:72px;bottom:40px;margin:0;font:600 21px 'JetBrains Mono',monospace;color:#173f68;letter-spacing:.02em}
.url span{display:inline-block;padding:9px 16px;border:2px solid #1d2350;border-radius:999px;background:#fffbf3}
</style><div class="grid"></div><div class="sky"></div><img class="model" src="/web/models/gyropup.webp" alt="">
<div class="words"><div class="mark"><img src="/web/icon.svg" alt="">cad-agent<b>.</b></div>
<p class="eyebrow">OPEN SOURCE · MIT · MACHINES BUILDING MACHINES</p>
<h1>CAD libraries, simulators, checks and tools for agents</h1>
<p class="lede">Deterministic checks, web widgets and a command line, with knowledge and an agent kit on top.</p></div>
<p class="url"><span>cad-agent.valpatel.com</span></p>`;
const ICON_HTML = `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:180px;height:180px;overflow:hidden;background:#fffbf3}
img{display:block;width:180px;height:180px}</style><img src="/web/icon.svg" alt="">`;

const dir = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-card-'));
await symlink(at('software/cadagent/webkit'), path.join(dir, 'kit'));
await symlink(at(ASSETS), path.join(dir, 'web'));
await writeFile(path.join(dir, 'card.html'), CARD_HTML);
await writeFile(path.join(dir, 'icon.html'), ICON_HTML);
const server = spawn(process.execPath, [at('tools/site/preview-site.mjs'), '--dir', dir, '--port', '0']);
let browser;
try {
  const base = await new Promise((ok, fail) => {
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
    server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
  });
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
  const outputs = {};
  for (const [kind, o] of Object.entries(OUTPUTS)) {
    const page = await browser.newPage({ viewport: { width: o.width, height: o.height }, deviceScaleFactor: 1, reducedMotion: 'reduce', colorScheme: 'light' });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
    await page.goto(`${base}/${kind}.html`, { waitUntil: 'load' });
    await page.evaluate(async () => {
      await Promise.all([...document.images].map(i => i.decode()));
      await document.fonts.ready;
    });
    if (kind === 'card') {
      const loaded = await page.evaluate(() => ['Inter', 'JetBrains Mono'].filter(f => ![...document.fonts].some(x => x.family.replace(/"/g, '') === f && x.status === 'loaded')));
      if (loaded.length) errors.push(`fonts did not load: ${loaded.join(', ')}`);
      // The words' ink (not their boxes) inside the card and clear of the model, which starts at about 760 px.
      const spill = await page.evaluate(() => [...document.querySelectorAll('.words > *, .url span')].filter(e => {
        const range = document.createRange(); range.selectNodeContents(e);
        const r = range.getBoundingClientRect(); return r.right > 740 || r.bottom > 630 || r.left < 0 || r.top < 0;
      }).map(e => e.className || e.localName));
      if (spill.length) errors.push(`words outside their column: ${spill.join(', ')}`);
      const gap = await page.evaluate(() => document.querySelector('.url span').getBoundingClientRect().top - document.querySelector('.lede').getBoundingClientRect().bottom);
      if (gap < 24) errors.push(`the address is ${gap.toFixed(0)} px under the words, not 24`);
    }
    if (errors.length) throw new Error(`${kind}: ${errors.join('; ')}`);
    const png = await page.screenshot({ type: 'png', animations: 'disabled' });
    await writeFile(at(o.file), png);
    outputs[kind] = { ...o, sha256: hash(png), bytes: png.length };
    await page.close();
    console.log(`${o.file}: ${o.width}x${o.height}, ${png.length} bytes`);
  }
  const record = { schema: 'cad-agent.social-card/1',
    made: `node ${GENERATOR}: the link card and touch icon, drawn in headless Chrome from the site's own emblem, fonts and model poster`,
    scope: 'A picture for shared links and home-screen icons; it shows the project, not a result.',
    browser: browser.version(), inputs, outputs };
  await writeFile(at(RECORD), JSON.stringify(record, null, 2) + '\n');
} finally {
  await browser?.close();
  server.kill('SIGTERM');
  await rm(dir, { recursive: true, force: true });
}
