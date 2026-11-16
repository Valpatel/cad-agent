/** <cad-model> touch arbitration (#650): a one-finger drag on the canvas turns the model vertically and sideways without
 * scrolling the page, while a drag outside the canvas still scrolls it, and a viewer too big to scroll past keeps
 * vertical swipes for the page. Both homepage models, phone portrait and landscape, auto-turn off.
 *
 * Chromium gets real touch input through CDP Input.dispatchTouchEvent in a hasTouch/isMobile context, so the browser's
 * own touch-action and scroll arbitration decides the outcome. Playwright cannot inject a touch drag into WebKit, so
 * the WebKit run checks only the computed arbitration contract and a real tap; drag arbitration on Safari remains a
 * physical-device check. Neither engine run is a physical phone. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium, webkit } from '../site/npm-context.mjs';
import { serveWebkit } from './webkit-server.mjs';

const models = new URL('../../tools/site/assets/models/', import.meta.url);
const file = (name, type) => async (_, res) => res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' }).end(await readFile(new URL(name, models)));
// The homepage "Built with cad-agent" layout (tools/site/assets/home.css): two columns, one below 700 px, square viewers.
const page = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cad-model touch</title><link rel="stylesheet" href="/kit/model/model.css">
<style>body{margin:0;font:16px/1.5 system-ui}.wrap{padding:0 16px}.filler{height:1200px;background:linear-gradient(#eee,#ccc)}
.project-viewers{display:grid;grid-template-columns:1fr 1fr;gap:24px}.project-viewers article{padding:22px;min-width:0}
.project-viewers cad-model{width:100%}@media(max-width:700px){.project-viewers{grid-template-columns:1fr}.project-viewers article{padding:16px}}
.bleed cad-model{width:100vw;aspect-ratio:1}</style>
<div class="filler" id="above">Above</div><div class="wrap"><div class="project-viewers">
<article><h3>Gyropup</h3><cad-model id="gyropup" src="/models/gyropup.json" label="Gyropup" turn="0" loading="eager" style="aspect-ratio:1"></cad-model></article>
<article><h3>J501</h3><cad-model id="j501" src="/models/j501.json" label="J501" turn="0" loading="eager" style="aspect-ratio:1"></cad-model></article>
</div></div><div class="filler" id="between">Between</div>
<div class="bleed"><cad-model id="bleed" src="/models/gyropup.json" label="Full bleed" turn="0" loading="eager"></cad-model></div>
<div class="filler">Below</div><script type="module" src="/kit/model/model.js"></script></html>`;
const site = await serveWebkit(new Map([
  ['/', (_, res) => res.writeHead(200, { 'Content-Type': 'text/html' }).end(page)],
  ['/favicon.ico', (_, res) => res.writeHead(204).end()],
  ...['gyropup', 'j501'].flatMap(n => [[`/models/${n}.json`, file(`${n}.json`, 'application/json')],
    [`/models/${n}.bin`, file(`${n}.bin`, 'application/octet-stream')]]),
]));
const engineName = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? 'webkit' : 'chromium';
const engine = engineName === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engineName === 'chromium'
  ? { headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : { channel: 'chromium' }) }
  : { headless: true });
const failures = [];
let checks = 0;
const check = (ok, message) => { checks++; if (!ok) failures.push(message); };

// The middle of the page gutter left of a viewer (the wrap, the article padding and the column gap): touches a few px
// from the canvas are adjusted onto it by the browser's touch targeting, so a scroll test must land clear of it.
const gutter = b => b.x - Math.min(b.x, 68) / 2;
const frames = p => p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
const scrollY = p => p.evaluate(() => Math.round(scrollY));
/** Wait out any fling from an earlier scroll, so it cannot be blamed on the next gesture. */
const settle = p => p.evaluate(() => new Promise(resolve => {
  let last = scrollY, still = 0;
  const step = () => { if (scrollY === last) still++; else { still = 0; last = scrollY; } if (still > 8) resolve(); else requestAnimationFrame(step); };
  requestAnimationFrame(step);
}));
/** Scroll the viewer to the middle of the screen, with room to scroll both ways. */
const centre = async (p, id) => {
  await settle(p);
  await p.evaluate(id => { const r = document.getElementById(id).getBoundingClientRect(); scrollTo(0, scrollY + r.top - (innerHeight - r.height) / 2); }, id);
  await settle(p);
};
const shot = (p, id) => p.evaluate(id => document.getElementById(id).snapshot(48, 48), id);
const box = (p, id) => p.evaluate(id => { const r = document.getElementById(id).getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }, id);

/** One finger (or several) moving in steps through the browser's real touch pipeline. */
async function touchDrag(cdp, p, from, to, { steps = 4, end = 'touchEnd', extra = [] } = {}) {
  const point = (x, y, id = 0) => ({ x, y, id, radiusX: 4, radiusY: 4, force: 1 });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point(...from), ...extra] });
  for (let i = 1; i <= steps; i++) {
    const k = i / steps, dx = (to[0] - from[0]) * k, dy = (to[1] - from[1]) * k;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [point(from[0] + dx, from[1] + dy), ...extra.map(t => ({ ...t, x: t.x + dx, y: t.y + dy }))] });
  }
  await cdp.send('Input.dispatchTouchEvent', { type: end, touchPoints: [] });
  await frames(p); await frames(p);
}

async function scenario(name, viewport) {
  const context = await browser.newContext({ viewport, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  const p = await context.newPage();
  const errors = [];
  p.on('pageerror', e => errors.push(String(e)));
  await p.goto(site.url + '/');
  for (const id of ['gyropup', 'j501', 'bleed'])
    await p.waitForFunction(id => ['ready', 'error'].includes(document.getElementById(id)?.dataset.state), id, { timeout: 60000 });
  const states = await p.evaluate(() => ['gyropup', 'j501', 'bleed'].map(id => document.getElementById(id).dataset.state));
  assert.deepEqual(states, ['ready', 'ready', 'ready'], `${name}: models must load (${errors.join('; ')})`);
  const action = id => p.evaluate(id => getComputedStyle(document.querySelector(`#${id} canvas`)).touchAction, id);

  for (const id of ['gyropup', 'j501']) {
    // The homepage viewers leave room to scroll past, so they take vertical drags; pinch zoom stays with the page.
    check(await action(id) === 'pinch-zoom', `${name} ${id}: canvas touch-action ${await action(id)}, want pinch-zoom`);
  }
  check(await action('bleed') === 'pan-y pinch-zoom' || viewport.width < viewport.height,
    `${name} bleed: a viewer too big to scroll past must leave vertical swipes to the page, got ${await action('bleed')}`);

  if (engineName === 'webkit') {
    // A real tap still names a part; drag arbitration cannot be injected here (see the header).
    const b = await (async () => { await p.locator('#gyropup').scrollIntoViewIfNeeded(); return box(p, 'gyropup'); })();
    await p.touchscreen.tap(b.x + b.w / 2, b.y + b.h / 2);
    await frames(p);
    const label = await p.locator('#gyropup .cad-model-label').textContent();
    check(label !== 'Drag to turn', `${name} gyropup: a tap on the model must name a part, label still "${label}"`);
    console.log(`${name}: WebKit touch drag arbitration NOT injected (Playwright has no WebKit touch-drag input); physical Safari check remains`);
    await context.close();
    return;
  }

  const cdp = await context.newCDPSession(p);
  for (const id of ['gyropup', 'j501']) {
    const tag = `${name} ${id}`;
    await centre(p, id);
    let b = await box(p, id);
    const cx = b.x + b.w / 2, cy = b.y + b.h / 2, reach = Math.min(b.w, b.h) * 0.3;
    for (const [dir, dx, dy] of [['vertical', 0, -reach], ['vertical-down', 0, reach], ['horizontal', reach, 0], ['diagonal', reach * 0.6, -reach * 0.8]]) {
      await settle(p);
      const y0 = await scrollY(p), before = await shot(p, id);
      await touchDrag(cdp, p, [cx - dx / 2, cy - dy / 2], [cx + dx / 2, cy + dy / 2]);
      const y1 = await scrollY(p), after = await shot(p, id);
      check(y1 === y0, `${tag} ${dir} drag scrolled the page: scrollY ${y0} -> ${y1}`);
      check(after !== before, `${tag} ${dir} drag did not turn the model`);
    }
    // Release outside the canvas (pointer capture keeps the drag), then scroll from outside the canvas right away.
    {
      const y0 = await scrollY(p), before = await shot(p, id);
      await touchDrag(cdp, p, [cx, cy], [cx, Math.max(2, b.y - 40)]);
      check(await scrollY(p) === y0, `${tag} drag released outside the canvas scrolled the page`);
      check(await shot(p, id) !== before, `${tag} drag released outside the canvas did not turn the model`);
      await settle(p);
      const y1 = await scrollY(p);
      await touchDrag(cdp, p, [gutter(b), cy + 50], [gutter(b), cy - 50]);
      check(await scrollY(p) > y1 + 50, `${tag} drag outside the canvas after a turn must scroll the page: ${y1} -> ${await scrollY(p)}`);
    }
    // A cancelled drag, then a page scroll from outside the canvas.
    {
      await centre(p, id);
      b = await box(p, id);
      const y0 = await scrollY(p);
      await touchDrag(cdp, p, [b.x + b.w / 2, b.y + b.h / 2], [b.x + b.w / 2, b.y + b.h / 2 - 40], { end: 'touchCancel' });
      check(await scrollY(p) === y0, `${tag} cancelled drag scrolled the page`);
      await touchDrag(cdp, p, [gutter(b), b.y + b.h / 2 + 50], [gutter(b), b.y + b.h / 2 - 50]);
      check(await scrollY(p) > y0 + 50, `${tag} drag outside the canvas after a cancel must scroll the page`);
    }
    // A second finger hands the gesture to the browser (pointercancel); one-finger turning still works afterwards.
    // Both fingers move together, so the page scale stays 1 and the touch coordinates stay layout coordinates.
    {
      await centre(p, id);
      b = await box(p, id);
      const x = b.x + b.w / 2, y = b.y + b.h / 2;
      await touchDrag(cdp, p, [x - 30, y], [x - 30, y - 40], { extra: [{ x: x + 30, y, id: 1, radiusX: 4, radiusY: 4, force: 1 }] });
      const scale = await p.evaluate(() => visualViewport.scale);
      check(Math.abs(scale - 1) < 0.01, `${tag} a parallel two-finger drag changed the page scale to ${scale}`);
      await settle(p);
      const y0 = await scrollY(p), before = await shot(p, id);
      await touchDrag(cdp, p, [x, y - reach / 2], [x, y + reach / 2]);   // downward: earlier drags left the tilt at its low stop
      check(await shot(p, id) !== before, `${tag} one-finger turn after a two-finger gesture did not turn the model`);
      check(await scrollY(p) === y0, `${tag} one-finger turn after a two-finger gesture scrolled the page`);
    }
    // A tap on the model names the part under the finger.
    {
      await centre(p, id);
      b = await box(p, id);
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: b.x + b.w / 2, y: b.y + b.h / 2, id: 0 }] });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await frames(p);
      const label = await p.locator(`#${id} .cad-model-label`).textContent();
      check(label !== 'Drag to turn', `${tag} a tap on the model centre must name a part, label "${label}"`);
    }
  }
  // Too big to scroll past: vertical swipes scroll the page, sideways drags still turn.
  if (viewport.width > viewport.height) {
    const cover = async () => {   // the fling after a swipe can carry the viewer off screen, so come back each time
      await settle(p);
      await p.evaluate(() => { const r = document.getElementById('bleed').getBoundingClientRect(); scrollTo(0, scrollY + r.top + 40); });
      await settle(p);
    };
    await cover();
    const b = await box(p, 'bleed'), x = viewport.width / 2, y = viewport.height / 2;
    check(b.y < 0 && b.y + b.h > viewport.height, `${name} bleed must cover the viewport for this control: ${JSON.stringify(b)}`);
    await settle(p);
    let y0 = await scrollY(p);
    await touchDrag(cdp, p, [x, y + 60], [x, y - 60]);
    check(await scrollY(p) > y0 + 40, `${name} bleed: a vertical swipe on a viewer that fills the screen must scroll the page`);
    await cover();
    y0 = await scrollY(p);
    const before = await shot(p, 'bleed');
    await touchDrag(cdp, p, [x - 80, y], [x + 80, y]);
    check(await shot(p, 'bleed') !== before, `${name} bleed: a sideways drag must still turn the model`);
    check(await scrollY(p) === y0, `${name} bleed: a sideways drag scrolled the page`);
  }
  check(errors.length === 0, `${name}: page errors ${errors.join('; ')}`);
  await context.close();
}

try {
  await scenario('portrait', { width: 390, height: 844 });
  await scenario('landscape', { width: 844, height: 390 });
} finally {
  await browser.close();
  await site.close();
}
if (failures.length) {
  console.error(`${failures.length} of ${checks} touch checks failed (${engineName}):\n- ${failures.join('\n- ')}`);
  process.exit(1);
}
console.log(`cad-model touch arbitration: ${checks} checks passed (${engineName})`);
