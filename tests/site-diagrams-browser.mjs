/** Exercise the actual Python site consumer, not a hand-authored copy of its bootstrap. */
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtemp,readFile,mkdir,writeFile,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {chromium,webkit} from '@playwright/test';
const temporary=await mkdtemp(path.join(os.tmpdir(),'cad-agent-generated-diagrams-'));
execFileSync(process.env.PYTHON||'python3',['-c',`import pathlib,sys
from cadagent.publish.site import build_site
root=pathlib.Path(sys.argv[1]);(root/'README.md').write_text('# Generated diagrams\\n\\n\x60\x60\x60mermaid\\nflowchart LR\\nA[Plan]-->B[Build]\\n\x60\x60\x60\\n')
for theme in ('light','hud'):
 p=root/theme;p.mkdir();(p/'README.md').write_text((root/'README.md').read_text());build_site(p,{'pages':['README.md'],'theme':theme},'Generated fixture')
`,temporary],{cwd:new URL('../',import.meta.url),env:{...process.env,PYTHONPATH:'src',PYTHONDONTWRITEBYTECODE:'1'}});
const server=http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost');const target=path.resolve(temporary,'.'+url.pathname);if(!target.startsWith(temporary+path.sep))throw Error();const data=await readFile(target);res.writeHead(200,{'Content-Type':target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html'});res.end(data);}catch{res.writeHead(404).end();}});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`,engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?undefined:'chrome',headless:true}:{headless:true});
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-generated-diagrams';await mkdir(out,{recursive:true});const checks=[];
try{
 for(const theme of ['light','hud'])for(const route of ['pages/readme-md.html','index.html']){
  const page=await browser.newPage({viewport:{width:320,height:568}}),thirdParty=[];
  page.on('request',req=>{if(!req.url().startsWith(base))thirdParty.push(req.url());});await page.goto(`${base}/${theme}/site/${route}`);
  if(route==='index.html')await page.evaluate(()=>{const p=document.createElement('pre');p.className='mermaid';p.textContent='flowchart TD\nLater-->Visible';document.querySelector('main').append(p);});
  await page.waitForSelector('.cad-diagram[data-state=ready] svg');assert.equal(await page.locator('pre.mermaid:visible').count(),0);
  assert.equal(await page.locator('.cad-diagram').getAttribute('data-theme'),theme==='hud'?'dark':'light');assert.deepEqual(thirdParty,[]);
  checks.push({theme,route,rendered:true});await page.close();
 }
 await writeFile(`${out}/${engine.name()}.json`,JSON.stringify(checks,null,2));console.log(`${engine.name()}: generated Python document/index, light/HUD, static/dynamic SVGs PASS`);
}finally{await browser.close();await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});await rm(temporary,{recursive:true,force:true});}
