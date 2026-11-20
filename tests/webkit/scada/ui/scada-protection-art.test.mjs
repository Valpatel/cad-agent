import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderElectricalArt} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/power/electrical.mjs';
import {renderNuclearArt} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/power/nuclear.mjs';
import {renderScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

function picture(markup) {
  const dom = new JSDOM(`<svg>${markup}</svg>`);
  return {dom, root:dom.window.document.querySelector('svg')};
}

test('window CT separates the primary conductor, toroidal core and paired secondary observation path',()=>{
  const state={value:60,connected:true,damage:'none'};
  const one=picture(renderElectricalArt('current-transformer',{id:'ct-one',state}));
  const two=picture(renderElectricalArt('current-transformer',{id:'ct-two',state:{...state,connected:false}}));
  try {
    for (const root of [one.root,two.root]) {
      assert.ok(root.querySelector('.scada-ct-core'));
      assert.equal(root.querySelector('.scada-ct-core').getAttribute('fill-rule'),'evenodd');
      assert.equal(root.querySelectorAll('.scada-ct-primary').length,2);
      assert.ok(root.querySelector('.scada-ct-secondary-winding'));
      assert.ok(root.querySelector('.scada-ct-secondary'));
    }
    assert.equal(one.root.querySelector('.scada-power-sensing').dataset.connected,'true');
    assert.equal(two.root.querySelector('.scada-power-sensing').dataset.connected,'false');
    assert.equal(two.root.querySelector('.scada-power-magnetic').dataset.conducting,'false');
    assert.deepEqual(state,{value:60,connected:true,damage:'none'});
  } finally { one.dom.window.close();two.dom.window.close(); }
});

test('protection relay has explicit function and trip cues, while unavailable measurements have no fabricated reading',()=>{
  const clear=picture(renderElectricalArt('protection-relay',{state:{value:64,tripped:false}}));
  const trip=picture(renderElectricalArt('protection-relay',{state:{value:64,tripped:true}}));
  try {
    assert.equal(clear.root.querySelector('.scada-relay-function').textContent,'I>');
    assert.ok(clear.root.querySelector('.scada-relay-shield'));
    assert.equal(clear.root.querySelector('.scada-relay-trip-contact').dataset.tripped,'false');
    assert.equal(trip.root.querySelector('.scada-relay-trip-contact').dataset.tripped,'true');
    assert.notEqual(clear.root.querySelector('.scada-relay-trip-contact').innerHTML,trip.root.querySelector('.scada-relay-trip-contact').innerHTML);
    assert.equal(clear.root.querySelector('.scada-relay-reading').textContent,'64');
  } finally { clear.dom.window.close();trip.dom.window.close(); }
  for (const override of [{connected:false},{active:false},{fault:true},{status:'offline'},{damage:'comms-loss'},{damage:'power-loss'}]) {
    const {dom,root}=picture(renderElectricalArt('protection-relay',{state:{value:64,...override}}));
    try { assert.equal(root.querySelector('.scada-relay-reading').textContent,'—');assert.equal(root.querySelector('.scada-relay-display').dataset.connected,'false'); }
    finally { dom.window.close(); }
  }
});

test('pressurizer inventory is clipped and instance-scoped, with independent retained heat and heater damage',()=>{
  const empty=picture(renderNuclearArt('pressurizer',{id:'press-empty',state:{level:-20,heat:55,damage:'heater-fault'}}));
  const full=picture(renderNuclearArt('pressurizer',{id:'press-full',state:{level:130,pressure:85,heat:55}}));
  try {
    assert.equal(empty.root.querySelector('.scada-nuclear-water').getAttribute('height'),'0');
    assert.equal(full.root.querySelector('.scada-nuclear-water').getAttribute('height'),'84');
    assert.equal(empty.root.querySelector('clipPath').id,'press-empty-pressurizer-water');
    assert.equal(full.root.querySelector('clipPath').id,'press-full-pressurizer-water');
    assert.ok(full.root.querySelector('[clip-path="url(#press-full-pressurizer-water)"] .scada-nuclear-water'));
    for(const name of ['shell','spray-line','relief-line','nozzle','surge'])assert.ok(full.root.querySelector(`.scada-pressurizer-${name}`));
    assert.equal(empty.root.querySelector('.scada-pressurizer-heaters').dataset.heaterAvailable,'false');
    assert.equal(empty.root.querySelector('.scada-pressurizer-heaters .scada-nuclear-heat'),null);
    assert.equal(empty.root.querySelector('.scada-nuclear-art').dataset.nuclearHeat,'true','a heater fault does not erase supplied retained heat');
    assert.ok(full.root.querySelector('.scada-pressurizer-heaters .scada-nuclear-heat'));
    assert.notEqual(full.root.querySelector('.scada-pressurizer-pressure-needle').getAttribute('transform'),empty.root.querySelector('.scada-pressurizer-pressure-needle').getAttribute('transform'));
  } finally { empty.dom.window.close();full.dom.window.close(); }
});


test('relay inner display, external gauge and accessible reading agree for unavailable observations',()=>{
  for(const override of [{connected:false},{active:false},{fault:true},{status:'offline'},{damage:'comms-loss'},{damage:'power-loss'}]) {
    const dom=new JSDOM(renderScadaComponent('protection-relay',{state:{value:64,...override}}));
    try {
      const root=dom.window.document.querySelector('.scada-component');
      assert.equal(root.querySelector('.scada-relay-reading').textContent,'—');
      assert.equal(root.querySelector('[data-scada-reading="value"]').textContent,'—');
      assert.equal(root.querySelector('[data-scada-gauge="value"]').dataset.readingValid,'false');
      assert.equal(root.querySelector('[data-scada-gauge="value"] b').style.width,'0%');
      assert.match(root.getAttribute('aria-label'),/value unavailable/);
    } finally {dom.window.close();}
  }
  const drift=new JSDOM(renderScadaComponent('protection-relay',{state:{value:64,damage:'drift',status:'warning'}}));
  try {
    const root=drift.window.document.querySelector('.scada-component');
    assert.equal(root.querySelector('.scada-relay-reading').textContent,'64');
    assert.equal(root.querySelector('[data-scada-reading="value"]').textContent,'64 idx');
    assert.equal(root.querySelector('[data-scada-gauge="value"] b').style.width,'64%');
    assert.match(root.getAttribute('aria-label'),/Warning.*illustrative value 64index.*damage: drift/);
  } finally {drift.window.close();}
});


test('a requested relay trip does not draw an asserted output when the device is failed or without power',()=>{
  for(const override of [{active:false},{fault:true},{status:'offline'},{damage:'power-loss'}]) {
    const {dom,root}=picture(renderElectricalArt('protection-relay',{state:{tripped:true,...override}}));
    try {
      assert.equal(root.querySelector('.scada-relay-trip-contact').dataset.tripped,'true');
      assert.equal(root.querySelector('.scada-relay-trip-contact').dataset.outputAsserted,'false');
      assert.equal(root.querySelector('.scada-relay-output').dataset.outputAsserted,'false');
      assert.ok(root.textContent.includes('TRIP OUT'));
    } finally {dom.window.close();}
  }
});
