import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

function picture(type,options={}) {
  const dom=new JSDOM(renderScadaComponent(type,options));
  return {dom,root:dom.window.document.querySelector('.scada-component')};
}

test('separator phase labels follow the declared variant without changing supplied state',()=>{
  const state=Object.freeze({level:55,load:60});
  const base=picture('separator',{id:'phase-base',state});
  const flash=picture('separator',{id:'phase-flash',variant:'flash-water',state});
  try {
    assert.equal(base.root.querySelector('.scada-separator-vessel').dataset.separatorPhases,'gas-oil-water');
    assert.deepEqual([...base.root.querySelectorAll('.scada-separator-label')].map(node=>node.textContent),['GAS','OIL','WATER','IN']);
    assert.ok(base.root.querySelector('.scada-separator-oil-layer'));
    assert.equal(flash.root.querySelector('.scada-separator-vessel').dataset.separatorPhases,'steam-water');
    assert.deepEqual([...flash.root.querySelectorAll('.scada-separator-label')].map(node=>node.textContent),['STEAM','WATER','DRAIN','IN']);
    assert.equal(flash.root.querySelector('[class*="separator-oil"]'),null,'flash-water does not claim an oil phase');
    for(const root of [base.root,flash.root])assert.equal(root.querySelector('[data-scada-reading="level"]').textContent,'55%');
    assert.deepEqual(state,{level:55,load:60});
  } finally {base.dom.window.close();flash.dom.window.close();}
});

test('separator liquid geometry follows clamped inventory, with water below oil and instance-local clipping',()=>{
  for(const variant of [undefined,'flash-water']) {
    let lastWaterHeight=-1;
    for(const level of [-20,25,75,120]) {
      const {dom,root}=picture('separator',{id:`inventory-${variant??'base'}-${level<0?'neg':level}`,variant,state:{level}});
      try {
        const water=root.querySelector('.scada-separator-water-layer'),oil=root.querySelector('.scada-separator-oil-layer');
        const h=Number(water.getAttribute('height'));
        assert.ok(h>=lastWaterHeight,'increasing inventory increases visible water hold-up');lastWaterHeight=h;
        assert.ok(h>=0&&h<=49,'water stays within the cutaway height');
        if(oil)assert.ok(Number(water.getAttribute('y'))>=Number(oil.getAttribute('y')),'the water phase settles below the oil phase');
        assert.equal(root.querySelector('.scada-separator-vessel').dataset.liquidEmpty,String(level<=0));
        if(level<=0)assert.equal(h,0,'an empty vessel has no liquid inventory');
        const clipped=water.parentElement;
        const clipId=clipped.getAttribute('clip-path').match(/^url\(#(.+)\)$/)[1];
        assert.ok(root.querySelector(`clipPath[id="${clipId}"]`),'inventory is clipped within this component instance');
      } finally {dom.window.close();}
    }
  }
});

test('solar output and pump speed preserve zero / stopped controls without mutating geometry or inputs',()=>{
  for(const [type,key,detail] of [['solar-panel','load','.scada-solar-current'],['submersible-pump','speed','.scada-rotor']]) {
    for(const amount of [0,10,90]) {
      const state=Object.freeze({[key]:amount,running:false});
      const {dom,root}=picture(type,{state});
      try {
        assert.equal(root.dataset.running,'false');
        assert.equal(root.querySelector(`[data-scada-reading="${key}"]`).textContent,`${amount}%`);
        assert.ok(root.querySelector(detail),'physical flow/rotation detail remains available when paused');
        if(type==='solar-panel')assert.equal(root.querySelector('.scada-solar-array').dataset.outputZero,String(amount===0));
        else assert.equal(root.dataset.speedZero,String(amount===0));
        assert.deepEqual(state,{[key]:amount,running:false});
      } finally {dom.window.close();}
    }
  }
});

test('wellhead pressure pointer follows its declared range and UPS inventory is retained while off',()=>{
 const angles=[];
 for(const value of [0,50000,100000]){
  const {dom,root}=picture('wellhead',{state:{value}});
  try{angles.push(Number(root.querySelector('.scada-wellhead-needle').getAttribute('transform').match(/rotate\(([-\d.]+)/)[1]));assert.equal(root.querySelector('[data-scada-reading="value"]').textContent,`${value} kPa`);}
  finally{dom.window.close();}
 }
 assert.deepEqual(angles,[-125,0,125]);
 for(const level of [0,50,100]){
  const {dom,root}=picture('ups',{state:{level,active:false}});
  try{assert.equal(Number(root.querySelector('.scada-ups-charge').getAttribute('width')),32*level/100);assert.equal(root.querySelector('[data-scada-reading="level"]').textContent,`${level}%`);assert.equal(root.dataset.active,'false');}
  finally{dom.window.close();}
 }
});

test('empty biofilter has no wet bubbles while external pipes remain separate, and signed flow is explicit',()=>{
 for(const level of [0,1,50,100]){
  const {dom,root}=picture('biofilter',{id:`bio-${level}`,state:{level}});
  try{
   assert.equal(Number(root.querySelector('.scada-biofilter-liquid').getAttribute('height')),level*.88);
   assert.equal(root.querySelector('.scada-biofilter-media').dataset.dry,String(level===0));
   assert.equal(root.querySelectorAll('.scada-agri-bubble').length,level===0?0:3);
   assert.ok(root.querySelector('.scada-agri-flow'),'external liquid/air paths are not removed when inventory is empty');
   if(level){const bubble=root.querySelector('.scada-agri-bubble'),clip=bubble.parentElement.parentElement.getAttribute('clip-path');assert.equal(clip,`url(#scada-bio-${level}-bio-wet)`);}
  }finally{dom.window.close();}
 }
 for(const [value,direction] of [[-12,'reverse'],[0,'stopped'],[12,'forward']]){
  const {dom,root}=picture('flow-meter',{state:{value}});
  try{assert.equal(root.querySelector('.scada-flow-meter').dataset.meterFlow,direction);assert.equal(root.dataset.flow,String(value!==0));assert.equal(root.querySelector('.scada-readout').textContent,String(value));}
  finally{dom.window.close();}
 }
});
