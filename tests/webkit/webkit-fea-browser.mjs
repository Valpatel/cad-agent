/** Real FEA surface, pointer hover and shared-palette contrast; synthetic values are not physical results. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,webkit} from '../site/npm-context.mjs';
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
const site=await serveWebkit(new Map([
  ['/fixture.json',(_req,res)=>res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(fixture))],
  ['/favicon.ico',(_req,res)=>res.writeHead(204).end()],
]));
const engine=process.env.PLAYWRIGHT_BROWSER==='webkit'?webkit:chromium;
const browser=await engine.launch(engine===chromium?{headless:true,channel:process.env.PLAYWRIGHT_CHANNEL==='chromium'?'chromium':'chrome',executablePath:process.env.CHROMIUM_EXECUTABLE}:{headless:true});
const out=process.env.TEST_OUTPUT||'/tmp/cad-agent-fea';await mkdir(out,{recursive:true});
const cases=[],errors=[];
try{
  for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width:1366,height:900},colorScheme:theme}),page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    try{
      await page.goto(site.url+'/kit/fea/fea.html?case=/fixture.json&nav=0&title=FEA%20fixture');
      await page.waitForFunction(()=>document.body.dataset.ready==='1');
      await page.evaluate(()=>window.__fea.fit('top'));
      // Finish a real paint before the native pointer enters the projected surface.
      await page.screenshot({path:out+'/'+engine.name()+'-'+theme+'-ready.png'});
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
    }catch(error){await page.screenshot({path:out+'/'+engine.name()+'-'+theme+'-failure.png'});throw error;}
    finally{await context.close();}
  }
  assert.deepEqual(errors,[]);
  await writeFile(out+'/'+engine.name()+'-report.json',JSON.stringify({passed:true,browser:await browser.version(),cases,errors},null,2));
  console.log(JSON.stringify({passed:true,engine:engine.name(),cases:cases.length,out}));
}finally{await browser.close();await site.close();}
