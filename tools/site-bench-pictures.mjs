/** Pictures of the review site that `cad-agent site` builds for the gate bench, for the docs (#179):
 *
 *   node tools/site-bench-pictures.mjs        # needs Python with cadagent importable from src/ (no CAD kernel)
 *
 * The gate bench (tests/fixtures/gate_bench/) is the repo's own test assembly. Its committed site_snapshot/ holds the
 * exports of a clean `cad-agent gates --build` run (refresh them with tests/fixtures/gate_bench/site_snapshot.py), so
 * the review site builds here without CadQuery, exactly as tests/test_site_review.py builds it. This copies the bench
 * to a temporary folder, runs `cad-agent site` there and writes into docs/img/gates/:
 *
 * - bench-connectivity.svg: the connectivity graph the site draws from exports/gates/connectivity.dot;
 * - bench-sections.webp: the review's front page, its counts and the sections table;
 * - bench-review.webp: the gates page's verdict table;
 * - bench-requirements.webp: the requirements page, each requirement traced to a section and a gate;
 * - bench-section.webp: the arm section's page, from its purpose to its requirement;
 * - bench-section-interfaces.webp: the same page's interfaces and decisions;
 * - bench-part-card.webp: the same page's card for the arm part.
 *
 * Each crop is one part of a page, captured at the docs column's width (DOCS_COLUMN) at twice the pixel density, so
 * on the docs page its text is the size it is on the review site: readable on a desktop, and a tap away on a phone
 * (each figure links to its full-size picture). Everything after the crop's last element is hidden, so a crop never
 * ends partway through a line.
 */
import { chromium } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import { cp, copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const OUT = path.join(root, 'docs/img/gates');
const DOCS_COLUMN = 860;          // CSS px: the docs page's article column (880) less its figure's padding and border
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
  const page = await browser.newPage({ viewport: { width: DOCS_COLUMN, height: 900 }, deviceScaleFactor: 2 });
  // [file, route, first element, last element]: CSS selectors on the markup `cad-agent site` writes. The crop runs from
  // the first element's top to the last one's bottom.
  const SHOTS = [
    ['bench-sections.webp', '/review/', 'main > .stats', 'main > h2#sections + .tablewrap'],
    ['bench-review.webp', '/review/gates', 'main > h2#summary', 'main > h2#summary + .tablewrap'],
    ['bench-requirements.webp', '/review/requirements', 'main > p:first-child', 'main > .tablewrap + p'],
    ['bench-section.webp', '/review/section-s-arm', 'main > p:first-child', 'main > h2#requirements + .tablewrap'],
    ['bench-section-interfaces.webp', '/review/section-s-arm', 'main > h2#interfaces', 'main > h2#decisions + .dec'],
    ['bench-part-card.webp', '/review/section-s-arm', 'main > .partcard:has(#part-arm)', 'main > .partcard:has(#part-arm)'],
  ];
  for (const [name, route, first, last] of SHOTS) {
    await page.goto(base + route, { waitUntil: 'networkidle' });
    if ((await page.textContent('body')).includes(tmp)) throw new Error(`${route} names the temporary folder`);
    const box = await page.evaluate(([first, last]) => {
      const [a, z] = [first, last].map(s => document.querySelector(s));
      if (!a || !z) throw new Error(`no element ${a ? last : first}`);
      // Hide whatever comes after the crop (the next element would otherwise show its first line at the edge).
      for (const el of document.querySelectorAll('main *')) if (z.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING && !z.contains(el)) el.style.visibility = 'hidden';
      document.querySelector('footer')?.style.setProperty('visibility', 'hidden');
      const [ra, rz] = [a, z].map(e => e.getBoundingClientRect());
      return { top: Math.max(0, Math.floor(ra.top + scrollY - 16)), bottom: Math.ceil(rz.bottom + scrollY + 16) };
    }, [first, last]);
    const shot = await page.screenshot({ type: 'png', fullPage: true, clip: { x: 0, y: box.top, width: DOCS_COLUMN, height: box.bottom - box.top } });
    // WebP, encoded by the browser itself (no image library needed)
    const webp = await page.evaluate(async png => {
      const img = new Image();
      img.src = 'data:image/png;base64,' + png;
      await img.decode();
      const c = Object.assign(document.createElement('canvas'), { width: img.width, height: img.height });
      c.getContext('2d').drawImage(img, 0, 0);
      return c.toDataURL('image/webp', 0.86).split(',')[1];
    }, shot.toString('base64'));
    await writeFile(path.join(OUT, name), Buffer.from(webp, 'base64'));
    console.log(`docs/img/gates/${name}: ${DOCS_COLUMN * 2} x ${(box.bottom - box.top) * 2}, ${Math.round(webp.length * 3 / 4 / 1024)} KB`);
  }
} finally {
  await browser.close();
  server.kill();
  await rm(tmp, { recursive: true, force: true });
}
