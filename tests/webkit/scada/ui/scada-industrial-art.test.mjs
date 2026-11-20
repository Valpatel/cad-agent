import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderIndustrialArt} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/art/industrial.mjs';

test('industrial rendering keeps SVG dependencies instance-scoped and accepts no injected type or damage markup',()=>{
 const state={active:true,load:70,speed:40,damage:'jammed'};
 const one=renderIndustrialArt('crusher',{id:'crusher-one',state}),two=renderIndustrialArt('crusher',{id:'crusher-two',state});
 assert.ok(one.includes('url(#crusher-one-steel)'));
 assert.ok(two.includes('url(#crusher-two-steel)'));
 assert.ok(!two.includes('crusher-one'));
 assert.deepEqual(state,{active:true,load:70,speed:40,damage:'jammed'},'art does not mutate supplied model state');
 assert.equal(renderIndustrialArt('__proto__'),'');
 assert.equal(renderIndustrialArt('constructor'),'');
 const injected=renderIndustrialArt('crusher',{id:'bad" onload="evil()',state:{damage:'"/><script>evil()</script>'}});
 const dom=new JSDOM(`<svg>${injected}</svg>`);
 try{
  assert.equal(dom.window.document.querySelector('script,[onload]'),null);
  assert.equal(dom.window.document.querySelector('.scada-industrial-art').dataset.industrialDamage,'none');
 }finally{dom.window.close();}
});

test('inventory, throughput and speed are bounded visual inputs with visible numeric endpoints',()=>{
 const get=(type,state)=>{
  const dom=new JSDOM(`<svg>${renderIndustrialArt(type,{id:'equipment',state})}</svg>`);
  return {dom,root:dom.window.document.querySelector('.scada-industrial-art')};
 };
 const low=get('weigh-hopper',{level:-100,load:0,speed:0});
 const high=get('weigh-hopper',{level:200,load:100,speed:100});
 const invalid=get('oven',{load:Infinity,speed:NaN,temperature:Infinity});
 try{
  assert.equal(low.root.querySelector('.scada-industrial-inventory').getAttribute('height'),'0');
  assert.equal(high.root.querySelector('.scada-industrial-inventory').getAttribute('height'),'24');
  assert.equal(low.root.dataset.industrialStopped,'true');
  assert.equal(high.root.dataset.industrialStopped,'false');
  assert.ok(Number.parseFloat(high.root.style.getPropertyValue('--scada-industrial-cycle'))<Number.parseFloat(low.root.style.getPropertyValue('--scada-industrial-cycle')));
  assert.ok(Number.parseFloat(high.root.style.getPropertyValue('--scada-industrial-material'))>Number.parseFloat(low.root.style.getPropertyValue('--scada-industrial-material')));
  assert.ok(!/NaN|Infinity/.test(invalid.root.outerHTML));
 }finally{low.dom.window.close();high.dom.window.close();invalid.dom.window.close();}
});
