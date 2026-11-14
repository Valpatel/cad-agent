import {createModelDefinition,PlaceholderSystemModel,CircuitSystemModel} from '../../src/index.mjs';
import {pumpEquationProviders,pumpDefaults} from '../../src/equation-examples/index.mjs';

const edge=(id,from,fromPort,to,toPort,medium='liquid')=>({id,from:{component:from,port:fromPort},to:{component:to,port:toPort},medium});

/** Headless engineering bench. V1 uses finite tanks and an explicit generator;
 * v2 uses declared water and electrical boundaries. All ratings are assumptions.
 */
export function createPumpBench({version=2,curve='quadratic',parameters={},powerRating=100,flowRating=100,sourceCapacity=100}={}) {
  const id=`engineering.pump.${curve}`,defaults=pumpDefaults[id];
  if (!defaults) throw new RangeError('Choose linear or quadratic.');
  const system={format:'scada-system',version:1,system:{id:'equation-pump-bench',label:'Editable pump-equation bench'},
    components:[{id:'source',type:'tank',label:'Assumed water supply'},{id:'pump',type:'pump',label:'Interchangeable pump'},
      {id:'sink',type:'tank',label:'Receiver'},{id:'grid',type:version===1?'generator':'transformer',label:'Assumed electrical supply'}],
    connections:[edge('inlet','source','outlet','pump','inlet'),edge('discharge','pump','outlet','sink','inlet'),
      edge('electricity','grid',version===1?'output':'secondary','pump','drive','electricity')]};
  const definition=createModelDefinition(system,{version});
  for(const config of Object.values(definition.components)) {
    config.parameters.damageRate=0;config.parameters.warningAt=100;config.parameters.capacity=100;
    config.parameters.loss=0;config.parameters.demand=100;config.initial.load=100;
  }
  const selected={...defaults,...parameters};
  definition.components.pump.initial.load=selected.initialSpeedRatio/selected.maxSpeedRatio*100;
  definition.components.pump.parameters.capacity=flowRating;
  definition.components.pump.parameters.demand=powerRating;
  definition.components.source.parameters.capacity=sourceCapacity;
  if(version===1) {
    definition.components.source.initial.inventory=100;definition.components.source.initial.level=100;
    definition.components.sink.initial.inventory=0;definition.components.sink.initial.level=0;
    definition.components.grid.parameters.capacity=powerRating;
  } else {
    const c=definition.components;
    c.source.circuits.water.role='source';c.source.circuits.water.parameters.capacity=sourceCapacity;
    c.sink.circuits.water.role='sink';c.sink.circuits.water.parameters.capacity=100;
    c.pump.circuits.process.parameters.capacity=flowRating;
    c.pump.circuits.process.initial.inventory=50;
    c.pump.energy.demand=powerRating;c.pump.energy.efficiency=1;
    c.grid.energy={role:'source',inputs:[],outputs:['secondary'],capacity:powerRating,demand:0,efficiency:1,supply:{kind:'boundary'}};
    c.grid.parameters.capacity=powerRating;
  }
  definition.equations={version:1,components:{pump:{id,version:'1.0.0',parameters}}};
  definition.assumptions.push('Pump coefficients, physical scales and boundary ratings are editable assumptions; no measured-system calibration.',
    'The pump curve is a local operating-point model. Directed network allocation may further limit its flow; network pressure balance is not solved.');
  const Engine=version===1?PlaceholderSystemModel:CircuitSystemModel;
  return {system,definition,model:new Engine(system,definition,{equationProviders:pumpEquationProviders})};
}
