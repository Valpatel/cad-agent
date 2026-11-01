/** Load cad-agent.valpatel.com pages in a real browser, served the way Cloudflare Pages serves them (pretty URLs and
 * the _headers file, including the Content-Security-Policy), at phone and desktop widths.
 * Fails on console errors, CSP violations, failed or third-party requests, sideways scrolling, a phone header without
 * the catalogue link, a hero animation that is not running (or still running under reduced motion), a catalogue
 * filter that hides results without saying so, and a diagram wider than the article column at 1100 px (the narrowest
 * width with the page tree), so no reader has to scroll a diagram sideways on a desktop, a wall of text: a stretch
 * of a page with nothing to look at longer than one and a half screens (tests/site-walls.mjs, #179), and diagrams that
 * move the page while it loads or need script to show (#132: the build draws them). Also the page tree's fold on
 * phones with nav.js loaded, late, blocked, failing or off, and outline jumps (foldProblems and jumpProblems, below). */
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
// The most a page with a diagram may move while it loads (#132; Google calls a page good under 0.1).
const DIAGRAM_SHIFT = 0.05;
// The kit scripts web/site.js starts on every page.
const SITE_KIT = ['/kit/diagrams.js', '/kit/copy.js', '/kit/nav.js'];
/** The torsion-snap and screw-boss explorers (#161): what each one's page must show, and how to drive it. */
const EXPLORERS = [
  { tag: 'cad-torsion-snap', prefix: 'ts', route: '/docs/compliant', script: 'torsion-snap', still: 'docs/img/compliant/torsion-snap-explorer.svg',
    part: 'end', attr: 'points', vectors: /^torsion/, start: { verdict: 'PASS', strain: '1.11 %' },
    // the twist from 8° to 10°: past the 9.3° limit
    slider: { name: /^Twist at the lever/, presses: 4, spoken: /degrees/, verdict: 'FAIL', tile: ['strain', '1.38 %'] },
    radio: { label: 'One bar', changes: 'force', check: (before, after) => Math.abs(parseFloat(after) - parseFloat(before) / 2) < 0.011 },
    contrast: ['.ts-tile b', '.ts-note', '.ts-tile span:not(.ts-k)', ['[data-part=label-force]', 'fill']],
    shapes: [{ bars: '1', twist: '30', lever: '30', width: '12', thickness: '0.6' }, { length: '4', width: '12', thickness: '4', twist: '30', lever: '3' },
      { material: 'copa-polymaker-wet', repeated: '', twist: '0' }, {}],
    // the note for each shape: the first two twist far enough for the trapeze effect to matter
    notes: [/trapeze effect/, /trapeze effect/, /^Saint-Venant/, /^Saint-Venant/] },
  { tag: 'cad-printed-boss', prefix: 'pb', route: '/docs/screw-bosses', script: 'printed-boss', still: 'docs/img/fasteners/screw-boss-explorer.svg',
    part: 'torque', attr: 'd', vectors: /^(screwBoss|nutFactor|thread|bossHoop|preload|torqueFor)/, start: { verdict: 'PASS', strip: '767 N' },
    // the torque from 0.30 to 0.40 N m: past half the stripping torque
    slider: { name: /^Tightening torque/, presses: 10, spoken: /newton metres/, verdict: 'FAIL', tile: ['verdict-note', 'over-tightened'] },
    radio: { label: 'Lying on its side', part: 'layers', check: (before, after) => before !== after },
    contrast: ['.pb-tile b', '.pb-note', '.pb-tile span:not(.pb-k)', ['[data-part=label-strip]', 'fill']],
    shapes: [{ size: '50', outside: '20', engagement: '25', torque: '3', material: 'petg-bambu-hf' }, { size: '20', outside: '2.4', engagement: '1', torque: '0.02' },
      { size: '35', outside: '4', engagement: '3', torque: '2.5', axis: 'lying', material: 'pa6-cf20-polymaker-wet' }, {}] },
];

const problems = [];
try {
  problems.push(...await cantileverProblems());          // the snap-arm explorer on /docs/compliant (#137), below
  problems.push(...await foldProblems());                // the page tree's fold on phones, with and without nav.js (#134)
  problems.push(...await jumpProblems());                // outline jumps: released by the reader's wheel, not by a stall
  problems.push(...await fourbarProblems());             // the four-bar animator on /docs/linkages (#159), below
  problems.push(...await fanCurveProblems());            // the fan-curve explorer on /docs/fans (#160), below
  for (const spec of EXPLORERS) problems.push(...await explorerProblems(spec));   // torsion snap and screw boss (#161), below
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
      // The shift at every width, each with what moved, so a CI log says what it was and where any shift comes from.
      const { shift, moved, measured = true } = await page.evaluate(() => new Promise(done => {
        if (!PerformanceObserver.supportedEntryTypes?.includes('layout-shift')) return done({ shift: 0, moved: [], measured: false });
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
      else if (measured) console.log(`  ${width}px /: layout shift ${shift.toFixed(3)}${moved.length ? `, under the 0.05 limit: ${moved.join(' | ')}` : ''}`);
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
      await page.goto(base + route);
      await settled(page);
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
      // A flat tree (no groups): the script opens the current page's group, never the fold itself, so on a phone it
      // stays closed (#209 review).
      const flat = await page.evaluate(() => {
        const el = document.createElement('cad-nav');
        el.innerHTML = '<ul><li><a href="/a">Alpha</a></li><li><a href="/b" aria-current="page">Beta</a></li></ul>';
        document.body.append(el);
        const open = el.querySelector(':scope > details.cad-nav-fold')?.open;
        el.remove();
        return open;
      });
      if (flat === undefined) seen.push('a flat tree gets no fold');
      else if (flat !== width >= 1100) seen.push(`a flat tree's fold is ${flat ? 'open' : 'closed'} at ${width}px`);
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
  await reduced.goto(base + '/');
  await settled(reduced);
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
    await wide.goto(base + route);
    await settled(wide);
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
    ...['/CONTRIBUTING', '/README', '/THIRD_PARTY_NOTICES', '/docs/agent-workflow', '/docs/design-process-plan',
      '/docs/dossier', '/docs/explore', '/docs/gates', '/docs/pcb', '/docs/review-packet', '/docs/toolkit',
      '/docs/vision', '/docs/volume-precision', '/lessons/electronics/pcb-evidence-and-review',
      '/lessons/mechanical/design-rules', '/lessons/mechanical/enclosure-features', '/lessons/process/agent-process',
      '/lessons/process/verify-from-source', '/lessons/review/verification-and-evidence',
      '/lessons/simulation/simulation-and-material', '/lessons/wiring/cables-connectors-and-routing',
      '/research/agent-toolkits-2026-10', '/research/compliant-mechanisms', '/research/design-workflows',
      '/research/fea-and-process-tools', '/research/landscape', '/research/process-profiles',
      '/research/simulation-tools', '/skills/cad-pr-review/SKILL', '/skills/cad-work-tracking/SKILL',
      '/skills/design-process/SKILL', '/skills/mcmaster-parts/SKILL'].map(r => [r, 179]),
  ]);
  // The list only shrinks: its length is pinned here, so a page can join it only with a visible edit to this number,
  // and each page that leaves it brings the number down with it.
  const WALLS_LEFT = 33;
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
  await wider.goto(base + '/docs/toolkit');
  await settled(wider);
  await wider.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight / 2); });
  await wider.waitForTimeout(300);
  if (!(await wider.locator('.doc-rail').isVisible())) problems.push('1600px: no "On this page" column');
  else if (!(await wider.locator('.doc-rail a[aria-current=location]').count())) problems.push('1600px: the right-hand outline does not mark the section');
  if (await wider.locator('cad-nav .cad-nav-outline').isVisible()) problems.push('1600px: the outline shows twice');
  await wider.close();
  // A big screen, where several last sections cannot reach the reading line: each outline link followed with the
  // site's smooth scrolling marks its own section once the scroll settles (#123 review: 21 of 59 were wrong).
  const big = await browser.newPage({ viewport: { width: 2560, height: 1440 } });
  await big.goto(base + '/docs/explore');
  await settled(big);
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
  // At the very end of the page the column <cad-nav> sits in has ended above the window's bottom: the panel shrinks to
  // the room left rather than sliding up, so its filter stays where it sticks, below the header (#230: one more page
  // in the tree pushed it under the header, and typing in it scrolled the page).
  const atEnd = await big.evaluate(async () => {
    scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const panel = document.querySelector('cad-nav .cad-nav-panel');
    return { top: panel.getBoundingClientRect().top, stick: parseFloat(getComputedStyle(panel).top) };
  });
  if (atEnd.top < atEnd.stick - 1) problems.push(`2560px /docs/explore: at the page's end the page tree's panel slid up to ${Math.round(atEnd.top)}px, above where it sticks (${atEnd.stick}px)`);
  await big.close();
  // The same jumps through the tree's own outline, in a window tall enough that several sections cannot reach the
  // reading line (review 3: at 1366x900 only the last one cannot, and the bottom rule marks it anyway).
  const tall = await browser.newPage({ viewport: { width: 1366, height: 1600 } });
  await tall.goto(base + '/docs/explore');
  await settled(tall);
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
  await desk.goto(base + '/docs/toolkit');
  await settled(desk);
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

/** Wait for the page as its reader sees it, the state the checks read: loaded, the site's kit scripts and `modules` (a
 * page's own, such as its demo's) run or failed, then painted. Not for a quiet network: Playwright discourages
 * networkidle, and WebKit on CI once waited 30 s for it on a page that had loaded (/docs/vision, #154). Importing a
 * module the page has already asked for makes no second request and settles once the module has run. The page's own
 * .then on it (site.js starting the diagrams) may still be queued then in Chrome, where the load event does not wait
 * for dynamic imports (#225 review), so a task turn and the two frames of painted() follow. */
async function settled(page, ...modules) {
  const kit = await page.evaluate(urls => Promise.race([Promise.allSettled(urls.map(u => import(u))).then(() => 'ran'),
    new Promise(ok => setTimeout(ok, 15000, 'stuck'))]).then(r => new Promise(ok => setTimeout(ok, 0, r))), [...SITE_KIT, ...modules]);
  if (kit !== 'ran') throw new Error(`${page.url()}: the kit scripts neither ran nor failed within 15 s`);
  await painted(page);
}

/** Stylesheets and fonts in, then two frames. With JavaScript off, Playwright can still run code in the page, but not
 * wait on a promise there. In WebKit, document.fonts.ready waits for the load event, which there waits for the page's
 * dynamic imports (nav.js, held back in foldProblems), so the fonts' status is what counts. */
function painted(page, js = true) {
  return !js ? page.waitForTimeout(150) :
    page.waitForFunction(() => [...document.querySelectorAll('link[rel=stylesheet]')].every(l => l.sheet) && document.fonts.status === 'loaded',
      null, { timeout: 10000 }).then(() => page.evaluate(() => new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)))));
}

/** The fan-curve explorer (the kit's <cad-fan-curve>) on /docs/fans, at phone and desktop widths, under the site CSP:
 * the fan vectors run again in this browser engine; the element replaces its still at exactly the reserved size (no
 * layout shift), and on a desktop its live chart puts the operating point where the still has it; its panel never
 * overflows, also after the controls change; every control has a label; the keyboard on the system slider moves the
 * point into the stall region and the tiles say so; the voltage and arrangement radios, pressed and held the way a
 * person presses them (#211), change the curve and the verdict; the hover line reads both curves; its tile text fits;
 * its colours keep their contrast in light and dark; its status line speaks after an input but not on page load; no
 * console or CSP errors. */
async function fanCurveProblems() {
  const out = [], route = '/docs/fans';
  const frames = (page, count = 3) => page.evaluate(count => new Promise(done => {
    let n = 0;
    const next = () => (++n >= count ? done() : requestAnimationFrame(next));
    requestAnimationFrame(next);
  }), count);
  // a press that lasts a few frames, as a person's does, on the label of a radio (#211: a quick click hides a redraw)
  const hold = async (page, locator) => {
    await locator.hover();
    await page.mouse.down();
    await frames(page, 3);
    await page.mouse.up();
  };
  const contrast = (page, selector, attr = 'color') => page.evaluate(([sel, at]) => {
    const rgb = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const el = document.querySelector(sel);
    let bg = el, back = 'rgba(0, 0, 0, 0)';
    while (bg && /rgba\(.*, 0\)|transparent/.test(back = getComputedStyle(bg).backgroundColor)) bg = bg.parentElement;
    const fore = at === 'color' ? getComputedStyle(el).color : getComputedStyle(el).fill;
    const [l1, l2] = [lum(fore), lum(back)].sort((x, y) => y - x);
    return (l1 + 0.05) / (l2 + 0.05);
  }, [selector, attr]);
  const overflow = demo => demo.locator('.fc-panel').evaluate(p => {
    const box = p.getBoundingClientRect();
    return { over: p.scrollHeight - p.clientHeight, out: [...p.querySelectorAll('*')].filter(n => n.getClientRects().length &&
      n.getBoundingClientRect().bottom > box.bottom + 0.5 && getComputedStyle(n).position !== 'absolute').length };
  });
  const vectors = JSON.parse(await readFile(path.join(root, 'tests/fixtures/formula-vectors.json'), 'utf8'));
  const fans = vectors.cases.filter(c => /^fan|^systemCoefficient$/.test(c.js) && !c.raises);
  const still = await readFile(path.join(root, 'docs/img/thermal/fan-curve-explorer.svg'), 'utf8');
  const stillPoint = still.match(/data-part="point" cx="([\d.]+)" cy="([\d.]+)"/).slice(1).join();
  for (const width of [360, 1366]) {
    const height = {};
    for (const script of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const seen = [], say = s => seen.push(s);
      page.on('console', m => { if (m.type() === 'error' && script) say(`console: ${m.text()}`); });
      page.on('pageerror', e => say(`page error: ${e.message}`));
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
      if (!script) await page.route('**/kit/fan-curve.js', r => r.abort());
      await page.goto(base + route);
      await settled(page, '/kit/fan-curve.js');
      const demo = page.locator('cad-fan-curve');
      await demo.scrollIntoViewIfNeeded();
      height[script] = (await demo.boundingBox())?.height;
      if (!script) {
        const img = await demo.locator(':scope > img').evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false);
        if (!img) say('no still image before the script loads');
      } else if (!(await demo.locator('svg [data-part=point]').count())) say('the live chart did not render');
      else {
        if (width === 1366) {
          // the port in this engine, on the fan golden vectors (the Node test runs them in V8 only): bit for bit
          const wrong = await page.evaluate(async cases => {
            const fx = await import('/kit/formulas.js');
            return cases.filter(c => JSON.stringify(fx[c.js](...c.args)) !== JSON.stringify(c.expected)).map(c => c.js);
          }, fans);
          if (wrong.length) say(`the port differs from the Python in this engine on ${wrong.length} fan vectors: ${wrong.slice(0, 3).join('; ')}`);
          const live = await demo.locator('[data-part=point]').evaluate(c => [c.getAttribute('cx'), c.getAttribute('cy')].join());
          if (live !== stillPoint) say(`the live chart's operating point (${live}) is not the still's (${stillPoint})`);
        }
        const panel = await overflow(demo);
        if (panel.over > 0 || panel.out) say(`the panel overflows (${panel.over}px, ${panel.out} elements)`);
        const unlabelled = await demo.evaluate(d => [...d.querySelectorAll('input')].filter(i => !i.labels?.length).map(i => i.name));
        if (unlabelled.length) say(`controls without a label: ${unlabelled.join(', ')}`);
        const tile = k => demo.locator(`[data-out=${k}]`).textContent();
        const status = () => demo.locator('.fc-status').textContent();
        if (await status()) say('the status line spoke before anyone touched the demo');
        if ((await tile('flow')) !== '150 m³/h' || (await tile('verdict')) !== 'Clear of stall') say(`the default reads ${await tile('flow')}, ${await tile('verdict')}`);
        // the site is light, whatever the reader prefers; the element follows the page
        await page.emulateMedia({ colorScheme: 'dark' });
        if ((await demo.getAttribute('data-theme')) !== 'light') say('the demo turned dark on a light page');
        for (const theme of ['light', 'dark']) {
          await demo.evaluate((d, t) => d.setAttribute('theme', t), theme);
          if ((await demo.getAttribute('data-theme')) !== theme) say(`theme="${theme}" is not applied`);
          for (const [sel, at, min] of [['cad-fan-curve .fc-tile b', 'color', 4.5], ['cad-fan-curve .fc-note', 'color', 4.5],
            ['cad-fan-curve .fc-tile span:not(.fc-k)', 'color', 4.5], ['cad-fan-curve [data-part=point-label]', 'fill', 4.5]]) {
            const ratio = await contrast(page, sel, at);
            if (!(ratio >= min)) say(`${theme}: ${sel} has a contrast of ${ratio.toFixed(2)}, under ${min}`);
          }
        }
        await demo.evaluate(d => d.removeAttribute('theme'));
        await page.emulateMedia({ colorScheme: 'light' });
        // the tiles' words fit for every kind of result (one line each at desktop width, cut with an ellipsis if not)
        for (const attrs of [['16', '2', '4', 'parallel'], ['8', '60', '4', 'series'], ['12', '25', '2', 'parallel'], ['12', '60', '1', 'parallel'], ['12', '12', '1', 'parallel']]) {
          const cut = await demo.evaluate((d, a) => {
            ['fan', 'system', 'count', 'arrangement'].forEach((k, i) => d.setAttribute(k, a[i]));
            return [...d.querySelectorAll('.fc-tile b, .fc-tile span')].filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent);
          }, attrs);
          if (cut.length) say(`${attrs}: tile text cut off: ${cut.join('; ')}`);
          const after = await overflow(demo);
          if (after.over > 0 || after.out) say(`${attrs}: the panel overflows (${after.over}px, ${after.out} elements)`);
        }                                                                               // ends on the page's state
        // the keyboard: the system slider from 12 to 25 Pa at 100 m³/h puts one fan in its stall region
        const slider = page.getByRole('slider', { name: /^System: pressure drop/ });
        await slider.focus();
        for (let i = 0; i < 13; i++) await slider.press('ArrowRight');
        if (!/pascals/.test(await slider.getAttribute('aria-valuetext') || '')) say('the system slider has no spoken value');
        if ((await tile('flow')) !== '112 m³/h' || (await tile('verdict')) !== 'In stall') say(`25 Pa reads ${await tile('flow')}, ${await tile('verdict')}, not 112 m³/h in stall`);
        if ((await demo.locator('[data-out=verdict-tile]').getAttribute('data-verdict')) !== 'poor') say('the stall verdict is not marked as a warning');
        // two fans: in parallel each still stalls; in series the pair runs clear (radios pressed and held)
        const fansSlider = page.getByRole('slider', { name: /^Fans/ });
        await fansSlider.focus();
        await fansSlider.press('ArrowRight');
        await hold(page, demo.locator('label', { hasText: 'Series' }));
        if (!(await page.getByRole('radio', { name: 'Series' }).isChecked()) || (await tile('flow')) !== '148 m³/h' || (await tile('verdict')) !== 'Clear of stall')
          say(`two in series at 25 Pa read ${await tile('flow')}, ${await tile('verdict')}, not 148 m³/h clear of stall`);
        await hold(page, demo.locator('label', { hasText: 'Parallel' }));
        if ((await tile('flow')) !== '140 m³/h' || (await tile('verdict')) !== 'In stall') say(`two in parallel at 25 Pa read ${await tile('flow')}, ${await tile('verdict')}`);
        if (!(await demo.locator('[data-part=single]').count())) say('with two fans, one fan\'s curve is not drawn');
        const curve = await demo.locator('[data-part=fan]').getAttribute('points');
        await hold(page, demo.locator('label', { hasText: '16 V' }));
        if ((await demo.locator('[data-part=fan]').getAttribute('points')) === curve || !(await page.getByRole('radio', { name: '16 V' }).isChecked())) say('the 16 V curve did not replace the 12 V one');
        const moved = await overflow(demo);
        if (moved.over > 0 || moved.out) say(`after the controls changed, the panel overflows (${moved.over}px, ${moved.out} elements)`);
        // the hover line reads the fan and the system at the flow under the pointer
        const chart = await demo.locator('.fc-figure svg').boundingBox();
        await page.mouse.move(chart.x + chart.width * 0.5, chart.y + chart.height * 0.5);
        await frames(page, 2);
        const hover = await demo.locator('[data-part=hover]').evaluate(g => ({ shown: g.getAttribute('visibility'), text: g.querySelector('text').textContent }));
        if (hover.shown !== 'visible' || !/^\d+ m³\/h: fan (–|[\d.]+ Pa) · system [\d.]+ Pa$/.test(hover.text)) say(`the hover line reads "${hover.text}" (${hover.shown})`);
        await page.waitForFunction(() => document.querySelector('cad-fan-curve .fc-status')?.textContent,
          null, { timeout: 3000 }).catch(() => say('the status line does not announce the result after an input'));
        const after = (await demo.boundingBox())?.height;
        if (!(Math.abs(after - height[script]) < 0.5)) say(`the explorer changed height with its controls (${height[script]}px, then ${after}px)`);
      }
      for (const s of seen) out.push(`${width}px ${route} fan curve${script ? '' : ' (before its script)'}: ${s}`);
      await page.close();
    }
    if (!(Math.abs(height.true - height.false) < 0.5)) out.push(`${width}px fan curve: ${height.false}px tall before its script, ${height.true}px after`);
  }
  // Over 700 ms (the announcement delay) with no input, the polite live region stays empty on page load.
  const quiet = await browser.newPage();
  await quiet.goto(base + route);
  await settled(quiet, '/kit/fan-curve.js');
  await quiet.waitForTimeout(800);
  if (await quiet.locator('cad-fan-curve .fc-status').textContent()) out.push('the fan-curve status line spoke on page load');
  await quiet.close();
  return out;
}

/** One of EXPLORERS on its page, at phone and desktop widths, under the site CSP: its golden vectors run again in this
 * engine; it replaces its still at exactly the reserved size (no layout shift), and on a desktop its live figure has
 * the still's geometry; its panel never overflows and its tile text fits, for the default and for extreme settings;
 * every control has a label; the keyboard on a slider changes the verdict; a radio pressed and held the way a person
 * presses it (#211) changes the result; its colours keep their contrast in light and dark, and it stays light on the
 * light site; its status line speaks after an input but not on page load; no console or CSP errors. */
async function explorerProblems(x) {
  const out = [], { tag, prefix: px, route } = x, name = tag.replace(/^cad-/, '');
  const frames = (page, count = 3) => page.evaluate(count => new Promise(done => {
    let n = 0;
    const next = () => (++n >= count ? done() : requestAnimationFrame(next));
    requestAnimationFrame(next);
  }), count);
  const hold = async (page, locator) => {
    await locator.hover();
    await page.mouse.down();
    await frames(page, 3);
    await page.mouse.up();
  };
  const contrast = (page, selector, attr = 'color') => page.evaluate(([sel, at]) => {
    const rgb = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const el = document.querySelector(sel);
    let bg = el, back = 'rgba(0, 0, 0, 0)';
    while (bg && /rgba\(.*, 0\)|transparent/.test(back = getComputedStyle(bg).backgroundColor)) bg = bg.parentElement;
    const fore = at === 'color' ? getComputedStyle(el).color : getComputedStyle(el).fill;
    const [l1, l2] = [lum(fore), lum(back)].sort((a, b) => b - a);
    return (l1 + 0.05) / (l2 + 0.05);
  }, [selector, attr]);
  const overflow = demo => demo.locator(`.${px}-panel`).evaluate(p => {
    const box = p.getBoundingClientRect();
    return { over: p.scrollHeight - p.clientHeight, out: [...p.querySelectorAll('*')].filter(n => n.getClientRects().length &&
      n.getBoundingClientRect().bottom > box.bottom + 0.5 && getComputedStyle(n).position !== 'absolute').length };
  });
  const vectors = JSON.parse(await readFile(path.join(root, 'tests/fixtures/formula-vectors.json'), 'utf8'));
  const cases = vectors.cases.filter(c => x.vectors.test(c.js) && !c.raises);
  const still = await readFile(path.join(root, x.still), 'utf8');
  const stillPart = still.match(new RegExp(`data-part="${x.part}" ${x.attr}="([^"]*)"`))?.[1];
  for (const width of [360, 1366]) {
    const height = {};
    for (const script of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const seen = [], say = s => seen.push(s);
      page.on('console', m => { if (m.type() === 'error' && script) say(`console: ${m.text()}`); });
      page.on('pageerror', e => say(`page error: ${e.message}`));
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
      if (!script) await page.route(`**/kit/${x.script}.js`, r => r.abort());
      await page.goto(base + route);
      await settled(page, `/kit/${x.script}.js`);
      const demo = page.locator(tag);
      await demo.scrollIntoViewIfNeeded();
      height[script] = (await demo.boundingBox())?.height;
      if (!script) {
        const img = await demo.locator(':scope > img').evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false);
        if (!img) say('no still image before the script loads');
      } else if (!(await demo.locator(`svg [data-part=${x.part}]`).count())) say('the live figure did not render');
      else {
        if (width === 1366) {
          // the port in this engine, on its golden vectors (the Node test runs them in V8 only): bit for bit
          const wrong = await page.evaluate(async cs => {
            const fx = await import('/kit/formulas.js');
            return cs.filter(c => JSON.stringify(fx[c.js](...c.args)) !== JSON.stringify(c.expected)).map(c => c.js);
          }, cases);
          if (cases.length < 20) say(`only ${cases.length} vectors`);
          if (wrong.length) say(`the port differs from the Python in this engine on ${wrong.length} vectors: ${wrong.slice(0, 3).join('; ')}`);
          const live = await demo.locator(`[data-part=${x.part}]`).getAttribute(x.attr);
          if (live !== stillPart) say(`the live figure's ${x.part} (${live}) is not the still's (${stillPart})`);
        }
        const panel = await overflow(demo);
        if (panel.over > 0 || panel.out) say(`the panel overflows (${panel.over}px, ${panel.out} elements)`);
        const unlabelled = await demo.evaluate(d => [...d.querySelectorAll('input, select')].filter(i => !i.labels?.length).map(i => i.name));
        if (unlabelled.length) say(`controls without a label: ${unlabelled.join(', ')}`);
        const tile = k => demo.locator(`[data-out=${k}]`).textContent();
        const status = () => demo.locator(`.${px}-status`).textContent();
        if (await status()) say('the status line spoke before anyone touched the demo');
        for (const [k, want] of Object.entries(x.start)) if ((await tile(k)) !== want) say(`the default reads ${k} ${await tile(k)}, not ${want}`);
        // the site is light, whatever the reader prefers; the element follows the page
        await page.emulateMedia({ colorScheme: 'dark' });
        if ((await demo.getAttribute('data-theme')) !== 'light') say('the demo turned dark on a light page');
        for (const theme of ['light', 'dark']) {
          await demo.evaluate((d, t) => d.setAttribute('theme', t), theme);
          if ((await demo.getAttribute('data-theme')) !== theme) say(`theme="${theme}" is not applied`);
          for (const c of x.contrast) {
            const [sel, at] = Array.isArray(c) ? c : [c, 'color'];
            const ratio = await contrast(page, `${tag} ${sel}`, at);
            if (!(ratio >= 4.5)) say(`${theme}: ${sel} has a contrast of ${ratio.toFixed(2)}, under 4.5`);
          }
        }
        await demo.evaluate(d => d.removeAttribute('theme'));
        await page.emulateMedia({ colorScheme: 'light' });
        // the panel holds and the tiles' words fit for extreme settings (the last is the page's own)
        const original = await demo.evaluate(d => Object.fromEntries([...d.attributes].map(a => [a.name, a.value])));
        for (const [i, shape] of x.shapes.entries()) {
          const cut = await demo.evaluate((d, [a, o]) => {
            for (const k of d.constructor.observedAttributes) if (k !== 'theme') {
              if (k in a) d.setAttribute(k, a[k]); else if (k in o) d.setAttribute(k, o[k]); else d.removeAttribute(k);
            }
            return [...d.querySelectorAll('[class$=-tile] b, [class$=-tile] span')].filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent);
          }, [shape, original]);
          if (cut.length) say(`${JSON.stringify(shape)}: tile text cut off: ${cut.join('; ')}`);
          const note = x.notes?.[i] && await demo.locator(`.${px}-note`).textContent();
          if (note && !x.notes[i].test(note)) say(`${JSON.stringify(shape)}: the note reads "${note}", not ${x.notes[i]}`);
          const after = await overflow(demo);
          if (after.over > 0 || after.out) say(`${JSON.stringify(shape)}: the panel overflows (${after.over}px, ${after.out} elements)`);
        }
        // the keyboard on a slider changes the verdict
        const slider = page.getByRole('slider', { name: x.slider.name });
        await slider.focus();
        for (let i = 0; i < x.slider.presses; i++) await slider.press('ArrowRight');
        if (!x.slider.spoken.test(await slider.getAttribute('aria-valuetext') || '')) say('the slider has no spoken value');
        if ((await tile('verdict')) !== x.slider.verdict || (await tile(x.slider.tile[0])) !== x.slider.tile[1])
          say(`after the slider: ${await tile('verdict')}, ${x.slider.tile[0]} ${await tile(x.slider.tile[0])}`);
        if ((await demo.locator('[data-out=verdict-tile]').getAttribute('data-verdict')) !== 'fail') say('the fail is not marked');
        // a radio, pressed and held
        const read = () => x.radio.changes ? tile(x.radio.changes) : demo.locator(`[data-part=${x.radio.part}]`).getAttribute('d');
        const before = await read();
        await hold(page, demo.locator('label', { hasText: x.radio.label }));
        if (!(await page.getByRole('radio', { name: x.radio.label }).isChecked()) || !x.radio.check(before, await read()))
          say(`pressing "${x.radio.label}" did not change the result (${before}, then ${await read()})`);
        const moved = await overflow(demo);
        if (moved.over > 0 || moved.out) say(`after the controls changed, the panel overflows (${moved.over}px, ${moved.out} elements)`);
        await page.waitForFunction(sel => document.querySelector(sel)?.textContent, `${tag} .${px}-status`, { timeout: 3000 })
          .catch(() => say('the status line does not announce the result after an input'));
        const after = (await demo.boundingBox())?.height;
        if (!(Math.abs(after - height[script]) < 0.5)) say(`the explorer changed height with its controls (${height[script]}px, then ${after}px)`);
      }
      for (const s of seen) out.push(`${width}px ${route} ${name}${script ? '' : ' (before its script)'}: ${s}`);
      await page.close();
    }
    if (!(Math.abs(height.true - height.false) < 0.5)) out.push(`${width}px ${name}: ${height.false}px tall before its script, ${height.true}px after`);
  }
  const quiet = await browser.newPage();
  await quiet.goto(base + route);
  await settled(quiet, `/kit/${x.script}.js`);
  await quiet.waitForTimeout(800);
  if (await quiet.locator(`${tag} .${px}-status`).textContent()) out.push(`the ${name} status line spoke on page load`);
  await quiet.close();
  return out;
}

/** Diagrams drawn by the build (#132, tools/site-diagrams.mjs). Drawn in the reader's browser, a diagram near the top
 * moved the page twice as it loaded (0.58 on /lessons/process/agent-process at 360 px, 0.10 on /docs/style-guide at
 * 1366 px); Google calls a page good under 0.1. On the pages below, at phone and desktop widths: the layout shift while
 * the page loads stays under DIAGRAM_SHIFT (Chrome; WebKit does not report shifts), the diagrams show with script off,
 * each the same size as with script on (so the script changes no diagram, anywhere on the page, in either engine), the
 * sideways-scroll hint shows exactly when its diagram overflows, without script too, and no page downloads Mermaid
 * (DIAGRAM_SHIFT is set at the top, with the routes). */
async function drawnDiagramProblems() {
  const out = [];
  const PAGES = ['/docs/toolkit', '/docs/style-guide', '/docs/vision', '/lessons/process/agent-process'];
  const boxes = page => page.$$eval('.cad-diagram', figs => figs.map(f => {
    const r = f.getBoundingClientRect(), svg = f.querySelector('.cad-diagram-view svg')?.getBoundingClientRect();
    const view = f.querySelector('.cad-diagram-view'), hint = f.querySelector('.cad-diagram-hint');
    return { state: f.dataset.state, box: [r.width, r.height].map(n => Math.round(n * 2) / 2), svg: svg && [svg.width, svg.height],
      overflows: view.scrollWidth > view.clientWidth + 1, hint: hint.getBoundingClientRect().height > 0 && getComputedStyle(hint).display !== 'none',
      clipped: hint.scrollHeight > hint.clientHeight + 1 };
  }));
  for (const width of [320, 360, 1366]) for (const route of PAGES) {
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
    // Measured once the kit has adopted every drawn figure and none is being drawn again, so a Mermaid download, if
    // any, has happened (not at networkidle: in WebKit on CI it never came on /docs/vision, #154).
    await page.goto(base + route);
    await settled(page);
    await page.waitForFunction(() => !document.querySelector('pre.mermaid, code.language-mermaid') &&
      [...document.querySelectorAll('.cad-diagram')].every(f => f.dataset.state === 'ready' || f.dataset.state === 'error'), null, { timeout: 20000 })
      .catch(() => out.push(`${where}: diagrams did not finish drawing`));
    const after = await boxes(page), shift = await page.evaluate(() => window.__shift);
    await context.close();
    if (!before.length) { out.push(`${where}: no diagram on the page`); continue; }
    if (shift > DIAGRAM_SHIFT) out.push(`${where}: the page moved by ${shift.toFixed(3)} while it loaded (limit ${DIAGRAM_SHIFT})`);
    if (runtime.length) out.push(`${where}: downloaded Mermaid (${runtime.length}x), though the build drew every diagram`);
    before.forEach((b, i) => {
      if (b.state !== 'ready' || !b.svg || b.svg[0] < 100 || b.svg[1] < 30) out.push(`${where}: diagram ${i + 1} does not show without script (${JSON.stringify(b)})`);
      const a = after[i];
      if (!a || a.box.join() !== b.box.join()) out.push(`${where}: diagram ${i + 1} is ${b.box.join(' x ')} px without script and ${a?.box.join(' x ')} px with it`);
      for (const [label, m] of [['without script', b], ['with script', a]])
        if (m && m.hint !== m.overflows) out.push(`${where}: diagram ${i + 1} ${m.overflows ? 'overflows' : 'fits'} but its scroll hint is ${m.hint ? 'shown' : 'hidden'} ${label}`);
        else if (m?.hint && m.clipped) out.push(`${where}: diagram ${i + 1}'s scroll hint is cut off ${label}`);
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
  const frames = (page, count = 10) => page.evaluate(count => new Promise(done => {
    let n = 0;
    const next = () => (++n >= count ? done() : requestAnimationFrame(next));
    requestAnimationFrame(next);
  }), count);
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
      await page.goto(base + '/docs/compliant');
      await settled(page, '/kit/cantilever.js');
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
        // Pause the way a person does, with a press that lasts a few frames. WebKit drops the click of a press whose
        // node the page replaces before the release. The demo used to rewrite the button's label on every frame, so in
        // WebKit a held press never paused it, and a quick test click failed only when a frame fell inside it (#211).
        await demo.locator('.cc-play').hover();
        await page.mouse.down();
        await frames(page, 3);
        await page.mouse.up();
        // The click handler pauses and draws the paused frame itself, so the label reads Play once the click lands.
        const stopped = await page.waitForFunction(() => document.querySelector('cad-cantilever .cc-play')?.textContent === 'Play',
          null, { timeout: 3000 }).then(() => true, () => false);
        const paused = await beam(page);
        await frames(page);
        if (!stopped) say('the pause button does not stop it: a press held for 3 frames was not a click');
        else if ((await beam(page)) !== paused) say('the pause button does not stop it: the beam moves while paused');
        // Play carries on from the frame on screen (full deflection), not from wherever a page clock has got to.
        // Not paused, the click below would pause it instead: that failure is already reported once.
        const resumed = stopped && await page.evaluate(() => {
          const d = document.querySelector('cad-cantilever');
          d.querySelector('.cc-play').click();                    // renders in the click handler, before any frame
          return d.querySelector('[data-part=beam]').getAttribute('points');
        });
        if (stopped && resumed !== paused) say('Play does not carry on from the paused frame');
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
  await late.goto(base + '/docs/compliant');
  await settled(late, '/kit/cantilever.js');
  const lateJump = await firstFrameProblem(late);
  if (lateJump) out.push(`1366px /docs/compliant demo, its script 2.6 s late: ${lateJump}`);
  await late.close();
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + '/docs/compliant');
  await settled(reduced, '/kit/cantilever.js');
  const first = await beam(reduced);
  await reduced.waitForTimeout(800);                 // past the status line's 700 ms announcement delay (below)
  if (!first || (await beam(reduced)) !== first || (await reduced.locator('cad-cantilever .cc-play').textContent()) !== 'Play')
    out.push('reduced motion: the demo is animating');
  // Over 700 ms (the announcement delay) since the element drew, with no input: the polite live region stays empty,
  // so a screen reader does not read the result out of context on page load.
  if (await reduced.locator('cad-cantilever .cc-status').textContent())
    out.push('the status line spoke on page load, with nobody touching the demo');
  await reduced.close();
  return out;
}

/** The four-bar animator (the kit's <cad-fourbar>) on /docs/linkages, at phone and desktop widths, under the site CSP:
 * the port reproduces the Python's golden vectors in this browser engine too; the element replaces its still at exactly
 * the reserved size (no layout shift) and its first live frame is the still, however late the script arrives; its
 * panel never overflows; every control has a label; it animates, pauses and carries on from the paused frame; the
 * keyboard on a slider changes the class, and a non-Grashof linkage stops at its limits (locked, mu 0) instead of
 * jumping; the assembly switches; its colours keep their contrast in light and dark; it holds still under reduced
 * motion; and its status line speaks after an input but not on page load, with no console errors. */
async function fourbarProblems() {
  const out = [], route = '/docs/linkages';
  const crank = page => page.locator('cad-fourbar [data-part=crank]').getAttribute('points');
  const firstFrame = () => new MutationObserver((records, observer) => {
    const r = records.find(m => m.attributeName === 'points' && m.target.dataset?.part === 'crank');
    if (r) { window.fbFirstFrame = { still: r.oldValue, live: r.target.getAttribute('points') }; observer.disconnect(); }
  }).observe(document, { subtree: true, attributes: true, attributeOldValue: true, attributeFilter: ['points'] });
  const firstFrameProblem = async page => {
    const first = await page.evaluate(() => window.fbFirstFrame);
    return !first ? 'the first live frame was not seen' :
      first.still !== first.live ? 'the first live frame is not the still: the crank jumps when the script takes over' : null;
  };
  const frames = (page, count = 10) => page.evaluate(count => new Promise(done => {
    let n = 0;
    const next = () => (++n >= count ? done() : requestAnimationFrame(next));
    requestAnimationFrame(next);
  }), count);
  // Pause the way a person does, with a press that lasts a few frames: WebKit drops the click of a press whose node the
  // page replaces before the release, and the demo used to rewrite the button's label on every frame (#211; the
  // compliant block says more). A quick click passes then, unless a frame falls inside it.
  const hold = async (page, locator) => {
    await locator.hover();
    await page.mouse.down();
    await frames(page, 3);
    await page.mouse.up();
  };
  // WCAG contrast of an element's text against the element's background (the nearest one that is not transparent)
  const contrast = (page, selector, attr = 'color') => page.evaluate(([sel, at]) => {
    const rgb = c => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const el = document.querySelector(sel);
    let bg = el, back = 'rgba(0, 0, 0, 0)';
    while (bg && /rgba\(.*, 0\)|transparent/.test(back = getComputedStyle(bg).backgroundColor)) bg = bg.parentElement;
    const fore = at === 'color' ? getComputedStyle(el).color : getComputedStyle(el).fill;
    const [l1, l2] = [lum(fore), lum(back)].sort((x, y) => y - x);
    return (l1 + 0.05) / (l2 + 0.05);
  }, [selector, attr]);
  const vectors = JSON.parse(await readFile(path.join(root, 'tests/fixtures/formula-vectors.json'), 'utf8'));
  const four = vectors.cases.filter(c => ['grashof', 'fourbarAngles', 'transmissionAngle', 'fourbarInputLimits'].includes(c.js));
  for (const width of [360, 1366]) {
    const height = {};
    for (const script of [false, true]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const seen = [], say = s => seen.push(s);
      page.on('console', m => { if (m.type() === 'error' && script) say(`console: ${m.text()}`); });
      page.on('pageerror', e => say(`page error: ${e.message}`));
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
      await page.addInitScript(firstFrame);
      if (!script) await page.route('**/kit/fourbar.js', r => r.abort());
      await page.goto(base + route);
      await settled(page, '/kit/fourbar.js');
      const demo = page.locator('cad-fourbar');
      await demo.scrollIntoViewIfNeeded();
      height[script] = (await demo.boundingBox())?.height;
      if (!script) {
        const img = await demo.locator(':scope > img').evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false);
        if (!img) say('no still image before the script loads');
      } else if (!(await demo.locator('svg [data-part=crank]').count())) say('the live figure did not render');
      else {
        // the port in this engine, on the four-bar golden vectors (the Node test runs them in V8 only)
        if (width === 1366) {
          const wrong = await page.evaluate(async ([cases, tol]) => {
            const fx = await import('/kit/formulas.js'), bad = [];
            const near = (g, w, t, angles) => {
              if (typeof w === 'number') {
                if (typeof g !== 'number') return false;
                const d = Math.abs(g - w), apart = angles ? Math.min(d, Math.abs(d - 2 * Math.PI)) : d;
                return apart <= Math.max(t.abs, t.rel * (angles ? Math.max(1, Math.abs(w)) : Math.abs(w)));
              }
              if (w && typeof w === 'object') return !!g && Object.keys(w).every(k => near(g[k], w[k], t, angles));
              return g === w;
            };
            for (const c of cases) if (!near(fx[c.js](...c.args), c.expected, c.tolerance || tol, c.angles)) bad.push(`${c.js}(${c.args})`);
            return bad;
          }, [four, vectors.tolerance]);
          if (wrong.length) say(`the port differs from the Python in this engine on ${wrong.length} vectors: ${wrong.slice(0, 3).join('; ')}`);
        }
        const jump = await firstFrameProblem(page);
        if (jump) say(jump);
        const panel = await demo.locator('.fb-panel').evaluate(p => {
          const box = p.getBoundingClientRect();
          return { over: p.scrollHeight - p.clientHeight, out: [...p.querySelectorAll('*')].filter(n => n.getClientRects().length &&
            n.getBoundingClientRect().bottom > box.bottom + 0.5 && getComputedStyle(n).position !== 'absolute').length };
        });
        if (panel.over > 0 || panel.out) say(`the panel overflows (${panel.over}px, ${panel.out} elements)`);
        const unlabelled = await demo.evaluate(d => [...d.querySelectorAll('input')].filter(i => !i.labels?.length).map(i => i.name));
        if (unlabelled.length) say(`controls without a label: ${unlabelled.join(', ')}`);
        const before = await crank(page);
        await page.waitForFunction(p => document.querySelector('cad-fourbar [data-part=crank]').getAttribute('points') !== p,
          before, { timeout: 3000 }).catch(() => say('the crank is not turning'));
        const status = () => demo.locator('.fb-status').textContent();
        if (await status()) say('the status line spoke before anyone touched the demo');
        if ((await demo.locator('[data-out=class]').textContent()) !== 'Crank-rocker') say('the default linkage is not a crank-rocker');
        // the site is light, whatever the reader prefers; the element follows the page
        await page.emulateMedia({ colorScheme: 'dark' });
        if ((await demo.getAttribute('data-theme')) !== 'light') say('the demo turned dark on a light page');
        for (const theme of ['light', 'dark']) {
          await demo.evaluate((d, t) => d.setAttribute('theme', t), theme);
          if ((await demo.getAttribute('data-theme')) !== theme) say(`theme="${theme}" is not applied`);
          for (const [sel, at, min] of [['cad-fourbar .fb-tile b', 'color', 4.5], ['cad-fourbar .fb-note', 'color', 4.5],
            ['cad-fourbar [data-part=label-input]', 'fill', 3], ['cad-fourbar [data-part=pill]', 'fill', 3]]) {
            const ratio = await contrast(page, sel, at);
            if (!(ratio >= min)) say(`${theme}: ${sel} has a contrast of ${ratio.toFixed(2)}, under ${min}`);
          }
        }
        await demo.evaluate(d => d.removeAttribute('theme'));
        await page.emulateMedia({ colorScheme: 'light' });
        // the tiles' words fit for every kind of linkage (one line each at desktop width, cut with an ellipsis if not)
        for (const links of [[80, 40, 120, 100], [80, 100, 40, 120], [150, 70, 70, 10], [100, 80, 70, 60], [150, 10, 10, 20], [40, 120, 80, 100]]) {
          const cut = await demo.evaluate((d, lengths) => {
            ['crank', 'coupler', 'rocker', 'ground'].forEach((k, i) => d.setAttribute(k, lengths[i]));
            return [...d.querySelectorAll('.fb-tile b, .fb-tile span')].filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent);
          }, links);
          if (cut.length) say(`${links}: tile text cut off: ${cut.join('; ')}`);
        }                                                                               // ends on the page's linkage
        // the other assembly, on the page's crank-rocker, paused: the coupler moves to where the ghost was. Not on a
        // rocking input, which dwells at its limits, where the two assemblies meet: paused there, nothing moves.
        await demo.evaluate(d => d.querySelector('.fb-play').click());     // pause, so the frames compare (the press: below)
        if ((await demo.locator('.fb-play').textContent()) !== 'Play') say('the demo was not playing before the assembly switch, so a click started it');
        const coupler = await demo.locator('[data-part=coupler]').getAttribute('points');
        await page.getByLabel('Crossed').check();
        const ghost = await demo.locator('[data-part=ghost]').getAttribute('points');
        if ((await demo.locator('[data-part=coupler]').getAttribute('points')) === coupler || !ghost) say('switching the assembly changed nothing');
        await demo.getByRole('radio', { name: 'Open', exact: true }).check();
        await demo.locator('.fb-play').click();                                         // play again
        // the keyboard: the crank to its longest makes the linkage non-Grashof, and the input then rocks between limits
        const slider = page.getByRole('slider', { name: /^Crank a/ });
        await slider.focus();
        await slider.press('End');
        if (!/millimetres$/.test(await slider.getAttribute('aria-valuetext') || '')) say('the slider has no spoken value');
        const cls = await demo.locator('[data-out=class]').textContent(), travel = await demo.locator('[data-out=travel]').textContent();
        if (cls !== 'Triple rocker' || travel !== '±104.5°') say(`a 150 mm crank gives ${cls}, ${travel}, not a triple rocker rocking ±104.5°`);
        if (!(await demo.locator('[data-part=no-close]').count()) || !(await demo.locator('[data-part=chart-no-close]').count()))
          say('where the links cannot close is not marked');
        if (width === 1366) {
          // it stops at a limit: the input reads ±104.5° and the linkage is locked (mu 0) before it turns back
          const locked = await page.waitForFunction(() => {
            const fig = document.querySelector('cad-fourbar');
            return /^θ₂ -?104\.5°$/.test(fig.querySelector('[data-part=label-input]').textContent) &&
              fig.querySelector('[data-part=label-mu]').textContent === 'locked · μ 0°';
          }, null, { timeout: 12000, polling: 'raf' }).then(() => true, () => false);
          if (!locked) say('the triple rocker never stops at its limit, locked');
          const beyond = await page.evaluate(() => new Promise(done => {
            let worst = 0, n = 0;
            const tick = () => {
              const t = parseFloat(document.querySelector('cad-fourbar [data-part=label-input]').textContent.replace(/^θ₂ /, ''));
              worst = Math.max(worst, Math.abs(t));
              if (++n < 120) requestAnimationFrame(tick); else done(worst);
            };
            requestAnimationFrame(tick);
          }));
          if (beyond > 104.5) say(`the input went to ${beyond}°, past its limit`);
        }
        await frames(page);
        await hold(page, demo.locator('.fb-play'));
        // The click handler pauses and draws the paused frame itself, so the label reads Play once the click lands.
        const stopped = await page.waitForFunction(() => document.querySelector('cad-fourbar .fb-play')?.textContent === 'Play',
          null, { timeout: 3000 }).then(() => true, () => false);
        const paused = await crank(page);
        await frames(page);
        if (!stopped) say('the pause button does not stop it: a press held for 3 frames was not a click');
        else if ((await crank(page)) !== paused) say('the pause button does not stop it: the crank moves while paused');
        // Not paused, the click below would pause it instead: that failure is already reported once.
        const resumed = stopped && await page.evaluate(() => {
          const d = document.querySelector('cad-fourbar');
          d.querySelector('.fb-play').click();
          return d.querySelector('[data-part=crank]').getAttribute('points');
        });
        if (stopped && resumed !== paused) say('Play does not carry on from the paused frame');
        await page.waitForFunction(() => document.querySelector('cad-fourbar .fb-status')?.textContent,
          null, { timeout: 3000 }).catch(() => say('the status line does not announce the result after an input'));
      }
      for (const s of seen) out.push(`${width}px ${route} four-bar${script ? '' : ' (before its script)'}: ${s}`);
      await page.close();
    }
    if (!(Math.abs(height.true - height.false) < 0.5)) out.push(`${width}px four-bar: ${height.false}px tall before its script, ${height.true}px after`);
  }
  const late = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  await late.addInitScript(firstFrame);
  await late.route('**/kit/fourbar.js', async r => { await new Promise(ok => setTimeout(ok, 2600)); await r.continue(); });
  await late.goto(base + route);
  await settled(late, '/kit/fourbar.js');
  const lateJump = await firstFrameProblem(late);
  if (lateJump) out.push(`1366px ${route} four-bar, its script 2.6 s late: ${lateJump}`);
  await late.close();
  const reduced = await browser.newPage({ reducedMotion: 'reduce' });
  await reduced.goto(base + route);
  await settled(reduced, '/kit/fourbar.js');
  const first = await crank(reduced);
  await reduced.waitForTimeout(800);                 // past the status line's 700 ms announcement delay
  if (!first || (await crank(reduced)) !== first || (await reduced.locator('cad-fourbar .fb-play').textContent()) !== 'Play')
    out.push('reduced motion: the four-bar is moving');
  if (await reduced.locator('cad-fourbar .fb-status').textContent()) out.push('the four-bar status line spoke on page load');
  await reduced.close();
  return out;
}

/** The page tree's fold (#134) on /docs/toolkit, at phone and desktop widths, with nav.js as it is, slow (held back until
 * the first paint is measured), blocked, failing (it throws) and with no script at all. Phones: a closed native
 * <details> that a click, Enter or Space opens and closes, before or without the script. Wide screens: no toggle, and
 * the tree on screen (hit-tested: Playwright's own WebKit visibility check calls anything inside a closed <details>
 * hidden), staying in view as the page scrolls, so the <details> does not box the sticky panel in. Nothing moves when
 * the script arrives, and the script never closes a fold the reader opened. */
async function foldProblems() {
  const out = [];
  // Every box the fold could move, in page coordinates (inside the panel, relative to its content: on a wide screen the
  // script may scroll the panel to show this page, which moves nothing).
  const boxes = () => {
    const panel = document.querySelector('cad-nav .cad-nav-panel'), p = panel.getBoundingClientRect();
    // The nav and the article grow with the article's diagrams as they render: their place and width, not height.
    const box = (sel, inPanel, sized = true) => {
      const el = document.querySelector(sel);
      if (!el || !el.getClientRects().length) return null;
      const r = el.getBoundingClientRect(), y = inPanel ? r.top - p.top + panel.scrollTop : r.top + scrollY;
      return [r.left, y, r.width, ...sized ? [r.height] : []].map(v => Math.round(v * 2) / 2).join(',');
    };
    return { nav: box('cad-nav', false, false), toggle: box('cad-nav .cad-nav-toggle'), panel: box('cad-nav .cad-nav-panel'),
      filter: box('cad-nav .cad-nav-filter'), group: box('cad-nav .cad-nav-group > summary', true),
      current: box('cad-nav a[aria-current=page]', true), title: box('.prose h1'), article: box('.doc-main', false, false) };
  };
  // On screen for a reader: it has a box and is what the point at its middle hits (after scrolling it into the panel's
  // view, away from the filter at the top).
  const shows = sel => {
    const el = document.querySelector(sel);
    if (!el?.getClientRects().length) return false;
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.left + Math.min(r.width / 2, 24), r.top + r.height / 2);
    return !!hit && (hit === el || el.contains(hit));
  };
  for (const width of [360, 1366]) for (const mode of ['script', 'slow', 'blocked', 'failing', 'none']) {
    const context = await browser.newContext({ viewport: { width, height: 800 }, javaScriptEnabled: mode !== 'none' });
    const page = await context.newPage();
    const seen = [], say = s => seen.push(s);
    let arrive;
    const held = new Promise(ok => { arrive = ok; });
    if (mode === 'slow') await page.route('**/kit/nav.js', async r => { await held; await r.continue(); });
    if (mode === 'blocked') await page.route('**/kit/nav.js', r => r.abort());
    if (mode === 'failing') await page.route('**/kit/nav.js', r => r.fulfill({ contentType: 'text/javascript', body: 'throw new Error("nav.js fails on purpose")' }));
    await page.goto(base + '/docs/toolkit', { waitUntil: mode === 'slow' ? 'domcontentloaded' : 'load' });
    const js = mode !== 'none';
    // nav.js has run or failed (with JavaScript off, Playwright cannot wait on a promise in the page; held back, it
    // has not arrived, and the rest of the page settles first: its diagrams render while nav.js is held back).
    if (js && mode !== 'slow') await settled(page);
    if (mode === 'slow') await page.waitForFunction(() => !document.querySelector('pre.mermaid, code.language-mermaid') &&
      [...document.querySelectorAll('.cad-diagram')].every(f => f.dataset.state === 'ready' || f.dataset.state === 'error'), null, { timeout: 20000 })
      .catch(() => say('diagrams did not finish rendering'));
    await painted(page, js);
    const nav = page.locator('cad-nav'), toggle = nav.locator('.cad-nav-toggle'), fold = nav.locator('details.cad-nav-fold');
    const open = () => fold.evaluate(d => d.open);
    if (!(await fold.count())) say('no <details class="cad-nav-fold"> around the tree');
    else if (width < 1100) {
      if (!(await toggle.isVisible())) say('no "Pages and contents" toggle');
      else if (await open() || await page.evaluate(shows, 'cad-nav a[aria-current=page]')) say('the tree is open before the toggle is pressed');
      else {
        await toggle.click();
        if (!(await open()) || !(await page.evaluate(shows, 'cad-nav a[aria-current=page]'))) say('a tap on the toggle does not open the tree');
        await toggle.click();
        if (await open()) say('a second tap does not close it');
        await toggle.focus();
        await page.keyboard.press('Enter');
        if (!(await open()) || !(await page.evaluate(shows, 'cad-nav a[aria-current=page]'))) say('Enter on the toggle does not open the tree');
        await page.keyboard.press('Space');
        if (await open()) say('Space on the toggle does not close it');
        await page.keyboard.press('Space');
        if (!(await open())) say('Space on the toggle does not open it');
      }
    } else {
      if ((await toggle.isVisible()) || (await toggle.evaluate(t => t.getClientRects().length))) say('a toggle shows on a wide screen');
      if (!(await page.evaluate(shows, 'cad-nav .cad-nav-group > summary'))) say('the tree is not on screen');
      if (!(await page.evaluate(shows, 'cad-nav a[aria-current=page]'))) say('this page is not on screen in the tree');
      const filter = await page.evaluate(shows, 'cad-nav .cad-nav-filter');
      if (filter !== (mode !== 'none')) say(filter ? 'a filter shows that cannot work without script' : 'the filter is not on screen');
      await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, document.body.scrollHeight / 2); });
      await painted(page, js);
      const y = await nav.locator('.cad-nav-panel').evaluate(p => p.getBoundingClientRect().top);
      if (!(y >= 0 && y <= 200)) say(`the tree scrolls away with the page (its top at ${Math.round(y)}px), so the fold boxes the sticky panel in`);
      await page.evaluate(() => { scrollTo(0, 0); document.documentElement.style.scrollBehavior = ''; });
    }
    if (mode === 'slow' && await fold.count()) {
      // The reader opens the tree on a phone before the script has arrived; when it does, the tree stays open and
      // nothing on the page moves (the boxes from the first paint, with the fold as the reader left it).
      if (width < 1100) {
        if (!(await open())) await toggle.click();
        if (!(await open())) say('the toggle does not open the tree before the script arrives');
      }
      await page.evaluate(() => scrollTo(0, 0));
      const before = await page.evaluate(boxes);
      arrive();
      await page.waitForFunction(() => customElements.get('cad-nav'), null, { timeout: 10000 });
      await painted(page);
      await page.evaluate(() => scrollTo(0, 0));
      const after = await page.evaluate(boxes);
      for (const k of Object.keys(before)) if (before[k] !== after[k]) say(`the ${k} moved when the script arrived: ${before[k]} -> ${after[k]}`);
      if (width < 1100 && !(await open())) say('the script closed the tree the reader had opened');
      if (width >= 1100 && !(await open())) say('the script did not open the fold on a wide screen (browsers without ::details-content need it)');
      // Chrome's own measure over the whole load, the reader's taps excluded (hadRecentInput).
      const shift = await page.evaluate(() => new Promise(done => {
        if (!PerformanceObserver.supportedEntryTypes?.includes('layout-shift')) return done(0);
        let sum = 0;
        new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) sum += e.value; }).observe({ type: 'layout-shift', buffered: true });
        setTimeout(() => done(sum), 200);
      }));
      if (shift > 0.05) say(`layout shift ${shift.toFixed(3)} with the script late (the limit is 0.05)`);
    }
    for (const s of seen) out.push(`${width}px /docs/toolkit fold, nav.js ${{ script: 'loaded', slow: 'late', blocked: 'blocked', failing: 'failing', none: 'off (no script)' }[mode]}: ${s}`);
    await context.close();
  }
  // The window crossing the breakpoint: the fold the script opened for a wide window closes again on a phone, and one
  // the reader opened on a phone stays open through a wide window and back.
  const turn = await browser.newPage({ viewport: { width: 1366, height: 800 } });
  await turn.goto(base + '/docs/toolkit');
  await settled(turn);
  const isOpen = () => turn.locator('details.cad-nav-fold').evaluate(d => d.open, null, { timeout: 2000 }).catch(() => null);
  await turn.setViewportSize({ width: 360, height: 800 });
  await turn.waitForFunction(() => !document.querySelector('details.cad-nav-fold')?.open, null, { timeout: 2000 }).catch(() => {});
  if ((await isOpen()) !== false) out.push('1366 -> 360px: the fold the script opened for the wide window stays open on the phone');
  await turn.locator('.cad-nav-toggle').click();
  await turn.setViewportSize({ width: 1366, height: 800 });
  await turn.waitForTimeout(100);                               // a frame at each width, so the script sees both
  await turn.setViewportSize({ width: 360, height: 800 });
  await turn.waitForTimeout(100);
  if ((await isOpen()) !== true) out.push('360 -> 1366 -> 360px: the fold the reader opened was closed');
  // Printed from a wide window, where the script opened the fold: the tree does not print, and on paper wide enough for
  // the site's grid (landscape A3, 1500 px) the article keeps the width, not the tree's empty column (#209 review).
  for (const w of [1366, 1500]) {
    await turn.setViewportSize({ width: w, height: 800 });
    await turn.emulateMedia({ media: 'print' });
    const paper = await turn.evaluate(() => ({ nav: getComputedStyle(document.querySelector('cad-nav')).display,
      article: document.querySelector('.doc-main').getBoundingClientRect().width, rail: document.querySelector('.doc-rail')?.getClientRects().length || 0 }));
    if (paper.nav !== 'none') out.push(`print at ${w}px: the page tree prints`);
    if (paper.article < 600) out.push(`print at ${w}px: the article prints ${Math.round(paper.article)}px wide`);
    if (paper.rail) out.push(`print at ${w}px: the "On this page" column prints`);
    await turn.emulateMedia({ media: 'screen' });
  }
  await turn.close();
  // No link text around the filter pill while the tree is scrolled (#134): with a link under the filter's top edge, the
  // points just inside the pill's box at its rounded corners, and in the strips above and below it, hit the panel's cover.
  const desk = await browser.newPage({ viewport: { width: 1366, height: 800 } });
  await desk.goto(base + '/docs/toolkit');
  await settled(desk);
  const corners = await desk.locator('cad-nav .cad-nav-panel').evaluate(panel => {
    for (const g of panel.querySelectorAll('details')) g.open = true;
    const f = panel.querySelector('.cad-nav-filter');
    const under = () => { const r = f.getBoundingClientRect(); return [...panel.querySelectorAll('a')].find(a => { const q = a.getBoundingClientRect(); return q.top < r.top + 2 && q.bottom > r.top + 2; }); };
    for (panel.scrollTop = 40; !under() && panel.scrollTop < panel.scrollHeight - panel.clientHeight; panel.scrollTop += 7);
    if (!under()) return 'no link ever scrolls under the filter, so this check tests nothing';
    const r = f.getBoundingClientRect(), top = panel.getBoundingClientRect().top;
    const hits = [[r.left + 1.5, r.top + 1.5], [r.right - 1.5, r.top + 1.5], [r.left + 1.5, r.bottom - 1.5], [r.right - 1.5, r.bottom - 1.5],
      [r.left + r.width / 2, top + 1.5], [r.left + r.width / 2, r.bottom + 4]]          // and the strips above and below it
      .map(([x, y]) => document.elementFromPoint(x, y)).filter(h => h?.closest('a'));
    return hits.length ? `link text shows in ${hits.length} place(s) around the filter: ${hits.map(h => h.closest('a').textContent).join(', ')}` : '';
  });
  if (corners) out.push(`1366px /docs/toolkit, the tree scrolled: ${corners}`);
  await desk.close();
  return out;
}

/** Jumps through the outline on a big screen (2560 x 1440, /docs/explore, the site's smooth scrolling), with the input
 * a desktop browser would give simulated, since headless browsers will not let a real wheel interrupt a smooth scroll
 * (#123 review 4):
 * - a wheel over the rail or the tree partway through the jump, and the page scroll it makes, releases it: the mark
 *   follows the reading line, not the heading the reader turned away from;
 * - a wheel that only scrolls the tree (it can still scroll that way) leaves the jump marked;
 * - a jump whose scroll stalls for 300 ms partway (a frame slow to paint, #158) still marks its heading once it lands. */
async function jumpProblems() {
  const out = [];
  const page = await browser.newPage({ viewport: { width: 2560, height: 1440 } });
  await page.goto(base + '/docs/explore');
  await settled(page);
  const settle = () => page.evaluate(() => new Promise(done => {
    let last = -1, still = 0;
    const tick = () => { if (scrollY === last) { if (++still > 15) return done(); } else { still = 0; last = scrollY; } requestAnimationFrame(tick); };
    tick(); setTimeout(done, 10000);
  }));
  const partway = () => page.evaluate(() => new Promise(ok => { const go = () => scrollY > 2000 ? ok() : requestAnimationFrame(go); go(); setTimeout(ok, 3000); }));
  const marked = async () => (await page.locator('.doc-rail a[aria-current=location]').allTextContents()).join();
  // What the nav marks with no jump: the last outline heading above the reading line, or at the very bottom the last on screen.
  const reading = () => page.evaluate(() => {
    const line = Math.min(innerHeight / 3, 220), root = document.documentElement;
    const heads = [...document.querySelectorAll('.doc-rail a')].map(a => document.getElementById(decodeURIComponent(a.hash.slice(1))));
    let h = heads.filter(x => x.getBoundingClientRect().top <= line).at(-1);
    if (root.scrollTop + innerHeight >= root.scrollHeight - 2) h = heads.filter(x => { const t = x.getBoundingClientRect().top; return t >= -2 && t < innerHeight - 8; }).at(-1) || h;
    return h?.textContent.trim() ?? '';
  });
  // Where a jump to the heading ends: below the page's 90 px scroll padding, as far as the page scrolls.
  const end = id => page.evaluate(i => { const r = document.documentElement; return Math.min(r.scrollHeight - r.clientHeight, scrollY + document.getElementById(i).getBoundingClientRect().top - 90); }, id);
  const rail = page.locator('.doc-rail a'), n = await rail.count();
  // A heading far enough down that "partway" (2000 px) is well before the jump ends.
  const far = await page.evaluate(() => [...document.querySelectorAll('.doc-rail a')].findIndex(a =>
    document.getElementById(decodeURIComponent(a.hash.slice(1))).getBoundingClientRect().top + scrollY > 5000));
  if (far < 0) { await page.close(); return ['2560px /docs/explore: no heading 5000 px down, so the jump checks test nothing']; }
  const target = rail.nth(far), id = decodeURIComponent((await target.getAttribute('href')).slice(1)), name = await target.textContent();
  for (const [where, sel] of [['rail', '.doc-rail a[href="#' + encodeURIComponent(id) + '"]'], ['tree', 'cad-nav a[aria-current=page]']]) {
    await page.evaluate(() => { scrollTo({ top: 0, behavior: 'instant' }); document.querySelector('cad-nav .cad-nav-panel').scrollTop = 0; });
    await settle();
    await target.click();
    await partway();
    await page.evaluate(s => {
      document.querySelector(s).dispatchEvent(new WheelEvent('wheel', { deltaY: -800, bubbles: true, cancelable: true }));
      scrollBy({ top: -800, behavior: 'instant' });            // the scroll the wheel makes, which stops the smooth one
    }, sel);
    await settle();
    if (Math.abs((await page.evaluate(() => scrollY)) - (await end(id))) < 200) out.push(`2560px /docs/explore: the wheel over the ${where} did not stop the jump to "${name}", so this check tests nothing`);
    else if ((await marked()) !== (await reading())) out.push(`2560px /docs/explore: a wheel over the ${where} during the jump to "${name}" leaves "${await marked()}" marked, not "${await reading()}"`);
  }
  // A wheel the tree takes: every group open so the tree scrolls, and scrolled halfway so it can scroll up.
  await page.evaluate(() => {
    scrollTo({ top: 0, behavior: 'instant' });
    const p = document.querySelector('cad-nav .cad-nav-panel');
    for (const g of p.querySelectorAll('details')) g.open = true;
    p.scrollTop = (p.scrollHeight - p.clientHeight) / 2;
  });
  await settle();
  if (!(await page.evaluate(() => { const p = document.querySelector('cad-nav .cad-nav-panel'); return p.scrollTop > 100; })))
    out.push('2560px /docs/explore: the tree cannot scroll with every group open, so the wheel-over-the-tree check tests nothing');
  await target.click();
  await partway();
  await page.evaluate(() => {
    const p = document.querySelector('cad-nav .cad-nav-panel'), b = p.getBoundingClientRect();
    const a = [...p.querySelectorAll('a')].find(x => { const r = x.getBoundingClientRect(); return r.top > b.top + 80 && r.bottom < b.bottom; });
    a.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true }));
    p.scrollTop -= 100;                                         // it scrolls the tree; the page's jump goes on
  });
  await settle();
  if ((await marked()) !== name) out.push(`2560px /docs/explore: a wheel that only scrolls the tree releases the jump to "${name}" ("${await marked()}" marked)`);
  // A stalled jump, to a heading that cannot reach the reading line (released, the mark would fall to the last one on
  // screen): partway, the scroll stops for 300 ms while timers run, then goes on a frame at a time to where it ends.
  const unreachable = [];
  for (let i = 0; i < n - 1; i++) {
    const h = decodeURIComponent((await rail.nth(i).getAttribute('href')).slice(1));
    if (await page.evaluate(x => { const r = document.documentElement; return scrollY + document.getElementById(x).getBoundingClientRect().top - Math.min(innerHeight / 3, 220) > r.scrollHeight - r.clientHeight; }, h)) unreachable.push(i);
  }
  if (!unreachable.length) out.push('2560px /docs/explore: every heading but the last reaches the reading line; pick a page where some cannot');
  for (const i of unreachable) {
    const link = rail.nth(i), h = decodeURIComponent((await link.getAttribute('href')).slice(1)), want = await link.textContent();
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    await settle();
    await link.click();
    await partway();
    await page.evaluate(async x => {
      scrollTo({ top: scrollY, behavior: 'instant' });          // the smooth scroll stops here
      const from = scrollY;
      await new Promise(r => setTimeout(r, 300));               // the stall
      const r = document.documentElement, to = Math.min(r.scrollHeight - r.clientHeight, scrollY + document.getElementById(x).getBoundingClientRect().top - 90);
      for (let k = 1; k <= 8; k++) { scrollTo({ top: from + (to - from) * k / 8, behavior: 'instant' }); await new Promise(f => requestAnimationFrame(f)); }
    }, h);
    await settle();
    if ((await marked()) !== want) out.push(`2560px /docs/explore: the jump to "${want}", stalled 300 ms partway, marks "${await marked()}"`);
  }
  await page.close();
  return out;
}
