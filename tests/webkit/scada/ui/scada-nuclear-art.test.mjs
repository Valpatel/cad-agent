import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderNuclearArt} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/power/nuclear.mjs';

const picture=(type,state,id='nuclear-one')=>{
 const dom=new JSDOM(`<svg>${renderNuclearArt(type,{id,state})}</svg>`);
 return {dom,art:dom.window.document.querySelector('.scada-nuclear-art')};
};

test('nuclear source activity, supplied circulation, retained heat and leaks are independent layers',()=>{
 const state={active:false,fault:true,running:true,status:'normal',damage:'leaking',heat:70,flow:40,level:55,load:0,rodPosition:100};
 const {dom,art}=picture('pwr-reactor-vessel',state);
 try{
  assert.equal(art.dataset.nuclearSource,'false');
  assert.equal(art.dataset.nuclearPrimary,'true');
  assert.equal(art.dataset.nuclearHeat,'true');
  assert.equal(art.dataset.nuclearLeaking,'true');
  assert.ok(art.querySelector('.scada-nuclear-drip'));
  assert.ok(Number.parseFloat(art.style.getPropertyValue('--scada-nuclear-heat-opacity'))>0);
  assert.deepEqual(state,{active:false,fault:true,running:true,status:'normal',damage:'leaking',heat:70,flow:40,level:55,load:0,rodPosition:100});
 }finally{dom.window.close();}
 const cold=picture('pwr-reactor-vessel',{...state,damage:'none',heat:0,flow:0});
 try{
  assert.equal(cold.art.dataset.nuclearPrimary,'false');
  assert.equal(cold.art.dataset.nuclearHeat,'false');
  assert.equal(cold.art.querySelector('.scada-nuclear-leak-mark'),null);
 }finally{cold.dom.window.close();}
});

test('steam-generator primary and secondary traces respond to separate supplied circuits',()=>{
 const one=picture('nuclear-steam-generator',{primaryFlow:0,secondaryFlow:75,heat:45,level:55});
 const two=picture('nuclear-steam-generator',{primaryFlow:80,secondaryFlow:0,heat:45,level:55});
 try{
  assert.equal(one.art.dataset.nuclearPrimary,'false');
  assert.equal(one.art.dataset.nuclearSecondary,'true');
  assert.equal(two.art.dataset.nuclearPrimary,'true');
  assert.equal(two.art.dataset.nuclearSecondary,'false');
  assert.ok(one.art.querySelectorAll('.scada-nuclear-primary').length>1);
  assert.ok(one.art.querySelectorAll('.scada-nuclear-secondary').length>1);
  assert.equal(one.art.querySelector('.scada-nuclear-primary.scada-nuclear-secondary'),null,'a fluid trace never belongs to both circuits');
 }finally{one.dom.window.close();two.dom.window.close();}
});

test('failed or unavailable nuclear monitors display no fabricated numeric measurement',()=>{
 for(const type of ['neutron-monitor','radiation-monitor']){
  for(const override of [{active:false},{fault:true},{status:'offline'},{connected:false},{damage:'broken'},{damage:'disconnected'}]){
   const {dom,art}=picture(type,{value:72,active:true,connected:true,...override});
   try{assert.equal(art.dataset.nuclearValid,'false');assert.equal(art.querySelector('.scada-nuclear-readout').textContent,'—');}
   finally{dom.window.close();}
  }
  const drift=picture(type,{value:72,active:true,connected:true,damage:'drift',status:'warning'});
  try{assert.equal(drift.art.dataset.nuclearValid,'true');assert.equal(drift.art.querySelector('.scada-nuclear-readout').textContent,'72');assert.ok(drift.art.querySelector('.scada-nuclear-drift'));}
  finally{drift.dom.window.close();}
 }
});

test('rod position changes geometry while a held or jammed drive has no ongoing actuator command',()=>{
 const withdrawn=picture('control-rod-drive',{rodPosition:0,speed:60,moving:false});
 const inserted=picture('control-rod-drive',{rodPosition:100,speed:60,moving:true});
 const jammed=picture('control-rod-drive',{rodPosition:30,speed:60,moving:true,damage:'jammed'});
 try{
  assert.notEqual(withdrawn.art.querySelector('.scada-nuclear-rods').getAttribute('style'),inserted.art.querySelector('.scada-nuclear-rods').getAttribute('style'));
  assert.equal(withdrawn.art.dataset.nuclearMoving,'false');
  assert.equal(inserted.art.dataset.nuclearMoving,'true');
  assert.equal(jammed.art.dataset.nuclearMoving,'false');
  assert.ok(jammed.art.querySelector('.scada-nuclear-drive-jam'));
 }finally{withdrawn.dom.window.close();inserted.dom.window.close();jammed.dom.window.close();}
});

test('PHWR moderator inventory is bounded, instance-scoped and isolated from heat-transport animation',()=>{
 const empty=picture('phwr-calandria',{level:-30,heat:Infinity,flow:NaN},'phwr-one');
 const full=picture('phwr-calandria',{level:140,heat:50,flow:60},'phwr-two');
 try{
  assert.equal(empty.art.querySelector('.scada-nuclear-water').getAttribute('height'),'0');
  assert.equal(full.art.querySelector('.scada-nuclear-water').getAttribute('height'),'64');
  assert.equal(empty.art.querySelector('clipPath').id,'phwr-one-moderator-fill');
  assert.equal(full.art.querySelector('clipPath').id,'phwr-two-moderator-fill');
  assert.equal(full.art.querySelector('.scada-nuclear-water.scada-nuclear-primary'),null);
  assert.ok(!/NaN|Infinity/.test(empty.art.outerHTML));
 }finally{empty.dom.window.close();full.dom.window.close();}
 assert.equal(renderNuclearArt('__proto__'),'');
 assert.equal(renderNuclearArt('constructor'),'');
 const injected=picture('pwr-reactor-vessel',{damage:'"/><script>evil()</script>'},'bad" onload="evil()');
 try{assert.equal(injected.art.dataset.nuclearDamage,'none');assert.equal(injected.dom.window.document.querySelector('script,[onload]'),null);}
 finally{injected.dom.window.close();}
});
