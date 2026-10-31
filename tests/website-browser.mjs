/** Load cad-agent.valpatel.com pages in a real browser, served the way Cloudflare Pages serves them (pretty URLs and
 * the _headers file, including the Content-Security-Policy), at phone and desktop widths.
 * Fails on console errors, CSP violations, failed or third-party requests, sideways scrolling, a phone header without
 * the catalogue link, a hero animation that is not running (or still running under reduced motion), a catalogue
 * filter that hides results without saying so, and a diagram wider than the article column at 1100 px (the narrowest
 * width with the page tree), so no reader has to scroll a diagram sideways on a desktop. */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium, webkit } from '@playwright/test';

const root = path.resolve(import.meta.dirname, '..');
const dir = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-website-browser-'));
execFileSync(process.execPath, ['tools/build-site.mjs', '--out', dir], { cwd: root, stdio: 'inherit' });
const server = spawn(process.execPath, ['tools/preview-site.mjs', '--dir', dir, '--port', '0'], { cwd: root });
const base = await new Promise((ok, fail) => {
  server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
  server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
});
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
const ROUTES = ['/', '/catalog', '/docs/compliant', '/docs/toolkit', '/README', '/research/landscape', '/agents/cad-resume',
  '/lessons/03-mechanical-design-rules', '/kit/file-viewer', '/missing-page'];
// /kit/viewer is the kit's project viewer: it needs a project's exports/view/view.json, so it is not a site page.
const problems = [];
try {
  for (const width of [360, 1366]) for (const route of ROUTES) {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    if (engine === chromium) await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    const page = await context.newPage();
    const seen = [];
    // A missing file shows up as an HTTP response below; the console's "status of 404" line repeats it, and on pages
    // without an icon link (the kit's) it is the browser's own /favicon.ico probe, which no page requested.
    page.on('console', m => { if (m.type() === 'error' && !/status of 404/.test(m.text())) seen.push(`console: ${m.text()}`); });
    page.on('pageerror', e => seen.push(`page error: ${e.message}`));
    page.on('requestfailed', r => seen.push(`failed: ${r.url()}`));
    page.on('response', r => { if (r.status() >= 400 && route !== '/missing-page') seen.push(`HTTP ${r.status()}: ${r.url()}`); });
    page.on('request', r => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) seen.push(`third party: ${r.url()}`); });
    await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
    const res = await page.goto(base + route, { waitUntil: 'networkidle' });
    if (route === '/missing-page') { if (res.status() !== 404) seen.push(`status ${res.status()}`); }
    else if (res.status() !== 200) seen.push(`status ${res.status()}`);
    if (route === '/README') await page.waitForSelector('.cad-diagram[data-state=ready] svg', { timeout: 15000 }).catch(() => seen.push('mermaid did not render'));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (overflow > 0) seen.push(`scrolls sideways by ${overflow}px`);
    if (!route.startsWith('/kit/')) {
      const visible = await page.locator('.site-header nav a[href="/catalog"]').isVisible();
      if (!visible) seen.push('no catalogue link in the header');
    }
    if (route === '/') {
      const names = await page.evaluate(() => document.getAnimations().map(a => a.animationName).filter(n => n?.startsWith('snap-')));
      if (names.length < 4) seen.push(`hero animations running: ${names.join(', ') || 'none'}`);
    }
    if (route === '/catalog' && width === 1366) {
      await page.fill('#q', 'zzzz-nothing-matches');
      if (!/No entries match/.test(await page.textContent('#filter-status'))) seen.push('empty filter result is not announced');
      await page.fill('#q', 'mit');
      const hits = await page.$$eval('.group .card:not([hidden])', cs => cs.map(c => c.dataset.text));
      if (!hits.length || hits.some(t => !/(^|[^\p{L}\p{N}])mit/u.test(t))) seen.push('"mit" matches inside other words');
    }
    if ((route === '/' || route === '/docs/toolkit') && width === 360) {   // copy buttons: one click, exact text
      const block = page.locator(route === '/' ? 'cad-copy.agent-copy' : '.prose cad-copy').first();
      const button = block.locator('.cad-copy-btn');
      if (!(await button.isVisible())) seen.push('no visible copy button');
      else {
        const box = await button.boundingBox();
        if (box.height < 24 || box.width < 44) seen.push(`copy button too small to tap (${box.width}x${box.height})`);
        await page.evaluate(() => { window.__copied = null; document.addEventListener('cad-copy', e => { window.__copied = e.detail; }); });
        await button.click();
        const detail = await page.waitForFunction(() => window.__copied, null, { timeout: 3000 }).then(h => h.jsonValue()).catch(() => null);
        const expected = await block.evaluate(el => el.querySelector('pre').textContent.replace(/\n$/, ''));
        if (!detail) seen.push('copy button did nothing');
        else {
          if (detail.text !== expected) seen.push('copy button copied different text than the block shows');
          if (detail.text.includes('Copy')) seen.push('copied text includes the button label');
          const state = await button.getAttribute('data-state');
          if (!(detail.ok ? state === 'copied' : state === 'manual')) seen.push(`copy button state ${state} after ok=${detail.ok}`);
          if (engine === chromium && !detail.ok) seen.push('clipboard write failed in Chromium');
          if (detail.ok && engine === chromium && (await page.evaluate(() => navigator.clipboard.readText())) !== expected) seen.push('clipboard holds other text');
        }
        // A label is text, never markup (other projects may put user text in it).
        const label = await page.evaluate(() => {
          const el = document.createElement('cad-copy');
          el.setAttribute('label', '<img src=x onerror="window.__xss=1">Copy');
          el.innerHTML = '<pre>x</pre>';
          document.body.append(el);
          const btn = el.querySelector('.cad-copy-btn');
          const r = { text: btn.textContent, img: !!btn.querySelector('img') };
          el.remove();
          return r;
        });
        if (label.img || !label.text.includes('<img')) seen.push('copy label is parsed as HTML');
      }
    }
    if (route === '/docs/toolkit') {                    // page tree: a column on wide screens, a toggle on phones
      const nav = page.locator('cad-nav');
      // Nothing jumps while the page loads: the tree is styled and folded from the first paint (kit/nav.css).
      const shift = await page.evaluate(() => new Promise(done => new PerformanceObserver((list, obs) => {
        obs.disconnect(); done(list.getEntries().filter(e => !e.hadRecentInput).reduce((s, e) => s + e.value, 0));
      }).observe({ type: 'layout-shift', buffered: true })).catch(() => 0));   // WebKit has no layout-shift entries
      if (shift > 0.05) seen.push(`layout shifts while loading: ${shift.toFixed(3)}`);
      if (width >= 1100) {
        await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight / 2); });
        await page.waitForTimeout(300);
        const box = await nav.locator('.cad-nav-panel').boundingBox();
        if (!box || box.y < 0 || box.y > 200) seen.push(`page tree is not in view after scrolling (y=${box?.y})`);
        if (!(await nav.locator('.cad-nav-outline a[aria-current=location]').count())) seen.push('outline does not mark the section being read');
        // The last sections can never reach the reading line; following their links must still mark them.
        const last = nav.locator('.cad-nav-outline a').last();
        await last.click();
        await page.waitForTimeout(400);
        if ((await last.getAttribute('aria-current')) !== 'location') seen.push('following the last outline link does not mark it');
        if (!(await nav.locator('.cad-nav-filter').isVisible())) seen.push('the filter is out of view');
        const filter = nav.locator('.cad-nav-filter');
        await filter.fill('zzzz-no-such-page');
        if (!/No pages match/.test(await nav.locator('.cad-nav-empty').textContent())) seen.push('filter with no match says nothing');
        await filter.press('Escape');
        const open = await nav.locator('details.cad-nav-group[open]').count();
        if (open !== 1) seen.push(`clearing the filter leaves ${open} groups open (was 1)`);
      } else {
        const toggle = nav.locator('.cad-nav-toggle');
        if (!(await toggle.isVisible())) seen.push('no Contents toggle on a narrow screen');
        else if (await nav.locator('.cad-nav-panel').isVisible()) seen.push('page tree is open before the toggle is pressed');
        else { await toggle.click(); if (!(await nav.locator('a[aria-current=page]').isVisible())) seen.push('toggle does not open the page tree'); }
      }
      // Keyboard users skip the header and the tree in one key press: after it, the next Tab is inside the article.
      await page.goto(base + route, { waitUntil: 'networkidle' });
      await page.keyboard.press('Tab');
      if ((await page.evaluate(() => document.activeElement?.className)) !== 'skip-link') seen.push('the first Tab stop is not "Skip to content"');
      await page.keyboard.press('Enter');
      await page.keyboard.press('Tab');
      if (!(await page.evaluate(() => !!document.activeElement?.closest('#content')))) seen.push('after "Skip to content", Tab does not land in the article');
      // A label is text, never markup (other projects may put user text in it).
      const injected = await page.evaluate(() => {
        const el = document.createElement('cad-nav');
        el.setAttribute('label', '<img src=x onerror="window.__xss=1">Pages');
        el.innerHTML = '<details class="cad-nav-group"><summary>x</summary><ul><li><a href="/">x</a></li></ul></details>';
        document.body.append(el);
        const r = !!el.querySelector('.cad-nav-toggle img');
        el.remove();
        return r;
      });
      if (injected) seen.push('nav label is parsed as HTML');
    }
    if (route === '/docs/compliant') {
      const href = await page.locator('.feedback a.button').getAttribute('href').catch(() => null);
      const u = href && new URL(href);
      if (!u || u.hostname !== 'github.com' || u.searchParams.get('template') !== 'feedback.yml' || !u.searchParams.get('page')?.endsWith('/docs/compliant'))
        seen.push(`feedback link does not open the prefilled form: ${href}`);
    }
    for (const s of seen) problems.push(`${width}px ${route}: ${s}`);
    await context.close();
  }
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + '/', { waitUntil: 'networkidle' });
  const still = await reduced.evaluate(() => document.getAnimations().filter(a => a.animationName?.startsWith('snap-')).length);
  if (still) problems.push(`reduced motion: ${still} hero animations still running`);
  await reduced.close();
  // Every page with a diagram, at the narrowest desktop width: each rendered diagram fits its column (#122).
  const diagramPages = [];
  for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
    const rel = path.relative(dir, path.join(e.parentPath, e.name));
    if (!e.isFile() || !rel.endsWith('.html') || rel.startsWith('kit')) continue;
    const sources = ((await readFile(path.join(dir, rel), 'utf8')).match(/class="language-mermaid"|<pre class="mermaid"/g) || []).length;
    if (sources) diagramPages.push(['/' + rel.replace(/\.html$/, '').split(path.sep).join('/'), sources]);
  }
  // Pages whose diagrams are being redrawn in an open PR. One that fits again fails the test, so it leaves this list.
  const KNOWN_WIDE = new Map([['/README', '#115 rewrites the README and its diagrams']]);
  // Headless Chrome hides scrollbars; a desktop browser with classic ones has up to 17px less, so keep that much spare.
  const SCROLLBAR = 17;
  const wide = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  for (const [route, sources] of diagramPages.sort()) {
    await wide.goto(base + route, { waitUntil: 'networkidle' });
    await wide.waitForFunction(n => document.querySelectorAll('.cad-diagram').length >= n &&
      [...document.querySelectorAll('.cad-diagram')].every(f => f.dataset.state === 'ready' || f.dataset.state === 'error'),
      sources, { timeout: 20000 }).catch(() => problems.push(`1100px ${route}: diagrams did not finish rendering`));
    const drawn = await wide.$$eval('.cad-diagram', fs => fs.filter(f => f.dataset.state === 'ready' && f.querySelector('svg')).length);
    if (drawn !== sources) problems.push(`1100px ${route}: ${drawn} of ${sources} diagrams rendered`);
    const over = (await wide.$$eval('.cad-diagram .cad-diagram-view', views => views.map(v => ({ over: v.scrollWidth - v.clientWidth, w: v.scrollWidth }))))
      .filter(d => d.over > 1 - SCROLLBAR);
    if (KNOWN_WIDE.has(route)) { if (!over.length) problems.push(`${route} now fits: remove it from KNOWN_WIDE`); continue; }
    for (const d of over) problems.push(`1100px ${route}: a diagram is ${d.w}px wide, ${d.over + SCROLLBAR}px wider than the column allows (top-down, at most three boxes per row)`);
  }
  await wide.close();
  // Very wide screens: the outline moves to its own column on the right and keeps marking the section being read.
  const wider = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  await wider.goto(base + '/docs/toolkit', { waitUntil: 'networkidle' });
  await wider.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight / 2); });
  await wider.waitForTimeout(300);
  if (!(await wider.locator('.doc-rail').isVisible())) problems.push('1600px: no "On this page" column');
  else if (!(await wider.locator('.doc-rail a[aria-current=location]').count())) problems.push('1600px: the right-hand outline does not mark the section');
  if (await wider.locator('cad-nav .cad-nav-outline').isVisible()) problems.push('1600px: the outline shows twice');
  await wider.close();
  assert.deepEqual(problems, []);
  console.log(`${engine.name()}: ${ROUTES.length} routes at 360 and 1366 px under the site CSP PASS`);
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}
