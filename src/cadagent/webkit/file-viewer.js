import * as THREE from 'three';
import {createStage} from './stage.js';
import {fileURL,loadFileGeometry} from './file-loader.js';
const views={iso:[1,.7,1.3],front:[0,0,1],side:[1,0,0],top:[0,1,.0001]};
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text)node.textContent=text;return node;}
function disposeModel(group){group?.traverse(node=>{if(node.isMesh){node.geometry.dispose();for(const material of [].concat(node.material))material.dispose();}});}
function buildModel(data){
  const group=new THREE.Group();group.name=data.sourceName;group.rotation.x=-Math.PI/2;group.scale.setScalar(.001);
  for(const source of data.meshes){
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(source.positions,3));
    if(source.indices)geometry.setIndex(new THREE.BufferAttribute(source.indices,1));
    if(source.normals)geometry.setAttribute('normal',new THREE.BufferAttribute(source.normals,3));else geometry.computeVertexNormals();
    if(source.colors)geometry.setAttribute('color',new THREE.BufferAttribute(source.colors,3));
    for(const g of source.groups)geometry.addGroup(g.start,g.count,g.materialIndex);
    const materials=source.materials.map(m=>new THREE.MeshStandardMaterial({color:new THREE.Color(...m.color),opacity:m.opacity,transparent:m.opacity<1,roughness:.5,metalness:.12,side:THREE.DoubleSide,vertexColors:!!source.colors}));
    const mesh=new THREE.Mesh(geometry,materials.length===1?materials[0]:materials);mesh.name=source.name;mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);
  }
  group.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(group),center=box.getCenter(new THREE.Vector3());
  group.position.set(-center.x,-box.min.y,-center.z);group.updateMatrixWorld(true);return group;
}
/** Mount an original-file preview. Later loads preserve the usable scene until replacement is ready. */
export function createFileViewer(host,{file,back,onState=()=>{},timeoutMs=30000,parseTimeoutMs=120000}={}){
  const root=element('div','file-viewer'),header=element('header','file-header'),titleBox=element('div','file-title'),title=element('h1',null,'Original CAD file'),subtitle=element('p',null,'Inspect the original geometry · download it unchanged');
  titleBox.append(title,subtitle);const nav=element('nav','file-nav');nav.setAttribute('aria-label','File navigation');
  if(back){try{const url=new URL(back,location.href);if(url.origin===location.origin&&/^https?:$/.test(url.protocol)&&!url.username&&!url.password){const link=element('a','file-link','Back to parts');link.href=url.href;nav.append(link);}}catch{/* No external navigation fallback. */}}
  const download=element('a','file-link','Download original');download.hidden=true;download.setAttribute('download','');nav.append(download);header.append(titleBox,nav);
  const canvas=element('div','file-canvas'),status=element('section','file-status'),statusText=element('p'),actions=element('div','file-status-actions');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const retry=element('button',null,'Retry file'),cancelButton=element('button',null,'Cancel');retry.type=cancelButton.type='button';actions.append(retry,cancelButton);status.append(statusText,actions);canvas.append(status);
  const footer=element('footer','file-controls'),toolbar=element('div','file-tools');toolbar.setAttribute('aria-label','Camera views');const viewButtons=[];
  for(const [key,label] of [['fit','Fit'],['iso','Isometric'],['front','Front'],['side','Side'],['top','Top']]){const button=element('button',null,label);button.type='button';button.addEventListener('click',()=>fit(key));toolbar.append(button);viewButtons.push(button);}
  const unitLabel=element('label',null,'STL units'),unitSelect=element('select');unitSelect.setAttribute('aria-label','STL units');for(const [value,label] of [['millimeter','mm'],['centimeter','cm'],['meter','m'],['micron','μm'],['inch','in'],['foot','ft']]){const option=element('option',null,label);option.value=value;unitSelect.append(option);}unitLabel.append(unitSelect);unitLabel.hidden=true;toolbar.append(unitLabel);
  const help=element('p','file-help','Drag to orbit · two fingers to pan or pinch · scroll gently to zoom'),details=element('details','file-details'),summary=element('summary',null,'File details'),detailText=element('p');details.append(summary,detailText);footer.append(toolbar,help,details);root.append(header,canvas,footer);host.append(root);
  let stage;try{stage=createStage(canvas,{height:.2,screenshots:true});}catch(error){root.remove();throw error;}
  stage.controls.maxPolarAngle=Math.PI;stage.controls.minPolarAngle=0;
  let model=null,info=null,currentFile=file,request=0,controller=null,disposed=false,busy=false,view='iso',zoomTarget=null;
  const events=new AbortController();
  const setStatus=(state,message)=>{root.dataset.state=state;busy=state==='loading';root.setAttribute('aria-busy',String(busy));status.dataset.state=state;status.hidden=state==='ready';statusText.textContent=message||'';retry.hidden=!['error','cancelled'].includes(state)||!currentFile;cancelButton.hidden=!busy;for(const b of viewButtons)b.disabled=!model;onState({state,message,info});};
  const bounds=()=>new THREE.Box3().setFromObject(model);
  function fit(next='fit'){
    if(!model)return;zoomTarget=null;
    const direction=next==='fit'?stage.camera.position.clone().sub(stage.controls.target):new THREE.Vector3(...(views[next]||views.iso));if(next!=='fit')view=next;
    stage.fitView(bounds(),{direction,margin:1.15});
  }
  // Pixel-sensitive wheel movement, eased over frames; native OrbitControls retains pinch/pan.
  canvas.addEventListener('wheel',event=>{
    if(!model)return;event.preventDefault();event.stopImmediatePropagation();
    const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?canvas.clientHeight:1),radius=zoomTarget??stage.camera.position.distanceTo(stage.controls.target);
    zoomTarget=THREE.MathUtils.clamp(radius*Math.exp(THREE.MathUtils.clamp(delta,-120,120)*.00013),stage.controls.minDistance,stage.controls.maxDistance);
  },{capture:true,passive:false,signal:events.signal});
  canvas.addEventListener('pointerdown',()=>{zoomTarget=null;},{capture:true,signal:events.signal});
  stage.onFrame((t,dt)=>{if(zoomTarget!==null){const offset=stage.camera.position.clone().sub(stage.controls.target),radius=offset.length(),next=THREE.MathUtils.lerp(radius,zoomTarget,1-Math.exp(-dt*18));stage.camera.position.copy(stage.controls.target).addScaledVector(offset.normalize(),next);if(Math.abs(next-zoomTarget)<zoomTarget*.00001)zoomTarget=null;}});
  let resizeFrame;const observer=new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(model)fit('fit');});});observer.observe(canvas);
  async function load(value=currentFile){
    if(disposed)return false;currentFile=value;const id=++request;controller?.abort();controller=new AbortController();
    document.body.dataset.ready=model?'1':'0';
    try{
      const source=fileURL(value);download.href=source.url.href;download.hidden=false;title.textContent=source.name;subtitle.textContent=model?'Currently showing '+info.sourceName:'Inspect the original geometry · download it unchanged';download.textContent=model?'Download requested original':'Download original';unitLabel.hidden=source.format!=='stl';setStatus('loading','Preparing the original file…');
      const nextInfo=await loadFileGeometry(value,{signal:controller.signal,unit:unitSelect.value,timeoutMs,parseTimeoutMs,onProgress:message=>{if(id===request&&!disposed)setStatus('loading',message);}});
      if(id!==request||disposed)return false;
      const next=buildModel(nextInfo);if(id!==request||disposed){disposeModel(next);return false;}
      const previous=model;stage.root.add(next);model=next;info=nextInfo;
      const box=bounds(),size=box.getSize(new THREE.Vector3()),extent=Math.max(size.x,size.y,size.z,.000001);stage.frame(extent);stage.controls.minDistance=extent*.04;stage.controls.maxDistance=extent*30;stage.camera.near=extent*.0005;stage.camera.far=extent*100;fit(view);
      if(previous){stage.root.remove(previous);disposeModel(previous);}
      const raw=new THREE.Box3();for(const m of info.meshes)raw.union(new THREE.Box3(new THREE.Vector3(...m.bounds.slice(0,3)),new THREE.Vector3(...m.bounds.slice(3))));
      info.boundsMm=raw.getSize(new THREE.Vector3()).toArray();summary.textContent=`${info.format} · ${info.triangles.toLocaleString()} triangles · ${info.boundsMm.map(n=>Number(n.toFixed(2))).join(' × ')} mm`;
      detailText.textContent=[info.unitNote,...info.warnings,'CAD Z-up is shown vertically. Preview tessellation does not alter the download.'].join('. ');
      await new Promise(resolve=>requestAnimationFrame(()=>{if(id===request&&!disposed)stage.renderer.render(stage.scene,stage.camera);resolve();}));
      if(id!==request||disposed)return false;document.body.dataset.ready='1';subtitle.textContent='Inspect the original geometry · download it unchanged';download.textContent='Download original';setStatus('ready');return true;
    }catch(error){if(id!==request||disposed)return false;setStatus(error.name==='AbortError'?'cancelled':'error',error.name==='AbortError'?'Loading cancelled. You can retry this original file.':(error.message||'The original file could not be opened.')+(model?' Still showing '+info.sourceName+'.':''));return false;}
  }
  function cancel(){request++;controller?.abort();setStatus('cancelled',model?'Loading cancelled. Still showing '+info.sourceName+'.':'Loading cancelled. You can retry this original file.');}
  retry.addEventListener('click',()=>load());cancelButton.addEventListener('click',cancel);unitSelect.addEventListener('change',()=>load());
  stage.start();if(file)load();else{currentFile=null;setStatus('empty','Open an STL, STEP or 3MF link from a parts list to preview its original geometry.');}
  const params=new URLSearchParams(location.search);if(params.get('ui')==='0')root.dataset.ui='hidden';if(views[params.get('view')])view=params.get('view');
  return{stage,root,get model(){return model;},get info(){return info;},load,cancel,retry:()=>load(),fit,dispose(){if(disposed)return;disposed=true;request++;controller?.abort();events.abort();observer.disconnect();cancelAnimationFrame(resizeFrame);disposeModel(model);stage.dispose();root.remove();}};
}
