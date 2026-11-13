/** Two real viewers share a contained host; resource and interaction checks use public APIs. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {chromium, webkit} from '../../site/npm-context.mjs';
import {serveWebkit} from '../webkit-server.mjs';

const vertices = [[0,0,0],[10,0,0],[10,20,0],[0,20,0],[0,0,30],[10,0,30],[10,20,30],[0,20,30]];
const faces = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]];
const stl = Buffer.alloc(84 + faces.length * 50);
stl.writeUInt32LE(faces.length, 80);
faces.forEach((face,i) => face.forEach((v,j) => vertices[v].forEach((n,k) => stl.writeFloatLE(n,84+i*50+12+j*12+k*4))));
const manifest = {
  title:'Fixture assembly', units:'mm', up:'z',
  parts:[{name:'block',file:'block.stl',bounds_mm:[0,0,0,10,20,30],color:'#4bb9cc',sha256:createHash('sha256').update(stl).digest('hex')}],
};
const step = await readFile(new URL('../../fixtures/file-viewer/block.step', import.meta.url));
const html = `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contained viewer test</title><link rel="stylesheet" href="/kit/host/viewer-host.css">
<style>body{margin:17px;background:#f6f4ed;color:#243e47;font:16px system-ui;min-height:1500px}h1{font-size:24px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px}.slot{height:510px;min-width:0}.spare{height:380px}button#outside{padding:8px}@media(max-width:600px){.pair{grid-template-columns:minmax(0,1fr)}.slot{height:430px}}</style>
<body><h1>Independent engineering viewers</h1><button id="outside">Outside control</button><p>Page content still scrolls.</p>
<main class="pair"><section class="slot" id="left"></section><section class="slot" id="right"></section></main><section class="spare" id="spare"></section>
<script type="importmap">{"imports":{"three":"/kit/vendor/three/three.module.min.js","three/addons/":"/kit/vendor/three/addons/"}}</script>
<script type="module">
import {createModelHost,createFileHost} from '/kit/host/adapters.js';
import {createViewerHost} from '/kit/host/viewer-host.js';
window.factories={createModelHost,createFileHost,createViewerHost};
window.events={left:[],right:[]};
window.left=createModelHost(document.querySelector('#left'),{manifestUrl:'/view.json',title:'Assembly'});
window.right=createFileHost(document.querySelector('#right'),{file:'/block.stl',title:'Original file'});
left.subscribe(event=>events.left.push(event));right.subscribe(event=>events.right.push(event));
window.ready=Promise.all([left.ready,right.ready]);
</script></body></html>`;
const routes = new Map([
  ['/',(_,res)=>res.writeHead(200,{'Content-Type':'text/html'}).end(html)],
  ['/favicon.ico',(_,res)=>res.writeHead(204).end()],
  ['/view.json',(_,res)=>res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(manifest))],
  ['/block.stl',(_,res)=>res.end(stl)],
  ['/block.step',(_,res)=>res.end(step)],
  ['/bad.json',(_,res)=>res.writeHead(200,{'Content-Type':'application/json'}).end('{"parts":[]}')],
]);
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const launch = engine === chromium
  ? (process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true} : {channel:process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome',headless:true})
  : {headless:true};
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-contained-viewers';
await mkdir(out,{recursive:true});
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const runtimeFiles = ['host/viewer-host.js','host/adapters.js','host/stage-controls.js','host/viewer-host.css',
  'viewer.js','file-viewer.js','file-loader.js','stage.js'];
const provenance = {
  sourceRevision:process.env.TEST_SOURCE_REVISION || 'unrecorded',
  harnessSha256:sha(await readFile(new URL(import.meta.url))),
  runtimeHashes:Object.fromEntries(await Promise.all(runtimeFiles.map(async name=>[name,sha(await readFile(new URL('../../../software/cadagent/webkit/'+name,import.meta.url)))]))),
  fixtureMeshSha256:sha(stl),
};
const site = await serveWebkit(routes), browser = await engine.launch(launch), errors = [], cases = [];
let page;
try {
  const context = await browser.newContext({viewport:{width:1200,height:900},reducedMotion:'reduce'});
  await context.addInitScript(() => {
    window.resourceCounts = {contexts:0,lost:0,workers:0,terminated:0};
    const getContext = HTMLCanvasElement.prototype.getContext, contexts = new WeakSet();
    HTMLCanvasElement.prototype.getContext = function(...args) {
      const result = getContext.apply(this,args);
      if (result && typeof result.getParameter === 'function' && !contexts.has(result)) {
        contexts.add(result); resourceCounts.contexts++;
        this.addEventListener('webglcontextlost',()=>resourceCounts.lost++,{once:true});
      }
      return result;
    };
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args){super(...args);resourceCounts.workers++;this.counted=false;}
      terminate(){if(!this.counted){this.counted=true;resourceCounts.terminated++;}return super.terminate();}
    };
  });
  page = await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  const open = async () => {
    await page.goto(site.url+'/');
    await page.waitForFunction(()=>window.left?.root.dataset.state==='ready' && window.right?.root.dataset.state==='ready');
    assert.deepEqual(await page.evaluate(()=>ready),[true,true]);
  };
  const state = name => page.evaluate(name=>window[name].getViewState(),name);
  const canvas = name => page.locator(`#${name} canvas`).first();
  const fit = name => page.locator(`#${name}`).getByRole('button',{name:/zoom to fit/i});
  await open();
  const initial = await page.evaluate(()=>({
    body:{margin:getComputedStyle(document.body).margin,overflow:getComputedStyle(document.body).overflow,ready:document.body.dataset.ready,stageError:document.body.dataset.stageError},
    ids:[...document.querySelectorAll('#left [id], #right [id]')].map(node=>node.id),
    canvas:[...document.querySelectorAll('.slot canvas')].map(node=>{const parent=node.parentElement,r=node.getBoundingClientRect();return{width:r.width,height:r.height,clientWidth:parent.clientWidth,scrollWidth:parent.scrollWidth,clientHeight:parent.clientHeight,scrollHeight:parent.scrollHeight};}),
    capabilities:[left.capabilities,right.capabilities],resources:{...resourceCounts},
  }));
  assert.equal(initial.body.margin,'17px');assert.notEqual(initial.body.overflow,'hidden');
  assert.equal(initial.body.ready,undefined);assert.equal(initial.body.stageError,undefined);
  assert.equal(new Set(initial.ids).size,initial.ids.length);assert.ok(!initial.ids.some(id=>['app','hud','panel','topbar'].includes(id)));
  assert.equal(initial.canvas.length,2);
  for (const box of initial.canvas){assert.ok(box.width>200&&box.height>120);assert.ok(box.scrollWidth<=box.clientWidth+1&&box.scrollHeight<=box.clientHeight+1);}
  assert.ok(await fit('left').isVisible());assert.ok(await fit('right').isVisible());
  assert.ok(initial.resources.contexts>=2);
  cases.push({name:'two real consumers, scoped CSS/status, bounded canvases',initial});

  // Actual keyboard and pointer changes affect only the focused viewer.
  const beforeRight = await state('right'), beforeLeft = await state('left');
  await page.locator('#left .cad-viewer-viewport').focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(80);
  assert.notDeepEqual(await state('left'),beforeLeft);assert.deepEqual(await state('right'),beforeRight);
  const leftChosen = await state('left');
  await page.evaluate(()=>{document.querySelector('.pair').style.gridTemplateColumns='minmax(0,3fr) minmax(0,2fr)';});
  await page.waitForTimeout(120);
  assert.deepEqual(await state('left'),leftChosen);assert.deepEqual(await state('right'),beforeRight);
  await fit('left').click();
  const rightBox = await canvas('right').boundingBox(), leftBeforePointer = await state('left');
  await page.mouse.move(rightBox.x+rightBox.width*.5,rightBox.y+rightBox.height*.5);
  await page.mouse.down();await page.mouse.move(rightBox.x+rightBox.width*.7,rightBox.y+rightBox.height*.65,{steps:6});await page.mouse.up();
  await page.waitForTimeout(100);
  assert.notDeepEqual(await state('right'),beforeRight);assert.deepEqual(await state('left'),leftBeforePointer);
  cases.push({name:'keyboard/pointer isolation and camera-preserving resize'});

  if(engine===chromium){
    await fit('right').click();
    const cameraRadius=value=>Math.hypot(...value.camera.position.map((n,i)=>n-value.camera.target[i]));
    const beforePinch=await state('right'),leftBeforePinch=await state('left');
    const cdp=await context.newCDPSession(page),rect=await canvas('right').boundingBox();
    const x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-25,y,id:1},{x:x+25,y,id:2}]});
    for(let d=30;d<=60;d+=5)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-d,y,id:1},{x:x+d,y,id:2}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    await page.waitForTimeout(100);
    const pinchRatio=cameraRadius(await state('right'))/cameraRadius(beforePinch);
    assert.ok(pinchRatio<.8&&pinchRatio>.2,`pinch ratio ${pinchRatio}`);
    assert.deepEqual(await state('left'),leftBeforePinch);
    await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:false});await cdp.detach();
    cases.push({name:'native two-finger pinch stays in its viewer',pinchRatio});
  }

  // A selection is local domain state; no cross-view mutation is inferred.
  const selection = await page.evaluate(()=>{
    const before=right.getViewState();left.select('block');
    return {left:left.getViewState(),right:right.getViewState(),before,events:events.left};
  });
  assert.deepEqual(selection.right,selection.before);assert.ok(JSON.stringify(selection.left).includes('block'));
  assert.ok(selection.events.length>0);
  await page.evaluate(()=>left.select(null));
  const fileSelection = await page.evaluate(()=>{
    const before=left.getViewState();right.select('mesh:0');
    return{selected:right.getViewState().selection,left:left.getViewState(),before};
  });
  assert.equal(fileSelection.selected,'mesh:0');assert.deepEqual(fileSelection.left,fileSelection.before);
  await page.evaluate(()=>right.select(null));
  cases.push({name:'both domain selections remain local',events:selection.events});

  // A saved presentation round-trips; malformed input is rejected without mutation.
  const restore = await page.evaluate(()=>{
    const saved=left.getViewState();left.fit();left.restoreViewState(saved);const restored=left.getViewState();
    let rejected=false;try{left.restoreViewState({version:999,camera:{position:[null,0,0]}});}catch{rejected=true;}
    return{saved,restored,rejected,after:left.getViewState()};
  });
  assert.deepEqual(restore.restored,restore.saved);assert.ok(restore.rejected);assert.deepEqual(restore.after,restore.saved);
  const foreign=await page.evaluate(()=>{
    const before=right.getViewState();let rejected=false;
    try{right.restoreViewState(left.getViewState());}catch{rejected=true;}
    return{before,after:right.getViewState(),rejected};
  });
  assert.ok(foreign.rejected);assert.deepEqual(foreign.before,foreign.after);
  cases.push({name:'presentation roundtrip, malformed and foreign-state rejection'});

  // An observer must not write into the live page after its host is removed.
  const sibling = await state('right');
  await page.evaluate(()=>document.querySelector('#left').remove());
  await page.waitForFunction(()=>resourceCounts.lost>=1);
  assert.deepEqual(await state('right'),sibling);assert.equal(await page.locator('#right canvas').count(),1);
  await fit('right').click();
  cases.push({name:'DOM removal disposes one renderer, sibling remains usable'});

  // Cancellation while the original STEP worker is consuming CPU terminates it.
  await page.route('**/file-step-worker.js',route=>route.fulfill({contentType:'text/javascript',body:'onmessage=()=>{postMessage({phase:"Busy parser fixture"});const end=Date.now()+10000;while(Date.now()<end){};postMessage({error:"Too late"});};'}));
  await page.evaluate(()=>{
    window.workerBefore=resourceCounts.terminated;
    window.busy=factories.createFileHost(document.querySelector('#spare'),{file:'/block.step',title:'Busy parser'});
  });
  await page.getByText('Busy parser fixture',{exact:false}).first().waitFor();
  const cancelledAt=Date.now();await page.evaluate(()=>busy.dispose());
  await page.waitForFunction(()=>resourceCounts.terminated>workerBefore);
  assert.ok(Date.now()-cancelledAt<2000);
  assert.equal(await page.locator('#spare canvas').count(),0);
  assert.equal(await page.evaluate(()=>busy.ready),false);
  await page.unroute('**/file-step-worker.js');
  cases.push({name:'active STEP CPU worker terminates on disposal'});

  // Detached or superseded requests do not paint late results or emit ready.
  let heldRoute;
  await page.route('**/held.json',route=>{heldRoute=route;});
  await page.evaluate(()=>{window.delayed=factories.createModelHost(document.querySelector('#spare'),{manifestUrl:'/held.json',title:'Delayed assembly'});window.delayedEvents=[];delayed.subscribe(event=>delayedEvents.push(event));});
  await page.waitForTimeout(50);
  await page.evaluate(()=>delayed.dispose());
  if(heldRoute)await heldRoute.fulfill({contentType:'application/json',body:JSON.stringify(manifest)}).catch(()=>{});
  assert.equal(await page.evaluate(()=>delayed.ready),false);
  assert.equal(await page.locator('#spare canvas').count(),0);
  await page.unroute('**/held.json');
  cases.push({name:'pending model mount cannot publish after disposal'});

  // A late handle returned by an uncooperative adapter must itself be disposed.
  await page.evaluate(()=>{
    window.lateDisposed=0;
    window.late=factories.createViewerHost(document.querySelector('#spare'),{title:'Late adapter',mount:async({viewport})=>{
      await new Promise(resolve=>window.finishLate=resolve);
      viewport.append(document.createElement('span'));
      return{fit(){},dispose(){lateDisposed++;},getViewState(){return{version:1};},restoreViewState(){},capabilities:{fit:true}};
    }});
  });
  await page.waitForFunction(()=>typeof finishLate==='function');
  await page.evaluate(()=>{late.dispose();finishLate();});
  await page.waitForFunction(()=>lateDisposed===1);
  assert.equal(await page.evaluate(()=>late.ready),false);assert.equal(await page.locator('#spare').innerHTML(),'');
  cases.push({name:'late adapter result is disposed once'});

  // Failed mount allocations disappear; a visible native retry stays available.
  await page.evaluate(()=>{
    window.failed=factories.createViewerHost(document.querySelector('#spare'),{title:'Failure fixture',mount:async({viewport})=>{
      const node=document.createElement('span');node.textContent='Allocated before failure';viewport.append(node);throw new Error('Fixture mount failed');
    }});
  });
  assert.equal(await page.evaluate(()=>failed.ready),false);
  assert.equal(await page.getByText('Allocated before failure',{exact:true}).count(),0);
  assert.ok(await page.getByText(/Fixture mount failed/).isVisible());
  assert.ok(await page.locator('#spare').getByRole('button',{name:/retry/i}).isVisible());
  await page.evaluate(()=>failed.dispose());
  cases.push({name:'failed mount removes partial DOM and presents retry'});

  await page.evaluate(()=>{window.invalid=factories.createModelHost(document.querySelector('#spare'),{manifestUrl:'/bad.json',title:'Invalid source'});});
  assert.equal(await page.evaluate(()=>invalid.ready),false);
  assert.equal(await page.locator('#spare canvas').count(),0);
  assert.ok(await page.locator('#spare').getByRole('button',{name:/retry/i}).isVisible());
  assert.ok(await page.locator('#spare').getByRole('button',{name:/zoom to fit/i}).isDisabled());
  await page.evaluate(()=>invalid.dispose());
  cases.push({name:'invalid real model keeps retry and disables unavailable camera'});

  // Three repeated real loads leave no contexts alive when the last host closes.
  for(let i=0;i<3;i++){
    const loaded=await page.evaluate(async()=>{window.cycle=factories.createFileHost(document.querySelector('#spare'),{file:'/block.stl',title:'Repeated file'});return cycle.ready;});
    assert.equal(loaded,true);await page.evaluate(()=>cycle.dispose());
  }
  await fit('right').focus();await page.evaluate(()=>right.dispose());
  assert.equal(await page.evaluate(()=>document.activeElement.id),'right');
  await page.waitForFunction(()=>resourceCounts.lost===resourceCounts.contexts);
  const released=await page.evaluate(()=>({...resourceCounts}));
  assert.equal(released.workers,released.terminated);
  cases.push({name:'repeat loads release GPU contexts and workers',resources:released});

  // Narrow layouts retain accessible camera controls without shrinking the page text.
  for(const viewport of [{width:390,height:844},{width:844,height:390}]){
    await page.setViewportSize(viewport);await open();
    const measured=await page.evaluate(()=>({
      pageWidth:document.documentElement.scrollWidth,
      canvases:[...document.querySelectorAll('.slot canvas')].map(node=>{const r=node.getBoundingClientRect(),p=node.parentElement;return{width:r.width,height:r.height,overflowX:p.scrollWidth-p.clientWidth,overflowY:p.scrollHeight-p.clientHeight};}),
    }));
    assert.ok(measured.pageWidth<=viewport.width+1);
    for(const c of measured.canvases){assert.ok(c.width>120&&c.height>120);assert.ok(c.overflowX<=1&&c.overflowY<=1);}
    for(const name of ['left','right'])assert.ok(await fit(name).isVisible());
    await page.screenshot({path:`${out}/${engine.name()}-${viewport.width}x${viewport.height}.png`,fullPage:true});
    cases.push({name:'responsive contained layout',viewport,measured});
  }
  assert.deepEqual(errors,[]);
  await writeFile(`${out}/${engine.name()}-report.json`,JSON.stringify({passed:true,...provenance,engine:engine.name(),browserVersion:browser.version(),cases,errors},null,2));
  console.log(JSON.stringify({passed:true,engine:engine.name(),cases:cases.length,out}));
}catch(error){
  if(page){await page.screenshot({path:`${out}/${engine.name()}-failure.png`,fullPage:true}).catch(()=>{});console.error(await page.locator('body').innerText().catch(()=>''));}
  throw error;
}finally{await browser.close();await site.close();}
