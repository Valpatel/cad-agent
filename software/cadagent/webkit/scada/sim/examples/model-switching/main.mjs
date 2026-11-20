import {createPlaceholderAdapter} from '../../src/index.mjs';
import {pumpEquationProviders, quadraticPumpProvider, solveQuadraticPump, solveLinearPump} from '../../src/equation-examples/index.mjs';
import {ScadaViewer} from '../../../ui/src/viewer/viewer.mjs';
import {ScadaWorkspace, renderScadaDialog} from '../../../ui/src/workspace/workspace.mjs';
import {createBenchModel, createSessionFile, readSessionFile} from './bench.mjs';

const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (value, digits = 2) => Number(value).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits});
const providers = new Map(pumpEquationProviders.map(provider => [provider.id, provider]));
const advanced = new Set(['densityKgM3','gravityMS2','flowAt100M3s','powerAt100W','pressureAt100Pa','shaftTimeConstantS','initialSpeedRatio','maxSpeedRatio']);
const labels = {
  shutoffHeadM: ['Nominal shutoff head', 'm'], quadraticResistanceS2M5: ['Quadratic pump coefficient', 's²/m⁵'], linearResistanceSM2: ['Linear pump coefficient', 's/m²'],
  staticHeadM: ['Static system head', 'm'], systemResistanceS2M5: ['System resistance', 's²/m⁵'], densityKgM3: ['Fluid density', 'kg/m³'], gravityMS2: ['Gravity', 'm/s²'],
  pumpEfficiency: ['Pump efficiency', 'fraction'], motorEfficiency: ['Motor efficiency', 'fraction'], driveEfficiency: ['Drive efficiency', 'fraction'], idlePowerW: ['Idle electrical demand', 'W'],
  flowAt100M3s: ['Flow at 100 allocation units', 'm³/s'], powerAt100W: ['Power at 100 allocation units', 'W'], pressureAt100Pa: ['Pressure at 100 display units', 'Pa'],
  shaftTimeConstantS: ['Shaft response time constant', 's'], initialSpeedRatio: ['Shaft speed on law reset', 'ratio'], maxSpeedRatio: ['Maximum speed ratio', 'ratio'],
};

let model, viewer, workspace, unsubscribe, frame, lastFrame = null, destroyed = false, system;
function status(message, error = false) { $('#status').textContent = message; $('#status').dataset.error = String(error); }
function guard(action) { try { return action(); } catch (error) { if (model) refresh(); status(error.message, true); return undefined; } }
function binding() { return model.exportModelDefinition().equations.components.pump; }
function providerState() { return model.exportSnapshot().equationState.components.pump.state; }
function command(action, args) { return model.dispatch({action, arguments: args}); }
function currentParameters() { const selected = binding(); return {...providers.get(selected.id).defaultParameters, ...selected.parameters}; }

function metrics() {
  const snapshot = model.getSnapshot(), selected = binding(), state = providerState(), params = currentParameters();
  const solve = selected.id === quadraticPumpProvider.id ? solveQuadraticPump : solveLinearPump;
  const enabled = snapshot.controls.pump.enabled;
  const potential = solve({...params, speedRatio: state.speedRatio, enabled});
  const actual = snapshot.readings.pump;
  return {snapshot, selected, state, params, potential, actual,
    flowM3s: actual.resourceOut * params.flowAt100M3s / 100,
    electricalPowerW: actual.powerIn * params.powerAt100W / 100};
}

function refresh() {
  const info = metrics();
  $('#provider').value = info.selected.id;
  $('#actual-flow').textContent = `${number(info.flowM3s * 1000)} L/s`;
  $('#potential-flow').textContent = `${number(info.potential.flowM3s * 1000)} L/s`;
  $('#actual-power').textContent = `${number(info.electricalPowerW / 1000)} kW`;
  $('#requested-power').textContent = `Local curve demand: ${number(info.potential.electricalPowerW / 1000)} kW`;
  $('#shaft-speed').textContent = `${number(info.state.speedRatio * 100, 1)}%`;
  $('#developed-head').textContent = `Local developed head: ${number(info.potential.headM)} m`;
  $('#clock').textContent = `${number(info.snapshot.minutes * 60, 1)} s`;
  $('#clock-state').textContent = info.snapshot.running ? 'RUNNING' : 'PAUSED';
  $('#run').textContent = info.snapshot.running ? 'Pause' : 'Run';
  $('#run').setAttribute('aria-pressed', String(info.snapshot.running));
  $('#provider-state').textContent = `Law state: ${number(info.state.elapsedS, 1)} s`;
}

function swap(id, parameters) {
  const provider = providers.get(id);
  if (!provider) throw new TypeError('This pump law is not registered.');
  const next = structuredClone(model.exportModelDefinition().equations);
  next.components.pump = {id, version: provider.version, parameters};
  model.setEquationBindings(next);
  status(`${provider.label ?? id} active. System time and inventories kept; law state restarted.`);
}

function parameterField(key, value, provider) {
  const schema = provider.parameterSchema.properties[key];
  const [label, unit] = labels[key] ?? [key, ''];
  const attrs = [['min', schema.minimum], ['max', schema.maximum]].filter(([,value]) => value !== undefined).map(([key,value]) => ` ${key}="${escape(value)}"`).join('');
  return `<label class="parameter-field"><span>${escape(label)} <small>${escape(unit)}</small></span><input name="${escape(key)}" type="number" value="${escape(value)}" required step="any"${attrs}><small>Assumed · editable${schema.description ? ` · ${escape(schema.description)}` : ''}</small></label>`;
}

function openParameters() {
  const selected = binding(), provider = providers.get(selected.id), params = currentParameters();
  const fields = group => Object.entries(params).filter(([key]) => advanced.has(key) === group).map(([key,value]) => parameterField(key,value,provider)).join('');
  const dialog = $('#bench-parameters-dialog');
  dialog.querySelector('[data-scada-dialog-subtitle]').textContent = `${provider.label ?? provider.id} · ${provider.id}@${provider.version}`;
  dialog.querySelector('[data-scada-dialog-body]').innerHTML = `<form id="parameter-form" class="parameter-form"><p class="assumption-note">Starting values are demonstration assumptions, not equipment calibration. Applying any parameter restarts the provider’s shaft state; system time and inventories continue.</p><h3>Curve & efficiency</h3><div class="parameter-fields">${fields(false)}</div><h3>Fluid, state & explicit unit bridges</h3><p>The surrounding allocation kernel is normalized. These scales convert its flow and power to SI values; changing them changes the effective boundary capacities.</p><div class="parameter-fields">${fields(true)}</div><p id="parameter-error" class="form-error" role="alert"></p><div class="form-actions"><button class="primary" type="submit">Apply parameters</button><button id="parameter-defaults" type="button">Use assumed defaults</button></div></form>`;
  $('#parameter-defaults').addEventListener('click', () => {
    for (const [key,value] of Object.entries(provider.defaultParameters)) $('#parameter-form').elements.namedItem(key).value = value;
  });
  $('#parameter-form').addEventListener('submit', event => {
    event.preventDefault();
    try {
      const values = Object.fromEntries([...new FormData(event.currentTarget)].map(([key,value]) => [key, Number(value)]));
      swap(provider.id, values); workspace.close();
    } catch (error) { $('#parameter-error').textContent = error.message; }
  });
  workspace.open('parameters', {opener: $('#parameters')});
}

function save() {
  const blob = new Blob([JSON.stringify(createSessionFile(model, viewer.view.id), null, 2) + '\n'], {type:'application/json'});
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = 'pump-equation-bench-session.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  status('Saved model identity, parameters, provider state, inventory, clock and focused view.');
}

function restore(data) {
  const saved = readSessionFile(data, system);
  model.importSnapshot(saved.session); // Core validates provider identity/state atomically.
  command('setRunning', {value: false});
  viewer.setView(saved.view); lastFrame = null;
  status('Session restored and paused. Saved pump law, parameters, state and system clock are active.');
}

function animate(now) {
  if (destroyed) return;
  const dt = lastFrame === null ? 0 : Math.min((now - lastFrame) / 1000, .25);
  lastFrame = now;
  if (!document.hidden && model.getSnapshot().running && dt > 0) {
    try { model.step(dt * Number($('#rate').value) / 60); }
    catch (error) { guard(() => command('setRunning', {value: false})); status(`Simulation paused: ${error.message}`, true); }
  }
  frame = requestAnimationFrame(animate);
}

async function boot() {
  const response = await fetch('./system.json');
  if (!response.ok) throw new Error(`Cannot load system definition (${response.status}).`);
  system = await response.json(); model = createBenchModel(system);
  command('setRunning', {value:false});
  $('#provider').innerHTML = pumpEquationProviders.map(provider => `<option value="${escape(provider.id)}">${provider.id === quadraticPumpProvider.id ? 'Quadratic pump curve' : 'Linear pump curve'}</option>`).join('');
  $('#dialogs').innerHTML = renderScadaDialog({id:'parameters',scope:'bench',title:'Pump law parameters',subtitle:'Editable assumptions',kind:'wide'}) + renderScadaDialog({id:'about',scope:'bench',title:'One system. Replaceable equations.',subtitle:'Actual registered providers, shared state and explicit limits.',kind:'wide',body:`<div class="dialog-copy"><div class="method-grid"><div><h3>Quadratic pump curve</h3><p class="equation-display">H = H₀ n² − a Q²</p><p>Intersected with the assumed system curve H = Hstatic + R Q².</p></div><div><h3>Linear pump curve</h3><p class="equation-display">H = H₀ n² − b n Q</p><p>A deliberately different local law using the same SI interface and efficiency chain.</p></div></div><p>Each law is registered JavaScript code with a parameter schema, version and state schema. The selector calls <code>model.setEquationBindings()</code>. JSON selects registered identities; it never contains executable expressions.</p><p><strong>Potential is not allocated flow.</strong> The SI helper solves one local curve intersection. The v2 kernel can then restrict transfer through equipment controls, inventory and available electrical supply. It is not a full hydraulic network solver. Head shown here is the local curve result, not a solved downstream pressure. The provider requests a conservative power envelope across possible throttled flows, so accepted electrical allocation can exceed the local duty-point demand. The shaft readout is commanded speed; supply limits can reduce effective speed and delivery.</p><p>The pump inspector controls speed, enable, fault and repair. The valve inspector sets a normalized allocation ceiling; it does not edit a physical valve Cv. The electrical boundary can be disabled in the Drive &amp; pump view. Both views operate the same model and clock.</p><p><strong>State has an owner.</strong> A law or parameter swap preserves the system clock and core inventories, but initializes provider state again. Save/load preserves both core and provider state, including exact provider versions. Loads open paused. An unavailable provider version or invalid state is rejected by the core before replacement.</p><p>All starting coefficients, unit bridges and boundaries are assumed and editable. No cavitation, surge, thermal pump damage, reverse flow, network pressure balance or calibrated protection model is claimed. <a href="./README.md">Example source map</a> · <a href="../../src/equation-examples/README.md">Equation provider references and limitations</a></p></div>`});
  workspace = new ScadaWorkspace($('#host-tools'));
  viewer = new ScadaViewer({definition:system,adapter:createPlaceholderAdapter(model),initialView:'hydraulics',selected:'pump',scope:'equation-bench'}).mount($('#viewer'));
  unsubscribe = model.subscribe(refresh); refresh();
  for (const id of ['provider','parameters','save','load','run','step','reset']) $(`#${id}`).disabled = false;
  $('#provider').addEventListener('change', event => guard(() => {
    const provider = providers.get(event.target.value), old = currentParameters();
    const params = Object.fromEntries(Object.entries(provider.defaultParameters).map(([key,value]) => [key, Object.hasOwn(old,key) ? old[key] : value]));
    swap(provider.id, params);
  }));
  $('#parameters').addEventListener('click', () => guard(openParameters));
  $('#run').addEventListener('click', () => guard(() => {lastFrame = null; command('setRunning',{value:!model.getSnapshot().running});status(model.getSnapshot().running ? 'Running one shared session. Equipment and parameter controls remain live.' : 'Paused. Both views retain the same system and provider state.');}));
  $('#step').addEventListener('click', () => guard(() => {command('setRunning',{value:false}); model.step(1/60);status('Advanced one simulated second; the session is paused.');}));
  $('#reset').addEventListener('click', () => guard(() => {command('setRunning',{value:false});model.reset();status('State reset; the selected law and edited model parameters are kept.');}));
  $('#save').addEventListener('click', () => guard(save));
  $('#load').addEventListener('click', () => $('#session-file').click());
  $('#session-file').addEventListener('change', async event => {
    const file = event.target.files[0]; event.target.value = ''; if (!file) return;
    try { if (file.size > 2_000_000) throw new Error('Session file exceeds the 2 MB bench limit.');restore(JSON.parse(await file.text())); }
    catch (error) { status(`Session rejected: ${error.message}`, true); }
  });
  document.addEventListener('visibilitychange', () => {lastFrame = null;});
  window.addEventListener('pagehide', event => {
    cancelAnimationFrame(frame); lastFrame = null;
    if (!event.persisted) {destroyed=true; unsubscribe();viewer.destroy();workspace.destroy();model.destroy();}
  });
  window.addEventListener('pageshow', event => {if (event.persisted && !destroyed) {lastFrame=null;frame=requestAnimationFrame(animate);}});
  // Developer inspection uses the same public model APIs as the UI; no second solver/session.
  window.equationBench = Object.freeze({model, viewer, metrics, saveData:()=>createSessionFile(model,viewer.view.id), restore});
  frame = requestAnimationFrame(animate);
  status('Paused at an assumed 60% speed. Inspect equipment, edit parameters or swap the pump law.');
}
boot().catch(error => status(`Unable to start the bench: ${error.message}`, true));
