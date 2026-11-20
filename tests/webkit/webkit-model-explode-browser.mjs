/** <cad-model>'s Explode tween on its first animation frame (#680), through the real button in a real browser.
 *
 * A browser may hand the first requestAnimationFrame callback a timestamp a fraction of a millisecond earlier than the
 * performance.now() the click handler read. This suite makes that deterministic: once the viewer is ready it replaces
 * performance.now and requestAnimationFrame with a frozen clock and a manual frame queue, so each frame runs at a
 * timestamp the test chooses. Each case activates Explode by pointer or Enter, with ordinary or reduced motion, runs
 * the first frame 0.5 ms before the event, and checks the pose (world-space mesh landmarks), completion, reverse,
 * a mid-flight reversal, the off-screen frame stop and that no uncaught error reaches the page. A skewed-clock case
 * (#769) runs a turning viewer's frames with timestamps 5 s early and 60 s ahead then back, and the Explode tween with
 * its first frame 3 s early: the view must never step backwards (a frame stamped before the last one draws the same
 * picture) and the tween must start at the closed pose and finish exactly open.
 * Limits: the clock shim replaces the browser's own frame timing, so this proves the tween's arithmetic and control
 * wiring, not any engine's real frame scheduling; it runs in Chromium or WebKit (PLAYWRIGHT_BROWSER), not on devices.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium, webkit } from '../site/npm-context.mjs';
import { serveWebkit } from './webkit-server.mjs';

const fixture = new URL('../fixtures/model/', import.meta.url);
const [json, bin] = await Promise.all(['two-parts.json', 'two-parts.bin'].map(n => readFile(new URL(n, fixture))));
const routes = new Map([
  ['/favicon.ico', (_, res) => res.writeHead(204).end()],
  ['/m/two-parts.json', (_, res) => res.end(json)],
  ['/m/two-parts.bin', (_, res) => res.end(bin)],
  ['/shadow.html', (_, res) => {
    res.setHeader('Content-Type', 'text/html');
    res.end(`<!doctype html><script type="module" src="/kit/model/model.js"></script>
      <button id="before">Before model</button><div id="host"><template shadowrootmode="open">
      <link rel="stylesheet" href="/kit/model/model.css">
      <cad-model style="display:block;width:400px;height:250px" src="/m/two-parts.json" loading="scroll"></cad-model>
      </template></div>`);
  }],
  ['/index.html', (req, res) => { res.setHeader('Content-Type', 'text/html'); res.end(`<!doctype html><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/kit/model/model.css"><style>body{margin:0}cad-model{display:block;width:100%;height:60vh;min-height:230px}#spacer{height:300vh}</style><script type="module" src="/kit/model/model.js"></script><cad-model src="/m/two-parts.json" loading="eager" turn="${req.url.includes('turn') ? 30 : 0}" label="Fixture"></cad-model><div id="spacer"></div>`); }],
]);
/** Replace performance.now and requestAnimationFrame with a frozen clock and a manual frame queue (window.__clock). */
const freeze = page => page.evaluate(() => {
  let clock = Math.ceil(performance.now()) + 1000, id = 0; const queue = new Map(), caught = [];
  Object.defineProperty(performance, 'now', { configurable: true, value: () => clock });
  window.requestAnimationFrame = cb => { queue.set(++id, cb); return id; };
  window.cancelAnimationFrame = i => { queue.delete(i); };
  window.__clock = {
    now: () => clock, advance: ms => { clock += ms; return clock; }, pending: () => queue.size,
    // Run queued frames at timestamp ts; an exception escapes to the page as the real one would.
    frame(ts) { const cbs = [...queue.values()]; queue.clear(); for (const cb of cbs) try { cb(ts); } catch (e) { caught.push(e.message); setTimeout(() => { throw e; }); } return caught.length; },
    caught,
  };
});

const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const site = await serveWebkit(routes);
const browser = await engine.launch(engine === chromium ? { executablePath: process.env.CHROMIUM_EXECUTABLE, headless: true } : { headless: true });
const EARLY = 0.5;                          // ms: the first frame's timestamp precedes the event's start by this much
const landmarks = page => page.evaluate(() => Object.values(document.querySelector('cad-model').captureAssemblyLandmarks({ tetra: [0, 1, 2, 3], 'box.v2': [0, 1, 2, 3] }).components).flat(2));
const gap = (a, b) => Math.max(...a.map((n, i) => Math.abs(n - b[i])));
let passed = 0;

try {
  // Document.activeElement sees the outer host. The reader's real Tab must reach Explode inside the shadow tree.
  {
    const page = await browser.newPage();
    try {
      await page.goto(`${site.url}/shadow.html`);
      const model = page.locator('cad-model');
      await model.waitFor({state:'attached'});
      await page.waitForFunction(() => document.querySelector('#host').shadowRoot.querySelector('cad-model').dataset.state === 'poster');
      await page.locator('#before').focus();
      await page.keyboard.press('Tab');
      await page.waitForFunction(() => ['ready','error'].includes(document.querySelector('#host').shadowRoot.querySelector('cad-model').dataset.state));
      const focus = await model.evaluate(el => ({
        state: el.dataset.state, tabindex: el.getAttribute('tabindex'),
        control: el.getRootNode().activeElement?.textContent,
      }));
      assert.deepEqual(focus, {state:'ready', tabindex:null, control:'Explode'});
      console.log('ok Tab hands focus to Explode inside a shadow tree');
    } finally { await page.close(); }
  }
  for (const input of ['pointer', 'keyboard']) for (const motion of ['no-preference', 'reduce']) {
    const name = `${input}/${motion}`, errors = [];
    const context = await browser.newContext({ viewport: { width: 900, height: 700 }, reducedMotion: motion });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    try {
      await page.goto(`${site.url}/index.html`);
      await page.waitForFunction(() => document.querySelector('cad-model')?.dataset.state === 'ready', null, { timeout: 20000 });
      await page.waitForTimeout(300);       // let the loop's own start-up frames finish before freezing the clock
      await freeze(page);
      const model = page.locator('cad-model'), button = model.getByRole('button', { name: 'Explode', exact: true });
      const activate = async () => { if (input === 'pointer') await button.click(); else { await button.focus(); await page.keyboard.press('Enter'); } };
      // Run the first frame EARLY ms before the event's start, then frames until the tween stops asking for more.
      const settle = async start => {
        await page.evaluate(ts => window.__clock.frame(ts), start - EARLY);
        const first = await landmarks(page);
        for (let t = start + 150; await page.evaluate(() => window.__clock.pending()) && t <= start + 2000; t += 150)
          await page.evaluate(ts => { window.__clock.advance(150); window.__clock.frame(ts); }, t);
        return first;
      };
      const assembled = await landmarks(page);

      let start = await page.evaluate(() => window.__clock.now());
      await activate();
      assert.equal(await button.getAttribute('aria-pressed'), 'true', `${name}: Explode is pressed`);
      if (motion === 'no-preference') assert.equal(await page.evaluate(() => window.__clock.pending()), 1, `${name}: one frame queued`);
      let first = await settle(start);
      assert.deepEqual(await page.evaluate(() => window.__clock.caught), [], `${name}: early first frame throws nothing`);
      if (motion === 'no-preference') assert.ok(gap(first, assembled) < 1e-6, `${name}: first frame keeps the assembled pose`);
      const exploded = await landmarks(page);
      assert.ok(gap(exploded, assembled) > 0.5, `${name}: the parts came apart`);
      assert.equal(await page.evaluate(() => window.__clock.pending()), 0, `${name}: frames stop once the tween completes`);

      start = await page.evaluate(() => window.__clock.now());
      await activate();
      assert.equal(await button.getAttribute('aria-pressed'), 'false', `${name}: Explode released`);
      first = await settle(start);
      if (motion === 'no-preference') assert.ok(gap(first, exploded) < 1e-6, `${name}: reverse first frame keeps the exploded pose`);
      assert.ok(gap(await landmarks(page), assembled) < 1e-6, `${name}: reverse returns to the assembled pose`);

      if (motion === 'no-preference') {
        // Reverse mid-flight: the second tween starts from wherever the first had reached, also with an early frame.
        start = await page.evaluate(() => window.__clock.now());
        await activate();
        await page.evaluate(ts => window.__clock.frame(ts), start - EARLY);
        await page.evaluate(() => window.__clock.frame(window.__clock.advance(300)));
        const middle = await landmarks(page);
        assert.ok(gap(middle, assembled) > 1e-3 && gap(middle, exploded) > 1e-3, `${name}: tween part way`);
        // Off screen, the pending frame is cancelled and none is requested; back on screen, the tween resumes.
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForFunction(() => window.__clock.pending() === 0);
        await page.waitForTimeout(100);
        assert.equal(await page.evaluate(() => window.__clock.pending()), 0, `${name}: no frames off screen`);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForFunction(() => window.__clock.pending() === 1);
        start = await page.evaluate(() => window.__clock.now());
        await activate();
        assert.equal(await button.getAttribute('aria-pressed'), 'false', `${name}: mid-flight reversal`);
        first = await settle(start);
        assert.ok(gap(first, middle) < 1e-6, `${name}: reversal's early first frame holds the mid-flight pose`);
        assert.ok(gap(await landmarks(page), assembled) < 1e-6, `${name}: reversal completes assembled`);
      }
      assert.deepEqual(await page.evaluate(() => window.__clock.caught), [], `${name}: no frame threw`);
      await page.waitForTimeout(50);
      assert.deepEqual(errors, [], `${name}: no uncaught page error`);
      assert.equal(await model.getAttribute('data-state'), 'ready', `${name}: viewer still ready`);
      console.log(`ok ${name}`); passed++;
    } finally { await context.close(); }
  }
  // Skewed clock (#769): frame timestamps that jump backwards must not turn the view backwards or reverse the tween.
  {
    const name = 'skewed clock', errors = [];
    const context = await browser.newContext({ viewport: { width: 900, height: 700 } });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    try {
      await page.goto(`${site.url}/index.html?turn`);
      await page.waitForFunction(() => document.querySelector('cad-model')?.dataset.state === 'ready', null, { timeout: 20000 });
      await freeze(page);
      // The turntable keeps asking for frames, so a frame requested from the browser before the freeze is still pending
      // and will run at the browser's own (unfrozen, earlier) timestamp. Wait until it has run and queued its successor
      // here: from then on every frame is one this case stamps. (Driving frames before that hand-off let the browser's
      // late frame land after the 5 s early one and take one clamped step: the WebKit CI failure on #770.)
      await page.waitForFunction(() => window.__clock.pending() === 1, null, { timeout: 20000, polling: 50 });
      const shot = () => page.evaluate(() => document.querySelector('cad-model').snapshot(64, 64));
      const stamps = [];
      // Run the one queued frame at `ts` (relative to the clock, or advancing it); exactly one must have been queued.
      const run = async (ms, advance) => {
        const r = await page.evaluate(([ms, advance]) => {
          const c = window.__clock, queued = c.pending(), ts = advance ? c.advance(ms) : c.now() + ms;
          c.frame(ts);
          return { queued, ts };
        }, [ms, advance]);
        stamps.push(r.ts);
        assert.equal(r.queued, 1, `${name}: expected one frame queued before the frame at ${r.ts} (stamps ${stamps.join(', ')})`);
      };
      const frame = ms => run(ms, false), step = ms => run(ms, true);
      // Evidence for a failure: mean absolute difference (0-255) between two 64 x 64 snapshots.
      const diff = (a, b) => page.evaluate(async ([a, b]) => {
        const px = async url => { const i = new Image(); i.src = url; await i.decode(); const c = document.createElement('canvas'); c.width = c.height = 64;
          const g = c.getContext('2d'); g.drawImage(i, 0, 0); return g.getImageData(0, 0, 64, 64).data; };
        const [x, y] = await Promise.all([px(a), px(b)]);
        let sum = 0; for (let i = 0; i < x.length; i++) sum += Math.abs(x[i] - y[i]);
        return +(sum / x.length).toFixed(2);
      }, [a, b]);
      const same = async (a, b, what) => {
        if (a !== b) assert.fail(`${name}: ${what} (mean pixel difference ${await diff(a, b)}, want 0; frame stamps ${stamps.join(', ')}; ${engine.name()})`);
      };
      await step(16); await step(16);
      let held = await shot();
      await frame(-5000);                   // stamped 5 s before the last frame
      await same(held, await shot(), 'a frame stamped 5 s early turned the view');
      await step(16);
      const moved = await shot();
      assert.ok(moved !== held, `${name}: the turntable resumes after the early frame (frame stamps ${stamps.join(', ')}; ${engine.name()})`);
      await step(60000);                    // a 60 s jump forward (clamped to one short step) ...
      held = await shot();
      await step(-60000);                   // ... and back again
      await same(held, await shot(), 'a frame stamped 60 s back turned the view');

      // Explode with its first frame 3 s behind the click: closed pose, then exactly the open pose.
      const model = page.locator('cad-model'), button = model.getByRole('button', { name: 'Pause' });
      await button.click();                 // stop the turntable so only the tween asks for frames
      const assembled = await landmarks(page), start = await page.evaluate(() => window.__clock.now());
      await model.getByRole('button', { name: 'Explode', exact: true }).click();
      await page.evaluate(ts => window.__clock.frame(ts), start - 3000);
      assert.ok(gap(await landmarks(page), assembled) < 1e-6, `${name}: a first frame 3 s early keeps the closed pose`);
      for (let t = start + 150; await page.evaluate(() => window.__clock.pending()) && t <= start + 2000; t += 150)
        await page.evaluate(ts => { window.__clock.advance(150); window.__clock.frame(ts); }, t);
      const open = await landmarks(page);
      await page.evaluate(() => document.querySelector('cad-model').setExplode(1));
      assert.ok(gap(open, await landmarks(page)) < 1e-9, `${name}: the tween finishes exactly at the open pose`);
      assert.deepEqual(await page.evaluate(() => window.__clock.caught), [], `${name}: no frame threw`);
      assert.deepEqual(errors, [], `${name}: no uncaught page error`);
      console.log(`ok ${name}`); passed++;
    } finally { await context.close(); }
  }
} finally { await browser.close(); await site.close(); }
console.log(`model explode first frame: ${passed}/5 cases passed in ${engine.name()}`);
