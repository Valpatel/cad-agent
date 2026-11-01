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
  '/lessons/mechanical/design-rules', '/kit/file-viewer', '/missing-page'];
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
    if (route === '/docs/toolkit') {                    // page tree: a column on wide screens, a toggle on phones
      const nav = page.locator('cad-nav');
      // Nothing jumps while the page loads: the tree is styled and folded from the first paint (kit/nav.css).
      // Settles in every engine: no shift at all is the goal, not a hang, and WebKit has no layout-shift entries.
      const shift = await page.evaluate(() => new Promise(done => {
        if (!PerformanceObserver.supportedEntryTypes?.includes('layout-shift')) return done(0);
        let sum = 0;
        new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) sum += e.value; })
          .observe({ type: 'layout-shift', buffered: true });
        setTimeout(() => done(sum), 200);
      }));
      if (shift > 0.05) seen.push(`layout shifts while loading: ${shift.toFixed(3)}`);
      if (width >= 1100) {
        await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight / 2); });
        await page.waitForTimeout(300);
        const box = await nav.locator('.cad-nav-panel').boundingBox();
        if (!box || box.y < 0 || box.y > 200) seen.push(`page tree is not in view after scrolling (y=${box?.y})`);
        if (!(await nav.locator('.cad-nav-outline a[aria-current=location]').count())) seen.push('outline does not mark the section being read');
        // The marked entry stays in view inside the panel (the outline sits under the tree, below the panel's fold), even
        // when the reader had scrolled the panel back to its top.
        await nav.locator('.cad-nav-panel').evaluate(p => { p.scrollTop = 0; });
        await page.evaluate(() => scrollTo(0, document.body.scrollHeight * 0.85));
        await page.waitForTimeout(300);
        const inView = await nav.locator('.cad-nav-panel').evaluate(p => {
          const a = p.querySelector('.cad-nav-outline a[aria-current=location]'), b = p.getBoundingClientRect(), r = a?.getBoundingClientRect();
          return !!r && r.top >= b.top && r.bottom <= b.bottom;
        });
        if (!inView) seen.push('the marked outline entry is out of the panel\'s view');
        // The last sections can never reach the reading line; following their links, with the site's smooth scrolling,
        // must still mark them once the scroll settles. Scrolling on releases the mark to the reading line.
        await page.evaluate(() => { document.documentElement.style.scrollBehavior = ''; scrollTo({ top: 0, behavior: 'instant' }); });
        const links = nav.locator('.cad-nav-outline a');
        // Until the page has not moved for 15 frames (a smooth scroll down a long page takes seconds).
        const settle = () => page.evaluate(() => new Promise(done => {
          let last = -1, still = 0;
          const tick = () => { if (scrollY === last) { if (++still > 15) return done(); } else { still = 0; last = scrollY; } requestAnimationFrame(tick); };
          tick(); setTimeout(done, 10000);
        }));
        for (const link of [links.nth((await links.count()) - 2), links.last()]) {
          await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
          await link.click();
          await settle();
          if ((await link.getAttribute('aria-current')) !== 'location') seen.push(`following "${await link.textContent()}" (smooth scroll) does not mark it`);
        }
        // A jump marks its heading until the reader scrolls on: jump to a middle heading, then scroll back until it sits
        // near the bottom of the window (still on screen, below the reading line). The section above is now being read.
        const middle = links.nth(Math.floor((await links.count()) / 2));
        await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; });   // an instant jump
        await middle.click();
        await settle();
        const id = decodeURIComponent((await middle.getAttribute('href')).slice(1));
        const back = await page.evaluate(i => innerHeight - 60 - document.getElementById(i).getBoundingClientRect().top, id);
        await page.mouse.move(700, 400);
        await page.mouse.wheel(0, -back);
        await settle();
        if ((await middle.getAttribute('aria-current')) === 'location') seen.push(`"${await middle.textContent()}" stays marked after the reader scrolls back`);
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
      if (!(await page.evaluate(() => !!document.activeElement?.closest('#main\\:content')))) seen.push('after "Skip to content", Tab does not land in the article');
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
      // A bare tree (plain <details>, no kit classes) filters too, and says nothing when a page matches.
      const bare = await page.evaluate(() => {
        const el = document.createElement('cad-nav');
        el.innerHTML = '<details open><summary>G</summary><ul><li><a href="/a">Alpha page</a></li><li><a href="/b">Beta page</a></li></ul></details>';
        document.body.append(el);
        const input = el.querySelector('.cad-nav-filter');
        input.value = 'alpha'; input.dispatchEvent(new Event('input'));
        const r = { hidden: [...el.querySelectorAll('li')].filter(li => li.hidden).length, empty: el.querySelector('.cad-nav-empty').textContent };
        el.remove();
        return r;
      });
      if (bare.hidden !== 1 || bare.empty) seen.push(`a bare tree does not filter: ${JSON.stringify(bare)}`);
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
  const KNOWN_WIDE = new Map();
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
    // The drawing's own width against the room inside its view (scrollWidth is never below clientWidth, so it cannot
    // show how much spare there is).
    // A view without a drawing failed to render; the count above reports it.
    const over = (await wide.$$eval('.cad-diagram .cad-diagram-view', views => views.filter(v => v.querySelector('svg')).map(v => {
      const cs = getComputedStyle(v), room = v.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      return { w: Math.ceil(v.querySelector('svg').getBoundingClientRect().width), room };
    }))).filter(d => d.w > d.room - SCROLLBAR + 1);
    if (KNOWN_WIDE.has(route)) { if (!over.length) problems.push(`${route} now fits: remove it from KNOWN_WIDE`); continue; }
    for (const d of over) problems.push(`1100px ${route}: a diagram is ${d.w}px wide; the column has ${d.room}px, less ${SCROLLBAR}px for a scrollbar (top-down, at most three boxes per row)`);
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
  // A big screen, where several last sections cannot reach the reading line: each outline link followed with the
  // site's smooth scrolling marks its own section once the scroll settles (#123 review: 21 of 59 were wrong).
  const big = await browser.newPage({ viewport: { width: 2560, height: 1440 } });
  await big.goto(base + '/docs/explore', { waitUntil: 'networkidle' });
  const rail = big.locator('.doc-rail a');
  const n = await rail.count();
  for (let i = Math.max(0, n - 4); i < n; i++) {
    await big.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    await rail.nth(i).click();
    await big.evaluate(() => new Promise(done => {
      let last = -1, still = 0;
      const tick = () => { if (scrollY === last) { if (++still > 15) return done(); } else { still = 0; last = scrollY; } requestAnimationFrame(tick); };
      tick(); setTimeout(done, 10000);
    }));
    const marked = await big.locator('.doc-rail a[aria-current=location]').allTextContents();
    const want = await rail.nth(i).textContent();
    if (marked.join() !== want) problems.push(`2560px /docs/explore: following "${want}" marks "${marked.join()}"`);
  }
  // Typing in the filter does not move the page, so it must not release a jump (the space used to). Jump to a section
  // that cannot reach the reading line and is not the last: released, the mark would fall to the last one on screen.
  for (const i of [n - 2, n - 3]) {
    await big.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    await rail.nth(i).click();
    await big.evaluate(() => new Promise(done => {
      let last = -1, still = 0;
      const tick = () => { if (scrollY === last) { if (++still > 15) return done(); } else { still = 0; last = scrollY; } requestAnimationFrame(tick); };
      tick(); setTimeout(done, 10000);
    }));
    const kept = await rail.nth(i).textContent();
    await big.locator('.cad-nav-filter').fill('');
    await big.locator('.cad-nav-filter').pressSequentially('vi e');
    await big.waitForTimeout(150);
    const after = await big.locator('.doc-rail a[aria-current=location]').allTextContents();
    if (after.join() !== kept) problems.push(`2560px /docs/explore: typing in the filter moved the mark from "${kept}" to "${after}"`);
    await big.locator('.cad-nav-filter').press('Escape');
  }
  await big.close();
  // The same jumps through the tree's own outline, in a window tall enough that several sections cannot reach the
  // reading line (review 3: at 1366x900 only the last one cannot, and the bottom rule marks it anyway).
  const tall = await browser.newPage({ viewport: { width: 1366, height: 1600 } });
  await tall.goto(base + '/docs/explore', { waitUntil: 'networkidle' });
  const unreachable = await tall.evaluate(() => {
    const line = Math.min(innerHeight / 3, 220), max = document.documentElement.scrollHeight - innerHeight;
    return [...document.querySelectorAll('cad-nav .cad-nav-outline a')].map((a, i) => [i, document.getElementById(decodeURIComponent(a.hash.slice(1)))])
      .filter(([, h]) => h && h.getBoundingClientRect().top + scrollY - line > max).map(([i]) => i);
  });
  if (unreachable.length < 2) problems.push(`1366x1600 /docs/explore: only ${unreachable.length} section(s) cannot reach the reading line; pick a page where several cannot`);
  const outline = tall.locator('cad-nav .cad-nav-outline a');
  for (const i of unreachable) {
    await tall.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    await outline.nth(i).click();
    await tall.evaluate(() => new Promise(done => {
      let last = -1, still = 0;
      const tick = () => { if (scrollY === last) { if (++still > 15) return done(); } else { still = 0; last = scrollY; } requestAnimationFrame(tick); };
      tick(); setTimeout(done, 10000);
    }));
    if ((await outline.nth(i).getAttribute('aria-current')) !== 'location')
      problems.push(`1366x1600 /docs/explore: following "${await outline.nth(i).textContent()}" (smooth scroll) does not mark it`);
  }
  await tall.close();
  // A wheel over the page tree scrolls the page when the tree has nothing to scroll (review 3: the panel trapped it).
  const desk = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await desk.goto(base + '/docs/toolkit', { waitUntil: 'networkidle' });
  const measure = () => desk.locator('cad-nav .cad-nav-panel').evaluate(p => {
    const r = p.getBoundingClientRect();
    return { over: p.scrollHeight - p.clientHeight, fits: p.scrollHeight <= p.clientHeight + 1, x: r.left + r.width / 2, y: r.top + 200 };
  });
  let panel = await measure();
  // The tree grows with the site (at this width the outline is in the right-hand rail, so every page's tree is the
  // same height): make the window taller until the tree has nothing to scroll, which is the case under test.
  if (!panel.fits) { await desk.setViewportSize({ width: 1920, height: 1080 + panel.over + 40 }); panel = await measure(); }
  if (!panel.fits) problems.push('1920px /docs/toolkit: the tree overflows its panel even in a taller window');
  await desk.mouse.move(panel.x, panel.y);
  await desk.mouse.wheel(0, 300);
  await desk.waitForTimeout(400);
  if ((await desk.evaluate(() => scrollY)) < 100) problems.push('1920px /docs/toolkit: a wheel over the page tree does not scroll the page');
  await desk.close();
  assert.deepEqual(problems, []);
  console.log(`${engine.name()}: ${ROUTES.length} routes at 360 and 1366 px under the site CSP PASS`);
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}

/** The snap-arm explorer (the kit's <cad-cantilever>) on /docs/compliant, at phone and desktop widths, under the site
 * CSP: it replaces its still at exactly the reserved size (no layout shift) and its first live frame is the still,
 * however late the script arrives, its panel never overflows, every control has a label, the keyboard moves a slider
 * and the strain follows, the print direction flips the verdict, it animates, pauses on request and carries on from
 * there, and holds still under reduced motion, with no console errors. */
async function cantileverProblems() {
  const out = [];
  const beam = page => page.locator('cad-cantilever [data-part=beam]').getAttribute('points');
  // The beam the script first draws (the still's shape, from drawCantilever) and the first frame it renders over it.
  // Both happen in the same task, so the observer sees them before any animation frame.
  const firstFrame = () => new MutationObserver((records, observer) => {
    const r = records.find(m => m.attributeName === 'points' && m.target.dataset?.part === 'beam');
    if (r) { window.ccFirstFrame = { still: r.oldValue, live: r.target.getAttribute('points') }; observer.disconnect(); }
  }).observe(document, { subtree: true, attributes: true, attributeOldValue: true, attributeFilter: ['points'] });
  const firstFrameProblem = async page => {
    const first = await page.evaluate(() => window.ccFirstFrame);
    return !first ? 'the first live frame was not seen' :
      first.still !== first.live ? 'the first live frame is not the still: the beam jumps when the script takes over' : null;
  };
  // A run of animation frames, not a wait: a throttled runner can sit 300 ms without one.
  const frames = page => page.evaluate(() => new Promise(done => {
    let n = 0;
    const next = () => (++n >= 10 ? done() : requestAnimationFrame(next));
    requestAnimationFrame(next);
  }));
  for (const width of [360, 1366]) {
    const height = {};
    for (const script of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const seen = [], say = s => seen.push(s);
      page.on('console', m => { if (m.type() === 'error' && script) say(`console: ${m.text()}`); });   // without the script: its blocked load
      page.on('pageerror', e => say(`page error: ${e.message}`));
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
      await page.addInitScript(firstFrame);
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
        const jump = await firstFrameProblem(page);
        if (jump) say(jump);
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
        // Wait for the pause to take effect before reading the frame, then let frames run (the click can land
        // between two of them on a slow runner).
        const stopped = await page.waitForFunction(() => document.querySelector('cad-cantilever .cc-play')?.textContent === 'Play',
          null, { timeout: 3000 }).then(() => true, () => false);
        const paused = await beam(page);
        await frames(page);
        if (!stopped || (await beam(page)) !== paused) say('the pause button does not stop it');
        // Play carries on from the frame on screen (full deflection), not from wherever a page clock has got to.
        const resumed = await page.evaluate(() => {
          const d = document.querySelector('cad-cantilever');
          d.querySelector('.cc-play').click();                    // renders in the click handler, before any frame
          return d.querySelector('[data-part=beam]').getAttribute('points');
        });
        if (resumed !== paused) say('Play does not carry on from the paused frame');
      }
      for (const s of seen) out.push(`${width}px /docs/compliant demo${script ? '' : ' (before its script)'}: ${s}`);
      await page.close();
    }
    if (!(Math.abs(height.true - height.false) < 0.5)) out.push(`${width}px demo: ${height.false}px tall before its script, ${height.true}px after`);
  }
  // The script arriving late (after the hold of a cycle timed from navigation) still takes over without a jump.
  const late = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await late.addInitScript(firstFrame);
  await late.route('**/kit/cantilever.js', async r => { await new Promise(ok => setTimeout(ok, 2600)); await r.continue(); });
  await late.goto(base + '/docs/compliant', { waitUntil: 'networkidle' });
  const lateJump = await firstFrameProblem(late);
  if (lateJump) out.push(`1366px /docs/compliant demo, its script 2.6 s late: ${lateJump}`);
  await late.close();
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + '/docs/compliant', { waitUntil: 'networkidle' });
  const first = await beam(reduced);
  await reduced.waitForTimeout(500);
  if (!first || (await beam(reduced)) !== first || (await reduced.locator('cad-cantilever .cc-play').textContent()) !== 'Play')
    out.push('reduced motion: the demo is animating');
  await reduced.close();
  return out;
}
