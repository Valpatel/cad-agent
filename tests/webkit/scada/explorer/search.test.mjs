import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {filterScenarios, scenarioMatchesQuery, scenarioFacets} from '../../../../software/cadagent/webkit/scada/explorer/search.mjs';
const {scenarios}=JSON.parse(await readFile(new URL('../../../../software/cadagent/webkit/scada/sim/scenarios/index.json',import.meta.url),'utf8'));
const matches=query=>filterScenarios(scenarios,{query}).map(item=>item.id);

test('chooser examples and the requested industries have explicit searchable aliases',()=>{
  const expected={Beer:'brewery',cookies:'fortune-cookies',minerals:'mineral-crushing',medicine:'pharma-oral-liquid',medicines:'tablets','wine making':'winery','brewing beer':'brewery','fortune cookie factory':'fortune-cookies','shampoo manufacturing facility':'shampoo','beverage manufacturing':'carbonated-beverages','industrial chemicals':'industrial-detergent',concrete:'concrete-batching','mineral processing':'mineral-flotation'};
  for(const [query,id] of Object.entries(expected))assert.ok(matches(query).includes(id),`${query} should find ${id}`);
});
test('all query tokens match across metadata, independent of punctuation and word order',()=>{
  assert.ok(matches('  FILTER, beer  ').includes('brewery'));
  assert.ok(matches('fortune-cookies').includes('fortune-cookies'));
  assert.ok(matches('brewi').includes('brewery'));
  assert.deepEqual(matches('beer impossibleinstrument'),[]);
  assert.deepEqual(matches('unlisted-scenario'),[]);
  assert.equal(scenarioMatchesQuery({title:'Évaporation',technologies:['Nutrient-film technique']},'evapor nutrient'),true);
});
test('sector filtering composes with search and every component type is discoverable',()=>{
  const brewery=scenarios.find(item=>item.id==='brewery');
  assert.ok(filterScenarios(scenarios,{query:'beer',sector:brewery.sector}).some(item=>item.id==='brewery'));
  assert.deepEqual(filterScenarios(scenarios,{query:'beer',sector:'No such sector'}),[]);
  assert.equal(filterScenarios(scenarios).length,scenarios.length);
  for(const entry of scenarios)for(const type of entry.componentTypes)assert.ok(scenarioMatchesQuery(entry,type),`${entry.id}: ${type}`);
});
test('technology and facility are independent facets that compose with sector and aliases',()=>{
  const rows=[{id:'raft',title:'Raft growing',sector:'Agriculture',technologies:['dwc','aquaponics'],facility:'Greenhouse',searchTerms:['deep water culture']},{id:'film',title:'Film channel',sector:'Agriculture',technologies:['nft','hydroponics'],facility:'Indoor room'},{id:'industrial',title:'Industrial water',sector:'Utilities'}];
  assert.deepEqual(filterScenarios(rows,{sector:'Agriculture',technology:'dwc',facility:'Greenhouse',query:'deep water'}).map(x=>x.id),['raft']);
  assert.deepEqual(filterScenarios(rows,{technology:'dwc',facility:'Indoor room'}),[]);
  assert.deepEqual(scenarioFacets(rows),{sectors:['Agriculture','Utilities'],technologies:['aquaponics','dwc','hydroponics','nft'],facilities:['Greenhouse','Indoor room']});
  assert.deepEqual(filterScenarios(rows,{query:'indoor hydro'}).map(x=>x.id),['film']);
});
test('agriculture technology aliases discover the canonical shared systems',()=>{
  const expected={'fish farm':'aquaponics-media-bed',raft:'aquaponics-dwc','deep water culture':'aquaponics-dwc','nutrient film':'hydroponics-nft','flood and drain':'hydroponics-ebb-flow','grow lights':'indoor-aeroponics',LED:'indoor-aeroponics'};
  for(const [query,id] of Object.entries(expected))assert.ok(matches(query).includes(id),`${query} should find ${id}`);
});
