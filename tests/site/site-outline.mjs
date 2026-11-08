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
