import test from 'node:test';
import assert from 'node:assert/strict';
import {selectScenario,selectEquipment} from '../../../../software/cadagent/webkit/scada/explorer/selection.mjs';
const entries=[{id:'natural',componentTypes:['generator'],componentVariants:[{type:'generator',variant:'natural-gas-enclosed'}]},{id:'portable',componentTypes:['generator'],componentVariants:[{type:'generator',variant:'gasoline-portable'}]},{id:'pump',componentTypes:['pump'],componentVariants:[{type:'pump',variant:'water'}]}];
test('type plus variant chooses the matching example before type-only fallback',()=>{
 assert.equal(selectScenario(entries,{componentType:'generator',variant:'gasoline-portable'}).entry.id,'portable');
 assert.equal(selectScenario(entries,{componentType:'generator'}).entry.id,'natural');
 assert.equal(selectScenario(entries,{componentType:'generator',variant:'unknown'}).fallback,'variant');
 assert.equal(selectScenario(entries,{componentType:'missing'}).fallback,'type');
});
test('an explicit valid scenario wins and missing scenario IDs fall back predictably',()=>{
 const selected=selectScenario(entries,{scenario:'pump',componentType:'generator',variant:'gasoline-portable'});
 assert.equal(selected.entry.id,'pump');assert.equal(selected.explicit,true);
 assert.equal(selectScenario(entries,{scenario:'removed'}).fallback,'scenario');
});
test('equipment selection matches the variant and resolves declared defaults without conflating fuels',()=>{
 const components=[{id:'natural',type:'generator'},{id:'portable',type:'generator',variant:'gasoline-portable'},{id:'pump',type:'pump',variant:'water'}];
 const resolve=item=>item.variant??'natural-gas-enclosed';
 assert.equal(selectEquipment(components,{componentType:'generator',variant:'gasoline-portable'},resolve).component.id,'portable');
 assert.equal(selectEquipment(components,{componentType:'generator',variant:'natural-gas-enclosed'},resolve).component.id,'natural');
 assert.equal(selectEquipment(components,{componentType:'generator',variant:'diesel-container'},resolve).fallback,'variant');
 assert.equal(selectEquipment(components,{componentType:'fish-tank'},resolve).fallback,'type');
});
