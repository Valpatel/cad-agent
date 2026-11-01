/** Pictures of the pages `cad-agent compare` and `cad-agent optimise` write for the worked example, for the docs (#122):
 *
 *   node tools/site-explore-pictures.mjs        # needs Python with cadagent importable from src/ (no CAD kernel)
 *
 * The worked example (examples/explore-two-wheel/) compares four two-wheel-legged robot designs built from a small
 * catalogue of made-up parts. This copies it to a temporary folder and runs, there, exactly what its README runs:
 * `cad-agent catalogue`, `cad-agent compare --swaps` and `cad-agent optimise` (60 seeded random trials). Then it writes
 * crops of the two pages into docs/img/explore/:
 *
 * - compare-header.webp: the comparison page's header: what is minimised, maximised and required, and its caveat;
 * - long-range-checks.webp: the Long range design's card and the checks its evaluator wrote;
 * - long-range-bom.webp: the same card's bill of materials, each line with its basis;
 * - long-range-swaps.webp: the same card's one-part swaps;
 * - search-trade-off.webp: the search leaderboard's trade-off chart of the trials.
 *
 * The pages are dated from the example's last commit (SOURCE_DATE_EPOCH), as a rebuild of them is, so the same commit
 * gives the same pictures. Each crop is taken at CROP_WIDTH CSS px at twice the pixel density: wide enough that the
 * tables show every column, so on the docs column (860 px) its text is a little smaller than on the page itself.
 */
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { cp, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '..');
const OUT = path.join(root, 'docs/img/explore');
const EXAMPLE = 'examples/explore-two-wheel';
const CROP_WIDTH = 1100;
const epoch = execFileSync('git', ['log', '-1', '--format=%ct', '--', EXAMPLE], { cwd: root, encoding: 'utf8' }).trim();
if (!/^\d+$/.test(epoch)) throw new Error(`${EXAMPLE} has no commit to date the pages from`);
const tmp = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-explore-'));
const project = path.join(tmp, 'explore-two-wheel');
await cp(path.join(root, EXAMPLE), project, { recursive: true, filter: src => !/(__pycache__|[/\\]exports)$/.test(src) });
const python = process.env.PYTHON || 'python3';
const env = { ...process.env, PYTHONPATH: path.join(root, 'src'), SOURCE_DATE_EPOCH: epoch };
for (const args of [['catalogue'], ['compare', '--swaps'], ['optimise']])
  execFileSync(python, ['-m', 'cadagent.cli', ...args], { cwd: project, env, stdio: ['ignore', 'inherit', 'inherit'] });
const pages = { compare: path.join(project, 'exports/explore/compare.html'),
                search: path.join(project, 'exports/explore/search/leaderboard.html') };

// [file, page, first element, last element]: CSS selectors on the markup the two commands write. The crop runs from
// the first element's top to the last one's bottom; a closed card on the way is opened.
const SHOTS = [
  ['compare-header.webp', 'compare', '.wrap > header', '.wrap > header'],
  ['long-range-checks.webp', 'compare', '#d-long-range > summary', '#d-long-range > ul.checks'],
  ['long-range-bom.webp', 'compare', '#d-long-range > ul.checks + h3', '#d-long-range > .chips'],
  ['long-range-swaps.webp', 'compare', '#d-long-range > pre + h3', '#d-long-range > pre + h3 + p + .tablewrap'],
  ['search-trade-off.webp', 'search', 'h2#trade-off', 'h2#trade-off + .card'],
];
await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome' });
try {
  const page = await browser.newPage({ viewport: { width: CROP_WIDTH, height: 900 }, deviceScaleFactor: 2 });
  for (const [name, which, first, last] of SHOTS) {
    await page.goto(pathToFileURL(pages[which]).href, { waitUntil: 'load' });
    if ((await page.content()).includes(tmp)) throw new Error(`the ${which} page names the temporary folder`);
    const box = await page.evaluate(([first, last]) => {
      const [a, z] = [first, last].map(s => document.querySelector(s));
      if (!a || !z) throw new Error(`no element ${a ? last : first}`);
      for (const el of [a, z]) { const d = el.closest('details'); if (d) d.open = true; }
      // Hide whatever comes before or after the crop (a neighbour would otherwise show its edge in the padding).
      for (const el of document.querySelectorAll('.wrap *')) {
        const after = z.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING && !z.contains(el);
        const before = a.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING && !el.contains(a);
        if ((after || before) && !el.contains(z)) el.style.visibility = 'hidden';
      }
      const [ra, rz] = [a, z].map(e => e.getBoundingClientRect());
      return { top: Math.max(0, Math.floor(ra.top + scrollY - 16)), bottom: Math.ceil(rz.bottom + scrollY + 16) };
    }, [first, last]);
    const shot = await page.screenshot({ type: 'png', fullPage: true, clip: { x: 0, y: box.top, width: CROP_WIDTH, height: box.bottom - box.top } });
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
    console.log(`docs/img/explore/${name}: ${CROP_WIDTH * 2} x ${(box.bottom - box.top) * 2}, ${Math.round(webp.length * 3 / 4 / 1024)} KB`);
  }
} finally {
  await browser.close();
  await rm(tmp, { recursive: true, force: true });
}
