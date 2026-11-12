/** Pure navigation/timestamp contracts: this file never builds or launches a browser. */
import test from 'node:test';import assert from 'node:assert/strict';
import {topicNodes,topicTree,topicPlacement,readerNav,updateTime} from '../../tools/site/compiler/site-explore-shell.mjs';
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
 try{const {detailURL}=await import('../../tools/site/assets/discovery.js');
  assert.equal(detailURL('https://cad-agent.valpatel.com/docs/toolkit#holes-clear'),'/docs/toolkit#holes-clear');
  assert.equal(detailURL('https://github.com/owner/tool'),'https://github.com/owner/tool');
  assert.equal(detailURL('javascript:alert(1)'),null);assert.equal(detailURL('https://user:pass@example.com'),null);
 }finally{delete globalThis.location;}
});

test('glyph sprite preserves every stable symbol while reusing identical artwork',async()=>{
 const {glyphSprite,glyphFor}=await import('../../tools/site/compiler/catalog-art.mjs');
 const slugs=['unplaced','fixture-unknown-topic','fixture-other-topic'];const sprite=glyphSprite(slugs);
 for(const slug of slugs)assert.ok(sprite.includes(`id="g-${slug}"`));
 assert.equal((sprite.match(/<use href="#g-unplaced"/g)||[]).length,2);
 assert.ok(glyphFor(slugs[0])===glyphFor(slugs[1]));
 assert.equal((glyphSprite(['unplaced','unplaced']).match(/<symbol/g)||[]).length,1);
});
