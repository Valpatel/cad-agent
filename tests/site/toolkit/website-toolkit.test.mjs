import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {SCADA_INPUTS, TOOLKIT_ROUTES, scadaToolkitModel, toolkitPages} from '../../../tools/site/compiler/site-toolkit.mjs';
import {matchesToolkitCard} from '../../../tools/site/assets/toolkit.js';
import {sourceLicenseResolver} from '../../../tools/site/compiler/site-catalog.mjs';

const root = path.resolve(import.meta.dirname,'../../..');
const read = file => JSON.parse(readFileSync(path.join(root,file),'utf8'));
const fixture = () => {
  const stateFields=[{key:'active',label:'Active',type:'boolean',default:true}];
  const shape={type:'pump',category:'rotating',label:'Pump',description:'A pump',variant:null,stateLabel:'Running example',state:{active:true},stateFields,path:'img/symbols/rotating/pump.svg'};
  const scenario={id:'wastewater-digester',title:'Wastewater digester',description:'An editable example',sector:'Water',system:'wastewater-digester/system.json',model:'wastewater-digester/model.json',views:[{id:'process'}],experiments:[{id:'trip'}]};
  return {components:{schemaVersion:1,categories:[{id:'rotating',label:'Pumps'}],components:[{id:'pump',category:'rotating',description:'A pump'}]},
    gallery:{format:'scada-ui-svg-gallery',version:1,symbols:[shape],states:[]},scenarios:{format:'scada-scenario-catalog',version:1,scenarios:[scenario]},
    thumbnails:{format:'scada-scenario-thumbnails',version:1,scenarios:[{id:'wastewater-digester',path:'img/thumbnails/water/wastewater-digester/preview.jpg'}]},has:()=>true};
};

test('real inventory exposes every equipment type, declared variant/state and target-owned scenario',()=>{
  const inputs=Object.fromEntries(Object.entries(SCADA_INPUTS).map(([key,file])=>[key,read(file)]));
  const model=scadaToolkitModel({...inputs,has:file=>existsSync(path.join(root,file))});
  assert.equal(model.counts.equipment,inputs.components.components.length);
  assert.equal(model.elements.length,inputs.gallery.symbols.length+inputs.gallery.states.length);
  assert.equal(model.simulations.length,inputs.scenarios.scenarios.length);
  assert.equal(model.license,'UNLICENSED');
  for(const item of model.elements)assert.ok(item.image.startsWith('/kit/scada/ui/img/'));
  for(const item of model.simulations){assert.ok(item.href.startsWith('/kit/scada/explorer/index.html?scenario='));assert.ok(item.image.startsWith('/kit/scada/sim/img/'));}
  const pages=toolkitPages(model);
  assert.deepEqual(pages.pages.map(p=>p.url),TOOLKIT_ROUTES);
  for(const p of pages.pages){assert.ok(p.markdown);assert.doesNotMatch(p.body,/digester-insight|chatgpt\.site|<iframe\b/);}
});

test('missing assets and mismatched inventories fail before publishing an incomplete capability',()=>{
  let f=fixture();f.has=()=>false;assert.throws(()=>scadaToolkitModel(f),/missing gallery asset/);
  f=fixture();f.gallery.symbols=[];assert.throws(()=>scadaToolkitModel(f),/every component/);
  f=fixture();f.gallery.symbols.push({...f.gallery.symbols[0]});assert.throws(()=>scadaToolkitModel(f),/duplicate gallery/);
  f=fixture();f.gallery.symbols[0].type='missing';assert.throws(()=>scadaToolkitModel(f),/does not match/);
  f=fixture();f.gallery.symbols[0].variant='missing';assert.throws(()=>scadaToolkitModel(f),/unknown variant/);
  f=fixture();f.components.components[0].variants=[{id:'new'}];assert.throws(()=>scadaToolkitModel(f),/missing variant preview/);
  f=fixture();f.components.categories.push({...f.components.categories[0]});assert.throws(()=>scadaToolkitModel(f),/duplicate category/);
  f=fixture();f.scenarios.scenarios.push({...f.scenarios.scenarios[0]});assert.throws(()=>scadaToolkitModel(f),/duplicate scenario/);
  f=fixture();f.thumbnails.scenarios=[];assert.throws(()=>scadaToolkitModel(f),/missing scenario thumbnail/);
  f=fixture();f.has=file=>!file.endsWith('/model.json');assert.throws(()=>scadaToolkitModel(f),/missing system\/model/);
});

test('gallery references cannot escape their owner or introduce network/script URLs',()=>{
  for(const value of ['https://example.test/a.svg','../secret.svg','img/../../secret.svg','img/%2e%2e/secret.svg','img/a.svg?x=1','javascript:alert(1)','img/a.svg#frag']){
    const f=fixture();f.gallery.symbols[0].path=value;assert.throws(()=>scadaToolkitModel(f),/invalid gallery asset/);
  }
  const f=fixture();f.scenarios.scenarios[0].system='../other/system.json';assert.throws(()=>scadaToolkitModel(f),/references must be local/);
});

test('unsupported metadata and editable state fields fail clearly',()=>{
  let f=fixture();f.components.schemaVersion=99;assert.throws(()=>scadaToolkitModel(f),/unsupported component/);
  f=fixture();f.gallery.version=99;assert.throws(()=>scadaToolkitModel(f),/unsupported gallery/);
  f=fixture();f.scenarios.version=99;assert.throws(()=>scadaToolkitModel(f),/unsupported scenario/);
  f=fixture();f.thumbnails.version=99;assert.throws(()=>scadaToolkitModel(f),/unsupported thumbnail/);
  f=fixture();f.gallery.symbols[0].stateFields=[{key:'html',type:'script'}];assert.throws(()=>scadaToolkitModel(f),/invalid state field/);
  f=fixture();f.gallery.symbols[0].stateFields=[{key:'speed',label:'Speed',type:'number',min:20,max:10}];assert.throws(()=>scadaToolkitModel(f),/invalid numeric bounds/);
});

test('generated pages escape metadata and retain useful no-script cards and links',()=>{
  const f=fixture();f.gallery.symbols[0].label='<img src=x onerror=alert(1)>';f.scenarios.scenarios[0].title='Water "><script>bad()</script>';
  const result=toolkitPages(scadaToolkitModel(f));
  const elements=result.pages.find(p=>p.url.endsWith('/elements')).body;
  assert.ok(elements.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.doesNotMatch(elements,/<img src=x|<script/);
  assert.match(elements,/data-scada-preview="equipment--pump" hidden/);
  assert.match(elements,/href="\/kit\/scada\/ui\/img\/symbols\/rotating\/pump.svg"/);
  assert.match(elements,/data-scada-filters hidden/);
  assert.ok(result.pages.find(p=>p.url==='/toolkit/scada').body.includes('scenario=wastewater-digester'));
});

test('filters combine words, category and entry kind without altering catalogue identity',()=>{
  const card={search:'Centrifugal pump · water transfer · running',category:'rotating',kind:'equipment'};
  assert.equal(matchesToolkitCard(card,{query:'WATER pump',category:'rotating',kind:'equipment'}),true);
  for(const choice of [{query:'pump solar'},{category:'power'},{kind:'variant'}])assert.equal(matchesToolkitCard(card,choice),false);
  assert.equal(matchesToolkitCard(card,{query:'  '}),true);
  assert.equal(matchesToolkitCard({search:'<script>',category:'x'},{query:'<script>'}),true,'search is plain text, never HTML or code');
});

test('source licence overrides preserve package terms without relabelling unrelated capabilities',()=>{
  const license=sourceLicenseResolver([{prefix:'software/cadagent/webkit/scada/',license:'UNLICENSED'},
    {prefix:'.agents/skills/scada-model-adaptation/',license:'UNLICENSED'}]);
  assert.equal(license('software/cadagent/webkit/scada/ui/README.md'),'UNLICENSED');
  assert.equal(license('.agents/skills/scada-model-adaptation/SKILL.md'),'UNLICENSED');
  assert.equal(license('software/cadagent/webkit/scada-extra/README.md'),'MIT');
  assert.equal(license('docs/toolkit.md'),'MIT');
  for(const records of [null,{},[{prefix:'../outside/',license:'MIT'}],[{prefix:'docs/',license:''}],
    [{prefix:'docs/',license:'MIT'},{prefix:'docs/',license:'UNLICENSED'}]])assert.throws(()=>sourceLicenseResolver(records),/licen[cs]e|license_overrides/);
});
