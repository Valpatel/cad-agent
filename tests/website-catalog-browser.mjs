/** The catalogue (/catalog) in a real browser (PLAYWRIGHT_BROWSER=webkit for WebKit), served the way Cloudflare Pages
 * serves it (pretty URLs, the _headers CSP). Fails on console errors or CSP violations, outside requests, layout shift
 * while loading, entries hidden without script, tabs, filters, sorting or the URL state not agreeing with each other,
 * old /catalog#anchors that no longer land (or that Back cannot return to), a shared view that opens on the hero, counts
 * that disagree with catalog/index.json, markup from the URL, a page that hides entries when gallery.js fails, a cover
 * shown twice in the overview, a phone page over its height budget, not in two columns or with pills under 11px, a
 * filter sheet that traps or loses focus, covers that move under prefers-reduced-motion, and an area rail whose domain
 * panels lack their tone, whose bars and counts do not line up, whose bars do not fill to their level, whose chosen row
 * looks like a hovered one or reads under 4.5:1, whose maturity key does not explain itself, or whose phone rows are
 * under 44 px. */
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

// `init`: a script to run before the page's own (to break something on purpose); `fails`: a page error it causes.
async function open(route, { width = 1366, height = 900, js = true, motion = 'no-preference', block = null, init = null, fails = null } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, javaScriptEnabled: js, reducedMotion: motion });
  const page = await context.newPage();
  const seen = [];
  if (block) await page.route(`**${block}`, r => r.abort());
  page.on('console', m => { if (m.type() === 'error' && !/status of 404/.test(m.text()) && !(block && /gallery\.js|Failed to load|load failed|importing a module/i.test(m.text()))) seen.push(`console: ${m.text()}`); });
  page.on('pageerror', e => { if (!(fails && fails.test(e.message))) seen.push(`page error: ${e.message}`); });
  page.on('requestfailed', r => { if (!/ERR_ABORTED|cancelled/i.test(r.failure()?.errorText || '') && !(block && r.url().endsWith(block))) seen.push(`failed: ${r.url()}`); });
  page.on('response', r => { if (r.status() >= 400) seen.push(`HTTP ${r.status()}: ${r.url()}`); });
  page.on('request', r => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) seen.push(`third party: ${r.url()}`); });
  if (js) await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
  if (init) await page.addInitScript(init);
  await page.goto(base + route, { waitUntil: 'networkidle' });
  if (js && !block && !fails) await page.waitForSelector('cad-gallery[data-ready]', { timeout: 10000 }).catch(() => seen.push('the gallery did not start'));
  const done = async () => { for (const s of seen) fail(`${route} @${width}${js ? '' : ' no-JS'}`, s); await context.close(); };
  return { page, done };
}
// Hidden from view but kept for screen readers (gallery.css: a 1 px clipped box), or not shown at all.
const offScreen = loc => loc.evaluate(el => { const r = el.getBoundingClientRect(); return !el.checkVisibility() || (r.width <= 1 && r.height <= 1); });
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
// A gallery whose start failed is the page as written: what the no-script page shows, and no control left working.
async function failedLikeNoScript(page, route, where) {
  await page.waitForSelector('cad-gallery[data-failed]', { timeout: 10000 }).catch(() => fail(where, 'the page did not mark data-failed'));
  if (await page.locator('cad-gallery[data-ready]').count()) fail(where, 'the gallery still says it is ready');
  const total = await page.locator('[data-item]').count();
  const shown = await visible(page);
  if (shown.length !== total) fail(where, `${shown.length} of ${total} entries visible`);
  for (const sel of ['.cat-search', '#sort', '[data-gallery-more]']) if (await page.locator(sel).first().isVisible()) fail(where, `${sel} shows but cannot work`);
  if (await page.locator('.cat-empty:visible').count()) fail(where, 'an empty-state box shows');
  if (!(await page.locator('.play').isVisible())) fail(where, 'the "Play with it" strip is gone');
  if (await page.locator('cad-gallery [role="tab"], cad-gallery [tabindex="-1"]').count()) fail(where, 'tabs keep their tab roles or a tabindex');
  if (await page.locator('[data-gallery-chips] > *').count()) fail(where, 'a chip from the view is left');
  const copies = await page.$$eval('cad-gallery cad-copy', els => els.map(e => e.querySelectorAll(':scope > .cad-copy-btn').length));
  if (copies.some(n => n !== 1)) fail(where, `copy buttons per <cad-copy>: ${[...new Set(copies)]}`);
  // The same panels, counts and status as the no-script page at this address.
  const read = p => p.evaluate(() => ({
    panels: [...document.querySelectorAll('[data-gallery-when]')].filter(e => e.checkVisibility()).length,
    counts: [...document.querySelectorAll('cad-gallery [data-count]')].map(e => e.textContent.trim()).join(),
    status: document.querySelector('[data-gallery-status]')?.textContent.trim(),
  }));
  const plain = await open(route, { js: false });
  const [got, want] = [await read(page), await read(plain.page)];
  for (const k of Object.keys(want)) if (got[k] !== want[k]) fail(where, `${k}: ${JSON.stringify(got[k]).slice(0, 80)}, no-script ${JSON.stringify(want[k]).slice(0, 80)}`);
  await plain.done();
  // A click on what was a chip or a tab does not bring the dead gallery back to life: links are plain links again.
  await page.locator('[data-gallery-tabs] a').nth(1).click();
  await page.waitForLoadState('domcontentloaded');
  if ((await visible(page)).length !== total) fail(where, 'a click re-filtered the failed gallery');
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

  // The first render throws (a data bug, a browser quirk): the gallery is not ready, marks itself failed, and the page
  // is the no-script page, not 48 of 161 entries with a dead search box (#185).
  {
    const init = () => {
      const toggle = Element.prototype.toggleAttribute;
      let thrown = false;
      Element.prototype.toggleAttribute = function (name, force) {
        if (!thrown && this.localName === 'cad-gallery' && name === 'data-overview') { thrown = true; throw new Error('test: the first render throws'); }
        return toggle.call(this, name, force);
      };
    };
    const { page, done } = await open('/catalog', { init, fails: /the first render throws/ });
    await failedLikeNoScript(page, '/catalog', 'first render throws');
    await done();
  }

  // The start throws later, after the first render, on a shared view: the page still goes back to what it wrote, with
  // no chip, open area panel or filtered status left from the view (#189 review).
  {
    const init = () => {
      const media = window.matchMedia.bind(window);
      let thrown = false;
      window.matchMedia = q => {
        if (!thrown && /reduced-motion/.test(q) && document.querySelector('cad-gallery')?.hasAttribute('data-ready')) { thrown = true; throw new Error('test: the start throws after the first render'); }
        return media(q);
      };
    };
    const route = '/catalog?kind=tools&area=gears';
    const { page, done } = await open(route, { init, fails: /the start throws after the first render/ });
    await failedLikeNoScript(page, route, 'start throws late');
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
      // The status line says the same for screen readers, so it is hidden from view while the box shows (#185).
      const status = page.locator('[data-gallery-status]');
      if (!(await status.textContent()).includes(empty.title)) fail('empty area', 'the status line does not say it for screen readers');
      if (!(await offScreen(status))) fail('empty area', 'the status line repeats the box on screen');
      await done();
    }
  }

  // Links are the choice applied to the current view: after a tab change and a cleared search, an area link carries
  // the new tab and no stale words (each render used to merge the href the last one wrote, #185).
  {
    const { page, done } = await open('/catalog?kind=tools');
    await page.locator('[data-gallery-tabs] [data-tab="guides"]').click();
    const search = page.locator('[data-gallery-search]');
    await search.fill('gear');
    await page.waitForTimeout(450);
    await search.fill('');
    await page.waitForTimeout(450);
    const href = await page.getAttribute('.area-tree .area-link[data-value="gears"]', 'href');
    const q = new URL(href, base).searchParams;
    if (q.get('kind') !== 'guides' || q.get('area') !== 'gears' || q.has('q')) fail('stale links', `the Gears link after Guides and a cleared search: ${href}`);
    await done();
  }

  // An area with entries, but none of the chosen kind, says so too instead of showing blank space (#185).
  {
    const catalog = JSON.parse(await readFile(path.join(dir, 'catalog.json'), 'utf8'));
    const areas = index.domains.flatMap(d => d.areas).filter(a => a.count > 0);
    let pick = null;
    for (const a of areas) {
      const kinds = new Set(catalog.items.filter(i => i.areas.includes(a.slug)).map(i => i.kind));
      const tab = index.kinds.find(k => !k.kinds.some(x => kinds.has(x)));
      if (tab) { pick = { area: a, tab }; break; }
    }
    if (!pick) fail('area without the kind', 'no area lacks a kind to test with');
    else {
      const where = `?area=${pick.area.slug}&kind=${pick.tab.tab}`;
      const { page, done } = await open(`/catalog${where}`);
      const box = page.locator('[data-gallery-empty-kind]');
      if (!(await box.isVisible())) fail(where, 'no message box: blank space');
      else {
        const text = await box.textContent();
        const tabName = await page.$eval(`[data-gallery-tabs] [data-tab="${pick.tab.tab}"]`, t => t.firstChild.textContent.trim().toLowerCase());
        if (!text.includes(pick.area.title) || !text.includes(tabName)) fail(where, `the box does not name the area and the kind (${tabName}): ${text}`);
        for (const sel of ['[data-gallery-empty]', '[data-gallery-empty-scope]']) if (await page.locator(sel).isVisible()) fail(where, `${sel} shows as well`);
        if (!(await offScreen(page.locator('[data-gallery-status]')))) fail(where, 'the status line repeats the box on screen');
        await box.locator('a').click();
        await page.waitForFunction(() => document.querySelectorAll('[data-item]:not([hidden])').length > 0, null, { timeout: 5000 })
          .catch(() => fail(where, '"show every kind" shows nothing'));
        const q = new URLSearchParams(query(page));
        if (q.get('area') !== pick.area.slug || q.get('kind')) fail(where, `"show every kind" went to ${query(page)}`);
        if (await box.isVisible()) fail(where, 'the box stays after "show every kind"');
        if (await offScreen(page.locator('[data-gallery-status]'))) fail(where, 'the status line stays hidden without a box');
        // The same view as opening the area itself.
        const shown = await visible(page);
        const direct = await open(`/catalog?area=${pick.area.slug}`);
        const want = await visible(direct.page);
        if (shown.join() !== want.join()) fail(where, `after "show every kind": ${shown.length} entries, ?area=${pick.area.slug} shows ${want.length}`);
        await direct.done();
      }
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

  // The area rail (#104): a panel per domain in its tone, bars and counts in columns, hover and the chosen row that look
  // different from a row at rest, readable text, and a maturity key that explains each level.
  {
    const where = 'rail';
    const { page, done } = await open('/catalog');
    const tones = await page.$$eval('details.dom', ds => ds.map(d => [d.dataset.domain, getComputedStyle(d).getPropertyValue('--tone').trim()]));
    if (tones.length !== index.domains.length) fail(where, `${tones.length} domain panels for ${index.domains.length} domains`);
    for (const [slug, tone] of tones) if (!tone) fail(where, `${slug}: its panel has no --tone`);
    // In each open domain, the counts end at one x and the maturity bars start at one x.
    const columns = await page.$$eval('details.dom[open]', ds => ds.map(d => {
      const rows = [...d.querySelectorAll(':scope > ul .area-link')];
      const edge = (sel, side) => rows.map(r => r.querySelector(sel)).filter(Boolean).map(e => e.getBoundingClientRect()[side]);
      return [d.dataset.domain, edge(':scope > .count', 'right'), edge(':scope > .mat-dots', 'left')];
    }));
    if (columns.length < 3) fail(where, `only ${columns.length} open domains to measure`);
    const spread = xs => Math.max(...xs) - Math.min(...xs);
    for (const [slug, rights, lefts] of columns) {
      if (rights.length < 2 || spread(rights) > 1) fail(where, `${slug}: the counts' right edges spread over ${spread(rights).toFixed(1)}px`);
      if (!lefts.length || spread(lefts) > 1) fail(where, `${slug}: the maturity bars' left edges spread over ${spread(lefts).toFixed(1)}px`);
    }
    // Each bar fills as many steps as its level: as many segments in the filled colour (the key's top level shows it)
    // as the level, the rest in the empty one (the key's lowest level ends in it).
    const bars = await page.$$eval('.area-tree .mat-dots', (bs, n) => {
      const paint = i => getComputedStyle(i).backgroundColor;
      const key = [...document.querySelectorAll('.key-scale .mat-dots')];
      const [on, off] = [paint(key.at(-1).querySelector('i')), paint(key[0].querySelector('i:last-child'))];
      return [on !== off, bs.map(b => { const ps = [...b.querySelectorAll('i')].map(paint);
        return [b.dataset.level, ps.length === n && ps.every(p => p === on || p === off) ? ps.filter(p => p === on).length : -1]; })];
    }, index.maturity.length);
    if (!bars[0]) fail(where, 'filled and empty steps look the same');
    for (const [level, on] of bars[1]) if (Number(level) !== on) fail(where, `a level-${level} bar fills ${on} steps`);
    // WCAG contrast of an element's text against a background colour, composited over white.
    const contrastOf = (sel, bgSel = sel) => page.evaluate(([sel, bgSel]) => {
      const rgb = c => { const [r, g, b, a = 1] = c.match(/[\d.]+/g).map(Number); return [r, g, b].map(v => v * a + 255 * (1 - a)); };
      const lum = c => rgb(c).map(v => v / 255).map(v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
      const [fg, bg] = [getComputedStyle(document.querySelector(sel)).color, getComputedStyle(document.querySelector(bgSel)).backgroundColor];
      const [hi, lo] = [lum(fg), lum(bg)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    }, [sel, bgSel]);
    const chosenAll = '.area-tree > li > .area-link[aria-current="true"]';
    if (!(await page.locator(chosenAll).count())) fail(where, '"All areas" is not the chosen row on /catalog');
    else if ((await contrastOf(`${chosenAll} .area-name`, chosenAll)) < 4.5) fail(where, `"All areas", chosen: text contrast ${(await contrastOf(`${chosenAll} .area-name`, chosenAll)).toFixed(2)}`);
    const idea = '.area-link[data-maturity="idea"]:not([aria-current]) .area-name';
    if ((await contrastOf(idea, 'details.dom')) < 4.5) fail(where, `an idea-level name: contrast ${(await contrastOf(idea, 'details.dom')).toFixed(2)} on its panel`);
    // At rest, hovered and chosen are three different looks.
    const row = '.area-link[data-value="gears"]';
    const look = () => page.$eval(row, a => { const s = getComputedStyle(a); return `${s.backgroundColor} | ${s.backgroundImage} | ${s.backgroundSize}`; });
    await page.mouse.move(1300, 880);
    const rest = await look();
    await page.hover(row);
    await page.waitForTimeout(350);
    const hovered = await look();
    await page.click(row);
    await page.waitForFunction(s => document.querySelector(s).getAttribute('aria-current') === 'true', row, { timeout: 5000 }).catch(() => fail(where, 'Gears is not chosen after a click'));
    await page.mouse.move(1300, 880);
    await page.waitForTimeout(350);
    const chosen = await look();
    if (hovered === rest) fail(where, `hovering a row does not change it (${rest})`);
    if (chosen === rest || chosen === hovered) fail(where, `the chosen row looks like one at rest or hovered (${chosen})`);
    for (const [part, bg] of [[`${row} .area-name`, row], [`${row} .count`, `${row} .count`]]) {
      const c = await contrastOf(part, bg);
      if (c < 4.5) fail(where, `chosen row: ${part.slice(row.length + 1)} contrast ${c.toFixed(2)}`);
    }
    // The key: a word per level, in order; focusing one shows what it means.
    const words = await page.$$eval('.key-scale .key-word', ws => ws.map(w => w.textContent));
    if (words.join() !== index.maturity.map(m => m.level).join()) fail(where, `the key says ${words}`);
    const means = page.locator('.key-scale li').nth(2).locator('.key-means');
    const shown = () => means.evaluate(m => getComputedStyle(m).clipPath === 'none' && m.getBoundingClientRect().height > 20);
    if (await shown()) fail(where, 'a level\'s meaning shows before it is asked for');
    await page.locator('.key-scale li').nth(2).focus();
    if (!(await shown())) fail(where, 'focusing a level in the key does not show what it means');
    if ((await means.textContent()).trim() !== `: ${index.maturity[2].means}`) fail(where, `the key's tooling says ${await means.textContent()}`);
    await done();
  }

  // A chip names what it filters: a domain's "All" row by its domain, a maturity box by its word (not its bar's
  // screen-reader words), and the retired ?gyropup=1 filters nothing.
  for (const [route, want] of [['/catalog?area=mechanical', 'All in mechanical design'], ['/catalog?maturity=tooling', 'Tooling'], ['/catalog?gyropup=1', '']]) {
    const { page, done } = await open(route);
    const chips = await page.$$eval('[data-gallery-chips] > *', cs => cs.map(c => c.textContent).join());
    if (chips !== want) fail(route, `chips say "${chips}", want "${want}"`);
    const status = (await page.textContent('[data-gallery-status]')).trim();
    if (!want && status !== `${index.count} entries`) fail(route, `status "${status}": it filters`);
    await done();
  }

  // The phone sheet: every row in the area tree, the domain's "All" included, is a 44 px tap target.
  {
    const { page, done } = await open('/catalog?area=cfd', { width: 390, height: 844 });
    await page.click('[data-gallery-sheet-open]');
    const short = await page.$$eval('[data-gallery-sheet] .area-tree :is(.area-link, summary)', els => els.filter(e => e.checkVisibility())
      .map(e => [e.dataset.value ?? e.textContent.trim().slice(0, 20), e.getBoundingClientRect().height]).filter(([, h]) => h < 44 - 0.01));
    if (short.length) fail('phone sheet', `rows under 44px: ${short.map(([n, h]) => `${n} ${h.toFixed(1)}`).join(', ')}`);
    if (!(await page.locator('[data-gallery-sheet] .area-link.dom-all[data-value="simulation"]').isVisible())) fail('phone sheet', 'the chosen area\'s domain is folded');
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
    // Tap targets in the toolbar: 44 CSS px. The 0.01 px allows float rounding while the hover lift (web/site.css) is
    // still moving after the click: CI read 43.99997 for a button whose layout height is 44 (#199).
    for (const sel of ['[data-gallery-sheet-open]', '#sort']) {
      const b = await page.locator(sel).boundingBox();
      if (b.height < 44 - 0.01) fail('phone', `${sel} is ${b.height}px tall (44 to tap)`);
    }
    await done();
  }

  // Moving covers play while seen, and never under reduced motion. Under 1000 px the strip holds every demo and
  // swipes, so its first moving cover plays once in view. Wider, the strip shows only its first four demos, which need
  // not include a moving one, so the desktop pass hovers the first card a reader can see with a moving cover.
  for (const width of [900, 1366]) for (const motion of ['no-preference', 'reduce']) {
    const { page, done } = await open('/catalog', { motion, width });
    const strip = width < 1000;
    const img = strip ? page.locator('img[data-anim]').first() : page.locator('[data-item] img[data-anim]:visible').first();
    if (!(await img.count())) fail('motion', `${width}px: no moving cover to check`);
    else {
      const moving = await img.getAttribute('data-anim');
      await img.scrollIntoViewIfNeeded();
      // a card's title link covers the card, so the pointer goes to the card, as a reader's does
      await (strip ? img : img.locator('xpath=ancestor::*[@data-item][1]')).hover();
      await page.waitForTimeout(300);
      const now = await img.getAttribute('src');
      if (motion === 'reduce' && now === moving) fail('motion', `${width}px: a cover moves under reduced motion`);
      if (motion !== 'reduce' && now !== moving) fail('motion', `${width}px: an animated cover did not start`);
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
