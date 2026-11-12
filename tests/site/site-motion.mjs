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
async function readmePictureProblems(browser, base, basename, options = {}) {
  const problems = [];
  // The existing CI artifact upload keeps these real painted controls, including failures.
  const evidence = await mkdtemp(path.join(tmpdir(), 'cad-agent-readme-motion-'));
  const animatedPath = options.animatedPath || `/docs/img/hero/${basename}.svg`;
  const stillPath = options.stillPath || `/docs/img/hero/${basename}-still.svg`;
  const selector = options.selector || `img[src="${animatedPath}"]`;
  const open = async reducedMotion => {
    const page = await browser.newPage({ viewport: { width: 390, height: 800 }, reducedMotion });
    try {
      const response = await page.goto(base + (options.route || '/README'), { waitUntil: 'networkidle' });
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
    if (await image.evaluate(img => new URL(img.currentSrc).pathname) !== animatedPath)
      problems.push('README did not select the animated image with motion enabled');
    if (!(await changes(image, 'normal'))) problems.push('README image does not animate with motion enabled');
  } finally { await normal.close(); }
  const page = await open('reduce');
  try {
    const image = page.locator(selector);
    if (await image.evaluate(img => new URL(img.currentSrc).pathname) !== stillPath)
      problems.push('README did not select the explicit reduced-motion still');
    if (await changes(image, 'reduced')) problems.push('README image still animates with reduced motion');
    // A cached screenshot or an animation-disabled screenshot API must not pass this check.
    const source = base + stillPath + '?broken-motion-control';
    await page.route(source, async route => {
      const response = await route.fetch();
      const body = (await response.text()).replace('</svg>',
        '<style>:root{animation:broken-motion 8s linear infinite!important}' +
        '@keyframes broken-motion{from{opacity:.1}to{opacity:1}}</style></svg>');
      await route.fulfill({ response, body });
    });
    await image.evaluate((img, source) => { img.closest('picture').querySelector('source').srcset = source; }, source);
    await page.waitForFunction(({ selector, source }) => document.querySelector(selector)?.currentSrc === source,
      { selector, source });
    await image.evaluate(img => img.decode());
    if (!(await changes(image, 'broken-still'))) problems.push('broken reduced-motion image control was accepted as a still');
  } finally { await page.close(); }
  return problems.map(problem => `${basename}: ${problem}`);
}

export async function repositoryHeroProblems(browser, base) {
  const problems = [];
  for (const name of ['repository-map', 'made-with-cad-agent'])
    problems.push(...await readmePictureProblems(browser, base, name));
  return problems;
}

/** Real homepage consumers: independent lazy views, truthful pending stages and retry readiness. */
export async function homepageModelProblems(browser, base) {
  const out = [];
  const context = await browser.newContext({viewport:{width:1100,height:800},reducedMotion:'reduce'});
  const page = await context.newPage();
  let failFirst, allowRetry;
  const firstGate = new Promise(resolve => { failFirst = resolve; });
  const retryGate = new Promise(resolve => { allowRetry = resolve; });
  let attempts = 0;
  try {
    await page.route('**/web/models/j501.bin', async route => {
      attempts++;
      if (attempts === 1) { await firstGate; return route.fulfill({status:503,body:'deliberate loader failure'}); }
      await retryGate; return route.continue();
    });
    await page.goto(base+'/',{waitUntil:'networkidle'});
    const early = await page.evaluate(() => performance.getEntriesByType('resource').filter(r => /three\.module|\/web\/models\/.*\.(json|bin)/.test(r.name)).length);
    if (early) out.push('project data was fetched while still at the learning hero');
    await page.locator('#built-with').evaluate(el => { document.documentElement.style.scrollBehavior='auto'; el.scrollIntoView({block:'start'}); });
    const j501 = page.locator('cad-model[src$="j501.json"]');
    const gyro = page.locator('cad-model[src$="gyropup.json"]');
    await page.waitForFunction(() => document.querySelector('cad-model[src$="j501.json"]')?.dataset.state === 'loading');
    if (!(await j501.locator('.cad-model-status progress').isVisible())) out.push('pending model has no visible progress');
    if (await j501.getAttribute('aria-busy') !== 'true') out.push('pending model is not announced busy');
    failFirst();
    await page.waitForFunction(() => document.querySelector('cad-model[src$="j501.json"]')?.dataset.state === 'error');
    await page.waitForFunction(() => document.querySelector('cad-model[src$="gyropup.json"]')?.dataset.state === 'ready',null,{timeout:20000});
    await page.evaluate(() => { const el=document.querySelector('cad-model[src$="j501.json"]'); window.__failedReady=el.ready; const other=document.querySelector('cad-model[src$="gyropup.json"]'); window.__otherReady=other.ready; window.__otherCanvas=other.querySelector('canvas'); });
    await j501.getByRole('button',{name:'Retry 3D view'}).click();
    const retry = await j501.evaluate(async el => { let settled=false; el.ready.then(()=>settled=true); await Promise.resolve(); return {fresh:el.ready!==window.__failedReady,settled,state:el.dataset.state,error:el.dataset.error,busy:el.getAttribute('aria-busy')}; });
    if (!retry.fresh || retry.settled || retry.state!=='loading' || retry.error || retry.busy!=='true') out.push('retry reused a settled readiness promise or stale error: '+JSON.stringify(retry));
    allowRetry();
    await page.waitForFunction(() => document.querySelector('cad-model[src$="j501.json"]')?.dataset.state === 'ready',null,{timeout:20000});
    const independent = await gyro.evaluate(el => el.ready===window.__otherReady && el.querySelector('canvas')===window.__otherCanvas && el.dataset.state==='ready');
    if (!independent) out.push('retry replaced or disturbed the other project viewer');
    if (await j501.locator('canvas').count() !== 1) out.push('retry duplicated the project canvas');
    if (attempts !== 2) out.push(`retry made ${attempts} binary requests, expected exactly two attempts`);
  } catch (error) { out.push('homepage loading/retry: '+error.message); }
  finally { failFirst(); allowRetry(); await context.close(); }
  for (const mode of ['no-script','no-webgl']) {
    const ctx = await browser.newContext({viewport:{width:390,height:844},javaScriptEnabled:mode!=='no-script',reducedMotion:'reduce'});
    const p = await ctx.newPage();
    try {
      if (mode==='no-webgl') await p.addInitScript(() => { const original=HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext=function(kind,...args){return /webgl/i.test(kind)?null:original.call(this,kind,...args);}; });
      await p.goto(base+'/',{waitUntil:'networkidle'});
      if (mode==='no-webgl') {
        for (const model of await p.locator('cad-model').all()) {
          await model.evaluate(el=>{document.documentElement.style.scrollBehavior='auto';el.scrollIntoView({block:'center'});});
          await p.waitForFunction(src=>document.querySelector(`cad-model[src="${src}"]`)?.dataset.state==='error',await model.getAttribute('src'),{timeout:20000});
          if (!(await model.getByRole('button',{name:'Retry 3D view'}).isVisible())) out.push('WebGL failure has no per-viewer recovery');
        }
      }
      const posters=await p.locator('cad-model img.cad-model-poster').evaluateAll(es=>es.map(e=>({loaded:e.complete&&e.naturalWidth>0,visible:e.checkVisibility()})));
      if (posters.length!==2||posters.some(p=>!p.loaded||!p.visible)) out.push(mode+': real project posters lost: '+JSON.stringify(posters));
      if (await p.locator('cad-model canvas').count()) out.push(mode+': a failed/disabled viewer left a live canvas');
    } catch(error) { out.push(mode+': '+error.message); }
    finally { await ctx.close(); }
  }
  return out;
}

/** Probe the actual responsive image, including a planted animated still as a rejection control. */
export async function learningPictureProblems(browser, base) {
  return readmePictureProblems(browser, base, 'learning-loop', {
    route:'/', selector:'img[src="/docs/img/hero/learning-loop.svg"]',
    animatedPath:'/docs/img/hero/learning-loop-mobile.svg',
    stillPath:'/docs/img/hero/learning-loop-mobile-still.svg',
  });
}
