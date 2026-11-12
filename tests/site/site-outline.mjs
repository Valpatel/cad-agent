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

/** Actual wheel input at the reader tree's upper boundary must not chain into an article scroll,
 * whose correctly preserved section tracker would otherwise pull the tree away from its search fields. */
export async function readerBoundaryProblems(browser, base) {
  const problems=[],states=[],evidence=await mkdtemp(path.join(tmpdir(),'cad-agent-reader-boundary-'));
  const snapshot=page=>page.evaluate(()=>{
    const p=document.querySelector('.cad-nav-panel'),s=document.querySelector('.explore-nav-search'),r=s.getBoundingClientRect();
    return {article:scrollY,panel:p.scrollTop,searchTop:r.top,searchBottom:r.bottom,contain:getComputedStyle(p).overscrollBehaviorY,current:[...document.querySelectorAll('.cad-nav-outline a[aria-current=location]')].map(a=>a.hash)};
  });
  const quiet=page=>page.evaluate(()=>new Promise(resolve=>{
    let prior='',same=0;const until=setTimeout(()=>resolve(false),2000);
    const tick=()=>{const p=document.querySelector('.cad-nav-panel'),now=scrollY+':'+p.scrollTop;if(now===prior)same++;else same=0;prior=now;if(same>=12){clearTimeout(until);resolve(true);}else requestAnimationFrame(tick);};requestAnimationFrame(tick);
  }));
  for(const viewport of [{width:1440,height:900},{width:1440,height:600},{width:1600,height:900}]){
    const page=await browser.newPage({viewport});
    try{
      await page.goto(base+'/docs/toolkit',{waitUntil:'networkidle'});await page.waitForSelector('cad-nav[data-ready]');
      await scrollOutline(page,6000);await quiet(page);
      const initial=await snapshot(page);if(!initial.current.length)problems.push('reader boundary: no active article heading at '+JSON.stringify(viewport));
      const panel=page.locator('.cad-nav-panel');const box=await panel.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+Math.min(150,box.height/2));
      await page.mouse.wheel(0,-10000);await page.waitForFunction(()=>document.querySelector('.cad-nav-panel').scrollTop===0);await quiet(page);
      const before=await snapshot(page);await page.mouse.wheel(0,-300);if(!await quiet(page))problems.push('reader boundary: input never settled');const after=await snapshot(page);
      states.push({viewport,initial,before,after});
      if(after.article!==before.article||after.panel!==0||after.searchTop<0||after.searchBottom>viewport.height)problems.push('reader boundary: lost search '+JSON.stringify({viewport,before,after}));
      // A keyboard user can still reach and type in the global search field at the top.
      const search=page.getByRole('searchbox',{name:'Search all knowledge'});
      const exposed=await search.evaluate(el=>{const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===el;});
      const labelExposed=await page.locator('label[for=explore-reader-search]').evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));});
      if(!exposed||!labelExposed)problems.push('reader boundary: global search is covered');
      await search.click();await search.fill('counterbores');if(await search.inputValue()!=='counterbores')problems.push('reader boundary: search input inaccessible');
      if(viewport.width===1440&&viewport.height===900){
        const cover=await page.addStyleTag({content:'cad-nav [data-nav-controls]{position:static!important}cad-nav .cad-nav-panel::before{display:block!important}'});
        const covered=await page.locator('label[for=explore-reader-search]').evaluate(el=>{const r=el.getBoundingClientRect();return !el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));});
        states.push({legacyCoverRejected:covered});if(!covered)problems.push('reader boundary: old opaque cover control was not rejected');await cover.evaluate(el=>el.remove());
        await page.addStyleTag({content:'cad-nav .cad-nav-panel{overscroll-behavior-y:auto!important}'});
        await page.mouse.move(box.x+box.width/2,box.y+150);await page.mouse.wheel(0,-300);await page.waitForFunction(y=>scrollY<y,before.article);await quiet(page);
        const negative=await snapshot(page);states.push({negative});
        if(!(negative.article<before.article&&negative.panel>0))problems.push('reader boundary: old scroll-chain control did not reproduce the trap');
      }
      await scrollOutline(page,await page.evaluate(()=>document.documentElement.scrollHeight));await quiet(page);
      const bottom=await page.evaluate(()=>{const rect=e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height};};return {host:rect(document.querySelector('cad-nav')),panel:rect(document.querySelector('.cad-nav-panel')),controls:rect(document.querySelector('[data-nav-controls]')),header:rect(document.querySelector('.site-header'))};});states.push({viewport,bottom});
      if(bottom.controls.top<bottom.header.bottom||bottom.controls.bottom>viewport.height||bottom.panel.height<bottom.controls.height+44)problems.push('reader boundary: footer leaves controls or links without room '+JSON.stringify(bottom));
    }finally{await page.close();}
  }
  for(const javaScriptEnabled of [true,false]){
    const page=await browser.newPage({viewport:{width:390,height:844},javaScriptEnabled});
    try{
      await page.goto(base+'/docs/toolkit',{waitUntil:'networkidle'});await page.locator('.cad-nav-toggle').click();
      const mode=await page.locator('.cad-nav-panel').evaluate(p=>({position:getComputedStyle(p).position,overflow:getComputedStyle(p).overflowY,contain:getComputedStyle(p).overscrollBehaviorY}));states.push({mobile:javaScriptEnabled,mode});
      if(mode.position!=='static'||mode.overflow!=='visible'||mode.contain!=='auto')problems.push('reader boundary: mobile native page scrolling changed');
    }finally{await page.close();}
  }
  await writeFile(path.join(evidence,'receipt.json'),JSON.stringify({states,problems},null,2));
  console.log('Reader boundary evidence: '+evidence);return problems;
}

/** Keep the actual last/last/middle outline-click journey, including the engine's own click autoscroll.
 * Also align a link natively at the panel's start: its center must clear the real sticky header. */
export async function readerOutlineClickProblems(browser, base) {
  const problems=[],states=[],evidence=await mkdtemp(path.join(tmpdir(),'cad-agent-reader-click-'));
  const page=await browser.newPage({viewport:{width:1366,height:800}});
  const settle=()=>page.evaluate(()=>new Promise(done=>{
    let last=-1,still=0;const tick=()=>{if(scrollY===last){if(++still>15)return done();}else{still=0;last=scrollY;}requestAnimationFrame(tick);};tick();setTimeout(done,10000);
  }));
  const state=(link,alignment=null)=>link.evaluate((a,mode)=>{
    // Capture the native alignment in the same task: queued tracking must not undo the planted CSS first.
    if(mode==='zero'){const style=document.createElement('style');style.id='reader-zero-inset-control';style.textContent='cad-nav .cad-nav-panel{scroll-padding-top:0!important}';document.head.append(style);}
    if(mode==='restored')document.getElementById('reader-zero-inset-control')?.remove();
    if(mode)a.scrollIntoView({block:'start',behavior:'instant'});
    const p=a.closest('.cad-nav-panel'),r=a.getBoundingClientRect(),c=p.querySelector('[data-nav-controls]').getBoundingClientRect();
    return {target:a.hash,article:scrollY,panel:p.scrollTop,padding:getComputedStyle(p).scrollPaddingTop,controlsHeight:c.height,top:r.top,bottom:r.bottom,controlsBottom:c.bottom,hit:a.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};
  },alignment);
  try{
    await page.goto(base+'/docs/toolkit',{waitUntil:'networkidle'});await page.waitForSelector('cad-nav[data-ready]');
    await scrollOutline(page,await page.evaluate(()=>document.body.scrollHeight/2));await page.locator('.cad-nav-panel').evaluate(p=>p.scrollTop=0);
    await scrollOutline(page,await page.evaluate(()=>document.body.scrollHeight*.85));
    await page.evaluate(()=>{document.documentElement.style.scrollBehavior='';scrollTo({top:0,behavior:'instant'});});
    const links=page.locator('cad-nav .cad-nav-outline a');
    for(const link of [links.nth((await links.count())-2),links.last()]){
      await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await link.click();await settle();
      if(await link.getAttribute('aria-current')!=='location')problems.push('reader click: smooth jump not marked');
    }
    await page.evaluate(()=>document.documentElement.style.scrollBehavior='auto');
    const middle=links.nth(Math.floor((await links.count())/2));await middle.click();await settle();states.push({realMiddleClick:await state(middle)});
    // Remove only the new inset: native start alignment must reproduce a link underneath the sticky controls.
    const negative=await state(middle,'zero');states.push({negative});if(negative.hit)problems.push('reader click: zero-inset header coverage control was not rejected');
    const corrected=await state(middle,'restored');states.push({corrected});if(!corrected.hit||parseFloat(corrected.padding)<corrected.controlsHeight)problems.push('reader click: link remains beneath sticky controls');
    await middle.click();await settle();
  }finally{
    await page.screenshot({path:path.join(evidence,'final.png')});await page.close();
    await writeFile(path.join(evidence,'receipt.json'),JSON.stringify({states,problems},null,2));console.log('Reader click evidence: '+evidence);
  }
  return problems;
}
