import {createModelDefinition,CircuitSystemModel} from '../../src/index.mjs';
import {resistiveHeaterProvider} from '../../src/equation-examples/index.mjs';

/** V2 example proving replacement of both actual electricity and heat accounting. */
export function createHeaterBench({parameters={},powerRating=100,load=100}={}) {
  const system={format:'scada-system',version:1,system:{id:'equation-heater-bench'},
    components:[{id:'grid',type:'transformer'},{id:'heater',type:'rack-oven'}],
    connections:[{id:'electricity',from:{component:'grid',port:'secondary'},to:{component:'heater',port:'supply'},medium:'electricity'}]};
  const definition=createModelDefinition(system,{version:2}),c=definition.components;
  for(const config of Object.values(c)){config.parameters.damageRate=0;config.parameters.warningAt=100;config.initial.load=100;config.parameters.capacity=100;}
  c.grid.energy={role:'source',inputs:[],outputs:['secondary'],capacity:powerRating,demand:0,efficiency:1,supply:{kind:'boundary'}};
  c.heater.initial.load=load;c.heater.energy.demand=100;c.heater.energy.efficiency=1;
  c.heater.thermalStore={capacity:100,initial:0,loss:0};
  // An explicit zero-conductance link suppresses the template's default product
  // coupling so this bench isolates the resistor's electrical/thermal balance.
  c.heater.thermalLinks=[{id:'isolated-body',from:{component:'heater',circuit:'body'},to:{component:'heater',circuit:'material'},conductance:0,maximumTransfer:20,lossFraction:0}];
  c.heater.heatSource.capacity=100;
  definition.equations={version:1,components:{heater:{id:resistiveHeaterProvider.id,version:resistiveHeaterProvider.version,parameters}}};
  definition.assumptions.push('RMS voltage, constant resistance and conversion efficiency are editable assumptions. No measured heating-curve calibration.');
  return {system,definition,model:new CircuitSystemModel(system,definition,{equationProviders:[resistiveHeaterProvider]})};
}
