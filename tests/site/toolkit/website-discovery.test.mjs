import {topicNodes,topicTree,topicPlacement,readerNav,updateTime,topicGlyphs,topicSprite} from '../../../tools/site/compiler/site-explore-shell.mjs';
/** Shared discovery uses real producer identities, not a second authored registry or inflated source counts. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gzipSync} from 'node:zlib';
import path from 'node:path';
import {builtSite} from '../built-site.mjs';
import {searchPatterns} from '../../../software/cadagent/webkit/ui/gallery.js';
import {discoveryModel,discoveryHTML,prepareDiscoveryPage} from '../../../tools/site/compiler/site-discovery.mjs';
const site=await builtSite('cad-agent-discovery-site-');test.after(()=>site.done());
const json=async f=>JSON.parse(await readFile(path.join(site.dir,f),'utf8'));
const model=await json('discovery.json'),catalog=await json('catalog.json'),refs=await json('catalog/references/records.json');
const refIndex=await json('catalog/references/index.json');
const fullSources=new Map((await Promise.all(refIndex.areas.map(a=>json(new URL(a.json).pathname.slice(1))))).flatMap(a=>a.records.map(r=>[r.id,r])));
const html=await readFile(path.join(site.dir,'explore.html'),'utf8');
const query=q=>model.items.filter(x=>searchPatterns(q).every(r=>r.test(model.search_fields.map(field=>x[field]||'').join(' ').toLowerCase())));

test('derived identities cover every catalogue entry and canonical source exactly once without rewriting their roles',()=>{
 assert.equal(model.schema,'cad-agent-discovery/1');
 assert.equal(model.revision,catalog.revision);
 const sources=Array.isArray(refs.records)?refs.records:Object.values(refs.records);
 assert.equal(new Set(model.items.map(x=>x.id)).size,model.items.length);
 assert.equal(model.source_counts.catalogue_entries,catalog.items.length);
 assert.equal(model.source_counts.reference_records,sources.length);
 for(const c of catalog.items){const x=model.items.filter(x=>x.collection==='catalogue'&&x.source_id===c.id);assert.equal(x.length,1,c.id);assert.equal(x[0].adoption,c.status);assert.equal(x[0].area_maturity,c.maturity);assert.equal(x[0].url,c.doc||c.url);}
 for(const r of sources){const x=model.items.filter(x=>x.collection==='reference'&&x.source_id===r.id);assert.equal(x.length,1,r.id);assert.equal(x[0].evidence,r.evidence);assert.equal(x[0].status,r.status);assert.equal(x[0].confidence,fullSources.get(r.id).confidence.level);assert.ok(x[0].url.endsWith('#'+r.id));assert.equal(x[0].adoption,undefined);assert.equal(x[0].area_maturity,undefined);}
});

test('real body incidents, canonical IDs, aliases and unplaced sources have useful exact destinations',()=>{
 assert.ok(query('counterbores').some(x=>x.url.includes('/docs/common-issues#issue-')));
 const disassembly=query('disassembly').find(x=>x.title.includes('disassembly'));
 assert.ok(disassembly?.url.endsWith('/lessons/process/user-intent-and-requirements#treat-doesnt-block-disassembly-as-a-hard-requirement'));
 assert.ok(query('snap fits').some(x=>x.url.endsWith('/docs/compliant')));
 for(const q of ['pem-consumer-electronics-design-guide-2021','pem-ce-guide-2021'])assert.ok(query(q).some(x=>x.url.endsWith('/references/fasteners-and-hardware#pem-consumer-electronics-design-guide-2021')));
 assert.ok(query('abbud-riveted-joints').some(x=>x.url.endsWith('/references/unplaced#abbud-riveted-joints')));
 const seat=model.items.find(x=>x.collection==='section' && x.url.endsWith('#move-the-head-seat-to-reach-a-standard-screw-length'));
 assert.match(seat.summary,/If the computed length/);assert.doesNotMatch(seat.summary,/What happened|Incident:/);
 for (const [q,path] of [['validate rendered','/docs/rendered-motion'],['download McMaster','/skills/mcmaster-parts/SKILL'],['twist printed','#try-it-the-torsion-snap-explorer']]) assert.ok(query(q).some(x=>x.url.endsWith(path)),q);
 assert.deepEqual(query('zz-no-such-fixture-599'),[]);
});

test('same external URL retains distinct adoption and evidence roles, never a duplicate source identity',()=>{
 const project=model.items.find(x=>x.source_id==='project-jdilla1277-agentcad'),source=model.items.find(x=>x.collection==='reference'&&x.source_id==='agentcad');
 assert.ok(project);assert.ok(source);assert.equal(project.url,source.source_url);assert.notEqual(project.id,source.id);assert.equal(project.group,'external');assert.equal(source.group,'references');assert.equal(source.adoption,undefined);
 assert.ok(query('agentcad').includes(project));assert.ok(query('agentcad').includes(source));
});

test('every derived section and source link resolves to its exact producer anchor',async()=>{
 for(const x of model.items){const u=new URL(x.url);if(u.origin!==model.origin||!u.hash)continue;const h=await readFile(path.join(site.dir,u.pathname+'.html'),'utf8');const id=decodeURIComponent(u.hash.slice(1));assert.ok(h.includes(`id="${id}"`),x.id+' '+x.url);}
});

test('compact projection avoids reference detail tables, article dumps and cover cards for hundreds of sources',()=>{
 assert.doesNotMatch(html,/class="refs-table"|class="card cat-card"/);
 assert.ok(html.includes('Source: Not yet read'));
 assert.ok(html.includes('Outside-tool adoption'));
 assert.ok(html.includes('value="candidate"'));
 assert.ok(!html.includes('Full catalogue'));
 assert.ok(html.includes('Entry type')&&html.includes('Licence')&&html.includes('Has a working example'));
 assert.doesNotMatch(html, /class="mat-dots"|<legend>Maturity/);
 assert.ok(html.includes('About these results'));
 assert.match(html, /<details class="discover-group" id="references" data-group="references"/);
 assert.ok(!/<details class="discover-group"[^>]*\bopen/.test(html), 'no-script groups start collapsed');
 assert.ok(html.includes('/discovery.json'));
 assert.ok(!/<li data-item[^>]*><a href="https:\/\/cad-agent.valpatel.com/.test(html), 'local result clicks stay on the reviewed producer');
 assert.ok(!/<img[^>]*src="https?:/.test(html), 'site-owned images stay same-origin under real CSP');
 assert.match(html, /<\/span> <span class="result-summary">/, 'title/summary remain separate search words');
 // Budget is for compact links/search metadata, not a second full reference table or article copies.
 const compactReferences=[...html.matchAll(/<li data-item id="reference:[\s\S]*?<\/li>/g)].map(m=>m[0]);
 assert.equal(compactReferences.length,model.source_counts.reference_records);
 assert.ok(compactReferences.reduce((n,s)=>n+Buffer.byteLength(s),0)<model.source_counts.reference_records*700,'reference projection remains compact; richer catalogue details are not copied onto sources');
 assert.ok(compactReferences.every(s=>!s.includes('result-details')&&!s.includes('result-cover')));
 const n=model.items.length;
 // Dated before/after: c301 Explore 856890 B / 132119 gzip; creator/original links 941750 B / 147813 gzip.
 // Accepted source now has 815 references and 1201 results: actual 942605 B versus base 890700 B.
 // New original destinations share an 80 B/canonical-reference aggregate allowance: 955900 B total.
 // Keep 700 B/reference, the base 700 B/result, gzip and DOM guards; no summaries/details added to references.
 const rawBytes=Buffer.byteLength(html),gzipBytes=gzipSync(html).length,tags=(html.match(/<[a-z][^>]*>/g)||[]).length;
 assert.ok(rawBytes<50000+n*700+model.source_counts.reference_records*80,'base 700 bytes/result plus shell and 80 bytes/reference original-link allowance');
 assert.ok(rawBytes<1000000,'1 MB absolute raw cap');
 assert.ok(gzipBytes<20000+n*110,'110 gzip bytes/result plus shell');
 assert.ok(gzipBytes<180000,'180 kB absolute gzip cap');
 assert.ok(tags<800+n*5,'compact result DOM plus fixed shell');
 assert.ok(tags<9000,'9000-tag absolute cap');
});

test('generated pitfall destinations are unique and hostile text is inert',()=>{
 const page={file:'docs/practice/common-issues.md'},input='<table><tr><td>Same issue</td><td>First</td></tr><tr><td>Same issue</td><td>Second</td></tr></table>';
 const h=prepareDiscoveryPage(page,input);assert.match(h,/id="issue-same-issue"/);assert.match(h,/id="issue-same-issue-1"/);
 assert.equal(prepareDiscoveryPage({file:'docs/else.md'},input),input);
 const r={id:'unsafe',title:'<img src=x onerror=alert(1)>',url:'javascript:alert(1)',status:'catalogued',evidence:{class:'snippet-only'}};
 const refs={refs:{records:new Map([['unsafe',r]]),aliases:new Map()},placed:new Map([['unsafe',['unplaced']]]),home:()=>'/references/unplaced#unsafe'};
 const x=discoveryModel({catalog:{items:[]},pages:[],references:refs,ORIGIN:'https://example.test',revision:'a',pageURL:()=>'/'});
 assert.equal(x.items[0].source_url,null);assert.equal(x.items[0].evidence,'snippet-only');
 const body=discoveryHTML(x,{areas:{domains:[]}});assert.doesNotMatch(body,/<img src=x|javascript:|onerror=alert\(1\)>/);assert.ok(body.includes('&lt;img'));
 assert.throws(()=>discoveryModel({catalog:{items:[{id:'bad',url:'javascript:alert(1)',areas:[]}]},pages:[],references:{refs:{records:new Map(),aliases:new Map()}},ORIGIN:'https://example.test',pageURL:()=>'/'}),/unsafe destination/);
});

// Pure topic-shell/time/detail contracts share this existing discovery owner.
const areas={domains:[{slug:'mechanical',title:'Mechanical',areas:[{slug:'fasteners',title:'Fasteners',topics:[{slug:'bosses',title:'Bosses',pages:['boss.md']}]}]}]};
const pages=[{file:'boss.md',title:'A screw boss'},{file:'other.md',title:'Other',section:'guides'}];const pageURL=f=>'/docs/'+f.slice(0,-3);
test('browse and reader share real nested taxonomy and preserve exact local page destinations',()=>{
 const nodes=topicNodes(areas);assert.equal(nodes.get('bosses').parent,'fasteners');assert.equal(nodes.get('bosses').domain,'mechanical');
 const browse=topicTree({areas,pages,pageURL,browse:true}),reader=readerNav({areas,pages,pageURL,current:'/docs/boss'});
 for(const html of [browse,reader]){for(const id of ['mechanical','fasteners','bosses','cross-cutting'])assert.ok(html.includes('data-topic="'+id+'"'));assert.ok(html.includes('data-topic="bosses"'));assert.doesNotMatch(html,/maturity|mat-dots/);}
 assert.ok(browse.includes('href="/explore?area=bosses"'));
 assert.match(reader,/href="\/docs\/boss" aria-current="page"/);assert.match(reader,/action="\/explore"/);assert.ok(reader.includes('name="q"'));
 assert.ok(reader.includes('data-topic="bosses" data-tone="mechanical" open'));
 const wrong=readerNav({areas,pages,pageURL,current:'/docs/missing'});assert.doesNotMatch(wrong,/aria-current="page"/);
});
test('recorded times display exact seconds in Pacific with DST, preserving full datetime',()=>{
 const winter=updateTime('2026-11-12T03:04:01+00:00');assert.equal(winter.datetime,'2026-11-12T03:04:01+00:00');assert.match(winter.label,/Nov 11, 2026, 7:04:01 PM PST/);
 assert.match(updateTime('2026-07-12T03:04:01Z').label,/8:04:01 PM PDT/);
 const date=updateTime('2026-11-12');assert.equal(date.datetime,'2026-11-12');assert.doesNotMatch(date.label,/PST|PDT|AM|PM/);
 assert.throws(()=>updateTime('not a time'));assert.throws(()=>updateTime('2026-11-12T03:04'));
});

test('one placement projection gives every tree page all its browse ancestors and explicit cross-cutting placement',()=>{
 const placement=topicPlacement({...areas,cross_cutting:{pages:['boss.md']}},pages,pageURL);
 assert.deepEqual(placement.byPage.get('/docs/boss'),['bosses','cross-cutting']);
 assert.deepEqual(placement.ancestors(placement.byPage.get('/docs/boss')),['bosses','fasteners','mechanical','cross-cutting']);
 assert.deepEqual(placement.byPage.get('/docs/other'),['cross-cutting']);
 const nav=readerNav({areas,pages,pageURL,current:'/docs/boss',outlineHTML:'<ol class="cad-nav-outline"><li><a href="#head">Head</a></li></ol>'});
 assert.ok(nav.includes('class="explore-mobile-outline"'));assert.ok(nav.includes('href="#head"'));
});

test('on-demand detail destinations retain local previews and reject executable/credential URLs',async()=>{
 globalThis.location={origin:'https://preview.example'};
 try{const {detailURL}=await import('../../../tools/site/assets/discovery.js');
  assert.equal(detailURL('https://cad-agent.valpatel.com/docs/toolkit#holes-clear'),'/docs/toolkit#holes-clear');
  assert.equal(detailURL('https://github.com/owner/tool'),'https://github.com/owner/tool');
  assert.equal(detailURL('javascript:alert(1)'),null);assert.equal(detailURL('https://user:pass@example.com'),null);
 }finally{delete globalThis.location;}
});

test('glyph sprite preserves every stable symbol while reusing identical artwork',async()=>{
 const {glyphSprite,glyphFor}=await import('../../../tools/site/compiler/catalog-art.mjs');
 const slugs=['unplaced','fixture-unknown-topic','fixture-other-topic'];const sprite=glyphSprite(slugs);
 for(const slug of slugs)assert.ok(sprite.includes(`id="g-${slug}"`));
 assert.equal((sprite.match(/<use href="#g-unplaced"/g)||[]).length,2);
 assert.ok(glyphFor(slugs[0])===glyphFor(slugs[1]));
 assert.equal((glyphSprite(['unplaced','unplaced']).match(/<symbol/g)||[]).length,1);
});

test('unillustrated topics reuse nearest ancestor artwork without changing topic symbol identities',()=>{
 const taxonomy={domains:[{slug:'mechanical',areas:[{slug:'cad-modelling',topics:[{slug:'motor-mounts'},{slug:'gears'}]},{slug:'fixture-unillustrated-area',topics:[{slug:'fixture-deep-topic'}]}]}]};
 const art=topicGlyphs(taxonomy);
 assert.equal(art.get('motor-mounts'),'cad-modelling');assert.equal(art.get('gears'),'gears');
 assert.equal(art.get('fixture-deep-topic'),'mechanical');assert.equal(art.get('cross-cutting'),'cross-cutting');
 const sprite=topicSprite(taxonomy);
 assert.match(sprite,/<symbol id="g-motor-mounts"[^>]*><use href="#g-cad-modelling"\/><\/symbol>/);
 for(const slug of topicNodes(taxonomy).keys())assert.ok(sprite.includes(`id="g-${slug}"`));
 assert.equal(topicSprite(taxonomy),sprite,'deterministic output');
});

test('legacy catalogue descriptions escape canonical plain text without passing it through HTML extraction',()=>{
 const what='A literal <img src=x onerror=alert(2)> and <script>alert(2)</script> description';
 const c={id:'fixture-literal',kind:'project',type:'upstream',status:'candidate',name:'Literal fixture',what,url:'https://example.test/tool',areas:[],related:[]};
 const catalog={items:[c]},references={refs:{records:new Map(),aliases:new Map()},placed:new Map()};
 const projection=discoveryModel({catalog,pages:[],references,ORIGIN:'https://example.test',revision:'fixture',pageURL:()=>'/'});
 const before=JSON.stringify(projection);
 const html=discoveryHTML(projection,{areas:{domains:[],maturity:[]},catalog,legacy:true});
 assert.ok(html.includes('A literal &lt;img src=x onerror=alert(2)&gt; and &lt;script&gt;alert(2)&lt;/script&gt; description'));
 assert.doesNotMatch(html,/<img src=x|<script>alert/);
 assert.equal(JSON.stringify(projection),before,'legacy rendering does not mutate discovery projection semantics');
});


test('shared reference rows credit creators and link originals without copying full records',()=>{
 const record={id:'credit-example',title:'Original study',authors:['Ada Example'],org:'Example Lab',url:'https://example.com/source?dlpdf=t&part=1',summary:'A practical source',status:'source',evidence:{class:'read'}};
 const references={refs:{records:new Map([[record.id,record]]),aliases:new Map()},placed:new Map([[record.id,['fasteners']]]),home:id=>'/references/fasteners#'+id};
 const areas={domains:[{slug:'mechanical',title:'Mechanical',areas:[{slug:'fasteners',title:'Fasteners'}]}],maturity:[]};
 const input={catalog:{items:[]},pages:[],references,ORIGIN:'https://cad-agent.valpatel.com',revision:'r',pageURL:()=>''};
 const m=discoveryModel(input),item=m.items[0];
 assert.equal(item.creator,'Ada Example · Example Lab');
 assert.ok(m.search_fields.includes('creator'));
 assert.ok(m.search_fields.map(k=>item[k]||'').join(' ').includes('Ada Example'));
 assert.ok(!item.search.includes('Ada Example'),'visible creator is not duplicated in hidden search metadata');
 const html=discoveryHTML(m,{areas,catalog:input.catalog});
 assert.match(html,/Ada Example · Example Lab · <a href="https:\/\/example.com\/source\?dlpdf=t&amp;part=1">Read original<\/a>/);
 assert.ok(!html.includes('result-details'));
 assert.equal(m.source_counts.reference_records,1);
 record.authors=['<img src=x onerror=alert(1)>'];record.url='javascript:alert(1)';
 const unsafe=discoveryHTML(discoveryModel(input),{areas,catalog:input.catalog});
 assert.ok(unsafe.includes('&lt;img src=x onerror=alert(1)&gt;'));
 assert.doesNotMatch(unsafe,/<img src=x|href="javascript:/);
});


test('outside original links survive legacy group remapping without guessed creator metadata',()=>{
 const areas={domains:[{slug:'mechanical',title:'Mechanical',areas:[{slug:'fasteners',title:'Fasteners'}]}],maturity:[]};
 const references={refs:{records:new Map(),aliases:new Map()},placed:new Map(),home:()=>''};
 for(const kind of ['project','library','benchmark']){
  const entry={id:kind+'-example',kind,name:'known-owner/example',url:'https://example.com/project?view=full&x=1',areas:['fasteners'],status:'reference',cover:'/cover.svg'};
  const catalog={items:[entry]},m=discoveryModel({catalog,pages:[],references,ORIGIN:'https://cad-agent.valpatel.com',revision:'r',pageURL:()=>''});
  assert.equal(m.items[0].creator,undefined,'no creator inferred from URL or repository identity');
  for(const legacy of [false,true]){
   const html=discoveryHTML(m,{areas,catalog,legacy});
   const label=kind==='benchmark'?'Visit original':'Visit project';
   assert.ok(html.includes('href="https://example.com/project?view=full&amp;x=1">'+label+'</a>'),kind+' legacy='+legacy);
  }
 }
});

test('every recorded author remains searchable alongside their organisation',()=>{
 for(const source of fullSources.values())for(const author of source.authors||[]){
  if(typeof author!=='string'||!author.trim())continue;
  assert.ok(query(author).some(item=>item.collection==='reference'&&item.source_id===source.id),source.id+': '+author);
 }
});
