import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const controls=['plc-rack','plc-cpu','remote-io','hmi','scada-server','network-switch','radio'];
test('lost control power is inactive while a supplied controller load is retained as a command',()=>{
 for(const type of controls){
  const dom=new JSDOM(renderScadaComponent(type,{state:{damage:'power-loss'}})+renderScadaComponent(type,{state:{damage:'none'}}));
  try{
   const [lost,repaired]=dom.window.document.querySelectorAll('.scada-component');
   assert.equal(lost.dataset.active,'false',type);assert.equal(lost.dataset.flow,'false');
   assert.match(lost.getAttribute('aria-label'),/Inactive/);assert.ok(lost.querySelector('.scada-damage-power-loss'));
   assert.equal(repaired.dataset.active,'true');
   const load=lost.querySelector('[data-scada-reading="load"]');if(load)assert.equal(load.textContent,'60%','load remains a supplied controller command, not an invented measurement');
  }finally{dom.window.close();}
 }
});

test('failed meter and instrument-transformer observations are unavailable without erasing damage',()=>{
 for(const [type,damage,key] of [['electrical-meter','broken','load'],['current-transformer','insulation-fault','value'],['voltage-transformer','insulation-fault','value']]){
  const dom=new JSDOM(renderScadaComponent(type,{state:{damage}}));
  try{
   const root=dom.window.document.querySelector('.scada-component'),gauge=root.querySelector(`[data-scada-gauge="${key}"]`);
   assert.equal(root.dataset.readingValid,'false');assert.equal(gauge.dataset.readingValid,'false');
   assert.equal(gauge.querySelector('strong').textContent,'—');assert.equal(gauge.querySelector('b').style.width,'0%');
   assert.match(root.getAttribute('aria-label'),new RegExp(`${key} unavailable`));assert.equal(root.dataset.damage,damage);
  }finally{dom.window.close();}
 }
 for(const type of ['electrical-meter','pressure-transmitter','gas-analyzer','protection-relay']){
  const dom=new JSDOM(renderScadaComponent(type,{state:{damage:'drift'}}));
  try{assert.equal(dom.window.document.querySelector('.scada-component').dataset.readingValid,'true','drift retains supplied readings rather than inventing a disconnection');}
  finally{dom.window.close();}
 }
});
