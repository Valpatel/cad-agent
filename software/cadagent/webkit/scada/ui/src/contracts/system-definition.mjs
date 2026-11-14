/** Versioned, data-only SCADA presentation definitions. No IO, timers or eval. */
import {getScadaComponent, normalizeScadaState} from '../catalog/registry.mjs';

export const SYSTEM_DEFINITION_VERSION = 1;
const ID = /^[A-Za-z][A-Za-z0-9_-]{0,99}$/;
const BLOCKED = new Set(['__proto__', 'prototype', 'constructor']);
const CREDENTIALS = new Set(['password', 'secret', 'token', 'accesstoken', 'refreshtoken', 'apikey', 'privatekey', 'credentials', 'authorization']);
const own = (object, key) => object !== null && typeof object === 'object' && Object.hasOwn(object, key);
const plain = value => value && typeof value === 'object' && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
const pointerPath = (path, key) => `${path}/${String(key).replaceAll('~', '~0').replaceAll('/', '~1')}`;
const issue = (path, code, message) => ({path, code, message});

function pointerTokens(pointer) {
  if (typeof pointer !== 'string' || pointer.length > 2048 || (pointer !== '' && !pointer.startsWith('/')) || /~(?![01])/.test(pointer))
    return {error: {code:'invalid_pointer', message:'Use an RFC 6901 JSON Pointer, with ~0 and ~1 escapes; expressions and URI fragments are not supported.'}};
  const tokens = pointer === '' ? [] : pointer.slice(1).split('/').map(token => token.replaceAll('~1', '/').replaceAll('~0', '~'));
  if (tokens.some(token => BLOCKED.has(token))) return {error:{code:'blocked_pointer', message:'Prototype traversal is forbidden.'}};
  return {tokens};
}

/** Never follows a prototype, invokes an accessor, evaluates text, or coerces values. */
export function resolveBinding(snapshot, pointer) {
  const parsed = pointerTokens(pointer);
  if (parsed.error) return {found:false, error:parsed.error};
  let value = snapshot;
  for (const token of parsed.tokens) {
    if (!value || typeof value !== 'object' || (!plain(value) && !Array.isArray(value)))
      return {found:false, error:{code:'missing_binding', message:`Cannot resolve ${pointer}.`}};
    const descriptor = Object.getOwnPropertyDescriptor(value, token);
    if (!descriptor) return {found:false, error:{code:'missing_binding', message:`Cannot resolve ${pointer}.`}};
    if (!Object.hasOwn(descriptor, 'value')) return {found:false, error:{code:'accessor_binding', message:'Accessor properties cannot supply bindings.'}};
    value = descriptor.value;
  }
  if (value === undefined) return {found:false, error:{code:'missing_binding', message:`The binding ${pointer} is undefined.`}};
  return {found:true, value};
}

function validStateValue(field, value) {
  if (field.type === 'boolean') return typeof value === 'boolean';
  if (field.type === 'number') return typeof value === 'number' && Number.isFinite(value) && value >= field.min && value <= field.max;
  return typeof value === 'string' && field.options.some(option => option.value === value);
}

/** Read bindings once per external snapshot. Missing readings are visibly offline. */
export function resolveComponentState(instance, snapshot) {
  const errors = [];
  let descriptor;
  try { descriptor = getScadaComponent(instance.type,{variant:instance.variant}); }
  catch { return {ok:false, state:null, errors:[issue('/type','unknown_selection','Unknown component type or variant.')]}; }
  const fields = new Map(descriptor.stateFields.map(field => [field.key, field]));
  const source = {};
  const copyState = (value,path) => {
    if (!plain(value)) { errors.push(issue(path,'invalid_bound_state','Visual state must be a plain object.')); return; }
    for (const key of Reflect.ownKeys(value)) {
      const property=Object.getOwnPropertyDescriptor(value,key);
      if (typeof key!=='string' || !fields.has(key) || !Object.hasOwn(property,'value') || !validStateValue(fields.get(key),property.value)) {
        errors.push(issue(pointerPath(path,key),'invalid_bound_state','Visual states require declared own data properties with valid values.'));
      } else source[key]=property.value;
    }
  };
  if (instance.state) copyState(instance.state,'/state');
  const bindings = instance.bindings || {};
  if (Object.keys(bindings).length) {
    for (const [key, pointer] of Object.entries(bindings)) {
      const result = resolveBinding(snapshot, pointer);
      if (!result.found) errors.push(issue(`/bindings/${key}`, result.error.code, result.error.message));
      else if (!fields.has(key) || !validStateValue(fields.get(key), result.value)) errors.push(issue(`/bindings/${key}`,'invalid_bound_state',`The binding for ${key} does not match its declared visual type or range.`));
      else source[key] = result.value;
    }
  } else {
    const result = resolveBinding(snapshot, `/components/${String(instance.id).replaceAll('~','~0').replaceAll('/','~1')}`);
    if (result.found) copyState(result.value,'/components');
    else if (!Object.keys(source).length) errors.push(issue('/bindings','missing_binding','No bound, adapter-supplied or explicitly authored visual state is available.'));
  }
  // A level/reading binding alone does not establish that equipment is running.
  if (!own(source,'active')) source.active = false;
  for (const [key,value] of Object.entries(source)) if (!fields.has(key) || !validStateValue(fields.get(key),value)) {
    errors.push(issue(`/state/${key}`,'invalid_bound_state',`Invalid visual state ${key}.`)); delete source[key];
  }
  if (errors.length) { source.active = false; source.status = 'offline'; }
  return {ok:errors.length === 0, state:freeze(normalizeScadaState(instance.type,source,{variant:instance.variant})), errors};
}

/** Validate shape and cross-references, clone JSON data, normalize defaults, freeze. */
export function validateSystemDefinition(input) {
  const errors = [];
  const add = (path,code,message) => { if (errors.length < 100) errors.push(issue(path,code,message)); };
  let count = 0;
  const ancestors = new WeakSet();
  function clone(value,path='',depth=0) {
    if (++count > 100000 || depth > 32) { add(path,'limit','Definition exceeds the size/depth limit.'); return null; }
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'string') { if (value.length > 8192) add(path,'limit','Text is too long.'); return value; }
    if (typeof value === 'number') { if (!Number.isFinite(value)) add(path,'nonfinite','Numbers must be finite.'); return value; }
    if (typeof value !== 'object' || (!Array.isArray(value) && !plain(value))) { add(path,'json_type','Only plain JSON data is supported.'); return null; }
    if (ancestors.has(value)) { add(path,'cycle','Cyclic objects are not JSON.'); return null; }
    ancestors.add(value);
    const result = Array.isArray(value) ? [] : {};
    for (const key of Reflect.ownKeys(value)) {
      if (Array.isArray(value) && key === 'length') continue;
      const next = pointerPath(path,key), property = Object.getOwnPropertyDescriptor(value,key);
      if (typeof key !== 'string' || BLOCKED.has(key)) { add(next,'unsafe_key','Prototype and symbol keys are forbidden.'); continue; }
      if (CREDENTIALS.has(key.toLowerCase().replace(/[^a-z]/g,''))) { add(next,'credential','Do not store credentials or secrets in a system definition.'); continue; }
      if (!Object.hasOwn(property,'value') || !property.enumerable) { add(next,'json_type','Only enumerable data properties are supported.'); continue; }
      if (Array.isArray(value) && !/^(0|[1-9]\d*)$/.test(key)) { add(next,'json_type','Arrays cannot contain named properties.'); continue; }
      result[key] = clone(property.value,next,depth+1);
    }
    if (Array.isArray(value) && Object.keys(value).length !== value.length) add(path,'json_type','Sparse arrays are not supported.');
    ancestors.delete(value);
    return result;
  }
  const definition = clone(input);
  if (errors.length) return {ok:false,errors};
  function object(value,path,allowed,required=[]) {
    if (!plain(value)) { add(path,'type','Expected an object.'); return false; }
    for (const key of Object.keys(value)) if (!allowed.includes(key)) add(pointerPath(path,key),'unknown_field',`Unknown field ${key}.`);
    for (const key of required) if (!own(value,key)) add(pointerPath(path,key),'required',`Required field ${key} is missing.`);
    return true;
  }
  const text = (value,path,max=4096) => { if (typeof value !== 'string' || !value.length || value.length > max) add(path,'type',`Expected nonempty text of at most ${max} characters.`); };
  const id = (value,path) => { if (typeof value !== 'string' || !ID.test(value)) add(path,'id','Use a stable ID beginning with a letter, followed by letters, digits, underscores or dashes; maximum100 characters.'); };
  const number = (value,path,min=0,max=1000000) => { if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) add(path,'range',`Expected a finite number between ${min} and ${max}.`); };
  const list = (value,path,max=10000) => { if (!Array.isArray(value) || value.length > max) { add(path,'type',`Expected an array of at most ${max} items.`); return []; } return value; };
  const unique = (items,path,key='id') => { const seen = new Set(); for (const [i,item] of items.entries()) if (plain(item)) { id(item[key],`${path}/${i}/${key}`); if (seen.has(item[key])) add(`${path}/${i}/${key}`,'duplicate',`Duplicate ${key}: ${item[key]}.`); seen.add(item[key]); } };
  const binding = (value,path) => { const parsed = pointerTokens(value); if (parsed.error) add(path,parsed.error.code,parsed.error.message); };
  const ref = (value,values,path,kind) => { if (!values.has(value)) add(path,'reference',`Unknown ${kind}: ${String(value)}.`); };
  const optionalText = (value,path,keys) => { for (const key of keys) if (own(value,key)) text(value[key],`${path}/${key}`); };
  const stringMap = (value,path) => { if (object(value,path,Object.keys(value || {}))) for (const [key,item] of Object.entries(value)) { text(key,pointerPath(path,key),100); text(item,pointerPath(path,key),256); } };

  if (!object(definition,'',['$schema','format','version','system','components','connections','views','commands','controls','units','provenance','assumptions'],['format','version','system','components','views'])) return {ok:false,errors};
  if (definition.format !== 'scada-system') add('/format','format','Expected format "scada-system".');
  if (definition.version !== SYSTEM_DEFINITION_VERSION) add('/version','version','Unsupported version. Explicitly migrate to version1 before loading.');
  if (own(definition,'$schema')) text(definition.$schema,'/$schema',2048);
  if (object(definition.system,'/system',['id','label','description'],['id','label'])) { id(definition.system.id,'/system/id'); text(definition.system.label,'/system/label',256); optionalText(definition.system,'/system',['description']); }
  for (const key of ['connections','commands','controls','provenance','assumptions']) if (!own(definition,key)) definition[key] = [];
  if (!own(definition,'units')) definition.units = {};
  stringMap(definition.units,'/units');
  const components = list(definition.components,'/components'), connections = list(definition.connections,'/connections'), views = list(definition.views,'/views',100), commands = list(definition.commands,'/commands'), controls = list(definition.controls,'/controls'), provenance = list(definition.provenance,'/provenance'), assumptions = list(definition.assumptions,'/assumptions');
  if (!components.length) add('/components','required','At least one component is required.');
  if (!views.length) add('/views','required','At least one view is required.');
  for (const [name,items] of Object.entries({components,connections,views,commands,controls,provenance,assumptions})) unique(items,`/${name}`);
  const componentIds = new Set(components.map(item=>item?.id)), connectionIds = new Set(connections.map(item=>item?.id)), commandIds = new Set(commands.map(item=>item?.id)), provenanceIds = new Set(provenance.map(item=>item?.id));
  const descriptors = new Map();
  for (const [index,item] of provenance.entries()) { const path=`/provenance/${index}`; if (!object(item,path,['id','label','kind','description','source'],['id','label','kind'])) continue; text(item.label,`${path}/label`,256); optionalText(item,path,['description','source']); if (!['assumed','recorded','external','illustrative'].includes(item.kind)) add(`${path}/kind`,'enum','Unknown provenance kind.'); }
  for (const [index,item] of assumptions.entries()) { const path=`/assumptions/${index}`; if (!object(item,path,['id','label','value','unit','description','provenance'],['id','label','value'])) continue; text(item.label,`${path}/label`,256); optionalText(item,path,['unit','description']); if (item.value !== null && !['string','number','boolean'].includes(typeof item.value)) add(`${path}/value`,'type','An assumption value must be a JSON scalar.'); if (own(item,'provenance')) ref(item.provenance,provenanceIds,`${path}/provenance`,'provenance'); }
  for (const [index,item] of components.entries()) {
    const path=`/components/${index}`;
    if (!object(item,path,['id','type','variant','label','state','bindings','ports','units','provenance'],['id','type'])) continue;
    let descriptor;
    try { descriptor=getScadaComponent(item.type); }
    catch { add(`${path}/type`,'unknown_type','Unknown registered component type.'); }
    if(descriptor && own(item,'variant')) {
      try { descriptor=getScadaComponent(item.type,{variant:item.variant}); }
      catch { add(`${path}/variant`,'unknown_variant','Choose a registered variant for this component type.'); }
    }
    if(descriptor)descriptors.set(item.id,descriptor);
    if (!own(item,'label') && descriptor) item.label=descriptor.label; else if (own(item,'label')) text(item.label,`${path}/label`,256);
    for (const key of ['state','bindings','units']) if (!own(item,key)) item[key]={};
    for (const key of ['ports','provenance']) if (!own(item,key)) item[key]=[];
    stringMap(item.units,`${path}/units`);
    const fields = new Map((descriptor?.stateFields || []).map(field=>[field.key,field]));
    if (object(item.state,`${path}/state`,[...fields.keys()])) for (const [key,value] of Object.entries(item.state)) if (fields.has(key) && !validStateValue(fields.get(key),value)) add(`${path}/state/${key}`,'state_type','State must match its declared type, option and numeric range.');
    if (object(item.bindings,`${path}/bindings`,[...fields.keys()])) for (const [key,value] of Object.entries(item.bindings)) binding(value,`${path}/bindings/${key}`);
    const ports=list(item.ports,`${path}/ports`,100); unique(ports,`${path}/ports`);
    for (const [pi,port] of ports.entries()) { const pp=`${path}/ports/${pi}`; if (!object(port,pp,['id','side','offset','label'],['id','side'])) continue; if (descriptor && !descriptor.ports.some(known=>known.id===port.id)) add(`${pp}/id`,'port','Unknown registry port.'); if (!['top','right','bottom','left'].includes(port.side)) add(`${pp}/side`,'enum','Unknown port side.'); if (!own(port,'offset')) port.offset=.5; number(port.offset,`${pp}/offset`,0,1); optionalText(port,pp,['label']); }
    for (const [pi,value] of list(item.provenance,`${path}/provenance`,100).entries()) ref(value,provenanceIds,`${path}/provenance/${pi}`,'provenance');
  }
  for (const [index,item] of connections.entries()) {
    const path=`/connections/${index}`;
    if (!object(item,path,['id','from','to','medium','flowBinding','label'],['id','from','to'])) continue;
    optionalText(item,path,['medium','label']); if (own(item,'flowBinding')) binding(item.flowBinding,`${path}/flowBinding`);
    for (const side of ['from','to']) if (object(item[side],`${path}/${side}`,['component','port'],['component','port'])) { ref(item[side].component,componentIds,`${path}/${side}/component`,'component'); const descriptor=descriptors.get(item[side].component); if (descriptor && !descriptor.ports.some(port=>port.id===item[side].port)) add(`${path}/${side}/port`,'port','Unknown registered endpoint port.'); }
  }
  for (const [index,item] of views.entries()) {
    const path=`/views/${index}`;
    if (!object(item,path,['id','label','canvas','placements','routes'],['id','canvas','placements'])) continue;
    if (!own(item,'label')) item.label=item.id; else text(item.label,`${path}/label`,256);
    if (object(item.canvas,`${path}/canvas`,['width','height'],['width','height'])) for (const key of ['width','height']) number(item.canvas[key],`${path}/canvas/${key}`,Number.MIN_VALUE);
    const placements=list(item.placements,`${path}/placements`); unique(placements,`${path}/placements`,'component');
    for (const [pi,placement] of placements.entries()) { const pp=`${path}/placements/${pi}`; if (!object(placement,pp,['component','x','y','width','height'],['component','x','y','width','height'])) continue; ref(placement.component,componentIds,`${pp}/component`,'component'); for (const key of ['x','y','width','height']) number(placement[key],`${pp}/${key}`,['width','height'].includes(key)?Number.MIN_VALUE:0); if (plain(item.canvas) && (placement.x+placement.width>item.canvas.width || placement.y+placement.height>item.canvas.height)) add(pp,'bounds','Placement extends beyond its canvas.'); }
    if (!own(item,'routes')) item.routes=[];
    const routes=list(item.routes,`${path}/routes`); unique(routes,`${path}/routes`,'connection');
    for (const [ri,route] of routes.entries()) { const rp=`${path}/routes/${ri}`; if (!object(route,rp,['connection','points'],['connection','points'])) continue; ref(route.connection,connectionIds,`${rp}/connection`,'connection'); const points=list(route.points,`${rp}/points`,1000); if (points.length<2) add(`${rp}/points`,'required','A route needs at least two points.'); for (const [pi,point] of points.entries()) if (object(point,`${rp}/points/${pi}`,['x','y'],['x','y'])) { number(point.x,`${rp}/points/${pi}/x`,0,plain(item.canvas)?item.canvas.width:1000000); number(point.y,`${rp}/points/${pi}/y`,0,plain(item.canvas)?item.canvas.height:1000000); } }
  }
  for (const [index,item] of commands.entries()) { const path=`/commands/${index}`; if (!object(item,path,['id','label','component','action','arguments'],['id','label','action'])) continue; text(item.label,`${path}/label`,256); id(item.action,`${path}/action`); if (own(item,'component')) ref(item.component,componentIds,`${path}/component`,'component'); if (!own(item,'arguments')) item.arguments={}; if (!plain(item.arguments)) add(`${path}/arguments`,'type','Command arguments must be a JSON object.'); }
  const diagramControls = new Set();
  for (const [index,item] of controls.entries()) {
    const path=`/controls/${index}`;
    if (!object(item,path,['id','label','command','component','kind','binding','min','max','step','diagram'],['id','label','command','kind'])) continue;
    text(item.label,`${path}/label`,256); ref(item.command,commandIds,`${path}/command`,'command'); if (own(item,'component')) ref(item.component,componentIds,`${path}/component`,'component');
    if (!['button','toggle','range'].includes(item.kind)) add(`${path}/kind`,'enum','Unknown control kind.');
    if (own(item,'binding')) binding(item.binding,`${path}/binding`); else if (['toggle','range'].includes(item.kind)) add(`${path}/binding`,'required','Value controls require an explicit binding.');
    if (item.kind==='range') { for (const key of ['min','max']) number(item[key],`${path}/${key}`,-1000000000,1000000000); if (!own(item,'step')) item.step=1; number(item.step,`${path}/step`,Number.MIN_VALUE,1000000000); if (item.min>=item.max) add(path,'range','Range min must be less than max.'); }
    else for (const key of ['min','max','step']) if (own(item,key)) add(`${path}/${key}`,'control','Numeric bounds belong only to range controls.');
    if (own(item,'diagram')) {
      if (item.kind !== 'toggle' || !own(item,'component')) add(`${path}/diagram`,'control','Diagram actions require a component-specific toggle.');
      if (object(item.diagram,`${path}/diagram`,['whenTrue','whenFalse'],['whenTrue','whenFalse'])) {
        for (const key of ['whenTrue','whenFalse']) text(item.diagram[key],`${path}/diagram/${key}`,40);
      }
      if (diagramControls.has(item.component)) add(`${path}/diagram`,'control','An equipment item can have only one diagram action.');
      diagramControls.add(item.component);
    }
  }
  return errors.length ? {ok:false,errors} : {ok:true,definition:freeze(definition)};
}
