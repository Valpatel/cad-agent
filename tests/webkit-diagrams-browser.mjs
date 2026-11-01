import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,webkit} from '@playwright/test';
import {serveWebkit} from './webkit-server.mjs';
const diagram='flowchart LR\nA[Design] --> B[Build] --> C[Test]';
const html=theme=>`<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/kit/diagrams.css"><style>body{margin:16px;font:16px system-ui;background:${theme==='dark'?'#10141b':'#fffaf2'};color:${theme==='dark'?'white':'#263e35'}}main{max-width:900px;margin:auto}</style><body data-diagram-theme="${theme}"><main><h1>Design evidence</h1><pre><code class="language-mermaid">${diagram}</code></pre><pre class="mermaid">sequenceDiagram\nDesigner->>Robot: Test safely\nRobot-->>Designer: Results</pre><div id="dynamic"></div></main><script type="module">import {observeDiagrams} from '/kit/diagrams.js';window.diagrams=observeDiagrams();</script></body></html>`;
// A page whose diagram was drawn ahead of time (drawDiagram, as the cad-agent site build does, #132), in `theme`.
const ahead={figure:''},aheadHtml=theme=>`<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/kit/diagrams.css"><style>body{margin:16px;font:16px system-ui}main{max-width:900px;margin:auto}</style><body data-diagram-theme="${theme}"><main><h1>Drawn ahead</h1>${ahead.figure}<p id="after">After the diagram</p></main><script type="module">import {observeDiagrams} from '/kit/diagrams.js';window.diagrams=observeDiagrams();</script></body></html>`;
const site=await serveWebkit(new Map([['/light',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(html('light'));}],['/dark',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(html('dark'));}],
 ['/blank',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end('<!doctype html><link rel="stylesheet" href="/kit/diagrams.css"><body><main></main></body>');}],
 ['/ahead-light',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(aheadHtml('light'));}],['/ahead-dark',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(aheadHtml('dark'));}]]));
const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?undefined:'chrome',headless:true}:{headless:true});
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-diagrams';await mkdir(out,{recursive:true});const cases=[],errors=[];
async function ready(page,n){await page.waitForFunction(n=>document.querySelectorAll('.cad-diagram[data-state=ready] svg').length===n,n);}
async function noRaw(page){assert.equal(await page.locator('code.language-mermaid:visible,pre.mermaid:visible,.cad-diagram details[open]').count(),0);assert.ok(!(await page.locator('body').innerText()).includes('flowchart LR'));}
try{
 for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width:320,height:568},colorScheme:theme});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(site.url+'/'+theme);await ready(page,2);await noRaw(page);
  assert.equal(await page.locator('.cad-diagram').first().getAttribute('data-theme'),theme);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'only the diagram may scroll');
  const paint=await page.locator('.cad-diagram').first().evaluate(el=>({background:getComputedStyle(el).backgroundColor,rect:el.querySelector('svg').getBoundingClientRect().toJSON(),svgText:el.querySelector('svg').textContent}));
  assert.ok(paint.rect.width>100&&paint.rect.height>30&&paint.svgText.includes('Design'));
  await page.evaluate(()=>{document.getElementById('dynamic').innerHTML='<pre><code class="language-mermaid">flowchart TD\nStart-->Done</code></pre>';});await ready(page,3);await noRaw(page);
  const ids=await page.locator('.cad-diagram svg').evaluateAll(nodes=>nodes.map(n=>n.id));assert.equal(new Set(ids).size,3);
  await page.evaluate(()=>window.diagrams.render());assert.equal(await page.locator('.cad-diagram').count(),3);
  const figure=page.locator('.cad-diagram').first();assert.ok(await figure.locator('.cad-diagram-hint').isVisible());
  const rightmost=await figure.evaluate(el=>{const view=el.querySelector('.cad-diagram-view'),nodes=[...el.querySelectorAll('svg .node')];const node=nodes.sort((a,b)=>b.getBoundingClientRect().right-a.getBoundingClientRect().right)[0];view.scrollLeft=view.scrollWidth;const r=node.getBoundingClientRect(),v=view.getBoundingClientRect();return{text:node.textContent.trim(),right:r.right,edge:v.right,scroll:view.scrollLeft};});
  assert.equal(rightmost.text,'Test');assert.ok(rightmost.scroll>0&&rightmost.right<=rightmost.edge+1);
  await page.setViewportSize({width:1800,height:900});await page.waitForFunction(()=>document.querySelector('.cad-diagram-hint').hidden);
  await page.setViewportSize({width:320,height:568});await page.waitForFunction(()=>!document.querySelector('.cad-diagram-hint').hidden);
  await figure.locator('.cad-diagram-view').evaluate(el=>el.scrollLeft=0);
  await page.screenshot({path:`${out}/${engine.name()}-${theme}-320.png`,fullPage:true});cases.push({theme,paint,dynamic:true});await page.close();
 }
 // Loading is observable; failed runtime retry uses a fresh request and preserves healthy page content.
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));let release,requested;
 const held=new Promise(r=>release=r),seen=new Promise(r=>requested=r);
 await page.route('**/vendor/mermaid/mermaid.min.js',async route=>{requested();await held;await route.abort();});
 await page.goto(site.url+'/light',{waitUntil:'domcontentloaded'});await seen;
 assert.equal(await page.locator('.cad-diagram[data-state=loading]').count(),2);await noRaw(page);
 release();await page.waitForFunction(()=>document.querySelectorAll('.cad-diagram[data-state=error]').length===2);
 await page.unroute('**/vendor/mermaid/mermaid.min.js');
 // Both failed graphs can retry without discarding the rest of the document.
 for(const figure of await page.locator('.cad-diagram').all())await figure.getByRole('button',{name:'Retry diagram'}).click();await ready(page,2);await noRaw(page);
 await page.evaluate(()=>{const p=document.createElement('pre');p.className='mermaid';p.textContent='not a supported diagram';document.getElementById('dynamic').append(p);});
 await page.waitForSelector('.cad-diagram[data-state=error]');assert.equal(await page.locator('.cad-diagram[data-state=ready]').count(),2);
 assert.equal(await page.locator('body > div[id^="dmermaid"],body > div[id^="dcad-diagram"]').count(),0);
 await page.getByText('Diagram source',{exact:true}).last().click();assert.ok((await page.locator('details[open]').innerText()).includes('not a supported diagram'));
 const retry=await page.getByRole('button',{name:'Retry diagram'}).boundingBox();assert.ok(retry.height>=44);
 cases.push({loading:true,failedRuntimeRetry:true,invalidSourceIsolated:true});await page.close();
 // Hostile labels from the advisories fixed in Mermaid 11.10.0 stay inert: a KaTeX sequence label measured through
 // innerHTML (GHSA-7rqq-prvp-x9jh) and architecture iconText passed to html() (GHSA-8gwm-58g9-j8pw). Mermaid 11.4.1 ran both.
 const hostile=await browser.newPage();hostile.on('pageerror',e=>errors.push(e.message));
 await hostile.goto(site.url+'/light');await ready(hostile,2);
 await hostile.evaluate(()=>{const hook='<img src="x" onerror="window.cadXss=(window.cadXss||0)+1">';
  for(const source of [`sequenceDiagram\n    participant A as Alice${hook}$$\\text{Alice}$$\n    A->>John: Hello John`,
    `architecture-beta\n    group api(cloud)[API]\n    service db "${hook}" [Database] in api`]){
   const p=document.createElement('pre');p.className='mermaid';p.textContent=source;document.getElementById('dynamic').append(p);}});
 await hostile.waitForFunction(()=>document.querySelectorAll('.cad-diagram').length===4&&!document.querySelector('.cad-diagram:not([data-state=ready]):not([data-state=error])'));
 await hostile.waitForLoadState('networkidle');await hostile.waitForTimeout(500);
 const injected=await hostile.evaluate(()=>({ran:window.cadXss||0,handlers:document.querySelectorAll('[onerror]').length,states:[...document.querySelectorAll('.cad-diagram')].map(f=>f.dataset.state)}));
 assert.equal(injected.ran,0,'a hostile diagram label ran script');assert.equal(injected.handlers,0,'a hostile diagram label left an event handler in the page');
 cases.push({hostileLabelsInert:injected});await hostile.close();
 // Drawn ahead of time: drawDiagram returns the finished figure (light and dark), or null for a source Mermaid cannot draw.
 const drawer=await browser.newPage();drawer.on('pageerror',e=>errors.push(e.message));await drawer.goto(site.url+'/blank');
 const drawn=await drawer.evaluate(async source=>{const {drawDiagram}=await import('/kit/diagrams.js');const main=document.querySelector('main');
  const light=await drawDiagram(source,{theme:'light',id:'cad-diagram-sahead',parent:main}),dark=await drawDiagram(source,{theme:'dark',id:'cad-diagram-sdark',parent:main});
  const bad=await drawDiagram('not a supported diagram',{parent:main});
  return {light:light.outerHTML,dark:dark.dataset.theme,darkState:dark.dataset.state,bad,left:main.children.length};},diagram);
 assert.equal(drawn.bad,null);assert.equal(drawn.left,0,'drawDiagram leaves nothing behind');assert.deepEqual([drawn.dark,drawn.darkState],['dark','ready']);
 assert.match(drawn.light,/^<figure class="cad-diagram" data-theme="light"[^>]* data-state="ready"[^>]* style="--cad-diagram-w: [\d.]+px;">/);
 assert.match(drawn.light,/<p class="cad-diagram-hint">/,'the hint is left to the stylesheet');assert.match(drawn.light,/<svg id="cad-diagram-sahead"/);
 await drawer.close();ahead.figure=drawn.light;
 // In a light page it stays as drawn: no Mermaid download, nothing moves when the script runs, and the hint follows the width.
 for(const [width,overflows] of [[320,true],[1800,false]]){
  const page=await browser.newPage({viewport:{width,height:700}}),fetched=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',q=>{if(/mermaid\.min\.js/.test(q.url()))fetched.push(q.url());});
  // Measured while the module is held back (after the stylesheet, which a reader's first paint has too).
  await page.route('**/kit/diagrams.js',async route=>{await page.evaluate(async()=>{const link=document.querySelector('link[rel=stylesheet]');
   if(!link.sheet)await new Promise(r=>link.addEventListener('load',r,{once:true}));window.firstBox=document.querySelector('#after').getBoundingClientRect().top;window.firstHint=document.querySelector('.cad-diagram-hint').getBoundingClientRect().height;}).catch(()=>{});await route.continue();});
  await page.goto(site.url+'/ahead-light');await page.waitForFunction(()=>window.diagrams);await page.waitForLoadState('networkidle');
  const seen=await page.evaluate(()=>({id:document.querySelector('.cad-diagram svg').id,state:document.querySelector('.cad-diagram').dataset.state,
   first:window.firstBox,now:document.querySelector('#after').getBoundingClientRect().top,firstHint:window.firstHint,hint:!document.querySelector('.cad-diagram-hint').hidden,
   hintHeight:document.querySelector('.cad-diagram-hint').getBoundingClientRect().height}));
  assert.deepEqual([seen.id,seen.state],['cad-diagram-sahead','ready']);assert.deepEqual(fetched,[],'a drawn figure needs no Mermaid');
  assert.equal(seen.now,seen.first,'the text after the diagram did not move when the script ran');
  assert.equal(seen.hint,overflows,`hint at ${width}px`);assert.equal(seen.firstHint>0,overflows,`hint before the script at ${width}px`);assert.equal(seen.hintHeight>0,overflows);
  await page.setViewportSize({width:width===320?1800:320,height:700});await page.waitForFunction(o=>document.querySelector('.cad-diagram-hint').hidden===o,overflows);
  await page.close();
 }
 // In a dark page the light figure is drawn again, dark.
 const darker=await browser.newPage();darker.on('pageerror',e=>errors.push(e.message));await darker.goto(site.url+'/ahead-dark');
 await darker.waitForFunction(()=>document.querySelector('.cad-diagram')?.dataset.theme==='dark'&&document.querySelector('.cad-diagram').dataset.state==='ready');
 const redrawn=await darker.evaluate(()=>({id:document.querySelector('.cad-diagram svg').id,bg:getComputedStyle(document.querySelector('.cad-diagram')).backgroundColor,source:document.querySelector('.cad-diagram-source').textContent}));
 assert.notEqual(redrawn.id,'cad-diagram-sahead');assert.equal(redrawn.bg,'rgb(23, 29, 39)');assert.equal(redrawn.source,diagram);
 await darker.close();cases.push({drawnAhead:{light:'kept',dark:'redrawn'}});
 assert.deepEqual(errors,[]);await writeFile(`${out}/${engine.name()}-report.json`,JSON.stringify({cases,errors},null,2));console.log(`${engine.name()}: static, dynamic, phone, themes, loading, retry, invalid-source, hostile-label and drawn-ahead cases PASS`);
}finally{await browser.close();await site.close();}
