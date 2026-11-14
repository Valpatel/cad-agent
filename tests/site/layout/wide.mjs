/** Representative widescreen acceptance (#703), using the same built pages and browser as the main suite. */
export const WIDE_VIEWPORTS = [
  { width: 1920, height: 1080 }, { width: 2560, height: 1440 },
  { width: 3440, height: 1440 }, { width: 3840, height: 2160 },
];
const ROUTES = ['/', '/toolkit', '/toolkit/scada/elements', '/explore', '/docs/toolkit'];

/** Broad presentation budgets, not an exact copy of the CSS's breakpoints or column formula. */
export function wideGeometryProblems(m) {
  const problems = [];
  const finite = n => Number.isFinite(n) && n > 0;
  if (!finite(m.viewport?.width) || !finite(m.viewport?.height)) return ['missing viewport geometry'];
  const { width, height } = m.viewport;
  for (const name of ['header', 'main']) {
    const box = m.shells?.[name];
    if (!finite(box?.width)) problems.push(`missing ${name} shell`);
    else if (box.width < width * .85) problems.push(`${name} shell uses ${(box.width / width * 100).toFixed(1)}% of viewport; needs at least 85%`);
  }
  if (!Number.isFinite(m.overflow) || m.overflow > 1) problems.push(`horizontal overflow: ${m.overflow}px`);
  if (m.route === '/toolkit/scada/elements') {
    const cards = m.cards || [];
    const firstRow = cards.filter(card => Math.abs(card.y - cards[0]?.y) <= 1);
    const minimumColumns = width >= 3440 ? 6 : width >= 2560 ? 5 : 4;
    if (firstRow.length < minimumColumns) problems.push(`gallery has ${firstRow.length} columns; needs at least ${minimumColumns}`);
    if (!firstRow.length || firstRow.some(card => !finite(card.width) || card.width < 260 || card.width > 520))
      problems.push(`gallery card widths must stay within 260–520px: ${firstRow.map(card => card.width.toFixed(1)).join(', ') || 'none'}`);
  }
  if (m.route === '/docs/toolkit') {
    if (!finite(m.document?.width) || m.document.width < width * .5) problems.push('document visual column uses less than 50% of viewport');
    if (!m.paragraphs?.length) problems.push('missing substantial narrative paragraphs');
    else if (m.paragraphs.some(p => !finite(p.width) || p.width > 960)) problems.push('narrative paragraphs exceed the 960px readability budget');
    if (!finite(m.table?.width) || m.table.width < m.document?.width * .9) problems.push('document table frame does not use the flexible visual column');
  }
  if (m.route === '/explore') {
    const firstRow = (m.groups || []).filter(group => Math.abs(group.y - m.groups[0]?.y) <= 1);
    const used = firstRow.length ? Math.max(...firstRow.map(group => group.x + group.width)) - Math.min(...firstRow.map(group => group.x)) : 0;
    if (!finite(m.groupArea?.width) || used < m.groupArea.width * .85) problems.push('Explore group row leaves more than 15% of its results area unused');
  }
  if (m.route === '/') {
    const limit = Math.min(900, height * .85);
    if (!m.hero?.loaded || !finite(m.hero.width) || !finite(m.hero.height)) problems.push('missing or unloaded homepage artwork');
    else if (m.hero.height > limit) problems.push(`homepage artwork is ${m.hero.height.toFixed(1)}px tall; budget ${limit}px`);
  }
  return problems;
}

/** Runs in the browser; keep independent of the predicate so DOM defects exercise the real measurements. */
export function wideGeometrySnapshot(route) {
  const box = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  };
  const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  const image = document.querySelector('.learning-art img');
  return {
    route, viewport: { width: innerWidth, height: innerHeight },
    theme: document.documentElement.dataset.theme || getComputedStyle(document.documentElement).colorScheme,
    overflow: document.documentElement.scrollWidth - innerWidth,
    shells: { header: box(document.querySelector('.site-header .wrap')), main: box(document.querySelector('main.wrap, main > .wrap')) },
    cards: route === '/toolkit/scada/elements' ? [...document.querySelectorAll('.toolkit-grid .toolkit-card')].filter(visible).map(box) : [],
    groups: route === '/explore' ? [...document.querySelectorAll('.discover-group')].filter(visible).map(box) : [],
    groupArea: box(document.querySelector('.discover-groups') || document.querySelector('#discover-results')),
    document: box(document.querySelector('.doc-main')),
    paragraphs: [...document.querySelectorAll('.prose > p')].filter(el => visible(el) && el.textContent.trim().length >= 100 && !el.querySelector('img,picture,svg,canvas,video,table')).slice(0, 5).map(box),
    table: box([...document.querySelectorAll('.prose .table-scroll')].find(visible)),
    hero: image ? { ...box(image), loaded: image.complete && image.naturalWidth > 0 } : null,
  };
}

async function settled(page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
  });
}

// Isolated page per route: controls cannot leak styles or scroll position into a later measurement.
// Each mutation is restored before the page closes, even if measuring it fails.
async function defectControl(page, route, kind, expected) {
  await page.evaluate(kind => {
    const selector = kind === 'shell' ? '.site-header .wrap, main.wrap, main > .wrap' : kind === 'gallery' ? '.toolkit-grid' : kind === 'groups' ? '.discover-groups' : '.learning-art img';
    window.__wideControl = [...document.querySelectorAll(selector)].map(el => [el, el.getAttribute('style')]);
    for (const [el] of window.__wideControl) {
      if (kind === 'shell') { el.style.setProperty('width', '1240px', 'important'); el.style.setProperty('max-width', '1240px', 'important'); }
      else if (kind === 'gallery') el.style.setProperty('grid-template-columns', 'repeat(3,minmax(0,1fr))', 'important');
      else if (kind === 'groups') el.style.setProperty('grid-template-columns', 'repeat(8,minmax(0,1fr))', 'important');
      else { el.style.setProperty('height', '1672px', 'important'); el.style.setProperty('max-height', 'none', 'important'); }
    }
  }, kind);
  try {
    await settled(page);
    const problems = wideGeometryProblems(await page.evaluate(wideGeometrySnapshot, route));
    return problems.some(p => expected.test(p)) ? [] : [`${kind} defect control escaped detection`];
  } finally {
    await page.evaluate(() => {
      for (const [el, style] of window.__wideControl) style === null ? el.removeAttribute('style') : el.setAttribute('style', style);
      delete window.__wideControl;
    });
  }
}

export async function wideLayoutProblems(browser, base, { onMeasurement = () => {} } = {}) {
  const problems = [];
  for (const viewport of WIDE_VIEWPORTS) for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport, colorScheme: theme });
    await context.addInitScript(theme => localStorage.setItem('cad-theme', theme), theme);
    try {
      for (const route of ROUTES) {
        const page = await context.newPage();
        const label = `${viewport.width}×${viewport.height} ${theme} ${route}`;
        const seen = [];
        page.on('pageerror', error => seen.push(`page error: ${error.message}`));
        try {
          const response = await page.goto(base + route, { waitUntil: 'networkidle' });
          if (response?.status() !== 200) seen.push(`HTTP ${response?.status()}`);
          await settled(page);
          const measurement = await page.evaluate(wideGeometrySnapshot, route);
          onMeasurement(measurement);
          if (measurement.theme !== theme) seen.push(`theme did not apply: ${measurement.theme}`);
          seen.push(...wideGeometryProblems(measurement));
          if (viewport.width === 3440 && theme === 'light') {
            if (route === '/') {
              seen.push(...await defectControl(page, route, 'shell', /shell uses/));
              seen.push(...await defectControl(page, route, 'hero', /artwork is/));
            }
            if (route === '/toolkit/scada/elements') seen.push(...await defectControl(page, route, 'gallery', /gallery has 3 columns/));
            if (route === '/explore') seen.push(...await defectControl(page, route, 'groups', /Explore group row leaves/));
          }
        } catch (error) { seen.push(error.message); }
        finally { await page.close(); }
        problems.push(...seen.map(p => `${label}: ${p}`));
      }
    } finally { await context.close(); }
  }
  return problems;
}
