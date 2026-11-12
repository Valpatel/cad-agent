import {lowContrast} from './site-outline.mjs';
/** Explore browsing, legacy catalogue bookmarks and focused readers, in both hosted engines.
 * Existing gallery predicates/URL states remain tested; no old maturity bar or modal-sheet presentation is required.
 * Native fallback, hostile data, runtime/CSP, exact legacy filters/hash/history and current contrast remain hard gates.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, webkit } from './npm-context.mjs';
import { builtSite } from './built-site.mjs';
import { longestStretch, VISUAL, WALL_LIMIT } from './site-walls.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const site = await builtSite('cad-agent-catalog-browser-', { stdio: 'inherit' });   // CAD_AGENT_SITE, or a fresh build of HEAD
const dir = site.dir;
const server = spawn(process.execPath, ['tools/site/preview-site.mjs', '--dir', dir, '--port', '0'], { cwd: root });
const base = await new Promise((ok, fail) => {
  server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
  server.on('exit', c => fail(new Error(`preview server exited ${c}`)));
});
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
// Legacy filtering and reader behavior now share the compact Explore shell.
const problems = [];
const fail = (where, what) => problems.push(`${where}: ${what}`);

// `init`: a script to run before the page's own (to break something on purpose); `fails`: a page error it causes;
// `forced`: 'active' emulates forced colours (Windows High Contrast and the like).
async function open(route, { width = 1366, height = 900, js = true, motion = 'no-preference', block = null, init = null, fails = null, forced = 'none', color = 'light' } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, javaScriptEnabled: js, reducedMotion: motion, forcedColors: forced, colorScheme: color });
  const page = await context.newPage();
  const seen = [];
  if (block) await page.route(`**${block}`, r => r.abort());
  page.on('console', m => { if (m.type() === 'error' && !/status of 404/.test(m.text()) && !(block && /gallery\.js|Failed to load|load failed|importing a module/i.test(m.text()))) seen.push(`console: ${m.text()}`); });
  page.on('pageerror', e => { if (!(fails && fails.test(e.message))) seen.push(`page error: ${e.message}`); });
  page.on('requestfailed', r => { if (!/ERR_ABORTED|cancelled/i.test(r.failure()?.errorText || '') && !(block && r.url().endsWith(block))) seen.push(`failed: ${r.url()}`); });
  page.on('response', r => { if (r.status() >= 400) seen.push(`HTTP ${r.status()}: ${r.url()}`); });
  page.on('request', r => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) seen.push(`third party: ${r.url()}`); });
  if (js) await page.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`)));
  if (init) await page.addInitScript(init);
  await page.goto(base + route, { waitUntil: 'networkidle' });
  if (js && !block && !fails && /^\/(?:explore|catalog)(?:[?#]|$)/.test(route)) await page.waitForSelector('cad-gallery[data-ready]', { timeout: 10000 }).catch(() => seen.push('the gallery did not start'));
  const done = async () => { for (const s of seen) fail(`${route} @${width}${js ? '' : ' no-JS'}`, s); await context.close(); };
  return { page, done };
}
// Hidden from view but kept for screen readers (gallery.css: a 1 px clipped box), or not shown at all.
const offScreen = loc => loc.evaluate(el => { const r = el.getBoundingClientRect(); return !el.checkVisibility() || (r.width <= 1 && r.height <= 1); });
const visible = (page, sel = '[data-item]') => page.$$eval(sel, els => els.filter(e => e.checkVisibility()).map(e => e.id));
const query = page => new URL(page.url()).search;

async function sharedDiscoveryChecks() {
  const cases = [
    ['counterbores', '/docs/common-issues#issue-'],
    ['validate rendered', '/docs/rendered-motion'],
    ['download McMaster', '/skills/mcmaster-parts/SKILL'],
    ['twist printed', '/docs/compliant#try-it-the-torsion-snap-explorer'],
    ['disassembly', '/lessons/process/user-intent-and-requirements#treat-doesnt-block-disassembly-as-a-hard-requirement'],
    ['snap fits', '/docs/compliant'],
    ['pem-consumer-electronics-design-guide-2021', '/references/fasteners-and-hardware#pem-consumer-electronics-design-guide-2021'],
    ['pem-ce-guide-2021', '/references/fasteners-and-hardware#pem-consumer-electronics-design-guide-2021'],
    ['abbud-riveted-joints', '/references/unplaced#abbud-riveted-joints'],
  ];
  for (const width of [320, 1366]) for (const color of ['light', 'dark']) {
    const {page, done} = await open('/explore', {width, color});
    try {
      const box = page.getByRole('searchbox', {name: 'Search everything'});
      // Lazy images outside a phone's horizontal strip are checked after they are actually brought into view.
      const initialScroll = await page.evaluate(() => ({x:scrollX,y:scrollY,strip:document.querySelector('.discover-demos').scrollLeft}));
      const stripImages = page.locator('.discover-demos img');
      for (let i=0;i<await stripImages.count();i++) {
        const image = stripImages.nth(i);await image.scrollIntoViewIfNeeded();
        const handle = await image.elementHandle();
        try { await page.waitForFunction(img => img.complete && img.naturalWidth > 0, handle, {timeout:10000}); }
        catch { fail('Explore images', `${width}px ${color}: displayed image ${i} did not load`); }
        finally { await handle.dispose(); }
      }
      const images = await stripImages.evaluateAll(xs => xs.map(x => ({src:x.getAttribute('src'),loaded:x.complete && x.naturalWidth>0})));
      if (images.length !== 3 || images.some(x => !x.loaded || !x.src.startsWith('/'))) fail('Explore images', JSON.stringify(images));
      await page.evaluate(saved => {document.querySelector('.discover-demos').scrollLeft=saved.strip;scrollTo({left:saved.x,top:saved.y,behavior:'instant'});}, initialScroll);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const start = await box.boundingBox();
      if (!start || start.y > 400) fail('Explore', `${width}px ${color}: search starts below the first view`);
      const before = await page.evaluate(() => ({height: document.documentElement.scrollHeight, nodes: document.querySelectorAll('*').length,
        visible: [...document.querySelectorAll('[data-item]')].filter(x => x.checkVisibility()).length}));
      if (width >= 1100) { const wall = await page.evaluate(longestStretch, VISUAL); if (wall.worst > WALL_LIMIT) fail('Explore reading', JSON.stringify(wall)); }
      if (before.height > 7000 || before.nodes > 7300 || before.visible > 8) fail('Explore', `${width}px ${color}: unbounded default ${JSON.stringify(before)}`);
      for (const [q, href] of cases) {
        await box.fill(q);
        await page.waitForFunction(needle => [...document.querySelectorAll('[data-item] a')].some(a => a.closest('[data-item]').checkVisibility() && new URL(a.href).pathname.concat(new URL(a.href).hash).startsWith(needle)), href);
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) fail('Explore', `${width}px ${color}: ${q} overflows`);
      }
      await box.fill('counterbores');
      const pitfall=page.locator('.discover-results a[href^="/docs/common-issues#issue-"]').first();
      const target=await pitfall.getAttribute('href');await pitfall.click();
      if (new URL(page.url()).origin !== base || !await page.locator('[id="'+decodeURIComponent(new URL(page.url()).hash.slice(1))+'"]').isVisible()) fail('Explore local destination', 'pitfall leaves preview or its real anchor stays hidden: '+target);
      await page.goto(base+'/explore');await page.waitForSelector('cad-gallery[data-ready]');
      await box.fill('agentcad');
      const roles = await page.locator('[data-item]').evaluateAll(xs => xs.filter(x => x.checkVisibility()).map(x => x.textContent));
      if (!roles.some(x => x.includes('Adoption: candidate')) || !roles.some(x => x.includes('Source: Read'))) fail('Explore', 'shared-URL adoption and evidence roles disappeared');
      await box.fill('zz-no-such-fixture-599');
      if ((await visible(page)).length || !await page.getByText('No matches. Try fewer words or clear the filters.', {exact:true}).isVisible()) fail('Explore', 'empty query retains stale matches or hides recovery');
      await page.getByRole('button', {name:'Clear search and filters'}).click();
      if (await box.inputValue() || !(await visible(page)).length) fail('Explore', 'clear does not recover');
      for (const q of ['counterbores','disassembly']) { await page.getByRole('link', {name:q,exact:true}).click(); await page.waitForURL(u => u.searchParams.get('q') === q); }
      await page.goBack(); if (await box.inputValue() !== 'counterbores') fail('Explore', 'Back lost the deliberate query');
      await page.goForward(); if (await box.inputValue() !== 'disassembly') fail('Explore', 'Forward lost the deliberate query');
    } finally { await done(); }
  }
  for (const options of [{js:false}, {block:'/kit/gallery.js'}, {block:'/web/site.js'}]) {
    const {page, done} = await open('/explore', {width:320, ...options});
    try {
      if (await page.getByRole('link',{name:'Full catalogue',exact:true}).count()) fail('Explore fallback','competing catalogue entrance remains');
      if (await page.getByRole('searchbox').isVisible()) fail('Explore fallback', 'non-working search remains visible');
      if (await page.locator('[data-gallery-tabs]').isVisible() || await page.getByRole('checkbox').first().isVisible()) fail('Explore fallback', 'non-working type/topic filters remain visible');
      await page.locator('details[data-group=references] > summary').click();
      if (!await page.locator('a[href$="/references/unplaced#abbud-riveted-joints"]').isVisible()) fail('Explore fallback', 'unplaced source link is not browsable through its native group');
    } finally { await done(); }
  }
}
const firstResultTop=page=>page.evaluate(()=>{const el=[...document.querySelectorAll('[data-item]')].find(e=>e.checkVisibility());return el?el.getBoundingClientRect().top:null;});
const catalog=JSON.parse(await readFile(path.join(dir,'catalog.json'),'utf8'));
const tabOf=kind=>({demo:'demos',tool:'tools',project:'projects',library:'libraries',benchmark:'benchmarks',guide:'guides',lesson:'lessons',research:'research',skill:'skills',agent:'skills'})[kind];
const areaIndex=JSON.parse(await readFile(path.join(dir,'catalog/index.json'),'utf8'));
const domainFor=new Map(areaIndex.domains.flatMap(d=>(d.areas||[]).map(a=>[a.slug,d.slug])));
async function nativeGroups(page){for(const d of await page.locator('details[data-group]').all())await d.evaluate(el=>{el.open=true;});}
async function legacyChecks(){
 for(const color of ['light','dark']){
  const {page,done}=await open('/catalog',{width:1100,height:800,color});try{
   await page.evaluate(()=>document.fonts.ready);
   const initial=await page.evaluate(()=>({x:scrollX,y:scrollY}));
   for(const img of await page.locator('[data-item] .result-preview').all())if(await img.isVisible()){
    await img.scrollIntoViewIfNeeded();await img.evaluate(el=>el.complete&&el.naturalWidth>0?Promise.resolve():el.decode());
   }
   await page.evaluate(p=>scrollTo({left:p.x,top:p.y,behavior:'instant'}),initial);
   const wall=await page.evaluate(longestStretch,VISUAL);if(wall.worst>WALL_LIMIT)fail('legacy reading '+color,JSON.stringify(wall));
   if((await visible(page)).length!==8)fail('legacy default','expected eight preview rows without hiding full catalogue entries');
  }finally{await done();}
 }

 // Actual saved filter combinations, derived independently from the immutable public catalogue model.
 const matrix=catalog.items.filter(c=>['tool','project','library','guide','skill','demo'].includes(c.kind)).filter((c,i,a)=>a.findIndex(x=>x.kind===c.kind)===i);
 for(const seed of matrix){
  const q=new URLSearchParams({kind:tabOf(seed.kind),area:seed.areas[0],type:seed.type,status:seed.status,licence:seed.licence_family});
  if(seed.maturity)q.set('maturity',seed.maturity);if(seed.demo)q.set('demo','1');q.set('sort','maturity');
  const expected=catalog.items.filter(c=>tabOf(c.kind)===tabOf(seed.kind)&&c.type===seed.type&&c.status===seed.status&&c.licence_family===seed.licence_family&&(!seed.maturity||c.maturity===seed.maturity)&&(!seed.demo||c.demo)&&(c.areas.includes(seed.areas[0])||c.areas.some(a=>domainFor.get(a)===seed.areas[0]))).map(c=>c.id).sort();
  const {page,done}=await open('/catalog?'+q);try{
   const got=(await visible(page)).sort();if(JSON.stringify(got)!==JSON.stringify(expected))fail('legacy filter matrix',JSON.stringify({q:String(q),got,expected}));
   if(await page.locator('.mat-dots,.area-maturity,.key-scale').count())fail('legacy','maturity presentation remains');
   const controls=await page.locator('input[name=maturity]').evaluateAll(xs=>xs.filter(x=>x.checkVisibility()).length);if(controls)fail('legacy','maturity controls are visible');
   if(await firstResultTop(page)>400)fail('legacy','saved view does not open on its results');
  }finally{await done();}
 }
 for(const anchor of ['tool','upstream','library','benchmark','docs','skills','agents','lessons','research',catalog.items.at(-1).id]){
  const {page,done}=await open('/catalog#'+anchor);try{
   const target=page.locator('[id="'+anchor+'"]');if(!await target.count()||!await target.evaluate(el=>el.closest('[data-item],[data-group]')?.checkVisibility()))fail('legacy hash','invisible '+anchor);
   const selected=await page.locator('[data-gallery-tabs] [aria-selected=true]').getAttribute('data-tab');
   await page.locator('[data-gallery-tabs] [data-tab="tools"]').click();await page.waitForURL(u=>u.searchParams.get('kind')==='tools');
   if(selected!=='tools'){await page.goBack();if(new URL(page.url()).hash!=='#'+anchor)fail('legacy hash history','Back lost '+anchor);}
  }finally{await done();}
 }
 for(const config of [{js:false},{block:'/kit/gallery.js'},{block:'/web/site.js'}]){
  const {page,done}=await open('/catalog?kind=tools&area=gears',config);try{
   await nativeGroups(page);const ids=(await visible(page)).sort(),expected=catalog.items.map(x=>x.id).sort();
   if(JSON.stringify(ids)!==JSON.stringify(expected))fail('legacy fallback '+JSON.stringify(config),JSON.stringify({missing:expected.filter(id=>!ids.includes(id)),unexpected:ids.filter(id=>!expected.includes(id)),groups:await page.locator('details[data-group]').evaluateAll(xs=>xs.map(e=>({group:e.dataset.group,open:e.open,visible:e.checkVisibility(),display:getComputedStyle(e).display}))),ready:await page.locator('cad-gallery').getAttribute('data-ready')}));
   if(await page.locator('[data-gallery-js]').evaluateAll(xs=>xs.some(x=>x.checkVisibility())))fail('legacy fallback','dead enhancement controls');
  }finally{await done();}
 }
 const {page,done}=await open('/catalog');try{
  await page.getByRole('searchbox',{name:'Search everything'}).fill('<b>x</b><img src=x>');
  if(await page.locator('img[src=x],cad-gallery b:text-is("x")').count())fail('URL injection','active search markup');
  await page.waitForURL(u=>u.searchParams.get('q')==='<b>x</b><img src=x>');
  if(!await page.locator('[data-gallery-chips]').textContent().then(x=>x.includes('<b>x</b><img src=x>')))fail('URL injection','query not plain text');
 }finally{await done();}
}
async function lifecycleChecks(){
 for(const late of [false,true]){
  const init=late?()=>{const media=window.matchMedia.bind(window);let thrown=false;window.matchMedia=q=>{if(!thrown&&/reduced-motion/.test(q)&&document.querySelector('cad-gallery')?.hasAttribute('data-ready')){thrown=true;throw Error('test: late gallery failure');}return media(q);};}:()=>{const toggle=Element.prototype.toggleAttribute;let thrown=false;Element.prototype.toggleAttribute=function(name,force){if(!thrown&&this.localName==='cad-gallery'&&name==='data-overview'){thrown=true;throw Error('test: early gallery failure');}return toggle.call(this,name,force);};};
  const {page,done}=await open('/catalog?kind=tools&area=gears',{init,fails:/test: (early|late) gallery failure/});try{
   await page.waitForSelector('cad-gallery[data-failed]');await nativeGroups(page);
   if((await visible(page)).length!==catalog.items.length)fail('gallery lifecycle','failure keeps a filtered view');
   if(await page.locator('[data-gallery-js]').evaluateAll(xs=>xs.some(x=>x.checkVisibility())))fail('gallery lifecycle','failure leaves enhancement controls active');
  }finally{await done();}
 }
}
async function interactionChecks(){
 const {page,done}=await open('/explore');try{
  const tabs=page.locator('[data-gallery-tabs] [data-tab]');await tabs.first().focus();await page.keyboard.press('ArrowRight');await page.waitForURL(u=>u.searchParams.get('kind')==='guides');
  if(await page.locator('[data-gallery-tabs] [aria-selected=true]').getAttribute('data-tab')!=='guides')fail('keyboard tabs','ArrowRight does not select guides');
  await page.keyboard.press('End');await page.waitForURL(u=>u.searchParams.get('kind')==='demos');await page.keyboard.press('Home');await page.waitForURL(u=>!u.searchParams.has('kind'));
  await page.locator('.discover-filter-options > summary').click();
  const box=page.locator('input[name=format][value=tool]');await box.check();await page.waitForURL(u=>u.searchParams.get('format')==='tool');
  const chip=page.getByRole('button',{name:'Remove filter: tool',exact:true});if(!await chip.isVisible())fail('filter chip','label includes a count or is not removable');
  await page.locator('[data-gallery-sort]').selectOption('az');await page.waitForURL(u=>u.searchParams.get('sort')==='az');
  await page.getByRole('button',{name:'Remove filter: tool',exact:true}).click();await page.waitForURL(u=>!u.searchParams.has('format'));
  await page.goBack();await box.waitFor();if(!await box.isChecked()||await page.locator('[data-gallery-sort]').inputValue()!=='az')fail('filter history','Back lost checkbox or sort');
  await page.locator('[data-group=guides] [data-gallery-more]').click();await page.waitForURL(u=>u.searchParams.get('kind')==='guides');
  const titles=await page.locator('[data-item]').evaluateAll(xs=>xs.filter(x=>x.checkVisibility()).map(x=>x.querySelector('.result-title').textContent.toLowerCase()));
  const expected=catalog.items.filter(x=>x.kind==='tool').map(x=>x.name.toLowerCase()).sort((a,b)=>a.localeCompare(b));
  if(JSON.stringify(titles)!==JSON.stringify(expected))fail('sort/filter','A–Z tool results disagree with catalogue');
  const projection=JSON.parse(await readFile(path.join(dir,'discovery.json'),'utf8')),total=projection.items.filter(x=>x.group==='guides').length;
  const line=await page.locator('[data-gallery-status]').textContent();if(line!==`${expected.length} of ${total} tools & guides`)fail('filtered count',line);
 }finally{await done();}
}
async function detailsChecks(){
 for(const badRevision of [false,true]){
  const {page,done}=await open('/explore?q=holes');try{
   let fetched=0;await page.route('**/catalog.json',route=>{fetched++;const fixture=structuredClone(catalog);if(badRevision)fixture.revision='0'.repeat(40);else{const c=fixture.items.find(x=>x.id==='tool-holes');c.notes='<img src=x onerror=alert(1)> is inert source text';c.how='echo <script>alert(1)</script>';}
    return route.fulfill({contentType:'application/json',body:JSON.stringify(fixture)});});
   if(fetched)fail('details','eager catalogue request');
   const host=page.locator('details[data-catalogue-id="tool-holes"]');
   const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/catalog.json');await host.locator('summary').click();await response;
   if(badRevision){await page.waitForFunction(()=>{const el=document.querySelector('details[data-catalogue-id="tool-holes"]');return !!el.querySelector('[data-detail-fallback]')&&!el.hasAttribute('data-detail-loading');});if(await host.getAttribute('data-detail-ready')!==null||!await host.locator('[data-detail-fallback]').isVisible())fail('details','stale feed hides fallback or becomes ready');}
   else{await page.waitForSelector('details[data-catalogue-id="tool-holes"][data-detail-ready]');if(!await host.textContent().then(t=>t.includes('<img src=x onerror=alert(1)>')))fail('details','notes text lost');if(await host.locator('img[src=x],script').count())fail('details','source metadata became executable');}
   if(fetched!==1)fail('details','expected one bounded existing-feed fetch, got '+fetched);
  }finally{await done();}
 }
}
async function readerChecks(){
 for(const width of [390,1366])for(const color of ['light','dark']){
  const {page,done}=await open('/docs/toolkit',{width,color});try{
   const nav=page.locator('cad-nav');if(width<1100)await nav.locator('.cad-nav-toggle').click();
   if(!await nav.locator('a[aria-current=page]').isVisible())fail('reader','current article missing from topic tree');
   const input=nav.getByRole('searchbox',{name:'Filter topic pages'}),prior=await nav.locator('details[open]').count();
   await input.fill('fasteners');if(!await nav.locator('details[data-topic="fasteners-and-hardware"]').isVisible())fail('topic filter','topic name does not match');
   await input.fill('zz-no-topic-603');if(!await nav.locator('.cad-nav-empty').textContent().then(x=>x.includes('No topics or pages match')))fail('topic filter','no empty result');
   await input.press('Escape');if(await nav.locator('details[open]').count()!==prior)fail('topic filter','clear did not restore fold state');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))fail('reader','horizontal overflow');
   const stamp=await page.locator('.site-footer time').evaluate(t=>({datetime:t.dateTime,text:t.textContent}));if(!/^\d{4}-\d{2}-\d{2}T/.test(stamp.datetime)||!/(?:PST|PDT)/.test(stamp.text))fail('timestamp','lost recorded instant/Pacific label');
  }finally{await done();}
 }
 for(const config of [{js:false},{block:'/kit/nav.js'},{block:'/web/site.js'}]){
  const {page,done}=await open('/docs/toolkit',{width:390,...config});try{
   await page.locator('cad-nav .cad-nav-toggle').click();if(!await page.locator('.explore-mobile-outline a').first().isVisible())fail('reader fallback','static article outline missing');
   const link=page.locator('.explore-mobile-outline a').first();await link.click();const hash=new URL(page.url()).hash;if(!hash||!await page.locator('[id="'+decodeURIComponent(hash.slice(1))+'"]').isVisible())fail('reader fallback','native outline target unavailable');
   if(config.js!==false&&!await page.locator('.cad-nav-filter').isDisabled())fail('reader fallback','nonworking filter is interactive');
  }finally{await done();}
 }
}
async function outlineThemeChecks(){
 for(const color of ['light','dark']){
  const {page,done}=await open('/docs/toolkit',{width:1600,color});try{
   const link=page.locator('.doc-rail a').filter({hasText:'Honest evidence'}).first();await link.scrollIntoViewIfNeeded();
   for(const state of ['normal','hover','focus','current']){
    if(state==='hover')await link.hover();
    if(state==='focus'){await page.keyboard.press('Tab');await link.focus();}
    if(state==='current')await link.evaluate(a=>a.setAttribute('aria-current','location'));
    await page.waitForTimeout(240);
    const low=await lowContrast(page,'.doc-rail');if(low.length)fail('reader outline '+color+' '+state,low.join('; '));
   }
   if(color==='dark'){
    await page.locator('.doc-rail').evaluate(el=>el.style.setProperty('--cad-nav-hover','#eef1e4'));await link.hover();await page.waitForTimeout(240);
    if(!(await lowContrast(page,'.doc-rail')).length)fail('outline negative control','pre-fix pale hover was not rejected');
   }
  }finally{await done();}
 }
}
try{await sharedDiscoveryChecks();await legacyChecks();await lifecycleChecks();await interactionChecks();await detailsChecks();await readerChecks();await outlineThemeChecks();}
finally{await browser.close();server.kill();await site.done();}
assert.deepEqual(problems,[],problems.join('\n'));
console.log(`Explore/catalogue/readers OK in ${engine.name()}`);
