/** The catalogue (/catalog) in a real browser (PLAYWRIGHT_BROWSER=webkit for WebKit), served the way Cloudflare Pages
 * serves it (pretty URLs, the _headers CSP). Fails on console errors or CSP violations, outside requests, layout shift
 * while loading, entries hidden without script, tabs, filters, sorting or the URL state not agreeing with each other,
 * old /catalog#anchors that no longer land, a phone page over its height budget or not in two columns, a filter sheet
 * that traps or loses focus, and covers that move under prefers-reduced-motion. */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium, webkit } from '@playwright/test';

const root = path.resolve(import.meta.dirname, '..');
const dir = await mkdtemp(path.join(os.tmpdir(), 'cad-agent-catalog-browser-'));
execFileSync(process.execPath, ['tools/build-site.mjs', '--out', dir], { cwd: root, stdio: 'inherit' });
const server = spawn(process.execPath, ['tools/preview-site.mjs', '--dir', dir, '--port', '0'], { cwd: root });
const base = await new Promise((ok, fail) => {
  server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
  server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
});
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
// A phone shows the overview in about a third of the old page's height (32,000 px at 390 px before the gallery).
const PHONE_BUDGET = 14000;
const problems = [];
const fail = (where, what) => problems.push(`${where}: ${what}`);

async function open(route, { width = 1366, height = 900, js = true, motion = 'no-preference' } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, javaScriptEnabled: js, reducedMotion: motion });
  const page = await context.newPage();
  const seen = [];
  page.on('console', m => { if (m.type() === 'error' && !/status of 404/.test(m.text())) seen.push(`console: ${m.text()}`); });
  page.on('pageerror', e => seen.push(`page error: ${e.message}`));
  page.on('requestfailed', r => { if (!/ERR_ABORTED|cancelled/i.test(r.failure()?.errorText || '')) seen.push(`failed: ${r.url()}`); });
  page.on('response', r => { if (r.status() >= 400) seen.push(`HTTP ${r.status()}: ${r.url()}`); });
  page.on('request', r => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) seen.push(`third party: ${r.url()}`); });
  if (js) await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
  await page.goto(base + route, { waitUntil: 'networkidle' });
  if (js) await page.waitForSelector('cad-gallery[data-ready]', { timeout: 10000 }).catch(() => seen.push('the gallery did not start'));
  const done = async () => { for (const s of seen) fail(`${route} @${width}${js ? '' : ' no-JS'}`, s); await context.close(); };
  return { page, done };
}
const visible = (page, sel = '[data-item]') => page.$$eval(sel, els => els.filter(e => e.checkVisibility()).map(e => e.id));
const query = page => new URL(page.url()).search;

try {
  // Without script: every entry shows, grouped by kind, and nothing that needs script is offered.
  {
    const { page, done } = await open('/catalog', { js: false });
    const total = await page.locator('[data-item]').count();
    const shown = await visible(page);
    if (shown.length !== total) fail('no-JS', `${shown.length} of ${total} entries visible`);
    if (await page.locator('.cat-search').isVisible()) fail('no-JS', 'the search box shows but cannot work');
    if (!(await page.locator('#tools').isVisible())) fail('no-JS', 'the Tools group is not visible');
    await done();
  }

  // The overview: no layout shift, a limited number per group with "see all", tabs as ARIA tabs.
  {
    const { page, done } = await open('/catalog');
    const shift = await page.evaluate(() => new Promise(ok => {
      if (!PerformanceObserver.supportedEntryTypes?.includes('layout-shift')) return ok(0);
      let sum = 0;
      new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) sum += e.value; }).observe({ type: 'layout-shift', buffered: true });
      setTimeout(() => ok(sum), 300);
    }));
    if (shift > 0.02) fail('/catalog', `layout shift while loading: ${shift.toFixed(3)}`);
    const limit = Number(await page.getAttribute('cad-gallery', 'limit'));
    for (const g of await page.$$('[data-group]')) {
      const id = await g.getAttribute('id'), n = await g.$$eval('[data-item]', els => els.filter(e => e.checkVisibility()).length);
      if (n > limit) fail('/catalog', `${id} shows ${n} entries in the overview (limit ${limit})`);
    }
    if ((await page.getAttribute('[data-gallery-tabs]', 'role')) !== 'tablist') fail('/catalog', 'tabs are not a tablist');
    const all = page.locator('[data-gallery-tabs] [data-tab=""]');
    if ((await all.getAttribute('aria-selected')) !== 'true') fail('/catalog', '"All" is not the selected tab');

    // A tab: the URL says it, only its group shows, all of it; arrow keys move between tabs.
    await page.click('[data-gallery-tabs] [data-tab="tools"]');
    if (query(page) !== '?kind=tools') fail('tabs', `URL ${query(page)} after choosing Tools`);
    const groups = await page.$$eval('[data-group]', gs => gs.filter(g => g.checkVisibility()).map(g => g.id));
    if (groups.join() !== 'tools') fail('tabs', `groups shown for Tools: ${groups}`);
    const tools = await page.locator('#tools [data-item]').count();
    if ((await visible(page, '#tools [data-item]')).length !== tools) fail('tabs', 'the Tools tab does not show every tool');
    await page.focus('[data-gallery-tabs] [data-tab="tools"]');
    await page.keyboard.press('ArrowRight');
    const next = await page.evaluate(() => [document.activeElement.dataset.tab, document.activeElement.getAttribute('aria-selected')]);
    if (next[0] !== 'projects' || next[1] !== 'true') fail('tabs', `ArrowRight from Tools went to ${next}`);
    if (query(page) !== '?kind=projects') fail('tabs', `URL ${query(page)} after ArrowRight`);

    // Sort by stars: the URL says it, and the projects are in that order.
    await page.selectOption('#sort', 'stars');
    if (query(page) !== '?kind=projects&sort=stars') fail('sort', `URL ${query(page)}`);
    const stars = await page.$$eval('#projects [data-item]', els => els.filter(e => e.checkVisibility()).map(e => Number(e.dataset.sortStars || -1)));
    if (stars.some((s, i) => i && s > stars[i - 1] && s !== -1 && stars[i - 1] !== -1)) fail('sort', `stars not descending: ${stars.slice(0, 8)}`);

    // A licence checkbox: every shown entry has it, the counts agree, a chip names it.
    await page.check('input[name=licence][value=permissive]');
    if (!/licence=permissive/.test(query(page))) fail('filters', `URL ${query(page)} after Permissive`);
    const lic = await page.$$eval('#projects [data-item]', els => els.filter(e => e.checkVisibility()).map(e => e.dataset.licence));
    if (!lic.length || lic.some(l => l !== 'permissive')) fail('filters', `licences shown: ${[...new Set(lic)]}`);
    const tabCount = Number(await page.textContent('[data-gallery-tabs] [data-tab="projects"] [data-count]'));
    if (tabCount !== lic.length) fail('filters', `Projects tab says ${tabCount}, ${lic.length} shown`);
    if (!/Permissive/.test(await page.textContent('[data-gallery-chips]'))) fail('filters', 'no chip for the licence filter');
    if (!new RegExp(`^${lic.length} of `).test(await page.textContent('#filter-status'))) fail('filters', `status: ${await page.textContent('#filter-status')}`);

    // History: Back undoes the last choice, and the controls follow.
    await page.goBack();
    await page.waitForFunction(() => !location.search.includes('licence'));
    if (await page.isChecked('input[name=licence][value=permissive]')) fail('history', 'Back left the licence box ticked');
    if ((await page.inputValue('#sort')) !== 'stars') fail('history', 'Back lost the sort');
    await done();
  }

  // A shared link opens that view: an area, a filter and a sort, with the area's panel.
  {
    const { page, done } = await open('/catalog?kind=tools&area=compliant-mechanisms&sort=az');
    const areas = await page.$$eval('[data-item]', els => els.filter(e => e.checkVisibility()).map(e => e.dataset.area));
    if (!areas.length || areas.some(a => !a.split(' ').includes('compliant-mechanisms'))) fail('shared link', `areas shown: ${areas}`);
    if (!(await page.locator('[data-gallery-when="area:compliant-mechanisms"]').isVisible())) fail('shared link', 'the area panel is hidden');
    if ((await page.getAttribute('.area-link[data-value="compliant-mechanisms"]', 'aria-current')) !== 'true') fail('shared link', 'the area is not marked current');
    if ((await page.inputValue('#sort')) !== 'az') fail('shared link', 'sort not restored');
    // An area link in a card adds to the view rather than replacing it.
    const href = await page.getAttribute('.area-link[data-value="mechanisms"]', 'href');
    if (!/kind=tools/.test(href) || !/area=mechanisms/.test(href)) fail('shared link', `area link leads to ${href}`);
    await done();
    const bad = await open('/catalog?kind=nonsense&area=nowhere&licence=x');
    if ((await visible(bad.page)).length < 10) fail('stale link', 'unknown values hide everything');
    await bad.done();
  }

  // Old anchors land on their group, and an entry's id lands on that entry.
  for (const [hash, group] of [['tool', 'tools'], ['upstream', 'projects'], ['lessons', 'lessons'], ['tool-snapfit', 'tools']]) {
    const { page, done } = await open(`/catalog#${hash}`);
    const target = page.locator(`[id="${hash}"]`);
    const shown = await page.$$eval('[data-group]', gs => gs.filter(g => g.checkVisibility()).map(g => g.id));
    if (!shown.includes(group)) fail(`#${hash}`, `group ${group} is not shown (${shown})`);
    const box = await page.locator(`#${group}`).boundingBox();
    if (!box || box.y > 900 || box.y + box.height < 0) fail(`#${hash}`, `group ${group} is out of view (y=${box?.y})`);
    if (hash.includes('-') && !(await target.isVisible())) fail(`#${hash}`, 'the entry is hidden');
    await done();
  }

  // Phones: a height budget, two columns, the sheet as a modal that gives focus back.
  {
    const { page, done } = await open('/catalog', { width: 390, height: 844 });
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    if (h > PHONE_BUDGET) fail('phone', `page is ${h}px tall (budget ${PHONE_BUDGET})`);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (over > 0) fail('phone', `scrolls sideways by ${over}px`);
    const tops = await page.$$eval('#tools [data-item]', els => els.filter(e => e.checkVisibility()).slice(0, 2).map(e => Math.round(e.getBoundingClientRect().top)));
    if (tops.length < 2 || tops[0] !== tops[1]) fail('phone', `cards are not in two columns (${tops})`);
    if (await page.locator('[data-gallery-sheet]').isVisible()) fail('phone', 'the filter sheet shows before it is opened');
    await page.click('[data-gallery-sheet-open]');
    if (!(await page.locator('[data-gallery-sheet] .area-tree').isVisible())) fail('phone', 'the sheet did not open');
    if (!(await page.evaluate(() => document.activeElement.closest('[data-gallery-sheet]')))) fail('phone', 'focus is not in the sheet');
    if (!(await page.evaluate(() => document.querySelector('.cat-hero').closest('[inert]')))) fail('phone', 'the page behind the sheet is not inert');
    await page.keyboard.press('Escape');
    if (await page.locator('[data-gallery-sheet] .area-tree').isVisible()) fail('phone', 'Escape did not close the sheet');
    if (!(await page.evaluate(() => document.activeElement.matches('[data-gallery-sheet-open]')))) fail('phone', 'focus did not return to the button');
    if (await page.evaluate(() => !!document.querySelector('[inert]'))) fail('phone', 'something stayed inert');
    // Tap targets in the toolbar.
    for (const sel of ['[data-gallery-sheet-open]', '#sort']) {
      const b = await page.locator(sel).boundingBox();
      if (b.height < 44) fail('phone', `${sel} is ${b.height}px tall (44 to tap)`);
    }
    await done();
  }

  // Moving covers play while seen, and never under reduced motion.
  for (const motion of ['no-preference', 'reduce']) {
    const { page, done } = await open('/catalog', { motion });
    const img = page.locator('img[data-anim]').first();
    if (await img.count()) {
      const moving = await img.getAttribute('data-anim');
      await img.scrollIntoViewIfNeeded();
      await img.hover();
      await page.waitForTimeout(300);
      const now = await img.getAttribute('src');
      if (motion === 'reduce' && now === moving) fail('motion', 'a cover moves under reduced motion');
      if (motion !== 'reduce' && now !== moving) fail('motion', 'an animated cover did not start');
    }
    await done();
  }
} finally {
  await browser.close();
  server.kill();
  await rm(dir, { recursive: true, force: true });
}
assert.deepEqual(problems, [], problems.join('\n'));
console.log(`catalogue OK in ${engine.name()}`);
