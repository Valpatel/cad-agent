import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {SYSTEM_DEFINITION_VERSION,validateSystemDefinition,resolveBinding,resolveComponentState} from '../../../../software/cadagent/webkit/scada/ui/src/contracts/system-definition.mjs';
import {SCADA_COMPONENTS,getScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const fixture = () => JSON.parse(readFileSync(new URL('../../../../software/cadagent/webkit/scada/ui/examples/minimal-system.json',import.meta.url)));
const valid = input => { const result=validateSystemDefinition(input); assert.equal(result.ok,true,JSON.stringify(result.errors)); return result.definition; };
const invalid = (change,code) => { const input=fixture(); change(input); const result=validateSystemDefinition(input); assert.equal(result.ok,false); assert.ok(result.errors.some(error=>error.code===code),JSON.stringify(result.errors)); assert.ok(result.errors.every(error=>typeof error.path==='string' && typeof error.message==='string')); return result; };

test('all base and explicitly selected variant contracts validate declared ports and typed default states',()=>{
  for(const base of SCADA_COMPONENTS)for(const variant of [undefined,...(base.variants??[]).map(item=>item.id)]){
    const selected=getScadaComponent(base.type,{variant});
    const component={id:'asset',type:base.type,...(variant?{variant}:{}),state:{...selected.defaultState},
      ports:selected.ports.map(port=>({id:port.id,side:'left'}))};
    const definition={format:'scada-system',version:1,system:{id:'selection',label:'Selection'},components:[component],
      views:[{id:'overview',canvas:{width:400,height:300},placements:[{component:'asset',x:20,y:20,width:230,height:240}]}]};
    const result=validateSystemDefinition(definition);
    assert.equal(result.ok,true,`${base.type}/${variant??'baseline'}: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(resolveComponentState(result.definition.components[0],{}).state,selected.defaultState);
    if(variant)assert.equal(result.definition.components[0].variant,variant);
  }
});

test('versioned example normalizes without mutating its authoring data and shares canonical instances across two views',()=>{
  const input=fixture(),before=structuredClone(input),definition=valid(input);
  assert.equal(SYSTEM_DEFINITION_VERSION,1); assert.deepEqual(input,before);
  assert.equal(definition.views.length,2);
  assert.deepEqual(definition.views.map(view=>view.placements.map(node=>node.component)),[['supplyPump','storageTank'],['supplyPump','storageTank']]);
  assert.equal(definition.components[0].ports[0].offset,.5);
  assert.ok(Object.isFrozen(definition) && Object.isFrozen(definition.components[0].bindings) && Object.isFrozen(definition.views[0].routes[0].points[0]));
  assert.throws(()=>definition.components.push({}),TypeError);
  assert.throws(()=>definition.components[0].bindings.active='/other',TypeError);
  const schema=JSON.parse(readFileSync(new URL('../../../../software/cadagent/webkit/scada/ui/schema/scada-system.schema.json',import.meta.url)));
  assert.equal(schema.$schema,'https://json-schema.org/draft/2020-12/schema');
  assert.equal(schema.$id,'urn:valpatel:scada-system:1'); assert.equal(schema.properties.version.const,definition.version);
});

test('unknown versions, fields, types and non-JSON values fail before a viewer can mount',()=>{
  invalid(d=>d.version=2,'version'); invalid(d=>d.components[0].type='magic-pump','unknown_type');
  invalid(d=>d.script='alert(1)','unknown_field'); invalid(d=>d.components[0].state.level=20,'unknown_field');
  for(const input of [null,[],true,{},new Date(),()=>{},'system: yaml'])assert.equal(validateSystemDefinition(input).ok,false);
  invalid(d=>d.assumptions[0].value=Infinity,'nonfinite'); invalid(d=>d.commands[0].arguments.bad=()=>{},'json_type');
  const cyclic=fixture();cyclic.commands[0].arguments.self=cyclic;assert.equal(validateSystemDefinition(cyclic).errors[0].code,'cycle');
});

test('cross-references reject duplicate equipment, unknown ports, dangling routes and commands',()=>{
  invalid(d=>d.components.push(structuredClone(d.components[0])),'duplicate');
  invalid(d=>d.connections[0].to.component='absent','reference');
  invalid(d=>d.connections[0].from.port='imaginary-outlet','port');
  invalid(d=>d.views[0].placements[0].component='absent','reference');
  invalid(d=>d.views[0].routes[0].connection='absent','reference');
  invalid(d=>d.controls[0].command='absent','reference');
  invalid(d=>d.components[0].provenance=['absent'],'reference');
  invalid(d=>d.views[0].placements.push(structuredClone(d.views[0].placements[0])),'duplicate');
  invalid(d=>d.components[0].ports[0].id='imaginary-port','port');
});

test('partial views may route to canonical off-view equipment without claiming physical compatibility',()=>{
  const input=fixture();input.views[0].placements.pop();input.connections[0].medium='illustrative-coupling';
  const definition=valid(input);assert.equal(definition.views[0].routes.length,1);assert.equal(definition.views[0].placements.length,1);
  assert.equal(definition.connections[0].to.component,'storageTank');
});

test('geometry and control bounds are finite, positive, coherent and inside the canvas',()=>{
  invalid(d=>d.views[0].canvas.width=0,'range');
  invalid(d=>d.views[0].placements[0].width=-1,'range');
  invalid(d=>d.views[0].placements[0].x=799,'bounds');
  invalid(d=>d.views[0].routes[0].points[0].y=401,'range');
  invalid(d=>d.views[0].routes[0].points=[{x:0,y:0}],'required');
  invalid(d=>d.components[0].ports[0].offset=2,'range');
  invalid(d=>d.controls[1].min=100,'range');
  invalid(d=>d.controls[1].step=0,'range');
  invalid(d=>delete d.controls[0].binding,'required');
  invalid(d=>d.controls[0].min=0,'control');
});

test('diagram actions explicitly name one component toggle and reject ambiguous declarations',()=>{
  const input=fixture(); input.controls[0].diagram={whenTrue:'Stop',whenFalse:'Start'};
  const normalized=valid(input); assert.deepEqual(normalized.controls[0].diagram,input.controls[0].diagram);
  for(const change of [
    d=>delete d.controls[0].component,
    d=>d.controls[0].kind='button',
    d=>d.controls[0].diagram.whenTrue='',
    d=>d.controls[0].diagram.whenFalse='x'.repeat(41),
    d=>d.controls[0].diagram.extra=true,
    d=>d.controls.push({...d.controls[0],id:'anotherToggle'}),
  ]){
    const candidate=structuredClone(input);change(candidate);
    assert.equal(validateSystemDefinition(candidate).ok,false,JSON.stringify(candidate.controls));
  }
});

test('authored visual fields and state bindings use the registry, not coercion or expressions',()=>{
  invalid(d=>d.components[0].state.active='true','state_type');
  invalid(d=>d.components[1].state.level=101,'state_type');
  invalid(d=>d.components[0].bindings.undeclaredField='/load','unknown_field');
  for(const pointer of ['state.pump.active','/a~2b','#/components/pump','return true','/constructor/prototype/value','/__proto__/value']){
    const result=validateSystemDefinition({...fixture(),components:[{id:'pump',type:'pump',bindings:{active:pointer}}]});
    assert.equal(result.ok,false);assert.ok(result.errors.some(error=>['invalid_pointer','blocked_pointer'].includes(error.code)),pointer);
  }
});

test('definition validation never reads accessors and blocks prototype or credential payloads',()=>{
  let invoked=0;const input=fixture();Object.defineProperty(input.commands[0].arguments,'value',{enumerable:true,get(){invoked++;return true;}});
  assert.equal(validateSystemDefinition(input).ok,false);assert.equal(invoked,0);
  for(const key of ['__proto__','constructor','prototype']){
    const payload=fixture();payload.commands[0].arguments=JSON.parse(`{"${key}":{"polluted":true}}`);
    assert.ok(validateSystemDefinition(payload).errors.some(error=>error.code==='unsafe_key'));
  }
  for(const key of ['password','apiKey','access_token','authorization'])invalid(d=>d.commands[0].arguments[key]='do-not-store','credential');
  assert.equal({}.polluted,undefined);
});

test('JSON Pointer resolves escaped keys and arrays using only own data properties',()=>{
  const snapshot={'a/b':{'~level':42},items:[{value:7}],blank:null,missing:undefined};
  assert.deepEqual(resolveBinding(snapshot,'/a~1b/~0level'),{found:true,value:42});
  assert.deepEqual(resolveBinding(snapshot,'/items/0/value'),{found:true,value:7});
  assert.deepEqual(resolveBinding(snapshot,'/blank'),{found:true,value:null});
  assert.equal(resolveBinding(snapshot,'/missing').found,false);assert.equal(resolveBinding(snapshot,'/absent').found,false);
  assert.equal(resolveBinding(snapshot,'/items/99').found,false);
  assert.equal(resolveBinding(snapshot,'/toString').found,false);
  assert.equal(resolveBinding(Object.create({value:99}),'/value').found,false);
  let invoked=0;const getters={};Object.defineProperty(getters,'value',{get(){invoked++;return 7;}});
  assert.equal(resolveBinding(getters,'/value').found,false);assert.equal(invoked,0);
  for(const path of ['/__proto__','/constructor','/prototype','$.x','/x~9'])assert.equal(resolveBinding(snapshot,path).found,false);
});

test('bound updates reach the same component in both layouts without cached state',()=>{
  const definition=valid(fixture()),tank=definition.components[1];
  const snapshot={components:{supplyPump:{active:true,fault:false},storageTank:{active:true,level:73}},flows:{fillLine:true}};
  for(const view of definition.views){assert.ok(view.placements.some(item=>item.component===tank.id));const state=resolveComponentState(tank,snapshot);assert.equal(state.ok,true);assert.equal(state.state.level,73);assert.equal(state.state.active,true);}
  snapshot.components.storageTank.level=18;assert.equal(resolveComponentState(tank,snapshot).state.level,18);
  assert.equal(tank.state.level,40);assert.equal(Object.isFrozen(snapshot),false);
});

test('missing, undefined or invalid readings retain authored fallbacks but become offline',()=>{
  const tank=valid(fixture()).components[1];
  for(const level of [undefined,null,'70',NaN,101]){
    const result=resolveComponentState(tank,{components:{storageTank:{active:true,level}}});
    assert.equal(result.ok,false);assert.equal(result.state.active,false);assert.equal(result.state.status,'offline');assert.equal(result.state.level,40);assert.ok(result.errors.length);
  }
  const absent=resolveComponentState(tank,{});assert.equal(absent.ok,false);assert.equal(absent.state.level,40);
});

test('a partial reading binding never implies an operating machine; absent unbound state is offline',()=>{
  const tank={id:'tank',type:'tank',bindings:{level:'/level'}};
  const result=resolveComponentState(tank,{level:60});assert.equal(result.ok,true);assert.equal(result.state.active,false);assert.equal(result.state.level,60);
  const missing=resolveComponentState({id:'pump',type:'pump'},{});assert.equal(missing.ok,false);assert.equal(missing.state.status,'offline');
  const staticState=resolveComponentState({id:'tank',type:'tank',state:{level:35}},{});assert.equal(staticState.ok,true);assert.equal(staticState.state.active,false);
  const supplied=resolveComponentState({id:'pump',type:'pump'},{components:{pump:{active:true}}});assert.equal(supplied.ok,true);assert.equal(supplied.state.active,true);
});

test('adapter-supplied state cannot trigger accessors or pollute a prototype',()=>{
  let invoked=0;const state={};Object.defineProperty(state,'active',{enumerable:true,get(){invoked++;return true;}});
  const result=resolveComponentState({id:'pump',type:'pump'},{components:{pump:state}});
  assert.equal(invoked,0);assert.equal(result.ok,false);assert.equal(result.state.status,'offline');
  const malicious=JSON.parse('{"__proto__":{"polluted":true},"active":true}');
  assert.equal(resolveComponentState({id:'pump',type:'pump'},{components:{pump:malicious}}).ok,false);assert.equal({}.polluted,undefined);
});
