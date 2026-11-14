/** The host's explicit boundary setup; the reusable providers own all equations. */
import {PlaceholderSystemModel, createV2ModelDefinition} from '../../src/index.mjs';
import {pumpEquationProviders, quadraticPumpProvider} from '../../src/equation-examples/index.mjs';

export function createBenchModel(system) {
  const definition = createV2ModelDefinition(system, {seed: 73109, assumptions: [
    'An illustrative water pump with explicit supply, delivery and electrical boundaries. All coefficients are assumed, not calibrated.',
    'The registered pump law solves one local pump/system-curve intersection in SI units. The v2 allocation kernel still uses explicit normalized flow and power bridges; this is not a hydraulic pressure-network solver.',
    'The two focused views observe one session. Automatic damage drift is disabled; equipment inspectors still expose manual fault and repair commands.',
  ]});
  for (const item of Object.values(definition.components)) {
    Object.assign(item.parameters, {capacity: 100, response: 1, damageRate: 0, warningAt: 100, loss: 0});
    item.initial.load = 100;
    for (const circuit of Object.values(item.circuits)) {
      Object.assign(circuit.parameters, {capacity: 100, stockScale: 100, loss: 0});
    }
  }
  const source = Object.values(definition.components.source.circuits)[0];
  source.role = 'source'; source.initial.inventory = 100;
  const sink = Object.values(definition.components.sink.circuits)[0];
  sink.role = 'sink'; sink.initial.inventory = 0;
  definition.components.pump.initial.load = 60;
  Object.assign(definition.components.pump.energy, {capacity: 100, demand: 100, efficiency: 1});
  definition.components.power.energy = {role: 'boundary', inputs: [], outputs: ['secondary'], capacity: 100, demand: 0, efficiency: 1};
  definition.equations = {version: 1, components: {pump: {
    id: quadraticPumpProvider.id, version: quadraticPumpProvider.version,
    parameters: {...quadraticPumpProvider.defaultParameters},
  }}};
  return new PlaceholderSystemModel(system, definition, {equationProviders: pumpEquationProviders});
}

export function createSessionFile(model, view) {
  return {format: 'scada-equation-bench', version: 1, view, session: model.exportSnapshot()};
}

export function readSessionFile(value, system) {
  if (!value || value.format !== 'scada-equation-bench' || value.version !== 1) throw new TypeError('Choose a version 1 equation-bench session file.');
  if (!system.views.some(view => view.id === value.view)) throw new TypeError('The saved view is not part of this bench.');
  if (value.session?.system?.id !== system.system.id) throw new TypeError('This session belongs to another system.');
  const equations = value.session.model?.equations, selected = equations?.components?.pump;
  if (!pumpEquationProviders.some(provider => provider.id === selected?.id && provider.version === selected.version)) throw new TypeError('The saved pump law/version is not registered in this bench.');
  if (Object.keys(equations.components).some(id => id !== 'pump') || Object.keys(equations.types ?? {}).length || Object.values(equations.families ?? {}).some(map => Object.keys(map).length)) throw new TypeError('This bench accepts equation overrides on the pump instance only.');
  return value;
}
