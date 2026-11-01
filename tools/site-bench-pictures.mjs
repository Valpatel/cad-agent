/** Pictures of the review site that `cad-agent site` builds for the gate bench, for the docs (#179):
 *
 *   node tools/site-bench-pictures.mjs        # needs Python with cadagent importable from src/ (no CAD kernel)
 *
 * The gate bench (tests/fixtures/gate_bench/) is the repo's own test assembly. Its committed site_snapshot/ holds the
 * exports of a clean `cad-agent gates --build` run (refresh them with tests/fixtures/gate_bench/site_snapshot.py), so
 * the review site builds here without CadQuery, exactly as tests/test_site_review.py builds it. This copies the bench
 * to a temporary folder, runs `cad-agent site` there and writes:
 *
 * - docs/img/gates/bench-connectivity.svg: the connectivity graph the site draws from exports/gates/connectivity.dot;
 * - docs/img/gates/bench-review.webp: the top of the site's gates page (its verdict table), 1440 px wide.
 */
import { chromium } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import { cp, copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const OUT = path.join(root, 'docs/img/gates');
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-bench-'));
const bench = path.join(tmp, 'gate_bench');
await cp(path.join(root, 'tests/fixtures/gate_bench'), bench, { recursive: true,
  filter: src => !/(__pycache__|site_snapshot|[/\\]exports|[/\\]site)$/.test(src) });
await cp(path.join(root, 'tests/fixtures/gate_bench/site_snapshot'), path.join(bench, 'project/exports'), { recursive: true });
const python = process.env.PYTHON || 'python3';
execFileSync(python, ['-m', 'cadagent.cli', 'site', '--project', path.join(bench, 'project')],
  { cwd: tmp, env: { ...process.env, PYTHONPATH: path.join(root, 'src') }, stdio: 'inherit' });
const site = path.join(bench, 'project/site');
await mkdir(OUT, { recursive: true });
const svg = await readFile(path.join(site, 'review/connectivity.svg'), 'utf8');
if (svg.includes(tmp) || /\/home\/|\/Users\//.test(svg)) throw new Error('the graph names a local path');
await copyFile(path.join(site, 'review/connectivity.svg'), path.join(OUT, 'bench-connectivity.svg'));
console.log(`docs/img/gates/bench-connectivity.svg: ${svg.length} bytes`);

const server = spawn(process.execPath, [path.join(root, 'tools/preview-site.mjs'), '--dir', site, '--port', '0']);
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
try {
  const base = await new Promise((ok, fail) => {
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
    server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await page.goto(base + '/review/gates', { waitUntil: 'networkidle' });
  const text = await page.textContent('body');
  if (text.includes(tmp)) throw new Error('the page names the temporary folder');
  // The site's header and its verdict table (the graph is the SVG above): down to the table's last row.
  const end = await page.evaluate(() => Math.ceil(document.querySelector('table').getBoundingClientRect().bottom + scrollY + 28));
  const shot = await page.screenshot({ type: 'png', fullPage: true, clip: { x: 0, y: 0, width: 1440, height: Math.min(end, 1500) } });
  // WebP, encoded by the browser itself (no image library needed)
  const webp = await page.evaluate(async png => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + png;
    await img.decode();
    const c = Object.assign(document.createElement('canvas'), { width: img.width, height: img.height });
    c.getContext('2d').drawImage(img, 0, 0);
    return c.toDataURL('image/webp', 0.86).split(',')[1];
  }, shot.toString('base64'));
  await writeFile(path.join(OUT, 'bench-review.webp'), Buffer.from(webp, 'base64'));
  console.log(`docs/img/gates/bench-review.webp: 1440 x ${Math.min(end, 1500)}`);
} finally {
  await browser.close();
  server.kill();
  await rm(tmp, { recursive: true, force: true });
}
