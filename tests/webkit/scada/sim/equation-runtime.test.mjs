import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createEquationRuntime,normalizeEquationBindings,validateDataSchema,validateSchemaValue,EQUATION_UNITS,EQUATION_PHASE_CONTRACTS} from '../../../../software/cadagent/webkit/scada/sim/src/equations/index.mjs';
import {createModelDefinition,validatePlaceholderModelDefinition} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';
import {formatEquationError} from '../../../../software/cadagent/webkit/scada/sim/src/equations/contracts.mjs';

const empty = {type:'object',additionalProperties:false,properties:{}};
const system = {system:{id:'equation-contract'},components:[{id:'first',type:'pump'},{id:'second',type:'pump'},{id:'store',type:'tank'}],connections:[]};
const bind = (id = 'test.rate',parameters = {}) => ({id,version:'1.0.0',parameters});
const equationDefinition = (selections = {types:{pump:bind()}}) => ({version:1,...selections});
function provider(overrides = {}) {
  return {id:'test.rate',version:'1.0.0',stateVersion:1,engines:[1,2],phases:['resource'],units:EQUATION_UNITS,
    parameterSchema:{type:'object',additionalProperties:false,properties:{rate:{type:'number',minimum:0,maximum:100}},required:['rate']},
    defaultParameters:{rate:25},stateSchema:{type:'object',additionalProperties:false,properties:{ticks:{type:'integer',minimum:0,maximum:1000}},required:['ticks']},
    initialize:() => ({ticks:0}),evaluate:(_phase,context) => ({capacity:context.parameters.rate + context.providerState.ticks}),
    advance:context => ({ticks:context.providerState.ticks + 1}),...overrides};
}
function runtime({equations = equationDefinition(),providers = [provider()],engineVersion = 2,initialize = true} = {}) {
  const definition = createModelDefinition(system,{version:engineVersion});
  if (equations !== undefined) definition.equations = equations;
  return createEquationRuntime({system,definition,engineVersion,providers,initialize});
}

test('selector precedence is component, type, engine family, with explicit built-in opt-out', () => {
  const equations = equationDefinition({families:{v2:{pump:bind('family'),storage:bind('family')}},types:{pump:bind('type')},components:{first:bind('component'),store:null}});
  const providers = [['family',10],['type',20],['component',30]].map(([id,rate]) => provider({id,defaultParameters:{rate}}));
  const run = runtime({equations,providers});
  assert.equal(run.evaluate('first','resource',{}, {capacity:1}).capacity,30);
  assert.equal(run.evaluate('second','resource',{}, {capacity:1}).capacity,20);
  assert.equal(run.has('store'),false);
  const family = runtime({equations:equationDefinition({families:{v2:{pump:bind('family')}},components:{first:null}}),providers});
  assert.equal(family.has('first'),false);
  assert.equal(family.evaluate('second','resource',{}, {capacity:1}).capacity,10);
  for (const bad of [equationDefinition({components:{typo:bind()}}),equationDefinition({types:{typo:bind()}}),equationDefinition({families:{v2:{typo:bind()}}}),{version:2},equationDefinition({source:'https://example.invalid/code.js'})]) assert.throws(() => normalizeEquationBindings(bad,{system}));
});

test('provider identity, engine support, phases, units and declarations are validated before callbacks', () => {
  let called = 0;
  const selected = provider({initialize:() => { called++; return {ticks:0}; }});
  for (const invalid of [[],[provider({version:'2.0.0'})],[provider({engines:[1]})],[provider({units:'SI'})],[provider({phases:['unknown']})],[provider({phases:['temperature'],engines:[1,2]})],[selected,selected],[provider({source:'return 10'})],[provider({initialize:async () => ({ticks:0})})]]) assert.throws(() => runtime({providers:invalid}));
  assert.equal(called,0);
});

test('parameter schemas reject unknown/out-of-domain input, without implicit coercion/defaults', () => {
  for (const parameters of [{rate:-1},{rate:'5'},{rate:101},{unknown:3},{rate:NaN}]) assert.throws(() => runtime({equations:equationDefinition({types:{pump:bind('test.rate',parameters)}})}));
  assert.equal(runtime().evaluate('first','resource',{}, {capacity:0}).capacity,25);
  const p = provider();delete p.defaultParameters;
  assert.throws(() => runtime({providers:[p]}),/Missing/);
  assert.throws(() => validateDataSchema({...empty,additionalProperties:true}),/additionalProperties/);
  assert.throws(() => validateDataSchema({...empty,$ref:'https://example.invalid/schema'}),/Unknown/);
  assert.throws(() => validateDataSchema({type:'number',default:5}),/Unknown/);
});

test('evaluation receives defensive frozen contexts and outputs cannot alias provider-owned objects', () => {
  const returned = {capacity:7};let received;
  const run = runtime({providers:[provider({evaluate:(_phase,context) => { received = context; return returned; }})]});
  const shared = {pressure:4}, context = {core:{enabled:true},readings:{one:shared,two:shared}};
  const output = run.evaluate('first','resource',context,{capacity:1});
  assert.equal(Object.isFrozen(received.readings.one),true);
  assert.equal(received.parameters.rate,25);
  assert.equal(received.equipment.family,'pump');
  assert.equal(received.engineVersion,2);
  assert.throws(() => { received.core.enabled = false; },TypeError);
  assert.throws(() => { received.providerState.ticks = 99; },TypeError);
  assert.equal(context.core.enabled,true);
  shared.pressure = 8;returned.capacity = 9;
  assert.equal(received.readings.one.pressure,4);
  assert.equal(output.capacity,7);
  assert.equal(Object.isFrozen(output),true);
});

test('pure evaluation never advances state; advance and checkpoint restore use owned JSON state', () => {
  const run = runtime();
  for (let i=0;i<10;i++) assert.equal(run.evaluate('first','resource',{}, {capacity:0}).capacity,25);
  const before = run.exportState(), token = run.checkpoint();
  run.advance('first',{dtMinutes:1,accepted:{resourceOut:5}});
  assert.equal(run.evaluate('first','resource',{}, {capacity:0}).capacity,26);
  const fork = run.fork();fork.advance('first',{});
  assert.equal(fork.exportState().components.first.state.ticks,2);
  assert.equal(run.exportState().components.first.state.ticks,1);
  run.restore(token);assert.deepEqual(run.exportState(),before);
  assert.throws(() => run.restore(fork.checkpoint()),/does not belong/);
  const exported = run.exportState();exported.components.first.state.ticks = 300;
  assert.equal(run.exportState().components.first.state.ticks,0);
});

test('saved provider identity, units, schema and resolved parameters must match; import never initializes', () => {
  let initialized = 0;
  const p = provider({initialize:() => { initialized++; return {ticks:0}; }}), run = runtime({providers:[p]});
  run.advance('first',{});
  const saved = run.exportState(), candidate = runtime({providers:[p],initialize:false});
  const count = initialized;
  candidate.importState(saved);assert.equal(initialized,count);assert.deepEqual(candidate.exportState(),saved);
  for (const mutate of [value => value.components.first.id='missing',value => value.components.first.version='2.0.0',value => value.components.first.stateVersion=2,value => value.components.first.units='SI',value => value.components.first.parameters.rate=4,value => value.components.first.schemaSignature='{}',value => value.components.first.state.ticks=-1,value => delete value.components.second,value => value.extra=1]) {
    const invalid = structuredClone(saved);mutate(invalid);
    assert.throws(() => candidate.importState(invalid));assert.deepEqual(candidate.exportState(),saved);
  }
  const changedSchema = provider({stateSchema:{...p.stateSchema,properties:{ticks:{type:'integer',minimum:0,maximum:2000}}}});
  assert.throws(() => runtime({providers:[changedSchema],initialize:false}).importState(saved),/schema/);
});

test('state and output errors leave prior runtime state unchanged', () => {
  for (const evaluate of [() => ({capacity:-1}),() => ({capacity:Infinity}),() => ({flow:10}),() => ({capacity:'5'}),() => Promise.resolve({capacity:5}),() => {throw new Error('law failed');}]) {
    const run = runtime({providers:[provider({evaluate})]}), saved = run.exportState();
    assert.throws(() => run.evaluate('first','resource',{}, {capacity:1}));assert.deepEqual(run.exportState(),saved);
  }
  for (const advance of [() => ({ticks:-1}),() => ({ticks:1,extra:1}),() => Promise.resolve({ticks:1})]) {
    const run = runtime({providers:[provider({advance})]}), saved = run.exportState();
    assert.throws(() => run.advance('first',{}));assert.deepEqual(run.exportState(),saved);
  }
});

test('reset initializes all selected state atomically and receives initial core context', () => {
  let failing = false;const contexts = [];
  const run = runtime({providers:[provider({initialize:context => { contexts.push(context);if(failing && context.equipment.id==='second')throw new Error('init failed');return{ticks:context.core?.initialTicks ?? 0}; }})]});
  run.advance('first',{});const before = run.exportState();failing = true;
  assert.throws(() => run.reset(() => ({core:{initialTicks:7}})),/init failed/);
  assert.deepEqual(run.exportState(),before);assert.equal(contexts.at(-1).providerState,null);
  failing = false;run.reset(() => ({core:{initialTicks:7}}));assert.equal(run.exportState().components.first.state.ticks,7);
});

test('binding replacements create candidate state without altering the existing runtime', () => {
  const original = runtime();original.advance('first',{});
  const definition = createModelDefinition(system,{version:2});definition.equations=equationDefinition({components:{first:bind('test.rate',{rate:80})}});
  const candidate = original.withDefinition(definition);
  assert.equal(candidate.evaluate('first','resource',{}, {capacity:0}).capacity,80);
  assert.equal(candidate.has('second'),false);
  assert.equal(original.evaluate('first','resource',{}, {capacity:0}).capacity,26);
  definition.equations.components.first=bind('missing');
  assert.throws(() => original.withDefinition(definition),/Missing/);
  assert.equal(original.evaluate('first','resource',{}, {capacity:0}).capacity,26);
});

test('unbound sessions preserve old defaults and omit all equation state', () => {
  const definition = createModelDefinition(system,{version:2});let calls = 0;
  const run = createEquationRuntime({system,definition,engineVersion:2,providers:[provider({initialize:()=>{calls++;return{ticks:0};}})]});
  const defaults = {capacity:42};assert.equal(run.evaluate('first','resource',{},defaults),defaults);
  assert.equal(calls,0);assert.equal(run.exportState(),undefined);assert.equal(run.hasBindings,false);
  run.importState(undefined);assert.throws(() => run.importState({version:1,components:{}}),/Unexpected/);
});

test('both model validators accept data-only bindings and reject executable/unknown selectors', () => {
  for (const version of [1,2]) {
    const plain = createModelDefinition(system,{version});
    const normalized = validatePlaceholderModelDefinition(system,plain);assert.equal(normalized.ok,true);
    assert.equal(Object.hasOwn(normalized.definition,'equations'),false);
    const definition = structuredClone(plain);definition.equations=equationDefinition();
    const result = validatePlaceholderModelDefinition(system,definition);assert.equal(result.ok,true,JSON.stringify(result.errors));
    assert.equal(Object.isFrozen(result.definition.equations),true);
    definition.equations.components={missing:bind()};assert.equal(validatePlaceholderModelDefinition(system,definition).ok,false);
    definition.equations=equationDefinition({types:{pump:{...bind(),evaluate:'return 10'}}});assert.equal(validatePlaceholderModelDefinition(system,definition).ok,false);
  }
});

test('schema values reject accessors and unsafe structures without executing them', () => {
  let read = 0;const input={};Object.defineProperty(input,'value',{enumerable:true,get(){read++;return 1;}});
  assert.throws(() => validateSchemaValue(empty,input));assert.equal(read,0);
  const cyclic={};cyclic.loop=cyclic;assert.throws(() => validateSchemaValue(empty,cyclic));
  assert.throws(() => validateDataSchema({type:'array',items:{type:'number'},minItems:3,maxItems:1}));
  assert.equal(EQUATION_PHASE_CONTRACTS.pressure.description.includes('v2 next'),true);
  assert.equal(EQUATION_PHASE_CONTRACTS.pressure.engineSemantics[1].stage,'response-target');
  assert.equal(EQUATION_PHASE_CONTRACTS.pressure.engineSemantics[2].stage,'next-state');
  assert.equal(EQUATION_PHASE_CONTRACTS.resource.engineUnits[1].includes('/ 10'),true);
});

test('unsupported rejected promises are consumed without invoking arbitrary thenables', async () => {
  const run = runtime({providers:[provider({evaluate:() => Promise.reject(new Error('async result'))})]});
  assert.throws(() => run.evaluate('first','resource',{}, {capacity:0}),/synchronously/);
  await new Promise(resolve => setImmediate(resolve));
  let getterCalls = 0;
  const thenable = {};Object.defineProperty(thenable,'then',{get(){getterCalls++;throw new Error('must not run');}});
  const other = runtime({providers:[provider({evaluate:() => thenable})]});
  assert.throws(() => other.evaluate('first','resource',{}, {capacity:0}),/synchronously/);
  assert.equal(getterCalls,0);
});

test('clock error formatting is bounded and never invokes message getters or object coercion', () => {
  let getters = 0,coercions = 0;
  const hostile = {get message(){getters++;throw new Error('getter');},toString(){coercions++;throw new Error('coercion');}};
  for (const value of [null,undefined,0,false,{},hostile,Object.create({message:'inherited'}),new Proxy({}, {getOwnPropertyDescriptor(){throw null;}})]) assert.equal(formatEquationError(value),'Equation provider failed.');
  assert.equal(getters,0);assert.equal(coercions,0);
  assert.equal(formatEquationError(new Error('provider failed')),'provider failed');
  assert.equal(formatEquationError('literal failure'),'literal failure');
  assert.equal(formatEquationError({message:'x'.repeat(1200)}).length,500);
  assert.equal(formatEquationError('x'.repeat(1200),1000).length,1000);
  assert.equal(formatEquationError('x'.repeat(1200),Infinity).length,500);
  assert.equal(formatEquationError('   '),'Equation provider failed.');
});

test('headless equation imports and state operations start no clocks or browser/network work', () => {
  const url = new URL('../../../../software/cadagent/webkit/scada/sim/src/equations/index.mjs',import.meta.url).href;
  const script = `for(const key of ['setInterval','setTimeout','fetch'])globalThis[key]=()=>{throw Error(key)};for(const key of ['window','document','localStorage'])Object.defineProperty(globalThis,key,{get(){throw Error(key)}});const{createEquationRuntime}=await import(${JSON.stringify(url)});const run=createEquationRuntime({system:{components:[]},definition:{components:{}},engineVersion:2});run.reset();run.fork();run.exportState();`;
  execFileSync(process.execPath,['--input-type=module','-e',script]);
});
