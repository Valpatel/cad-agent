import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {ScadaCamera, ScadaViewer} from '../../../../software/cadagent/webkit/scada/ui/src/viewer/viewer.mjs';

const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} ≈ ${expected}`);
function setup({stage = true, width = 800, height = 400} = {}) {
  const dom = new JSDOM(`<main><div id="viewport" style="overflow:auto">${stage ? '<div data-scada-stage>' : ''}<div data-scada-canvas style="transform:scale(.7)"><button id="equipment">Pump</button></div>${stage ? '</div>' : ''}</div><button id="outside">Outside</button></main>`, {pretendToBeVisual:true});
  const {window} = dom, viewport = window.document.querySelector('#viewport'), canvas = viewport.querySelector('[data-scada-canvas]');
  const size = {width,height};
  Object.defineProperties(viewport, {clientWidth:{get:() => size.width}, clientHeight:{get:() => size.height}});
  viewport.getBoundingClientRect = () => ({left:10,top:20,right:10+size.width,bottom:20+size.height,...size});
  const observers = [];
  window.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.disconnected = false; observers.push(this); }
    observe(element) { this.target = element; }
    disconnect() { this.disconnected = true; }
  };
  const pointer = (target, type, {id=1,x=100,y=100,pointerType='mouse',button=0} = {}) => {
    const event = new window.MouseEvent(type,{bubbles:true,cancelable:true,clientX:x+10,clientY:y+20,button});
    Object.defineProperties(event,{pointerId:{value:id},pointerType:{value:pointerType}});
    target.dispatchEvent(event); return event;
  };
  return {dom,window,viewport,canvas,size,observers,pointer,
    mount:options => new ScadaCamera({viewport,canvas,width:2000,height:1000,...options})};
}

test('direct or staged worlds fit below screen-space controls, without scroll containers', () => {
  for (const stage of [true,false]) {
    const fixture = setup({stage}), camera = fixture.mount();
    const {viewport,canvas} = fixture, state = camera.state;
    near(state.zoom,.324); near(state.x,76); near(state.y,64);
    assert.equal(viewport.style.overflow,'clip');
    assert.equal(viewport.style.touchAction,'none');
    assert.equal(canvas.style.transform,'translate(76px, 64px) scale(0.324)');
    const fit = viewport.querySelector('[data-scada-camera-fit]');
    assert.equal(fit.parentElement,viewport);
    assert.equal(fit.textContent,'Zoom to fit');
    assert.equal(fit.hasAttribute('data-scada-zoom'),false,'legacy toolbar selector stays unique');
    if (stage) assert.equal(viewport.querySelector('[data-scada-stage]').style.width,'100%');
    camera.destroy(); fixture.window.close();
  }
});

test('pointer-anchored zoom preserves the world point and huge fitted layouts zoom out monotonically', () => {
  const fixture = setup(), camera = fixture.mount();
  const point = {x:210,y:170}, before = camera.state;
  camera.setZoom(1.5,point);
  near((point.x-camera.state.x)/camera.state.zoom,(point.x-before.x)/before.zoom);
  near((point.y-camera.state.y)/camera.state.zoom,(point.y-before.y)/before.zoom);
  camera.setZoom(100); assert.equal(camera.state.zoom,3);
  camera.setSize(200000,100000,{fit:true}); const fitted = camera.state.zoom;
  assert.ok(fitted < .05);
  camera.zoomBy(.8); near(camera.state.zoom,fitted);
  camera.zoomBy(1.25); assert.ok(camera.state.zoom > fitted);
  camera.destroy(); fixture.window.close();
});

test('wheel is consumed only inside the viewport and uses its pointer as the zoom anchor', () => {
  const fixture = setup(), {window,viewport} = fixture, camera = fixture.mount(), before = camera.state;
  const outside = new window.WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-360});
  window.document.querySelector('#outside').dispatchEvent(outside);
  assert.equal(outside.defaultPrevented,false); assert.deepEqual(camera.state,before);
  const wheel = new window.WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-360,clientX:210,clientY:170});
  viewport.dispatchEvent(wheel);
  assert.equal(wheel.defaultPrevented,true); assert.ok(camera.state.zoom > before.zoom);
  near((200-camera.state.x)/camera.state.zoom,(200-before.x)/before.zoom);
  near((150-camera.state.y)/camera.state.zoom,(150-before.y)/before.zoom);
  camera.destroy(); fixture.window.close();
});

test('equipment taps remain clicks, drags suppress pointer activation, and keyboard activation remains available', () => {
  const fixture = setup(), {window,viewport,pointer} = fixture, camera = fixture.mount();
  const equipment = viewport.querySelector('#equipment'); let clicks = 0;
  equipment.addEventListener('click',() => clicks++);
  const click = detail => equipment.dispatchEvent(new window.MouseEvent('click',{bubbles:true,cancelable:true,detail}));
  pointer(equipment,'pointerdown'); pointer(equipment,'pointermove',{x:103,y:102}); pointer(equipment,'pointerup'); click(1);
  assert.equal(clicks,1); assert.equal(camera.state.fitted,true);
  const before = camera.state;
  pointer(equipment,'pointerdown'); pointer(window,'pointermove',{x:150,y:120}); pointer(window,'pointerup',{x:150,y:120});
  near(camera.state.x,before.x+50); near(camera.state.y,before.y+20);
  click(1); assert.equal(clicks,1); click(0); assert.equal(clicks,2);
  const fit = viewport.querySelector('[data-scada-camera-fit]'), manual = camera.state;
  pointer(fit,'pointerdown',{x:750,y:30}); pointer(window,'pointermove',{x:790,y:60}); pointer(window,'pointerup',{x:790,y:60});
  assert.deepEqual(camera.state,manual,'a drag beginning on screen controls never moves the world');
  fit.dispatchEvent(new window.MouseEvent('click',{bubbles:true,cancelable:true,detail:1}));
  assert.equal(camera.state.fitted,true,'Fit remains usable immediately after a canvas drag');
  camera.destroy(); window.close();
});

test('release outside the viewport before drag threshold leaves no phantom pinch pointer', () => {
  const fixture = setup(), {window,viewport,pointer} = fixture, camera = fixture.mount();
  pointer(viewport,'pointerdown',{id:1,x:799}); pointer(window,'pointerup',{id:1,x:801});
  const before = camera.state;
  pointer(viewport,'pointerdown',{id:2,x:200,pointerType:'touch'});
  pointer(window,'pointermove',{id:2,x:240,pointerType:'touch'});
  near(camera.state.zoom,before.zoom); near(camera.state.x,before.x+40);
  pointer(window,'pointercancel',{id:2,pointerType:'touch'});
  assert.equal(viewport.dataset.cameraDragging,'false');
  camera.destroy(); window.close();
});

test('two-finger pinch follows the moving midpoint and returns to single-finger pan', () => {
  const fixture = setup(), {window,viewport,pointer} = fixture, camera = fixture.mount();
  pointer(viewport,'pointerdown',{id:1,x:200,y:200,pointerType:'touch'});
  pointer(viewport,'pointerdown',{id:2,x:400,y:200,pointerType:'touch'});
  const before = camera.state;
  pointer(window,'pointermove',{id:2,x:500,y:200,pointerType:'touch'});
  near(camera.state.zoom,before.zoom*1.5);
  near((350-camera.state.x)/camera.state.zoom,(300-before.x)/before.zoom);
  pointer(window,'pointerup',{id:2,x:500,y:200,pointerType:'touch'});
  const after = camera.state;
  pointer(window,'pointermove',{id:1,x:230,y:220,pointerType:'touch'});
  near(camera.state.x,after.x+30); near(camera.state.y,after.y+20);
  pointer(window,'pointerup',{id:1,pointerType:'touch'});
  camera.destroy(); window.close();
});

test('keyboard navigation pans and fits without hijacking editable controls', () => {
  const fixture = setup(), {window,viewport} = fixture, camera = fixture.mount();
  const key = (target,key,options={}) => { const event = new window.KeyboardEvent('keydown',{key,bubbles:true,cancelable:true,...options}); target.dispatchEvent(event); return event; };
  const before = camera.state;
  assert.equal(key(viewport,'ArrowRight').defaultPrevented,true); near(camera.state.x,before.x-40);
  key(viewport,'+'); assert.ok(camera.state.zoom > before.zoom);
  key(viewport,'Home'); assert.equal(camera.state.fitted,true);
  const input = window.document.createElement('input'); viewport.append(input);
  const fitted = camera.state;
  assert.equal(key(input,'ArrowLeft').defaultPrevented,false); assert.deepEqual(camera.state,fitted);
  assert.equal(key(viewport,'f',{ctrlKey:true}).defaultPrevented,false);
  key(viewport,'ArrowDown'); key(viewport,'f'); assert.equal(camera.state.fitted,true);
  camera.destroy(); window.close();
});

test('resize refits a fitted world but preserves the manual world center', () => {
  const fixture = setup(), {size,observers,canvas} = fixture, camera = fixture.mount();
  size.width=500; size.height=600; observers[0].callback();
  near(camera.state.zoom,476/2000); assert.equal(camera.state.fitted,true);
  camera.setZoom(1); camera.panBy(50,-25); const before = camera.state;
  const worldCenter = {x:(250-before.x)/before.zoom,y:(300-before.y)/before.zoom};
  size.width=900; size.height=400; observers[0].callback();
  near((450-camera.state.x)/camera.state.zoom,worldCenter.x);
  near((200-camera.state.y)/camera.state.zoom,worldCenter.y);
  const saved = camera.state; canvas.style.transform='scale(0.1)'; camera.refresh();
  assert.deepEqual(camera.state,saved); assert.match(canvas.style.transform,/scale\(1\)/);
  camera.destroy(); assert.equal(observers[0].disconnected,true); fixture.window.close();
});

test('focus reveals offscreen equipment by camera movement without native scroll offsets', () => {
  const fixture = setup(), {window,viewport} = fixture, camera = fixture.mount();
  camera.setZoom(1); const equipment = viewport.querySelector('#equipment'); let worldY=700;
  equipment.getBoundingClientRect = () => {
    const {x,y,zoom} = camera.state, left=10+x+1700*zoom, top=20+y+worldY*zoom;
    return {left,top,right:left+160*zoom,bottom:top+100*zoom,width:160*zoom,height:100*zoom};
  };
  equipment.focus();
  const bounds = equipment.getBoundingClientRect(), view = viewport.getBoundingClientRect();
  assert.ok(bounds.left >= view.left && bounds.right <= view.right);
  assert.ok(bounds.top >= view.top && bounds.bottom <= view.bottom);
  assert.equal(window.document.activeElement,equipment);
  assert.equal(viewport.scrollLeft,0); assert.equal(viewport.scrollTop,0);
  window.document.querySelector('#outside').focus(); worldY=0;
  camera.setState({x:-1000,y:-200,zoom:1}); equipment.focus();
  assert.ok(equipment.getBoundingClientRect().top >= view.top+64,'focused top-right equipment is revealed below pinned controls');
  camera.destroy(); window.close();
});

test('destroy restores owned styles, removes screen controls and observers, and detaches all window handlers', () => {
  const fixture = setup(), {window,viewport,canvas,pointer,observers} = fixture, camera = fixture.mount();
  pointer(viewport,'pointerdown'); camera.destroy(); camera.destroy();
  assert.equal(viewport.style.overflow,'auto'); assert.equal(canvas.style.transform,'scale(.7)');
  assert.equal(viewport.hasAttribute('data-scada-camera'),false);
  assert.equal(viewport.querySelector('[data-scada-camera-fit]'),null);
  assert.equal(observers[0].disconnected,true);
  const before = camera.state; pointer(window,'pointermove',{x:200});
  viewport.dispatchEvent(new window.WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-100}));
  assert.deepEqual(camera.state,before); fixture.window.close();
});

test('failed initialization cleans owned resources before rethrowing callback errors', () => {
  const fixture = setup(), {window,viewport,canvas,observers} = fixture;
  let additions=0, removals=0;
  const add=window.addEventListener.bind(window), remove=window.removeEventListener.bind(window);
  window.addEventListener=(type,...args) => { if(type.startsWith('pointer')) additions++; return add(type,...args); };
  window.removeEventListener=(type,...args) => { if(type.startsWith('pointer')) removals++; return remove(type,...args); };
  assert.throws(() => fixture.mount({onChange:() => { throw new Error('Host callback failed'); }}),/Host callback failed/);
  assert.equal(additions,3); assert.equal(removals,3); assert.equal(observers[0].disconnected,true);
  assert.equal(viewport.hasAttribute('data-scada-camera'),false); assert.equal(viewport.style.overflow,'auto');
  viewport.dispatchEvent(new window.WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-100}));
  assert.equal(canvas.style.transform,'scale(.7)'); window.close();
});

test('invalid sizes, states and foreign stages are rejected before changing mounted state', () => {
  const fixture = setup(), camera = fixture.mount(), before = camera.state;
  assert.throws(() => camera.setSize(0,100),/positive/);
  assert.throws(() => camera.setZoom(NaN),/finite/);
  assert.throws(() => camera.setState({x:0,y:0,zoom:Infinity}),/finite/);
  assert.deepEqual(camera.state,before);
  assert.throws(() => fixture.mount({stage:fixture.viewport}),/stage/);
  camera.destroy(); fixture.window.close();
});

test('viewer snapshot patches retain camera, equipment and focused recovery control; host-only mode owns none', () => {
  const fixture = setup(), {window} = fixture, root=window.document.createElement('section'); window.document.body.append(root);
  let publish; const snapshot={components:{pump:{active:true}}};
  const adapter={getSnapshot:() => snapshot,subscribe:listener => {publish=listener;return () => {};}};
  const options={adapter,equipment:[{id:'pump',type:'pump'}],views:[{id:'water',width:1000,height:600,nodes:[{id:'pump',x:100,y:100,w:160,h:160}]}]};
  const viewer = new ScadaViewer(options).mount(root), camera=viewer.camera;
  const viewport=camera.viewport; Object.defineProperties(viewport,{clientWidth:{value:700},clientHeight:{value:350}});camera.refresh();
  camera.setZoom(1.25); camera.panBy(40,-30);
  const before=camera.state, equipment=root.querySelector('[data-scada-equipment]'), fit=root.querySelector('[data-scada-camera-fit]'); fit.focus();
  publish(snapshot);
  assert.equal(viewer.camera,camera); assert.deepEqual(camera.state,before);
  assert.equal(root.querySelector('[data-scada-equipment]'),equipment);
  assert.equal(root.querySelector('[data-scada-camera-fit]'),fit); assert.equal(window.document.activeElement,fit);
  assert.equal(root.querySelectorAll('[data-scada-zoom=fit]').length,1);
  assert.equal(viewer.zoom,1.25);
  viewer.destroy(); assert.equal(viewer.camera,null);
  const host = new ScadaViewer(options).mount(root,{render:false,bindEvents:false,workspace:false});
  assert.equal(host.camera,null); host.destroy(); window.close();
});

test('explicit constructor and pre-mount setZoom requests survive initial camera mounting', () => {
  const fixture=setup(), {window}=fixture, adapter={getSnapshot:() => ({}),subscribe:() => () => {}};
  const options={adapter,equipment:[{id:'pump',type:'pump'}],views:[{id:'water',width:1000,height:600,nodes:[{id:'pump',x:100,y:100,w:160,h:160}]}]};
  for (const mode of ['constructor','setter']) {
    const root=window.document.createElement('section'); window.document.body.append(root);
    const viewer=new ScadaViewer({...options,...(mode==='constructor'?{zoom:2}:{})});
    if(mode==='setter') viewer.setZoom(2);
    viewer.mount(root);
    assert.equal(viewer.zoom,2,`${mode} explicit zoom retained`);
    assert.equal(viewer.camera.state.zoom,2); assert.equal(viewer.camera.state.fitted,false);
    viewer.destroy(); root.remove();
  }
  window.close();
});
