import {EQUATION_UNITS} from '../equations/index.mjs';
import {firstOrderResponse, pumpPowerEnvelope, limitPumpPower, pumpAtFlow, resistiveHeaterPower} from './physics.mjs';

const objectSchema = properties => ({type:'object', properties, required:Object.keys(properties), additionalProperties:false});
const number = (title, minimum = 0, maximum = 1e9) => ({type:'number', title, minimum, maximum});
const positive = (title, maximum = 1e9) => ({type:'number', title, exclusiveMinimum:0, maximum});
const fraction = title => ({type:'number', title, exclusiveMinimum:0, maximum:1});
const common = Object.freeze({shutoffHeadM:40, staticHeadM:4, systemResistanceS2M5:30000,
  densityKgM3:1000, gravityMS2:9.80665, pumpEfficiency:.8, motorEfficiency:.9, driveEfficiency:1,
  idlePowerW:100, flowAt100M3s:.05, powerAt100W:10000, pressureAt100Pa:1e6,
  shaftTimeConstantS:30, initialSpeedRatio:.6, maxSpeedRatio:1});

/** Every numeric default is an editable assumption, not measured plant data. */
export const pumpDefaults = Object.freeze({
  'engineering.pump.quadratic':Object.freeze({...common, quadraticResistanceS2M5:60000}),
  'engineering.pump.linear':Object.freeze({...common, linearResistanceSM2:1200}),
});
export const parameterUnits = Object.freeze({shutoffHeadM:'m', staticHeadM:'m',
  systemResistanceS2M5:'s²/m⁵', quadraticResistanceS2M5:'s²/m⁵', linearResistanceSM2:'s/m²',
  densityKgM3:'kg/m³', gravityMS2:'m/s²', pumpEfficiency:'fraction', motorEfficiency:'fraction',
  driveEfficiency:'fraction', idlePowerW:'W', flowAt100M3s:'m³/s at rate index 100',
  powerAt100W:'W at power index 100', pressureAt100Pa:'Pa at pressure index 100',
  shaftTimeConstantS:'s', initialSpeedRatio:'nominal speed ratio', maxSpeedRatio:'nominal speed ratio',
  voltageV:'V RMS', resistanceOhm:'Ω', conversionEfficiency:'fraction'});
const commonSchema = {
  shutoffHeadM:positive('Nominal shutoff head (assumed)'), staticHeadM:number('Static system head (assumed)'),
  systemResistanceS2M5:number('System quadratic resistance (assumed)'), densityKgM3:positive('Fluid density (assumed)'),
  gravityMS2:positive('Gravity (assumed standard gravity)'), pumpEfficiency:fraction('Pump efficiency (assumed constant)'),
  motorEfficiency:fraction('Motor efficiency (assumed constant)'), driveEfficiency:fraction('Drive efficiency (assumed constant)'),
  idlePowerW:number('Running idle electrical power (assumed)'), flowAt100M3s:positive('Flow scale for index 100'),
  powerAt100W:positive('Electrical scale for index 100'), pressureAt100Pa:positive('Pressure scale for index 100'),
  shaftTimeConstantS:number('Shaft response time constant (assumed)'), initialSpeedRatio:number('Initial shaft speed ratio',0,3),
  maxSpeedRatio:positive('Maximum shaft speed ratio',3),
};
const stateSchema = objectSchema({speedRatio:number('Committed commanded shaft speed',0,3),
  lastStepSpeedRatio:number('Commanded shaft speed used in last interval',0,3),
  lastEffectiveSpeedRatio:number('Power-limited effective shaft speed in last interval',0,3),
  lastPotentialFlowM3s:number('Local full-power curve flow before kernel allocation'),
  lastAcceptedFlowM3s:number('Accepted kernel flow converted to SI'),
  lastAcceptedElectricalPowerW:number('Accepted electrical allocation converted to SI'),
  lastDevelopedHeadM:number('Pump curve head at accepted forward flow'),
  lastRequiredElectricalPowerW:number('Curve power at accepted forward flow'),
  elapsedS:number('Accepted elapsed time',0,1e14), acceptedEnergyJ:number('Accepted electrical energy',0,1e24),
  acceptedVolumeM3:number('Accepted pumped volume',0,1e24), volumePerStockUnitM3:positive('Physical volume represented by a kernel stock unit'),
});

/** Raw v1/v2 rate indices share a flow conversion; their stock increments do not. */
export function volumePerStockUnitM3(engineVersion, flowAt100M3s) {
  if (![1,2].includes(engineVersion) || !(flowAt100M3s > 0) || !Number.isFinite(flowAt100M3s)) throw new RangeError('Expected engine 1 or 2 and positive finite flow scale.');
  return flowAt100M3s * (engineVersion === 1 ? 6 : .6);
}
/** Schema bounds describe each field independently. These correlations also
 * apply to restored state: import does not initialize an already saved model.
 * Historical totals remain independently bounded observations, not a signed
 * proof of the model's entire past trajectory.
 */
function validatePumpContext(ctx) {
  const p=ctx.parameters,s=ctx.providerState;
  if(p.initialSpeedRatio>p.maxSpeedRatio) throw new RangeError('Initial speed exceeds maximum speed.');
  if(s===null) return;
  for(const field of ['speedRatio','lastStepSpeedRatio','lastEffectiveSpeedRatio']) {
    if(s[field]>p.maxSpeedRatio) throw new RangeError(`Saved ${field} exceeds maximum speed.`);
  }
  if(s.lastEffectiveSpeedRatio>s.lastStepSpeedRatio) throw new RangeError('Saved effective speed exceeds the accepted interval shaft speed.');
  if(s.volumePerStockUnitM3!==volumePerStockUnitM3(ctx.engineVersion,p.flowAt100M3s)) {
    throw new RangeError('Saved stock-volume conversion does not match the engine and flow scale.');
  }
}
const coreSpeed = ctx => ctx.core.operating / 100 * ctx.parameters.maxSpeedRatio;
const health = ctx => ctx.gates?.healthFactor ?? 1;
const externalControl = ctx => ctx.gates?.controlFactor ?? 1;
const powerFraction = ctx => ctx.gates?.powerFactor ?? ctx.accepted?.powerFactor ?? ctx.readings?.powerFactor ?? 1;
const inputFor = (ctx, speedRatio) => ({...ctx.parameters, speedRatio, enabled:ctx.core.enabled});
function operatingPoint(curve, ctx, constrainPower = true) {
  const speed = coreSpeed(ctx) * health(ctx) * (constrainPower ? externalControl(ctx) : 1);
  const input = inputFor(ctx, speed), full = pumpPowerEnvelope(curve, input);
  const availablePowerW = ctx.powerBasis === 'unconnected-bench' ? 0 : ctx.availablePower === undefined
    ? full.maximumElectricalPowerW * powerFraction(ctx)
    : ctx.availablePower * ctx.parameters.powerAt100W / 100;
  return constrainPower ? limitPumpPower(curve, input, availablePowerW) : full;
}
function startupPower(ctx, point) {
  // Running idle demand also lets an initially stationary drive obtain a supply.
  return ctx.core.enabled && ctx.core.load > 0 && health(ctx) > 0
    ? Math.max(ctx.parameters.idlePowerW, point.maximumElectricalPowerW) : 0;
}
function createPumpProvider(curve) {
  const id = `engineering.pump.${curve}`;
  return Object.freeze({id, version:'1.0.0', stateVersion:1, engines:[1,2],
    phases:['operating','resource','energy','pressure'], units:EQUATION_UNITS,
    label:`Centrifugal pump — ${curve} characteristic`,
    description:'Assumed local pump/system curve with affinity scaling, conservative motor demand and serialized shaft response; not a network hydraulic solver.',
    defaultParameters:pumpDefaults[id],
    parameterSchema:objectSchema({...commonSchema, ...(curve === 'quadratic'
      ? {quadraticResistanceS2M5:positive('Nominal quadratic pump coefficient (assumed)')}
      : {linearResistanceSM2:positive('Nominal linear pump coefficient (assumed)')})}), stateSchema,
    initialize(ctx) {
      const p = ctx.parameters;
      validatePumpContext(ctx);
      // Exercise physical validation even before the first model step.
      pumpPowerEnvelope(curve, inputFor(ctx, p.initialSpeedRatio));
      return {speedRatio:p.initialSpeedRatio, lastStepSpeedRatio:p.initialSpeedRatio, lastEffectiveSpeedRatio:0,
        lastPotentialFlowM3s:0,lastAcceptedFlowM3s:0,lastAcceptedElectricalPowerW:0,lastDevelopedHeadM:0,
        lastRequiredElectricalPowerW:0,elapsedS:0,acceptedEnergyJ:0,acceptedVolumeM3:0,
        volumePerStockUnitM3:volumePerStockUnitM3(ctx.engineVersion,p.flowAt100M3s)};
    },
    evaluate(phase, ctx) {
      validatePumpContext(ctx);
      const p = ctx.parameters;
      if (phase === 'operating') {
        const target = ctx.core.enabled ? ctx.core.load / 100 * p.maxSpeedRatio : 0;
        return {operating:100 * firstOrderResponse(ctx.providerState.speedRatio,target,p.shaftTimeConstantS,ctx.dtMinutes*60) / p.maxSpeedRatio};
      }
      if (phase === 'resource') return {capacity:operatingPoint(curve,ctx).flowM3s / p.flowAt100M3s * 100};
      if (phase === 'energy') return {demand:startupPower(ctx,operatingPoint(curve,ctx,false)) / p.powerAt100W * 100};
      if (phase === 'pressure') {
        const point = operatingPoint(curve,ctx), flow = (ctx.readings?.resourceOut ?? 0) * p.flowAt100M3s / 100;
        const actual = pumpAtFlow(curve,inputFor(ctx,point.speedRatio),flow);
        return {target:actual.pressurePa / p.pressureAt100Pa * 100};
      }
      return {};
    },
    advance(ctx) {
      validatePumpContext(ctx);
      const p=ctx.parameters, old=ctx.providerState, dtS=ctx.dtMinutes*60;
      // Conditions can fail the component after allocation in the same substep.
      // Bookkeep using the accepted solve's factors, not its newly failed state.
      const accepted=ctx.accepted.gates ? {...ctx,gates:ctx.accepted.gates,
        availablePower:ctx.accepted.availablePower??ctx.availablePower,
        powerBasis:ctx.accepted.powerBasis??ctx.powerBasis,
        core:{...ctx.core,enabled:ctx.accepted.gates.enabled,operating:ctx.accepted.gates.operatingFraction*100}} : ctx;
      const potential=operatingPoint(curve,accepted,false), point=operatingPoint(curve,accepted);
      const flow=ctx.accepted.resourceOut*p.flowAt100M3s/100;
      const power=ctx.accepted.energyIn*p.powerAt100W/100;
      const actual=pumpAtFlow(curve,inputFor(accepted,point.speedRatio),flow);
      const next={...old,speedRatio:coreSpeed(ctx),lastStepSpeedRatio:coreSpeed(accepted),lastEffectiveSpeedRatio:point.speedRatio,
        lastPotentialFlowM3s:potential.flowM3s,lastAcceptedFlowM3s:flow,lastAcceptedElectricalPowerW:power,
        lastDevelopedHeadM:actual.headM,lastRequiredElectricalPowerW:actual.electricalPowerW,
        elapsedS:old.elapsedS+dtS,acceptedEnergyJ:old.acceptedEnergyJ+power*dtS,acceptedVolumeM3:old.acceptedVolumeM3+flow*dtS};
      validatePumpContext({...ctx,providerState:next});
      return next;
    },
  });
}
export const quadraticPumpProvider = createPumpProvider('quadratic');
export const linearPumpProvider = createPumpProvider('linear');
export const pumpEquationProviders = Object.freeze([quadraticPumpProvider,linearPumpProvider]);

/** V2 resistor source changes real electrical demand and accepted heat. The host
 * must configure an energy-input heatSource and an adequately rated thermal store.
 */
export const resistiveHeaterProvider = Object.freeze({id:'engineering.heater.resistive',version:'1.0.0',stateVersion:1,
  engines:[2], phases:['energy','thermal-source'], units:EQUATION_UNITS,
  label:'Constant-resistance electric heater', description:'Assumed RMS-voltage resistor; accepted electricity limits heat and the kernel retains thermal energy.',
  defaultParameters:{voltageV:230,resistanceOhm:23,conversionEfficiency:.95,powerAt100W:10000},
  parameterSchema:objectSchema({voltageV:number('RMS supply voltage (assumed)'),resistanceOhm:positive('Heating resistance (assumed constant)'),
    conversionEfficiency:fraction('Heat conversion efficiency (assumed)'),powerAt100W:positive('Electrical scale for index 100')}),
  stateSchema:objectSchema({elapsedS:number('Accepted elapsed time',0,1e14),acceptedElectricalEnergyJ:number('Accepted electrical energy',0,1e24),acceptedHeatJ:number('Accepted thermal energy',0,1e24)}),
  initialize:()=>({elapsedS:0,acceptedElectricalEnergyJ:0,acceptedHeatJ:0}),
  evaluate(phase,ctx) {
    const p=ctx.parameters;
    const duty=ctx.core.enabled ? ctx.core.operating/100*health(ctx) : 0;
    const power=resistiveHeaterPower({...p,duty,efficiency:p.conversionEfficiency});
    if (phase==='energy') return {demand:power.electricalPowerW/p.powerAt100W*100};
    if (phase==='thermal-source') {
      if(ctx.configuration.heatSource?.supply?.kind!=='energy-input') throw new TypeError('Resistive heater requires an energy-input heat source.');
      const acceptedW=ctx.accepted.energyIn*p.powerAt100W/100;
      const heatW=Math.min(power.electricalPowerW,acceptedW)*p.conversionEfficiency;
      return {heat:heatW*ctx.dtMinutes*60/(p.powerAt100W*.6)};
    }
    return {};
  },
  advance(ctx) {
    const old=ctx.providerState,quantumJ=ctx.parameters.powerAt100W*.6;
    return {elapsedS:old.elapsedS+ctx.dtMinutes*60,
      acceptedElectricalEnergyJ:old.acceptedElectricalEnergyJ+ctx.accepted.energyIn*ctx.dtMinutes*quantumJ,
      acceptedHeatJ:old.acceptedHeatJ+ctx.accepted.heatSource*quantumJ};
  },
});
