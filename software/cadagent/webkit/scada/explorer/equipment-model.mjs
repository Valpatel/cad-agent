/** Host-side inspection of the equations actually registered with this session.
 * This module reports source/configuration; it does not evaluate or replace laws. */
import {COMPONENT_MODEL_CLASSES, CircuitSystemModel, getModelDescriptor, normalizeEquationBindings, resolveEquationBinding, EQUATION_PHASE_CONTRACTS} from '../sim/src/index.mjs';
import {parameterUnits, quadraticPumpProvider, linearPumpProvider, resistiveHeaterProvider, solveQuadraticPump, solveLinearPump, resistiveHeaterPower, firstOrderResponse} from '../sim/src/equation-examples/index.mjs';

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const code = value => Function.prototype.toString.call(value);
const json = value => JSON.stringify(value, null, 2);
const kernelPath = version => version === 2 ? '../sim/src/v2/circuit-system.mjs' : '../sim/src/components.mjs';
const physics = new Map([[quadraticPumpProvider,solveQuadraticPump], [linearPumpProvider,solveLinearPump], [resistiveHeaterProvider,resistiveHeaterPower]]);

// Inspect the shipped class source instead of maintaining a second copy of its
// formulas. This is presentation-only extraction, never parsing/executing JSON.
function kernelMethod(name) {
  const lines = code(CircuitSystemModel).split('\n');
  const start = lines.findIndex(line => line.startsWith(`  #${name}(`));
  if (start < 0) return null; // A transformed distribution can still link the full source.
  const following = lines.findIndex((line, index) => index > start && /^  (?:#?[A-Za-z]\w*\(|get )/.test(line));
  return lines.slice(start, following < 0 ? -1 : following).join('\n').trim();
}

function builtinSources(config, version) {
  if (version === 2) {
    const sections = [['operating','Operating fraction'],['healthFactor','Fault availability'],['advance','Time integration and condition']];
    if (Object.keys(config.circuits ?? {}).length) sections.push(['resource','Connected material allocation'],['advanceResources','Stock and pressure integration']);
    if (config.energy) sections.push(['energyPlan','Electrical demand and conversion']);
    if (config.thermalStore || config.heatSource || config.thermalLinks?.length) sections.push(['advanceHeat','Retained heat and transfer']);
    if (config.observation || ['sensor','controller','network'].includes(config.model)) sections.push(['observations','Instrument observations']);
    return sections.map(([name,label]) => ({label,source:kernelMethod(name)})).filter(item => item.source);
  }
  const Class = COMPONENT_MODEL_CLASSES[config.kind];
  if (!Class) return [];
  return ['operatingStep','capacity','powerRequest','pressureTarget','temperatureTarget','signalTarget','conditionStep']
    .filter(name => typeof Class.prototype[name] === 'function')
    .map(name => ({label:name,source:code(Class.prototype[name])}));
}

export function equipmentModelReport({system, definition, id, providers = [], equationState}) {
  const component = system.components.find(item => item.id === id), config = definition.components[id];
  if (!component || !config) throw new RangeError(`Unknown equipment: ${id}`);
  const version = definition.version;
  if (![1,2].includes(version)) throw new RangeError('Unsupported model engine.');
  const family = version === 1 ? config.kind : config.model;
  const descriptor = getModelDescriptor(component.type,{version,variant:config.variant ?? component.variant});
  const equations = definition.equations ? normalizeEquationBindings(definition.equations,{system}) : null;
  const binding = resolveEquationBinding(equations,{...component,family},version);
  const provider = binding && providers.find(item => item.id === binding.id && item.version === binding.version);
  if (binding && !provider) throw new TypeError(`Missing registered equation provider ${binding.id}@${binding.version}.`);
  const saved = equationState?.components?.[id];
  if (saved && (!binding || saved.id !== binding.id || saved.version !== binding.version)) throw new TypeError('Saved equation identity does not match the active equipment binding.');
  const parameters = provider ? saved?.parameters ?? {...provider.defaultParameters,...binding.parameters} : config.parameters;
  const sources = provider ? [{label:'Active provider evaluation',source:code(provider.evaluate)},
    ...(provider.advance ? [{label:'Accepted-step state integration',source:code(provider.advance)}] : [])] : builtinSources(config,version);
  // These helpers are the actual imported implementations for the bundled 1.0.0 laws.
  const helper = physics.get(provider);
  if (helper) sources.unshift({label:'Physical law implementation',source:code(helper)});
  if (helper && provider.id.startsWith('engineering.pump.')) sources.push({label:'Shaft response',source:code(firstOrderResponse)});
  return {id,label:component.label ?? id,type:component.type,version,family,configuration:structuredClone(config),
    provider:provider ? {id:provider.id,version:provider.version,label:provider.label ?? provider.id,description:provider.description ?? '',units:provider.units,phases:[...provider.phases],stateVersion:provider.stateVersion} : null,
    parameters:structuredClone(parameters ?? {}), parameterUnits:provider ? helper ? {...parameterUnits} : {} : Object.fromEntries(descriptor.parameters.map(item=>[item.key,item.unit])),
    providerState: saved ? structuredClone(saved.state) : null,
    phaseContracts:provider ? provider.phases.map(phase => ({phase,...EQUATION_PHASE_CONTRACTS[phase]})) : [],
    sources,sourcePath:provider ? helper ? '../sim/src/equation-examples/providers.mjs' : null : kernelPath(version),
    bundledProvider:Boolean(helper)};
}

export function renderEquipmentModel(report) {
  const identity = report.provider ? `${report.provider.id}@${report.provider.version}` : `Built-in ${report.family} · engine v${report.version}`;
  const units = report.provider ? report.provider.units : 'Normalized illustrative indices';
  const sourceLink = !report.provider || report.bundledProvider ? `<a href="${esc(report.sourcePath)}" target="_blank" rel="noopener">Open implementation source ↗</a>` : '';
  const contracts = report.phaseContracts.map(item => `<li><strong>${esc(item.phase)}</strong><p>${esc(item.description)}</p><code>${esc(json(item.outputs))}</code>${item.engineUnits?.[report.version] ? `<p>${esc(item.engineUnits[report.version])}</p>` : ''}</li>`).join('');
  const values = Object.entries(report.parameters).map(([key,value]) => `<tr><th scope="row">${esc(key)}</th><td>${esc(typeof value === 'object' ? json(value) : value)}</td><td>${esc(report.parameterUnits[key] ?? (report.provider ? 'Provider schema' : 'Kernel index / declared parameter unit'))}</td></tr>`).join('');
  return `<section class="lab-equation-report" data-equation-report data-equipment-id="${esc(report.id)}">
    <div class="lab-model-identity"><code>${esc(report.id)}</code><span>${esc(report.type)} · ${esc(report.family)}</span></div>
    <dl class="lab-equation-meta"><div><dt>Active equations</dt><dd data-equation-identity>${esc(identity)}</dd></div><div><dt>Contract units</dt><dd>${esc(units)}</dd></div></dl>
    <p class="lab-model-description">${report.provider ? esc(report.provider.description) : 'Shared illustrative kernel. The configuration below selects this equipment’s circuits, energy roles and behavior; these are not calibrated equipment laws.'}</p>
    <details class="lab-model-section" data-model-equations><summary>Equations & implementation</summary>
      <p class="lab-model-description">Source below comes directly from the loaded implementation. It is shown as code, not evaluated from the diagram or model JSON. ${sourceLink}</p>
      ${report.sources.map(item => `<details class="lab-equation-source"><summary>${esc(item.label)}</summary><pre tabindex="0"><code>${esc(item.source)}</code></pre></details>`).join('')}
      ${contracts ? `<details class="lab-equation-source"><summary>Phase contracts & units</summary><ul class="lab-equation-contracts">${contracts}</ul></details>` : ''}
      ${report.bundledProvider ? '<p class="lab-model-description"><a href="../sim/src/equation-examples/physics.mjs" target="_blank" rel="noopener">Complete physical helpers ↗</a> · <a href="../sim/examples/model-switching/" target="_blank" rel="noopener">Compare and swap pump laws ↗</a></p>' : ''}
    </details>
    <details class="lab-model-section" data-model-current-configuration><summary>Current configuration & resolved values</summary>
      <p class="lab-model-description">This is the current accepted configuration. Edit the controls below, or export the complete model from Session. Source code and provider bindings are not changed by these fields.</p>
      <table class="lab-equation-parameters"><caption>Resolved ${report.provider ? 'provider' : 'equipment'} parameters</caption><thead><tr><th>Parameter</th><th>Value</th><th>Units</th></tr></thead><tbody>${values}</tbody></table>
      <details class="lab-equation-source"><summary>Equipment model JSON</summary><pre tabindex="0"><code data-equipment-model-json>${esc(json(report.configuration))}</code></pre></details>
      ${report.providerState ? `<details class="lab-equation-source"><summary>Provider state at inspection</summary><pre tabindex="0"><code>${esc(json(report.providerState))}</code></pre></details>` : ''}
    </details>
  </section>`;
}
