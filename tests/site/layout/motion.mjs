/** Rendered SVG still checks. Page media emulation covers an SVG document, but can miss an external <img>'s SVG. */
import { mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fetchThrough, navigate, partHandler } from '../navigation.mjs';

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
    const response = await navigate(page, url);
    if (response?.status() !== 200) throw new Error(`SVG still source returned ${response?.status()}`);
    // Match the README's responsive image sizing; retain the SVG's real viewBox, CSS and geometry.
    await page.locator('svg').evaluate(svg => { svg.style.width = '100%'; svg.style.height = 'auto'; });
    await page.evaluate(() => new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok))));
    return page.evaluate(heroStillState);
  };
  try {
    problems.push(...heroStillProblems(await read(source)).map(p => `reduced-motion hero: ${p}`));
    await page.route(source + '?hidden-control', partHandler(async route => {
      const response = await fetchThrough(route);
      const body = (await response.text()).replace('</svg>',
        '<style>@media(prefers-reduced-motion:reduce){.draw{opacity:0!important}}</style></svg>');
      await route.fulfill({ response, body });
    }));
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
      const response = await navigate(page, base + (options.route || '/README'), { waitUntil: 'networkidle' });
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
    await page.route(source, partHandler(async route => {
      const response = await fetchThrough(route);
      const body = (await response.text()).replace('</svg>',
        '<style>:root{animation:broken-motion 8s linear infinite!important}' +
        '@keyframes broken-motion{from{opacity:.1}to{opacity:1}}</style></svg>');
      await route.fulfill({ response, body });
    }));
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
    await navigate(page, base+'/',{waitUntil:'networkidle'});
    const early = await page.evaluate(() => performance.getEntriesByType('resource').filter(r => /three\.module|\/web\/models\/.*\.(json|bin)/.test(r.name)).length);
    if (early) out.push('project data was fetched while still at the learning hero');
    await page.locator('#built-with .project-viewers').evaluate(el => { document.documentElement.style.scrollBehavior='auto'; el.scrollIntoView({block:'start'}); });
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
      await navigate(p, base+'/',{waitUntil:'networkidle'});
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

const MODEL_DATA = /three\.module|\/web\/models\/.*\.(json|bin)/;
const HERO_SIZES = [{width:390,height:844},{width:1280,height:720},{width:1440,height:900}];

/** The home viewers (loading="scroll", #748): no three.js and no model data until the reader scrolls or reaches a
 * viewer, at every size, though on a desktop screen they sit inside the viewer's 300px look-ahead. Then a little scroll
 * starts them, and so does keyboard focus alone (no scroll). A planted control serves the page with the viewers made
 * eager, and the same check must catch it at each size. */
export async function homepageViewerGateProblems(browser, base, receipt = {}) {
  const out = [];
  receipt.sizes = [];
  const fetched = page => page.evaluate(re => performance.getEntriesByType('resource').filter(r => new RegExp(re).test(r.name)).map(r => new URL(r.name).pathname), MODEL_DATA.source);
  for (const viewport of HERO_SIZES) for (const planted of [false, true]) {
    const label = `${viewport.width}x${viewport.height}${planted ? ' planted eager control' : ''}`;
    const ctx = await browser.newContext({viewport, reducedMotion:'reduce'});
    const page = await ctx.newPage();
    try {
      if (planted) await page.route(base + '/', partHandler(async route => {
        const response = await fetchThrough(route);
        await route.fulfill({ response, body: (await response.text()).replaceAll('loading="scroll"', 'loading="eager"') });
      }));
      await navigate(page, base + '/', {waitUntil:'networkidle'});
      const before = await fetched(page);
      receipt.sizes.push({ label, beforeScroll: before.length });
      if (planted) { if (!before.length) out.push(label + ': the eager control fetched nothing, so the check cannot tell'); continue; }
      if (before.length) out.push(`${label}: fetched before any scroll: ${before.join(', ')}`);
      if (await page.evaluate(() => scrollY) !== 0) out.push(label + ': the page opened scrolled');
      if (viewport.width >= 1000) {
        // A small scroll, the viewers still below the fold but inside the look-ahead: they start.
        await page.mouse.wheel(0, 120);
        await page.waitForFunction(() => [...document.querySelectorAll('cad-model')].every(el => el.dataset.state !== 'poster'), null, {timeout:20000})
          .catch(() => out.push(label + ': a small scroll did not start the viewers inside the look-ahead'));
      }
    } catch (error) { out.push(label + ': ' + error.message); }
    finally { await ctx.close(); }
  }
  // Keyboard: focus alone (no scroll) starts a viewer.
  const ctx = await browser.newContext({viewport:{width:1440,height:900}, reducedMotion:'reduce'});
  const page = await ctx.newPage();
  try {
    await navigate(page, base + '/', {waitUntil:'networkidle'});
    const viewer = page.locator('cad-model[src$="gyropup.json"]');
    if (await viewer.getAttribute('tabindex') !== '0') out.push('a waiting home viewer is not in the tab order');
    await viewer.evaluate(el => el.focus({ preventScroll: true }));
    await page.waitForFunction(() => document.querySelector('cad-model[src$="gyropup.json"]').dataset.state !== 'poster', null, {timeout:20000})
      .catch(() => out.push('focus did not start the home viewer'));
    if (await page.evaluate(() => scrollY) !== 0) out.push('the focus check scrolled the page, so it did not test focus alone');
  } catch (error) { out.push('viewer focus: ' + error.message); }
  finally { await ctx.close(); }
  return out;
}

/** The hero recording (#748): with motion, the still is shown first and the animation replaces it after load, in one
 * request; under reduced motion, and with Save-Data, the animation is never requested. A planted site.js without the
 * reduced-motion guard must be caught. */
export async function heroRecordingProblems(browser, base, receipt = {}) {
  const out = [];
  const ANIMATION = '/docs/img/gyropup/turret-playground.webp', STILL = '/docs/img/gyropup/turret-playground-still.webp';
  const open = async ({ reducedMotion, saveData = false, planted = false }) => {
    const ctx = await browser.newContext({viewport:{width:390,height:844}, reducedMotion});
    const page = await ctx.newPage();
    const requests = [];
    page.on('request', r => { if (new URL(r.url()).pathname === ANIMATION) requests.push(r.url()); });
    if (saveData) await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true } }));
    if (planted) await page.route(base + '/web/site.js', partHandler(async route => {
      const response = await fetchThrough(route);
      await route.fulfill({ response, body: (await response.text()).replace("matchMedia('(prefers-reduced-motion: reduce)').matches || ", '') });
    }));
    await navigate(page, base + '/', {waitUntil:'networkidle'});
    return { ctx, page, requests };
  };
  const current = page => page.locator('.hero-run img').evaluate(img => new URL(img.currentSrc).pathname);
  try {
    const { ctx, page, requests } = await open({ reducedMotion:'no-preference' });
    try {
      await page.waitForFunction(src => new URL(document.querySelector('.hero-run img').currentSrc).pathname === src, ANIMATION, {timeout:20000})
        .catch(() => out.push('with motion, the animation never replaced the still'));
      const state = await page.locator('.hero-run img').evaluate(img => ({ complete: img.complete, width: img.naturalWidth, height: img.naturalHeight }));
      if (!state.complete || state.width !== 720 || state.height !== 336) out.push('the animation is not the recorded 720x336 picture: ' + JSON.stringify(state));
      if (requests.length !== 1) out.push(`with motion, ${requests.length} requests for the animation, expected one`);
      receipt.motion = { requests: requests.length, current: await current(page) };
    } finally { await ctx.close(); }
    for (const [label, options] of [['reduced motion', { reducedMotion:'reduce' }], ['Save-Data', { reducedMotion:'no-preference', saveData:true }]]) {
      const { ctx, page, requests } = await open(options);
      try {
        if (requests.length) out.push(`${label}: the animation was requested`);
        if (await current(page) !== STILL) out.push(`${label}: the still is not shown`);
        receipt[label] = { requests: requests.length };
      } finally { await ctx.close(); }
    }
    const control = await open({ reducedMotion:'reduce', planted:true });
    try {
      receipt.plantedRequests = control.requests.length;
      if (!control.requests.length) out.push('planted control: a site.js without the reduced-motion guard requested nothing, so the check cannot tell');
    } finally { await control.ctx.close(); }
  } catch (error) { out.push('hero recording: ' + error.message); }
  return out;
}

/** The home page's robot-replay card (#798): neither its still nor its animation loads before the reader scrolls
 * near it on a phone; once near, the animation replaces the still exactly once; never under reduced motion or Save-Data.
 * Planted controls: a site.js without the nearness gate requests the animation before any scroll, and one without the
 * reduced-motion guard requests it under reduced motion, so each check can fail. */
export async function replayCardProblems(browser, base, receipt = {}) {
  const out = [];
  const ANIMATION = '/kit/simulation/examples/gyropup-v2/card.webp', STILL = '/kit/simulation/examples/gyropup-v2/card-still.webp';
  const CARD = '.run-mini-media[href="/toolkit#robot-replay"] img';
  const open = async ({ reducedMotion, saveData = false, plant = null }) => {
    const ctx = await browser.newContext({viewport:{width:390,height:844}, reducedMotion});
    const page = await ctx.newPage();
    const requests = { [ANIMATION]: 0, [STILL]: 0 };
    page.on('request', r => { const p = new URL(r.url()).pathname; if (p in requests) requests[p]++; });
    if (saveData) await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true } }));
    if (plant) await page.route(base + '/web/site.js', partHandler(async route => {
      const response = await fetchThrough(route), text = await response.text();
      if (!text.includes(plant[0])) throw new Error(`planted control: ${plant[0]} is not in site.js`);
      await route.fulfill({ response, body: text.replace(plant[0], plant[1]) });
    }));
    await navigate(page, base + '/', {waitUntil:'networkidle'});
    const before = { ...requests };
    return { ctx, page, requests, before };
  };
  const near = async page => {
    await page.locator(CARD).scrollIntoViewIfNeeded();
    await page.waitForFunction(sel => { const img = document.querySelector(sel); return img.complete && img.naturalWidth > 0; }, CARD, {timeout:20000});
  };
  const current = page => page.locator(CARD).evaluate(img => new URL(img.currentSrc).pathname);
  try {
    {
      const { ctx, page, requests, before } = await open({ reducedMotion:'no-preference' });
      try {
        if (before[ANIMATION] || before[STILL]) out.push(`before any scroll the card loaded ${JSON.stringify(before)}`);
        await near(page);
        await page.waitForFunction(([sel, src]) => new URL(document.querySelector(sel).currentSrc).pathname === src, [CARD, ANIMATION], {timeout:20000})
          .catch(() => out.push('near the card, the animation never replaced the still'));
        if (requests[ANIMATION] !== 1) out.push(`near the card, ${requests[ANIMATION]} requests for the animation, expected one`);
        receipt.motion = { before, after: { ...requests } };
      } finally { await ctx.close(); }
    }
    for (const [label, options] of [['reduced motion', { reducedMotion:'reduce' }], ['Save-Data', { reducedMotion:'no-preference', saveData:true }]]) {
      const { ctx, page, requests } = await open(options);
      try {
        await near(page);
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        if (requests[ANIMATION]) out.push(`${label}: the card's animation was requested`);
        if (await current(page) !== STILL) out.push(`${label}: the card's still is not shown`);
        receipt[label] = { ...requests };
      } finally { await ctx.close(); }
    }
    const gate = await open({ reducedMotion:'no-preference', plant:["img.loading !== 'lazy'", 'true'] });
    try {
      await gate.page.waitForFunction(() => performance.getEntriesByType('resource').some(e => e.name.endsWith('/gyropup-v2/card.webp')), null, {timeout:20000}).catch(() => {});
      receipt.plantedGate = gate.requests[ANIMATION];
      if (!gate.requests[ANIMATION]) out.push('planted control: a site.js without the nearness gate loaded nothing before scroll, so the check cannot tell');
    } finally { await gate.ctx.close(); }
    const guard = await open({ reducedMotion:'reduce', plant:["matchMedia('(prefers-reduced-motion: reduce)').matches || ", ''] });
    try {
      await near(guard.page);
      await guard.page.waitForFunction(() => performance.getEntriesByType('resource').some(e => e.name.endsWith('/gyropup-v2/card.webp')), null, {timeout:20000}).catch(() => {});
      receipt.plantedGuard = guard.requests[ANIMATION];
      if (!guard.requests[ANIMATION]) out.push('planted control: a site.js without the reduced-motion guard requested nothing, so the check cannot tell');
    } finally { await guard.ctx.close(); }
  } catch (error) { out.push('replay card: ' + error.message); }
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


/** A tiny real packed fixture isolates post-allocation GPU rollback from model size. */
export async function homepageLateDrawProblems(browser, base, receipt = {}) {
  const out=[], errors=[];
  const fixture=JSON.parse(await readFile(new URL('../../fixtures/model/two-parts.json',import.meta.url),'utf8'));
  const binary=await readFile(new URL('../../fixtures/model/two-parts.bin',import.meta.url));
  const ctx=await browser.newContext({viewport:{width:1100,height:800},reducedMotion:'reduce'});
  const page=await ctx.newPage(); page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.route('**/web/models/*.json',route=>{const name=new URL(route.request().url()).pathname.includes('j501')?'j501':'other';return route.fulfill({contentType:'application/json',body:JSON.stringify({...fixture,bin:`/__late-${name}.bin`})});});
    await page.route('**/__late-*.bin',route=>route.fulfill({contentType:'application/octet-stream',body:binary}));
    await page.addInitScript(()=>{
      window.__lateDrawFaults=0;
      for(const Klass of [window.WebGLRenderingContext,window.WebGL2RenderingContext]) if(Klass)
        for(const method of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced']) {
          const original=Klass.prototype[method];if(!original)continue;
          Klass.prototype[method]=function(...args){
            if(!window.__lateDrawFaults&&this.canvas?.closest('cad-model')?.getAttribute('src')?.endsWith('j501.json')) {
              window.__lateDrawFaults++;throw Error('planted first GPU draw failure after allocation');
            }
            return original.apply(this,args);
          };
        }
    });
    await navigate(page, base+'/',{waitUntil:'networkidle'});
    await page.locator('#built-with .project-viewers').evaluate(el=>{document.documentElement.style.scrollBehavior='auto';el.scrollIntoView({block:'start'});});
    await page.waitForFunction(()=>document.querySelector('cad-model[src$="j501.json"]')?.dataset.state==='error',null,{timeout:20000});
    await page.waitForFunction(()=>document.querySelector('cad-model[src$="gyropup.json"]')?.dataset.state==='ready',null,{timeout:20000});
    const target=page.locator('cad-model[src$="j501.json"]');
    const failed=await target.evaluate(el=>{window.__lateFailedReady=el.ready;const other=document.querySelector('cad-model[src$="gyropup.json"]');window.__lateOtherCanvas=other.querySelector('canvas');return {canvases:el.querySelectorAll('canvas').length,controls:el.querySelectorAll('.cad-model-ui').length,poster:el.querySelector('img').checkVisibility(),faults:window.__lateDrawFaults};});
    receipt.failed=failed;
    if(failed.canvases||failed.controls||!failed.poster||failed.faults!==1)out.push('late GPU failure did not roll back to the real poster: '+JSON.stringify(failed));
    await target.getByRole('button',{name:'Retry 3D view'}).click();
    await page.waitForFunction(()=>document.querySelector('cad-model[src$="j501.json"]')?.dataset.state==='ready',null,{timeout:20000});
    const ready=await target.evaluate(el=>({canvases:el.querySelectorAll('canvas').length,controls:el.querySelectorAll('.cad-model-ui').length,freshReady:el.ready!==window.__lateFailedReady,error:el.dataset.error,otherUnchanged:document.querySelector('cad-model[src$="gyropup.json"]').querySelector('canvas')===window.__lateOtherCanvas,otherReady:document.querySelector('cad-model[src$="gyropup.json"]').dataset.state==='ready',otherControls:document.querySelector('cad-model[src$="gyropup.json"]').querySelectorAll('.cad-model-ui').length}));
    receipt.recovered=ready;
    if(ready.canvases!==1||ready.controls!==1||!ready.freshReady||ready.error||!ready.otherUnchanged||!ready.otherReady||ready.otherControls!==1)out.push('late failure retry did not create exactly one independent live view: '+JSON.stringify(ready));
    await page.setViewportSize({width:1000,height:800});
    await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(100);
    if(errors.length)out.push('late retry left a failing observer or renderer: '+errors.join('; '));
  } catch(error){out.push('late draw rollback: '+error.message);}
  finally{await ctx.close();}
  return out;
}

/** Wait for a lazy image's own load before decode(). Scrolling only starts the request; Chromium r1194 (Playwright 1.56)
 * rejects decode() on a lazy image whose load has not started with EncodingError, which newer Chrome waits out. Since #748
 * moved the reel below the viewers, its images are no longer inside the lazy-load distance at first paint. */
const loadedThenDecoded = el => (el.complete ? Promise.resolve()
  : new Promise((ok, no) => { el.addEventListener('load', ok, { once: true }); el.addEventListener('error', () => no(new Error('image failed to load: ' + el.currentSrc)), { once: true }); }))
  .then(() => el.decode());

/** Every displayed computed SVG is tested through its real picture consumer. */
export async function resultImageMotionProblems(browser, base, receipt = {}) {
  receipt.images=[];
  const out=[];
  const ctx=await browser.newContext({viewport:{width:1366,height:900},reducedMotion:'reduce'});
  const page=await ctx.newPage();
  try {
    await navigate(page, base+'/',{waitUntil:'networkidle'});
    // Five animated reel results (the snap fit is inline SVG) and the turret playground recording (#748).
    const images=page.locator('.reel-tile picture img, .run-media picture img');
    if(await images.count()!==6)out.push('expected five animated reel images and the turret recording');
    for(const image of await images.all()) {
      await image.scrollIntoViewIfNeeded();await image.evaluate(loadedThenDecoded);
      const state=await image.evaluate(el=>({src:el.getAttribute('src'),current:new URL(el.currentSrc).pathname,loaded:el.complete&&el.naturalWidth>0}));
      if(!state.loaded||!(state.current.includes('/result-stills/')||state.current.endsWith('-still.webp')))out.push('result did not select its finished image: '+JSON.stringify(state));
      const first=await image.screenshot();await page.waitForTimeout(300);const second=await image.screenshot();
      const stable=first.equals(second);receipt.images.push({...state,stable});
      if(!stable)out.push('computed image still moves under reduced motion: '+state.src);
    }
  }catch(error){out.push('result image consumer: '+error.message);}
  finally{await ctx.close();}
  // A deliberately moving image at the exact selected still URL must be rejected too.
  const control=await browser.newContext({viewport:{width:1366,height:900},reducedMotion:'reduce'});
  const cp=await control.newPage();
  try {
    await cp.route('**/result-stills/thermal-history-still.svg',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="390"><rect width="760" height="390" fill="black"/><rect width="180" height="390" fill="cyan"><animate attributeName="x" values="0;580;0" dur="2s" repeatCount="indefinite"/></rect></svg>'}));
    await navigate(cp, base+'/',{waitUntil:'networkidle'});
    const image=cp.locator('.reel-tile img[src$="thermal-history.svg"]');
    await image.scrollIntoViewIfNeeded();await image.evaluate(loadedThenDecoded);
    const first=await image.screenshot();await cp.waitForTimeout(300);const second=await image.screenshot();
    receipt.movingControlObserved=!first.equals(second);
    if(!receipt.movingControlObserved)out.push('moving reduced-image control was not observable; stillness probe is inconclusive');
  } catch(error){out.push('moving result-image rejection control: '+error.message);}
  finally{await control.close();}
  return out;
}
