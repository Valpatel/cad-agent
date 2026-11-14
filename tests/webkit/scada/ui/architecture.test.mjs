import {UI, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir,cp,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {dirname,join,resolve,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from '../dependencies.mjs';

const packageRoot=UI;
const source=join(packageRoot,'src');

test('metadata, discovery and definition validation work without any artwork or UI implementation',async()=>{
 const fixture=await mkdtemp(join(tmpdir(),'scada-contract-only-'));
 try{
  for(const name of ['catalog','contracts','metadata.mjs'])await cp(join(source,name),join(fixture,name),{recursive:true});
  const metadata=await import(pathToFileURL(join(fixture,'metadata.mjs')));
  const catalog=await import(pathToFileURL(join(fixture,'catalog/discovery.mjs')));
  const contract=await import(pathToFileURL(join(fixture,'contracts/system-definition.mjs')));
  const system=JSON.parse(await readFile(join(packageRoot,'examples/minimal-system.json'),'utf8'));
  assert.ok(metadata.SCADA_COMPONENTS.length>0);
  assert.ok(catalog.findScadaComponents({query:'pump'}).length>0);
  assert.equal(contract.validateSystemDefinition(system).ok,true);
  assert.throws(()=>catalog.getScadaComponent('missing-type'),RangeError);
  const invalid=structuredClone(system);invalid.components[0].type='missing-type';
  assert.equal(contract.validateSystemDefinition(invalid).ok,false);
 }finally{await rm(fixture,{recursive:true,force:true});}
});

test('contract/discovery entry graphs stay independent of renderers, controllers and host code',async()=>{
 const result=await build({entryPoints:['metadata.mjs','catalog/discovery.mjs','contracts/system-definition.mjs'].map(name=>join(source,name)),absWorkingDir:packageRoot,bundle:true,write:false,outdir:join(tmpdir(),'scada-contract-bundle'),format:'esm',platform:'node',metafile:true,logLevel:'silent'});
 for(const filename of Object.keys(result.metafile.inputs)){
  const name=relative(source,resolve(packageRoot,filename)).replaceAll('\\','/');
  assert.ok(!name.startsWith('../'),name);
  assert.doesNotMatch(name,/(?:^|\/)(?:symbols|viewer|workspace|apps|dist|scada-sim)\//,name);
 }
});
