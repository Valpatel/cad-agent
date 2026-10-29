import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,webkit} from '@playwright/test';
import {serveWebkit} from './webkit-server.mjs';
const diagram='flowchart LR\nA[Design] --> B[Build] --> C[Test]';
const html=theme=>`<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/kit/diagrams.css"><style>body{margin:16px;font:16px system-ui;background:${theme==='dark'?'#10141b':'#fffaf2'};color:${theme==='dark'?'white':'#263e35'}}main{max-width:900px;margin:auto}</style><body data-diagram-theme="${theme}"><main><h1>Design evidence</h1><pre><code class="language-mermaid">${diagram}</code></pre><pre class="mermaid">sequenceDiagram\nDesigner->>Robot: Test safely\nRobot-->>Designer: Results</pre><div id="dynamic"></div></main><script type="module">import {observeDiagrams} from '/kit/diagrams.js';window.diagrams=observeDiagrams();</script></body></html>`;
const site=await serveWebkit(new Map([['/light',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(html('light'));}],['/dark',(_q,r)=>{r.writeHead(200,{'Content-Type':'text/html'});r.end(html('dark'));}]]));
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
 for(const button of await page.getByRole('button',{name:'Retry diagram'}).all())await button.click();await ready(page,2);await noRaw(page);
 await page.evaluate(()=>{const p=document.createElement('pre');p.className='mermaid';p.textContent='not a supported diagram';document.getElementById('dynamic').append(p);});
 await page.waitForSelector('.cad-diagram[data-state=error]');assert.equal(await page.locator('.cad-diagram[data-state=ready]').count(),2);
 assert.equal(await page.locator('body > div[id^="dmermaid"],body > div[id^="dcad-diagram"]').count(),0);
 await page.getByText('Diagram source',{exact:true}).last().click();assert.ok((await page.locator('details[open]').innerText()).includes('not a supported diagram'));
 const retry=await page.getByRole('button',{name:'Retry diagram'}).boundingBox();assert.ok(retry.height>=44);
 cases.push({loading:true,failedRuntimeRetry:true,invalidSourceIsolated:true});await page.close();
 assert.deepEqual(errors,[]);await writeFile(`${out}/${engine.name()}-report.json`,JSON.stringify({cases,errors},null,2));console.log(`${engine.name()}: static, dynamic, phone, themes, loading, retry and invalid-source cases PASS`);
}finally{await browser.close();await site.close();}
