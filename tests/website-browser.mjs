/** Load cad-agent.valpatel.com pages in a real browser, served the way Cloudflare Pages serves them (pretty URLs and
 * the _headers file, including the Content-Security-Policy), at phone and desktop widths.
 * Fails on console errors, CSP violations, failed or third-party requests, sideways scrolling, a phone header without
 * the catalogue link, a hero animation that is not running (or still running under reduced motion), and a catalogue
 * filter that hides results without saying so. */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
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
  problems.push(...await cantileverProblems());          // the snap-arm explorer on /docs/compliant (#137), below
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
  assert.deepEqual(problems, []);
  console.log(`${engine.name()}: ${ROUTES.length} routes at 360 and 1366 px under the site CSP PASS`);
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}

/** The snap-arm explorer (the kit's <cad-cantilever>) on /docs/compliant, at phone and desktop widths, under the site
 * CSP: it replaces its still at exactly the reserved size (no layout shift), its panel never overflows, every control
 * has a label, the keyboard moves a slider and the strain follows, the print direction flips the verdict, it animates,
 * pauses on request and holds still under reduced motion, with no console errors. */
async function cantileverProblems() {
  const out = [];
  const beam = page => page.locator('cad-cantilever [data-part=beam]').getAttribute('points');
  for (const width of [360, 1366]) {
    const height = {};
    for (const script of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const seen = [], say = s => seen.push(s);
      page.on('console', m => { if (m.type() === 'error' && script) say(`console: ${m.text()}`); });   // without the script: its blocked load
      page.on('pageerror', e => say(`page error: ${e.message}`));
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
      if (!script) await page.route('**/kit/cantilever.js', r => r.abort());
      await page.goto(base + '/docs/compliant', { waitUntil: 'networkidle' });
      const demo = page.locator('cad-cantilever');
      await demo.scrollIntoViewIfNeeded();
      height[script] = (await demo.boundingBox())?.height;
      if (!script) {
        const img = await demo.locator(':scope > img').evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false);
        if (!img) say('no still image before the script loads');
      } else if (!(await demo.locator('svg [data-part=beam]').count())) say('the live figure did not render');
      else {
        const panel = await demo.locator('.cc-panel').evaluate(p => {
          const box = p.getBoundingClientRect();
          return { over: p.scrollHeight - p.clientHeight, out: [...p.querySelectorAll('*')].filter(n => n.getClientRects().length &&
            n.getBoundingClientRect().bottom > box.bottom + 0.5 && getComputedStyle(n).position !== 'absolute').length };
        });
        if (panel.over > 0 || panel.out) say(`the panel overflows (${panel.over}px, ${panel.out} elements)`);
        const unlabelled = await demo.evaluate(d => [...d.querySelectorAll('input, select')].filter(i => !i.labels?.length).map(i => i.name));
        if (unlabelled.length) say(`controls without a label: ${unlabelled.join(', ')}`);
        const before = await beam(page);                 // it starts once it is on screen (an IntersectionObserver)
        await page.waitForFunction(p => document.querySelector('cad-cantilever [data-part=beam]').getAttribute('points') !== p,
          before, { timeout: 3000 }).catch(() => say('the beam is not animating'));
        const strain = async () => parseFloat(await demo.locator('[data-out=strain]').textContent());
        const s0 = await strain();
        const slider = page.getByRole('slider', { name: /^Deflection at the hook/ });
        await slider.focus();
        for (let i = 0; i < 4; i++) await slider.press('ArrowRight');
        if (!((await strain()) > s0)) say(`the keyboard on the deflection slider did not raise the strain (${s0} → ${await strain()})`);
        if (!/millimetres$/.test(await slider.getAttribute('aria-valuetext') || '')) say('the slider has no spoken value');
        if ((await demo.locator('[data-out=verdict]').textContent()) !== 'PASS') say('the default arm does not pass flat on the bed');
        await page.getByLabel('Upright (across the layers)').check();
        if ((await demo.locator('[data-out=verdict]').textContent()) !== 'FAIL') say('printing the arm upright does not fail it');
        await demo.locator('.cc-play').click();
        const paused = await beam(page);
        await page.waitForTimeout(300);
        if ((await beam(page)) !== paused || (await demo.locator('.cc-play').textContent()) !== 'Play') say('the pause button does not stop it');
      }
      for (const s of seen) out.push(`${width}px /docs/compliant demo${script ? '' : ' (before its script)'}: ${s}`);
      await page.close();
    }
    if (!(Math.abs(height.true - height.false) < 0.5)) out.push(`${width}px demo: ${height.false}px tall before its script, ${height.true}px after`);
  }
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + '/docs/compliant', { waitUntil: 'networkidle' });
  const first = await beam(reduced);
  await reduced.waitForTimeout(500);
  if (!first || (await beam(reduced)) !== first || (await reduced.locator('cad-cantilever .cc-play').textContent()) !== 'Play')
    out.push('reduced motion: the demo is animating');
  await reduced.close();
  return out;
}
