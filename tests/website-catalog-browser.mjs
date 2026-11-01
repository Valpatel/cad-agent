/** The catalogue (/catalog) in a real browser (PLAYWRIGHT_BROWSER=webkit for WebKit), served the way Cloudflare Pages
 * serves it (pretty URLs, the _headers CSP). Fails on console errors or CSP violations, outside requests, layout shift
 * while loading, entries hidden without script, tabs, filters, sorting or the URL state not agreeing with each other,
 * old /catalog#anchors that no longer land (or that Back cannot return to), a shared view that opens on the hero, counts
 * that disagree with catalog/index.json, markup from the URL, a page that hides entries when gallery.js fails, a cover
 * shown twice in the overview, a phone page over its height budget, not in two columns or with pills under 11px, a
 * filter sheet that traps or loses focus, and covers that move under prefers-reduced-motion. */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
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

async function open(route, { width = 1366, height = 900, js = true, motion = 'no-preference', block = null } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, javaScriptEnabled: js, reducedMotion: motion });
  const page = await context.newPage();
  const seen = [];
  if (block) await page.route(`**${block}`, r => r.abort());
  page.on('console', m => { if (m.type() === 'error' && !/status of 404/.test(m.text()) && !(block && /gallery\.js|Failed to load|load failed|importing a module/i.test(m.text()))) seen.push(`console: ${m.text()}`); });
  page.on('pageerror', e => seen.push(`page error: ${e.message}`));
  page.on('requestfailed', r => { if (!/ERR_ABORTED|cancelled/i.test(r.failure()?.errorText || '') && !(block && r.url().endsWith(block))) seen.push(`failed: ${r.url()}`); });
  page.on('response', r => { if (r.status() >= 400) seen.push(`HTTP ${r.status()}: ${r.url()}`); });
  page.on('request', r => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) seen.push(`third party: ${r.url()}`); });
  if (js) await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
  await page.goto(base + route, { waitUntil: 'networkidle' });
  if (js && !block) await page.waitForSelector('cad-gallery[data-ready]', { timeout: 10000 }).catch(() => seen.push('the gallery did not start'));
  const done = async () => { for (const s of seen) fail(`${route} @${width}${js ? '' : ' no-JS'}`, s); await context.close(); };
  return { page, done };
}
const visible = (page, sel = '[data-item]') => page.$$eval(sel, els => els.filter(e => e.checkVisibility()).map(e => e.id));
const query = page => new URL(page.url()).search;

// Every count on the page (area tree, domains, tabs) against catalog/index.json, with no filters on.
const index = JSON.parse(await readFile(path.join(dir, 'catalog/index.json'), 'utf8'));
const indexCount = new Map([['', index.count], ...index.domains.map(d => [d.slug, d.count]),
  ...index.domains.flatMap(d => d.areas.map(a => [a.slug, a.count])), ...index.buckets.map(b => [b.slug, b.count])]);
async function countsMatchIndex(page, where) {
  const links = await page.$$eval('.area-tree .area-link', as => as.map(a => [a.dataset.value, a.querySelector('[data-count]')?.textContent.trim()]));
  const domains = await page.$$eval('.area-tree [data-count-of]', els => els.map(e => [e.dataset.countOf.replace(/^area:/, ''), e.textContent.trim()]));
  if (links.length < index.domains.length + 20) fail(where, `only ${links.length} area links in the tree`);
  for (const [slug, n] of [...links, ...domains]) if (Number(n) !== indexCount.get(slug)) fail(where, `area ${slug || '(all)'} says ${n}, index.json ${indexCount.get(slug)}`);
  const tabs = await page.$$eval('[data-gallery-tabs] [data-tab]', ts => ts.map(t => [t.dataset.tab, t.querySelector('[data-count]')?.textContent.trim()]));
  for (const [tab, n] of tabs) {
    const want = tab ? index.kinds.find(k => k.tab === tab)?.count : index.count;
    if (Number(n) !== want) fail(where, `tab ${tab || 'All'} says ${n}, index.json ${want}`);
  }
}
// The first thing a shared view is about (the area's panel, else the first entry): its top, in px from the window's.
const firstResultTop = page => page.evaluate(() => {
  const el = [...document.querySelectorAll('[data-gallery-when]:not([hidden]), [data-item]')].find(e => e.checkVisibility());
  return el ? Math.round(el.getBoundingClientRect().top) : null;
});

try {
  // Without script: every entry shows, grouped by kind, and nothing that needs script is offered.
  {
    const { page, done } = await open('/catalog', { js: false });
    const total = await page.locator('[data-item]').count();
    const shown = await visible(page);
    if (shown.length !== total) fail('no-JS', `${shown.length} of ${total} entries visible`);
    if (await page.locator('.cat-search').isVisible()) fail('no-JS', 'the search box shows but cannot work');
    if (!(await page.locator('#tools').isVisible())) fail('no-JS', 'the Tools group is not visible');
    await countsMatchIndex(page, 'no-JS');
    await done();
  }

  // gallery.js blocked (a script error or a bad kit deploy): like no script, every entry shows and no dead controls.
  {
    const { page, done } = await open('/catalog', { block: '/kit/gallery.js' });
    await page.waitForSelector('cad-gallery[data-failed]', { timeout: 10000 }).catch(() => fail('gallery.js blocked', 'the page did not mark data-failed'));
    const total = await page.locator('[data-item]').count();
    const shown = await visible(page);
    if (shown.length !== total) fail('gallery.js blocked', `${shown.length} of ${total} entries visible`);
    for (const sel of ['.cat-search', '#sort', '[data-gallery-more]']) if (await page.locator(sel).first().isVisible()) fail('gallery.js blocked', `${sel} shows but cannot work`);
    if (!(await page.locator('.play').isVisible())) fail('gallery.js blocked', 'the "Play with it" strip is gone');
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
    await countsMatchIndex(page, '/catalog');
    // No picture twice in the overview (the strip and the first cards of each group).
    const covers = await page.$$eval('.play img, [data-item] .card-cover img', imgs => imgs.filter(i => i.checkVisibility()).map(i => i.dataset.still || i.getAttribute('src')));
    const twice = covers.filter((c, i) => covers.indexOf(c) !== i);
    if (twice.length) fail('/catalog', `covers shown twice in the overview: ${[...new Set(twice)]}`);
    if (covers.length < 40) fail('/catalog', `only ${covers.length} covers in the overview`);
    // Covers keep 4:3, whatever the picture.
    const ratios = await page.$$eval('[data-item] .card-cover', els => els.filter(e => e.checkVisibility()).map(e => [e.closest('[data-item]').id, e.getBoundingClientRect().height / e.getBoundingClientRect().width]));
    for (const [id, r] of ratios) if (Math.abs(r - 0.75) > 0.02) fail('/catalog', `${id}: cover is ${r.toFixed(3)} tall for its width (4:3 is 0.75)`);

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

  // A shared view opens on what was shared, not on the hero, on a desktop and on a phone.
  for (const [width, height] of [[1366, 900], [390, 844]]) {
    for (const route of ['/catalog?area=compliant-mechanisms', '/catalog?kind=tools', '/catalog?q=kicad']) {
      const { page, done } = await open(route, { width, height });
      await page.waitForTimeout(300);
      const top = await firstResultTop(page);
      if (top == null || top < 0 || top > height * 0.6) fail(`${route} @${width}`, `the first result is at ${top}px (window ${height}px)`);
      await done();
    }
  }

  // An area with nothing in it yet says so.
  {
    const empty = index.domains.flatMap(d => d.areas).find(a => a.count === 0);
    if (empty) {
      const { page, done } = await open(`/catalog?area=${empty.slug}`);
      if (!(await page.locator('[data-gallery-empty-scope]').isVisible())) fail('empty area', `${empty.slug}: no "nothing here yet" message`);
      else if (!(await page.textContent('[data-gallery-empty-scope]')).includes(empty.title)) fail('empty area', 'the message does not name the area');
      if (await page.locator('[data-gallery-empty]').isVisible()) fail('empty area', 'it also says no entries match the filters');
      await done();
    }
  }

  // Markup in the URL stays text: the search chip is plain text, and nothing from it reaches the page as elements.
  {
    const hostile = '<b>x</b><img src=x>';
    const { page, done } = await open(`/catalog?q=${encodeURIComponent(hostile)}`);
    const chips = await page.$$eval('[data-gallery-chips] > *', cs => cs.map(c => [c.children.length, c.textContent]));
    if (!chips.some(([, t]) => t.includes(hostile))) fail('?q=', `no chip shows the words as typed (${JSON.stringify(chips)})`);
    if (chips.some(([n]) => n)) fail('?q=', 'a chip has child elements (markup from the URL)');
    if (await page.locator('img[src="x"], cad-gallery b:text-is("x")').count()) fail('?q=', 'markup from the URL is on the page');
    await done();
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

  // An old anchor's tab is in the history: choose another tab, then Back returns to it.
  {
    const { page, done } = await open('/catalog#tool');
    if (!/^\?kind=tools$/.test(query(page)) || !page.url().endsWith('#tool')) fail('#tool', `URL after landing: ${page.url().slice(base.length)}`);
    await page.click('[data-gallery-tabs] [data-tab="projects"]');
    await page.goBack();
    await page.waitForFunction(() => location.search === '?kind=tools', null, { timeout: 5000 }).catch(() => fail('#tool', `Back went to ${page.url().slice(base.length)}`));
    const sel = await page.getAttribute('[data-gallery-tabs] [aria-selected="true"]', 'data-tab');
    if (sel !== 'tools') fail('#tool', `Back shows the ${sel || 'All'} tab, not Tools`);
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
    // Pills readable (11px or more), the sort named, the mode pill as wide as its word.
    const small = await page.$$eval('.cat-card .pill, .play-text .pill', ps => ps.filter(p => p.checkVisibility()).map(p => parseFloat(getComputedStyle(p).fontSize)).filter(s => s < 11));
    if (small.length) fail('phone', `${small.length} pills under 11px (${[...new Set(small)]})`);
    if (!(await page.getByRole('combobox', { name: 'Sort' }).count())) fail('phone', 'the sort has no accessible name');
    const stretch = await page.$$eval('.play-text', ts => ts.map(t => t.querySelector('.pill').getBoundingClientRect().width / t.getBoundingClientRect().width));
    if (stretch.some(r => r > 0.7)) fail('phone', `a mode pill spans ${Math.round(Math.max(...stretch) * 100)}% of its tile`);
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
