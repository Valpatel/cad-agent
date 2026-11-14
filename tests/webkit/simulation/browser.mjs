/** Real recorded solver poses through the shared stage, controls and disposable host. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,webkit} from '../../site/npm-context.mjs';
import {serveWebkit} from '../webkit-server.mjs';

const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:process.env.PLAYWRIGHT_CHANNEL==='chromium'?{}:{channel:'chrome'})}:{headless:true});
const site=process.env.REPLAY_BASE_URL?null:await serveWebkit(new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]));
const base=process.env.REPLAY_BASE_URL||site.url;
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-robot-replay';await mkdir(out,{recursive:true});
const errors=[],cases=[];
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
  assert.deepEqual(errors,[]);
  await writeFile(`${out}/${engine.name()}.json`,JSON.stringify({engine:engine.name(),base,sourceRevision:process.env.TEST_SOURCE_REVISION||'unrecorded',cases,errors},null,2));
  console.log(`${engine.name()}: ${cases.length} recorded replay layout/theme/controls/pose/disposal cases passed`);
}finally{await browser.close();await site?.close();}
