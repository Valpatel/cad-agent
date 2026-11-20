import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {JSDOM} from '../dependencies.mjs';
import {
  SCADA_COMPONENTS,getScadaComponent,getScadaVariants,
  normalizeScadaState,renderScadaComponent,
} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';
import {findScadaComponents,getScadaFacets} from '../../../../software/cadagent/webkit/scada/ui/src/catalog/discovery.mjs';
import {validateSystemDefinition,resolveComponentState} from '../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';

test('discovery is deterministic, orthogonal and includes variant capabilities',()=>{
  const all=findScadaComponents();
  assert.equal(all.length,SCADA_COMPONENTS.length);
  assert.deepEqual(all.map(item=>item.type),all.map(item=>item.type).sort());
  assert.deepEqual(findScadaComponents({fuel:'diesel'}).map(item=>item.type),['generator']);
  assert.deepEqual(findScadaComponents({fuel:'diesel',medium:'liquid',modelSupport:'visual-only'}).map(item=>item.type),['generator']);
  assert.equal(findScadaComponents({query:'portable gasoline'})[0].type,'generator');
  assert.equal(findScadaComponents({technology:'boiling-water-reactor'})[0].type,'bwr-reactor-vessel');
  assert.equal(findScadaComponents({type:'pump',medium:'gas'})[0].type,'pump','explicit helium variant is discoverable');
  assert.deepEqual(findScadaComponents({category:'nuclear',fuel:'diesel'}),[]);
  assert.ok(findScadaComponents({category:['nuclear','climate']}).every(item=>['nuclear','climate'].includes(item.category)));
  assert.ok(Object.isFrozen(all));assert.ok(Object.isFrozen(getScadaFacets()));
  assert.ok(getScadaFacets().technology.includes('gas-insulated-switchgear'));
});

test('queries and variant selections reject inherited or executable input',()=>{
  let called=false;
  for(const value of [null,[],Object.create({query:'pump'}),{misspelled:'power'}])assert.throws(()=>findScadaComponents(value),TypeError);
  assert.throws(()=>findScadaComponents({get query(){called=true;return 'pump';}}),TypeError);
  const list=[];Object.defineProperty(list,'0',{get(){called=true;return 'power';},enumerable:true});
  assert.throws(()=>findScadaComponents({category:list}),TypeError);
  assert.equal(called,false);
  for(const variant of [null,4,{},'invented'])assert.throws(()=>getScadaComponent('generator',{variant}));
  assert.throws(()=>getScadaComponent('generator',Object.create({variant:'diesel-skid'})),TypeError);
});

test('variants resolve explicit fuel ports, carriers, circuits and power domains without mutation',()=>{
  const before=JSON.stringify(SCADA_COMPONENTS);
  const diesel=getScadaComponent('generator',{variant:'diesel-skid'});
  assert.ok(diesel.ports.some(port=>port.id==='liquid-fuel'&&port.medium==='liquid'));
  assert.ok(!diesel.ports.some(port=>port.id==='fuel'));
  assert.ok(!getScadaComponent('generator').ports.some(port=>port.id==='liquid-fuel'));
  const helium=getScadaComponent('nuclear-steam-generator',{variant:'helium-primary'});
  assert.equal(helium.ports.find(port=>port.id==='primary-in').medium,'gas');
  assert.equal(helium.circuits.find(circuit=>circuit.id==='primary').fluid,'helium');
  assert.equal(helium.circuits.find(circuit=>circuit.id==='secondary').fluid,'secondary-water');
  const exchanger=getScadaComponent('heat-exchanger',{variant:'sodium-sodium'});
  assert.deepEqual(exchanger.circuits.map(circuit=>circuit.id),['hot','cold']);
  assert.ok(exchanger.circuits.every(circuit=>circuit.fluid==='sodium'));
  assert.equal(getScadaComponent('disconnect-switch',{variant:'dc-isolator'}).powerDomains.line,'dc');
  assert.equal(getScadaComponent('solar-panel').powerDomains.dc,'dc');
  const flash=getScadaComponent('separator',{variant:'flash-water'});
  assert.equal(flash.ports.find(port=>port.id==='gas').medium,'steam');
  assert.deepEqual(flash.circuits[0].ports,['inlet','outlet','gas','drain']);
  assert.equal(JSON.stringify(SCADA_COMPONENTS),before);
  assert.throws(()=>normalizeScadaState('power-inverter',{direction:'reverse'}),TypeError);
  assert.equal(normalizeScadaState('power-inverter',{direction:'reverse'},{variant:'bidirectional'}).direction,'reverse');
});

test('all registered variant selections render safely while live generator art stays stable',()=>{
  let count=0;
  for(const descriptor of SCADA_COMPONENTS)for(const variant of getScadaVariants(descriptor.type)){
    const markup=renderScadaComponent(descriptor.type,{variant:variant.id});
    assert.ok(markup.includes('<svg'));assert.ok(!/undefined|NaN/.test(markup),`${descriptor.type}/${variant.id}`);count++;
  }
  assert.ok(count>SCADA_COMPONENTS.length/2);
  assert.match(renderScadaComponent('generator'),/twin-art-generator-enclosure/);
  assert.match(renderScadaComponent('generator',{hostState:true}),/twin-art-generator-enclosure/);
  assert.match(renderScadaComponent('generator',{variant:'gasoline-portable'}),/scada-genset/);
  assert.throws(()=>renderScadaComponent('generator',{variant:'diesel-skid',hostState:true}),/hostState/);
});

function oneComponent(type,variant) {
  return {format:'scada-system',version:1,system:{id:'example',label:'Example'},
    components:[{id:'unit',type,...(variant===undefined?{}:{variant})}],
    views:[{id:'overview',canvas:{width:300,height:300},placements:[{component:'unit',x:10,y:10,width:210,height:210}]}]};
}

test('portable definitions retain variant identity and validate effective endpoints and bound states',()=>{
  const input=oneComponent('generator','diesel-skid');
  input.components[0].ports=[{id:'liquid-fuel',side:'left'}];
  const good=validateSystemDefinition(input);
  assert.equal(good.ok,true,JSON.stringify(good.errors));
  assert.equal(good.definition.components[0].variant,'diesel-skid');
  input.components[0].ports=[{id:'fuel',side:'left'}];
  assert.equal(validateSystemDefinition(input).ok,false,'diesel must not reinterpret a gas port');
  assert.equal(validateSystemDefinition(oneComponent('tank','diesel-skid')).ok,false);
  assert.equal(validateSystemDefinition(oneComponent('tank',null)).ok,false);
  const instance={type:'power-inverter',variant:'bidirectional',state:{active:true},bindings:{direction:'/direction'}};
  assert.equal(resolveComponentState(instance,{direction:'reverse'}).state.direction,'reverse');
  assert.equal(resolveComponentState({...instance,variant:'dc-to-ac'},{direction:'reverse'}).ok,false);
});

test('failed instruments mark their numeric gauges unavailable, including accessible descriptions',()=>{
  for(const type of ['neutron-monitor','radiation-monitor','water-quality-probe','humidity-sensor','light-sensor','pressure-transmitter']){
    const dom=new JSDOM(renderScadaComponent(type,{state:{fault:true}}));
    try{
      assert.match(dom.window.document.querySelector('[role=img]').getAttribute('aria-label'),/unavailable/);
      for(const reading of dom.window.document.querySelectorAll('[data-scada-reading]'))assert.equal(reading.textContent,'—');
    }finally{dom.window.close();}
  }
});

test('workspace styling is host-neutral and supports normal class-specific consumer overrides',async()=>{
  const css=await readFile(new URL('../../../../software/cadagent/webkit/scada/ui/src/workspace/workspace.css',import.meta.url),'utf8');
  assert.ok(!css.includes('#main'),'the reusable package has no host ID dependency or imported ID specificity');
  assert.match(css,/\.scada-workspace \.scada-toolbutton\{/);
});
