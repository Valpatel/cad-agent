/** A panel's actual marked entry, and scroll-event/frame readiness before strict geometry checks. */
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

export function outlineEntryState(panel) {
  const a = panel.querySelector('.cad-nav-outline a[aria-current=location]');
  const b = panel.getBoundingClientRect(), r = a?.getBoundingClientRect();
  return { scrollY, panelTop: panel.scrollTop, active: a?.getAttribute('href') || null,
    panel: { top: b.top, bottom: b.bottom }, entry: r ? { top: r.top, bottom: r.bottom } : null,
    inView: !!r && r.top >= b.top && r.bottom <= b.bottom };
}

/** No geometry convergence: wait for the commanded page scroll and one frame, with a hard two-second bound.
 * The component's existing scroll listener queues its mark before this listener queues the observation frame.
 * A page already at the target needs only that frame; scrolling the panel alone never calls this helper. */
export function scrollOutline(page, target) {
  return page.evaluate(target => new Promise(resolve => {
    let frame, expected, eventSeen = false, stage = 'scroll';
    const finish = ready => {
      clearTimeout(timer); cancelAnimationFrame(frame); removeEventListener('scroll', onScroll);
      resolve({ ready, stage, eventSeen, target: expected, scrollY });
    };
    const afterScroll = () => { stage = 'frame'; frame = requestAnimationFrame(() => finish(true)); };
    const onScroll = () => { if (scrollY === expected) { eventSeen = true; removeEventListener('scroll', onScroll); afterScroll(); } };
    const timer = setTimeout(() => finish(false), 2000);
    addEventListener('scroll', onScroll, { passive: true });
    const before = scrollY;
    scrollTo({ top: target, behavior: 'instant' }); expected = scrollY;
    if (expected === before) { removeEventListener('scroll', onScroll); afterScroll(); }
  }), target);
}

/** Real component regression: a reader moves the panel, then scrolls within the SAME article section. */
export async function sameSectionOutlineProblems(browser, base) {
  const problems = [], evidence = await mkdtemp(path.join(tmpdir(), 'cad-agent-outline-control-'));
  const page = await browser.newPage({ viewport: { width: 1366, height: 800 } });
  const errors = [], states = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  try {
    await page.goto(base + '/docs/toolkit', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => customElements.get('cad-nav'), null, { timeout: 2000 });
    // Assemble a detached fixture before connecting it, so the real component sees its complete article and children.
    await page.evaluate(() => {
      const style = document.createElement('style');
      style.textContent = 'body{margin:0}.outline-fixture{display:grid;grid-template-columns:280px 1fr;gap:24px}.outline-fixture cad-nav,.outline-fixture article{height:12000px}.outline-fixture h2{margin:0}';
      document.head.append(style);
      const fixture = document.createElement('div'); fixture.className = 'outline-fixture';
      const links = Array.from({ length: 40 }, (_, i) => `<li><a href="#">Other page ${i}</a></li>`).join('');
      fixture.innerHTML = `<cad-nav for="article"><details class="cad-nav-fold"><summary class="cad-nav-toggle">Pages and contents</summary><div class="cad-nav-panel"><input class="cad-nav-filter"><details class="cad-nav-group" open><summary>Docs</summary><ul>${links}<li><a href="/docs/toolkit" aria-current="page">Current page</a></li></ul></details></div></details></cad-nav><article><h2 id="same">Long section</h2><div style="height:9000px"></div><h2 id="second">Second section</h2><div style="height:2000px"></div><h2 id="third">Third section</h2></article>`;
      document.body.replaceChildren(fixture);
    });
    const panel = page.locator('.cad-nav-panel');
    const move = async target => {
      const ready = await scrollOutline(page, target); states.push({ ready });
      if (!ready.ready) problems.push(`outline control: ${ready.stage} was not delivered within 2000 ms`);
    };
    await move(3000);
    const before = await panel.evaluate(outlineEntryState); states.push({ before });
    if (before.active !== '#same' || !before.inView) problems.push('outline control: initial marked entry is missing or hidden');
    await panel.evaluate(p => { p.scrollTop = 0; });
    await page.waitForTimeout(300);                 // the reader owns the panel until the PAGE moves
    const reader = await panel.evaluate(outlineEntryState); states.push({ reader });
    if (reader.panelTop !== 0 || reader.scrollY !== 3000) problems.push('outline control: the reader cannot move the panel independently');
    await move(4000);
    const after = await panel.evaluate(outlineEntryState); states.push({ after });
    if (after.active !== '#same' || !after.inView) problems.push('outline control: the unchanged active section is outside the panel after page scrolling');
    await page.screenshot({ path: path.join(evidence, 'after-page-scroll.png') });
    // Same strict predicate: a planted hidden entry must still fail, after the identical readiness boundary.
    await panel.locator('a[aria-current=location]').evaluate(a => { a.style.display = 'none'; });
    await move(4100);
    const hidden = await panel.evaluate(outlineEntryState); states.push({ hidden });
    if (hidden.inView) problems.push('outline control accepted a hidden marked entry');
  } catch (e) { problems.push('outline control: ' + e.message); }
  finally {
    await writeFile(path.join(evidence, 'states.json'), JSON.stringify({ states, errors, problems }, null, 2) + '\n');
    await page.close();
  }
  return [...problems, ...errors.map(e => 'outline control runtime: ' + e)];
}

/** Existing whole-page WCAG predicate, shared by general themes and targeted outline states. */
export const lowContrast = (page, only = null) => page.evaluate(only => {
    const ctx = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d', { willReadFrequently: true });
    // Each colour is read back from the canvas once, and each element's backdrop worked out once: a page asks for the
    // same few colours thousands of times, and a canvas read is slow (in WebKit most of all).
    const seen = new Map(), backdrops = new Map();
    const rgba = c => { if (seen.has(c)) return seen.get(c); ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; seen.set(c, [d[0], d[1], d[2], d[3] / 255]); return seen.get(c); };
    const lum = ([r, g, b]) => [r, g, b].map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };
    // What can be behind: a colour, or each stop of a CSS gradient (text must read on all of them); null for a picture.
    const over = ([r, g, b, a], under) => [r, g, b].map((v, i) => v * a + under[i] * (1 - a));
    const behind = el => { if (!backdrops.has(el)) backdrops.set(el, backdrop(el)); return backdrops.get(el); };
    const backdrop = el => {
      const layers = [];
      for (let e = el; e; e = e.parentElement) {
        const cs = getComputedStyle(e), c = rgba(cs.backgroundColor);
        if (/url\(/.test(cs.backgroundImage)) return null;
        // a gradient sized to nothing (the catalogue rows' hover sweep, until hovered) is not behind anything yet
        const stops = cs.backgroundImage === 'none' || /^0(?:%|px)/.test(cs.backgroundSize) ? []
          : (cs.backgroundImage.match(/(?:rgba?|oklab|oklch|lab|lch|color)\((?:[^()]|\([^()]*\))*\)/g) || []).map(rgba);
        if (stops.length) layers.push(stops);
        if (c[3] > 0) layers.push([c]);
        if (c[3] >= 1 || (stops.length && stops.every(x => x[3] >= 1))) break;
      }
      let under = [[255, 255, 255]];
      for (const layer of layers.reverse()) under = layer.flatMap(c => under.map(u => over(c, u)));
      return under;
    };
    const SKIP = 'svg, img, video, canvas, cad-model, cad-cantilever, cad-fourbar, cad-fan-curve, cad-torsion-snap, cad-printed-boss, .cad-diagram-view, .visually-hidden, .sr, .glyph-sprite, [hidden]';
    const low = [], walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const name = el => `${el.localName}${el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''}`;
    for (const input of only ? [] : document.querySelectorAll('input[placeholder]')) {
      if (!input.getClientRects().length || input.closest(SKIP)) continue;
      const bgs = behind(input), fg = rgba(getComputedStyle(input, '::placeholder').color);
      const c = bgs && Math.min(...bgs.map(bg => ratio(over(fg, bg), bg)));
      if (c && c < 4.5) low.push(`${name(input)} placeholder "${input.placeholder.slice(0, 30)}" ${c.toFixed(2)}:1`);
    }
    for (let n; (n = walk.nextNode());) {
      const el = n.parentElement;
      if (!n.data.trim() || el.closest(SKIP) || (only && !el.closest(only))) continue;
      const cs = getComputedStyle(el), r = el.getBoundingClientRect();
      if (!r.width || !r.height || cs.visibility === 'hidden' || +cs.opacity === 0 || !el.checkVisibility?.({ opacityProperty: true, visibilityProperty: true })) continue;
      const bgs = behind(el);
      if (!bgs) continue;
      const fg = rgba(cs.color), c = Math.min(...bgs.map(bg => ratio(over(fg, bg), bg)));
      const size = parseFloat(cs.fontSize), large = size >= 24 || (size >= 18.66 && +cs.fontWeight >= 700), need = large ? 3 : 4.5;
      if (c < need) low.push(`${name(el)} "${n.data.trim().slice(0, 30)}" ${c.toFixed(2)}:1`);
    }
    return [...new Set(low)];
  }, only);
