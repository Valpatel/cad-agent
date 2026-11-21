/** Real FEA surface, pointer hover and shared-palette contrast; synthetic values are not physical results. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,webkit} from '../site/npm-context.mjs';
import {bounded} from '../site/navigation.mjs';
import {serveWebkit} from './webkit-server.mjs';

const pack=(dtype,data)=>({dtype,b64:Buffer.from(new ({float32:Float32Array,uint32:Uint32Array,uint8:Uint8Array}[dtype])(data).buffer).toString('base64')});
const fixture={format:'cadagent-fea-viewer',name:'Theme fixture',size_mm:100,bounds_mm:[[0,0,0],[100,20,10]],
  material:{name:'Illustrative',strength_mpa:10},result:{safety_factor:2},failure:{design_stress_mpa:5,first_failure_factor:2,max_load_factor:3},
  surface:{vertices:3,triangles:1,positions:pack('float32',[0,0,0,100,0,0,0,20,10]),index:pack('uint32',[0,1,2]),
    displacement:pack('float32',[0,0,0,0,0,-.1,0,0,-.05]),von_mises:pack('float32',[5,5,5]),tri_von_mises:pack('float32',[5]),flags:pack('uint8',[1,0,0])},
  hot_spots:[{position:[20,5,2.5],normal:[0,0,1],stress_mpa:5,of_strength:.5,fails_at:2,hint:'Illustrative sample'}],
  assumptions:'Synthetic rendering fixture, not a physical result.'};
function contrast(foreground,background){
  const rgb=c=>c.match(/[\d.]+/g).map(Number),fg=rgb(foreground),bg=rgb(background),alpha=bg[3]??1;
  const luminance=channels=>channels.slice(0,3).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((s,n,i)=>s+n*[.2126,.7152,.0722][i],0);
  const a=luminance(fg),b=luminance(bg.slice(0,3).map((n,i)=>n*alpha+[10,10,15][i]*(1-alpha)));
  return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
async function rethrowWithScreenshot(original, label, takeScreenshot) {
  try {
    await takeScreenshot();
  } catch (captureError) {
    throw new AggregateError([original, captureError], `FEA ${label} failed and its screenshot could not be saved`, { cause: original });
  }
  throw original;
}

// Stream milestones from Node so a stuck renderer or a cancelled job still leaves a partial log.
const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
function progress(theme, step, detail) {
  console.log('FEA progress', JSON.stringify({ engine: engine.name(), theme, step, detail }));
}

const readyMessage = 'FEA fixture: body data-ready set';
const errorPrefix = 'FEA fixture initialization error: ';
const timeoutMs = 30_000;

async function openFixture(page, siteUrl, file, mark) {
  const url = new URL(file, siteUrl).href;
  // Buffer an early result across navigation. A failed navigation cannot leave a rejected promise behind.
  const startup = Promise.withResolvers();
  page.on('request', request => {
    if (request.url() === url) mark('fixture requested', file);
  });
  page.on('response', response => {
    if (response.url() === url) mark('fixture response', response.status());
  });
  page.on('requestfinished', request => {
    if (request.url() === url) mark('fixture body received', file);
  });
  page.on('requestfailed', request => {
    if (request.url() === url) mark('fixture request failed', request.failure()?.errorText);
  });
  page.on('pageerror', error => mark('page error', error.message));
  page.once('crash', () => {
    mark('page crashed');
    startup.resolve('FEA fixture page crashed during initialization');
  });
  page.once('close', () => startup.resolve('FEA fixture page closed during initialization'));
  page.on('console', message => {
    if (message.type() !== 'debug') return;
    const text = message.text();
    if (text === readyMessage) {
      mark('ready attribute set');
      startup.resolve();
    } else if (text.startsWith(errorPrefix)) {
      startup.resolve(text.slice(errorPrefix.length));
    }
  });
  await page.addInitScript(({ readyMessage, errorPrefix }) => {
    const observer = new MutationObserver(() => {
      const failure = document.querySelector('#stage-overlay .hud-card .hud-note')?.textContent;
      if (failure?.startsWith('Could not load ')) console.debug(errorPrefix + failure);
      else if (document.body?.dataset.ready === '1') console.debug(readyMessage);
      else return;
      observer.disconnect();
    });
    observer.observe(document, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['data-ready'] });
  }, { readyMessage, errorPrefix });
  mark('navigating', file);
  await page.goto(siteUrl+'/kit/fea/fea.html?case='+file+'&nav=0&title=FEA%20fixture');
  mark('waiting for ready');
  const failure = await bounded(() => startup.promise, timeoutMs, 'FEA initialization');
  if (failure) throw new Error(failure);
  mark('ready');
}

async function fitAndWaitForDraw(page, mark) {
  mark('fitting top view');
  // A ready flag means initialization finished. Require a new renderer.render() after the camera fit.
  await bounded(() => page.evaluate(() => {
    const { stage, fit } = window.__fea;
    const before = stage.draws;
    fit('top');
    return new Promise(resolve => {
      function checkDraw() {
        if (stage.draws > before) resolve();
        else requestAnimationFrame(checkDraw);
      }
      checkDraw();
    });
  }), timeoutMs, 'post-fit FEA surface draw');
  mark('top view drawn');
}

async function freezeFrames(page) {
  // Playwright's injected polling script can bypass its simulated clock. Withhold native RAF before page code loads.
  await page.addInitScript(() => {
    const request = window.requestAnimationFrame.bind(window);
    const cancel = window.cancelAnimationFrame.bind(window);
    const callbacks = new Map();
    let id = 0;
    window.requestAnimationFrame = callback => {
      callbacks.set(++id, callback);
      return id;
    };
    window.cancelAnimationFrame = handle => callbacks.delete(handle);
    window.resumeFeaFrames = () => {
      window.requestAnimationFrame = request;
      window.cancelAnimationFrame = cancel;
      for (const callback of callbacks.values()) request(callback);
      callbacks.clear();
      return new Promise(resolve => request(resolve));
    };
  });
}

async function checkStalledInitialization(browser, siteUrl) {
  const page = await browser.newPage();
  const events = [];
  try {
    await freezeFrames(page);
    await assert.rejects(openFixture(page, siteUrl, '/stalled-fixture.json', (step, detail) => events.push([step, detail])),
      /FEA initialization exceeded 30000 ms/);
    assert.ok(events.some(([step, status]) => step === 'fixture response' && status === 200));
    assert.ok(!events.some(([step]) => step === 'fixture body received' || step === 'ready attribute set'));
  } finally {
    await page.close();
  }
}

async function checkFailedInitialization(browser, siteUrl) {
  const page = await browser.newPage();
  const events = [];
  const captureError = new Error('planted screenshot failure');
  try {
    await freezeFrames(page);
    await assert.rejects(async () => {
      try {
        await openFixture(page, siteUrl, '/missing-fixture.json', (step, detail) => events.push([step, detail]));
      } catch (error) {
        await rethrowWithScreenshot(error, 'missing fixture', async () => { throw captureError; });
      }
    }, error => error instanceof AggregateError && error.cause === error.errors[0] &&
      error.cause.message.includes('Could not load /missing-fixture.json: 404') && error.errors[1] === captureError);
    assert.ok(events.some(([step, file]) => step === 'fixture requested' && file === '/missing-fixture.json'));
    assert.ok(events.some(([step, status]) => step === 'fixture response' && status === 404));
    assert.ok(!events.some(([step]) => step === 'ready attribute set'));
  } finally {
    await page.close();
  }
}

async function checkReadyBeforeFrame(browser, siteUrl, releaseBody) {
  const page = await browser.newPage();
  const file = '/held-fixture.json', url = siteUrl + file;
  const events = [];
  try {
    await freezeFrames(page);
    const headers = page.waitForResponse(url, { timeout: timeoutMs });
    const waiting = Promise.withResolvers();
    await Promise.all([
      openFixture(page, siteUrl, file, (step, detail) => {
        events.push([step, detail]);
        if (step === 'waiting for ready') waiting.resolve();
      }),
      (async () => {
        assert.equal((await headers).status(), 200);
        await bounded(() => waiting.promise, timeoutMs, 'control to begin waiting on the held fixture');
        assert.equal(await page.evaluate(() => document.body.dataset.ready), undefined);
        assert.ok(!events.some(([step]) => step === 'fixture body received'), 'the server is still holding the body');
        assert.ok(!events.some(([step]) => step === 'ready attribute set'));
        const body = page.waitForEvent('requestfinished', { predicate: request => request.url() === url, timeout: timeoutMs });
        releaseBody();
        await body;
      })(),
    ]);
    assert.ok(events.some(([step, seen]) => step === 'fixture body received' && seen === file));
    assert.ok(events.some(([step]) => step === 'ready attribute set'));
    const draws = () => page.evaluate(() => window.__fea.stage.draws);
    assert.equal(await page.evaluate(() => window.__fea.stage.frames), 0, 'startup must finish before the first frame');
    await assert.rejects(fitAndWaitForDraw(page, () => {}), /post-fit FEA surface draw exceeded 30000 ms/);
    assert.equal(await draws(), 0, 'a ready flag cannot pass the surface check with frames withheld');
    await bounded(() => page.evaluate(() => window.resumeFeaFrames()), timeoutMs, 'control stage to resume frames');
    assert.ok(await draws() > 0, 'the mounted stage must draw after frames resume');
  } finally {
    releaseBody();
    await page.close();
  }
}

progress(null, 'starting fixture server');
const heldBody = Promise.withResolvers();
const site=await serveWebkit(new Map([
  ['/fixture.json',(_req,res)=>res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(fixture))],
  ['/stalled-fixture.json', (_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.write('{');
  }],
  ['/held-fixture.json', async (_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    const body = JSON.stringify(fixture);
    res.write(body.slice(0, 1));
    await heldBody.promise;
    res.end(body.slice(1));
  }],
  ['/favicon.ico',(_req,res)=>res.writeHead(204).end()],
]));
progress(null, 'launching browser');
const browser=await engine.launch(engine===chromium?{headless:true,channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?'chromium':'chrome',executablePath:process.env.CHROMIUM_EXECUTABLE}:{headless:true});
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-fea';await mkdir(out,{recursive:true});
const cases=[],errors=[];
try{
  const primary = new Error('planted FEA failure'), secondary = new Error('planted capture failure');
  await assert.rejects(rethrowWithScreenshot(primary, 'control', async () => {}), error => error === primary);
  await assert.rejects(rethrowWithScreenshot(primary, 'control', async () => { throw secondary; }),
    error => error instanceof AggregateError && error.cause === primary &&
      error.errors[0] === primary && error.errors[1] === secondary);
  cases.push({ failureEvidence: 'original preserved with a successful or failed screenshot' });
  for(const theme of ['light','dark']){
    const mark = (step, detail) => progress(theme, step, detail);
    mark('creating context');
    const context=await browser.newContext({viewport:{width:1366,height:900},colorScheme:theme});
    mark('creating page');
    const page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    try{
      await openFixture(page, site.url, '/fixture.json', mark);
      await fitAndWaitForDraw(page, mark);
      // Finish a real paint before the native pointer enters the projected surface.
      mark('capturing ready surface');
      await bounded(() => page.screenshot({ path: `${out}/${engine.name()}-${theme}-ready.png`, timeout: timeoutMs }), timeoutMs, 'FEA ready screenshot');
      const hover=async()=>{
        const point=await page.evaluate(async()=>{
          const THREE=await import('/kit/vendor/three/three.module.min.js'),v=window.__fea;v.stage.root.updateMatrixWorld(true);v.stage.camera.updateMatrixWorld(true);
          let mesh;v.stage.root.traverse(node=>{if(node.isMesh&&node.material.vertexColors)mesh=node;});
          const positions=mesh.geometry.getAttribute('position'),center=new THREE.Vector3();
          for(let i=0;i<3;i++)center.add(new THREE.Vector3().fromBufferAttribute(positions,i));
          center.divideScalar(3);mesh.localToWorld(center);center.project(v.stage.camera);
          const canvas=v.stage.renderer.domElement,r=canvas.getBoundingClientRect(),x=r.left+(center.x+1)*r.width/2,y=r.top+(1-center.y)*r.height/2;
          return{x,y,canvasReceivesPointer:document.elementFromPoint(x,y)===canvas};
        });
        assert.ok(point.canvasReceivesPointer,JSON.stringify(point));
        await page.mouse.move(0,0);await page.mouse.move(point.x,point.y,{steps:3});
        await page.locator('.fea-tip').waitFor({state:'visible'});return point;
      };
      const paint=async(selector,surface=selector)=>page.evaluate(({selector,surface})=>{
        const el=document.querySelector(selector),background=document.querySelector(surface),style=getComputedStyle(el);
        return{text:el.textContent,color:style.color,background:getComputedStyle(background).backgroundColor,visible:el.checkVisibility()};
      },{selector,surface});
      const readable=sample=>{assert.ok(sample.visible,JSON.stringify(sample));assert.ok(contrast(sample.color,sample.background)>=4.5,JSON.stringify(sample));};
      const header=await paint('#topbar h1','#topbar'),panel=await paint('#panel');readable(header);
      assert.equal(panel.background,theme==='light'?'rgb(255, 255, 255)':'rgb(14, 14, 20)');
      for(const state of ['design','overload']){
        mark('checking surface', state);
        if(state==='overload'){
          await page.getByRole('button',{name:'Max',exact:true}).click();
          await page.waitForFunction(()=>document.querySelector('.fea-status').classList.contains('over'));
        }
        const point=await hover();
        if(state==='overload'){await page.mouse.click(point.x,point.y);await page.locator('.hud-readouts .r.fail b').first().waitFor();}
        const tip=await paint('.fea-tip'),bold=await paint('.fea-tip b','.fea-tip');
        const marker=await paint('.fea-label'),listMarker=await paint('.fea-spot .n');
        const readout=await paint('.hud-readouts .r.'+(state==='design'?'ok':'fail')+' b','#panel');
        for(const sample of [tip,bold,marker,listMarker,readout])readable(sample);
        assert.match(tip.text,state==='design'?/5\.0.*MPa/:/15\.0.*MPa/);
        await page.screenshot({path:out+'/'+engine.name()+'-'+theme+'-'+state+'.png'});
        cases.push({theme,state,point,header,tip,bold,marker,listMarker,readout});
        if(theme==='light'&&state==='design'){
          await page.locator('.fea-tip').evaluate(el=>{el.style.backgroundColor='#11121a';el.style.color='#4a5172';});
          const defective=await paint('.fea-tip');assert.ok(contrast(defective.color,defective.background)<4.5,'Original mixed-palette tooltip must fail the measured oracle');
          await page.locator('.fea-tip').evaluate(el=>{el.style.removeProperty('background-color');el.style.removeProperty('color');});
          cases.push({rejectedMixedPaletteTooltip:defective});
        }
      }
    } catch (error) {
      const label = `${engine.name()} ${theme}`;
      // A slow or cancelled diagnostic capture must not hide the first failing assertion or browser action.
      console.error(`FEA ${label} failed`, error);
      await rethrowWithScreenshot(error, label, () => bounded(
        () => page.screenshot({ path: `${out}/${engine.name()}-${theme}-failure.png`, timeout: timeoutMs }), timeoutMs, 'FEA failure screenshot'));
    }
    finally{
      mark('closing context');
      await context.close();
    }
  }
  assert.deepEqual(errors,[]);
  progress(null, 'checking stalled initialization and withheld surface draw');
  await Promise.all([
    checkStalledInitialization(browser, site.url),
    checkReadyBeforeFrame(browser, site.url, heldBody.resolve),
  ]);
  cases.push({ stalledInitialization: 'an unfinished fixture body fails at the 30-second Node deadline' });
  cases.push({ deferredFrame: 'startup completes without frames, and a missing post-fit draw fails at the 30-second Node deadline' });
  progress(null, 'checking failed initialization');
  await checkFailedInitialization(browser, site.url);
  cases.push({ failedInitialization: 'actual missing fixture retained before screenshot error' });
  await writeFile(out+'/'+engine.name()+'-report.json',JSON.stringify({passed:true,browser:await browser.version(),cases,errors},null,2));
  console.log(JSON.stringify({passed:true,engine:engine.name(),cases:cases.length,out}));
}finally{
  progress(null, 'closing browser');
  try { await browser.close(); } finally {
    progress(null, 'closing fixture server');
    await site.close();
  }
}
