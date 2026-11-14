import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from '../dependencies.mjs';
import {ScadaViewer, renderScadaDiagram, normalizeViewerDefinition} from '../../../../software/cadagent/webkit/scada/ui/src/viewer/viewer.mjs';
import {UtilityModel} from '../../../../software/cadagent/webkit/scada/ui/examples/viewer/utility-model.mjs';
import {createUtilityAdapter} from '../../../../software/cadagent/webkit/scada/ui/examples/viewer/utility-adapter.mjs';

const definition = JSON.parse(fs.readFileSync(new URL('../../../../software/cadagent/webkit/scada/ui/examples/viewer/system.json', import.meta.url), 'utf8'));
const setup = () => new JSDOM('<main><div id="editable"></div><div id="monitor"></div></main>', {url:'https://consumer.example/'});
const click = (window, selector, root = window.document) => {
  const element = root.querySelector(selector); assert.ok(element, selector);
  element.dispatchEvent(new window.MouseEvent('click', {bubbles:true})); return element;
};

test('diagram actions dispatch the declared asset without opening a dialog and preserve focused DOM', () => {
  const dom=setup(),{window}=dom,model=new UtilityModel();
  const viewer=new ScadaViewer({definition,adapter:createUtilityAdapter(model),selected:'tank'}).mount(window.document.querySelector('#editable'));
  const observer=new ScadaViewer({definition,adapter:createUtilityAdapter(model,{readOnly:true})}).mount(window.document.querySelector('#monitor'));
  try {
    const action=viewer.root.querySelector('[data-scada-diagram-control="valveSwitch"]');
    assert.equal(action.textContent,'Close');assert.equal(action.closest('[data-scada-equipment]'),null);
    assert.equal(observer.root.querySelector('[data-scada-diagram-control]'),null);
    action.focus();click(window,'[data-scada-diagram-control="valveSwitch"]',viewer.root);
    assert.equal(model.getSnapshot().valveOpen,false);assert.equal(viewer.selected,'valve');
    assert.equal(action.textContent,'Open');assert.equal(window.document.activeElement,action);
    assert.equal(viewer.root.querySelector('dialog').hasAttribute('open'),false);
    assert.equal(observer.snapshot.controls.valveOpen,false);
    viewer.setView('power');assert.equal(viewer.root.querySelector('[data-scada-diagram-control="valveSwitch"]').textContent,'Open');
    click(window,'[data-scada-diagram-control="pumpSwitch"]',viewer.root);
    assert.equal(model.getSnapshot().pumpOn,false);
    assert.equal(model.getSnapshot().valveOpen,false);
  } finally {viewer.destroy();observer.destroy();dom.window.close();}
});

test('view switches mount their own SVG tree while ticks retain equipment, focus and camera controls', () => {
  const dom=setup(),model=new UtilityModel();
  const viewer=new ScadaViewer({definition,adapter:createUtilityAdapter(model)}).mount(dom.window.document.querySelector('#editable'));
  try {
    const viewport=viewer.camera.viewport,canvas=viewer.camera.canvas;
    const art=viewer.root.querySelector('[data-scada-equipment="tank"] svg');
    const action=viewer.root.querySelector('[data-scada-diagram-control="valveSwitch"]');
    action.focus();click(dom.window,'[data-scada-diagram-control="valveSwitch"]',viewer.root);
    assert.equal(viewer.camera.canvas,canvas);
    assert.equal(viewer.root.querySelector('[data-scada-equipment="tank"] svg'),art);
    assert.equal(dom.window.document.activeElement,action);
    viewer.setView('power');
    assert.equal(viewer.camera.viewport,viewport);
    assert.notEqual(viewer.camera.canvas,canvas);
    assert.equal(canvas.isConnected,false);
    assert.equal(viewer.camera.canvas.dataset.scadaView,'power');
    assert.equal(viewer.root.querySelectorAll('[data-scada-camera-controls]').length,1);
    assert.equal(viewer.root.querySelector('[data-scada-diagram-control="valveSwitch"]').textContent,'Open');
    viewer.setView('water');
    assert.equal(viewer.camera.canvas.dataset.scadaView,'water');
    assert.equal(viewer.root.querySelectorAll('[data-scada-camera-controls]').length,1);
  } finally {viewer.destroy();dom.window.close();}
});

test('diagram actions require a typed live binding and expose adapter rejection without changing state', async () => {
  const dom=setup(),model=new UtilityModel();let writes=0;
  const adapter={getSnapshot:()=>({...model.getSnapshot(),controls:{pumpOn:'true',valveOpen:true}}),subscribe:()=>()=>{},dispatch:()=>{writes++;return Promise.reject(new Error('Interlock refuses this command'));}};
  const viewer=new ScadaViewer({definition,adapter}).mount(dom.window.document.querySelector('#editable'));
  try {
    const pump=viewer.root.querySelector('[data-scada-diagram-control="pumpSwitch"]');
    assert.equal(pump.disabled,true);click(dom.window,'[data-scada-diagram-control="pumpSwitch"]',viewer.root);assert.equal(writes,0);
    click(dom.window,'[data-scada-diagram-control="valveSwitch"]',viewer.root);
    await new Promise(resolve=>setTimeout(resolve,0));assert.equal(writes,1);
    assert.match(viewer.root.querySelector('[data-scada-viewer-error]').textContent,/Interlock refuses/);
    assert.equal(viewer.root.querySelector('[data-scada-diagram-control="valveSwitch"]').textContent,'Close');
  } finally {viewer.destroy();dom.window.close();}
});

test('viewer fit ceiling reaches every layout and rejects invalid options before reading the model', () => {
  const dom = setup(), root = dom.window.document.querySelector('#editable');
  let reads = 0, subscriptions = 0;
  const adapter = {getSnapshot:() => { reads++; return {}; }, subscribe:() => { subscriptions++; return () => subscriptions--; }};
  const options = {adapter,equipment:[{id:'pump',type:'pump'}],views:[
    {id:'water',width:1000,height:500,nodes:[{id:'pump',x:100,y:100,w:160,h:160}]},
    {id:'detail',width:500,height:400,nodes:[{id:'pump',x:100,y:100,w:160,h:160}]},
  ]};
  const original = root.outerHTML;
  for (const fitMaxZoom of [0,-1,3.01,NaN,Infinity,-Infinity,null,'2',true]) {
    assert.throws(() => new ScadaViewer({...options,fitMaxZoom}), /fitMaxZoom/);
    assert.equal(reads,0); assert.equal(subscriptions,0); assert.equal(root.outerHTML,original);
  }
  for (const [fitOptions,expected] of [[{},1],[{fitMaxZoom:2},2]]) {
    const viewer = new ScadaViewer({...options,...fitOptions}).mount(root);
    try {
      Object.defineProperties(viewer.camera.viewport,{clientWidth:{value:4000},clientHeight:{value:2200}});
      viewer.camera.refresh(); assert.equal(viewer.zoom,expected);
      viewer.setView('detail'); assert.equal(viewer.zoom,expected);
      viewer.setZoom(2.5); assert.equal(viewer.zoom,2.5);
      viewer.fit(); assert.equal(viewer.zoom,expected);
      assert.equal(viewer.camera.state.fitted,true);
    } finally { viewer.destroy(); }
    assert.equal(subscriptions,0);
  }
  dom.window.close();
});

test('portable definition normalizes without mutation and geometry resolves ports with escaped labels', () => {
  const original = structuredClone(definition), normalized = normalizeViewerDefinition(definition);
  assert.equal(normalized.views.length, 2);
  assert.deepEqual(definition, original);
  assert.equal(normalized.views[0].nodes[0].type, 'tank');
  const equipment = [{id:'pump', ports:[{id:'outlet', side:'right', offset:.25}]}, {id:'tank', ports:[{id:'inlet', side:'left', offset:.5}]}];
  const view = {id:'portable', width:600, height:300, layout:{pump:{x:10,y:20,w:100,h:80},tank:{x:300,y:80,w:120,h:120}}, edges:[{id:'water',from:{component:'pump',port:'outlet'},to:{component:'tank',port:'inlet'}}], labels:[{x:10,y:15,text:'<script>untrusted</script>'}]};
  const markup = renderScadaDiagram({view, equipment, snapshot:{flows:{water:true}}, selected:'pump', zoom:1.5, renderNode:(node, context) => `<button data-item="${node.id}" data-selected="${context.selected === node.id}"></button>`});
  const document = new JSDOM(markup).window.document;
  assert.equal(document.querySelector('.scada-diagram-pipe').getAttribute('d'), 'M110 40H205V140H300');
  assert.equal(document.querySelector('[data-scada-connection]').dataset.active, 'true');
  assert.equal(document.querySelectorAll('[data-scada-port]').length, 2);
  assert.equal(document.querySelector('script'), null);
  assert.match(document.querySelector('.scada-diagram-labels').textContent, /<script>/);
  assert.match(document.querySelector('[data-scada-canvas]').getAttribute('style'), /scale\(var\(--scada-zoom\)\)/);
  assert.throws(() => renderScadaDiagram({view, renderNode:() => '', zoomProperty:'--zoom;color:red'}), /custom property/);
});

test('flow bindings never coerce strings, invoke accessors, or bypass an explicit missing pointer', () => {
  const view = {id:'data', width:100, height:100, nodes:[], edges:[{id:'line', path:'M0 0L100 100', flowBinding:'/reading'}]};
  const render = snapshot => new JSDOM(renderScadaDiagram({view, snapshot, renderNode:() => ''})).window.document.querySelector('[data-scada-connection]');
  assert.equal(render({reading:true}).dataset.active, 'true');
  assert.equal(render({reading:false}).dataset.active, 'false');
  assert.equal(render({reading:'false'}).dataset.dataStatus, 'missing');
  assert.equal(render({flows:{line:true}}).dataset.active, 'false');
  let accessors = 0;
  const input = {}; Object.defineProperty(input, 'reading', {get(){ accessors++; return true; }});
  assert.equal(render(input).dataset.active, 'false');
  assert.equal(accessors, 0);
});

test('two mounted views share one external model, forward schema commands, and keep diagrams and focused controls stable', () => {
  const dom = setup(), {window} = dom, model = new UtilityModel();
  const primary = new ScadaViewer({definition, adapter:createUtilityAdapter(model), scope:'primary'}).mount(window.document.querySelector('#editable'));
  const monitor = new ScadaViewer({definition, adapter:createUtilityAdapter(model, {readOnly:true}), initialView:'power', scope:'monitor'}).mount(window.document.querySelector('#monitor'));
  try {
    const root = primary.root, pump = root.querySelector('[data-scada-equipment="pump"]');
    const art = pump.querySelector('.twin-equipment-art');
    click(window, '[data-scada-equipment="pump"]', root);
    const dialog = root.querySelector('dialog');
    assert.ok(dialog.hasAttribute('open'));
    const input = root.querySelector('[data-scada-control="demand"]'); input.focus(); input.value = '72';
    input.dispatchEvent(new window.Event('change', {bubbles:true}));
    assert.equal(model.getSnapshot().demandPct, 72);
    assert.equal(window.document.activeElement, input);
    assert.equal(root.querySelector('[data-scada-equipment="pump"] .twin-equipment-art'), art);
    assert.equal(dialog.getAttribute('aria-modal'), 'true', 'snapshot patching retains modal lifecycle attributes');
    assert.equal(dialog.dataset.scadaFallback, 'true');
    click(window, '[data-scada-control="pumpSwitch"]', dialog);
    assert.equal(model.getSnapshot().pumpOn, false);
    assert.equal(primary.root.querySelector('[data-scada-equipment="pump"] .scada-viewer-equipment-status').textContent, 'Inactive');
    assert.equal(monitor.snapshot.controls.pumpOn, false);
    assert.equal(monitor.root.querySelector('[data-scada-equipment="pump"] [data-scada-type]').dataset.active, 'false');
    primary.closeInspector(); assert.equal(window.document.activeElement, pump);
    primary.setView('power').select('generator', {open:true});
    click(window, '[data-scada-control="breakGenerator"]', primary.root);
    assert.equal(model.getSnapshot().generatorFault, true);
    assert.equal(monitor.snapshot.components.generator.fault, true);
    assert.equal(primary.selected, 'generator');
    primary.setView('water');
    assert.equal(primary.selected, 'generator', 'off-map equipment remains selected and inspectable');
    assert.equal(model.getSnapshot().generatorFault, true);
    primary.openInspector();
    assert.match(primary.root.querySelector('dialog h2').textContent, /Backup generator/);
  } finally { primary.destroy(); monitor.destroy(); model.stop(); window.close(); }
});

test('read-only adapters disable all commands but continue receiving external updates', () => {
  const dom = setup(), model = new UtilityModel();
  const viewer = new ScadaViewer({definition, adapter:createUtilityAdapter(model, {readOnly:true})}).mount(dom.window.document.querySelector('#monitor'));
  try {
    viewer.select('pump', {open:true});
    assert.ok([...viewer.root.querySelectorAll('[data-scada-control]')].every(control => control.disabled));
    assert.throws(() => viewer.dispatch({action:'reset'}), /read-only/);
    const before = model.getSnapshot();
    click(dom.window, '[data-scada-control="pumpSwitch"]', viewer.root);
    assert.deepEqual(model.getSnapshot(), before);
    model.dispatch({action:'set', arguments:{key:'pumpOn', value:false}});
    assert.equal(viewer.snapshot.controls.pumpOn, false);
    assert.equal(viewer.root.querySelector('[data-scada-equipment="pump"] [data-scada-type]').dataset.active, 'false');
  } finally { viewer.destroy(); model.stop(); dom.window.close(); }
});

test('host attachment preserves markup, event metadata and independent adapter lifetime', () => {
  const dom = setup(), root = dom.window.document.querySelector('#editable'); root.innerHTML = '<button id="host">Host-owned controls</button>';
  const model = new UtilityModel(), original = createUtilityAdapter(model), hooks = [];
  let subscriptions = 0, deliveries = 0;
  const adapter = {...original, subscribe(listener){ subscriptions++; const unsubscribe = model.subscribe(() => { deliveries++; listener(original.getSnapshot(), {type:'reset', resetPresentation:true}); }); return () => { subscriptions--; unsubscribe(); }; }};
  const viewer = new ScadaViewer({definition, adapter, hooks:{update:event => hooks.push(event)}});
  const button = root.firstElementChild;
  try {
    viewer.mount(root, {render:false, bindEvents:false, workspace:false});
    viewer.mount(root, {render:false, bindEvents:false, workspace:false});
    assert.equal(subscriptions, 1);
    assert.equal(root.firstElementChild, button);
    model.dispatch({action:'reset'});
    assert.equal(deliveries, 1);
    assert.equal(hooks.at(-1).event.resetPresentation, true);
    assert.equal(hooks.at(-1).reason, 'snapshot');
    viewer.select('pump').setView('power').setZoom(1.5);
    assert.equal(viewer.zoom, 1.5);
    assert.equal(root.firstElementChild, button);
    viewer.destroy(); viewer.destroy();
    assert.equal(subscriptions, 0);
    model.tick();
    assert.equal(model.getSnapshot().minutes, 1, 'presentation cleanup does not stop or destroy the model');
    assert.equal(deliveries, 1);
  } finally { viewer.destroy(); model.stop(); dom.window.close(); }
});

test('missing component and control data are visibly offline and never replaced with active defaults', () => {
  const dom = setup();
  const adapter = {getSnapshot:() => ({controls:{pumpOn:'false'}, components:{}}), subscribe:() => () => {}, dispatch:() => { throw new Error('must not dispatch'); }};
  const viewer = new ScadaViewer({definition, adapter, selected:'pump'}).mount(dom.window.document.querySelector('#editable'));
  try {
    assert.equal(viewer.root.querySelector('[data-scada-equipment="pump"]').dataset.dataStatus, 'missing');
    assert.equal(viewer.root.querySelector('[data-scada-equipment="pump"] [data-scada-type]').dataset.active, 'false');
    viewer.openInspector();
    assert.match(viewer.root.querySelector('dialog').textContent, /unavailable|missing|No visual|No state/i);
    assert.equal(viewer.root.querySelector('[data-scada-control="pumpSwitch"]').disabled, true);
    assert.equal(viewer.root.querySelector('[data-scada-control="demand"]').disabled, true);
  } finally { viewer.destroy(); dom.window.close(); }
});

test('adapter rejections are shown, malformed controls do not dispatch, and bad subscriptions clean up', async () => {
  const dom = setup(), model = new UtilityModel(), original = createUtilityAdapter(model);
  let dispatched = 0;
  const adapter = {...original, dispatch(){ dispatched++; return Promise.reject(new Error('Host rejected command')); }};
  const viewer = new ScadaViewer({definition, adapter}).mount(dom.window.document.querySelector('#editable'));
  try {
    viewer.select('pump', {open:true});
    await assert.rejects(viewer.dispatch({action:'set'}), /Host rejected/);
    assert.match(viewer.root.querySelector('[data-scada-viewer-error]').textContent, /Host rejected/);
    assert.equal(viewer.root.querySelector('dialog [data-scada-viewer-dialog-error]').hidden, false);
    assert.match(viewer.root.querySelector('dialog [data-scada-viewer-dialog-error]').textContent, /Host rejected/);
    assert.equal(dispatched, 1);
    const malformed = new ScadaViewer({definition, adapter:{...original, subscribe:() => null}});
    assert.throws(() => malformed.mount(dom.window.document.querySelector('#monitor')), /unsubscribe/);
    assert.equal(malformed.root, null);
    assert.equal(malformed.workspace, null);
    const throwing = new ScadaViewer({definition, adapter:{...original, subscribe(){ throw new Error('Connection unavailable'); }}});
    assert.throws(() => throwing.mount(dom.window.document.querySelector('#monitor')), /Connection unavailable/);
    assert.equal(throwing.root, null);
    assert.equal(throwing.workspace, null);
    assert.throws(() => viewer.setView('missing'), /Unknown view/);
    assert.throws(() => viewer.select('missing'), /Unknown equipment/);
    assert.throws(() => viewer.setZoom(0), /Zoom/);
  } finally { viewer.destroy(); model.stop(); dom.window.close(); }
});

test('settling an asynchronous host command after destroy cannot update detached presentation', async () => {
  const dom = setup(), model = new UtilityModel(), adapter = createUtilityAdapter(model);
  let settle, renders = 0;
  const viewer = new ScadaViewer({definition, adapter:{...adapter, dispatch:() => new Promise(resolve => { settle = resolve; })}, hooks:{update:() => renders++}}).mount(dom.window.document.querySelector('#editable'));
  const pending = viewer.dispatch({action:'reset'});
  const before = renders;
  viewer.destroy(); settle('accepted');
  assert.equal(await pending, 'accepted');
  assert.equal(renders, before);
  assert.equal(viewer.root, null);
  model.stop(); dom.window.close();
});

test('invalid focused drafts and their in-dialog feedback survive unrelated adapter updates', () => {
  const dom = setup(), model = new UtilityModel(), adapter = createUtilityAdapter(model);
  const controls = definition.controls.map(control => control.id === 'demand' ? {...control, kind:'number'} : control);
  const viewer = new ScadaViewer({definition, adapter, controls, selected:'pump'}).mount(dom.window.document.querySelector('#editable'));
  try {
    viewer.openInspector();
    const input = viewer.root.querySelector('[data-scada-control="demand"]'); input.focus(); input.value = '-1';
    input.dispatchEvent(new dom.window.Event('change', {bubbles:true}));
    assert.equal(model.getSnapshot().demandPct, 50);
    assert.equal(input.getAttribute('aria-invalid'), 'true');
    assert.ok(dom.window.document.getElementById(input.getAttribute('aria-describedby')));
    assert.equal(viewer.root.querySelector('dialog [data-scada-viewer-dialog-error]').hidden, false);
    model.tick();
    assert.equal(input.value, '-1');
    assert.equal(dom.window.document.activeElement, input);
    assert.equal(input.getAttribute('aria-invalid'), 'true');
    assert.match(viewer.root.querySelector('dialog [data-scada-viewer-dialog-error]').textContent, /control limits/);
    input.value = '65'; input.dispatchEvent(new dom.window.Event('change', {bubbles:true}));
    assert.equal(model.getSnapshot().demandPct, 65);
    assert.equal(input.hasAttribute('aria-invalid'), false);
    assert.equal(viewer.root.querySelector('dialog [data-scada-viewer-dialog-error]').hidden, true);
  } finally { viewer.destroy(); model.stop(); dom.window.close(); }
});

test('opt-in process layout fits the viewport while manual camera, selection and shared adapter remain independent', async () => {
  const document = JSON.parse(fs.readFileSync(new URL('../../../fixtures/scada/default-model-inputs/winery.system.json',import.meta.url)));
  const original = structuredClone(document), dom=setup(), snapshot={running:false,session:'unchanged'};
  let subscriptions=0, commands=0, reads=0;
  const adapter={getSnapshot:()=>{reads++;return snapshot;},subscribe:()=>{subscriptions++;return()=>subscriptions--;},dispatch:()=>commands++};
  const primary=new ScadaViewer({definition:document,adapter,fitMaxZoom:1.5,responsiveLayout:'process-chain'}).mount(dom.window.document.querySelector('#editable'));
  const observer=new ScadaViewer({definition:document,adapter:{getSnapshot:adapter.getSnapshot,subscribe:adapter.subscribe},fitMaxZoom:1.5,responsiveLayout:'process-chain'}).mount(dom.window.document.querySelector('#monitor'));
  try {
    let width=3320,height=950;
    for(const viewer of [primary,observer])Object.defineProperties(viewer.camera.viewport,{clientWidth:{get:()=>width},clientHeight:{get:()=>height}});
    primary.select('crusher');
    const beforeReads=reads;
    primary.camera.refresh();observer.camera.refresh();await Promise.resolve();await Promise.resolve();
    assert.equal(primary.view.layoutProjection.columns,5);assert.equal(observer.view.layoutProjection.columns,5);
    assert.equal(primary.selected,'crusher');assert.equal(primary.snapshot,snapshot);assert.equal(observer.snapshot,snapshot);
    assert.equal(reads,beforeReads,'presentation projection does not request a model reset or snapshot');
    assert.equal(subscriptions,2);assert.equal(commands,0);assert.equal(observer.readOnly,true);
    primary.setZoom(1.2);primary.camera.panBy(25,-10);
    const manual=primary.camera.state,oldView=primary.view;
    const worldCenter={x:(width/2-manual.x)/manual.zoom,y:(height/2-manual.y)/manual.zoom};
    width=1100;height=1000;primary.camera.refresh();observer.camera.refresh();await Promise.resolve();await Promise.resolve();
    assert.equal(primary.view,oldView,'manual resize keeps the chosen arrangement');
    const after=primary.camera.state;
    assert.equal(after.zoom,manual.zoom);assert.equal(after.fitted,false);
    assert.equal((width/2-after.x)/after.zoom,worldCenter.x);assert.equal((height/2-after.y)/after.zoom,worldCenter.y);
    assert.notEqual(observer.view.width,oldView.width,'fitted observer can adapt independently');
    primary.fit();await Promise.resolve();await Promise.resolve();
    assert.equal(primary.camera.state.fitted,true);assert.equal(primary.view.width,observer.view.width);
    assert.equal(primary.selected,'crusher');assert.deepEqual(document,original);assert.equal(commands,0);assert.equal(subscriptions,2);
    width=3320;height=950;primary.camera.refresh();primary.destroy();await Promise.resolve();assert.equal(subscriptions,1);
    assert.equal(observer.snapshot,snapshot);
  } finally {primary.destroy();observer.destroy();dom.window.close();}
  assert.equal(subscriptions,0);
});
