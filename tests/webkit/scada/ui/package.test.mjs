import {REPO, UI, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir,cp,rm,readdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {dirname,join,resolve,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {SCADA_COMPONENTS,SCADA_CATEGORIES} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const packageRoot=UI;
const packageManifest=JSON.parse(await readFile(join(packageRoot,'package.json'),'utf8'));
const run=(command,args,cwd,env={})=>execFileSync(command,args,{cwd,encoding:'utf8',env:{...process.env,...env},stdio:['ignore','pipe','pipe'],timeout:30000});

async function runtimeFiles(directory) {
 const entries=await readdir(directory,{withFileTypes:true}), result=[];
 for (const entry of entries) {
  const path=join(directory,entry.name);
  if(entry.isDirectory()) result.push(...await runtimeFiles(path));
  else if(entry.isFile()&&/\.(?:mjs|css)$/.test(entry.name)) result.push(relative(join(packageRoot,'src'),path));
 }
 return result.sort();
}
const runtimePaths=await runtimeFiles(join(packageRoot,'src'));

test('the actual npm tarball installs offline and exposes a self-contained public API and stylesheet graph',async()=>{
 const temporary=await mkdtemp(join(tmpdir(),'scada-package-smoke-'));
 try{
  const env={npm_config_cache:join(temporary,'npm-cache'),npm_config_update_notifier:'false'};
  const packed=JSON.parse(run('npm',['pack','--offline','--ignore-scripts','--json','--pack-destination',temporary],packageRoot,env))[0];
  assert.ok(packed.filename.endsWith('.tgz'));
  const consumer=join(temporary,'consumer');await mkdir(consumer);
  await writeFile(join(consumer,'package.json'),JSON.stringify({private:true,type:'module'}));
  run('npm',['install','--offline','--ignore-scripts','--no-audit','--no-fund','--no-package-lock',join(temporary,packed.filename)],consumer,env);
  const output=run(process.execPath,['--input-type=module','--eval',`
    import assert from 'node:assert/strict';
    import {readFile} from 'node:fs/promises';
    import * as library from '@valpatel/scada-ui';
    import * as components from '@valpatel/scada-ui/components';
    import * as workspace from '@valpatel/scada-ui/workspace';
    import * as viewer from '@valpatel/scada-ui/viewer';
    import * as system from '@valpatel/scada-ui/system-definition';
    import * as metadata from '@valpatel/scada-ui/metadata';
    import data from '@valpatel/scada-ui/metadata.json' with {type:'json'};
    import schema from '@valpatel/scada-ui/schema' with {type:'json'};
    import thumbnails from '@valpatel/scada-ui/thumbnails.json' with {type:'json'};
    import manifest from '@valpatel/scada-ui/package.json' with {type:'json'};
    assert.equal(manifest.version,${JSON.stringify(packageManifest.version)});
    assert.equal(manifest.private,true);
    assert.equal(manifest.license,'MIT');
    assert.equal(library.SCADA_COMPONENTS.length,${SCADA_COMPONENTS.length});
    assert.strictEqual(metadata.SCADA_COMPONENTS,library.SCADA_COMPONENTS);
    assert.strictEqual(components.renderScadaComponent,library.renderScadaComponent);
    assert.strictEqual(workspace.ScadaWorkspace,library.ScadaWorkspace);
    assert.strictEqual(viewer.ScadaViewer,library.ScadaViewer);
    assert.strictEqual(system.validateSystemDefinition,library.validateSystemDefinition);
    assert.deepEqual(data.components,library.SCADA_COMPONENTS);
    assert.equal(schema.$id,'urn:valpatel:scada-system:1');
    assert.equal(thumbnails.components.length,library.SCADA_COMPONENTS.length);
    for(const item of library.SCADA_COMPONENTS)assert.ok(library.renderScadaComponent(item.type).includes('scada-component'));
    assert.ok(library.renderScadaDialog({id:'equipment',title:'Pump <1>',body:'<p>Trusted host markup</p>'}).includes('Pump &lt;1&gt;'));
    assert.ok(library.renderScadaToolbar({content:'<button>Operate</button>'}).includes('Operate'));
    assert.throws(()=>library.normalizeScadaState('pump',{active:'yes'}),TypeError);
    const checked=library.validateSystemDefinition({format:'scada-system',version:1,
      system:{id:'portable-test',label:'Portable test system'},
      components:[{id:'feed',type:'pump',bindings:{active:'/running'}}],
      views:[{id:'overview',canvas:{width:320,height:200},placements:[{component:'feed',x:30,y:30,width:160,height:130}]}]
    });
    assert.equal(checked.ok,true,JSON.stringify(checked.errors));
    assert.equal(library.resolveComponentState(checked.definition.components[0],{running:true}).state.active,true);
    assert.equal(library.resolveBinding({running:true},'/running').value,true);
    assert.equal(library.resolveBinding({},'/__proto__/active').found,false);
    const scene=library.normalizeViewerDefinition(checked.definition);
    const diagram=library.renderScadaDiagram({view:scene.views[0],equipment:scene.equipment,snapshot:{running:true},
      renderNode:(node,context)=>library.renderScadaComponent(node.type,{id:node.id,state:library.resolveComponentState(node,context.snapshot).state})});
    assert.ok(diagram.includes('scada-diagram-canvas'));
    assert.ok(diagram.includes('data-scada-type="pump"'));
    const packageURL=new URL('.',import.meta.resolve('@valpatel/scada-ui/package.json'));
    const {UtilityModel}=await import(new URL('examples/viewer/utility-model.mjs',packageURL));
    const {createUtilityAdapter}=await import(new URL('examples/viewer/utility-adapter.mjs',packageURL));
    const example=JSON.parse(await readFile(new URL('examples/viewer/system.json',packageURL),'utf8'));
    assert.equal(library.validateSystemDefinition(example).ok,true);
    const model=new UtilityModel(),editable=createUtilityAdapter(model),monitor=createUtilityAdapter(model,{readOnly:true});
    assert.equal(monitor.dispatch,undefined);
    let observed=0;const unsubscribe=monitor.subscribe(()=>observed++);
    editable.dispatch({action:'set',arguments:{key:'pumpOn',value:false}});
    assert.equal(editable.getSnapshot().components.pump.active,false);
    assert.equal(monitor.getSnapshot().components.pump.active,false);
    assert.equal(observed,1);unsubscribe();
    assert.equal(model.getSnapshot().minutes,0,'importing/rendering the package does not start the sample model clock');
    console.log('isolated package imports and '+library.SCADA_COMPONENTS.length+' renderers passed');
  `],consumer);
  assert.match(output,/renderers passed/);
  const installed=join(consumer,'node_modules/@valpatel/scada-ui');
  const manifest=JSON.parse(await readFile(join(installed,'package.json'),'utf8'));
  assert.equal(manifest.dependencies,undefined,'the UI package has no runtime npm dependencies');
  assert.deepEqual(await readFile(join(installed,'LICENSE.txt')),await readFile(join(REPO,'LICENSE')),'installed UI consumers receive the complete project MIT grant');
  const visited=new Set();
  async function visitStyles(filename){
   const path=resolve(installed,filename);
   assert.ok(!relative(installed,path).startsWith(`..${sep}`),'stylesheet dependency stays inside the package');
   if(visited.has(path))return;visited.add(path);
   const css=await readFile(path,'utf8');
   for(const match of css.matchAll(/@import\s+(?:url\(\s*)?["']([^"']+)["']/g)){
    assert.match(match[1],/^\.\.?\//,'styles use relative package URLs, including sibling domains');
    await visitStyles(relative(installed,resolve(dirname(path),match[1])));
   }
   for(const match of css.matchAll(/url\(\s*["']?([^)'"\s]+)["']?\s*\)/g)){
    const target=match[1];if(target.startsWith('#')||target.startsWith('data:'))continue;
    assert.match(target,/^\.\.?\//,'asset URL is relative');
    const asset=resolve(dirname(path),target);
    assert.ok(!relative(installed,asset).startsWith(`..${sep}`),'asset stays inside the package');
    await readFile(asset);
   }
  }
  for(const path of Object.values(manifest.exports))if(path.endsWith('.css'))await visitStyles(path);
  assert.ok(visited.size>=4,'combined styles include components, original artwork and workspace styles');
  for(const filename of runtimePaths)assert.deepEqual(await readFile(join(installed,'src',filename)),await readFile(join(packageRoot,'src',filename)),`packed ${filename} matches canonical source`);
  const packedPaths=new Set(packed.files.map(file=>file.path));
  assert.ok(packedPaths.has('src/index.mjs'));assert.ok(packedPaths.has('metadata/components.json'));
  assert.ok(packedPaths.has('schema/scada-system.schema.json'));
  const thumbnailManifest=JSON.parse(await readFile(join(installed,'metadata/thumbnails.json'),'utf8'));
  assert.equal(thumbnailManifest.capture.format,'jpeg');
  assert.equal(thumbnailManifest.capture.quality,85);
  assert.deepEqual(new Set(thumbnailManifest.components.map(item=>item.type)),new Set(JSON.parse(await readFile(join(installed,'metadata/components.json'),'utf8')).components.map(item=>item.type)));
  for(const thumbnail of [...thumbnailManifest.components,...thumbnailManifest.variants]){
   const bytes=await readFile(join(installed,thumbnail.path));
   assert.deepEqual(bytes.subarray(0,3),Buffer.from([255,216,255]),`packed ${thumbnail.type} preview is a JPEG`);
   assert.equal(thumbnail.format,'jpeg');
  }
  assert.ok(packedPaths.has('examples/minimal-system.json'));
  for(const example of ['examples/components/index.html','examples/viewer/index.html']){
   const file=join(installed,example),html=await readFile(file,'utf8');
   for(const match of html.matchAll(/(?:src|href)=["']([^"']+)["']/g)){
    const link=match[1];if(link.startsWith('https:')||link.startsWith('#'))continue;
    const target=resolve(dirname(file),link);
    assert.ok(!relative(installed,target).startsWith(`..${sep}`),`${example} stays inside the package`);
    await readFile(target);
   }
  }
  assert.ok(![...packedPaths].some(path=>path.startsWith('node_modules/')||path.startsWith('dist/')||path.startsWith('scripts/')||path.startsWith('tests/')||path.includes('twin-runtime')),'package excludes the application and its simulation session');
  assert.deepEqual((await readdir(join(consumer,'node_modules'))).filter(name=>name!=='.package-lock.json'),['@valpatel']);
 }finally{await rm(temporary,{recursive:true,force:true});}
});
