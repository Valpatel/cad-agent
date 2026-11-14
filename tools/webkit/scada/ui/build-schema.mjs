#!/usr/bin/env node
import {UI} from '../paths.mjs';
/** Keep the portable presentation schema's registry choices in sync. */
import {readFile,writeFile} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {SCADA_COMPONENTS,getScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/catalog/registry.mjs';

const packageRoot = UI;

export async function buildScadaSchema({check=false}={}) {
  const path=resolve(packageRoot,'schema/scada-system.schema.json');
  const previous=await readFile(path,'utf8');
  const schema=JSON.parse(previous);
  const fields=new Map();
  const selections=SCADA_COMPONENTS.flatMap(item=>[item,...(item.variants??[]).map(variant=>getScadaComponent(item.type,{variant:variant.id}))]);
  for(const descriptor of selections) {
    for(const field of descriptor.stateFields) {
      const known=fields.get(field.key);
      if(known && known.type!==field.type) throw new TypeError(`Conflicting state type: ${field.key}`);
      if(field.type==='number') {
        fields.set(field.key,{type:'number',minimum:Math.min(known?.minimum??field.min,field.min),maximum:Math.max(known?.maximum??field.max,field.max)});
      } else if(field.type==='select') {
        fields.set(field.key,{type:'select',enum:[...new Set([...(known?.enum??[]),...field.options.map(option=>option.value)])]});
      } else fields.set(field.key,{type:'boolean'});
    }
  }
  schema.$defs.state.properties=Object.fromEntries([...fields].map(([key,value])=>{
    const property={...value};
    if(property.type==='select')delete property.type;
    return [key,property];
  }));
  schema.$defs.bindings.properties=Object.fromEntries([...fields.keys()].map(key=>[key,{$ref:'#/$defs/pointer'}]));
  schema.$defs.component.properties.type.enum=SCADA_COMPONENTS.map(item=>item.type);
  schema.$defs.component.properties.variant={type:'string',pattern:'^[a-z][a-z0-9-]*$',maxLength:100};
  schema.$defs.component.allOf=SCADA_COMPONENTS.map(item=>({
    if:{properties:{type:{const:item.type}},required:['type']},
    then:item.variants?.length
      ? {properties:{variant:{enum:item.variants.map(variant=>variant.id)}}}
      : {not:{required:['variant']}},
  }));
  const next=`${JSON.stringify(schema,null,2)}\n`;
  if(check && previous!==next)throw new Error('SCADA schema is stale; run npm --prefix tools/webkit/scada run build:schema.');
  if(!check && previous!==next)await writeFile(path,next);
  return {changed:previous!==next,types:SCADA_COMPONENTS.length,stateFields:fields.size};
}

if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2);
  if(args.some(arg=>arg!=='--check'))throw new Error('Usage: node tools/webkit/scada/ui/build-schema.mjs [--check]');
  const result=await buildScadaSchema({check:args.includes('--check')});
  process.stdout.write(`${args.includes('--check')?'Verified':'Updated'} schema: ${result.types} types, ${result.stateFields} state fields.\n`);
}
