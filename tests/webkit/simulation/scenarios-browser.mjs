/** Gyropup's recorded scenarios in a browser: the scenario switch shows the chosen recording (an independent pose
 * oracle, with a planted control that the oracle tells scenarios apart), its own summary, the followed camera, and a
 * tampered recording refused by its SHA-256. Deterministic: playback is seeked, never timed. */
import assert from 'node:assert/strict';
import {mkdir,readFile} from 'node:fs/promises';
import {chromium,webkit} from '../../site/npm-context.mjs';
import {serveWebkit} from '../webkit-server.mjs';

const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:process.env.PLAYWRIGHT_CHANNEL==='chromium'?{}:{channel:'chrome'})}:{headless:true});
const site=await serveWebkit(new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]));
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-robot-scenarios';await mkdir(out,{recursive:true});
const example=new URL('../../../software/cadagent/webkit/simulation/examples/gyropup-v2/',import.meta.url);
const index=JSON.parse(await readFile(new URL('index.json',example),'utf8'));
const recordings=Object.fromEntries(await Promise.all(index.scenarios.map(async s=>[s.id,JSON.parse(await readFile(new URL(s.file,example),'utf8'))])));
const page_=`${site.url}/kit/simulation/examples/gyropup-v2/viewer.html`;
const errors=[],cases=[];
// Independent quaternion-to-matrix oracle, then the exact Z-up -> Y-up basis change of the scene root.
const expectedMatrix=({position:[px,py,pz],quaternion:q})=>{const n=Math.hypot(...q),[x,y,z,w]=q.map(c=>c/n);return [1-2*(y*y+z*z),2*(x*z-y*w),-2*(x*y+z*w),0,2*(x*y-z*w),2*(y*z+x*w),-(1-2*(x*x+z*z)),0,2*(x*z+y*w),1-2*(x*x+y*y),-2*(y*z-x*w),0,px,pz,-py,1];};
const mismatch=(actual,pose)=>Math.max(...expectedMatrix(pose).map((n,k)=>Math.abs(actual[k]-n)));
const frameAt=(id,t)=>recordings[id].frames.find(f=>Math.abs(f.time_s-t)<1e-9);
const seekAndRead=(page,t)=>page.evaluate(async t=>{
  __replay.playback.seek(t);const frame=__replay.stage.renderer.info.render.frame;
  await new Promise(resolve=>{const wait=()=>__replay.stage.renderer.info.render.frame>frame+1?resolve():requestAnimationFrame(wait);wait();});
  return {matrices:__replay.scene.groups.map(g=>g.matrixWorld.toArray()),target:__replay.stage.controls.target.toArray(),camera:__replay.stage.camera.position.toArray()};
},t);
const summaryText=page=>page.locator('.replay-summary').innerText();
// On a phone the 3D view comes first, straight under the title bar, and the controls (scenario select included) follow it
// inside the host's width; on a wide screen the controls stay above the view. Returns the problem, or null.
const orderProblem=async(page,width)=>{
  const o=await page.evaluate(()=>{const r=s=>document.querySelector(s).getBoundingClientRect();
    return {canvas:r('#replay canvas').top,controls:r('.replay-controls').top,bar:r('.cad-viewer-toolbar').bottom,select:r('.replay-scenario select').right,host:r('.cad-viewer-host').right};});
  if(width<=600)return o.canvas<o.controls&&Math.abs(o.canvas-o.bar)<2&&o.select<=o.host+0.5?null:`phone order: ${JSON.stringify(o)}`;
  return o.controls<o.canvas?null:`wide order: ${JSON.stringify(o)}`;
};
try{
  for(const [width,theme] of [[390,'light'],[1100,'dark']]){
    const context=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:'reduce'});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(page_);await page.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:120000});
    const select=page.getByLabel('Scenario',{exact:true});
    assert.deepEqual(await select.locator('option').allTextContents(),index.scenarios.map(s=>s.label));
    assert.equal(await select.inputValue(),'kerb_drop');
    assert.equal(await page.evaluate(()=>__replay.playback.state().playing),false,'reduced motion: the recording does not start by itself');
    const geometry=await page.evaluate(()=>({page:document.documentElement.scrollWidth<=document.documentElement.clientWidth+1,canvas:document.querySelector('#replay canvas').getBoundingClientRect().height}));
    assert.ok(geometry.page&&geometry.canvas>200,JSON.stringify(geometry));
    // The phone layout (see orderProblem).
    let problem=await orderProblem(page,width);assert.equal(problem,null);
    // Planted controls: the pre-#798 phone layout (the host's own order, controls above the view) and a select wider
    // than the host must each be reported, or the check above proves nothing.
    if(width<=600)for(const [name,css] of [['the old order','.cad-replay-host>*{order:0!important}.cad-replay-host,.cad-replay-host.cad-replay-summarised{grid-template-rows:auto auto minmax(300px,1fr) auto auto!important}'],
      ['an overflowing select','.replay-scenario select{flex:none!important;min-width:520px!important;max-width:none!important}']]){
      const planted=await page.addStyleTag({content:css});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
      problem=await orderProblem(page,width);await planted.evaluate(el=>el.remove());
      assert.ok(problem,`planted control: ${name} passed the phone-order check`);
    }
    // The slider's last step is the recorded end even when the duration is not a whole number of steps. The run's
    // 6.996 s is a whole number of 1 ms steps, so the check gives the slider a 7 ms step, where End stops at 6.993 s.
    const slider=page.getByRole('slider',{name:'Recording time',exact:true});await slider.focus();await slider.press('End');
    assert.equal(await page.evaluate(()=>__replay.playback.state().time),await page.evaluate(()=>__replay.playback.state().duration));
    await slider.press('Home');await page.evaluate(()=>{document.querySelector('.replay-time input').step='0.007';});await slider.press('End');
    const end=await page.evaluate(()=>({...__replay.playback.state(),value:document.querySelector('.replay-time input').value}));
    assert.ok(end.time===end.duration&&+end.value<end.duration,`End stops at ${end.time} of ${end.duration} (slider ${end.value})`);
    await page.evaluate(()=>{document.querySelector('.replay-time input').step='.001';});await slider.press('Home');
    // The summary is the index's own text for this scenario.
    const kerb=index.scenarios[0].summary;let text=await summaryText(page);
    for(const piece of [kerb.verdict.label,...kerb.metrics.map(m=>m.value),kerb.note])assert.ok(text.toLowerCase().includes(piece.toLowerCase()),`summary lacks ${piece}: ${text}`);
    // Poses: every body at t = 2.97 s (recorded frame 90; frames are 33 ms apart) is the recorded kerb_drop frame.
    let read=await seekAndRead(page,2.97);
    read.matrices.forEach((m,i)=>assert.ok(mismatch(m,frameAt('kerb_drop',2.97).poses[i])<1e-6,`kerb_drop body ${i}`));
    // The followed camera travels with the robot's base across the floor (about 2.5 m from 2.97 s to 5.94 s, recorded frames 90 and 180).
    const before=read.target;read=await seekAndRead(page,5.94);
    const travelled=read.target[0]-before[0],base=frameAt('kerb_drop',5.94).poses[0].position[0]-frameAt('kerb_drop',2.97).poses[0].position[0];
    assert.ok(Math.abs(travelled-base)<1e-6&&base>2,`camera followed ${travelled} m, base moved ${base} m`);
    await page.locator('.cad-viewer-viewport').screenshot({path:`${out}/${engine.name()}-${width}-${theme}-kerb_drop.png`});
    // Switch through the visible select; the speed survives the switch.
    await page.getByLabel('Playback speed',{exact:true}).selectOption('2');
    await select.selectOption('push');
    await page.waitForFunction(()=>__replay.scenario==='push'&&!document.querySelector('[aria-label="Scenario"]').disabled);
    assert.equal(await page.evaluate(()=>__replay.playback.state().speed),2);
    read=await seekAndRead(page,2.97);
    const push=frameAt('push',2.97),kerbFrame=frameAt('kerb_drop',2.97);
    read.matrices.forEach((m,i)=>assert.ok(mismatch(m,push.poses[i])<1e-6,`push body ${i}`));
    // Planted control: the same oracle, given the scenario that was left, must fail, or the check above proves nothing.
    assert.ok(mismatch(read.matrices[0],kerbFrame.poses[0])>0.1,'planted control: kerb_drop and push poses at 2.97 s are indistinguishable');
    text=await summaryText(page);
    assert.ok(text.includes(index.scenarios[2].summary.metrics[0].value)&&text.includes('push at 2.0 s'),text);
    assert.ok(!text.includes(kerb.metrics[0].value),'the summary still shows the previous scenario');
    // A run that stays near its start is framed whole: seeking does not move the camera.
    const still=read.camera;read=await seekAndRead(page,5);assert.deepEqual(read.camera,still);
    for(const id of ['side_kerb','landing','push']){
      await select.selectOption(id);await page.waitForFunction(id=>__replay.scenario===id&&!document.querySelector('[aria-label="Scenario"]').disabled,id);
      await seekAndRead(page,{side_kerb:5,landing:0.2,push:2.5}[id]);
      await page.locator('.cad-viewer-viewport').screenshot({path:`${out}/${engine.name()}-${width}-${theme}-${id}.png`});
    }
    cases.push({width,theme,switches:4,oracle:'every body matches its recorded frame; the left scenario does not'});
    const cleanup=await page.evaluate(()=>{__replay.dispose();return document.querySelectorAll('#replay canvas').length;});
    assert.equal(cleanup,0);await context.close();
  }
  // With motion allowed the featured recording plays once ready and loops; Pause holds it. Planted control: the same
  // page under reduced motion with the guard removed from viewer.js must autoplay, or the reduced-motion check is blind.
  {
    const context=await browser.newContext({viewport:{width:1100,height:900},reducedMotion:'no-preference'}),page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(page_);await page.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:120000});
    assert.equal(await page.evaluate(()=>__replay.playback.state().playing),true,'the featured recording starts playing');
    await page.waitForFunction(()=>__replay.playback.state().time>0.1);
    const duration=await page.evaluate(()=>{const {duration}=__replay.playback.state();__replay.playback.seek(duration-0.02);return duration;});
    await page.waitForFunction(d=>{const s=__replay.playback.state();return s.playing&&s.time<d-0.02;},duration);
    assert.equal(await page.evaluate(()=>__replay.playback.state().loop),true);
    await page.getByRole('button',{name:'Pause recording',exact:true}).click();
    const held=await page.evaluate(()=>__replay.playback.state());assert.equal(held.playing,false);
    await page.evaluate(()=>new Promise(resolve=>{let n=0;const tick=()=>++n>3?resolve():requestAnimationFrame(tick);tick();}));
    assert.equal(await page.evaluate(()=>__replay.playback.state().time),held.time,'Pause holds the recording');
    await context.close();
    const planted=await browser.newContext({viewport:{width:1100,height:900},reducedMotion:'reduce'}),control=await planted.newPage();
    await control.route('**/simulation/viewer.js',async route=>{const response=await route.fetch();const body=(await response.text()).replace("&&!matchMedia('(prefers-reduced-motion: reduce)').matches",'');
      assert.ok(body.includes('if(autoplay)'),'planted control: the reduced-motion guard was not found to remove');await route.fulfill({response,body});});
    await control.goto(page_);await control.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:120000});
    assert.equal(await control.evaluate(()=>__replay.playback.state().playing),true,'planted control: without its guard the viewer must autoplay under reduced motion');
    await planted.close();
    cases.push({name:'autoplay and loop with motion; none under reduced motion (planted control autoplays without the guard); Pause holds'});
  }
  // A recording whose bytes differ from the index's SHA-256 is refused when chosen; Retry viewer starts again cleanly.
  const context=await browser.newContext({viewport:{width:1100,height:900},reducedMotion:'reduce'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  const landing=await readFile(new URL('landing.json',example));
  await page.route('**/gyropup-v2/landing.json',route=>route.fulfill({status:200,contentType:'application/json',body:Buffer.concat([landing.subarray(0,-2),Buffer.from(' '),landing.subarray(-2)])}));
  await page.goto(page_);await page.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:120000});
  await page.getByLabel('Scenario',{exact:true}).selectOption('landing');
  await page.waitForFunction(()=>document.querySelector('.cad-viewer-host').dataset.state==='error');
  assert.match(await page.locator('.cad-viewer-message').innerText(),/SHA-256 mismatch/);
  assert.equal(await page.evaluate(()=>__replay.scenario),'kerb_drop','the verified scenario stays on the stage');
  assert.equal(await page.getByLabel('Scenario',{exact:true}).inputValue(),'kerb_drop');
  await page.unroute('**/gyropup-v2/landing.json');await page.getByRole('button',{name:'Retry viewer',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.cad-viewer-host').dataset.state==='ready');
  assert.equal(await page.evaluate(()=>__replay.selectScenario('landing')),true);
  cases.push({name:'tampered recording refused by SHA-256; retry restores the verified example'});await context.close();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({engine:engine.name(),cases},null,1));
}finally{await browser.close();await site.close();}
