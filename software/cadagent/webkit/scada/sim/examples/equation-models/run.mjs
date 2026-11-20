import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {createPumpBench} from './pump-bench.mjs';

const assumptions=JSON.parse(readFileSync(new URL('./pump-parameters.json',import.meta.url),'utf8'));
const rows=[];
for(const version of [1,2]) {
  const parameters={...assumptions.parameters,...assumptions.curves.quadratic};
  const {model}=createPumpBench({version,parameters});
  model.dispatch({action:'setLoad',arguments:{equipment:'pump',value:50}});
  model.step(1);
  const saved=model.exportSnapshot();
  rows.push({engine:version,curve:'quadratic',state:saved.equationState.components.pump.state});
  model.setEquationBindings({version:1,components:{pump:{id:'engineering.pump.linear',version:'1.0.0',
    parameters:{...assumptions.parameters,...assumptions.curves.linear}}}});
  model.step(.1);
  rows.push({engine:version,curve:'linear',state:model.exportSnapshot().equationState.components.pump.state});
  model.importSnapshot(saved);model.step(.1);const replay=model.exportSnapshot();
  model.importSnapshot(saved);model.step(.1);assert.deepEqual(model.exportSnapshot(),replay);
  model.destroy();
}
console.log(JSON.stringify({provenance:assumptions.provenance,scope:'Local equations with kernel flow and energy allocation; not a nonlinear hydraulic network solve.',replay:'exact saved-state continuation verified',results:rows},null,2));
