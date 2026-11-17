/** The top bar under `cad-agent site --serve`, on a real served project (#807). The Python server (serve_site, the code
 * behind `cad-agent site --serve`) serves a small project; Playwright opens its pages at 390 and 1366 px:
 * - the site's own pages (the bar in their markup, publish/site.py): at 390 px every link is a 44 px target and the bar
 *   does not scroll sideways (the phone rule it shares with ui/appnav.js);
 * - the kit's file viewer, with the server's injected bar and with its own (nav=1): the viewer starts at the bar's
 *   bottom, not a bar's height lower (the injected bar used to pad the body as well as the page's own has-appnav room);
 * - fea/fea.html?nav=0: no injected bar, and the server sent no injection;
 * - the kit pages' bar takes the kit theme's colours, light or dark with the reader's setting.
 * Planted controls: the site's bar without its phone rule, and the old double offset (the body padded on top of the
 * page's own room), must each be reported. Needs Python with cadagent's `site` extra (markdown). */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, copyFile, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, webkit } from '../site/npm-context.mjs';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const project = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-served-bar-'));
await writeFile(path.join(project, 'README.md'), '# Served bar fixture\n\nA project page under the served top bar.\n');
await copyFile(path.join(repo, 'software/cadagent/webkit/host/example.stl'), path.join(project, 'part.stl'));
const nav = [{ id: 'overview', title: 'Overview', href: 'site/' }, { id: 'model', title: 'Model', href: 'site/index.html#model' },
  { id: 'files', title: 'Files', href: '_cadagent/kit/files/file-viewer.html?file=/part.stl' }, { id: 'readme', title: 'Readme', href: 'README.md' }];
const server = spawn(process.env.PYTHON || 'python3', ['-c', `import sys, json
from pathlib import Path
from cadagent.publish.site import serve_site
server, url = serve_site(Path(sys.argv[1]), {"pages": ["README.md"], "nav": json.loads(sys.argv[2])}, "Served bar fixture")
print(url, flush=True)
server.serve_forever()`, project, JSON.stringify(nav)], { cwd: repo, stdio: ['ignore', 'pipe', 'inherit'],
  env: { ...process.env, PYTHONPATH: path.join(repo, 'software'), PYTHONDONTWRITEBYTECODE: '1' } });
const base = await new Promise((ok, fail) => {
  server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[^\s/]+/); if (m) ok(m[0]); });
  server.on('exit', c => fail(new Error(`serve_site exited ${c}`)));
  setTimeout(() => fail(new Error('serve_site printed no address in 60 s')), 60000).unref();   // never holds the run open
});
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
const VIEWER = '/_cadagent/kit/files/file-viewer.html?file=/part.stl';
const problems = [];

const open = async (route, width, colorScheme = 'light') => {
  const page = await browser.newPage({ viewport: { width, height: 800 }, colorScheme });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // A failed load is reported by its address (the browser's own favicon.ico request is not the page's), not by its
  // console line, which names no address.
  page.on('console', m => { if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(m.text()); });
  page.on('response', r => { const p = new URL(r.url()).pathname; if (r.status() >= 400 && p !== '/favicon.ico') errors.push(`${r.status()} ${p}`); });
  await page.goto(base + route);
  return { page, errors };
};
const bar = page => page.evaluate(() => {
  const nav = document.querySelector('nav.appnav');
  if (!nav) return null;
  const r = nav.getBoundingClientRect(), lum = c => { const [r, g, b] = c.match(/[\d.]+/g).map(Number); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
  return { bottom: r.bottom, inner: nav.scrollWidth - nav.clientWidth, injected: nav.dataset.injected === '1', themed: nav.classList.contains('themed'),
    light: lum(getComputedStyle(nav).backgroundColor) > 0.5, links: [...nav.querySelectorAll('a')].map(a => { const q = a.getBoundingClientRect(); return { h: q.height, w: q.width, right: q.right }; }) };
});
const phoneProblems = (b, what, width) => [
  ...(b.inner > 0 ? [`${what} ${width}px: the bar scrolls ${b.inner} px sideways inside itself`] : []),
  ...(b.links.some(l => l.h < 44 || l.w < 44) ? [`${what} ${width}px: bar links smaller than 44 px (${b.links.map(l => `${Math.round(l.w)}x${Math.round(l.h)}`).join(', ')})`] : []),
  ...(b.links.some(l => l.right > width + 0.5) ? [`${what} ${width}px: a bar link runs off the screen`] : []),
];

try {
  // The site's own pages: the bar in their markup, with the shared phone rule.
  for (const width of [360, 390]) {
    const { page, errors } = await open('/site/', width);
    try {
      const b = await bar(page);
      if (!b) problems.push(`/site/ ${width}px: no top bar`);
      else problems.push(...phoneProblems(b, '/site/', width));
      if (width === 390) {   // planted: the bar as it was before #807, without the phone rule
        await page.addStyleTag({ content: '.appnav .brand,.appnav a.tab{min-height:0!important;min-width:0!important;display:inline!important;padding:6px 10px!important}' });
        if (!phoneProblems(await bar(page), '/site/', width).length) problems.push('planted control: the site bar without its phone rule passed, so the phone check tests nothing');
      }
      if (errors.length) problems.push(`/site/ ${width}px: ${errors.join('; ')}`);
    } finally { await page.close(); }
  }
  // The kit's file viewer under the served bar: injected (no nav=1) and its own (nav=1).
  for (const [what, route, injected] of [['injected bar', VIEWER, true], ['own bar (nav=1)', VIEWER + '&nav=1', false]]) {
    for (const width of [390, 1366]) for (const colorScheme of ['light', 'dark']) {
      const { page, errors } = await open(route, width, colorScheme);
      try {
        await page.locator('nav.appnav').waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
        await page.waitForFunction(() => window.__fileViewer?.root.dataset.state === 'ready', null, { timeout: 30000 }).catch(() => {});
        const b = await bar(page), top = await page.evaluate(() => document.getElementById('file-viewer').getBoundingClientRect().top);
        const at = `file viewer, ${what}, ${width}px ${colorScheme}`;
        if (!b) { problems.push(`${at}: no top bar`); continue; }
        if (b.injected !== injected) problems.push(`${at}: the bar is ${b.injected ? '' : 'not '}the injected one`);
        if (Math.abs(top - b.bottom) > 1) problems.push(`${at}: the viewer starts at ${Math.round(top)} px, the bar ends at ${Math.round(b.bottom)} px`);
        if (!b.themed || b.light !== (colorScheme === 'light')) problems.push(`${at}: the bar is ${b.light ? 'light' : 'dark'}${b.themed ? '' : ' (not themed)'} on a ${colorScheme} page`);
        if (width === 390) problems.push(...phoneProblems(b, at, width));
        if (injected && width === 390 && colorScheme === 'light') {   // planted: the old double offset
          await page.evaluate(() => { document.body.style.paddingTop = '46px'; });
          const planted = await page.evaluate(() => document.getElementById('file-viewer').getBoundingClientRect().top);
          if (Math.abs(planted - b.bottom) <= 1) problems.push('planted control: a body padded under the page\'s own room passed, so the offset check tests nothing');
        }
        if (errors.length) problems.push(`${at}: ${errors.join('; ')}`);
      } finally { await page.close(); }
    }
  }
  // nav=0: the server sends no injection and no bar shows; without it the same page gets the injected script.
  for (const [query, wanted] of [['?nav=0', false], ['?nav=1', true]]) {
    const html = await (await fetch(base + '/_cadagent/kit/fea/fea.html' + query)).text();
    if (html.includes('injected: true') !== wanted) problems.push(`fea.html${query}: the server ${wanted ? 'did not inject' : 'injected'} the bar`);
  }
  {
    const { page } = await open('/_cadagent/kit/fea/fea.html?nav=0', 390);
    try {
      await page.waitForTimeout(1500);
      if (await page.locator('nav.appnav').count()) problems.push('fea.html?nav=0: a top bar shows');
    } finally { await page.close(); }
  }
  assert.deepEqual(problems, []);
  console.log(`${engine.name()}: served top bar (site pages, file viewer injected and own, nav=0, theme) at 360-1366 px PASS`);
} finally {
  await browser.close();
  server.kill();
  await rm(project, { recursive: true, force: true });
}
