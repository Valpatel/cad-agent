import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync, statSync} from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {SCADA_INPUTS, TOOLKIT_ROUTES, scadaToolkitModel, toolkitPages, toolkitFullText, toolkitCapabilities, buildGuideCaptionMissing, BUILD_GUIDE_PHRASES} from '../../../tools/site/compiler/site-toolkit.mjs';
import {YAML} from '../npm-context.mjs';
import {matchesToolkitCard} from '../../../tools/site/assets/toolkit.js';
import {sourceLicenseResolver} from '../../../tools/site/compiler/site-catalog.mjs';

import {checkManifoldSource, manifoldGeometryMismatches} from './toolkit-examples-browser.mjs';

test('original STEP reports the failed measurements independently', () => {
  const reference = { format: 'STEP', triangles: 9518, bounds: [114.300003, 114.197014, 83.184998] };
  assert.deepEqual(manifoldGeometryMismatches(reference), []);
  assert.deepEqual(manifoldGeometryMismatches({ ...reference, triangles: 8305 }),
    [{ field: 'triangles', expected: 9518, actual: 8305 }]);
  const wrongBounds = [114.302, 114.197, 83.185];
  assert.deepEqual(manifoldGeometryMismatches({ ...reference, format: 'STL', bounds: wrongBounds }), [
    { field: 'format', expected: 'STEP', actual: 'STL' },
    { field: 'boundsMm', expected: [114.300, 114.197, 83.185], actual: wrongBounds },
  ]);
});

test('a failed original download preserves the measured geometry and its missing digest', async () => {
  const original = '/files/pump-manifold.step';
  const page = {
    getByRole: () => ({ getAttribute: async () => original }),
    url: () => 'https://example.test/viewer',
    request: { get: async () => { throw new Error('connection reset'); } },
  };
  const failures = [];
  await checkManifoldSource(page, original,
    { format: 'STEP', triangles: 8305, bounds: [114.3, 114.197, 83.185] }, message => failures.push(message));
  assert.match(failures[0], /pump-manifold[.]step: connection reset/);
  const details = JSON.parse(failures[1].slice('unexpected manifold geometry: '.length));
  assert.deepEqual(details, { original, sha256: null, differences: [{ field: 'triangles', expected: 9518, actual: 8305 }] });
});

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
  assert.equal(model.license,'MIT');
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

test('SCADA human documentation and agent workflows use the existing rendered site owners',()=>{
  const {pages}=toolkitPages(scadaToolkitModel(fixture()));
  for(const page of pages.filter(page=>page.url.startsWith('/toolkit/scada'))) {
    assert.match(page.body,/MIT-licensed/);
    assert.doesNotMatch(page.body,/UNLICENSED|href="\/kit\/scada\/[^"#?]*\.md/);
    assert.match(page.body,/href="\/repo\/folders\/d-docs\/d-practice\/d-scada\/README">Use &(?:amp;)? extend/);
  }
  const overview=pages.find(page=>page.url==='/toolkit/scada');
  for(const name of ['component-authoring','system-authoring','model-adaptation','viewer-review','distribution-review']) {
    assert.ok(overview.body.includes(`/skills/scada-${name}/SKILL`));
    assert.ok(overview.markdown.includes(`/skills/scada-${name}/SKILL`));
  }
  assert.match(overview.body,/href="\/docs\/agent-workflow">For agents/);
  for(const owner of ['ui','sim'])assert.ok(overview.body.includes(`/repo/folders/d-software/d-cadagent/d-webkit/d-scada/d-${owner}/README`));
});

test('combined Toolkit agent text binds every local link to its published origin without rewriting examples',()=>{
  const pages=toolkitPages(scadaToolkitModel(fixture())).pages;
  const full=toolkitFullText(pages,'https://cad.example');
  const links=[...full.matchAll(/\]\(([^)\s]+)/g)].map(m=>m[1]);
  assert.ok(links.length>10);assert.ok(links.every(href=>href.startsWith('https://cad.example/')));
  assert.match(full,/https:\/\/cad\.example\/kit\/scada\/explorer\/index\.html\?scenario=wastewater-digester/);
  assert.match(full,/Source: https:\/\/cad\.example\/toolkit\/scada\/elements\.md/);
  const example=toolkitFullText([{url:'/toolkit/scada',markdown:'[local](elements?q=pump#state "Equipment") [anchor](#models) [external](https://other.example/a?q=b) [protocol-relative](//other.example/b)\n\n`[literal](/code)`\n\n```md\n[literal](/fenced)\n```'}],'https://cad.example');
  assert.ok(example.includes('[local](https://cad.example/toolkit/elements?q=pump#state "Equipment")'));
  assert.ok(example.includes('[anchor](https://cad.example/toolkit/scada.md#models)'));
  assert.ok(example.includes('[external](https://other.example/a?q=b)'));
  assert.ok(example.includes('[protocol-relative](https://other.example/b)'));
  assert.ok(example.includes('`[literal](/code)`'));assert.ok(example.includes('[literal](/fenced)'));
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


test('capabilities open owned working examples, with real previews and explicit planned boundaries',()=>{
  const inputs=Object.fromEntries(Object.entries(SCADA_INPUTS).map(([key,file])=>[key,read(file)]));
  const has=file=>existsSync(path.join(root,file));
  const model=scadaToolkitModel({...inputs,has});
  const cards=toolkitCapabilities(model,{has,catalog:[{id:'demo-fourbar-animator',url:'https://cad-agent.valpatel.com/docs/linkages#try-it-the-four-bar-animator'}]});
  assert.equal(cards.find(card=>card.id==='mechanisms').href,'/docs/linkages#try-it-the-four-bar-animator');
  assert.throws(()=>toolkitCapabilities(model,{catalog:[{id:'demo-fourbar-animator',url:'https://external.invalid/demo'}]}),/must be locally published/);
  assert.deepEqual(cards.map(card=>card.id),['scada-elements','scada-simulations','models','robot-replay','files','assembly','mechanisms','calculators']);
  const file=cards.find(card=>card.id==='files');
  const capture=read('tools/site/assets/toolkit/SOURCE.json').captures['file-review'];
  assert.equal(file.href, capture.route + '&nav=1', 'the photo and card open the same original file');
  assert.equal(capture.scene.source, 'pump-manifold.stl');
  assert.equal(file.sourceDownload, '/web/toolkit/pump-manifold.step');
  const replay=cards.find(card=>card.id==='robot-replay');
  assert.match(replay.description,/Gyropup, a work-in-progress wheel-legged robot, in recorded MuJoCo runs from its dated snapshot/);
  for (const phrase of ["Recorded solver output", "replayed, not recomputed", "not a validation of hardware"]) assert.ok(replay.description.includes(phrase), phrase);
  assert.equal(replay.href,'/kit/simulation/examples/gyropup-v2/viewer.html?nav=1');
  assert.equal(replay.image,'/kit/simulation/examples/gyropup-v2/card-still.webp');
  assert.equal(replay.motion,'/kit/simulation/examples/gyropup-v2/card.webp');
  assert.ok(replay.docs.startsWith('/repo/folders/'));
  for(const card of cards) {
    assert.ok(card.image.startsWith('/') && card.alt.length>20,card.id);
    assert.ok(card.href.startsWith('/') && card.action.length>3 && card.docs.startsWith('/'),card.id);
    assert.doesNotMatch(card.href,/^#|javascript:|https?:/);
  }
  const result=toolkitPages(model,{has});
  const overview=result.pages.find(page=>page.url==='/toolkit');
  assert.equal((overview.body.match(/data-toolkit-launch/g)||[]).length,cards.length);
  for(const card of cards) assert.ok(overview.markdown.includes(card.href));
  assert.match(overview.body,/PCB layer review, electrical-panel diagrams and harness views are planned/);
  const models=result.pages.find(page=>page.url==='/toolkit/models');
  assert.match(models.body,/<cad-model[^>]*src="\/web\/models\/gyropup.json"/);
  assert.match(models.body,/not a robot dynamics simulation/);
  assert.deepEqual(models.css,['/kit/model/model.css']);
  assert.throws(()=>toolkitPages(model,{has:file=>has(file) && !file.endsWith('file-review.webp')}),/missing example asset.*file-review.webp/);
  assert.throws(()=>toolkitPages(model,{has:file=>has(file) && !file.endsWith('model/viewer.html')}),/missing example asset.*model\/viewer.html/);
  assert.throws(()=>toolkitPages(model,{has:file=>has(file) && !file.endsWith('gyropup-v2/card-still.webp')}),/missing example asset.*gyropup-v2\/card-still.webp/);
  assert.throws(()=>toolkitPages(model,{has:file=>has(file) && !file.endsWith('gyropup-v2/card.webp')}),/missing example asset.*gyropup-v2\/card.webp/);
  assert.match(overview.body,/<img src="\/kit\/simulation\/examples\/gyropup-v2\/card-still.webp"[^>]*loading="lazy" data-motion-src="\/kit\/simulation\/examples\/gyropup-v2\/card.webp">/);
});

test('published assembly example preserves the complete source-bound fixture closure',()=>{
  const owner='tools/site/assets/toolkit/assembly/';
  const source='tests/fixtures/assembly-plan/';
  const guide=read(owner+'guide.json'), view=read(owner+'view.json');
  for(const name of ['guide.json',guide.model.file,guide.assembly_plan.file,...view.parts.map(part=>part.file)]) {
    assert.deepEqual(readFileSync(path.join(root,owner,name)),readFileSync(path.join(root,source,name)),name);
  }
  assert.equal(guide.snapshot.source_commit,'1'.repeat(40),'Synthetic input identity is retained');
  const manifest=read('tools/site/assets/toolkit/SOURCE.json');
  assert.equal(manifest.schema,'cad-agent.toolkit-examples/1');
  assert.equal(Object.keys(manifest.copies).length,8);
  assert.match(manifest.scope,/no physical or project qualification/);
  execFileSync(process.execPath,['tools/site/figures/toolkit-examples.mjs','--check'],{cwd:root,stdio:'pipe'});
});

test('the build-guide card features the real Gyropup turret guide, closed over its own hashes (#811)',()=>{
  const example='software/cadagent/webkit/assembly/examples/gyropup-turret/';
  const guide=read(example+'guide.json'), view=read(example+guide.model.file), receipt=read(example+'receipt.json');
  const sha=file=>createHash('sha256').update(readFileSync(path.join(root,example,file))).digest('hex');
  assert.equal(view.schema,'cad-agent-model/1','one packed model binds every mesh');
  for(const binding of [guide.model,{file:view.bin,sha256:view.sha256}]) assert.equal(sha(binding.file),binding.sha256,binding.file);
  assert.ok(statSync(path.join(root,example,view.bin)).size<512*1024,'the packed turret stays small');
  assert.equal(receipt.license,'MIT'); assert.equal(receipt.project,'Valpatel/gyropup');
  assert.equal(guide.snapshot.source_commit,receipt.revision); assert.match(receipt.revision,/^[0-9a-f]{40}$/);
  assert.notEqual(guide.snapshot.source_commit,'1'.repeat(40),'the synthetic fixture is no longer what visitors see');
  assert.ok(readFileSync(path.join(root,example,'LICENSE.txt'),'utf8').startsWith('MIT License'));
  // At least five steps over real parts, each adding highlighted parts drawn back along their way in, every part used.
  assert.ok(guide.steps.length>=5);
  for(const [i,step] of guide.steps.entries()) {
    assert.ok(step.highlight.length && step.text.length>40,step.id);
    assert.deepEqual(step.parts.slice(-step.highlight.length),step.highlight,`${step.id} adds its highlighted parts last`);
    if(i) assert.deepEqual(step.parts.slice(0,-step.highlight.length),guide.steps[i-1].parts,`${step.id} keeps the earlier parts`);
  }
  assert.deepEqual(guide.steps.at(-1).parts.slice().sort(),view.parts.map(p=>p.name).sort());
  // Fasteners after the parts they hold: the cartridge thumbscrew comes after the cartridge, the screws with their board.
  const stepOf=name=>guide.steps.findIndex(step=>step.highlight.includes(name));
  assert.ok(stepOf('ct_thumbscrew')>stepOf('cartridge_body'));
  assert.ok(guide.steps[stepOf('base_board_screws')].highlight.indexOf('base_board_screws')>guide.steps[stepOf('base_board')].highlight.indexOf('base_board'));
  assert.match(guide.source.qualification,/Example sequence/);
  for(const phrase of ['work-in-progress','not a verified build procedure','CAD step order does not prove']) assert.ok(guide.source.qualification.includes(phrase),phrase);
  const manifest=read('tools/site/assets/toolkit/SOURCE.json');
  assert.equal(manifest.schema,'cad-agent.toolkit-examples/1');
  assert.equal(manifest.featured.path,example.slice(0,-1)); assert.equal(manifest.featured.revision,receipt.revision);
  assert.equal(manifest.captures.assembly.scene.instruction,'step-11');
  // The rail keeps its published URL, unlinked: no card or caption leads to it.
  assert.ok(!toolkitCapabilities(scadaToolkitModel({...Object.fromEntries(Object.entries(SCADA_INPUTS).map(([key,file])=>[key,read(file)])),has:file=>existsSync(path.join(root,file))})).some(c=>/web\/toolkit\/assembly\/|synthetic rail/i.test(c.href+c.description+c.alt)));
  assert.match(manifest.scope,/no physical or project qualification/);
  execFileSync(process.execPath,['tools/site/figures/toolkit-examples.mjs','--check'],{cwd:root,stdio:'pipe'});
});

test('build-guide captions say what the guide is, on the toolkit and home cards; planted captions are refused (#811)',()=>{
  const inputs=Object.fromEntries(Object.entries(SCADA_INPUTS).map(([key,file])=>[key,read(file)]));
  const model=scadaToolkitModel({...inputs,has:file=>existsSync(path.join(root,file))});
  const card=toolkitCapabilities(model).find(c=>c.id==='assembly');
  assert.deepEqual(buildGuideCaptionMissing(card.description),[]);
  assert.equal(card.href,'/kit/model/viewer.html?guide=/kit/assembly/examples/gyropup-turret/guide.json&nav=1');
  const home=YAML.parse(readFileSync(path.join(root,'docs/home.yaml'),'utf8')).showcase.cards.find(c=>c.toolkit==='assembly');
  assert.deepEqual(buildGuideCaptionMissing(home.caption),[]);
  // Planted controls: the old synthetic caption, and each required phrase removed in turn, are each caught.
  assert.deepEqual(buildGuideCaptionMissing("Step through a synthetic rail assembly's declared insertion order, part by part."),BUILD_GUIDE_PHRASES);
  for(const phrase of BUILD_GUIDE_PHRASES) {
    const planted=home.caption.replace(new RegExp(phrase.replace(/[-]/g,'\\-'),'i'),'PLANTED');
    assert.deepEqual(buildGuideCaptionMissing(planted),[phrase],`removing "${phrase}" is caught`);
  }
});
