/** Load cad-agent.valpatel.com pages in a real browser, served the way Cloudflare Pages serves them (pretty URLs and
 * the _headers file, including the Content-Security-Policy), at phone and desktop widths.
 * Fails on console errors, CSP violations, failed or third-party requests, sideways scrolling, a phone header without
 * the catalogue link, a hero animation that is not running (or still running under reduced motion), a catalogue
 * filter that hides results without saying so, and a diagram wider than the article column at 1100 px (the narrowest
 * width with the page tree), so no reader has to scroll a diagram sideways on a desktop, a wall of text: a stretch
 * of a page with nothing to look at longer than one and a half screens (tests/site-walls.mjs, #179), and diagrams that
 * move the page while it loads or need script to show (#132: the build draws them). */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium, webkit } from '@playwright/test';
import { VIEWPORT, VISUAL, WALL_CLEARED, WALL_LIMIT, longestStretch, plantedScript } from './site-walls.mjs';

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
  problems.push(...await drawnDiagramProblems());        // diagrams drawn by the build: no shift, no script (#132), below
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
    // The home page's 3D model: its box around the poster when the page has loaded (its stylesheets with it: WebKit can
    // fire DOMContentLoaded before they arrive and lay out an unstyled box no reader sees). three.js and the model only
    // start after the load event, so this is still the poster.
    if (route === '/') await page.addInitScript(() => addEventListener('load', () => {
      const r = document.querySelector('cad-model')?.getBoundingClientRect();
      window.__posterBox = r && [r.width, r.height];
    }, { once: true }));
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
      // The 3D Gyropup (#179): it becomes the live model, fetches three.js and the model only after the page has
      // loaded (the poster is all the first paint needs), and nothing moves when it swaps in.
      const ready = await page.waitForFunction(() => ['ready', 'error'].includes(document.querySelector('cad-model')?.dataset.state), null, { timeout: 20000 })
        .then(() => page.evaluate(() => { const el = document.querySelector('cad-model'); return el.dataset.state === 'ready' ? 'ready' : el.dataset.error; }))
        .catch(() => 'never left the poster');
      if (ready !== 'ready') seen.push(`3D model: ${ready}`);
      const late = await page.evaluate(() => {
        const loaded = performance.getEntriesByType('navigation')[0].loadEventStart;
        return performance.getEntriesByType('resource').filter(r => /three\.module|\/web\/models\//.test(r.name) && !/\.webp$/.test(r.name) && r.startTime < loaded).map(r => r.name);
      });
      if (late.length) seen.push(`3D model fetched before the page loaded: ${late.join(', ')}`);
      // The live model takes exactly the poster's box (a font arriving may move it, never resize it), and the page
      // as a whole shifts no more than the page tree's limit.
      const box = await page.evaluate(() => { const r = document.querySelector('cad-model').getBoundingClientRect(); return { now: [r.width, r.height], first: window.__posterBox }; });
      if (!box.first || Math.abs(box.now[0] - box.first[0]) > 0.5 || Math.abs(box.now[1] - box.first[1]) > 0.5)
        seen.push(`the 3D model's box changed from ${box.first?.map(Math.round)} to ${box.now.map(Math.round)}`);
      // Each shift with what moved, so a CI log says where any shift comes from.
      const { shift, moved } = await page.evaluate(() => new Promise(done => {
        if (!PerformanceObserver.supportedEntryTypes?.includes('layout-shift')) return done({ shift: 0, moved: [] });
        let sum = 0; const moved = [];
        const name = n => !n ? '?' : n.nodeType !== 1 ? `${n.parentElement?.localName || '?'} text` : n.localName + (n.id ? '#' + n.id : '') + (n.classList[0] ? '.' + n.classList[0] : '');
        const rect = r => [r.x, r.y, r.width, r.height].map(Math.round).join(',');
        new PerformanceObserver(list => {
          for (const e of list.getEntries()) if (!e.hadRecentInput) {
            sum += e.value;
            moved.push(`${e.value.toFixed(3)} at ${Math.round(e.startTime)} ms: ${e.sources.map(x => `${name(x.node)} ${rect(x.previousRect)} -> ${rect(x.currentRect)}`).join('; ')}`);
          }
        }).observe({ type: 'layout-shift', buffered: true });
        setTimeout(() => done({ shift: sum, moved }), 200);
      }));
      if (shift > 0.05) seen.push(`layout shifts on the home page: ${shift.toFixed(3)} (${moved.join(' | ')})`);
      else if (shift > 0.01) console.log(`  note: ${width}px /: layout shift ${shift.toFixed(3)}, under the 0.05 limit: ${moved.join(' | ')}`);
      // Scrolled away, it draws nothing, even when the tab is hidden and shown again (#182 review).
      if (ready === 'ready') {
        await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight); });
        await page.waitForTimeout(400);
        const before = await page.evaluate(() => { document.dispatchEvent(new Event('visibilitychange')); return document.querySelector('cad-model').frames; });
        await page.waitForTimeout(800);
        const drawn = await page.evaluate(n => document.querySelector('cad-model').frames - n, before);
        if (drawn > 1) seen.push(`the 3D model drew ${drawn} frames off screen after the tab came back`);
      }
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
  // No text under a copy button (#126): every page with code, at mouse and touch widths around the kit's breakpoints,
  // idle and right after a copy on the page with the most code (the "Copied" label is wider than "Copy").
  const codePages = [];
  for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
    const rel = path.relative(dir, path.join(e.parentPath, e.name));
    if (!e.isFile() || !rel.endsWith('.html') || rel.startsWith('kit')) continue;
    const pres = ((await readFile(path.join(dir, rel), 'utf8')).match(/<pre\b/g) || []).length;
    if (pres) codePages.push(['/' + rel.replace(/\.html$/, '').split(path.sep).join('/'), pres]);
  }
  const busiest = codePages.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([r]) => r).reverse();
  const covered = () => {
    const out = [];
    for (const el of document.querySelectorAll('cad-copy')) {
      const btn = el.querySelector(':scope > .cad-copy-btn'), pre = el.querySelector(':scope > pre');
      if (!btn || !pre || !btn.offsetWidth) continue;
      const b = btn.getBoundingClientRect(), p = pre.getBoundingClientRect();
      const view = [p.left + pre.clientLeft, p.top + pre.clientTop, p.left + pre.clientLeft + pre.clientWidth, p.top + pre.clientTop + pre.clientHeight];
      const walk = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
      for (let n; (n = walk.nextNode());) {
        const range = document.createRange();
        range.selectNodeContents(n);
        const hit = [...range.getClientRects()].find(q => {
          const l = Math.max(q.left, view[0]), t = Math.max(q.top, view[1]), r = Math.min(q.right, view[2]), btm = Math.min(q.bottom, view[3]);
          return r - l >= 1 && btm - t >= 1 && r > b.left + 1 && l < b.right - 1 && btm > b.top + 1 && t < b.bottom - 1;
        });
        if (hit && n.textContent.trim()) { out.push(`"${n.textContent.trim().split('\n')[0].slice(0, 40)}" under the ${b.width.toFixed(0)}px button`); break; }
      }
    }
    return out;
  };
  for (const [width, touch] of [[360, true], [520, true], [768, true], [600, false], [800, false], [1366, false]]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, hasTouch: touch });   // touch: pointer: coarse
    if (engine === chromium) await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    const page = await context.newPage();
    const where = `${width}px ${touch ? 'touch' : 'mouse'}`;
    for (const route of busiest) {
      await page.goto(base + route, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))));
      for (const c of await page.evaluate(covered)) problems.push(`${where} ${route}: ${c}`);
    }
    await page.locator('cad-copy > .cad-copy-btn').first().click();
    await page.waitForFunction(() => document.querySelector('cad-copy > .cad-copy-btn')?.dataset.state !== 'idle');
    for (const c of await page.evaluate(covered)) problems.push(`${where} ${busiest.at(-1)} after copying: ${c}`);
    if (width === 768 || width === 1366) {
      // Planted blocks (review of #130), so the site's content does not decide whether this can fail. A probe block
      // learns where the text area ends and how wide a character is; then 41 copies of one line, each in a column
      // 1.5 px wider than the last, sweep the line's end 60 px across the button's edge, so no band of a few pixels
      // (a label a little wider than the room) is missed. All wrapped by enhance(); then every button pressed (the
      // wider labels); then a stylesheet that arrives late and makes the button bigger.
      await page.evaluate(async () => {
        const { enhance } = await import('/kit/copy.js');
        const frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        const box = document.createElement('div');
        box.id = 'planted';
        document.querySelector('article, main, body').append(box);
        const probe = Object.assign(document.createElement('div'), { style: 'width:520px' });
        probe.append(Object.assign(document.createElement('pre'), { textContent: 'x'.repeat(10) }));
        box.append(probe);
        enhance(probe);
        await frames();
        const pre = probe.querySelector('pre'), cs = getComputedStyle(pre), range = document.createRange();
        range.selectNodeContents(pre.firstChild);
        const char = range.getBoundingClientRect().width / 10;
        const text = pre.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
        const line = 'x'.repeat(Math.floor(text / char));
        box.replaceChildren();
        for (let i = 0; i <= 40; i++) {
          const col = Object.assign(document.createElement('div'), { style: `width:${490 + i * 1.5}px` });
          col.append(Object.assign(document.createElement('pre'), { textContent: line }));
          box.append(col);
        }
        enhance(box);
      });
      const settle = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      await settle();
      for (const c of await page.evaluate(covered)) problems.push(`${where} planted, idle: ${c}`);
      await page.evaluate(() => { for (const b of document.querySelectorAll('#planted .cad-copy-btn')) b.click(); });
      await page.waitForFunction(() => [...document.querySelectorAll('#planted .cad-copy-btn')].every(b => b.dataset.state !== 'idle'));
      await settle();
      for (const c of await page.evaluate(covered)) problems.push(`${where} planted, after copying: ${c}`);
      await page.addStyleTag({ content: 'cad-copy>.cad-copy-btn{font-size:15px;padding:.3em 1.2em}' });
      await settle();
      for (const c of await page.evaluate(covered)) problems.push(`${where} planted, late stylesheet: ${c}`);
    }
    await context.close();
  }
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + '/', { waitUntil: 'networkidle' });
  const still = await reduced.evaluate(() => document.getAnimations().filter(a => a.animationName?.startsWith('snap-')).length);
  if (still) problems.push(`reduced motion: ${still} hero animations still running`);
  // The model stands still (no turntable, so no Pause button) until the reader drags it.
  await reduced.waitForFunction(() => document.querySelector('cad-model')?.dataset.state === 'ready', null, { timeout: 20000 })
    .catch(() => problems.push('reduced motion: the 3D model did not load'));
  const turning = await reduced.evaluate(() => [...document.querySelectorAll('cad-model .cad-model-ui button')].filter(b => !b.hidden && b.textContent === 'Pause').length);
  if (turning) problems.push('reduced motion: the 3D model turns by itself');
  await reduced.close();
  // Every page with a diagram, at the narrowest desktop width: each rendered diagram fits its column (#122).
  const diagramPages = [];
  for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
    const rel = path.relative(dir, path.join(e.parentPath, e.name));
    if (!e.isFile() || !rel.endsWith('.html') || rel.startsWith('kit')) continue;
    const sources = ((await readFile(path.join(dir, rel), 'utf8')).match(/class="language-mermaid"|<pre class="mermaid"|<figure class="cad-diagram"/g) || []).length;
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
  // Walls of text (#179): on every page at 1366 x 800, the longest stretch of content with no picture, diagram, demo
  // or render stays under WALL_LIMIT (1.5 screens). WALLS is the backlog, each page with the issue that breaks it up;
  // it only shrinks: a page not on it must pass, and one on it that measures under WALL_CLEARED must leave it.
  const WALLS = new Map([
    // #146 adds the snap-arm explorer.
    ['/docs/compliant', 146],
    // #179 slice 3: real outputs for the rest. /docs/toolkit splits into area pages once #121's layout lands.
    ...['/CONTRIBUTING', '/README', '/THIRD_PARTY_NOTICES', '/docs/agent-workflow', '/docs/common-issues', '/docs/design-process-plan',
      '/docs/dossier', '/docs/explore', '/docs/file-viewer', '/docs/gates', '/docs/pcb', '/docs/review-packet', '/docs/toolkit',
      '/docs/vision', '/docs/volume-precision', '/docs/web-parts', '/lessons/electronics/pcb-evidence-and-review',
      '/lessons/mechanical/design-rules', '/lessons/mechanical/enclosure-features', '/lessons/mechanical/fasteners-and-assembly-access',
      '/lessons/process/agent-process', '/lessons/process/user-intent-and-requirements', '/lessons/process/verify-from-source',
      '/lessons/review/review-site-ux', '/lessons/review/verification-and-evidence',
      '/lessons/simulation/simulation-and-material', '/lessons/wiring/cables-connectors-and-routing', '/research/agent-toolkits-2026-10',
      '/research/compliant-mechanisms', '/research/design-workflows', '/research/fea-and-process-tools', '/research/landscape',
      '/research/process-profiles', '/research/simulation-tools', '/skills/cad-pr-review/SKILL',
      '/skills/cad-work-tracking/SKILL', '/skills/design-process/SKILL', '/skills/mcmaster-parts/SKILL'].map(r => [r, 179]),
  ]);
  // The list only shrinks: its length is pinned here, so a page can join it only with a visible edit to this number,
  // and each page that leaves it brings the number down with it.
  const WALLS_LEFT = 39;
  if (WALLS.size !== WALLS_LEFT) problems.push(`walls: WALLS has ${WALLS.size} pages and WALLS_LEFT says ${WALLS_LEFT}: ${WALLS.size < WALLS_LEFT ? `lower WALLS_LEFT to ${WALLS.size}` : 'the backlog only shrinks; fix the page instead'}`);
  const sitePages = [];
  for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
    const rel = path.relative(dir, path.join(e.parentPath, e.name));
    if (e.isFile() && rel.endsWith('.html') && !rel.startsWith('kit') && rel !== '404.html')
      sitePages.push('/' + rel.replace(/(^|\/)index\.html$|\.html$/, '').split(path.sep).join('/'));
  }
  for (const route of WALLS.keys()) if (!sitePages.includes(route)) problems.push(`walls: ${route} is not a page; remove it from WALLS`);
  const reader = await browser.newPage({ viewport: VIEWPORT });
  // Layout shifts while each page loads, for the pages with a diagram (#132): Chrome reports them, WebKit does not.
  await reader.addInitScript(() => {
    window.__shift = 0;
    if (PerformanceObserver.supportedEntryTypes?.includes('layout-shift'))
      new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) window.__shift += e.value; })
        .observe({ type: 'layout-shift', buffered: true });
  });
  const withDiagrams = new Set(diagramPages.map(([r]) => r));
  await reader.goto(base + '/docs/compliant', { waitUntil: 'load' });
  // The measure itself, on planted articles of known geometry, so a broken measure cannot pass every page.
  for (const [name, { got, want }] of Object.entries(await reader.evaluate(plantedScript())))
    if (Math.abs(got - want) > 1) problems.push(`walls: the planted "${name}" article measures ${got}px, not ${want}px`);
  for (const route of sitePages.sort()) {
    await reader.goto(base + route, { waitUntil: 'load' });
    await reader.waitForFunction(() => !document.querySelector('pre.mermaid, code.language-mermaid') &&
      [...document.querySelectorAll('.cad-diagram')].every(f => f.dataset.state === 'ready' || f.dataset.state === 'error'), null, { timeout: 20000 })
      .catch(() => problems.push(`walls ${route}: diagrams did not finish rendering`));
    await reader.evaluate(() => document.fonts.ready);
    if (withDiagrams.has(route)) {
      const shift = await reader.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(() => done(window.__shift)))));
      if (shift > DIAGRAM_SHIFT) problems.push(`1366px ${route}: the page moved by ${shift.toFixed(3)} while it loaded (limit ${DIAGRAM_SHIFT}; diagrams are drawn by the build)`);
    }
    const wall = await reader.evaluate(longestStretch, VISUAL);
    const where = `${wall.worst}px with nothing to look at, ${wall.from}-${wall.to}px into the page, after "${wall.after}"`;
    if (WALLS.has(route)) { if (wall.worst < WALL_CLEARED) problems.push(`walls ${route}: ${where}, well under ${WALL_LIMIT}px: remove it from WALLS (#${WALLS.get(route)})`); }
    else if (wall.worst > WALL_LIMIT) problems.push(`walls ${route}: ${where}; the limit is ${WALL_LIMIT}px. Add a real output, diagram or demo there, or fold the long reference parts into <details>`);
  }
  await reader.close();
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
  // Every group is folded first, so the panel is still a scroll container but has nothing to scroll whatever the
  // number of pages. The open Docs group alone outgrew 1080 px when the vision page arrived (#148); from 1500 px the
  // tree leaves out the page's outline.
  const desk = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await desk.goto(base + '/docs/toolkit', { waitUntil: 'networkidle' });
  const panel = await desk.locator('cad-nav .cad-nav-panel').evaluate(p => {
    for (const group of p.querySelectorAll('details')) group.open = false;
    const r = p.getBoundingClientRect(), cs = getComputedStyle(p);
    return { fits: p.scrollHeight <= p.clientHeight + 1, scroller: /auto|scroll/.test(cs.overflowY), x: r.left + r.width / 2, y: r.top + 60 };
  });
  if (!panel.fits) problems.push('1920px /docs/toolkit: with every group folded the tree still overflows its panel');
  if (!panel.scroller) problems.push('1920px /docs/toolkit: the tree panel is no longer a scroll container, so this check tests nothing');
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

/** Diagrams drawn by the build (#132, tools/site-diagrams.mjs). Drawn in the reader's browser, a diagram near the top
 * moved the page twice as it loaded (0.58 on /lessons/process/agent-process at 360 px, 0.10 on /docs/style-guide at
 * 1366 px); Google calls a page good under 0.1. On the pages below, at phone and desktop widths: the layout shift while
 * the page loads stays under DIAGRAM_SHIFT (Chrome; WebKit does not report shifts), the diagrams show with script off,
 * each in the same box as with script on (so the script moves nothing, anywhere on the page, in either engine), the
 * sideways-scroll hint shows exactly when its diagram overflows, without script too, and no page downloads Mermaid. */
const DIAGRAM_SHIFT = 0.05;
async function drawnDiagramProblems() {
  const out = [];
  const PAGES = ['/docs/toolkit', '/docs/style-guide', '/docs/vision', '/lessons/process/agent-process'];
  const boxes = page => page.$$eval('.cad-diagram', figs => figs.map(f => {
    const r = f.getBoundingClientRect(), svg = f.querySelector('.cad-diagram-view svg')?.getBoundingClientRect();
    const view = f.querySelector('.cad-diagram-view'), hint = f.querySelector('.cad-diagram-hint');
    return { state: f.dataset.state, box: [r.x, r.y + scrollY, r.width, r.height].map(n => Math.round(n * 2) / 2), svg: svg && [svg.width, svg.height],
      overflows: view.scrollWidth > view.clientWidth + 1, hint: hint.getBoundingClientRect().height > 0 && getComputedStyle(hint).display !== 'none' };
  }));
  for (const width of [360, 1366]) for (const route of PAGES) {
    const where = `${width}px ${route}`;
    const still = await browser.newContext({ viewport: { width, height: 800 }, javaScriptEnabled: false });
    const off = await still.newPage();
    await off.goto(base + route, { waitUntil: 'load' });
    await off.evaluate(() => document.fonts.ready);
    const before = await boxes(off);
    await still.close();
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await context.newPage();
    const runtime = [];
    page.on('request', r => { if (/mermaid\.min\.js/.test(r.url())) runtime.push(r.url()); });
    await page.addInitScript(() => {
      window.__shift = 0;
      if (PerformanceObserver.supportedEntryTypes?.includes('layout-shift'))
        new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) window.__shift += e.value; })
          .observe({ type: 'layout-shift', buffered: true });
    });
    await page.goto(base + route, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))));
    const after = await boxes(page), shift = await page.evaluate(() => window.__shift);
    await context.close();
    if (!before.length) { out.push(`${where}: no diagram on the page`); continue; }
    if (shift > DIAGRAM_SHIFT) out.push(`${where}: the page moved by ${shift.toFixed(3)} while it loaded (limit ${DIAGRAM_SHIFT})`);
    if (runtime.length) out.push(`${where}: downloaded Mermaid (${runtime.length}x), though the build drew every diagram`);
    before.forEach((b, i) => {
      if (b.state !== 'ready' || !b.svg || b.svg[0] < 100 || b.svg[1] < 30) out.push(`${where}: diagram ${i + 1} does not show without script (${JSON.stringify(b)})`);
      const a = after[i];
      if (!a || a.box.join() !== b.box.join()) out.push(`${where}: diagram ${i + 1} is at ${b.box} without script and at ${a?.box} with it`);
      for (const [label, m] of [['without script', b], ['with script', a]])
        if (m && m.hint !== m.overflows) out.push(`${where}: diagram ${i + 1} ${m.overflows ? 'overflows' : 'fits'} but its scroll hint is ${m.hint ? 'shown' : 'hidden'} ${label}`);
    });
  }
  return out;
}

/** The snap-arm explorer (the kit's <cad-cantilever>) on /docs/compliant, at phone and desktop widths, under the site
 * CSP: it replaces its still at exactly the reserved size (no layout shift) and its first live frame is the still,
 * however late the script arrives, its panel never overflows, every control has a label, the keyboard moves a slider
 * and the strain follows, the print direction flips the verdict, it animates, pauses on request and carries on from
 * there, holds still under reduced motion, and its status line speaks after an input but not on page load, with no
 * console errors. */
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
        const status = () => demo.locator('.cc-status').textContent();
        if (await status()) say('the status line spoke before anyone touched the demo');
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
        await page.waitForFunction(() => document.querySelector('cad-cantilever .cc-status')?.textContent,
          null, { timeout: 3000 }).catch(() => say('the status line does not announce the result after an input'));
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
  // Over 700 ms (the announcement delay) since the element drew, with no input: the polite live region stays empty,
  // so a screen reader does not read the result out of context on page load.
  if (await reduced.locator('cad-cantilever .cc-status').textContent())
    out.push('the status line spoke on page load, with nobody touching the demo');
  await reduced.close();
  return out;
}
