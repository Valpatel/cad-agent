/** Real Explorer controls against the shipped /kit asset layout. No model test hooks. */
import assert from 'node:assert/strict';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium, webkit, expect} from '../../../site/npm-context.mjs';
import {PlaceholderSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {serveWebkit} from '../../webkit-server.mjs';

const root=fileURLToPath(new URL('../../../../',import.meta.url));
const output=path.resolve(process.env.TEST_OUTPUT??'/tmp/cad-agent-scada-explorer');
const browserName=process.env.PLAYWRIGHT_BROWSER??'chromium';
const engine=browserName==='webkit'?webkit:chromium;
const launch={headless:true,...(engine===chromium?process.env.PLAYWRIGHT_EXECUTABLE_PATH?
  {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?undefined:'chrome'}:{})};
await mkdir(output,{recursive:true});
const server=await serveWebkit(new Map([['/favicon.ico',(_req,res)=>res.writeHead(204).end()]]));
const baseURL=process.env.SCADA_BASE_URL??server.url;
let browser,context,page;
const checks=[],errors=[],responses=[],screenshots=[];
const wastewaterSystem=JSON.parse(await readFile(new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/wastewater-digester/system.json',import.meta.url),'utf8'));
const observedSnapshot=saved=>{const model=new PlaceholderSystemModel(wastewaterSystem,saved.model);model.importSnapshot(saved);const snapshot=model.getSnapshot();model.destroy();return snapshot;};
const receipt={browser:browserName,baseURL,checks,errors,responses,screenshots,sources:{}};
const check=async(name,fn)=>{await fn();checks.push(name);console.log(`PASS ${name}`);};
const shot=async name=>{const filename=`${browserName}-${name}.png`;await page.screenshot({path:path.join(output,filename),fullPage:await page.locator('dialog[open]').count()===0});screenshots.push(filename);};
const minutes=async()=>parseFloat(await page.locator('[data-kpi="time"]').innerText());
const close=async()=>{await page.locator('dialog[open]').last().locator(':scope > header [data-scada-close]').click();};
const open=async id=>{await page.locator(`[data-scada-open="${id}"]`).first().click();await expect(page.locator(`#industry-${id}-dialog`)).toBeVisible();};
const paused=async()=>{if(await page.locator('#industry-lab').getAttribute('data-running')==='true')await page.locator('[data-action="running"]').click();};
const noHorizontalOverflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
const observerContained=async()=>{
  const bounds=await page.locator('#industry-observer-dialog').boundingBox();
  assert.ok(bounds.y>=0&&bounds.y+bounds.height<=page.viewportSize().height+1,`Observer escapes the window: ${JSON.stringify(bounds)}`);
  const body=page.locator('#industry-observer-dialog > [data-scada-dialog-body]');
  const size=await body.evaluate(element=>({content:element.scrollHeight,height:element.clientHeight}));
  assert.ok(size.content<=size.height+1,`Observer controls overflow their available height: ${JSON.stringify(size)}`);
};
const viewportContract=async selector=>{
  const result=await page.locator(selector).evaluate(element=>({
    overflow:getComputedStyle(element).overflow,scrollLeft:element.scrollLeft,scrollTop:element.scrollTop,
    width:element.clientWidth,height:element.clientHeight,fit:!!element.querySelector('[data-scada-camera-fit]')
  }));
  assert.ok(['hidden','clip'].includes(result.overflow),JSON.stringify(result));
  assert.equal(result.scrollLeft,0);assert.equal(result.scrollTop,0);assert.ok(result.width>100&&result.height>100);assert.equal(result.fit,true);
};
const session=async()=>{
  await open('session');const promise=page.waitForEvent('download');await page.locator('[data-action="export"]').click();
  const download=await promise;const payload=JSON.parse(await readFile(await download.path(),'utf8'));await close();return payload;
};

try{
  browser=await engine.launch(launch);receipt.version=browser.version();
  context=await browser.newContext({viewport:{width:1440,height:1100},colorScheme:'light',acceptDownloads:true});page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.status()>=400)responses.push(`${response.status()} ${response.url()}`);});
  await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=wastewater-digester`);
  await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');
  await check('target-owned wastewater control room opens with three views and sound off',async()=>{
    await expect(page.locator('[data-scenario-title]')).toContainText('Wastewater');
    await expect(page.locator('#lab-viewer [data-scada-view-choice]')).toHaveCount(3);
    await expect(page.locator('[data-sound-label]')).toHaveText('Sound off');
    await paused();await noHorizontalOverflow();await viewportContract('#lab-viewer [data-scada-scroll]');await shot('treatment');
  });
  await check('shared application theme follows system, persists across entry and leaves the session unchanged',async()=>{
    const before=await session();
    await page.evaluate(()=>{window.themeEvents=[];document.addEventListener('cad-themechange',event=>window.themeEvents.push(event.detail.theme));});
    const mode=()=>page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme);
    assert.equal(await mode(),'light');
    assert.match(await page.locator('body').evaluate(element=>getComputedStyle(element).fontFamily),/Inter/);
    await page.emulateMedia({colorScheme:'dark'});await expect.poll(mode).toBe('dark');
    await expect.poll(()=>page.evaluate(()=>window.themeEvents)).toEqual(['dark']);
    await page.locator('.theme-toggle').click();await expect.poll(mode).toBe('light');
    assert.equal(await page.evaluate(()=>localStorage.getItem('cad-theme')),'light');
    await page.emulateMedia({colorScheme:'light'});await page.emulateMedia({colorScheme:'dark'});
    assert.equal(await mode(),'light');assert.deepEqual(await page.evaluate(()=>window.themeEvents),['dark','light']);
    const another=await context.newPage();
    try{
      await another.emulateMedia({colorScheme:'dark'});
      await another.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=winery`);
      await expect(another.locator('#industry-lab')).toHaveAttribute('aria-busy','false');
      assert.equal(await another.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'light');
      await another.reload();await expect(another.locator('#industry-lab')).toHaveAttribute('aria-busy','false');
      assert.equal(await another.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'light');
      await another.locator('.theme-toggle').click();
      await expect.poll(mode).toBe('dark');
      assert.equal(await page.evaluate(()=>localStorage.getItem('cad-theme')),null);
    }finally{await another.close();await page.bringToFront();}
    await page.emulateMedia({colorScheme:'light'});await expect.poll(mode).toBe('light');
    assert.deepEqual(await session(),before);
  });
  await check('equipment inspector actions and on/off labels retain readable contrast in both themes',async()=>{
    receipt.inspectorContrast=[];
    const before=await session();
    for(const colorScheme of ['light','dark']){
      await page.emulateMedia({colorScheme});
      await page.locator('#lab-viewer [data-scada-inspect]').click();
      const dialog=page.locator('#industry-viewer-inspector-dialog');await expect(dialog).toBeVisible();
      const buttons=dialog.locator('.scada-viewer-button:not(:disabled)');
      assert.ok(await buttons.count()>=6);
      await expect(dialog.locator('.scada-viewer-toggle[aria-pressed=true] span')).toContainText('On / open');
      assert.ok(await dialog.locator('.scada-viewer-toggle[aria-pressed=false] span').count()>0);
      for(const button of await buttons.all())for(const state of ['default','hover']){
        if(state==='hover')await button.hover();else await page.mouse.move(0,0);
        const result=await button.evaluate(element=>{
          const rgb=value=>value.match(/[\d.]+/g).slice(0,3).map(Number);
          const luminance=value=>rgb(value).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;}).reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0);
          const background=getComputedStyle(element).backgroundColor,b=luminance(background);
          return [element,...element.querySelectorAll('span')].map(node=>{
            const color=getComputedStyle(node).color,f=luminance(color);
            return {text:node.textContent.trim(),color,background,ratio:(Math.max(f,b)+.05)/(Math.min(f,b)+.05)};
          });
        });
        for(const item of result)assert.ok(item.ratio>=4.5,`${colorScheme} ${state}: ${JSON.stringify(item)}`);
        receipt.inspectorContrast.push({colorScheme,state,readings:result});
      }
      await shot(`equipment-inspector-${colorScheme}`);await close();
    }
    await page.emulateMedia({colorScheme:'light'});assert.deepEqual(await session(),before);
  });
  await check('desktop and ultrawide windows contain the workspace and enlarge fitted art within the host limit',async()=>{
    for(const scenario of ['winery','wastewater-digester'])for(const colorScheme of ['light','dark'])for(const [width,height] of [[3440,1440],[1920,1080],[1366,768]]){
      await page.setViewportSize({width,height});await page.emulateMedia({colorScheme});
      await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=${scenario}`);
      await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
      const viewport=page.locator('#lab-viewer [data-scada-scroll]');
      await viewport.locator('[data-scada-camera-fit]').click();await viewportContract('#lab-viewer [data-scada-scroll]');
      const bounds=await viewport.boundingBox(),fit=await viewport.locator('[data-scada-camera-fit]').boundingBox();
      assert.ok(bounds.width>width*.9,`${scenario}: unused desktop width ${JSON.stringify(bounds)}`);
      assert.ok(bounds.height>height*.35,`${scenario}: controls consume the diagram ${JSON.stringify(bounds)}`);
      assert.ok(bounds.y>=0&&bounds.y+bounds.height<=height,`${scenario}: diagram escapes window`);
      assert.ok(fit.x>=0&&fit.y>=0&&fit.x+fit.width<=width&&fit.y+fit.height<=height,'Fit is outside the window');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),true);
      const zoom=Number(await viewport.getAttribute('data-camera-zoom'));assert.ok(zoom>0&&zoom<=1.5);
      if(width===3440){
        assert.ok(zoom>1,'The explicit host fit policy must use extra room');
        const occupied=await viewport.locator('[data-scada-equipment]').evaluateAll(nodes=>{
          const rects=nodes.map(node=>node.getBoundingClientRect());
          return {span:Math.max(...rects.map(r=>r.right))-Math.min(...rects.map(r=>r.left)),minimumWidth:Math.min(...rects.map(r=>r.width)),rows:new Set(rects.map(r=>Math.round(r.top))).size};
        });
        assert.ok(occupied.span/bounds.width>(scenario==='winery'?.6:.75),`${scenario}: equipment leaves the wide canvas unused ${JSON.stringify(occupied)}`);
        assert.ok(occupied.minimumWidth>290,'Fitted equipment must remain readable');
        assert.equal(occupied.rows,scenario==='winery'?2:1);
      }
      await noHorizontalOverflow();await shot(`${scenario}-${colorScheme}-${width}`);
    }
    await page.setViewportSize({width:1440,height:1100});await page.emulateMedia({colorScheme:'light'});
    await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=wastewater-digester`);
    await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
  });
  await check('tall desktop toolbar stays stable and short landscape retains page scrolling with contained pan/zoom',async()=>{
    await page.setViewportSize({width:1440,height:1600});
    await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=hydroponics-ebb-flow`);
    await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
    await page.locator('#lab-viewer [data-scada-zoom=fit]').click();
    const stable=await page.locator('#lab-viewer [data-scada-zoom=fit]').evaluate(async element=>{
      const boxes=[];for(let i=0;i<12;i++){await new Promise(requestAnimationFrame);const r=element.getBoundingClientRect();boxes.push([r.x,r.y,r.width,r.height]);}return boxes;
    });
    assert.ok(stable.every(box=>box.every((value,index)=>Math.abs(value-stable[0][index])<.5)),'Fitted percentage must not cause toolbar resize feedback');
    await page.setViewportSize({width:844,height:390});
    await viewportContract('#lab-viewer [data-scada-scroll]');await noHorizontalOverflow();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight),true);
    await page.locator('#lab-viewer [data-scada-camera-fit]').click();
    await open('faults');await expect(page.locator('#industry-faults-dialog')).toBeVisible();await close();
    await shot('short-landscape');
    await page.setViewportSize({width:1440,height:1100});await page.emulateMedia({colorScheme:'light'});
    await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=wastewater-digester`);
    await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
  });
  await check('one step and layout switches preserve one shared session',async()=>{
    const before=await minutes();await page.locator('[data-action="step"]').click();assert.equal(await minutes(),before+1);
    await page.locator('#lab-viewer [data-scada-view-choice="sludge-energy"]').click();assert.equal(await minutes(),before+1);
    await expect(page.locator('#lab-viewer [data-scada-equipment="digester"]')).toBeVisible();await shot('sludge-energy');
  });
  await check('generator fault, connected load power and repair use real controls',async()=>{
    await open('faults');await page.locator('[data-fault-equipment]').selectOption('chp');
    await page.locator('[data-experiment="break-generator"]').click();await close();await page.locator('[data-action="step"]').click();
    let saved=await session();assert.equal(saved.state.components.chp.failed,true);assert.equal(observedSnapshot(saved).readings.loads.powerIn,0);
    await expect(page.locator('#lab-viewer [data-scada-equipment="chp"] .scada-viewer-equipment-status')).toContainText(/fault|offline/i);
    await shot('generator-fault');
    await open('faults');await page.locator('[data-fault-equipment]').selectOption('chp');await page.locator('[data-action="repair"]').click();await close();
    await page.locator('[data-action="step"]').click();saved=await session();assert.equal(saved.state.components.chp.failed,false);assert.ok(observedSnapshot(saved).readings.loads.powerIn>0);
  });
  await check('readonly observer receives live ticks and cannot send equipment commands',async()=>{
    await page.locator('[data-action="running"]').click();await open('session');await page.locator('[data-scada-open="observer"]').click();
    await expect(page.locator('[data-scada-viewer]')).toHaveCount(2);
    const observer=page.locator('[data-observer-viewer]');await expect(observer.locator('[data-scada-viewer]')).toHaveAttribute('data-readonly','true');
    const before=await minutes();await page.waitForFunction(before=>parseFloat(document.querySelector('[data-kpi="time"]').textContent)>before,before);
    const sharedTimes=await page.evaluate(()=>['[data-observer-time]','[data-kpi="time"]'].map(selector=>parseFloat(document.querySelector(selector).textContent)));
    assert.equal(sharedTimes[0],sharedTimes[1]);
    await observer.locator('[data-scada-picker]').selectOption('chp');
    const controls=observer.locator('[data-scada-control]');assert.ok(await controls.count()>0);
    for(const control of await controls.all())await expect(control).toBeDisabled();
    await close();await expect(page.locator('#industry-observer-dialog')).toBeVisible();
    await viewportContract('[data-observer-viewer] [data-scada-scroll]');await observerContained();await shot('observer');
    await close();await expect(page.locator('[data-scada-viewer]')).toHaveCount(1);await paused();
    const after=await minutes();await page.locator('[data-action="step"]').click();assert.equal(await minutes(),after+1);
  });
  await check('opt-in sound remains silent while paused and mute is explicit',async()=>{
    await open('sound');await page.locator('[data-action="sound-enabled"]').click();
    await expect(page.locator('[data-action="sound-enabled"]')).toHaveAttribute('aria-pressed','true');
    await expect(page.locator('[data-dialog-message="sound"]')).toContainText('output currently silent');
    await close();await page.locator('[data-action="running"]').click();await open('sound');
    await expect(page.locator('[data-dialog-message="sound"]')).toContainText('Sound active');
    await page.locator('[data-action="sound-enabled"]').click();await expect(page.locator('[data-sound-label]')).toHaveText('Sound off');
    await close();await paused();
  });
  await check('session round trip restores edits and malformed JSON preserves state',async()=>{
    const saved=await session();await page.locator('[data-action="step"]').click();await open('session');
    await page.locator('[data-import-file]').setInputFiles({name:'saved.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(saved))});
    await expect(page.locator('[data-dialog-message="session"]')).toContainText('Saved session restored');assert.equal(await minutes(),saved.state.minutes);
    await page.locator('[data-import-file]').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{"invalid":true}')});
    await expect(page.locator('[data-dialog-message="session"]')).toContainText('not restored');assert.equal(await minutes(),saved.state.minutes);await close();
    assert.deepEqual(await session(),saved);
  });
  await check('mouse zoom, drag, keyboard fit and pinned fit never scroll the canvas',async()=>{
    const viewport=page.locator('#lab-viewer [data-scada-scroll]');await viewport.scrollIntoViewIfNeeded();
    await page.locator('#lab-viewer [data-scada-zoom="fit"]').click();
    const initial=Number(await viewport.getAttribute('data-camera-zoom'));const box=await viewport.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,-250);
    await expect.poll(async()=>Number(await viewport.getAttribute('data-camera-zoom'))).toBeGreaterThan(initial);
    const x=Number(await viewport.getAttribute('data-camera-x'));
    await page.mouse.move(box.x+box.width/2,box.y+box.height-40);await page.mouse.down();await page.mouse.move(box.x+box.width/2+80,box.y+box.height-70,{steps:8});await page.mouse.up();
    assert.notEqual(Number(await viewport.getAttribute('data-camera-x')),x);await viewport.focus();await page.keyboard.press('Home');
    await expect(viewport).toHaveAttribute('data-camera-fitted','true');
    await page.locator('#lab-viewer [data-scada-zoom="in"]').click();await viewport.locator('[data-scada-camera-fit]').click();
    await expect(viewport).toHaveAttribute('data-camera-fitted','true');await viewportContract('#lab-viewer [data-scada-scroll]');await noHorizontalOverflow();
  });
  await check('v2 energy assumptions remain editable after changing industries',async()=>{
    await open('scenarios');await page.locator('[data-scenario-search]').fill('electric batch oven');
    await page.locator('[data-scenario="electric-batch-oven"]').click();await expect(page.locator('[data-scenario-title]')).toContainText('batch');await paused();
    await open('model');await page.locator('[data-model-equipment]').selectOption('oven');
    await page.locator('summary').filter({hasText:'Energy supply & conversion'}).click();
    const field=page.locator('[data-model-editor-form="energy"] [data-editor-field]').first();const value=Number(await field.inputValue());
    const max=Number(await field.getAttribute('max'));const next=value+1<=max?value+1:value-1;
    await field.fill(String(next));await page.locator('[data-model-editor-form="energy"] button[type="submit"]').click();
    await expect(page.locator('[data-dialog-message="model"]')).toContainText('edits applied');await shot('v2-energy-editor');await close();
    assert.equal((await session()).version,2);
  });
  await check('direct v2 readonly capability disables native controls without taking ownership of the model',async()=>{
    const result=await page.evaluate(async()=>{
      const [{CircuitSystemModel,createV2Adapter},{ScadaViewer},definition,configuration]=await Promise.all([
        import('/kit/scada/sim/src/index.mjs'),import('/kit/scada/ui/src/index.mjs'),
        fetch('/kit/scada/sim/scenarios/hydroponics-nft/system.json').then(response=>response.json()),
        fetch('/kit/scada/sim/scenarios/hydroponics-nft/model.json').then(response=>response.json())
      ]);
      const model=new CircuitSystemModel(definition,configuration),container=document.createElement('div');
      const dispatch=model.dispatch.bind(model);let commands=0;
      model.dispatch=command=>{commands++;return dispatch(command);};
      document.body.append(container);model.step(1);
      const adapter=createV2Adapter(model,{readOnly:true}),viewer=new ScadaViewer({definition,adapter,scope:'direct-v2-observer'});
      try{
        const before=JSON.stringify(model.exportSnapshot());viewer.mount(container).select('supplyPump',{open:true});
        const controls=[...container.querySelectorAll('[data-scada-control]')];
        const capability={readOnly:viewer.readOnly,dispatchPresent:Object.hasOwn(adapter,'dispatch'),count:controls.length,disabled:controls.every(control=>control.disabled)};
        for(const control of controls){control.click();control.dispatchEvent(new Event('change',{bubbles:true}));}
        const unchanged=JSON.stringify(model.exportSnapshot())===before;
        model.step(.25);const observed=viewer.snapshot===model.getSnapshot()&&viewer.snapshot.minutes===1.25;
        const last=viewer.snapshot;viewer.destroy();model.step(.25);
        return {...capability,commands,unchanged,observed,detached:viewer.snapshot===last,continued:model.getSnapshot().minutes===1.5};
      }finally{viewer.destroy();model.destroy();container.remove();}
    });
    assert.ok(result.count>=4);assert.deepEqual({...result,count:undefined},{readOnly:true,dispatchPresent:false,count:undefined,disabled:true,commands:0,unchanged:true,observed:true,detached:true,continued:true});
  });
  await check('narrow viewport and reduced motion preserve readable controls and camera recovery',async()=>{
    await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
    await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=wastewater-digester`);await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
    for(const view of ['treatment','sludge-energy','power-control']){
      await page.locator(`#lab-viewer [data-scada-view-choice="${view}"]`).click();
      const viewport=page.locator('#lab-viewer [data-scada-scroll]');await viewport.locator('[data-scada-camera-fit]').click();
      await noHorizontalOverflow();await viewportContract('#lab-viewer [data-scada-scroll]');
    }
    await shot('narrow-power');await open('faults');await noHorizontalOverflow();await shot('narrow-faults');await close();
    await open('session');await page.locator('[data-scada-open="observer"]').click();
    await observerContained();await viewportContract('[data-observer-viewer] [data-scada-scroll]');await noHorizontalOverflow();await shot('narrow-observer');await close();
  });
  await check('no browser runtime errors or failed asset requests',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(responses,[]);});
  receipt.status='passed';
}catch(error){receipt.status='failed';receipt.failure=error.stack;if(page)await shot('failure').catch(()=>{});throw error;}
finally{
  for(const relative of ['explorer/main.mjs','explorer/model-editor.mjs','explorer/styles.css','ui/src/viewer/viewer.mjs','ui/src/viewer/camera.mjs','sim/src/adapter.mjs','sim/src/v2/circuit-system.mjs','sim/scenarios/wastewater-digester/system.json','sim/scenarios/wastewater-digester/model.json']){
    receipt.sources[relative]=createHash('sha256').update(await readFile(path.join(root,'software/cadagent/webkit/scada',relative))).digest('hex');
  }
  for(const relative of ['ui/theme.css','ui/theme.js','vendor/fonts/fonts.css'])receipt.sources[`webkit/${relative}`]=createHash('sha256').update(await readFile(path.join(root,'software/cadagent/webkit',relative))).digest('hex');
  await writeFile(path.join(output,`${browserName}-receipt.json`),`${JSON.stringify(receipt,null,2)}\n`);
  await context?.close();await browser?.close();await server.close();
}
