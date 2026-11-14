/** Real capability cards and their existing viewer/calculator consumers; reuse the suite's error recorder. */
export async function toolkitExampleChecks({open,fail}) {
  const ids=['scada-elements','scada-simulations','models','robot-replay','files','assembly','mechanisms','calculators'];
  for(const width of [320,1366,1920,3440]) for(const color of ['light','dark']) for(const js of [true,false]) {
    const {page,done}=await open('/toolkit',{width,color,js,motion:'reduce'});
    const where=`Toolkit examples @${width} ${color}${js?'':' no-JS'}`;
    try {
      const cards=page.locator('[data-toolkit-capability]');
      const actual=await cards.evaluateAll(nodes=>nodes.map(node=>node.dataset.toolkitCapability));
      if(JSON.stringify(actual)!==JSON.stringify(ids))fail(where,`capability inventory: ${JSON.stringify(actual)}`);
      for(const id of ids) {
        const card=page.locator(`[data-toolkit-capability="${id}"]`),image=card.locator('img'),launch=card.locator('[data-toolkit-launch]');
        await image.scrollIntoViewIfNeeded();
        const handle=await image.elementHandle();
        try {await page.waitForFunction(img=>img.complete&&img.naturalWidth>0,handle);}
        finally {await handle.dispose();}
        const values=await card.evaluate(card=>{
          const image=card.querySelector('img'),launch=card.querySelector('[data-toolkit-launch]'),cover=card.querySelector('.toolkit-image-link');
          const rect=card.getBoundingClientRect(),button=launch.getBoundingClientRect();
          return {src:image.getAttribute('src'),alt:image.alt,href:launch.getAttribute('href'),cover:cover.getAttribute('href'),
            title:card.querySelector('h2')?.textContent,buttonText:launch.textContent,width:rect.width,left:rect.left,right:rect.right,
            buttonHeight:button.height,contentOverflow:card.scrollWidth>card.clientWidth+1};
        });
        if(!values.alt.trim()||!values.title?.trim()||!values.buttonText.trim())fail(where,`${id}: missing descriptive image or launch text`);
        if(!/^\/(?!\/)/.test(values.src)||!/^\/(?!\/)/.test(values.href)||values.cover!==values.href)fail(where,`${id}: non-local or divergent native image/launch link`);
        if(values.left<0||values.right>width+1||values.contentOverflow||values.buttonHeight<44)fail(where,`${id}: clipped card or undersized launch ${JSON.stringify(values)}`);
        if(!await launch.isVisible()||await launch.getAttribute('aria-disabled')==='true')fail(where,`${id}: native launch is not available`);
      }
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))fail(where,'horizontal page overflow');
      if(width>=1920) {
        const row=await page.locator('.toolkit-capabilities').evaluate(grid=>{
          const cards=[...grid.querySelectorAll('[data-toolkit-capability]')].map(card=>card.getBoundingClientRect());
          const first=cards.filter(card=>Math.abs(card.top-cards[0].top)<=1),bounds=grid.getBoundingClientRect();
          return {count:first.length,usage:(Math.max(...first.map(card=>card.right))-Math.min(...first.map(card=>card.left)))/bounds.width};
        });
        if(row.count<3||row.count>5||row.usage<.9)fail(where,`wide overview has tiny cards or unused tracks: ${JSON.stringify(row)}`);
      }
      const roadmap=await page.locator('.toolkit-roadmap').filter({hasText:'Growing the workbench'}).textContent();
      if(!/PCB.*electrical.*harness.*planned/i.test(roadmap))fail(where,'future viewers are not clearly distinguished from working examples');
    } finally {await done();}
  }

  // Follow the actual card links, including catalogue-projected demo URLs: no test-only route substitutes.
  for(const width of [320,1366]) for(const color of ['light','dark']) for(const id of ['models','robot-replay','files','assembly','mechanisms','calculators']) {
    const {page,done}=await open('/toolkit',{width,color,motion:'reduce'});
    const where=`Toolkit launch ${id} @${width} ${color}`;
    try {
      const launch=page.locator(`[data-toolkit-capability="${id}"] [data-toolkit-launch]`),href=await launch.getAttribute('href');
      const destination=new URL(href,page.url());
      await launch.scrollIntoViewIfNeeded();await launch.focus();
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      if(!await launch.evaluate(link=>link===document.activeElement))fail(where,'native launch could not receive keyboard focus');
      // Pages redirects an HTML file to its extensionless public route while preserving its bound input query.
      await Promise.all([page.waitForURL(url=>url.origin===destination.origin&&[destination.pathname,destination.pathname.replace(/\.html$/,'')].includes(url.pathname)&&url.search===destination.search&&url.hash===destination.hash,{waitUntil:'domcontentloaded'}),launch.press('Enter')]);
      if(id==='models') {
        const model=page.locator('cad-model');await model.scrollIntoViewIfNeeded();
        await page.waitForFunction(()=>document.querySelector('cad-model')?.dataset.state==='ready'&&document.querySelector('cad-model').frames>0);
        const before=await model.evaluate(model=>({image:model.snapshot(240,160),parts:model.stats.parts,triangles:model.stats.triangles}));
        if(before.parts<1||before.triangles<1)fail(where,'ready model has no rendered mesh geometry');
        const explode=model.getByRole('button',{name:'Explode',exact:true});await explode.click();
        if(await explode.getAttribute('aria-pressed')!=='true')fail(where,'Explode did not activate');
        const after=await model.evaluate(model=>model.snapshot(240,160));
        if(before.image===after)fail(where,'Explode changed the button but not the rendered geometry');
        await explode.click();
        if(await explode.getAttribute('aria-pressed')!=='false')fail(where,'Explode could not return to the assembly');
      } else if(id==='robot-replay') {
        await page.waitForFunction(()=>document.body.dataset.ready==='1'&&window.__replay?.stage.renderer.info.render.triangles>0);
        const identity=await page.evaluate(async()=>{
          const base=new URL('./examples/two-link-arm/',location.href);
          const bytes=await (await fetch(new URL('recording.json',base))).arrayBuffer(),recording=JSON.parse(new TextDecoder().decode(bytes));
          const receipt=await (await fetch(new URL('receipt.json',base))).json();
          const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
          return {schema:recording.schema,title:recording.title,frames:recording.frames.length,bodyIds:recording.bodies.map(body=>body.id),
            loadedIds:window.__replay.scene.groups.map(group=>group.name),duration:window.__replay.playback.state().duration,
            engine:receipt.engine,verified:hash===receipt.artifacts['recording.json'],sources:receipt.sources,
            status:document.querySelector('#receipt-status').textContent};
        });
        if(identity.schema!=='cad-agent.pose-recording/1'||identity.title!=='Two-link arm · recorded simulation'||identity.frames!==501||identity.duration!==10
          ||JSON.stringify(identity.bodyIds)!==JSON.stringify(['base','upper','forearm'])||JSON.stringify(identity.loadedIds)!==JSON.stringify(identity.bodyIds))fail(where,`wrong default recording or rendered body identity: ${JSON.stringify(identity)}`);
        if(identity.engine?.name!=='MuJoCo'||identity.engine?.version!=='3.3.7'||!identity.verified||!/hash verified/.test(identity.status)
          ||!['docs/examples/robot-replay/produce.py','docs/examples/robot-replay/config.json'].every(name=>/^[0-9a-f]{64}$/.test(identity.sources?.[name])))fail(where,'recording is not bound to its actual solver/source receipt');
        await page.getByRole('button',{name:'Play recording',exact:true}).click();
        await page.waitForFunction(()=>window.__replay.playback.state().time>.1);
        await page.getByRole('button',{name:'Pause recording',exact:true}).click();
        await page.waitForFunction(()=>!window.__replay.playback.state().playing);
        const paused=await page.evaluate(()=>({time:window.__replay.playback.state().time,frame:window.__replay.stage.renderer.info.render.frame}));
        await page.waitForFunction(frame=>window.__replay.stage.renderer.info.render.frame>frame+1,paused.frame);
        if(await page.evaluate(()=>window.__replay.playback.state().time)!==paused.time)fail(where,'paused recording advanced while the stage rendered');
        await page.getByRole('combobox',{name:'Playback speed',exact:true}).selectOption('2');
        if(await page.evaluate(()=>window.__replay.playback.state().speed)!==2)fail(where,'speed control did not update the playback clock');
        const slider=page.getByRole('slider',{name:'Recording time',exact:true});
        await slider.scrollIntoViewIfNeeded();await slider.focus();
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        if(!await slider.evaluate(input=>input===document.activeElement))fail(where,'recording time could not receive keyboard focus');
        await slider.press('Home');await page.waitForFunction(()=>window.__replay.playback.state().time===0);
        const before=await page.evaluate(()=>({matrix:window.__replay.scene.groups.find(group=>group.name==='forearm').matrixWorld.toArray(),frame:window.__replay.stage.renderer.info.render.frame}));
        await page.waitForFunction(frame=>window.__replay.stage.renderer.info.render.frame>frame+1,before.frame);
        const canvas=page.locator('#replay canvas'),image=await canvas.screenshot();
        await slider.scrollIntoViewIfNeeded();await slider.focus();await slider.press('End');
        await page.waitForFunction(()=>window.__replay.playback.state().time===10);
        const after=await page.evaluate(()=>({matrix:window.__replay.scene.groups.find(group=>group.name==='forearm').matrixWorld.toArray(),frame:window.__replay.stage.renderer.info.render.frame}));
        await page.waitForFunction(frame=>window.__replay.stage.renderer.info.render.frame>frame+1,after.frame);
        if(JSON.stringify(after.matrix)===JSON.stringify(before.matrix)||image.equals(await canvas.screenshot()))fail(where,'scrubbing changed time without changing the actual rendered arm');
        const fitted=await page.evaluate(()=>window.__replay.getViewState().camera),viewport=page.locator('.cad-viewer-viewport');
        await viewport.focus();await viewport.press('ArrowRight');
        await page.waitForFunction(before=>JSON.stringify(window.__replay.getViewState().camera)!==JSON.stringify(before),fitted);
        await page.getByRole('button',{name:'Zoom to fit',exact:true}).click();
        await page.waitForFunction(before=>{const camera=window.__replay.getViewState().camera;return ['position','target'].every(key=>camera[key].every((value,i)=>Math.abs(value-before[key][i])<1e-8));},fitted);
      } else if(id==='files') {
        await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready'&&window.__fileViewer.stage.renderer.info.render.triangles>0);
        const before=await page.evaluate(()=>({camera:window.__fileViewer.stage.camera.position.toArray(),source:window.__fileViewer.info.sourceName}));
        if(before.source!=='example.stl')fail(where,`wrong source loaded: ${before.source}`);
        await page.getByRole('button',{name:'Front',exact:true}).click();
        await page.waitForFunction(before=>JSON.stringify(window.__fileViewer.stage.camera.position.toArray())!==JSON.stringify(before),before.camera);
        await page.getByRole('button',{name:'Fit',exact:true}).click();
        const target=await page.getByRole('link',{name:'Download original',exact:true}).getAttribute('href');
        if(new URL(target,page.url()).pathname!=='/kit/host/example.stl')fail(where,'download is not the loaded original');
        if(!await page.getByRole('combobox',{name:'STL units',exact:true}).isVisible())fail(where,'STL units control is missing');
      } else if(id==='assembly') {
        await page.waitForFunction(()=>document.body.dataset.ready==='1'&&window.__viewer?.stage.renderer.info.render.triangles>0);
        const before=await page.evaluate(()=>({parts:window.__viewer.parts.map(p=>p.name).sort(),plate:window.__viewer.parts.find(p=>p.name==='plate').mesh.position.toArray(),revision:window.__guide.guide.snapshot.source_commit}));
        if(JSON.stringify(before.parts)!==JSON.stringify(['base','fastener','lid','plate','rail'])||before.revision!=='1'.repeat(40))fail(where,'synthetic fixture identity or mesh closure changed');
        await page.getByRole('combobox',{name:'Instruction step',exact:true}).selectOption('lid');
        await page.waitForFunction(()=>window.__guide.controller.current==='lid');
        const after=await page.evaluate(()=>window.__viewer.parts.find(p=>p.name==='plate').mesh.position.toArray());
        if(JSON.stringify(after)===JSON.stringify(before.plate))fail(where,'instruction changed without moving the source-bound plate');
        await page.getByRole('button',{name:'Assembled',exact:true}).click();
        if(await page.evaluate(()=>window.__guide.controller.current!==null||Object.values(window.__viewer.getState().offsets_mm).some(v=>v.some(n=>n!==0))))fail(where,'Assembled did not reset the authored motion');
      } else if(id==='mechanisms') {
        const demo=page.locator('cad-fourbar');await demo.scrollIntoViewIfNeeded();
        await page.waitForFunction(()=>document.querySelector('cad-fourbar')?.built&&document.querySelector('cad-fourbar [data-part=crank]'));
        const before=await demo.locator('[data-part=crank]').getAttribute('points');
        const slider=demo.getByRole('slider',{name:/^Crank a/});await slider.scrollIntoViewIfNeeded();await slider.focus();await slider.press('End');
        await page.waitForFunction(()=>document.querySelector('cad-fourbar').state.crank===150);
        if(await demo.locator('[data-out=class]').textContent()!=='Triple rocker'||await demo.locator('[data-part=crank]').getAttribute('points')===before)fail(where,'crank input did not reach the kinematic result and rendered linkage');
        const play=demo.getByRole('button',{name:/^Play/});await play.click();
        const first=await demo.locator('[data-part=crank]').getAttribute('points');
        await page.waitForFunction(first=>document.querySelector('cad-fourbar [data-part=crank]').getAttribute('points')!==first,first);
        await demo.getByRole('button',{name:/^Pause/}).click();
        if(await demo.locator('.fb-play').textContent()!=='Play')fail(where,'linkage cannot be paused');
      } else {
        const demo=page.locator('cad-cantilever');await demo.scrollIntoViewIfNeeded();
        await page.waitForFunction(()=>document.querySelector('cad-cantilever')?.built&&document.querySelector('cad-cantilever [data-part=beam]'));
        const before={beam:await demo.locator('[data-part=beam]').getAttribute('points'),force:await demo.locator('b[data-out=force]').textContent()};
        const slider=demo.getByRole('slider',{name:/^Root thickness/});await slider.scrollIntoViewIfNeeded();await slider.focus();await slider.press('End');
        await page.waitForFunction(()=>document.querySelector('cad-cantilever').state.thickness===4);
        if(await demo.locator('[data-part=beam]').getAttribute('points')===before.beam||await demo.locator('b[data-out=force]').textContent()===before.force)fail(where,'thickness input did not update both geometry and equation result');
        if(!/not proof of strength/i.test(await demo.locator('.cc-note').textContent()))fail(where,'calculator assumptions are missing');
      }
    } finally {await done();}
  }
}
