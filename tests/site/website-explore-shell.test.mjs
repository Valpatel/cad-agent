/** Pure navigation/timestamp contracts: this file never builds or launches a browser. */
import test from 'node:test';import assert from 'node:assert/strict';
import {topicNodes,topicTree,readerNav,updateTime} from '../../tools/site/compiler/site-explore-shell.mjs';
const areas={domains:[{slug:'mechanical',title:'Mechanical',areas:[{slug:'fasteners',title:'Fasteners',topics:[{slug:'bosses',title:'Bosses',pages:['boss.md']}]}]}]};
const pages=[{file:'boss.md',title:'A screw boss'},{file:'other.md',title:'Other',section:'guides'}];const pageURL=f=>'/docs/'+f.slice(0,-3);
test('browse and reader share real nested taxonomy and preserve exact local page destinations',()=>{
 const nodes=topicNodes(areas);assert.equal(nodes.get('bosses').parent,'fasteners');assert.equal(nodes.get('bosses').domain,'mechanical');
 const browse=topicTree({areas,pages,pageURL,browse:true}),reader=readerNav({areas,pages,pageURL,current:'/docs/boss'});
 for(const html of [browse,reader]){for(const id of ['mechanical','fasteners','bosses','cross-cutting'])assert.ok(html.includes('data-topic="'+id+'"'));assert.ok(html.includes('href="/docs/boss"'));assert.doesNotMatch(html,/maturity|mat-dots/);}
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
