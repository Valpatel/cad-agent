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
