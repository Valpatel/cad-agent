/** Pictures of the web kit's components at work, for the docs (#179):
 *
 *   node tools/site-kit-pictures.mjs --gyropup <checkout of Valpatel/gyropup>
 *
 * Each picture is the kit itself (src/cadagent/webkit/), served as the site serves it, running on real files:
 *
 * - docs/img/kit/part-table.webp: kit/part-table.js and kit/part-tracker.js on the gate bench's parts (its committed
 *   run, tests/fixtures/gate_bench/site_snapshot/dossier-geometry.json, and its dossier cards), one row per part or
 *   screw entry in that record (19 rows for 26 parts: the eight balls are one), sorted by size; a cell the bench does
 *   not declare says so; nothing is marked ordered or printed;
 * - docs/img/kit/part-table-search.webp: the same table searched for "screw";
 * - docs/img/kit/file-viewer-step.webp: kit/file-viewer.html on one of Gyropup's STEP files (MIT; read from the
 *   checkout's git at the revision docs/img/gyropup/SOURCE.json records, never its working tree);
 * - docs/img/kit/file-viewer-front.webp: the same viewer after viewer.fit('front');
 * - docs/img/kit/file-viewer-theme.webp: the same viewer after setTheme() with the palette docs/file-viewer.md shows;
 * - docs/img/kit/file-viewer-error.webp: the viewer on a STEP file cut off halfway, as the validation's bad files are.
 *
 * Captured in Chrome (WebGL in software when there is no GPU) at the docs column's width and twice its density, so the
 * text reads at its own size on the page. A different browser or renderer can change the pixels, not what they show.
 */
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import YAML from 'yaml';

const root = path.resolve(import.meta.dirname, '..');
const kit = path.join(root, 'src/cadagent/webkit');
const OUT = path.join(root, 'docs/img/kit');
const DOCS_COLUMN = 860;              // CSS px: the docs page's article column (880) less its figure's padding and border
const arg = process.argv.indexOf('--gyropup');
if (arg < 0) throw new Error('usage: node tools/site-kit-pictures.mjs --gyropup <checkout of Valpatel/gyropup>');
const gyropup = path.resolve(process.argv[arg + 1]);
const source = JSON.parse(await readFile(path.join(root, 'docs/img/gyropup/SOURCE.json'), 'utf8'));
const PART = 'exports/asm_hip_motor_plate_l.step';                 // Gyropup's left hip motor plate
const step = execFileSync('git', ['-C', gyropup, 'show', `${source.revision}:${PART}`], { maxBuffer: 1 << 28 });

// The gate bench's parts, as its dossier and its committed geometry record them.
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const bench = path.join(root, 'tests/fixtures/gate_bench');
const geometry = JSON.parse(await readFile(path.join(bench, 'site_snapshot/dossier-geometry.json'), 'utf8'));
const cards = new Map();
for (const f of ['arm', 'bracket', 'frame', 'store']) {
  const sec = YAML.parse(await readFile(path.join(bench, `project/dossier/sections/${f}.yaml`), 'utf8'));
  for (const p of sec.parts || []) cards.set(p.id, { ...p, section: sec.id });
}
const rows = [];
for (const [id, part] of Object.entries(geometry.parts)) {
  const box = part.instances[0].bbox, size = box.max.map((v, i) => v - box.min[i]);
  const card = cards.get(id) || {};
  const material = card.material ? `${card.material.name}, ${card.material.process}` : 'not declared';
  rows.push({ id, section: part.section, what: card.function || 'not declared', material, size, count: part.count });
}
// Screws: the geometry record's fastener entries (no card, no section, no material); their words are its fields.
for (const [id, f] of Object.entries(geometry.fasteners))
  rows.push({ id, section: 'not declared', what: `M${f.diameter_mm} × ${f.length_mm} screw (${f.key}) into ${f.into}`, material: 'not declared', size: null, sizeText: `Ø${f.diameter_mm} × ${f.length_mm}`, count: f.count });
const mm = r => r.sizeText || r.size.map(v => +v.toFixed(1)).join(' × ');
const table = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/kit/vendor/fonts/fonts.css"><link rel="stylesheet" href="/kit/part-table.css">
<style>body{margin:0;padding:18px 20px;background:#fffdf5;color:#173d3c;font:14px/1.5 Inter,system-ui,sans-serif}table{width:100%}h1{font-size:20px;margin:0 0 12px}</style>
<main><h1>Gate bench parts</h1><div id="progress"></div><div class="cad-table-scroll"><table id="parts"><caption>Parts, from the bench's dossier and geometry record</caption>
<thead><tr><th data-sort="text">Part</th><th data-sort="text">Section</th><th data-sort="text">What it does</th><th data-sort="number">Size, mm</th><th data-sort="number">Count</th></tr></thead><tbody>
${rows.map(r => `<tr data-part-key="${esc(r.id)}" data-part-label="${esc(r.id)}"><td><b>${esc(r.id)}</b><br><small>${esc(r.material)}</small></td><td>${esc(r.section)}</td><td>${esc(r.what)}</td><td data-sort-value="${r.size ? r.size.reduce((a, b) => a * b, 1).toFixed(1) : ''}">${esc(mm(r))}</td><td data-sort-value="${r.count}">${r.count}</td></tr>`).join('\n')}
</tbody></table></div></main><script type="module">
import {createPartTracker} from '/kit/part-tracker.js';import {enhancePartTable,mountProgressTools} from '/kit/part-table.js';
const tracker=createPartTracker({project:'gate-bench'});mountProgressTools(document.getElementById('progress'),tracker);
enhancePartTable(document.getElementById('parts'),{tracker,statuses:[{id:'ordered',label:'Ordered'},{id:'printed',label:'Printed'}]});document.body.dataset.ready='true';
</script></html>`;

const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.wasm': 'application/wasm', '.woff2': 'font/woff2' };
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    if (url.pathname === '/parts') return res.writeHead(200, { 'Content-Type': 'text/html' }).end(table);
    if (url.pathname === '/' + path.basename(PART)) return res.writeHead(200, { 'Content-Type': 'application/octet-stream' }).end(step);
    if (url.pathname === '/truncated.step') return res.writeHead(200, { 'Content-Type': 'application/octet-stream' }).end(step.subarray(0, step.length >> 1));
    const target = path.resolve(kit, '.' + decodeURIComponent(url.pathname.replace(/^\/kit/, '')));
    if (!url.pathname.startsWith('/kit/') || !target.startsWith(kit + path.sep)) return res.writeHead(404).end();
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(target)] || 'application/octet-stream' }).end(await readFile(target));
  } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
});
await new Promise(ok => server.listen(0, '127.0.0.1', ok));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
await mkdir(OUT, { recursive: true });
const save = async (page, name, clip) => {
  const png = await page.screenshot({ type: 'png', ...(clip ? { clip } : {}) });
  const webp = await page.evaluate(async png => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + png;
    await img.decode();
    const c = Object.assign(document.createElement('canvas'), { width: img.width, height: img.height });
    c.getContext('2d').drawImage(img, 0, 0);
    return c.toDataURL('image/webp', 0.86).split(',')[1];
  }, png.toString('base64'));
  await writeFile(path.join(OUT, name), Buffer.from(webp, 'base64'));
  console.log(`docs/img/kit/${name}: ${Math.round(webp.length * 3 / 4 / 1024)} KB`);
};
try {
  const page = await browser.newPage({ viewport: { width: DOCS_COLUMN, height: 560 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // The part table, sorted by size (largest first), as a reader would sort it.
  await page.goto(base + '/parts');
  await page.waitForFunction(() => document.body.dataset.ready === 'true');
  await page.getByRole('button', { name: 'Size, mm: sort ascending', exact: true }).click();
  await page.getByRole('button', { name: 'Size, mm: sort descending', exact: true }).click();
  await page.evaluate(() => document.fonts.ready);
  const height = await page.evaluate(() => Math.ceil(document.querySelector('tbody tr:nth-child(8)').getBoundingClientRect().bottom + 2));
  await page.setViewportSize({ width: DOCS_COLUMN, height });
  await save(page, 'part-table.webp');
  await page.getByRole('searchbox').fill('screw');
  await page.waitForFunction(() => !/^19 of/.test(document.querySelector('.cad-table-count')?.textContent || '19 of'));
  console.log(`  searched "screw": ${await page.textContent('.cad-table-count')}`);
  await page.setViewportSize({ width: DOCS_COLUMN, height: await page.evaluate(() => Math.ceil(document.querySelector('table').getBoundingClientRect().bottom + 18)) });
  await save(page, 'part-table-search.webp');
  // The file viewer on the STEP file.
  await page.setViewportSize({ width: DOCS_COLUMN, height: 560 });
  const ready = state => page.waitForFunction(s => window.__fileViewer?.root.dataset.state === s, state, { timeout: 120000 });
  const settle = () => page.evaluate(() => new Promise(done => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(done)), 900)));
  await page.goto(base + '/kit/file-viewer.html?file=' + encodeURIComponent('/' + path.basename(PART)));
  await ready('ready');
  await settle();
  await save(page, 'file-viewer-step.webp');
  await page.evaluate(() => window.__fileViewer.fit('front'));
  await settle();
  await save(page, 'file-viewer-front.webp');
  await page.evaluate(() => window.__fileViewer.fit('iso'));
  await page.evaluate(() => window.__fileViewer.setTheme({ mode: 'light', colors: { accent: '#126d58', surface: '#fffaf2' }, fontFamily: 'Inter, system-ui, sans-serif' }));
  await settle();
  await save(page, 'file-viewer-theme.webp');
  // A STEP file cut off halfway: the viewer says what failed and offers Retry.
  await page.goto(base + '/kit/file-viewer.html?file=%2Ftruncated.step');
  await ready('error');
  await settle();
  await save(page, 'file-viewer-error.webp');
  if (errors.length) throw new Error(`page errors: ${errors.join('; ')}`);
} finally {
  await browser.close();
  server.close();
}
