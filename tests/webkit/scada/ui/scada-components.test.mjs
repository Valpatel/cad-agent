import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {SCADA_COMPONENTS,SCADA_CATEGORIES,getScadaComponent,normalizeScadaState,renderScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

test('the registry documents distinct assets, typed controls, ports and model boundaries',()=>{
 assert.ok(SCADA_COMPONENTS.length>0);
 assert.equal(new Set(SCADA_COMPONENTS.map(item=>item.type)).size,SCADA_COMPONENTS.length);
 const categories=new Set(SCADA_CATEGORIES.map(category=>category.id));
 assert.equal(categories.size,SCADA_CATEGORIES.length);
 for(const item of SCADA_COMPONENTS){
  assert.equal(item.id,item.type);assert.equal(item.name,item.label);
  assert.ok(categories.has(item.category));assert.ok(item.description.length>25);
  assert.strictEqual(getScadaComponent(item.type),item);
  assert.ok(Object.isFrozen(item));assert.ok(Object.isFrozen(item.stateFields));assert.ok(Object.isFrozen(item.defaultState));
  assert.ok(['shared-model','visual-only'].includes(item.modelSupport.kind));
  assert.match(item.modelSupport.description,/no physics|no process/i);
  assert.match(item.provenance,/original/i);
  assert.match(item.provenance,/illustrative|not a vendor|no vendor/i);
  assert.ok(item.ports.length>0);assert.equal(new Set(item.ports.map(port=>port.id)).size,item.ports.length);
  for(const port of item.ports){assert.ok(port.label&&port.medium);assert.ok(['in','out','bidirectional'].includes(port.direction));}
  assert.equal(new Set(item.stateFields.map(field=>field.key)).size,item.stateFields.length);
  for(const key of ['active','running','fault','status'])assert.ok(item.stateFields.some(field=>field.key===key));
  assert.deepEqual(normalizeScadaState(item.type),item.defaultState);
  for(const field of item.stateFields){
   assert.ok(field.label);assert.ok(['boolean','number','select'].includes(field.type));
   if(field.type==='number'){assert.ok(Number.isFinite(field.min)&&Number.isFinite(field.max));assert.ok(field.min<field.max);}
   if(field.type==='select')assert.ok(field.options.some(option=>option.value===field.default));
  }
 }
 assert.throws(()=>getScadaComponent('__proto__'),RangeError);
 assert.throws(()=>getScadaComponent('unimplemented-pump'),RangeError);
});

test('normalization rejects invalid types, unknown keys, inherited state and accessors',()=>{
 for(const item of SCADA_COMPONENTS){
  for(const field of item.stateFields){
   for(const bad of [null,undefined,{},[],NaN,Infinity])assert.throws(()=>normalizeScadaState(item.type,{[field.key]:bad}),TypeError,`${item.type}/${field.key} rejects invalid values`);
   if(field.type==='boolean')for(const bad of [0,1,'true','false'])assert.throws(()=>normalizeScadaState(item.type,{[field.key]:bad}),TypeError);
   if(field.type==='number'){
    assert.throws(()=>normalizeScadaState(item.type,{[field.key]:'42'}),TypeError);
    assert.equal(normalizeScadaState(item.type,{[field.key]:field.min-100})[field.key],field.min);
    assert.equal(normalizeScadaState(item.type,{[field.key]:field.max+100})[field.key],field.max);
   }
   if(field.type==='select')assert.throws(()=>normalizeScadaState(item.type,{[field.key]:'invented'}),TypeError);
  }
  assert.throws(()=>normalizeScadaState(item.type,{accidentalSetting:true}),/Unknown/);
  assert.throws(()=>normalizeScadaState(item.type,Object.create({active:false})),/plain own-property/);
  assert.throws(()=>normalizeScadaState(item.type,JSON.parse('{"__proto__":{"active":false}}')),/Unknown/);
  assert.throws(()=>normalizeScadaState(item.type,{[Symbol('active')]:false}),/Unknown/);
 }
 let getterCalled=false;
 assert.throws(()=>normalizeScadaState('pump',{get active(){getterCalled=true;return false;}}),/not accessors/);
 assert.equal(getterCalled,false,'validation does not execute an accessor');
 assert.equal(normalizeScadaState('pump',Object.assign(Object.create(null),{active:false})).active,false);
 const supplied=Object.freeze({active:false,fault:true});
 assert.deepEqual(normalizeScadaState('pump',supplied),{...getScadaComponent('pump').defaultState,active:false,fault:true});
 assert.deepEqual(supplied,{active:false,fault:true},'normalization does not mutate input');
});

test('every type renders standalone with local fragment references and unique automatic instance IDs',()=>{
 const html=SCADA_COMPONENTS.flatMap(item=>[renderScadaComponent(item.type),renderScadaComponent(item.type)]).join('');
 const dom=new JSDOM(html),document=dom.window.document;
 try{
  const wrappers=[...document.querySelectorAll('.scada-component')];assert.equal(wrappers.length,SCADA_COMPONENTS.length*2);
  const instances=wrappers.map(node=>node.dataset.scadaInstance);assert.equal(new Set(instances).size,instances.length);
  const ids=[...document.querySelectorAll('[id]')].map(node=>node.id);assert.equal(new Set(ids).size,ids.length);
  for(const wrapper of wrappers){
   assert.equal(wrapper.getAttribute('role'),'img');assert.ok(wrapper.getAttribute('aria-label'));
   assert.equal(wrapper.dataset.scadaHostState,'false');assert.ok(wrapper.querySelector('svg'));
   for(const element of wrapper.querySelectorAll('*'))for(const attribute of element.attributes){
    for(const match of attribute.value.matchAll(/url\(#([^)]*)\)/g))assert.ok(wrapper.querySelector(`[id="${match[1]}"]`),`${wrapper.dataset.scadaType} owns ${match[1]}`);
    assert.ok(!/^on/i.test(attribute.name),'drawing has no inline event handler');
   }
  }
 }finally{dom.window.close();}
});

test('labels are escaped, invalid IDs are rejected and decorative instances do not compete with host names',()=>{
 const label='Feed <img src=x onerror=alert(1)> "A" & B';
 const dom=new JSDOM(renderScadaComponent('pump',{id:'feed_01-east',label})+renderScadaComponent('pump',{decorative:true}));
 try{
  const [named,decorative]=dom.window.document.querySelectorAll('.scada-component');
  assert.ok(named.getAttribute('aria-label').startsWith(label));assert.equal(named.querySelector('img'),null);
  assert.equal(decorative.getAttribute('aria-hidden'),'true');assert.equal(decorative.getAttribute('role'),null);
  assert.equal(decorative.getAttribute('aria-label'),null);
 }finally{dom.window.close();}
 for(const id of ['',1,'1pump','pump.a','a b','a"/><script>bad</script>','a/b',Object.create(null)])assert.throws(()=>renderScadaComponent('pump',{id}),TypeError);
 assert.throws(()=>renderScadaComponent('pump',{decorative:'true'}),TypeError);
 assert.throws(()=>renderScadaComponent('pump',{hostState:1}),TypeError);
});

test('visual state suppresses production activity for failures, offline and disconnected equipment',()=>{
 for(const item of SCADA_COMPONENTS){
  for(const override of [{active:false},{fault:true},{status:'offline'},...(item.stateFields.some(field=>field.key==='connected')?[{connected:false}]:[])]){
   const dom=new JSDOM(renderScadaComponent(item.type,{state:override}));
   try{const wrapper=dom.window.document.querySelector('.scada-component');assert.equal(wrapper.dataset.active,'false',`${item.type} reflects ${JSON.stringify(override)}`);assert.equal(wrapper.dataset.flow,'false');}
   finally{dom.window.close();}
  }
 }
 for(const type of ['gate-valve','control-valve','check-valve','relief-valve','butterfly-valve','pipe','junction','breaker']){
  for(const open of [false,true]){
   const dom=new JSDOM(renderScadaComponent(type,{state:{open}}));
   try{const wrapper=dom.window.document.querySelector('.scada-component');assert.equal(wrapper.dataset.open,String(open));assert.equal(wrapper.dataset.flow,String(type==='breaker'?!open:open),'an open breaker interrupts its electrical path');}
   finally{dom.window.close();}
  }
 }
});

test('declared fill and load fields have observable gauges while live hosts keep model variables',()=>{
 for(const item of SCADA_COMPONENTS){
  for(const key of ['level','load'].filter(key=>item.stateFields.some(field=>field.key===key))){
   const dom=new JSDOM(renderScadaComponent(item.type,{state:{[key]:73}}));
   try{
    const gauge=dom.window.document.querySelector(`[data-scada-gauge="${key}"]`);
    assert.ok(gauge,`${item.type} visibly represents ${key}`);
    assert.equal(gauge.querySelector('b').style.width,'73%');assert.equal(gauge.querySelector('strong').textContent,'73%');
   }finally{dom.window.close();}
  }
 }
 for(const type of ['digester','gas-holder','gas-treatment','boiler','flare','pump','generator','electrical-meter']){
  const dom=new JSDOM(renderScadaComponent(type,{id:`live-${type}`,hostState:true,decorative:true}));
  try{
   const wrapper=dom.window.document.querySelector('.scada-component');
   assert.equal(wrapper.dataset.scadaHostState,'true');assert.equal(wrapper.getAttribute('style'),null,'live host custom properties remain inherited');
   assert.ok(wrapper.querySelector('.twin-equipment-art'),'live art uses the shared existing drawing');
   assert.equal(wrapper.querySelector('.scada-component-gauges'),null,'host metrics remain owned by the twin button');
  }finally{dom.window.close();}
 }
});

test('variable valves interpolate physical opening and an explicit close overrides their position',()=>{
 for(const type of ['gate-valve','control-valve','butterfly-valve']){
  const doc=new JSDOM([0,50,100].map(opening=>renderScadaComponent(type,{state:{opening}})).join('')+renderScadaComponent(type,{state:{open:false,opening:73}})+renderScadaComponent(type,{state:{open:true}}));
  try{
   const [closed,half,full,overridden,legacy]=doc.window.document.querySelectorAll('.scada-component');
   for(const [node,opening] of [[closed,0],[half,50],[full,100],[overridden,0],[legacy,100]]){
    assert.equal(node.dataset.opening,String(opening));
    assert.equal(node.dataset.flow,String(opening>0));
    assert.equal(node.querySelector('[data-scada-reading="opening"]').textContent,`${opening}%`);
    assert.equal(Number(node.style.getPropertyValue('--scada-flow-opacity')),.95*opening/100);
   }
   const position=node=>{
    const disc=node.querySelector('.scada-valve-disc');
    return type==='butterfly-valve'?Number(disc.getAttribute('rx')):Number(disc.style.transform.match(/translateY\(([-\d.]+)px\)/)[1]);
   };
   assert.equal(position(half),(position(closed)+position(full))/2,'half opening moves the physical disc halfway');
   assert.equal(position(overridden),position(closed),'the closed command overrides a nonzero position');
   assert.equal(position(legacy),position(full),'boolean-only open remains fully open');
  }finally{doc.window.close();}
 }
});

test('every standalone component exposes distinct warning and fault cues without contradicting stopped state',()=>{
 for(const item of SCADA_COMPONENTS){
  const dom=new JSDOM(renderScadaComponent(item.type,{state:{status:'warning',running:false}})+renderScadaComponent(item.type,{state:{fault:true,running:false}}));
  try{
   const [warning,fault]=dom.window.document.querySelectorAll('.scada-component');
   assert.ok(warning.querySelector('[data-condition="warning"]'),`${item.type} has a visible warning symbol`);
   assert.match(warning.getAttribute('aria-label'),/Warning/);
   assert.ok(fault.querySelector('[data-condition="fault"]'),`${item.type} has a visible fault symbol`);
   assert.match(fault.getAttribute('aria-label'),/Fault/);assert.equal(fault.dataset.active,'false');
  }finally{dom.window.close();}
 }
 for(const state of [{fault:true},{status:'offline'},{active:false}]){
  const dom=new JSDOM(renderScadaComponent('dosing-pump',{state}));
  try{assert.equal(dom.window.document.querySelector('.scada-readout').textContent,'OFF','local display agrees with suppressed effective activity');}
  finally{dom.window.close();}
 }
 const dom=new JSDOM(renderScadaComponent('digester',{hostState:true,state:{fault:true}}));
 try{assert.equal(dom.window.document.querySelector('.scada-component-condition'),null,'the live host owns its own fault presentation');}
 finally{dom.window.close();}
});

test('every declared damage mode has physical SVG geometry and every numeric endpoint remains readable',()=>{
 const physicalShape='path,rect,circle,ellipse,line,polyline,polygon';
 const geometrySignatures=wrapper=>new Set([...wrapper.querySelectorAll(physicalShape)].filter(shape=>shape.closest('svg')&&!shape.closest('defs,.scada-component-condition')).map(shape=>{
  const transforms=[];
  for(let node=shape;node&&node!==wrapper;node=node.parentElement)transforms.push([node.getAttribute('transform'),node.style.transform]);
  return shape.outerHTML+JSON.stringify(transforms);
 }));
 for(const item of SCADA_COMPONENTS){
  const damage=item.stateFields.find(field=>field.key==='damage');assert.ok(damage,`${item.type} declares damage choices`);
  const id='damage-contract-'+item.type,baseline=new JSDOM(renderScadaComponent(item.type,{id}));
  const baselineGeometry=geometrySignatures(baseline.window.document.querySelector('.scada-component'));
  baseline.window.close();
  for(const option of damage.options){
   const dom=new JSDOM(renderScadaComponent(item.type,{id,state:{damage:option.value}}));
   try{
    const wrapper=dom.window.document.querySelector('.scada-component');
    assert.equal(wrapper.dataset.damage,option.value);
    if(option.value!=='none'){
     const shape=wrapper.querySelector(`[data-damage="${option.value}"].scada-damage-art,[data-industrial-damage="${option.value}"],[data-power-damage="${option.value}"],[data-agri-damage="${option.value}"],[data-nuclear-damage="${option.value}"] > :last-child`);
     const hookedGeometry=shape&&(shape.matches(physicalShape)||shape.querySelector(physicalShape));
     // Equipment-specific incidents can alter the main drawing rather than
     // append to a generic damage group (for example condenser air bubbles).
     // Same-ID comparisons exclude the condition badge and label-only changes.
     const damagedGeometry=geometrySignatures(wrapper);
     const changedGeometry=[...damagedGeometry].some(signature=>!baselineGeometry.has(signature))||[...baselineGeometry].some(signature=>!damagedGeometry.has(signature));
     assert.ok(hookedGeometry||changedGeometry,`${item.type}/${option.value} is more than a text label`);
     assert.ok(wrapper.getAttribute('aria-label').includes(`damage: ${option.value.replaceAll('-',' ')}`));
    }
   }finally{dom.window.close();}
  }
  for(const field of item.stateFields.filter(field=>field.type==='number')){
   for(const value of [field.min,(field.min+field.max)/2,field.max]){
    const dom=new JSDOM(renderScadaComponent(item.type,{state:{[field.key]:value}}));
    try{
     const reading=dom.window.document.querySelector(`[data-scada-reading="${field.key}"]`);
     assert.ok(reading,`${item.type}/${field.key} has a keyed readable value`);
     const unit=field.unit==='index'?'idx':field.unit||'';
     assert.equal(reading.textContent,`${Number(value.toFixed(1))}${unit&&unit!=='%'?' ':''}${unit}`);
     const bar=reading.closest('[data-scada-gauge]').querySelector('b');
     assert.equal(Number.parseFloat(bar.style.width),100*(value-field.min)/(field.max-field.min));
    }finally{dom.window.close();}
   }
  }
 }
});

test('shared live assets preserve their equipment-specific art and automation has distinct silhouettes',()=>{
 const dom=new JSDOM(['pump','generator','gas-holder','boiler','plc-rack','plc-cpu','remote-io','hmi','scada-server','network-switch','radio'].map(type=>renderScadaComponent(type)).join(''));
 try{
  const component=type=>dom.window.document.querySelector(`[data-scada-type="${type}"]`);
  assert.ok(component('pump').querySelector('.twin-art-pump-body'));
  assert.equal(component('pump').querySelector('.twin-art-generator-enclosure'),null);
  assert.ok(component('generator').querySelector('.twin-art-generator-enclosure'));
  assert.ok(component('generator').querySelector('.twin-art-generator-electric'));
  assert.ok(component('gas-holder').querySelector('[data-twin-buffer-liquid]'));
  assert.ok(component('boiler').querySelector('.twin-art-fire'));
  const silhouettes=['plc-rack','plc-cpu','remote-io','hmi','scada-server','network-switch','radio'].map(type=>component(type).querySelector('.scada-drawing').innerHTML.replaceAll(component(type).dataset.scadaInstance,'INSTANCE'));
  assert.equal(new Set(silhouettes).size,7,'automation components are separate drawings, not label aliases');
 }finally{dom.window.close();}
});
