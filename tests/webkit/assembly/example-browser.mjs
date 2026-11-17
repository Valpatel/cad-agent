/** The featured build guide (#811), Gyropup's turret, in the shipped reader: its steps show the parts they add,
 * earlier parts ghost, the guide says what it is, and on a phone the 3D view comes first with every control labelled
 * and at least 44 px. Each check runs on the real page and then on a planted fault it must catch. */
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '../../site/npm-context.mjs';
import { serveWebkit } from '../webkit-server.mjs';

const example = new URL('../../../software/cadagent/webkit/assembly/examples/gyropup-turret/', import.meta.url);
const guide = JSON.parse(await readFile(new URL('guide.json', example)));
const route = '/kit/model/viewer.html?guide=../assembly/examples/gyropup-turret/guide.json';
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-assembly-example'; await mkdir(out, { recursive: true });
// The site's own bar (ui/appnav.js) reads <root>/site/nav.json; these are the site's real tabs (#804).
const NAV = { title: 'cad-agent', nav: [{ title: 'Explore', href: 'explore' }, { title: 'Toolkit', href: 'toolkit' }, { title: 'For agents', href: 'docs/agent-workflow' }] };
const site = await serveWebkit(new Map([['/favicon.ico', (_, res) => res.writeHead(204).end()],
  ['/site/nav.json', (_, res) => res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify(NAV))]]));
const PHRASES = ['Example sequence', 'work-in-progress', 'not a verified build procedure', 'CAD step order does not prove'];
const STEPS = ['step-01', 'step-03', 'step-11'];
let browser; const cases = [];

/** The guide's statement, the select's steps and, for the shown step, the scene: visible and highlighted parts as the
 * guide lists them, every highlighted part moved by its authored offset, earlier parts ghosted, new parts solid. */
const stepProblems = (page, id) => page.evaluate(({ id, guide, PHRASES }) => {
  const problems = [], step = guide.steps.find(s => s.id === id), v = window.__viewer, state = v.getState();
  const note = document.querySelector('.guide-qualification')?.textContent || '';
  for (const phrase of PHRASES) if (!note.includes(phrase)) problems.push(`the reader does not say "${phrase}"`);
  const options = [...document.querySelector('[aria-label="Instruction step"]').options].map(o => o.value).filter(Boolean);
  if (JSON.stringify(options) !== JSON.stringify(guide.steps.map(s => s.id))) problems.push('the step list is not the guide\'s');
  if (document.querySelector('.guide-text')?.textContent !== step.text) problems.push(`${id}: the instruction text is not the guide's`);
  if (JSON.stringify([...state.visible].sort()) !== JSON.stringify([...step.parts].sort())) problems.push(`${id}: visible parts differ from the guide`);
  if (JSON.stringify([...state.highlight].sort()) !== JSON.stringify([...step.highlight].sort())) problems.push(`${id}: highlighted parts differ from the guide`);
  for (const p of v.parts) {
    const shown = p.mesh.visible, wanted = step.parts.includes(p.name);
    if (shown !== wanted) problems.push(`${id}: ${p.name} is ${shown ? 'shown' : 'hidden'}`);
    if (!wanted) continue;
    const isNew = step.highlight.includes(p.name), m = p.mesh.material;
    if (isNew && (m.transparent && m.opacity < 1)) problems.push(`${id}: new part ${p.name} is ghosted`);
    if (!isNew && !(m.transparent && m.opacity < 1)) problems.push(`${id}: earlier part ${p.name} is not ghosted`);
    const offset = state.offsets_mm[p.name] || [0, 0, 0], authored = step.offsets_mm[p.name] || [0, 0, 0];
    if (offset.some((n, i) => Math.abs(n - authored[i]) > 1e-6)) problems.push(`${id}: ${p.name} is not at its authored offset`);
  }
  if (!step.highlight.some(n => (step.offsets_mm[n] || [0, 0, 0]).some(Boolean)) && id !== 'step-01') problems.push(`${id}: no part is drawn back along its way in`);
  return problems;
}, { id, guide, PHRASES });

/** Phone layout: the 3D view first and visible, nothing scrolls sideways, every visible control labelled and its
 * target (its own box, or the label that holds it) at least 44 x 44 px. */
const phoneProblems = page => page.evaluate(() => {
  const problems = [], app = document.querySelector('#app').getBoundingClientRect(), panel = document.querySelector('#panel').getBoundingClientRect();
  const canvas = document.querySelector('#app canvas')?.getBoundingClientRect();
  if (!(app.top < panel.top && canvas && canvas.height > 200 && canvas.top < innerHeight / 2)) problems.push(`the 3D view is not first (view ${app.top}, panel ${panel.top})`);
  if (document.documentElement.scrollWidth > innerWidth + 1) problems.push('the page scrolls sideways');
  const bar = document.querySelector('nav.appnav')?.getBoundingClientRect();
  if (bar && app.top < bar.bottom - 1) problems.push(`the 3D view starts under the site bar (${app.top} < ${bar.bottom})`);
  if (panel.top < app.bottom - 1) problems.push(`the panel covers ${Math.round(app.bottom - panel.top)} px of the 3D view`);
  for (const e of document.querySelectorAll('#hud a, #hud button, #hud select, #hud input, nav.appnav a')) {
    if (!e.getClientRects().length || getComputedStyle(e).visibility === 'hidden') continue;
    const target = (e.closest('label') || e).getBoundingClientRect();
    const name = (e.getAttribute('aria-label') || e.labels?.[0]?.textContent || e.textContent || e.title || '').trim();
    const what = `${e.tagName.toLowerCase()} "${name.slice(0, 30)}"`;
    if (!name) problems.push(`${what}: no label`);
    if (target.width < 44 || target.height < 44) problems.push(`${what}: ${Math.round(target.width)} x ${Math.round(target.height)} px`);
    if (target.left < 0 || target.right > innerWidth + 1) problems.push(`${what}: cut off at the screen's edge (${Math.round(target.left)}-${Math.round(target.right)} of ${innerWidth})`);
  }
  return problems;
});

/** A short phone (390 x 664): with the panel unscrolled, Previous and Next and the first two lines of the step's text
 * are on screen below the 3D view, however long the step's text is (steps 8 and 10 are the longest). */
const firstScreenProblems = (page, id) => page.evaluate(id => {
  const problems = [], panel = document.querySelector('#panel'), app = document.querySelector('#app').getBoundingClientRect();
  if (panel.scrollTop !== 0) problems.push(`${id}: the panel is scrolled`);
  for (const name of ['Previous', 'Next']) {
    const b = [...panel.querySelectorAll('button')].find(e => e.textContent.trim() === name)?.getBoundingClientRect();
    if (!b || b.top < app.bottom - 1 || b.bottom > innerHeight) problems.push(`${id}: ${name} is not on the first screen (${b?.top}-${b?.bottom} of ${innerHeight})`);
  }
  const text = panel.querySelector('.guide-text'), r = text.getBoundingClientRect(), line = parseFloat(getComputedStyle(text).lineHeight) || 24;
  if (r.top < app.bottom - 1 || r.top + 2 * line > innerHeight) problems.push(`${id}: the step's first lines are not on the first screen (text at ${Math.round(r.top)} of ${innerHeight})`);
  return problems;
}, id);

async function open(context) {
  const page = await context.newPage(), bad = [];
  page.on('pageerror', e => bad.push(e.message));
  page.on('console', m => { if (m.type() === 'error') bad.push('console: ' + m.text()); });
  page.on('response', r => { if (r.status() >= 400) bad.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  await page.goto(site.url + route);
  await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 60000 });
  return { page, bad };
}
const choose = async (page, id) => { await page.getByRole('combobox', { name: 'Instruction step', exact: true }).selectOption(id); await page.evaluate(() => new Promise(requestAnimationFrame)); };

try {
  browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? 'chromium' : 'chrome', executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true } : { headless: true });
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: 'reduce' });
    try {
      const { page, bad } = await open(context);
      assert.equal(await page.locator('#title').textContent(), 'Gyropup turret');
      for (const id of STEPS) {
        await choose(page, id);
        assert.deepEqual(await stepProblems(page, id), [], `${viewport.width}px ${id}`);
        await page.screenshot({ path: `${out}/${engine.name()}-${viewport.width}-${id}.png` });
        cases.push({ viewport: viewport.width, step: id });
      }
      // Next and Previous walk the authored order.
      await page.getByRole('button', { name: 'Next', exact: true }).click();
      assert.equal(await page.getByLabel('Instruction step', { exact: true }).inputValue(), 'step-12');
      await page.getByRole('button', { name: 'Previous', exact: true }).click();
      assert.equal(await page.getByLabel('Instruction step', { exact: true }).inputValue(), 'step-11');
      // Planted: a scene that does not follow the step (step 11's new parts hidden) is caught.
      await page.evaluate(() => { const s = window.__viewer.getState(); window.__viewer.applyState({ ...s, visible: s.visible.filter(n => n !== 'barrel'), highlight: s.highlight.filter(n => n !== 'barrel') }); });
      assert.ok((await stepProblems(page, 'step-11')).some(p => /barrel/.test(p)), 'planted: a hidden new part is caught');
      if (viewport.width === 390) {
        await page.setViewportSize({ width: 390, height: 664 });
        for (const id of ['step-08', 'step-10']) {
          await choose(page, id);
          assert.deepEqual(await firstScreenProblems(page, id), [], `390 x 664 ${id}`);
          await page.screenshot({ path: `${out}/${engine.name()}-390x664-${id}.png` });
        }
        // Planted: the version line and qualification back above the step (their desktop order) push Next off screen.
        const plant = await page.addStyleTag({ content: '.guide-controls>.guide-version,.guide-controls>.guide-qualification{order:0!important}.guide-controls>h2{order:-1!important}' });
        assert.ok((await firstScreenProblems(page, 'step-10')).some(p => /Next is not on the first screen/.test(p)), 'planted: buttons pushed off a short phone are caught');
        await plant.evaluate(e => e.remove());
        await page.setViewportSize(viewport);
        await choose(page, 'step-08');
        assert.deepEqual(await phoneProblems(page), [], 'phone layout');
        // Planted controls: a 30 px button, an unlabelled part checkbox and the panel moved above the view are caught.
        await page.addStyleTag({ content: '#panel .hud-btn{min-height:0!important;height:30px!important}' });
        assert.ok((await phoneProblems(page)).some(p => /button "ISO": \d+ x 30 px/.test(p)), 'planted: a small button is caught');
        await page.evaluate(() => document.querySelector('#panel input[type=checkbox][aria-label^="Show "]').removeAttribute('aria-label'));
        await page.evaluate(() => { const row = document.querySelector('#panel label.hud-toggle input:not([aria-label])').closest('label'); row.replaceWith(...row.childNodes); });
        assert.ok((await phoneProblems(page)).some(p => /no label/.test(p)), 'planted: an unlabelled control is caught');
        await page.addStyleTag({ content: '#panel{top:0!important;bottom:auto!important;height:60vh!important}#app{top:60vh!important}' });
        assert.ok((await phoneProblems(page)).some(p => /3D view is not first/.test(p)), 'planted: the panel above the view is caught');
      }
      assert.deepEqual(bad, [], `${viewport.width}px: errors`);
      cases.push({ viewport: viewport.width, planted: true });
    } finally { await context.close(); }
  }
  // The URL visitors get: the cards link the reader with nav=1, so the site's bar sits above it (review of #812).
  for (const viewport of [{ width: 390, height: 664 }, { width: 360, height: 640 }]) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: 'reduce' });
    try {
      const page = await context.newPage(), bad = [];
      page.on('pageerror', e => bad.push(e.message));
      page.on('console', m => { if (m.type() === 'error') bad.push('console: ' + m.text()); });
      page.on('response', r => { if (r.status() >= 400) bad.push(`${r.status()} ${new URL(r.url()).pathname}`); });
      await page.goto(site.url + route + '&nav=1');
      await page.waitForFunction(() => document.body.dataset.ready === '1' && document.querySelector('nav.appnav'), null, { timeout: 60000 });
      for (const id of ['step-08', 'step-10']) {
        await choose(page, id);
        assert.deepEqual([...await phoneProblems(page), ...await firstScreenProblems(page, id)], [], `nav=1 ${viewport.width} x ${viewport.height} ${id}`);
      }
      await page.screenshot({ path: `${out}/${engine.name()}-nav-${viewport.width}x${viewport.height}.png` });
      if (viewport.width === 360) {
        // Planted: the bar's desktop tab size, and the view at its full 55vh under the bar (as before), are each caught.
        const small = await page.addStyleTag({ content: '.appnav a.tab{min-height:0!important;padding:6px 10px!important;font-size:12px!important;letter-spacing:.08em!important}' });
        const found = await phoneProblems(page);
        assert.ok(found.some(p => /^a ".*": \d+ x \d\d? px|cut off at the screen's edge/.test(p) && /Explore|Toolkit|For agents/.test(p)), `planted: small or cut-off bar tabs are caught (${found.join('; ')})`);
        await small.evaluate(e => e.remove());
        const under = await page.addStyleTag({ content: 'body #app{height:55vh!important}' });
        assert.ok((await phoneProblems(page)).some(p => /the panel covers \d+ px of the 3D view/.test(p)), 'planted: a panel over the view is caught');
        await under.evaluate(e => e.remove());
      }
      assert.deepEqual(bad, [], `nav=1 ${viewport.width}: errors`);
      cases.push({ viewport: viewport.width, nav: true });
    } finally { await context.close(); }
  }
  await writeFile(`${out}/${engine.name()}-example-report.json`, JSON.stringify({ passed: true, browser: browser.version(), cases }, null, 2));
  console.log(JSON.stringify({ passed: true, engine: engine.name(), cases: cases.length, out }));
} finally { try { await browser?.close(); } finally { await site.close(); } }
