/** Rendered SVG still checks. Page media emulation covers an SVG document, but can miss an external <img>'s SVG. */
export function heroStillState() {
  const alpha = el => {
    if (!el) return 0;
    let value = 1;
    for (let at = el; at; at = at.parentElement) {
      const style = getComputedStyle(at);
      if (style.display === 'none' || style.visibility === 'hidden') return 0;
      value *= Number(style.opacity);
    }
    return value;
  };
  const draw = document.querySelector('.draw');
  const box = draw?.getBoundingClientRect();
  const fills = [...document.querySelectorAll('.f')];
  const marks = [...document.querySelectorAll('.tick')];
  const exploded = [...document.querySelectorAll('[class]')].filter(el => [...el.classList].some(c => /^x\d+$/.test(c)))
    .filter(el => {
      const transform = getComputedStyle(el).transform;
      return transform !== 'none' && !new DOMMatrixReadOnly(transform).isIdentity;
    }).length;
  return { reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
    animations: document.getAnimations().length,
    drawing: alpha(draw) > .99 && box?.width > 0 && box?.height > 0,
    fills: fills.length, visibleFills: fills.filter(el => alpha(el) > .99).length,
    marks: marks.length, visibleMarks: marks.filter(el => alpha(el) > .99).length, exploded };
}

export function heroStillProblems(state) {
  const out = [];
  if (!state.reduced) out.push('SVG document did not receive reduced-motion preference');
  if (state.animations) out.push(`${state.animations} SVG animations still running`);
  if (!state.drawing) out.push('SVG drawing is hidden or empty');
  if (!state.fills || state.fills !== state.visibleFills) out.push('SVG solid fills are hidden or missing');
  if (!state.marks || state.marks !== state.visibleMarks) out.push('SVG check marks are hidden or missing');
  if (state.exploded) out.push('SVG parts remain exploded in the still');
  return out;
}

/** Validate the real document and reject a hidden drawing even when its media rule and zero-animation check pass. */
export async function reducedHeroProblems(browser, base) {
  const problems = [];
  const page = await browser.newPage({ viewport: { width: 360, height: 800 }, reducedMotion: 'reduce' });
  const source = `${base}/docs/img/hero/gyropup-leg.svg`;
  const read = async url => {
    const response = await page.goto(url);
    if (response?.status() !== 200) throw new Error(`SVG still source returned ${response?.status()}`);
    // Match the README's responsive image sizing; retain the SVG's real viewBox, CSS and geometry.
    await page.locator('svg').evaluate(svg => { svg.style.width = '100%'; svg.style.height = 'auto'; });
    await page.evaluate(() => new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok))));
    return page.evaluate(heroStillState);
  };
  try {
    problems.push(...heroStillProblems(await read(source)).map(p => `reduced-motion hero: ${p}`));
    await page.route(source + '?hidden-control', async route => {
      const response = await route.fetch();
      const body = (await response.text()).replace('</svg>',
        '<style>@media(prefers-reduced-motion:reduce){.draw{opacity:0!important}}</style></svg>');
      await route.fulfill({ response, body });
    });
    const bad = await read(source + '?hidden-control');
    if (!bad.reduced || bad.animations !== 0) problems.push('hidden-drawing control did not retain reduced motion and zero animations');
    if (!heroStillProblems(bad).includes('SVG drawing is hidden or empty'))
      problems.push('hidden-drawing control was accepted as a valid SVG still');
  } finally { await page.close(); }
  return problems;
}

/** Image mode is a different consumer: compare pixels of the actual compiled README's header over time.
 * Chromium's page media override does not reach SVG <img> documents (observed in Chrome 151); use its browser
 * preference flag for this isolated browser. Keep the normal-motion control and deliberately broken still. */
export async function repositoryHeroProblems(browser, engine, launchOptions, base) {
  const problems = [];
  const selector = 'img[src="/docs/img/hero/repository-map.svg"]';
  const open = async (host, reducedMotion) => {
    const page = await host.newPage({ viewport: { width: 390, height: 800 }, reducedMotion });
    try {
      const response = await page.goto(base + '/README', { waitUntil: 'networkidle' });
      if (response?.status() !== 200) throw new Error(`README returned ${response?.status()}`);
      await page.locator(selector).evaluate(img => img.decode());
      return page;
    } catch (error) { await page.close(); throw error; }
  };
  const changes = async image => {
    const before = await image.screenshot();
    await new Promise(resolve => setTimeout(resolve, 1250));
    return !before.equals(await image.screenshot());
  };
  const normal = await open(browser, 'no-preference');
  try {
    if (!(await changes(normal.locator(selector)))) problems.push('README image does not animate with motion enabled');
  } finally { await normal.close(); }
  const stillBrowser = await engine.launch({ ...launchOptions,
    ...(engine.name() === 'chromium' ? { args: [...(launchOptions.args || []), '--force-prefers-reduced-motion'] } : {}) });
  try {
    const page = await open(stillBrowser, 'reduce');
    try {
      if (!(await page.evaluate(() => matchMedia('(prefers-reduced-motion:reduce)').matches)))
        problems.push('README did not receive reduced-motion preference');
      if (await changes(page.locator(selector))) problems.push('README image still animates with reduced motion');
      // A static blank, a cached screenshot or an animation-disabled screenshot API must not pass this check.
      const source = base + '/docs/img/hero/repository-map.svg?broken-motion-control';
      await page.route(source, async route => {
        const response = await route.fetch();
        const body = (await response.text()).replace('</svg>',
          '<style>:root{animation:broken-motion 8s linear infinite!important}' +
          '@keyframes broken-motion{from{opacity:.1}to{opacity:1}}</style></svg>');
        await route.fulfill({ response, body });
      });
      const image = page.locator(selector);
      await image.evaluate((img, source) => { img.src = source; }, source);
      const control = page.locator('img[src$="?broken-motion-control"]');
      await control.evaluate(img => img.decode());
      if (!(await changes(control))) problems.push('broken reduced-motion image control was accepted as a still');
    } finally { await page.close(); }
  } finally { await stillBrowser.close(); }
  return problems;
}
