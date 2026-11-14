/** Real quick-panel gestures and public viewer-consumer contracts. */
import assert from 'node:assert/strict';
import {expect} from '../../../site/npm-context.mjs';

export async function inspectionBrowserChecks({page,baseURL,check,shot,receipt,session,paused,definition}) {
  const root=page.locator('#lab-viewer'),panel=page.locator('#industry-viewer-quick-panel');
  const viewport=root.locator('[data-scada-scroll]');
  const inspect=async id=>{
    await root.locator('[data-scada-picker]').selectOption(id);
    await expect(panel).toBeVisible();
    await expect(panel).toHaveAttribute('data-scada-inspection-equipment',id);
    return panel;
  };
  const camera=()=>viewport.evaluate(el=>({x:Number(el.dataset.cameraX),y:Number(el.dataset.cameraY),zoom:Number(el.dataset.cameraZoom)}));
  const reload=async()=>{
    await page.goto(`${baseURL}/kit/scada/explorer/index.html?scenario=wastewater-digester`);
    await expect(page.locator('#industry-lab')).toHaveAttribute('aria-busy','false');await paused();
  };
  const bounds=async()=>{
    await expect(panel).toHaveAttribute('aria-modal','false');
    assert.equal(await panel.evaluate(el=>el.matches(':popover-open')),true,'Quick controls use the nonmodal top layer');
    assert.equal(await page.evaluate(()=>document.documentElement.style.overflow==='hidden'),false,'Quick controls must not lock document scrolling');
    const box=await panel.boundingBox(),size=page.viewportSize();
    assert.ok(box.x>=0&&box.y>=0&&box.x+box.width<=size.width+1&&box.y+box.height<=size.height+1,JSON.stringify({box,size}));
    assert.ok(box.width<=Math.min(360,size.width-24)+1&&box.height<=Math.min(440,size.height-24)+1,`Quick panel takes over its viewport: ${JSON.stringify({box,size})}`);
    assert.equal(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
    assert.equal(await viewport.evaluate(el=>Boolean(el.closest('[inert]'))),false);
    assert.ok((await panel.locator('[data-scada-popover-close]').boundingBox()).height>=44);
    assert.ok(await panel.locator('.scada-viewer-controls').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=14));
    return box;
  };

  await check('canonical equipment IDs appear in every view and dropdown without persistent selected fills',async()=>{
    const accepted=await session(),time=accepted.state.minutes;
    const expected=new Map(definition.components.map(component=>[component.id,component.label??component.id]));
    const options=await root.locator('[data-scada-picker] option').evaluateAll(nodes=>nodes.map(node=>({id:node.value,label:node.textContent})));
    assert.equal(new Set(options.map(item=>item.id)).size,expected.size);
    assert.equal(options.length,expected.size);
    for(const item of options)assert.equal(item.label,`${item.id} · ${expected.get(item.id)}`);
    for(const view of definition.views){
      await root.locator(`[data-scada-view-choice="${view.id}"]`).click();
      const equipment=await root.locator('[data-scada-equipment]').evaluateAll(nodes=>nodes.map(node=>({id:node.dataset.scadaEquipment,tag:node.querySelector('.scada-viewer-equipment-id')?.textContent,pressed:node.hasAttribute('aria-pressed')})));
      assert.deepEqual(equipment.map(item=>item.id).sort(),view.placements.map(item=>item.component).sort());
      for(const item of equipment){assert.equal(item.tag,item.id);assert.equal(item.pressed,false);assert.ok(expected.has(item.id));}
    }
    await root.locator('[data-scada-view-choice="overview"]').click();
    const node=root.locator('[data-scada-equipment="liftPump"]');
    await page.mouse.move(0,0);
    const color=()=>node.evaluate(el=>({background:getComputedStyle(el).backgroundImage,color:getComputedStyle(el).backgroundColor}));
    const before=await color();await node.click();await expect(panel).toBeVisible();
    await page.keyboard.press('Escape');await expect(panel).not.toBeVisible();await page.mouse.move(0,0);
    assert.deepEqual(await color(),before,'Inspecting equipment must not leave a selected fill');
    await expect(node).toBeFocused();
    // Tab traversal establishes keyboard focus in engines that retain pointer modality after Enter.
    await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');await expect(node).toBeFocused();
    await node.press('Enter');await expect(panel).toBeVisible();await page.keyboard.press('Escape');
    await expect(panel).not.toBeVisible();await expect(node).toBeFocused();
    assert.equal(await node.evaluate(el=>el.matches(':focus-visible')),true,'Keyboard inspection and dismissal retain visible focus');
    await expect(node).not.toHaveAttribute('aria-pressed',/.*/);
    assert.equal(parseFloat(await page.locator('[data-kpi=time]').innerText()),time);
    assert.deepEqual(await session(),accepted);
  });

  await check('quick controls stay compact and nonmodal across phone, short desktop and ultrawide themes',async()=>{
    receipt.quickPanelGeometry=[];
    for(const colorScheme of ['light','dark'])for(const [width,height] of [[320,844],[390,844],[844,390],[1366,768],[3440,1440]]){
      await page.setViewportSize({width,height});await page.emulateMedia({colorScheme});
      await inspect('liftPump');const box=await bounds();
      const controls=await panel.locator('[data-scada-control]').evaluateAll(nodes=>nodes.map(node=>node.dataset.scadaControl));
      const expected=definition.controls.filter(control=>control.component==='liftPump').map(control=>control.id);
      assert.deepEqual(controls.sort(),expected.sort(),'Quick controls are scoped to the exact equipment');
      await expect(panel.locator('.scada-inspection-id')).toHaveText('liftPump');
      await expect(root.locator('[data-scada-equipment="liftPump"]')).toHaveAttribute('aria-expanded','true');
      await shot(`quick-controls-${colorScheme}-${width}x${height}`);
      receipt.quickPanelGeometry.push({colorScheme,width,height,box});
      // The exposed page remains interactive, with no modal backdrop or scroll lock.
      await page.mouse.click(width-4,height-4);await expect(panel).not.toBeVisible();
      const before=parseFloat(await page.locator('[data-kpi=time]').innerText());
      const step=page.locator('[data-action=step]');await step.click();
      await expect(panel).not.toBeVisible();await expect(step).toBeFocused();
      assert.equal(parseFloat(await page.locator('[data-kpi=time]').innerText()),before+1);
      await expect(root.locator('[data-scada-equipment][aria-pressed]')).toHaveCount(0);
    }
  });

  await check('quick controls follow camera movement at screen resolution and target the clicked equipment',async()=>{
    await page.setViewportSize({width:3440,height:1440});await page.emulateMedia({colorScheme:'dark'});
    await root.locator('[data-scada-camera-fit]').click();
    const node=root.locator('[data-scada-equipment="digester"]');await node.click();await expect(panel).toBeVisible();
    const initial=await bounds(),anchor=await node.boundingBox(),initialCamera=await camera();
    await viewport.focus();await viewport.press('ArrowRight');
    await expect.poll(async()=>(await camera()).x).not.toBe(initialCamera.x);
    await expect(panel).toBeVisible();
    await expect.poll(async()=>(await panel.boundingBox()).x).not.toBe(initial.x);
    const moved=await bounds(),movedAnchor=await node.boundingBox();
    assert.ok(Math.abs((moved.x-initial.x)-(movedAnchor.x-anchor.x))<1,'The open panel follows its equipment anchor');
    assert.ok(Math.abs(moved.width-initial.width)<1&&Math.abs(moved.height-initial.height)<1);
    await viewport.press('=');await expect.poll(async()=>(await camera()).zoom).toBeGreaterThan(initialCamera.zoom);
    await expect(panel).toBeVisible();const zoomed=await bounds();
    assert.ok(Math.abs(zoomed.width-initial.width)<1,'Panel text must not scale with the diagram');
    await viewport.press('Home');await expect(viewport).toHaveAttribute('data-camera-fitted','true');await expect(panel).toBeVisible();
    const slider=panel.locator('[data-scada-control="digester-load-control"]'),beforeSlider=await camera();
    await slider.press('End');assert.equal(await slider.inputValue(),'100');assert.deepEqual(await camera(),beforeSlider,'Slider keys must not move the camera');
    // Native pointer activation on another asset swaps command context and heading together.
    const other=root.locator('[data-scada-equipment="liftPump"]');await other.click();
    await expect(panel).toHaveAttribute('data-scada-inspection-equipment','liftPump');
    await expect(panel.locator('[data-scada-control="digester-load-control"]')).toHaveCount(0);
    const load=panel.locator('[data-scada-control="liftPump-load-control"]');await load.press('Home');
    assert.equal(await load.inputValue(),'0');
    const saved=await session();assert.equal(saved.state.components.liftPump.load,0);assert.equal(saved.state.components.digester.load,100);
    // A real drag beginning on equipment pans without opening controls or dispatching a command.
    const before=await session(),box=await other.boundingBox(),start=await camera();
    await page.mouse.move(box.x+box.width/2,box.y+15);await page.mouse.down();
    await page.mouse.move(box.x+box.width/2+65,box.y+45,{steps:8});await page.mouse.up();
    await expect(panel).not.toBeVisible();assert.notEqual((await camera()).x,start.x);
    assert.deepEqual(await session(),before);await root.locator('[data-scada-camera-fit]').click();
  });

  await check('deep settings show the exact equipment equations and preserve canonical identity after edits',async()=>{
    await inspect('liftPump');await panel.locator('[data-scada-details]').click();
    await expect(panel).not.toBeVisible();
    const details=page.locator('#industry-model-dialog');await expect(details).toBeVisible();
    await expect(details.locator('[data-model-equipment]')).toHaveValue('liftPump');
    await expect(details.locator('[data-equation-report]')).toHaveAttribute('data-equipment-id','liftPump');
    await expect(details.locator('[data-scada-dialog-title]')).toContainText('liftPump');
    await expect(details.locator('[data-equation-identity]')).toContainText('Built-in pump');
    await details.locator('[data-model-equations] > summary').click();
    const implementation=details.locator('.lab-equation-source').filter({has:page.locator('summary').filter({hasText:'pressureTarget'})}).first();
    await implementation.locator(':scope > summary').click();
    await expect(implementation.locator('code')).toContainText('pressureTarget(');
    await expect(implementation.locator('code')).toContainText('return');
    await details.locator('[data-model-current-configuration] > summary').click();
    const jsonDisclosure=details.locator('.lab-equation-source').filter({has:page.locator('summary').filter({hasText:'Equipment model JSON'})});
    await jsonDisclosure.locator(':scope > summary').click();
    const config=JSON.parse(await details.locator('[data-equipment-model-json]').innerText());assert.equal(config.model??config.kind,'pump');
    const field=details.locator('[data-parameter]').first(),key=await field.getAttribute('data-parameter');
    const value=Number(await field.inputValue()),max=Number(await field.getAttribute('max')),next=value+1<=max?value+1:value-1;
    await field.fill(String(next));await details.locator('[data-apply-parameters]').click();
    await expect(details.locator('[data-dialog-message=model]')).toContainText('edits applied');
    await expect.poll(async()=>JSON.parse(await details.locator('[data-equipment-model-json]').innerText()).parameters[key]).toBe(next);
    for(const [width,height] of [[3440,1440],[1366,768],[390,844]]){
      await page.setViewportSize({width,height});await implementation.scrollIntoViewIfNeeded();
      await expect(implementation.locator('code')).toBeVisible();
      await shot(`equipment-details-equations-${width}`);
    }
    await page.keyboard.press('Escape');await expect(details).not.toBeVisible();
    await expect(root.locator('[data-scada-equipment="liftPump"]')).toBeFocused();
    const saved=await session();assert.equal(saved.model.components.liftPump.parameters[key],next);
  });

  await check('same-equipment drafts survive ticks while switching equipment replaces the draft and command target',async()=>{
    await page.evaluate(async()=>{
      const [{ScadaViewer},{PlaceholderSystemModel,createPlaceholderAdapter},system,config]=await Promise.all([
        import('/kit/scada/ui/src/index.mjs'),import('/kit/scada/sim/src/index.mjs'),
        fetch('/kit/scada/sim/scenarios/wastewater-digester/system.json').then(response=>response.json()),
        fetch('/kit/scada/sim/scenarios/wastewater-digester/model.json').then(response=>response.json())]);
      const model=new PlaceholderSystemModel(system,config);model.dispatch({action:'setRunning',arguments:{value:false}});
      model.dispatch({action:'setLoad',arguments:{equipment:'liftPump',value:61}});model.dispatch({action:'setLoad',arguments:{equipment:'screen',value:44}});
      const controls=system.controls.map(control=>control.kind==='range'?{...control,kind:'number'}:control);
      const container=document.createElement('div');container.id='inspection-consumer';container.style.cssText='position:fixed;inset:12px;z-index:900;overflow:auto;background:#071322;';document.body.append(container);
      const viewer=new ScadaViewer({definition:system,controls,adapter:createPlaceholderAdapter(model),scope:'inspection-consumer'}).mount(container);
      window.__inspectionConsumer={model,viewer,container};
    });
    try{
      const consumer=page.locator('#inspection-consumer'),quick=consumer.locator('[data-scada-popover]');
      await consumer.locator('[data-scada-picker]').selectOption('liftPump');await expect(quick).toBeVisible();
      const field=quick.locator('[data-scada-control="liftPump-load-control"]');await field.fill('73');
      await page.evaluate(()=>{window.__inspectionDraft=document.querySelector('#inspection-consumer [data-scada-control="liftPump-load-control"]');window.__inspectionConsumer.model.step(1);});
      await expect(field).toHaveValue('73');await expect(field).toBeFocused();
      assert.equal(await field.evaluate(el=>el===window.__inspectionDraft),true);
      // Host-selected equipment may change while a focused draft is still uncommitted.
      await page.evaluate(()=>window.__inspectionConsumer.viewer.select('screen',{open:true}));
      await expect(quick).toHaveAttribute('data-scada-inspection-equipment','screen');
      const target=quick.locator('[data-scada-control="screen-load-control"]');await expect(target).toHaveValue('44');
      assert.equal(await page.evaluate(()=>window.__inspectionDraft.isConnected),false,'A different equipment must not inherit the focused input node');
      await target.fill('37');await target.press('Tab');
      const controls=await page.evaluate(()=>window.__inspectionConsumer.model.getSnapshot().controls);
      assert.equal(controls.screen.load,37);assert.equal(controls.liftPump.load,61);
      await page.keyboard.press('Escape');await expect(quick).not.toBeVisible();
      await expect(consumer.locator('[data-scada-equipment][aria-pressed]')).toHaveCount(0);
    }finally{
      await page.evaluate(()=>{window.__inspectionConsumer?.viewer.destroy();window.__inspectionConsumer?.model.destroy();window.__inspectionConsumer?.container.remove();delete window.__inspectionConsumer;delete window.__inspectionDraft;});
    }
  });

  await check('long canonical identifiers remain readable in portable footers and both inspection levels',async()=>{
    await page.setViewportSize({width:390,height:844});
    const id='V'+'X'.repeat(99);
    await page.evaluate(async id=>{
      const {ScadaViewer}=await import('/kit/scada/ui/src/index.mjs');
      const container=document.createElement('div');container.id='long-id-consumer';document.body.append(container);
      const viewer=new ScadaViewer({scope:'long-id-consumer',equipment:[{id,type:'tank',label:'Tank',bindings:{level:'/level'}}],
        views:[{id:'main',label:'Main',width:400,height:240,placements:[{component:id,x:50,y:50,width:160,height:160}]}],
        adapter:{getSnapshot:()=>({level:20}),subscribe:()=>()=>{}}}).mount(container);
      window.__longIdConsumer={viewer,container};
    },id);
    try{
      const consumer=page.locator('#long-id-consumer');
      const noOverflow=locator=>locator.evaluate(el=>el.scrollWidth<=el.clientWidth+1);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
      const footer=consumer.locator('.scada-viewer-status>span').last();await expect(footer).toContainText(id);assert.equal(await noOverflow(footer),true);
      await expect(consumer.locator('.scada-viewer-equipment-id')).toHaveText(id);
      await expect(consumer.locator('[data-scada-picker] option')).toHaveText(`${id} · Tank`);
      await consumer.locator('[data-scada-inspect]').click();
      const quick=consumer.locator('[data-scada-popover]');await expect(quick).toBeVisible();await expect(quick.locator('.scada-inspection-id')).toHaveText(id);
      assert.equal(await noOverflow(quick),true);assert.ok((await quick.boundingBox()).width<=360);await shot('long-id-quick-controls');
      await quick.locator('[data-scada-details]').click();
      const details=consumer.locator('dialog[open]');await expect(details).toBeVisible();
      const title=details.locator('[data-scada-dialog-title]');await expect(title).toContainText(id);
      assert.equal(await noOverflow(details),true);assert.equal(await noOverflow(title),true);
      const close=details.locator(':scope > header [data-scada-close]'),button=await close.boundingBox(),box=await details.boundingBox();
      assert.ok(button.width>=44&&button.height>=44&&button.x>=box.x&&button.x+button.width<=box.x+box.width);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await shot('long-id-detailed-controls');
      await close.click();await expect(details).not.toBeVisible();
    }finally{
      await page.evaluate(()=>{window.__longIdConsumer?.viewer.destroy();window.__longIdConsumer?.container.remove();delete window.__longIdConsumer;});
    }
  });

  await page.setViewportSize({width:1440,height:1100});await page.emulateMedia({colorScheme:'light'});await reload();
}
