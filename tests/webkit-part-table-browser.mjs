import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '@playwright/test';
import { serveWebkit } from './webkit-server.mjs';
const html = `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/kit/part-table.css"><style>body{margin:16px;background:#fffaf2;color:#243f3a;font-family:system-ui}main{max-width:900px;margin:auto}table{min-width:640px}h1{font-size:24px}</style><main><h1>Fixture parts</h1><div id="progress"></div><div class="cad-table-scroll"><table id="parts"><caption>Assembly parts</caption><thead><tr><th data-sort="text">Part</th><th data-sort="number">Quantity</th><th data-sort="number">Cost</th></tr></thead><tbody>
<tr data-part-key="a" data-part-label="Bolt 10"><td>Bolt 10</td><td data-sort-value="2">2 pieces</td><td data-sort-value="10">$10.00</td></tr>
<tr data-part-key="b" data-part-label="Bolt 2"><td>Bolt 2</td><td data-sort-value="10">10 pieces</td><td data-sort-value="2">$2.00</td></tr>
<tr data-part-key="c" data-part-label="Plate"><td>Plate</td><td data-sort-value="">Not specified</td><td data-sort-value="">Not priced</td></tr>
<tr data-part-key="d" data-part-label="Rod"><td>Rod</td><td data-sort-value="1">1 piece</td><td data-sort-value="2">$2.00</td></tr>
</tbody><tfoot><tr><td>Total</td><td>13 known pieces</td><td>$14 known</td></tr></tfoot></table></div></main><script type="module">
import {createPartTracker} from '/kit/part-tracker.js';import {enhancePartTable,mountProgressTools} from '/kit/part-table.js';
window.tracker=createPartTracker({project:'fixture'});window.progressTools=mountProgressTools(document.getElementById('progress'),tracker);
window.tableAPI=enhancePartTable(document.getElementById('parts'),{tracker,statuses:[{id:'ordered',label:'Ordered'},{id:'inHand',label:'In hand'}]});document.body.dataset.ready='true';
</script></html>`;
const site = await serveWebkit(new Map([['/fixture', (_req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); }]]));
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
const errors = [], out = process.env.TEST_OUTPUT || '/tmp/cad-agent-part-table'; await mkdir(out, { recursive: true });
try {
  const context = await browser.newContext(), page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  const visit = async page => { await page.goto(site.url + '/fixture'); await page.waitForFunction(() => document.body.dataset.ready === 'true'); };
  const ids = () => page.locator('tbody tr').evaluateAll(rows => rows.map(row => row.dataset.partKey));
  await visit(page);
  await page.getByRole('button', { name: 'Cost: sort ascending', exact: true }).click(); assert.deepEqual(await ids(), ['b', 'd', 'a', 'c']);
  assert.equal(await page.locator('th').nth(2).getAttribute('aria-sort'), 'ascending');
  await page.getByRole('checkbox', { name: 'Ordered: Bolt 2', exact: true }).check();
  await page.getByRole('button', { name: 'Cost: sort descending', exact: true }).click(); assert.deepEqual(await ids(), ['a', 'b', 'd', 'c']);
  assert.ok(await page.getByRole('checkbox', { name: 'Ordered: Bolt 2', exact: true }).isChecked());
  const search = page.getByRole('searchbox', { name: 'Search Assembly parts' }); await search.fill('bolt 2');
  assert.equal(await page.locator('tbody tr:visible').count(), 1); assert.match(await page.locator('.cad-table-count').textContent(), /1 of 4/);
  await search.fill(''); await page.getByLabel('Sort Assembly parts', { exact: true }).selectOption('1:-1'); assert.deepEqual(await ids(), ['b', 'a', 'd', 'c']);
  await page.getByLabel('Sort Assembly parts', { exact: true }).selectOption('0:1'); assert.deepEqual(await ids(), ['b', 'a', 'c', 'd']);
  await page.getByLabel('Sort Assembly parts', { exact: true }).selectOption(''); assert.deepEqual(await ids(), ['a', 'b', 'c', 'd']);
  await page.reload(); await page.waitForFunction(() => document.body.dataset.ready === 'true');
  assert.ok(await page.getByRole('checkbox', { name: 'Ordered: Bolt 2', exact: true }).isChecked());
  const second = await context.newPage(); await visit(second); await second.getByRole('checkbox', { name: 'In hand: Plate', exact: true }).check();
  await page.waitForFunction(() => document.querySelector('input[aria-label="In hand: Plate"]').checked); await second.close();
  await page.locator('input[type=file]').setInputFiles({ name: 'progress.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ version: 1, project: 'fixture', parts: { d: { printed: true, inHand: true } } })) });
  await page.waitForFunction(() => document.querySelector('.cad-progress-receipt').textContent.includes('Imported'));
  assert.ok(await page.getByRole('checkbox', { name: 'In hand: Rod', exact: true }).isChecked()); assert.ok(await page.getByRole('checkbox', { name: 'Ordered: Bolt 2', exact: true }).isChecked());
  await page.locator('input[type=file]').setInputFiles({ name: 'wrong.json', mimeType: 'application/json', buffer: Buffer.from('{"version":1,"project":"other","parts":{}}') });
  await page.waitForFunction(() => document.querySelector('.cad-progress-receipt').textContent.includes('another project'));
  assert.ok(await page.getByRole('checkbox', { name: 'In hand: Rod', exact: true }).isChecked());
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: 'Export progress', exact: true }).click();
  const download = await downloadEvent; assert.equal(download.suggestedFilename(), 'fixture-progress.json');
  const exported = JSON.parse(await readFile(await download.path(), 'utf8')); assert.equal(exported.parts.b.ordered, true); assert.equal(exported.parts.d.printed, true);
  for (const [width, height] of [[320, 568], [390, 844], [568, 320], [768, 1024]]) {
    await page.setViewportSize({ width, height });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Only the table scrolls horizontally');
    for (const selector of ['.cad-table-search input', '.cad-table-sort select', '.cad-progress-tools button']) {
      const boxes = await page.locator(selector).evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { x: r.x, right: r.right, h: r.height }; }));
      assert.ok(boxes.every(r => r.x >= 0 && r.right <= width && r.h >= 44), JSON.stringify(boxes));
    }
    await page.getByLabel('Sort Assembly parts', { exact: true }).focus(); assert.ok(await page.getByLabel('Sort Assembly parts', { exact: true }).evaluate(el => el === document.activeElement));
    await page.screenshot({ path: `${out}/${engine.name()}-${width}.png`, fullPage: true });
  }
  // File decoding can finish after a newer selection or after a portal rerender.
  // Neither stale completion may overwrite the checklist or saved state.
  await page.evaluate(() => {
    const text = File.prototype.text;
    File.prototype.text = function () { return this.name === 'held.json' ? new Promise(resolve => { window.releaseImport = resolve; }) : text.call(this); };
  });
  const progressFile = value => JSON.stringify({ version: 1, project: 'fixture', parts: { d: { inHand: value } } });
  await page.locator('input[type=file]').setInputFiles({ name: 'held.json', mimeType: 'application/json', buffer: Buffer.from(progressFile(true)) });
  await page.waitForFunction(() => !!window.releaseImport);
  await page.locator('input[type=file]').setInputFiles({ name: 'newer.json', mimeType: 'application/json', buffer: Buffer.from(progressFile(false)) });
  await page.waitForFunction(() => !window.tracker.get('d', 'inHand'));
  await page.evaluate(async text => { window.releaseImport(text); await new Promise(resolve => setTimeout(resolve, 0)); }, progressFile(true));
  assert.equal(await page.evaluate(() => window.tracker.get('d', 'inHand')), false);
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem(window.tracker.key)).parts.d.inHand), false);
  await page.evaluate(() => { window.releaseImport = null; });
  await page.locator('input[type=file]').setInputFiles({ name: 'held.json', mimeType: 'application/json', buffer: Buffer.from(progressFile(true)) });
  await page.waitForFunction(() => !!window.releaseImport);
  await page.evaluate(async text => { window.progressTools.dispose(); window.releaseImport(text); await new Promise(resolve => setTimeout(resolve, 0)); }, progressFile(true));
  assert.equal(await page.evaluate(() => window.tracker.get('d', 'inHand')), false);
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem(window.tracker.key)).parts.d.inHand), false);
  await context.close();
  const denied = await browser.newContext(); await denied.addInitScript(() => { Storage.prototype.setItem = function () { throw new DOMException('Denied', 'SecurityError'); }; });
  const limited = await denied.newPage(); await visit(limited); await limited.getByRole('checkbox', { name: 'Ordered: Bolt 10', exact: true }).check();
  assert.match(await limited.locator('.cad-progress-tools').textContent(), /stay in this tab/); assert.ok(await limited.getByRole('checkbox', { name: 'Ordered: Bolt 10', exact: true }).isChecked());
  await denied.close(); assert.deepEqual(errors, []);
  await writeFile(`${out}/${engine.name()}-report.json`, JSON.stringify({ checkedAt: new Date().toISOString(), engine: engine.name(), errors, checks: ['numeric/text stable sorting', 'unknown values last both directions', 'keyboard/touch controls', 'filter count', 'stable checked identities', 'revisit/cross-tab persistence', 'atomic import and native download', 'stale/disposed import isolation', 'denied storage', '4 responsive layouts'] }, null, 2));
  console.log(`PASS ${engine.name()}: sortable parts, stable local status, import/export, keyboard and 4 layouts`);
} finally { await browser.close(); await site.close(); }
