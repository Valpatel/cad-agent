import test from 'node:test';
import assert from 'node:assert/strict';
import {solveQuadraticPump, solveLinearPump, pumpAtFlow, pumpPowerEnvelope, limitPumpPower, firstOrderResponse, resistiveHeaterPower, stepLumpedThermal} from '../../../../software/cadagent/webkit/scada/sim/src/equation-examples/physics.mjs';

const base = Object.freeze({speedRatio:1, shutoffHeadM:40, staticHeadM:4, systemResistanceS2M5:30000,
  quadraticResistanceS2M5:60000, linearResistanceSM2:1200, densityKgM3:1000, gravityMS2:9.80665,
  pumpEfficiency:.8, motorEfficiency:.9, driveEfficiency:1, idlePowerW:100});
const near = (actual, expected, tolerance=1e-10) => assert.ok(Math.abs(actual-expected)<=tolerance*Math.max(1,Math.abs(expected)), `${actual} differs from ${expected}`);

test('independent nominal point: linear and quadratic curves intersect the same 20 L/s, 16 m duty',()=>{
  for(const solve of [solveLinearPump,solveQuadraticPump]){
    const p=solve(base);
    near(p.flowM3s,.02);near(p.headM,16);near(p.pressurePa,156906.4);
    near(p.hydraulicPowerW,3138.128);near(p.electricalPowerW,4458.511111111111);
    assert.equal(p.blocked,false);assert.ok(Object.isFrozen(p));
  }
});

test('off-design laws genuinely differ and the linear nominal slope follows affinity scaling',()=>{
  const quadratic=solveQuadraticPump({...base,speedRatio:.5});
  near(quadratic.flowM3s,.008164965809277261);near(quadratic.headM,6);near(quadratic.electricalPowerW,767.2580162795736);
  const linear=solveLinearPump({...base,speedRatio:.5});
  near(linear.flowM3s,.007320508075688773);near(linear.headM,5.607695154586736);near(linear.electricalPowerW,659.1312936805175);
  assert.notEqual(linear.flowM3s,quadratic.flowM3s);
  for(const solve of [solveLinearPump,solveQuadraticPump]){
    const nominal=solve({...base,staticHeadM:0});const half=solve({...base,staticHeadM:0,speedRatio:.5});
    near(half.flowM3s,nominal.flowM3s/2);near(half.headM,nominal.headM/4);
    near(half.hydraulicPowerW,nominal.hydraulicPowerW/8);
  }
});

test('stopped and blocked pump states distinguish shutoff head, external static head and idle draw',()=>{
  for(const solve of [solveLinearPump,solveQuadraticPump]){
    const stopped=solve({...base,speedRatio:0});
    assert.equal(stopped.flowM3s,0);assert.equal(stopped.headM,0);assert.equal(stopped.electricalPowerW,0);assert.equal(stopped.systemHeadM,4);
    const off=solve({...base,enabled:false});assert.equal(off.electricalPowerW,0);assert.equal(off.headM,0);
    const blocked=solve({...base,staticHeadM:60});
    assert.equal(blocked.flowM3s,0);assert.equal(blocked.headM,40);assert.equal(blocked.systemHeadM,60);assert.equal(blocked.electricalPowerW,100);assert.equal(blocked.blocked,true);
  }
});

test('stable linear positive root survives near cancellation and zero system resistance',()=>{
  const p=solveLinearPump({...base,shutoffHeadM:1,staticHeadM:0,linearResistanceSM2:1e8,systemResistanceS2M5:1});
  near(p.flowM3s,1e-8,1e-15);assert.ok(p.flowM3s>0);
  near(solveLinearPump({...base,systemResistanceS2M5:0}).flowM3s,.03);
});

test('allocated-flow pump head is evaluated on the pump curve, separate from the free operating point',()=>{
  const p=pumpAtFlow('quadratic',base,.01);
  near(p.headM,34);near(p.systemHeadM,7);near(p.hydraulicPowerW,3334.261);
  assert.notEqual(p.headM,p.systemHeadM);
  assert.throws(()=>pumpAtFlow('quadratic',base,.1),/nonnegative-head/);
  assert.throws(()=>pumpAtFlow('linear',{...base,speedRatio:0},.01),/stopped pump/);
});

test('power envelope covers throttled operation and a finite power budget selects a safe local speed',()=>{
  for(const curve of ['quadratic','linear']) {
    const envelope=pumpPowerEnvelope(curve,base);
    for(let i=0;i<=100;i++) assert.ok(pumpAtFlow(curve,base,envelope.flowM3s*i/100).electricalPowerW<=envelope.maximumElectricalPowerW+1e-8);
    const limited=limitPumpPower(curve,base,500);
    near(limited.maximumElectricalPowerW,500);
    assert.ok(limited.speedRatio<1);assert.ok(limited.flowM3s>0);
    assert.equal(limitPumpPower(curve,base,99).flowM3s,0);
    assert.equal(limitPumpPower(curve,base,100).speedRatio,0);
    assert.equal(limitPumpPower(curve,base,10000).speedRatio,1);
  }
  const peakQ=Math.sqrt(40/(3*60000));
  const expected=1000*9.80665*peakQ*(40-60000*peakQ**2)/(.8*.9)+100;
  near(pumpPowerEnvelope('quadratic',base).maximumElectricalPowerW,expected);
});

test('physical input and arithmetic errors fail even for disabled equipment',()=>{
  for(const solve of [solveLinearPump,solveQuadraticPump]){
    for(const bad of [{pumpEfficiency:0},{motorEfficiency:1.1},{densityKgM3:0},{gravityMS2:NaN},{staticHeadM:-1},{systemResistanceS2M5:-1},{speedRatio:Infinity}]){
      assert.throws(()=>solve({...base,...bad,enabled:false}),RangeError);
    }
    assert.throws(()=>solve({...base,shutoffHeadM:Number.MAX_VALUE,speedRatio:2}),/scaled shutoff head/);
    assert.throws(()=>solve({...base,densityKgM3:Number.MAX_VALUE}),RangeError);
  }
});

test('exact shaft response is partition independent for a constant target and explicitly handles zero lag',()=>{
  const one=firstOrderResponse(0,1,30,60);
  near(one,.8646647167633873);
  near(firstOrderResponse(firstOrderResponse(0,1,30,20),1,30,40),one);
  assert.equal(firstOrderResponse(.5,.2,0,0),.5);assert.equal(firstOrderResponse(.5,.2,0,1),.2);
  assert.throws(()=>firstOrderResponse(0,1,-1,10),RangeError);
});

test('resistive heater power uses RMS voltage, resistance, duty and explicit conversion efficiency',()=>{
  const p=resistiveHeaterPower({voltageV:240,resistanceOhm:24,duty:.5,efficiency:.9});
  assert.equal(p.electricalPowerW,1200);assert.equal(p.heatPowerW,1080);
  assert.throws(()=>resistiveHeaterPower({voltageV:240,resistanceOhm:0}),RangeError);
});

test('exact lumped thermal step matches an independent half-decay point and signed energy balance',()=>{
  const input={temperatureK:293.15,ambientK:283.15,capacityJK:1000,conductanceWK:10,heatPowerW:200,dtS:100*Math.log(2)};
  const next=stepLumpedThermal(input);
  near(next.temperatureK,298.15);near(next.storedEnergyChangeJ,5000);near(next.inputEnergyJ,13862.943611198907);near(next.heatLossJ,8862.943611198907);
  const one=stepLumpedThermal({...input,dtS:35});
  const two=stepLumpedThermal({...input,temperatureK:one.temperatureK,dtS:input.dtS-35});near(two.temperatureK,next.temperatureK);
  const insulated=stepLumpedThermal({...input,conductanceWK:0,dtS:10});near(insulated.temperatureK,295.15);assert.equal(insulated.heatLossJ,0);
  const warming=stepLumpedThermal({...input,temperatureK:273.15,heatPowerW:0});assert.ok(warming.heatLossJ<0);
  assert.throws(()=>stepLumpedThermal({...input,capacityJK:0}),RangeError);
});
