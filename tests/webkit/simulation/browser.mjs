/** Real recorded solver poses through the shared stage, controls and disposable host. */
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {chromium,webkit} from '../../site/npm-context.mjs';
import {serveWebkit} from '../webkit-server.mjs';

const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:process.env.PLAYWRIGHT_CHANNEL==='chromium'?{}:{channel:'chrome'})}:{headless:true});
const site=process.env.REPLAY_BASE_URL?null:await serveWebkit(new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]));
const base=process.env.REPLAY_BASE_URL||site.url;
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-robot-replay';await mkdir(out,{recursive:true});
const errors=[],cases=[];
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const runtimePaths=['simulation/replay.js','simulation/viewer.js','simulation/scene.js','simulation/page.js','simulation/viewer.html','simulation/viewer.css','simulation/examples/two-link-arm/recording.json','simulation/examples/two-link-arm/receipt.json','model/stage.js','host/viewer-host.js','host/viewer-host.css','host/stage-controls.js','ui/theme.js','ui/theme.css'];
const provenance={harnessSha256:hash(await readFile(new URL(import.meta.url))),runtimeHashes:Object.fromEntries(await Promise.all(runtimePaths.map(async name=>[name,hash(await readFile(new URL('../../../software/cadagent/webkit/'+name,import.meta.url)))])))};
try{
  for(const width of [390,1100,3440])for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width,height:width===3440?1440:900},colorScheme:theme,reducedMotion:'reduce'});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/kit/simulation/viewer.html');await page.waitForFunction(()=>document.body.dataset.ready==='1');
    await page.waitForFunction(()=>document.fonts.status==='loaded');
    const geom=await page.evaluate(()=>{
      const root=document.querySelector('.cad-replay-host'),canvas=root.querySelector('canvas'),viewport=canvas.parentElement;
      const rect=canvas.getBoundingClientRect();return {root:{width:root.clientWidth,scrollWidth:root.scrollWidth},viewport:{width:viewport.clientWidth,height:viewport.clientHeight,scrollWidth:viewport.scrollWidth,scrollHeight:viewport.scrollHeight},canvas:{width:rect.width,height:rect.height},page:{width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth},state:__replay.playback.state(),background:__replay.stage.scene.background.getHexString(),theme:getComputedStyle(root).getPropertyValue('--viewer-bg').trim()};
    });
    assert.ok(geom.canvas.width>250&&geom.canvas.height>200,JSON.stringify(geom));
    assert.ok(geom.root.scrollWidth<=geom.root.width+1&&geom.viewport.scrollWidth<=geom.viewport.width+1&&geom.viewport.scrollHeight<=geom.viewport.height+1&&geom.page.scrollWidth<=geom.page.width+1,JSON.stringify(geom));
    assert.equal(geom.state.playing,false,'recording starts paused');
    for(const name of ['Play recording','Restart recording','Zoom to fit'])assert.ok(await page.getByRole('button',{name,exact:true}).isVisible());
    assert.ok(await page.getByLabel('Recording time',{exact:true}).isVisible());assert.ok(await page.getByLabel('Playback speed',{exact:true}).isVisible());
    const pose=await page.evaluate(async()=>{
      const source=await (await fetch('./examples/two-link-arm/recording.json')).json();
      __replay.playback.seek(1);const sample=source.frames.find(f=>f.time_s===1);
      return {expected:sample.poses,actual:__replay.scene.groups.map(g=>g.matrixWorld.toArray())};
    });
    // Independent quaternion-to-matrix oracle, then exact Z-up -> Y-up basis conversion.
    pose.expected.forEach((p,i)=>{
      const [x,y,z,w]=p.quaternion,[px,py,pz]=p.position;
      const expected=[1-2*(y*y+z*z),2*(x*z-y*w),-2*(x*y+z*w),0,2*(x*y-z*w),2*(y*z+x*w),-(1-2*(x*x+z*z)),0,2*(x*z+y*w),1-2*(x*x+y*y),-2*(y*z-x*w),0,px,pz,-py,1];
      expected.forEach((n,k)=>assert.ok(Math.abs(pose.actual[i][k]-n)<1e-9,`body ${i} matrix ${k}: ${pose.actual[i][k]} != ${n}`));
    });
    await page.getByRole('button',{name:'Play recording',exact:true}).click();await page.waitForFunction(()=>__replay.playback.state().time>1.15);
    await page.getByRole('button',{name:'Pause recording',exact:true}).click();await page.waitForFunction(()=>!__replay.playback.state().playing);
    const paused=await page.evaluate(()=>__replay.playback.state().time);await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>__replay.playback.state().time),paused);
    await page.getByLabel('Playback speed',{exact:true}).selectOption('2');assert.equal(await page.evaluate(()=>__replay.playback.state().speed),2);
    const scrub=page.getByLabel('Recording time',{exact:true});await scrub.scrollIntoViewIfNeeded();await scrub.focus();
    await page.waitForFunction(()=>document.activeElement===document.querySelector('[aria-label="Recording time"]'));
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.keyboard.press('End');await page.waitForFunction(()=>__replay.playback.state().time===10);
    await page.keyboard.press('Home');await page.waitForFunction(()=>__replay.playback.state().time===0);
    const initial=await page.evaluate(()=>__replay.getViewState().camera);await page.locator('.cad-viewer-viewport').focus();await page.keyboard.press('ArrowRight');
    const turned=await page.evaluate(()=>__replay.getViewState().camera);assert.notDeepEqual(turned,initial);
    await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();const fitted=await page.evaluate(()=>__replay.getViewState().camera);
    initial.position.forEach((n,i)=>assert.ok(Math.abs(n-fitted.position[i])<1e-9));
    await page.getByRole('button',{name:'Toggle dark theme',exact:true}).click();
    const toggled=await page.evaluate(()=>({color:__replay.stage.scene.background.getHexString(),pressed:document.querySelector('.theme-toggle').getAttribute('aria-pressed')}));
    assert.notEqual(toggled.color,geom.background);assert.equal(toggled.pressed,String(theme==='light'));
    await page.getByRole('button',{name:'Toggle dark theme',exact:true}).click();
    await page.evaluate(()=>__replay.playback.seek(3.2));await page.screenshot({path:`${out}/${engine.name()}-${width}-${theme}.png`,fullPage:true});
    if(width===1100&&theme==='dark')await page.locator('.cad-viewer-viewport').screenshot({path:`${out}/preview.png`});
    const cleanup=await page.evaluate(()=>{
      const clock=__replay.playback,scene=__replay.scene;let meshes=0,geometries=0,materials=0;
      scene.root.traverse(object=>{if(object.isMesh){meshes++;object.geometry.addEventListener('dispose',()=>geometries++);object.material.addEventListener('dispose',()=>materials++);}});
      __replay.dispose();__replay.dispose();return {disposed:clock.state().disposed,canvas:document.querySelectorAll('#replay canvas').length,sceneDetached:scene.root.parent===null,meshes,geometries,materials};
    });
    assert.equal(cleanup.disposed,true);assert.equal(cleanup.canvas,0);assert.equal(cleanup.sceneDetached,true);assert.ok(cleanup.meshes>0);assert.equal(cleanup.geometries,cleanup.meshes);assert.equal(cleanup.materials,cleanup.meshes);
    cases.push({width,theme,geom,pose:'all recorded world transforms match independent oracle',cleanup});await context.close();
  }
  const context=await browser.newContext({viewport:{width:1100,height:900},reducedMotion:'reduce'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/simulation/examples/two-link-arm/recording.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
  await page.goto(base+'/kit/simulation/viewer.html');await page.waitForFunction(()=>document.body.dataset.ready==='error');
  assert.match(await page.locator('.cad-viewer-message').innerText(),/SHA-256 mismatch/);assert.equal(await page.locator('#replay canvas').count(),0);
  await page.unroute('**/simulation/examples/two-link-arm/recording.json');await page.getByRole('button',{name:'Retry viewer',exact:true}).click();
  await page.waitForFunction(()=>document.body.dataset.ready==='1');assert.equal(await page.locator('#replay canvas').count(),1);
  cases.push({name:'corrupt recording refuses to render; retry restores verified example'});
  const aborted=await page.evaluate(async()=>{
    const {createReplayViewer}=await import('./viewer.js'),container=document.createElement('div'),lifetime=new AbortController();document.body.append(container);
    const viewer=createReplayViewer(container,{recordingUrl:new URL('./examples/two-link-arm/recording.json',location.href),signal:lifetime.signal});lifetime.abort();
    const ready=await viewer.ready,count=container.childElementCount;viewer.dispose();container.remove();return{ready,count};
  });
  assert.deepEqual(aborted,{ready:false,count:0});cases.push({name:'aborted pending load leaves no host or canvas'});await context.close();
  const boundaryContext=await browser.newContext({viewport:{width:1100,height:900},reducedMotion:'reduce'}),boundary=await boundaryContext.newPage();
  boundary.on('pageerror',e=>errors.push(e.message));
  await boundary.route('**/simulation/examples/two-link-arm/receipt.json',route=>route.fulfill({status:503,body:'unavailable'}));
  await boundary.goto(base+'/kit/simulation/viewer.html');await boundary.waitForFunction(()=>document.body.dataset.ready==='error');
  assert.ok(await boundary.getByRole('button',{name:'Retry recording',exact:true}).isVisible());
  await boundary.unroute('**/simulation/examples/two-link-arm/receipt.json');await boundary.getByRole('button',{name:'Retry recording',exact:true}).click();
  await boundary.waitForFunction(()=>document.body.dataset.ready==='1');cases.push({name:'receipt outage has an explicit working retry'});
  const sparse=await boundary.evaluate(async()=>{
    const THREE=await import('three'),{createReplayViewer}=await import('./viewer.js');
    const source={schema:'cad-agent.pose-recording/1',title:'Sparse rotation counterexample',convention:{length:'m',up:'z',handedness:'right',quaternion:'xyzw'},bodies:[{id:'bar',label:'Rotating bar',geometry:[{shape:'box',size:[4,.1,.1],position:[0,0,0],quaternion:[0,0,0,1],color:'#00aabb'}]}],frames:[{time_s:0,poses:[{position:[0,0,3],quaternion:[0,0,0,1]}]},{time_s:2,poses:[{position:[0,0,3],quaternion:[0,1,0,0]}]}]};
    const container=document.createElement('div');container.style.cssText='width:900px;height:500px';document.body.append(container);
    const viewer=createReplayViewer(container,{recording:source});await viewer.ready;const peaks=[];
    for(const time of [0,.25,.5,.75,1,1.25,1.5,1.75,2]){
      viewer.playback.seek(time);const mesh=viewer.scene.groups[0].children[0],box=mesh.geometry.boundingBox;viewer.stage.camera.updateMatrixWorld(true);
      let max=0;for(let i=0;i<8;i++){const p=new THREE.Vector3(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z).applyMatrix4(mesh.matrixWorld).project(viewer.stage.camera);max=Math.max(max,Math.abs(p.x),Math.abs(p.y));}peaks.push({time,max});
    }
    viewer.dispose();container.remove();return peaks;
  });
  assert.ok(sparse.every(p=>p.max<1),JSON.stringify(sparse));cases.push({name:'Fit contains sparse180-degree rotation between endpoints',sparse});await boundaryContext.close();
  assert.deepEqual(errors,[]);
  await writeFile(`${out}/${engine.name()}.json`,JSON.stringify({engine:engine.name(),base,sourceRevision:process.env.TEST_SOURCE_REVISION||'unrecorded',...provenance,cases,errors},null,2));
  console.log(`${engine.name()}: ${cases.length} recorded replay layout/theme/controls/pose/disposal cases passed`);
}finally{await browser.close();await site?.close();}
