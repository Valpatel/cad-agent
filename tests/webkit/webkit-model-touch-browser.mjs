/** <cad-model> touch arbitration (#650, #769): a one-finger drag on the canvas turns the model vertically and sideways
 * without scrolling the page while the viewer is at most half as tall as the space that scrolls past it (the visible
 * viewport, or a shorter ancestor box that can scroll vertically); a drag outside the canvas still scrolls; a taller
 * viewer leaves vertical swipes to the page or the box and still turns sideways; two fingers zoom the page and leave
 * the view alone. Both homepage models, phone portrait and landscape, auto-turn off.
 *
 * The share check lays two viewers side by side with the homepage's own site.css and home.css, opens each page in
 * portrait and resizes it (so the rule is also re-decided on an orientation change), centres the first viewer and
 * swipes vertically from a 7 x 5 grid of start points. At 844x390, 740x360, 932x430 and 1024x768 (where the viewers
 * are 56 % of the height, so a looser threshold fails) at least half of them must scroll the page. At 390x844, where
 * the viewers keep vertical turning, the floor is a loose 10 of 35: the home page measures 18/35 there, 28/35 at
 * 412x915 and 15/35 at 360x640 with the first viewer centred, and 7/35, 7/35 and 14/35 at the worst offset with both
 * viewers on screen (about 51-62 % of the screen then takes the swipe, and only the band between the cards and the side
 * gutters scroll). The page is never trapped there, and those figures are the same as before #769.
 *
 * The box check puts a 300 px and a 120 px viewer in a 320 px overflow-y:auto box, the 300 px one again behind an
 * auto-height overflow-x:auto and an auto-height overflow-y:auto wrapper holding the box's content (wrappers that
 * cannot scroll do not count),
 * and a 120 px viewer whose only wrapper is overflow-x:auto; it pins the threshold with a 422/423 px viewer at 390x844,
 * a pointer that went down without a lift that must not stop the next one-finger turn, and a viewer moved into the box
 * at the same size (re-decided after the move; in Chromium the element's ResizeObserver also fires on the move, so this
 * does not isolate the reconnect call).
 *
 * Chromium gets real touch input through CDP Input.dispatchTouchEvent in a hasTouch/isMobile context, so the browser's
 * own touch-action and scroll arbitration decides the outcome. That is emulated touch in desktop Chromium: Safari's
 * and Chrome Android's own gesture handling, browser toolbars that resize the viewport, and physical phones are not
 * covered. Playwright cannot inject a touch drag into WebKit, so
 * the WebKit run checks only the computed arbitration contract and a real tap; drag arbitration on Safari remains a
 * physical-device check. Neither engine run is a physical phone. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium, webkit } from '../site/npm-context.mjs';
import { serveWebkit } from './webkit-server.mjs';

const models = new URL('../../tools/site/assets/models/', import.meta.url);
const siteCss = new URL('../../tools/site/assets/site.css', import.meta.url), homeCss = new URL('../../tools/site/assets/home.css', import.meta.url);
const fixture = new URL('../fixtures/model/', import.meta.url);
const file = (name, type, from = models) => async (_, res) => res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' }).end(await readFile(new URL(name, from)));
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
// The homepage's "See it run" row with the site's real stylesheets (gutters, grid, article padding), between tall fillers.
const lorem = 'A short description of the model, as the homepage cards carry under each viewer, wrapping to a few lines.';
const card = (id, name) => `<article><h3>${name}</h3><cad-model id="${id}" src="/m/two-parts.json" label="${name}" turn="0" loading="eager" style="aspect-ratio:1"></cad-model><p>${lorem}</p></article>`;
const home = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cad-model scroll share</title><link rel="stylesheet" href="/web/site.css"><link rel="stylesheet" href="/kit/model/model.css"><link rel="stylesheet" href="/web/home.css">
<style>.filler{height:1600px}</style><div class="filler"></div><div class="wrap"><section class="section built-with"><div class="project-viewers">
${card('left', 'Left')}${card('right', 'Right')}</div></section></div><div class="filler"></div><script type="module" src="/kit/model/model.js"></script></html>`;
// A scrollable box holding a viewer nearly as tall as the box and a small one, on a page that scrolls too.
const viewer = (id, h) => `<cad-model id="${id}" src="/m/two-parts.json" label="${id}" turn="0" loading="eager" style="height:${h}px"></cad-model>`;
const nested = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cad-model in a box</title><link rel="stylesheet" href="/kit/model/model.css">
<style>body{margin:0}.filler{height:900px}.box{height:320px;overflow-y:auto;margin:0 24px 400px;border:1px solid}.pad{height:260px}
.tail{height:900px}cad-model{aspect-ratio:auto;width:100%}</style><div class="filler"></div><div class="box" id="box"><div class="pad"></div>
${viewer('big', 300)}<div class="pad"></div>${viewer('small', 120)}<div class="tail"></div></div>
<div class="box" id="boxx"><div style="overflow-x:auto"><div class="pad"></div>${viewer('bigx', 300)}<div class="tail"></div></div></div>
<div class="box" id="boxy"><div style="overflow-y:auto"><div class="pad"></div>${viewer('bigy', 300)}<div class="tail"></div></div></div>
<div style="overflow-x:auto;margin:0 24px">${viewer('smallx', 120)}</div><div class="filler"></div><script type="module" src="/kit/model/model.js"></script></html>`;
const site = await serveWebkit(new Map([
  ['/', (_, res) => res.writeHead(200, { 'Content-Type': 'text/html' }).end(page)],
  ['/home', (_, res) => res.writeHead(200, { 'Content-Type': 'text/html' }).end(home)],
  ['/nested', (_, res) => res.writeHead(200, { 'Content-Type': 'text/html' }).end(nested)],
  ['/web/site.css', file(siteCss.href, 'text/css')],
  ['/web/home.css', file(homeCss.href, 'text/css')],
  ['/m/two-parts.json', file('two-parts.json', 'application/json', fixture)],
  ['/m/two-parts.bin', file('two-parts.bin', 'application/octet-stream', fixture)],
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
const scrollTop = (p, id) => p.evaluate(id => Math.round(document.getElementById(id).scrollTop), id);
/** Wait out any fling from an earlier scroll (of the page, or of the element `id`), so it cannot be blamed on the next
 * gesture. A scroll that never comes to rest within 300 frames is a named failure, not a hang. */
const settle = (p, id = null) => p.evaluate(id => new Promise((resolve, reject) => {
  const at = () => id ? document.getElementById(id).scrollTop : scrollY;
  let last = at(), still = 0, n = 0;
  const step = () => {
    const y = at();
    if (y === last) still++; else { still = 0; last = y; }
    if (still > 8) resolve();
    else if (++n >= 300) reject(new Error(`scrolling did not come to rest within 300 frames; last ${id ? `#${id} scrollTop` : 'scrollY'} ${y}`));
    else requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}), id);
/** Scroll the viewer to the middle of the screen, with room to scroll both ways. */
const centre = async (p, id) => {
  await settle(p);
  await p.evaluate(id => { const r = document.getElementById(id).getBoundingClientRect(); scrollTo({ top: scrollY + r.top - (innerHeight - r.height) / 2, behavior: 'instant' }); }, id);
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

  // In portrait the homepage viewers are under half the screen's height, so they take vertical drags; in landscape they
  // are taller than half of it, so vertical swipes scroll the page and sideways drags turn. Pinch zoom stays with the page.
  const upright = viewport.width < viewport.height, want = upright ? 'pinch-zoom' : 'pan-y pinch-zoom';
  for (const id of ['gyropup', 'j501'])
    check(await action(id) === want, `${name} ${id}: canvas touch-action ${await action(id)}, want ${want}`);
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
    const turns = upright ? [['vertical', 0, -reach], ['vertical-down', 0, reach], ['horizontal', reach, 0], ['diagonal', reach * 0.6, -reach * 0.8]]
      : [['horizontal', reach, 0], ['horizontal-back', -reach, 0]];
    for (const [dir, dx, dy] of turns) {
      await settle(p);
      const y0 = await scrollY(p), before = await shot(p, id);
      await touchDrag(cdp, p, [cx - dx / 2, cy - dy / 2], [cx + dx / 2, cy + dy / 2]);
      const y1 = await scrollY(p), after = await shot(p, id);
      check(y1 === y0, `${tag} ${dir} drag scrolled the page: scrollY ${y0} -> ${y1}`);
      check(after !== before, `${tag} ${dir} drag did not turn the model`);
    }
    if (!upright) {
      await settle(p);
      const y0 = await scrollY(p);
      await touchDrag(cdp, p, [cx, cy + reach / 2], [cx, cy - reach / 2]);
      check(await scrollY(p) > y0 + 40, `${tag} a vertical swipe on a viewer taller than half the screen must scroll the page: ${y0} -> ${await scrollY(p)}`);
      await centre(p, id);
    }
    // A one-finger move along the axis this viewer turns on: up where it takes vertical drags, else to the left.
    const away = (x, y, d) => upright ? [x, y - d] : [x - d, y];
    // Release outside the canvas (pointer capture keeps the drag), then scroll from outside the canvas right away.
    {
      const y0 = await scrollY(p), before = await shot(p, id);
      await touchDrag(cdp, p, [cx, cy], upright ? [cx, Math.max(2, b.y - 40)] : [Math.max(2, b.x - 20), cy]);
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
      await touchDrag(cdp, p, [b.x + b.w / 2, b.y + b.h / 2], away(b.x + b.w / 2, b.y + b.h / 2, 40), { end: 'touchCancel' });
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
      await touchDrag(cdp, p, [x - 30, y], away(x - 30, y, 40), { extra: [{ x: x + 30, y, id: 1, radiusX: 4, radiusY: 4, force: 1 }] });
      const scale = await p.evaluate(() => visualViewport.scale);
      check(Math.abs(scale - 1) < 0.01, `${tag} a parallel two-finger drag changed the page scale to ${scale}`);
      await settle(p);
      const y0 = await scrollY(p), before = await shot(p, id);
      // Downward where it tilts: earlier drags left the tilt at its low stop.
      await touchDrag(cdp, p, upright ? [x, y - reach / 2] : [x - reach / 2, y], upright ? [x, y + reach / 2] : [x + reach / 2, y]);
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
  // A real pinch (two fingers spreading) on a viewer zooms the page and leaves the view as it was. Last, since the page
  // stays zoomed.
  {
    await centre(p, 'gyropup');
    const b = await box(p, 'gyropup'), x = b.x + b.w / 2, y = b.y + b.h / 2, before = await shot(p, 'gyropup');
    const finger = (id, dx) => ({ x: x + dx, y, id, radiusX: 4, radiusY: 4, force: 1 });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [finger(0, -20), finger(1, 20)] });
    for (let i = 1; i <= 6; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [finger(0, -20 - 15 * i), finger(1, 20 + 15 * i)] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await frames(p); await frames(p);
    const scale = await p.evaluate(() => visualViewport.scale);
    check(scale > 1.05, `${name}: a pinch on a viewer must zoom the page, visualViewport.scale ${scale}`);
    check(await shot(p, 'gyropup') === before, `${name}: a pinch on a viewer must leave the view alone, but the model turned`);
  }
  check(errors.length === 0, `${name}: page errors ${errors.join('; ')}`);
  await context.close();
}

const MIN_SHARE = 0.5;   // the rule's promise: a row of viewers leaves at least half of the screen's height to scroll from
const PORTRAIT_FLOOR = 10 / 35;   // portrait viewers keep vertical turning; the home page measures 18/35 there
/** Two viewers side by side under the homepage's real stylesheets. Each phone size gets its own page, opened in
 * portrait and resized to that size (so the rule must be re-decided), runs in parallel with the others, centres the
 * row (the worst place for it) and swipes vertically from a 7 x 5 grid of start points; at least MIN_SHARE must
 * scroll the page (PORTRAIT_FLOOR in portrait). */
async function share() {
  const sizes = [[390, 844], [844, 390], [740, 360], [932, 430], [1024, 768]];
  const one = async ([width, height]) => {
    const name = `${width}x${height}`;
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
    const p = await context.newPage(), errors = [];
    p.on('pageerror', e => errors.push(String(e)));
    try {
      await p.goto(site.url + '/home');
      for (const id of ['left', 'right']) await p.waitForFunction(id => document.getElementById(id)?.dataset.state === 'ready', id, { timeout: 60000 });
      await p.setViewportSize({ width, height });
      // The rule is re-decided on the resize; wait until it agrees with the new size, then read what it chose.
      const agreed = await p.waitForFunction(() => ['left', 'right'].every(id => {
        const el = document.getElementById(id), want = el.clientHeight <= visualViewport.height / 2 ? 'pinch-zoom' : 'pan-y pinch-zoom';
        return el.querySelector('canvas')?.style.touchAction === want;
      }), null, { timeout: 10000 }).then(() => true, () => false);
      check(agreed, `${name}: after the resize the viewers' touch-action does not follow the half-height rule`);
      const actions = await p.evaluate(() => ['left', 'right'].map(id => document.querySelector(`#${id} canvas`).style.touchAction));
      const cdp = await context.newCDPSession(p);
      let scrolled = 0, total = 0, moved = true;
      for (let row = 0; row < 5; row++) for (let col = 0; col < 7; col++) {
        if (moved) await centre(p, 'left');
        const x = (col + 0.5) / 7 * width, y = (row + 0.5) / 5 * height, y0 = await scrollY(p);
        await touchDrag(cdp, p, [x, y], [x, y + (y < height / 2 ? 60 : -60)]);
        moved = Math.abs(await scrollY(p) - y0) >= 20;
        scrolled += moved; total++;
      }
      const floor = width < height ? PORTRAIT_FLOOR : MIN_SHARE;
      check(scrolled / total >= floor, `${name}: a vertical swipe scrolled the page from ${scrolled} of ${total} start points; want at least ${Math.ceil(floor * total)}`);
      check(errors.length === 0, `${name}: page errors ${errors.join('; ')}`);
      return `${name} ${scrolled}/${total} (${actions.join(' / ')})`;
    } finally { await context.close(); }
  };
  console.log(`vertical swipes that scroll with two viewers side by side: ${(await Promise.all(sizes.map(one))).join('; ')}`);
}

/** Viewers in 320 px overflow-y:auto boxes (directly, and behind auto-height wrappers that cannot scroll), a small one
 * behind an overflow-x:auto wrapper, the exact half-height boundary, and a pointer that went down without a lift. */
async function nestedBox() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  const p = await context.newPage(), errors = [];
  p.on('pageerror', e => errors.push(String(e)));
  await p.goto(site.url + '/nested');
  const ids = ['big', 'small', 'bigx', 'bigy', 'smallx'];
  for (const id of ids) await p.waitForFunction(id => document.getElementById(id)?.dataset.state === 'ready', id, { timeout: 60000 });
  const cdp = await context.newCDPSession(p);
  const action = id => p.evaluate(id => document.querySelector(`#${id} canvas`).style.touchAction, id);
  // Bring the box to the middle of the page, then the viewer to the middle of the box.
  const inBox = async (id, boxId) => {
    await settle(p); await settle(p, boxId);
    await p.evaluate(([id, boxId]) => {
      const box = document.getElementById(boxId), r = box.getBoundingClientRect();
      scrollTo({ top: scrollY + r.top - (innerHeight - r.height) / 2, behavior: 'instant' });
      const v = document.getElementById(id).getBoundingClientRect(), b = box.getBoundingClientRect();
      box.scrollTop += v.top - b.top - (box.clientHeight - v.height) / 2;
    }, [id, boxId]);
    await settle(p); await settle(p, boxId);
    return box(p, id);
  };
  const wants = { big: 'pan-y pinch-zoom', small: 'pinch-zoom', bigx: 'pan-y pinch-zoom', bigy: 'pan-y pinch-zoom', smallx: 'pinch-zoom' };
  for (const [id, want] of Object.entries(wants)) check(await action(id) === want, `box ${id}: touch-action ${await action(id)}, want ${want}`);
  // A 300 px viewer, directly in the box or behind a wrapper that cannot scroll: a vertical swipe on it scrolls the box.
  for (const [id, boxId] of [['big', 'box'], ['bigx', 'boxx'], ['bigy', 'boxy']]) {
    const b = await inBox(id, boxId), x = b.x + b.w / 2, y = b.y + b.h / 2, t0 = await scrollTop(p, boxId);
    await touchDrag(cdp, p, [x, y + 50], [x, y - 50]);
    check(await scrollTop(p, boxId) > t0 + 40, `box ${id}: a vertical swipe on the 300 px viewer must scroll #${boxId}: scrollTop ${t0} -> ${await scrollTop(p, boxId)}`);
  }
  {
    const b = await inBox('small', 'box'), x = b.x + b.w / 2, y = b.y + b.h / 2, t0 = await scrollTop(p, 'box'), y0 = await scrollY(p), before = await shot(p, 'small');
    await touchDrag(cdp, p, [x, y + 40], [x, y - 40]);
    check(await scrollTop(p, 'box') === t0 && await scrollY(p) === y0, `box: a vertical drag on the 120 px viewer scrolled (box ${t0} -> ${await scrollTop(p, 'box')})`);
    check(await shot(p, 'small') !== before, 'box: a vertical drag on the 120 px viewer did not turn the model');
  }
  // A 120 px viewer whose only wrapper is overflow-x:auto keeps vertical turning on the page; so it does after a
  // pointer went down on it with no lift (a lift the viewer never saw), since a new gesture starts afresh.
  for (const phantom of [false, true]) {
    const tag = phantom ? 'after a pointer with no lift' : 'behind overflow-x:auto';
    await centre(p, 'smallx');
    const b = await box(p, 'smallx'), x = b.x + b.w / 2, y = b.y + b.h / 2, y0 = await scrollY(p), before = await shot(p, 'smallx');
    if (phantom) await p.evaluate(([x, y]) => document.querySelector('#smallx canvas').dispatchEvent(new PointerEvent('pointerdown',
      { pointerId: 99, isPrimary: false, pointerType: 'touch', clientX: x, clientY: y, bubbles: true })), [x, y]);
    const d = phantom ? -40 : 40;   // the other way the second time: the first drag leaves the tilt at its stop
    await touchDrag(cdp, p, [x, y + d], [x, y - d]);
    check(await shot(p, 'smallx') !== before, `box smallx: a vertical one-finger drag ${tag} did not turn the model`);
    check(await scrollY(p) === y0, `box smallx: a vertical one-finger drag ${tag} scrolled the page`);
  }
  // The threshold itself: half of the 844 px viewport is 422 px.
  for (const [height, want] of [[422, 'pinch-zoom'], [423, 'pan-y pinch-zoom'], [120, 'pinch-zoom']]) {
    await p.evaluate(h => { document.getElementById('smallx').style.height = `${h}px`; }, height);
    const ok = await p.waitForFunction(want => document.querySelector('#smallx canvas').style.touchAction === want, want, { timeout: 10000 }).then(() => true, () => false);
    check(ok, `box: a ${height} px viewer in an 844 px viewport must have touch-action ${want}, got ${await action('smallx')}`);
  }
  // Taller box: the big viewer is now under half of it and takes vertical drags; back to 320 px, it gives them up again.
  for (const [height, want] of [[700, 'pinch-zoom'], [320, 'pan-y pinch-zoom']]) {
    await p.evaluate(h => { document.getElementById('box').style.height = `${h}px`; }, height);
    const ok = await p.waitForFunction(want => document.querySelector('#big canvas').style.touchAction === want, want, { timeout: 10000 }).then(() => true, () => false);
    check(ok, `box: after the box became ${height} px the 300 px viewer did not switch to ${want}`);
  }
  // Moved into the 320 px box at the same size: the rule is decided again (on reconnect, and in Chromium also by the
  // element's ResizeObserver, which reports again after a move), so the 300 px viewer gives vertical swipes to the box.
  {
    await p.evaluate(() => Object.assign(document.getElementById('smallx').style, { height: '300px', width: '300px' }));
    const before = await p.waitForFunction(() => document.querySelector('#smallx canvas').style.touchAction === 'pinch-zoom', null, { timeout: 10000 }).then(() => true, () => false);
    check(before, `box: a 300 px viewer on the 844 px page must take vertical drags before the move, got ${await action('smallx')}`);
    await p.evaluate(() => document.getElementById('box').prepend(document.getElementById('smallx')));
    const after = await p.waitForFunction(() => document.querySelector('#smallx canvas').style.touchAction === 'pan-y pinch-zoom', null, { timeout: 10000 }).then(() => true, () => false);
    check(after, `box: a 300 px viewer moved into the 320 px box must leave vertical swipes to it, got ${await action('smallx')}`);
  }
  check(errors.length === 0, `box: page errors ${errors.join('; ')}`);
  await context.close();
}

try {
  await scenario('portrait', { width: 390, height: 844 });
  await scenario('landscape', { width: 844, height: 390 });
  if (engineName === 'chromium') { await share(); await nestedBox(); }
} finally {
  await browser.close();
  await site.close();
}
if (failures.length) {
  console.error(`${failures.length} of ${checks} touch checks failed (${engineName}):\n- ${failures.join('\n- ')}`);
  process.exit(1);
}
console.log(`cad-model touch arbitration: ${checks} checks passed (${engineName})`);
