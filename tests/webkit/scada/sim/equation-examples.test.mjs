import test from 'node:test';
import assert from 'node:assert/strict';
import {createPumpBench} from '../../../../software/cadagent/webkit/scada/sim/examples/equation-models/pump-bench.mjs';
import {createHeaterBench} from '../../../../software/cadagent/webkit/scada/sim/examples/equation-models/heater-bench.mjs';
import {pumpDefaults,pumpEquationProviders,volumePerStockUnitM3} from '../../../../software/cadagent/webkit/scada/sim/src/equation-examples/index.mjs';
import {PlaceholderSystemModel,CircuitSystemModel} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const near=(actual,expected,tolerance=1e-8)=>assert.ok(Math.abs(actual-expected)<=tolerance*Math.max(1,Math.abs(expected)),`${actual} != ${expected}`);
const state=model=>model.exportSnapshot().equationState.components.pump.state;
const command=(model,action,value,equipment='pump')=>model.dispatch({action,arguments:{equipment,value}});

for(const version of [1,2]) {
  test(`v${version}: swapping real pump laws changes core flow, power demand and pressure at the same commanded speed`,()=>{
    const values=[];
    for(const curve of ['quadratic','linear']) {
      const {model}=createPumpBench({version,curve,parameters:{initialSpeedRatio:.5,shaftTimeConstantS:0}});
      model.step(.1);
      const snapshot=model.getSnapshot(),s=state(model);
      near(s.lastAcceptedFlowM3s,curve==='quadratic'?.008164965809277261:.007320508075688773);
      near(snapshot.readings.pump.resourceOut,s.lastAcceptedFlowM3s/.05*100);
      near(s.lastDevelopedHeadM,curve==='quadratic'?6:5.607695154586736);
      near(s.acceptedVolumeM3,s.lastAcceptedFlowM3s*6);
      assert.ok(s.lastAcceptedElectricalPowerW>=s.lastRequiredElectricalPowerW-1e-8);
      values.push(snapshot.readings.pump);model.destroy();
    }
    assert.notEqual(values[0].resourceOut,values[1].resourceOut);
    assert.notEqual(values[0].powerIn,values[1].powerIn);
    assert.notEqual(values[0].pressure,values[1].pressure);
  });

  test(`v${version}: finite motor budget and a below-idle supply constrain physical flow even with rating clipping`,()=>{
    const {model}=createPumpBench({version,powerRating:5,parameters:{initialSpeedRatio:1,shaftTimeConstantS:0}});
    model.step(.1);const s=state(model);
    assert.ok(s.lastAcceptedFlowM3s>0&&s.lastAcceptedFlowM3s<.02);
    assert.ok(s.lastRequiredElectricalPowerW<=s.lastAcceptedElectricalPowerW+1e-7);
    assert.ok(s.lastAcceptedElectricalPowerW<=500+1e-8);
    model.destroy();
    const weak=createPumpBench({version,powerRating:.5,parameters:{initialSpeedRatio:1,shaftTimeConstantS:0}}).model;
    weak.step(.1);near(state(weak).lastAcceptedFlowM3s,0);near(state(weak).lastEffectiveSpeedRatio,0);weak.destroy();
  });

  test(`v${version}: provider state replays exactly, binding replacement keeps core inventory, and disable cannot leak flow`,()=>{
    const {model}=createPumpBench({version});command(model,'setLoad',100);model.step(.1);
    const saved=model.exportSnapshot(),beforeState=state(model);
    near(beforeState.speedRatio,1-(1-.6)*Math.exp(-6/30));
    model.step(.3);const expected=model.exportSnapshot();model.importSnapshot(saved);model.step(.3);
    assert.deepEqual(model.exportSnapshot(),expected);
    const coreBefore=model.exportSnapshot().state;
    model.setEquationBindings({version:1,components:{pump:{id:'engineering.pump.linear',version:'1.0.0',parameters:{initialSpeedRatio:.6}}}});
    assert.deepEqual(model.exportSnapshot().state,coreBefore);
    assert.equal(state(model).elapsedS,0);
    command(model,'setEnabled',false);model.step(.1);near(model.getSnapshot().readings.pump.resourceOut,0);
    near(state(model).lastAcceptedFlowM3s,0);model.destroy();
  });

  test(`v${version}: engineering pump requires an explicit electrical supply connection`,()=>{
    const fixture=createPumpBench({version,parameters:{initialSpeedRatio:1,shaftTimeConstantS:0}});fixture.model.destroy();
    fixture.system.connections=fixture.system.connections.filter(edge=>edge.id!=='electricity');
    const Engine=version===1?PlaceholderSystemModel:CircuitSystemModel;
    const model=new Engine(fixture.system,fixture.definition,{equationProviders:pumpEquationProviders});
    model.step(.1);near(state(model).lastAcceptedFlowM3s,0);near(state(model).lastAcceptedElectricalPowerW,0);
    near(model.getSnapshot().readings.pump.resourceOut,0);model.destroy();
  });

  test(`v${version}: stock accounting has explicit units and clipped capacity is not reported as curve potential`,()=>{
    const {model}=createPumpBench({version,flowRating:5,parameters:{initialSpeedRatio:1,shaftTimeConstantS:0}});
    model.step(.1);const s=state(model);near(s.lastAcceptedFlowM3s,.0025);
    near(s.lastPotentialFlowM3s,.02);assert.ok(s.lastAcceptedFlowM3s<s.lastPotentialFlowM3s);
    near(s.acceptedVolumeM3,5*.1*(version===1?.1:1)*s.volumePerStockUnitM3);
    assert.ok(s.lastRequiredElectricalPowerW<=s.lastAcceptedElectricalPowerW+1e-8);model.destroy();
  });

  test(`v${version}: same-step equipment failure preserves the accepted pre-failure interval in provider state`,()=>{
    const fixture=createPumpBench({version,parameters:{initialSpeedRatio:1,shaftTimeConstantS:0}});
    fixture.model.destroy();
    fixture.definition.components.pump.initial.damage=99.99;
    fixture.definition.components.pump.parameters.warningAt=0;
    fixture.definition.components.pump.parameters.damageRate=10;
    const Engine=version===1?PlaceholderSystemModel:CircuitSystemModel;
    const model=new Engine(fixture.system,fixture.definition,{equationProviders:pumpEquationProviders});
    model.step(.1);
    const s=state(model),core=model.exportSnapshot().state.components.pump;
    assert.ok(core.damage>=100);near(model.getSnapshot().readings.pump.resourceOut,0);
    assert.ok(s.lastAcceptedFlowM3s>0);assert.ok(s.lastDevelopedHeadM>0);
    // V1 continuously derates numeric damage before the fault latches; v2 does
    // not. Both must preserve the pre-failure accepted curve rather than use
    // the newly failed zero availability when recording this interval.
    near(s.lastDevelopedHeadM,version===1?5.30107:16);
    assert.ok(s.lastRequiredElectricalPowerW<=s.lastAcceptedElectricalPowerW+1e-8);
    const volume=s.acceptedVolumeM3;model.step(.1);near(state(model).lastAcceptedFlowM3s,0);near(state(model).acceptedVolumeM3,volume);
    model.destroy();
  });

  test(`v${version}: corrupted saved pump-state correlations reject atomically and preserve a usable session`,()=>{
    for(const curve of ['quadratic','linear']) {
      const {model}=createPumpBench({version,curve,parameters:{initialSpeedRatio:.5,maxSpeedRatio:.75}});
      model.step(.1);const saved=model.exportSnapshot();
      const corruptions=[
        s=>{s.speedRatio=.8;},
        s=>{s.lastStepSpeedRatio=.8;},
        s=>{s.lastEffectiveSpeedRatio=.8;},
        s=>{s.lastEffectiveSpeedRatio=.6;s.lastStepSpeedRatio=.5;},
        s=>{s.volumePerStockUnitM3*=2;},
      ];
      for(const corrupt of corruptions) {
        const invalid=structuredClone(saved);corrupt(invalid.equationState.components.pump.state);
        assert.throws(()=>model.importSnapshot(invalid),/Saved/);
        assert.deepEqual(model.exportSnapshot(),saved);
        model.step(.01);assert.ok(state(model).lastAcceptedFlowM3s>0);
        model.importSnapshot(saved);
      }
      // A matching parameter record in both model and provider state still has
      // to obey cross-field constraints; restore intentionally skips initialize.
      const invalid=structuredClone(saved);
      invalid.model.equations.components.pump.parameters.initialSpeedRatio=.8;
      invalid.equationState.components.pump.parameters.initialSpeedRatio=.8;
      assert.throws(()=>model.importSnapshot(invalid),/Initial speed/);
      assert.deepEqual(model.exportSnapshot(),saved);
      model.step(.01);assert.ok(state(model).lastAcceptedFlowM3s>0);
      model.reset();assert.ok(model.getSnapshot().readings.pump.resourceOut>0);
      model.destroy();
    }
  });
}

test('physical scales and correlated parameter failures are explicit and transactional',()=>{
  near(volumePerStockUnitM3(1,.05),.3);near(volumePerStockUnitM3(2,.05),.03);
  assert.throws(()=>volumePerStockUnitM3(3,.05),RangeError);
  const {model}=createPumpBench();const saved=model.exportSnapshot();
  for(const parameters of [{pumpEfficiency:0},{densityKgM3:0},{initialSpeedRatio:2,maxSpeedRatio:1},{unregisteredCoefficient:1}]) {
    assert.throws(()=>model.setEquationBindings({version:1,components:{pump:{id:'engineering.pump.quadratic',version:'1.0.0',parameters}}}));
    assert.deepEqual(model.exportSnapshot(),saved);
  }
  assert.ok(Object.isFrozen(pumpDefaults['engineering.pump.quadratic']));model.destroy();
});

test('v2 resistor changes actual electrical demand and retained heat with exact SI energy accounting',()=>{
  const {model}=createHeaterBench({parameters:{voltageV:240,resistanceOhm:24,conversionEfficiency:.9}});
  model.step(.1);const saved=model.exportSnapshot(),s=saved.equationState.components.heater.state;
  near(s.acceptedElectricalEnergyJ,2400*6);near(s.acceptedHeatJ,2160*6);
  near(saved.state.thermalStores.heater,s.acceptedHeatJ/6000);
  near(model.getSnapshot().ledger.energyLoss,(2400-2160)*6/6000);
  model.step(.2);const replay=model.exportSnapshot();model.importSnapshot(saved);model.step(.2);assert.deepEqual(model.exportSnapshot(),replay);
  command(model,'setEnabled',false,'heater');const before=model.exportSnapshot().state.thermalStores.heater;model.step(.1);
  near(model.exportSnapshot().state.thermalStores.heater,before);model.destroy();
});

test('v2 resistive heat is bounded by actual finite electricity supply',()=>{
  const {model}=createHeaterBench({powerRating:1,parameters:{voltageV:240,resistanceOhm:24,conversionEfficiency:.9}});
  model.step(.1);const s=model.exportSnapshot().equationState.components.heater.state;
  near(s.acceptedElectricalEnergyJ,100*6);near(s.acceptedHeatJ,90*6);model.destroy();
});
