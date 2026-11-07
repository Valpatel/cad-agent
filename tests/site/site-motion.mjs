/** Rendered SVG still checks. Page media emulation covers an SVG document, but can miss an external <img>'s SVG. */
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

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

/** Compare the compiled README's actual picture selection and painted image over time.
 * Page emulation need not propagate inside SVG images: the parent selects a generated still explicitly. */
export async function repositoryHeroProblems(browser, base) {
  const problems = [];
  // The existing CI artifact upload keeps these real painted controls, including failures.
  const evidence = await mkdtemp(path.join(tmpdir(), 'cad-agent-readme-motion-'));
  const selector = 'img[src="/docs/img/hero/repository-map.svg"]';
  const open = async reducedMotion => {
    const page = await browser.newPage({ viewport: { width: 390, height: 800 }, reducedMotion });
    try {
      const response = await page.goto(base + '/README', { waitUntil: 'networkidle' });
      if (response?.status() !== 200) throw new Error(`README returned ${response?.status()}`);
      await page.locator(selector).evaluate(img => img.decode());
      return page;
    } catch (error) { await page.close(); throw error; }
  };
  const changes = async (image, label) => {
    const before = await image.screenshot({ path: path.join(evidence, label + '-before.png') });
    await new Promise(resolve => setTimeout(resolve, 1250));
    const after = await image.screenshot({ path: path.join(evidence, label + '-after.png') });
    const changed = !before.equals(after);
    const state = await image.evaluate(img => ({ source: img.currentSrc, width: img.naturalWidth, height: img.naturalHeight,
      pageReducedMotion: matchMedia('(prefers-reduced-motion:reduce)').matches }));
    await writeFile(path.join(evidence, label + '.json'), JSON.stringify({ browser: browser.version(), changed, ...state }, null, 2));
    return changed;
  };
  const normal = await open('no-preference');
  try {
    const image = normal.locator(selector);
    if (await image.evaluate(img => new URL(img.currentSrc).pathname) !== '/docs/img/hero/repository-map.svg')
      problems.push('README did not select the animated image with motion enabled');
    if (!(await changes(image, 'normal'))) problems.push('README image does not animate with motion enabled');
  } finally { await normal.close(); }
  const page = await open('reduce');
  try {
    const image = page.locator(selector);
    if (await image.evaluate(img => new URL(img.currentSrc).pathname) !== '/docs/img/hero/repository-map-still.svg')
      problems.push('README did not select the explicit reduced-motion still');
    if (await changes(image, 'reduced')) problems.push('README image still animates with reduced motion');
    // A cached screenshot or an animation-disabled screenshot API must not pass this check.
    const source = base + '/docs/img/hero/repository-map-still.svg?broken-motion-control';
    await page.route(source, async route => {
      const response = await route.fetch();
      const body = (await response.text()).replace('</svg>',
        '<style>:root{animation:broken-motion 8s linear infinite!important}' +
        '@keyframes broken-motion{from{opacity:.1}to{opacity:1}}</style></svg>');
      await route.fulfill({ response, body });
    });
    await image.evaluate((img, source) => { img.closest('picture').querySelector('source').srcset = source; }, source);
    await page.waitForFunction(source => document.querySelector('picture img')?.currentSrc === source, source);
    await image.evaluate(img => img.decode());
    if (!(await changes(image, 'broken-still'))) problems.push('broken reduced-motion image control was accepted as a still');
  } finally { await page.close(); }
  return problems;
}
