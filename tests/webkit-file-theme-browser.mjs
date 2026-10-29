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
  for(const viewport of [{width:1440,height:900},{width:320,height:568},{width:568,height:320}]){
    await page.setViewportSize(viewport);
    for(const theme of ['light','dark']){
      await page.goto(site.url+'/kit/file-viewer.html?file=/block.stl&back=/parts&theme='+theme);
      await page.waitForFunction(()=>window.__fileViewer?.root.dataset.state==='ready');
      const palette=await appearance();assert.equal(palette.mode,theme);
      assert.ok(contrast(palette.button.color,palette.button.background)>=4.5);
      assert.ok(contrast(palette.text,palette.surface)>=4.5);
      assert.ok(contrast(palette.muted,palette.surface)>=4.5);
      assert.ok(contrast(palette.button.border,palette.button.background)>=3,JSON.stringify(palette));
      assert.equal(await page.getByRole('link',{name:'Back to parts'}).getAttribute('href'),site.url+'/parts');
      assert.equal(await page.getByRole('link',{name:'Download original'}).getAttribute('href'),site.url+'/block.stl');
      const layout=await page.evaluate(()=>({width:document.documentElement.scrollWidth,canvas:document.querySelector('canvas').getBoundingClientRect().height}));
      assert.ok(layout.width<=viewport.width&&layout.canvas>120);
      await page.screenshot({path:`${out}/${engine}-theme-${theme}-${viewport.width}x${viewport.height}.png`});
      cases.push({theme,viewport,palette,layout});
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
}
