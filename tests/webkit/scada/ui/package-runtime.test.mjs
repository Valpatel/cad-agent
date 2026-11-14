import {UI, TOOLS, TESTS} from '../../../../tools/webkit/scada/paths.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {SCADA_COMPONENTS} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const packageRoot=UI;
const expectedVariants=SCADA_COMPONENTS.reduce((count,item)=>count+(item.variants?.length??0),0);
test('an actual offline npm consumer can discover/render every type and variant without starting IO or a model',async t=>{
  const artifacts=await mkdtemp(join(tmpdir(),'scada-ui-package-runtime-'));
  t.after(()=>rm(artifacts,{recursive:true,force:true}));
  const run=(command,args,cwd)=>execFileSync(command,args,{cwd,encoding:'utf8',timeout:30000,
  env:{...process.env,npm_config_cache:join(artifacts,'npm-cache'),npm_config_update_notifier:'false'},
  stdio:['ignore','pipe','pipe']});

  const packed=JSON.parse(run('npm',['pack','--offline','--ignore-scripts','--json','--pack-destination',artifacts],packageRoot))[0];
  const consumer=join(artifacts,'consumer');await mkdir(consumer,{recursive:true});
  await writeFile(join(consumer,'package.json'),JSON.stringify({private:true,type:'module'}));
  run('npm',['install','--offline','--ignore-scripts','--no-audit','--no-fund','--no-package-lock',join(artifacts,packed.filename)],consumer);
  const probe=`
    import assert from 'node:assert/strict';
    const calls={timer:0,animation:0,network:0};
    const blocked=key=>(...args)=>{calls[key]++;throw new Error('Unexpected '+key);};
    globalThis.setInterval=blocked('timer');globalThis.setTimeout=blocked('timer');
    globalThis.requestAnimationFrame=blocked('animation');globalThis.fetch=blocked('network');
    globalThis.WebSocket=class{constructor(){calls.network++;throw new Error('Unexpected socket');}};
    globalThis.XMLHttpRequest=class{constructor(){calls.network++;throw new Error('Unexpected request');}};
    const library=await import('@valpatel/scada-ui');
    const catalog=await import('@valpatel/scada-ui/catalog');
    const components=await import('@valpatel/scada-ui/components');
    const metadata=await import('@valpatel/scada-ui/metadata');
    const workspace=await import('@valpatel/scada-ui/workspace');
    const viewer=await import('@valpatel/scada-ui/viewer');
    const system=await import('@valpatel/scada-ui/system-definition');
    assert.equal(library.SCADA_COMPONENTS.length,${SCADA_COMPONENTS.length});
    assert.strictEqual(library.findScadaComponents,catalog.findScadaComponents);
    assert.strictEqual(metadata.getScadaVariants,components.getScadaVariants);
    assert.strictEqual(workspace.ScadaWorkspace,library.ScadaWorkspace);
    assert.strictEqual(viewer.ScadaViewer,library.ScadaViewer);
    assert.strictEqual(system.resolveComponentState,library.resolveComponentState);
    assert.equal(catalog.findScadaComponents({fuel:'diesel',medium:'liquid'})[0].type,'generator');
    let variants=0;
    for(const item of library.SCADA_COMPONENTS){
      assert.ok(library.renderScadaComponent(item.type).includes('<svg'));
      for(const variant of library.getScadaVariants(item.type)){
        const selected=library.getScadaComponent(item.type,{variant:variant.id});
        assert.equal(selected.selectedVariant.id,variant.id);
        assert.ok(library.renderScadaComponent(item.type,{variant:variant.id}).includes('<svg'));
        variants++;
      }
    }
    assert.equal(variants,${expectedVariants});
    const definition={format:'scada-system',version:1,system:{id:'portable',label:'Portable'},
      components:[{id:'unit',type:'generator',variant:'diesel-skid',state:{active:true}}],
      views:[{id:'overview',canvas:{width:320,height:260},placements:[{component:'unit',x:20,y:20,width:210,height:210}]}]};
    assert.equal(system.validateSystemDefinition(definition).ok,true);
    let subscriptions=0;
    const readonly=new viewer.ScadaViewer({definition,adapter:{getSnapshot:()=>({}),subscribe:()=>{subscriptions++;return()=>subscriptions--;}}});
    assert.equal(readonly.readOnly,true);
    assert.match(readonly.render(),/data-readonly="true"/);
    assert.throws(()=>readonly.dispatch({action:'anything'}),/read-only/);
    assert.equal(subscriptions,0,'server-side construction/rendering does not mount a subscription');
    readonly.destroy();
    assert.deepEqual(calls,{timer:0,animation:0,network:0});
    console.log(JSON.stringify({types:library.SCADA_COMPONENTS.length,variants,exports:true,readonly:true,calls}));
  `;
  const report=JSON.parse(run(process.execPath,['--input-type=module','--eval',probe],consumer));
  const manifest=JSON.parse(await readFile(join(consumer,'node_modules/@valpatel/scada-ui/package.json'),'utf8'));
  assert.equal(manifest.dependencies,undefined);
  await writeFile(join(artifacts,'runtime-report.json'),JSON.stringify({...report,version:manifest.version,tarball:packed.filename},null,2)+'\n');
});
