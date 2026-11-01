/** Load cad-agent.valpatel.com pages in a real browser, served the way Cloudflare Pages serves them (pretty URLs and
 * the _headers file, including the Content-Security-Policy), at phone and desktop widths.
 * Fails on console errors, CSP violations, failed or third-party requests, sideways scrolling, a phone header without
 * the catalogue link, a hero animation that is not running (or still running under reduced motion), and a catalogue
 * filter that hides results without saying so. */
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
  await reduced.close();
  assert.deepEqual(problems, []);
  console.log(`${engine.name()}: ${ROUTES.length} routes at 360 and 1366 px under the site CSP PASS`);
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}
