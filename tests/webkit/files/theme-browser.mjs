import assert from 'node:assert/strict';

function luminance(color){
  const channels=color.match(/[\d.]+/g).slice(0,3).map(n=>Number(n)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);
  return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;
}
const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};

export async function checkFileThemes({page,site,out,engine,cases}){
  const external=[],request=req=>{if(/^https?:/.test(req.url())&&!req.url().startsWith(site.url+'/'))external.push(req.url());};
  page.on('request',request);
  const appearance=()=>page.evaluate(()=>{
    const viewer=window.__fileViewer,button=viewer.root.querySelector('.file-tools button'),header=viewer.root.querySelector('.file-header'),help=viewer.root.querySelector('.file-title p');
    const css=getComputedStyle(button),surface=getComputedStyle(header),text=getComputedStyle(help);
    return{mode:viewer.root.dataset.fileTheme,button:{color:css.color,background:css.backgroundColor,border:css.borderColor},
      text:surface.color,surface:surface.backgroundColor,muted:text.color,background:viewer.stage.scene.background.getHexString(),
      model:viewer.model.uuid,camera:viewer.stage.camera.position.toArray(),target:viewer.stage.controls.target.toArray(),
      materials:viewer.model.children.map(mesh=>[].concat(mesh.material).map(m=>m.color.getHexString()))};
  });
  const readable=palette=>{
    assert.ok(contrast(palette.button.color,palette.button.background)>=4.5,JSON.stringify(palette));
    assert.ok(contrast(palette.text,palette.surface)>=4.5,JSON.stringify(palette));
    assert.ok(contrast(palette.muted,palette.surface)>=4.5,JSON.stringify(palette));
    assert.ok(contrast(palette.button.border,palette.button.background)>=3,JSON.stringify(palette));
  };
  const retained=({model,camera,target,materials})=>({model,camera,target,materials});
  // Enter without a query override, exactly as links from the Toolkit do. Opposite stored/OS
  // choices catch a page that silently falls back to the reusable viewer's own dark default.
  for(const viewport of [{width:1440,height:900},{width:320,height:568}]){
    await page.setViewportSize(viewport);
    for(const [system,saved,expected] of [['light',null,'light'],['dark',null,'dark'],['light','dark','dark'],['dark','light','light']]){
      await page.emulateMedia({colorScheme:system});
      await page.evaluate(saved=>saved?localStorage.setItem('cad-theme',saved):localStorage.removeItem('cad-theme'),saved);
      await page.goto(site.url+'/kit/files/file-viewer.html?file=/block.stl&back=/parts');
      await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready');
      const before=await appearance();assert.equal(before.mode,expected);readable(before);
      assert.equal(before.surface,expected==='light'?'rgb(255, 255, 255)':'rgb(14, 14, 20)','Standalone page uses the shared application surface');
      const toggle=page.getByRole('button',{name:'Toggle color theme',exact:true});
      assert.ok(await toggle.isVisible());assert.equal(await toggle.getAttribute('aria-pressed'),String(expected==='dark'));
      await toggle.click();const next=expected==='light'?'dark':'light';
      await page.waitForFunction(mode=>window.__fileViewer.root.dataset.fileTheme===mode,next);
      const after=await appearance();readable(after);assert.deepEqual(retained(after),retained(before),'Native theme toggle preserves the loaded scene and camera');
      assert.equal(await toggle.getAttribute('aria-pressed'),String(next==='dark'));
      assert.equal(await page.evaluate(()=>localStorage.getItem('cad-theme')),next===system?null:next);
      const bounds=await toggle.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=viewport.width&&bounds.y+bounds.height<=viewport.height);
      await page.screenshot({path:`${out}/${engine}-shared-${system}-${saved||'system'}-${viewport.width}.png`});
      cases.push({sharedFileTheme:{system,saved,expected,next,viewport,before,after,preservesScene:true}});
    }
  }
  // A real second tab may change the preference while the renderer module is in flight.
  // Mount with that latest choice, then retain the scene on the next storage event.
  const preferences=await page.context().newPage();
  try{
    await preferences.goto(site.url+'/kit/ui/theme.css');
    for(const query of ['', '&theme=light']){
      await page.emulateMedia({colorScheme:'light'});await page.evaluate(()=>localStorage.removeItem('cad-theme'));
      let held,began;const requested=new Promise(resolve=>{began=resolve;}),entry=site.url+'/kit/files/file-viewer.js';
      await page.route(entry,route=>{held=route;began();});
      try{
        await page.goto(site.url+'/kit/files/file-viewer.html?file=/block.stl'+query,{waitUntil:'commit'});
        await requested;
        await preferences.evaluate(()=>localStorage.setItem('cad-theme','dark'));
        await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
        await held.continue();held=null;
        await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready');
        const before=await appearance();readable(before);assert.equal(before.mode,query?'light':'dark');
        assert.equal(before.background,query?'ffffff':'0a0a0f','A delayed mount uses the latest preference unless the URL has an explicit theme');
        await preferences.evaluate(()=>localStorage.setItem('cad-theme','light'));
        await page.waitForFunction(()=>document.documentElement.dataset.theme==='light'&&window.__fileViewer.root.dataset.fileTheme==='light');
        const after=await appearance();readable(after);assert.deepEqual(retained(after),retained(before),'A later cross-tab choice cannot replace geometry, materials or camera');
        cases.push({delayedFileTheme:{query:query||null,before,after,crossTab:true}});
      }finally{if(held)await held.continue();await page.unroute(entry);}
    }
  }finally{await preferences.close();}
  // Real waiting/error surfaces remain readable before geometry exists, including an entry
  // module failure where the import-independent fallback is the only available interface.
  await page.setViewportSize({width:320,height:568});
  for(const theme of ['light','dark']){
    await page.evaluate(theme=>localStorage.setItem('cad-theme',theme),theme);
    let held,began;const requested=new Promise(resolve=>{began=resolve;});
    await page.route(site.url+'/theme-held.stl',route=>{held=route;began();});
    try{
      await page.goto(site.url+'/kit/files/file-viewer.html?file=/theme-held.stl',{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='loading');
      await requested;
      await checkStatus('.file-status','Cancel');
    }finally{if(held)await held.abort();await page.unroute(site.url+'/theme-held.stl');}
    await page.goto(site.url+'/kit/files/file-viewer.html?file=/bad.stl');
    await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='error');
    await checkStatus('.file-status','Retry file');
    await page.route('**/file-viewer.js',route=>route.abort());
    try{
      await page.goto(site.url+'/kit/files/file-viewer.html?file=/block.stl');
      await page.getByRole('button',{name:'Retry viewer',exact:true}).waitFor();
      await checkStatus('.file-bootstrap','Retry viewer');
      await page.screenshot({path:`${out}/${engine}-bootstrap-error-${theme}.png`});
    }finally{await page.unroute('**/file-viewer.js');}
    cases.push({fileThemeStatus:{theme,loading:true,geometryError:true,entryError:true}});
  }
  async function checkStatus(selector,action){
    const status=await page.locator(selector).evaluate(node=>{
      const text=getComputedStyle(node.querySelector('p')),surface=getComputedStyle(node),r=node.getBoundingClientRect();
      return{color:text.color,background:surface.backgroundColor,left:r.left,right:r.right,top:r.top,bottom:r.bottom};
    });
    assert.ok(contrast(status.color,status.background)>=4.5,JSON.stringify(status));
    assert.ok(status.left>=0&&status.right<=320&&status.top>=0&&status.bottom<=568,JSON.stringify(status));
    const button=page.getByRole('button',{name:action,exact:true});assert.ok(await button.isVisible());
    const box=await button.boundingBox();assert.ok(box.x>=0&&box.x+box.width<=320&&box.y+box.height<=568&&box.height>=44,JSON.stringify(box));
    await button.focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');
    const focus=await button.evaluate(el=>({active:document.activeElement===el,outline:getComputedStyle(el).outlineStyle,width:parseFloat(getComputedStyle(el).outlineWidth)}));
    assert.ok(focus.active&&focus.outline!=='none'&&focus.width>=2,JSON.stringify(focus));
  }
  for(const viewport of [{width:1440,height:900},{width:320,height:568},{width:568,height:320}]){
    await page.setViewportSize(viewport);
    for(const [theme,system,expected] of [['light','dark','light'],['dark','light','dark'],['auto','light','light'],['auto','dark','dark']]){
      await page.emulateMedia({colorScheme:system});
      await page.evaluate(expected=>localStorage.setItem('cad-theme',expected==='light'?'dark':'light'),expected);
      await page.goto(site.url+'/kit/files/file-viewer.html?file=/block.stl&back=/parts&theme='+theme);
      await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready');
      const palette=await appearance();assert.equal(palette.mode,expected);
      readable(palette);assert.equal(await page.locator('#page-theme').count(),0,'Explicit query isolates the reusable viewer palette from page preferences');
      assert.equal(await page.getByRole('link',{name:'Back to parts'}).getAttribute('href'),site.url+'/parts');
      assert.equal(await page.getByRole('link',{name:'Download original'}).getAttribute('href'),site.url+'/block.stl');
      const layout=await page.evaluate(()=>({width:document.documentElement.scrollWidth,canvas:document.querySelector('canvas').getBoundingClientRect().height}));
      assert.ok(layout.width<=viewport.width&&layout.canvas>120);
      await page.screenshot({path:`${out}/${engine}-theme-${theme}-${system}-${viewport.width}x${viewport.height}.png`});
      cases.push({theme,system,expected,viewport,palette,layout});
    }
  }
  const before=await appearance();
  await page.evaluate(()=>window.__fileViewer.setTheme({mode:'light',colors:{accent:'#126d58',canvas:'#edf5ee'},fontFamily:'monospace'}));
  const after=await appearance();
  assert.equal(after.background,'edf5ee');assert.equal(after.model,before.model);
  assert.deepEqual(after.camera,before.camera);assert.deepEqual(after.target,before.target);assert.deepEqual(after.materials,before.materials);
  const invalid=await page.evaluate(()=>{try{window.__fileViewer.setTheme({mode:'unknown'});return false;}catch{return true;}});
  assert.ok(invalid);assert.deepEqual(await appearance(),after);
  await page.evaluate(()=>window.__fileViewer.setTheme('auto'));
  for(const colorScheme of ['light','dark','light']){
    await page.emulateMedia({colorScheme});
    await page.waitForFunction(mode=>window.__fileViewer.root.dataset.fileTheme===mode,colorScheme);
    assert.equal((await appearance()).mode,colorScheme);
  }
  await page.evaluate(()=>{window.__retiredRoot=window.__fileViewer.root;window.__fileViewer.dispose();});
  await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await page.evaluate(()=>window.__retiredRoot.dataset.fileTheme),'light','Disposed auto listener cannot mutate its retired viewer');
  assert.deepEqual(external,[]);page.off('request',request);
  cases.push({themeUpdates:'preserve model/materials/camera; reject invalid changes; follow OS; release listener',externalRequests:external});
  // A default page follows live OS changes, including its WebGL background, without a
  // stored override or a synthetic event dispatched by the test.
  await page.evaluate(()=>localStorage.removeItem('cad-theme'));await page.emulateMedia({colorScheme:'light'});
  await page.goto(site.url+'/kit/files/file-viewer.html?file=/block.stl');
  await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready');
  const initial=await appearance();
  for(const mode of ['dark','light']){
    await page.emulateMedia({colorScheme:mode});
    await page.waitForFunction(mode=>window.__fileViewer.root.dataset.fileTheme===mode,mode,{timeout:5000});
    const updated=await appearance();readable(updated);assert.deepEqual(retained(updated),retained(initial));
    assert.equal(updated.background,mode==='light'?'fffbf3':'0a0a0f');
    assert.equal(await page.evaluate(()=>localStorage.getItem('cad-theme')),null);
  }
  cases.push({defaultFileThemeFollowsLiveOS:true});
}
