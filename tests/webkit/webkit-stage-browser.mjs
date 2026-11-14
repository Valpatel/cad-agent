/** Actual shared-stage pixels, with an independent projected-line oracle and a filled-floor negative control. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium, webkit } from '../site/npm-context.mjs';
import { serveWebkit } from './webkit-server.mjs';

const html = `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shared stage grid regression</title><style>body{margin:0;background:#0b1018}#stage{width:100vw;height:100vh}</style>
<script type="importmap">{"imports":{"three":"/kit/vendor/three/three.module.min.js","three/addons/":"/kit/vendor/three/addons/"}}</script>
<div id="stage"></div><script type="module">
import * as THREE from 'three';import {createStage} from '/kit/stage.js';
window.THREE=THREE;window.height=.024;
window.stage=createStage(document.querySelector('#stage'),{height,screenshots:true});
window.model=new THREE.Mesh(new THREE.BoxGeometry(.01,.03,.02),new THREE.MeshStandardMaterial({color:'#4bb9cc'}));
model.position.y=.015;model.castShadow=true;model.receiveShadow=true;stage.root.add(model);
window.grid=stage.scene.getObjectByName('stage-grid')||stage.scene.children.find(o=>o.isGridHelper);
window.draw=()=>{stage.controls.update();stage.renderer.render(stage.scene,stage.camera);};
window.pixels=()=>{const gl=stage.renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
const data=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);return data;};
window.isolate=object=>{stage.scene.background=null;for(const child of stage.scene.children)child.visible=child===object;draw();};
window.restore=()=>{for(const child of stage.scene.children)child.visible=true;draw();};
window.ready=true;
</script></html>`;
const site = await serveWebkit(new Map([
  ['/', (_, res) => res.writeHead(200, {'Content-Type':'text/html'}).end(html)],
  ['/favicon.ico', (_, res) => res.writeHead(204).end()],
]));
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-stage-grid';
await mkdir(out, {recursive:true});
const errors = [], cases = [];
let browser;

// Fixed fixture geometry, not the renderer's grid buffers or shader. Clip each mathematical line in homogeneous
// coordinates, project it to the framebuffer, then allow a 2.25 px AA band. A filled triangle cannot pass this oracle.
async function gridPixels(page) {
  return page.evaluate(() => {
    draw();
    const gl=stage.renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
    const matrix=new THREE.Matrix4().multiplyMatrices(stage.camera.projectionMatrix,stage.camera.matrixWorldInverse);
    const mask=new Uint8Array(w*h), radius=2.25;
    const clip=(a,b)=>{
      let lo=0,hi=1;
      for(const axis of ['x','y','z'])for(const sign of [-1,1]){
        const da=a.w+sign*a[axis],db=b.w+sign*b[axis];
        if(da<0&&db<0)return null;
        if((da<0)!==(db<0)){const t=da/(da-db);if(da<0)lo=Math.max(lo,t);else hi=Math.min(hi,t);}
      }
      if(lo>hi)return null;
      const p=a.clone().lerp(b,lo),q=a.clone().lerp(b,hi);
      return [[(p.x/p.w+1)*w/2,(p.y/p.w+1)*h/2],[(q.x/q.w+1)*w/2,(q.y/q.w+1)*h/2]];
    };
    const half=10*height,y=.0005*height;
    for(let i=0;i<=52;i++)for(const axis of [0,1]){
      const at=-half+i*(2*half/52);
      const a=new THREE.Vector4(axis?at:-half,y,axis?-half:at,1).applyMatrix4(matrix);
      const b=new THREE.Vector4(axis?at:half,y,axis?half:at,1).applyMatrix4(matrix);
      const segment=clip(a,b);if(!segment)continue;
      const [[ax,ay],[bx,by]]=segment,dx=bx-ax,dy=by-ay,len=dx*dx+dy*dy;
      for(let py=Math.max(0,Math.floor(Math.min(ay,by)-radius));py<Math.min(h,Math.ceil(Math.max(ay,by)+radius));py++)
        for(let px=Math.max(0,Math.floor(Math.min(ax,bx)-radius));px<Math.min(w,Math.ceil(Math.max(ax,bx)+radius));px++){
          const t=len?Math.max(0,Math.min(1,((px+.5-ax)*dx+(py+.5-ay)*dy)/len)):0;
          if(Math.hypot(px+.5-ax-t*dx,py+.5-ay-t*dy)<=radius)mask[py*w+px]=1;
        }
    }
    const data=pixels(),rgbSum=[0,0,0];let painted=0,outside=0,alphaSum=0;
    for(let i=0;i<w*h;i++)if(data[4*i+3]>2){painted++;alphaSum+=data[4*i+3];if(!mask[i])outside++;for(let c=0;c<3;c++)rgbSum[c]+=data[4*i+c];}
    return {painted,outside,alphaSum,rgbSum,width:w,height:h,near:stage.camera.near,far:stage.camera.far,
      webglVersion:gl.getParameter(gl.VERSION)};
  });
}
function assertGrid(sample) {
  assert.ok(sample.painted>100,`The grid must remain visible: ${JSON.stringify(sample)}`);
  assert.ok(sample.outside<=8,`Grid filled pixels outside projected line bands: ${JSON.stringify(sample)}`);
}

try {
  browser = await engine.launch(engine===chromium
    ? {headless:true,...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE}
      : {channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?undefined:'chrome'})}
    : {headless:true});
  const context=await browser.newContext({deviceScaleFactor:1,reducedMotion:'reduce'});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  for(const [width,height] of [[404,430],[1100,800],[390,844],[844,390]]){
    await page.setViewportSize({width,height});await page.goto(site.url);await page.waitForFunction(()=>window.ready);
    for(const theme of ['dark','light']){
      await page.evaluate(theme=>{
        restore();stage.frame(height);
        stage.setPalette(theme==='dark'?{accent:'#00f0ff',grid:'#0e7490',glow:'#00f0ff',background:'#0b1018'}
          :{accent:'#006e7a',grid:'#477984',glow:'#7cbdc6',background:'#f4f3ed'});
        draw();
      },theme);
      await page.screenshot({path:`${out}/${engine.name()}-${width}x${height}-${theme}.png`});
      const shadow=await page.evaluate(()=>{
        const before=pixels(),ground=stage.scene.children.find(o=>o.material?.isShadowMaterial);
        ground.visible=false;draw();const after=pixels();ground.visible=true;draw();
        let changed=0;for(let i=0;i<before.length;i+=4)if(Math.abs(before[i]-after[i])+Math.abs(before[i+1]-after[i+1])+Math.abs(before[i+2]-after[i+2])>5)changed++;
        return {changed,castShadow:model.castShadow,receiveShadow:ground.receiveShadow};
      });
      assert.ok(shadow.changed>20,'The model still casts a visible floor shadow');
      assert.ok(shadow.castShadow&&shadow.receiveShadow);
      await page.evaluate(()=>isolate(grid));
      const sample=await gridPixels(page);assertGrid(sample);
      if(theme==='light')assert.notDeepEqual(sample.rgbSum,cases.at(-1).grid.rgbSum,'Palette must recolor actual grid pixels');
      assert.equal(sample.near,.024*.02,'The fix must preserve the small original near plane');
      await page.evaluate(()=>stage.setSceneLight(0,true));const dimmed=await gridPixels(page);assertGrid(dimmed);
      assert.ok(dimmed.alphaSum<sample.alphaSum*.6,'Dimmer must change the actual grid pixels');
      await page.evaluate(()=>stage.setSceneLight(1,true));
      cases.push({width,height,theme,grid:sample,dimmed,shadow});
    }
    await page.evaluate(()=>stage.dispose());assert.equal(await page.locator('canvas').count(),0);
  }

  await page.setViewportSize({width:404,height:430});await page.goto(site.url);await page.waitForFunction(()=>window.ready);
  await page.evaluate(()=>{
    window.native=new THREE.GridHelper(1,52,0x00f0ff,0x0e7490);
    native.scale.setScalar(20*height);native.position.y=.0005*height;
    Object.assign(native.material,{transparent:true,depthWrite:false,opacity:.12});stage.scene.add(native);isolate(native);
  });
  const nativeControl=await gridPixels(page);
  await page.screenshot({path:`${out}/${engine.name()}-native-lines-control.png`});
  await page.evaluate(()=>{
    native.removeFromParent();native.geometry.dispose();native.material.dispose();
    window.filled=new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.MeshBasicMaterial({color:0x00f0ff,transparent:true,opacity:.12,side:THREE.DoubleSide}));
    filled.rotation.x=-Math.PI/2;filled.scale.setScalar(20*height);filled.position.y=.0005*height;
    stage.scene.add(filled);isolate(filled);
  });
  const filledControl=await gridPixels(page);
  assert.ok(filledControl.outside>1000,'The independent oracle must reject a broadly filled floor');
  assert.throws(()=>assertGrid(filledControl));
  await page.evaluate(()=>{filled.removeFromParent();filled.geometry.dispose();filled.material.dispose();isolate(grid);});
  const corrected=await gridPixels(page);assertGrid(corrected);
  await page.screenshot({path:`${out}/${engine.name()}-grid-only.png`});

  // Camera motion, zoom and projection updates remain valid; no per-camera grid rebuild or far/near workaround.
  for(const [x,y,z] of [[-.036,.0276,.0624],[.036,.06,-.0624],[0,.08,.001],[.007,.008,.018],[-.036,-.0276,.0624]]){
    await page.evaluate(([x,y,z])=>{stage.controls.maxPolarAngle=Math.PI;stage.camera.position.set(x,y,z);stage.controls.target.set(0,.006,0);draw();},[x,y,z]);
    const sample=await gridPixels(page);assertGrid(sample);cases.push({camera:[x,y,z],grid:sample});
  }
  const palette=await page.evaluate(()=>{
    stage.frame(height);stage.setPalette({accent:'#ff0000',grid:'#0000ff'});draw();
    const data=pixels();let axes=0,minor=0;
    for(let i=0;i<data.length;i+=4)if(data[i+3]>2){if(data[i]>data[i+2]*2)axes++;if(data[i+2]>data[i]*2)minor++;}
    return {axes,minor};
  });
  assert.ok(palette.axes>20&&palette.minor>100,`Both accent axes and minor lines must render: ${JSON.stringify(palette)}`);
  const disposal=await page.evaluate(async()=>{
    let geometry=0,material=0,frames=0;
    grid.geometry.addEventListener('dispose',()=>geometry++);grid.material.addEventListener('dispose',()=>material++);
    stage.onFrame(()=>frames++);stage.start();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const before=frames;stage.dispose();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    model.geometry.dispose();model.material.dispose();return {geometry,material,before,after:frames,canvases:document.querySelectorAll('canvas').length};
  });
  assert.deepEqual(disposal,{geometry:1,material:1,before:disposal.before,after:disposal.before,canvases:0});
  assert.ok(disposal.before>0);assert.deepEqual(errors,[]);
  await context.close();

  // Exercise the renderer's real WebGL 1 fallback, not a mocked capabilities flag. Derivative shaders need both
  // OES_standard_derivatives support and the extension directive in GLSL ES 1.00, unlike the default WebGL 2 path.
  const fallback=await browser.newContext({viewport:{width:404,height:430},deviceScaleFactor:1,reducedMotion:'reduce'});
  await fallback.addInitScript(()=>{
    const original=HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext=function(kind,...args){return kind==='webgl2'?null:original.call(this,kind,...args);};
  });
  const fallbackPage=await fallback.newPage(),fallbackErrors=[];
  fallbackPage.on('pageerror',error=>fallbackErrors.push(error.message));
  fallbackPage.on('console',message=>{if(message.type()==='error')fallbackErrors.push(message.text());});
  await fallbackPage.goto(site.url);await fallbackPage.waitForFunction(()=>window.ready);
  const fallbackInfo=await fallbackPage.evaluate(()=>{
    const gl=stage.renderer.getContext();
    return {version:gl.getParameter(gl.VERSION),webgl2:stage.renderer.capabilities.isWebGL2,
      derivativesAvailable:!!gl.getExtension('OES_standard_derivatives')};
  });
  assert.equal(fallbackInfo.webgl2,false);assert.match(fallbackInfo.version,/^WebGL 1\.0/);
  assert.equal(fallbackInfo.derivativesAvailable,true,'The fallback fixture needs actual derivatives support');
  for(const theme of ['dark','light']){
    await fallbackPage.evaluate(theme=>{
      restore();stage.setPalette(theme==='dark'?{accent:'#00f0ff',grid:'#0e7490',background:'#0b1018'}
        :{accent:'#006e7a',grid:'#477984',background:'#f4f3ed'});draw();
    },theme);
    await fallbackPage.screenshot({path:`${out}/${engine.name()}-webgl1-${theme}.png`});
    await fallbackPage.evaluate(()=>isolate(grid));
    const sample=await gridPixels(fallbackPage);
    assert.deepEqual(fallbackErrors,[],'WebGL 1 must compile and draw without shader errors');assertGrid(sample);
    cases.push({context:'webgl1',theme,grid:sample});
  }
  await fallbackPage.evaluate(()=>{stage.dispose();model.geometry.dispose();model.material.dispose();});
  assert.equal(await fallbackPage.locator('canvas').count(),0);
  await fallback.close();
  const hash=data=>createHash('sha256').update(data).digest('hex');
  const report={engine:engine.name(),browserVersion:browser.version(),sourceRevision:process.env.TEST_SOURCE_REVISION||'unrecorded',
    stageSha256:hash(await readFile(new URL('../../software/cadagent/webkit/stage.js',import.meta.url))),
    harnessSha256:hash(await readFile(new URL(import.meta.url))),cases,nativeControl,filledControl,corrected,palette,disposal,
    fallback:{...fallbackInfo,errors:fallbackErrors},errors};
  await writeFile(`${out}/${engine.name()}-result.json`,JSON.stringify(report,null,2));
  console.log(JSON.stringify({engine:report.engine,cases:cases.length,nativeOutside:nativeControl.outside,correctedOutside:corrected.outside,errors:errors.length}));
} finally {await browser?.close();await site.close();}
