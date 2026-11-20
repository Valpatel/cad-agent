/** Capture the Gyropup replay viewer as the toolkit and home cards' animation and still.
 *
 *     node docs/examples/robot-replay/capture-gyropup.mjs            (CHROMIUM_EXECUTABLE=<chrome> to pick a build)
 *     node docs/examples/robot-replay/capture-gyropup.mjs --check    (the pictures still match their record)
 *
 * Opens the real example page (simulation/examples/gyropup-v2/viewer.html) in Chromium, pauses playback and seeks the
 * recording to fixed recorded times, so every frame is a recorded instant, not wall-clock timing. Each frame is the
 * viewer's own 3D viewport. Pillow (the repository's existing extra) writes a looping WebP and a separate still for
 * reduced motion, Save-Data and readers without script. card.json records the times, the browser, the source hashes
 * and the outputs.
 *
 * Limits: recorded solver output from Gyropup's dated snapshot of a work-in-progress prototype, replayed, not
 * recomputed; the pictures prove nothing about the hardware.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '../../../tests/site/npm-context.mjs';
import {serveWebkit} from '../../../tests/webkit/webkit-server.mjs';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const generator='docs/examples/robot-replay/capture-gyropup.mjs',bundle='software/cadagent/webkit/simulation/examples/gyropup-v2';
const ANIMATION='card.webp',STILL='card-still.webp',RECORD='card.json';
const SCENARIO='kerb_drop',START=1.6,END=4.4,FPS=15,STILL_AT=3.0,SIZE={width:640,height:400},QUALITY=58;
const VIEWPORT={width:1000,height:1000};
const CLOSER=1,LOWER=0.03;   // after Fit: camera this much nearer its target (Fit alone fills the card since #809), both this many metres lower, so the robot
                               // fills the card and its wheels stay in frame after the 50 mm drop
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const sourcePaths=[generator,...['replay.js','viewer.js','scene.js','scenarios.js','viewer.css',`examples/gyropup-v2/viewer.html`,`examples/gyropup-v2/index.json`,`examples/gyropup-v2/robot.json`,`examples/gyropup-v2/robot.bin`,`examples/gyropup-v2/${SCENARIO}.json`].map(p=>'software/cadagent/webkit/simulation/'+p),
  ...['model/stage.js','model/model.js','host/viewer-host.js','host/viewer-host.css','host/stage-controls.js','ui/theme.js','ui/theme.css'].map(p=>'software/cadagent/webkit/'+p)];
const recordPath=path.join(root,bundle,RECORD);

if(process.argv.includes('--check')){
  const record=JSON.parse(await readFile(recordPath,'utf8'));
  assert.equal(record.generator.sha256,hash(await readFile(path.join(root,generator))),'Recapture after the capture script changes');
  for(const [file,expected] of [[record.file,record.sha256],[record.still.file,record.still.sha256]])
    assert.equal(hash(await readFile(path.join(root,bundle,file))),expected,`Changed picture: ${file}`);
  console.log('Gyropup replay card animation and still match their record.');
  process.exit(0);
}

const scratch=await mkdtemp(path.join(tmpdir(),'gyropup-card-'));
const server=await serveWebkit(new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]));
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
try{
  const page=await browser.newPage({viewport:VIEWPORT,deviceScaleFactor:1,colorScheme:'light',reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`${server.url}/kit/simulation/examples/gyropup-v2/viewer.html?scenario=${SCENARIO}`);
  await page.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:120000});
  // Size the 3D viewport to the card's 16:10, then frame the robot as Fit does at the first captured instant.
  await page.evaluate(async({size})=>{
    const stage=document.querySelector('#replay'),viewport=document.querySelector('.cad-viewer-viewport');
    stage.style.height=`${stage.clientHeight+Math.round(viewport.clientWidth*size.height/size.width)-viewport.clientHeight}px`;
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    await document.fonts.ready;
  },{size:SIZE});
  const seek=t=>page.evaluate(async t=>{__replay.playback.pause();__replay.playback.seek(t);const frame=__replay.stage.frames;
    await new Promise(resolve=>{const wait=()=>__replay.stage.frames>frame+1?resolve():requestAnimationFrame(wait);wait();});},t);
  await seek(START);await page.evaluate(k=>{__replay.fit();const {camera,controls}=__replay.stage;camera.position.lerp(controls.target,1-k.closer);camera.position.y-=k.lower;controls.target.y-=k.lower;controls.update?.();},{closer:CLOSER,lower:LOWER});await seek(START);
  const viewport=page.locator('.cad-viewer-viewport'),times=[];
  for(let i=0;START+i/FPS<=END+1e-9;i++)times.push(+(START+i/FPS).toFixed(6));
  const frames=[];
  for(const [i,t] of times.entries()){await seek(t);const file=path.join(scratch,`f${String(i).padStart(3,'0')}.png`);await viewport.screenshot({path:file});frames.push(file);}
  const stillIndex=times.findIndex(t=>Math.abs(t-STILL_AT)<1e-6);assert.ok(stillIndex>=0,'the still is one of the captured instants');
  assert.deepEqual(errors,[],'the viewer raised errors');
  const durations=times.map(()=>Math.round(1000/FPS));durations[0]=700;durations[durations.length-1]=900;   // hold the start and the end
  execFileSync(process.env.PYTHON||'python3',['-I','-c',`
import json, sys
from PIL import Image
spec = json.loads(sys.argv[1])
size = (spec['size']['width'], spec['size']['height'])
ims = [Image.open(f).convert('RGB').resize(size, Image.LANCZOS) for f in spec['frames']]
ims[0].save(spec['out'], save_all=True, append_images=ims[1:], duration=spec['durations'], loop=0, quality=spec['q'], method=6)
ims[spec['still']].save(spec['stillOut'], quality=80, method=6)
`,JSON.stringify({frames,durations,size:SIZE,q:QUALITY,still:stillIndex,out:path.join(root,bundle,ANIMATION),stillOut:path.join(root,bundle,STILL)})]);
  const anim=await readFile(path.join(root,bundle,ANIMATION)),still=await readFile(path.join(root,bundle,STILL));
  const record={schema:'cad-agent.browser-capture/1',
    description:'The Gyropup replay viewer seeking through recorded times of one scenario; light theme, paused between frames',
    file:ANIMATION,scenario:SCENARIO,recorded_times_s:{start:START,end:END,step:+(1/FPS).toFixed(6)},frames:times.length,durations_ms:durations,
    width:SIZE.width,height:SIZE.height,viewport:VIEWPORT,camera_after_fit:{closer:CLOSER,lower_m:LOWER},browser:{engine:'chromium',version:browser.version()},
    generator:{path:generator,sha256:hash(await readFile(path.join(root,generator)))},
    sources:Object.fromEntries(await Promise.all(sourcePaths.map(async p=>[p,hash(await readFile(path.join(root,p)))]))),
    sha256:hash(anim),still:{file:STILL,recorded_time_s:STILL_AT,sha256:hash(still)},
    limits:'Recorded solver output from Gyropup\'s dated snapshot of a work-in-progress prototype, replayed, not recomputed; not a validation of hardware.'};
  await writeFile(recordPath,JSON.stringify(record,null,1)+'\n');
  console.log(`Captured ${times.length} frames: ${ANIMATION} ${anim.length} B, ${STILL} ${still.length} B`);
}finally{await browser.close();await server.close();await rm(scratch,{recursive:true,force:true});}
