/** Standalone host example. The UI package owns presentation; this host owns
 * exactly one placeholder model, one clock and explicit session persistence. */
import {ScadaViewer, ScadaWorkspace, renderScadaDialog, renderScadaComponent, getScadaComponent} from '../ui/src/index.mjs';
import {PlaceholderSystemModel, createPlaceholderAdapter, getModelDescriptor} from '../sim/src/index.mjs';
import {pumpEquationProviders, resistiveHeaterProvider} from '../sim/src/equation-examples/index.mjs';
import {LabSound} from './sound.mjs';
import {filterScenarios, scenarioFacets} from './search.mjs';
import {ExtendedModelEditor} from './model-editor.mjs';
import {selectScenario, selectEquipment} from './selection.mjs';

const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const titleCase = value => { const text=String(value??''); return text.charAt(0).toUpperCase()+text.slice(1); };
const technologyLabel=value=>String(value).split('-').map(word=>['nft','dwc','led','pwr','bwr','phwr','smr','hvac','pv','chp'].includes(word)?word.toUpperCase():titleCase(word)).join(' ');
const finite = (value, fallback=0) => Number.isFinite(value) ? value : fallback;
const fixed = (value, digits=1) => finite(value).toFixed(digits);
const $ = selector => document.querySelector(selector);
const lab = $('#industry-lab'), tools = $('#lab-tools');
const base = new URL('../sim/scenarios/', import.meta.url);
const equationProviders = [...pumpEquationProviders, resistiveHeaterProvider];
let catalog = [], selectedScenario = null, system = null, modelDefinition = null, model = null, adapter = null, viewer = null, observer = null;
const sound = new LabSound({onChange: updateSound});
let unsubscribe = null, workspace = null, extendedEditor = null, speed = 1, timer = null, loadEpoch = 0, lastEventSignature = '', pendingImport = false, loadAbort = null, disposed = false;

async function json(url, signal) {
  const response = await fetch(url, {signal});
  if (!response.ok) throw new Error(`Could not load ${new URL(url).pathname.split('/').slice(-2).join('/')} (${response.status}).`);
  return response.json();
}
function message(text, error=false) {
  const node = $('[data-lab-message]'); node.textContent = text; node.hidden = !text; node.dataset.error = String(error);
}
function dialogMessage(id, text, error=false) {
  const node = tools.querySelector(`[data-dialog-message="${id}"]`);
  if (node) { node.textContent = text; node.dataset.error = String(error); }
}
function download(name, value) {
  const url = URL.createObjectURL(new Blob([`${JSON.stringify(value, null, 2)}\n`], {type:'application/json'}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function selectedEquipment(kind='fault') {
  return tools.querySelector(`[data-${kind}-equipment]`)?.value ?? viewer?.selected ?? system?.components[0]?.id;
}
function equipmentOptions(selected) {
  return (system?.components ?? []).map(item => `<option value="${esc(item.id)}"${item.id === selected ? ' selected' : ''}>${esc(item.label ?? item.id)}</option>`).join('');
}
function component(id) { return system?.components.find(item => item.id === id); }
function descriptor(id) { return getModelDescriptor(component(id).type,{version:modelDefinition.version,variant:modelDefinition.components[id].variant??component(id).variant}); }
function setBusy(value) {
  lab.setAttribute('aria-busy', String(value));
  tools.querySelectorAll('[data-action]:not([data-action^="sound-"]),[data-experiment],[data-fault]').forEach(button => { button.disabled = value; });
  if (!value) updateSound();
}
function command(action, args={}) {
  if (!model) return;
  try { adapter.dispatch({action, arguments:args}); return true; }
  catch (error) { message(error.message, true); if(workspace?.activeId)dialogMessage(workspace.activeId,error.message,true); return false; }
}

function renderTools() {
  const facets=scenarioFacets(catalog);
  tools.innerHTML = `<div class="lab-toolbar" role="group" aria-label="Simulation controls">
    <div class="lab-toolbar-group"><button type="button" class="scada-toolbutton lab-choose" data-scada-open="scenarios">▦ <span>Choose industry</span></button><button type="button" class="scada-toolbutton lab-run" data-action="running">Pause</button><button type="button" class="scada-toolbutton" data-action="step" title="Pause and advance one illustrative minute">Step +1</button><label class="lab-speed">Speed <select data-speed aria-label="Simulation speed"><option value="1">1×</option><option value="4">4×</option><option value="12">12×</option></select></label></div>
    <div class="lab-toolbar-group"><button type="button" class="scada-toolbutton" data-scada-open="faults">⚡ Fault lab</button><button type="button" class="scada-toolbutton" data-scada-open="model">Model &amp; guesses</button><button type="button" class="scada-toolbutton" data-scada-open="sound"><span data-sound-label>Sound off</span></button><button type="button" class="scada-toolbutton" data-scada-open="session">Session</button></div>
  </div>
  ${renderScadaDialog({id:'scenarios',scope:'industry',title:'Choose your control room',subtitle:`${catalog.length} example systems built from one shared symbol library and one model interface.`,kind:'wide',body:`<p class="lab-scenario-warning">Opening another industry starts its initial model. Download your current session first if you want to return to it.</p><div class="lab-search"><label>Find a process<input type="search" data-scenario-search placeholder="Beer, cookies, minerals, medicine, aquaponics…" autocomplete="off"></label><label>Sector<select data-scenario-sector><option value="">All sectors</option>${facets.sectors.map(sector=>`<option>${esc(sector)}</option>`).join('')}</select></label><label>Technology<select data-scenario-technology><option value="">All technologies</option>${facets.technologies.map(value=>`<option value="${esc(value)}">${esc(technologyLabel(value))}</option>`).join('')}</select></label></div><details class="lab-filter-details"><summary>Facility filter</summary><label class="lab-field">Facility<select data-scenario-facility><option value="">All facilities</option>${facets.facilities.map(value=>`<option>${esc(value)}</option>`).join('')}</select></label></details><div class="lab-results-toolbar"><p class="lab-results-count" data-scenario-count role="status"></p><button type="button" class="scada-toolbutton" data-action="clear-filters">Clear filters</button></div><p class="lab-current-scenario" data-scenario-current></p><div class="lab-scenario-grid" data-scenario-grid></div>`})}
  ${renderScadaDialog({id:'faults',scope:'industry',title:'Fault lab',subtitle:'Experiment with equipment failures. These are illustrative responses, with no connection to real equipment.',kind:'wide',body:`<label class="lab-field">Target equipment<select data-fault-equipment></select></label><div data-fault-readings></div><div data-fault-controls></div><div class="lab-actions"><button type="button" class="scada-toolbutton" data-action="repair">Repair selected equipment</button><button type="button" class="scada-toolbutton" data-action="inspect-fault">Open equipment controls</button></div><p class="lab-form-message" data-dialog-message="faults" role="status"></p><h3 class="lab-section-title">Try a scenario experiment</h3><div class="lab-fault-grid" data-experiments></div><p class="lab-panel-note" style="margin-top:16px">Run or step the model to observe how the fault affects connected equipment. Switching diagram layouts keeps the same faults and readings.</p>`})}
  ${renderScadaDialog({id:'model',scope:'industry',title:'Model & editable guesses',subtitle:'Every number here is a placeholder. Replace the model or adapter when a real system model is available.',kind:'wide',footer:'<div class="lab-actions"><button type="submit" form="lab-parameter-form" class="scada-toolbutton" data-apply-parameters>Apply parameter edits</button><button type="button" class="scada-toolbutton" data-action="parameter-defaults">Restore equipment parameters</button></div><p class="lab-form-message" data-dialog-message="model" role="status"></p>',body:`<p class="lab-notice">Editable demonstration values. These models prove commands and connections; they are not calibrated process or equipment models.</p><p class="lab-model-description"><a href="../sim/examples/model-switching/" target="_blank" rel="noopener">Open pump equation bench ↗</a> — compare registered pump laws, edit SI assumptions and replay a separate example session.</p><details class="lab-code-disclosure"><summary>About this industry</summary><h3 class="lab-section-title" data-model-scenario-title></h3><p class="lab-model-description" data-model-scenario-description></p><ol class="lab-stage-list" data-process-steps></ol></details><label class="lab-field lab-model-equipment">Equipment model<select data-model-equipment></select></label><div data-model-description></div><form id="lab-parameter-form" class="lab-parameter-form" data-parameter-form><div data-parameters></div></form><div data-extended-model></div><details class="lab-code-disclosure"><summary>Integration contract</summary><p class="lab-model-description">The JSON system defines components, connections, layouts and bindings. A separate JSON model supplies placeholder parameters. The viewer only reads an adapter and sends commands; it does not calculate physics.</p><pre class="lab-source-code">// Register trusted provider code; JSON selects provider IDs and parameters.
const equationProviders = [...pumpEquationProviders, resistiveHeaterProvider];
const model = new PlaceholderSystemModel(system, modelConfig, {equationProviders});
const adapter = createPlaceholderAdapter(model);
const viewer = new ScadaViewer({definition: system, adapter});
viewer.mount(container);
// One host-owned clock; all views share the same model.
model.step(1);</pre></details>`})}
  ${renderScadaDialog({id:'sound',scope:'industry',title:'Sound & alarms',subtitle:'Optional procedural sound, generated in this tab. Sound starts off on every reload.',kind:'panel',body:`<p class="lab-panel-note">A quiet machinery mix follows the current model load. Warning and fault tones repeat until acknowledged or repaired. Sound is silent while the model is paused or the tab is hidden.</p><div class="lab-actions"><button type="button" class="scada-toolbutton" data-action="sound-enabled" aria-pressed="false">Enable sound</button><button type="button" class="scada-toolbutton" data-action="sound-ack">Acknowledge alarms</button></div><div class="lab-fields" style="margin-top:20px"><label class="lab-field">Volume <output data-sound-volume-label>25%</output><input type="range" data-sound-volume min="0" max="100" value="25" aria-label="Sound volume"></label><label class="lab-field">Machinery ambience<select data-sound-ambience><option value="on">On</option><option value="off">Alarms only</option></select></label></div><p class="lab-form-message" data-dialog-message="sound" role="status"></p><h3 class="lab-section-title">Current model alarms</h3><ol class="lab-events" data-sound-alarms></ol>`})}
  ${renderScadaDialog({id:'session',scope:'industry',title:'Simulation session',subtitle:'Save an experiment, inspect recent events or restart the current industry.',kind:'wide',body:`<p class="lab-panel-note">This session lives in this browser tab. No equipment commands leave your browser. A saved session can be restored into the matching industry.</p><div class="lab-actions"><button type="button" class="scada-toolbutton" data-action="export">↓ Save session JSON</button><button type="button" class="scada-toolbutton" data-action="import">↑ Restore session JSON</button><button type="button" class="scada-toolbutton lab-danger" data-action="reset">Reset process state</button><button type="button" class="scada-toolbutton" data-scada-open="observer">Open read-only observer</button></div><input class="lab-import-file" type="file" accept="application/json,.json" data-import-file tabindex="-1" aria-label="Session JSON file"><p class="lab-form-message" data-dialog-message="session" role="status"></p><h3 class="lab-section-title">Reusable definitions</h3><p class="lab-model-description">Keep these documents separate: the system is presentation and topology; the model config is replaceable behavior and estimated values.</p><div class="lab-actions"><button type="button" class="scada-toolbutton" data-action="system-json">↓ System JSON</button><button type="button" class="scada-toolbutton" data-action="model-json">↓ Model JSON</button></div><div class="lab-session-links"><a href="../sim/docs/INTEGRATION.md" target="_blank" rel="noopener">CAD integration guide</a><a href="../ui/schema/scada-system.schema.json" target="_blank" rel="noopener">System JSON Schema</a><a href="https://github.com/Valpatel/cad-agent/tree/dev/software/cadagent/webkit/scada" target="_blank" rel="noopener">Source packages</a></div><h3 class="lab-section-title">Recent model events</h3><ol class="lab-events" data-events></ol>`})}`;
  tools.insertAdjacentHTML('beforeend', renderScadaDialog({id:'observer',scope:'industry',title:'Read-only observer',subtitle:'A second viewer of this same simulation session. Inspect equipment and change the layout; process commands are unavailable.',kind:'wide',body:'<p class="lab-observer-status">Shared simulation time: <strong data-observer-time>0.0 min</strong></p><div data-observer-viewer></div>'}));
  workspace = new ScadaWorkspace(tools, {onOpen:({id}) => {
    viewer?.closeInspector();
    if (id === 'scenarios') renderScenarioCards();
    if (id === 'faults') { renderFaultPanel(viewer?.selected); renderExperiments(); }
    if (id === 'model') renderModelPanel(viewer?.selected);
    if (id === 'session') renderEvents(true);
    if (id === 'sound') updateSound();
    if (id === 'observer') openObserver();
  }, onClose:({id}) => {
    if(id==='observer'){
      observer?.destroy();observer=null;
      tools.querySelector('[data-observer-viewer]')?.replaceChildren();
    }
  }});
  extendedEditor=new ExtendedModelEditor($('[data-extended-model]'),{dispatch:command,onMessage:text=>dialogMessage('model',text)});
  tools.addEventListener('click', onClick);
  tools.addEventListener('change', onChange);
  tools.addEventListener('input', event => { if (event.target.matches('[data-scenario-search]')) {saveFiltersToURL();renderScenarioCards();} if (event.target.matches('[data-sound-volume]')) sound.setVolume(Number(event.target.value)/100); });
  tools.addEventListener('submit', onSubmit);
  const filterURL=new URL(location.href);
  for(const[name,selector]of[['q','[data-scenario-search]'],['sector','[data-scenario-sector]'],['technology','[data-scenario-technology]'],['facility','[data-scenario-facility]']]){
    const input=$(selector),value=filterURL.searchParams.get(name)??'';if(input.tagName!=='SELECT'||[...input.options].some(option=>option.value===value))input.value=value;
  }
}
function scenarioFilters(){return{query:$('[data-scenario-search]').value,sector:$('[data-scenario-sector]').value,technology:$('[data-scenario-technology]').value,facility:$('[data-scenario-facility]').value};}
function saveFiltersToURL(){const url=new URL(location.href),filters=scenarioFilters();for(const[key,value]of Object.entries({q:filters.query,sector:filters.sector,technology:filters.technology,facility:filters.facility})){if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);}history.replaceState(null,'',url);}
function renderScenarioCards() {
  const results = filterScenarios(catalog, scenarioFilters());
  $('[data-scenario-count]').textContent = `${results.length} of ${catalog.length} industries`;
  $('[data-scenario-current]').textContent=selectedScenario?`Current session: ${selectedScenario.title}. Filtering this list keeps your model running.`:'';
  $('[data-scenario-grid]').innerHTML = results.length ? results.map((item) => `<button type="button" class="lab-scenario-card" data-scenario="${esc(item.id)}" aria-current="${item.id === selectedScenario?.id}"><span class="lab-scenario-meta">${esc(item.sector)}</span><strong>${esc(item.title)}</strong><p>${esc(item.description)}</p>${item.previewTypes?.length ? `<span class="lab-card-art" aria-hidden="true">${item.previewTypes.slice(0,3).map((type,index)=>renderScadaComponent(type,{id:`lab-card-${item.id}-${index}`,state:{running:false},decorative:true})).join('')}</span>` : ''}<span class="lab-card-bottom"><span>${item.processSteps?.length ?? 'Multiple'} process stages · shared views</span><span aria-hidden="true">${item.id === selectedScenario?.id ? '✓' : '→'}</span></span></button>`).join('') : '<p class="lab-empty">No matching industry. Try another process name or sector.</p>';
}
function renderFaultPanel(id=selectedEquipment()) {
  $('[data-fault-equipment]').innerHTML = equipmentOptions(id);
  const info = descriptor(id);
  $('[data-fault-controls]').innerHTML = `<h3 class="lab-section-title">Inject a fault</h3><div class="lab-fault-grid">${info.failureModes.map(fault => `<button type="button" class="scada-toolbutton lab-fault-button" data-fault="${esc(fault.id)}" aria-pressed="false"><strong>${esc(titleCase(fault.label))}</strong><span>${esc(fault.description ?? fault.effect)}</span></button>`).join('')}</div>`;
  dialogMessage('faults',''); updateFaultReadings();
}
function updateFaultReadings() {
  if (!model) return;
  const id = selectedEquipment(), state = model.getSnapshot(), reading = state.readings[id] ?? {}, control = state.controls[id] ?? {};
  $('[data-fault-readings]').innerHTML = `<dl class="lab-readings"><div><dt>Throughput index</dt><dd>${fixed(reading.flow)}</dd></div><div><dt>Pressure index</dt><dd>${fixed(reading.pressure)}</dd></div><div><dt>Damage</dt><dd>${fixed(reading.damage,0)}%</dd></div></dl>`;
  tools.querySelectorAll('[data-fault]').forEach(button => button.setAttribute('aria-pressed', String(state.components[id]?.damage === button.dataset.fault)));
}
function renderExperiments() {
  $('[data-experiments]').innerHTML = (selectedScenario.experiments ?? []).map(item => `<button type="button" class="scada-toolbutton lab-fault-button" data-experiment="${esc(item.id)}"><strong>${esc(item.title)}</strong><span>${esc(item.expected)}</span></button>`).join('') || '<p class="lab-panel-note">Choose an equipment fault above, then watch its connected assets.</p>';
}
function renderModelPanel(id=selectedEquipment('model')) {
  $('[data-model-equipment]').innerHTML = equipmentOptions(id);
  $('[data-model-scenario-title]').textContent = selectedScenario.title;
  $('[data-model-scenario-description]').textContent = selectedScenario.description;
  $('[data-process-steps]').innerHTML = (selectedScenario.processSteps ?? []).map(step => `<li>${esc(step)}</li>`).join('');
  const info = descriptor(id), state = model.getSnapshot(), configured = modelDefinition.components[id];
  $('[data-model-description]').innerHTML = `<h3 class="lab-section-title">${esc(component(id).label ?? info.label)}</h3><p class="lab-model-description">${esc(component(id).description ?? info.label)} ${esc((configured.assumptions ?? []).join(' '))}</p><details class="lab-code-disclosure"><summary>Placeholder behavior &amp; assumptions</summary><p class="lab-model-description">Model family: ${esc(configured.kind??configured.model)}. ${info.assumptions.map(esc).join(' ')}</p></details>`;
  $('[data-parameters]').innerHTML = info.parameters.map(parameter => {
    const value = state.parameters?.[id]?.[parameter.key] ?? info.defaultModel?.parameters?.[parameter.key] ?? parameter.default;
    return `<div class="lab-parameter-row"><div><label for="lab-param-${esc(parameter.key)}">${esc(parameter.label)} <span class="lab-parameter-value">${esc(parameter.unit)} · assumed</span></label><p id="lab-param-${esc(parameter.key)}-help">${esc(parameter.description)}</p></div><input type="number" id="lab-param-${esc(parameter.key)}" name="${esc(parameter.key)}" data-parameter="${esc(parameter.key)}" min="${parameter.min}" max="${parameter.max}" step="any" value="${finite(value)}" required aria-describedby="lab-param-${esc(parameter.key)}-help"></div>`;
  }).join('');
  extendedEditor.render({id,model,descriptor:info,component:component(id)});
  dialogMessage('model','');
}
function renderEvents(force=false) {
  if (!model || (!force && workspace.activeId !== 'session')) return;
  const events = model.getSnapshot().events ?? [], signature = JSON.stringify(events.slice(-20));
  if (!force && signature === lastEventSignature) return; lastEventSignature = signature;
  $('[data-events]').innerHTML = events.length ? events.slice(-20).reverse().map(event => `<li><time>${fixed(event.minutes ?? event.time)} min</time>${esc(event.message ?? event.description ?? event.type ?? event.action ?? JSON.stringify(event))}</li>`).join('') : '<li>No events yet. Operate equipment or inject a fault to begin an experiment.</li>';
}
function openObserver() {
  observer?.destroy();
  observer = new ScadaViewer({definition:system,adapter:createPlaceholderAdapter(model,{readOnly:true}),scope:'industry-observer'});
  observer.mount(tools.querySelector('[data-observer-viewer]'));
  if(viewer.view?.id) observer.setView(viewer.view.id);
  update();
}
function update() {
  if (!model) return;
  const state = model.getSnapshot(), components = Object.values(state.components);
  lab.dataset.running = String(state.running);
  $('[data-session-state]').textContent = document.hidden ? 'Clock suspended' : state.running ? 'Model running' : 'Model paused';
  $('[data-action="running"]').textContent = state.running ? 'Pause' : 'Run';
  $('[data-kpi="time"]').innerHTML = `${fixed(state.minutes)} <small>min</small>`;
  const observerTime=tools.querySelector('[data-observer-time]');if(observerTime)observerTime.textContent=`${fixed(state.minutes)} min`;
  $('[data-kpi="active"]').textContent = `${components.filter(item=>item.active && item.status !== 'offline').length} / ${components.length}`;
  // A descriptive mean over material participants, including stopped/zero-flow assets.
  // This is not terminal production or a conserved plant-wide material balance.
  const nonMaterial=new Set(['electricity','electrical','mechanical','optical','light','data','signal','measurement','thermal','control']);
  const material=system.components.filter(item=>!['controller','sensor','network'].includes((modelDefinition.components[item.id].kind??modelDefinition.components[item.id].model))&&descriptor(item.id).ports.some(port=>!nonMaterial.has(port.medium)));
  const flows=material.map(item=>finite(state.readings[item.id]?.flow));
  $('[data-kpi="flow"]').innerHTML = `${fixed(flows.length ? flows.reduce((sum,value)=>sum+value,0)/flows.length : 0)} <small>index</small>`;
  const faults = components.filter(item=>item.fault || item.status === 'warning' || item.status === 'offline').length;
  $('[data-kpi="health"]').textContent = faults ? `${faults} attention` : 'Nominal'; $('[data-kpi="health"]').dataset.warning = String(faults>0);
  if (workspace.activeId === 'faults') updateFaultReadings();
  if (workspace.activeId === 'model') extendedEditor.update();
  renderEvents();
  sound.update(state,{visible:!document.hidden,labels:Object.fromEntries(system.components.map(item=>[item.id,item.label??item.id]))});
}
async function loadScenario(id, {initial=false,fallback=null}={}) {
  const entry = catalog.find(item => item.id === id);
  if (!entry) throw new Error('Unknown industry. Choose one from the catalog.');
  if (entry.id === selectedScenario?.id && !initial) { const url=new URL(location.href);url.searchParams.delete('componentType');url.searchParams.delete('variant');history.replaceState(null,'',url);workspace.close();return; }
  if(disposed)return;
  loadAbort?.abort();loadAbort=new AbortController();
  const epoch = ++loadEpoch; setBusy(true); message(`Opening ${entry.title}…`);
  try {
    const [nextSystem, nextDefinition] = await Promise.all([json(new URL(entry.system,base),loadAbort.signal), json(new URL(entry.model,base),loadAbort.signal)]);
    if (epoch !== loadEpoch || disposed) return;
    const nextModel = new PlaceholderSystemModel(nextSystem,nextDefinition,{equationProviders});
    const nextAdapter = createPlaceholderAdapter(nextModel);
    // Validate the presentation before replacing a working session.
    const nextViewer = new ScadaViewer({definition:nextSystem,adapter:nextAdapter,scope:'industry-viewer'});
    workspace.close({restoreFocus:false}); viewer?.destroy(); unsubscribe?.(); model?.destroy(); sound.reset();
    selectedScenario=entry; system=nextSystem; modelDefinition=nextDefinition; model=nextModel; adapter=nextAdapter; viewer=nextViewer;
    viewer.mount($('#lab-viewer'));
    unsubscribe=model.subscribe(update);
    $('[data-scenario-title]').textContent=entry.title; $('[data-scenario-description]').textContent=entry.description;
    document.title=`${entry.title} · cad-agent simulation lab`;
    const url = new URL(location.href); url.searchParams.set('scenario',entry.id); if(!initial){url.searchParams.delete('componentType');url.searchParams.delete('variant');} history.replaceState(null,'',url);
    renderFaultPanel(viewer.selected); renderModelPanel(viewer.selected); renderExperiments(); update();
    let selectionNote='';
    if(initial){
      const requestedType=url.searchParams.get('componentType'),requestedVariant=url.searchParams.get('variant');
      const selection=selectEquipment(system.components,{componentType:requestedType,variant:requestedVariant},item=>item.variant??modelDefinition.components[item.id].variant??getScadaComponent(item.type).defaultVariant),target=selection.component;
      if(target){const targetView=viewer.views.find(view=>view.nodes?.some(node=>node.id===target.id));if(targetView)viewer.setView(targetView.id);viewer.select(target.id,{open:true,opener:$('[data-scada-open="model"]')});}
      if(selection.fallback==='variant'||fallback==='variant')selectionNote=`The requested ${requestedVariant} variant is not available in this example. ${target?`Opened ${target.label??target.id} with its declared configuration.`:'Choose a matching example from the catalog.'}`;
      else if(selection.fallback==='type'||fallback==='type')selectionNote=`The requested component type is not present in ${entry.title}. This example remains open; choose another from the catalog.`;
      else if(fallback==='scenario')selectionNote=`The linked scenario was not found. Opened ${entry.title}.`;
    }
    message(initial ? selectionNote : `${entry.title} opened with its initial model. All diagram views now share this session.`);
    if (!initial) $('[data-scenario-title]').scrollIntoView({block:'start'});
  } catch (error) { if(error.name==='AbortError'||disposed||epoch!==loadEpoch)return;message(error.message,true); if (!model) $('#lab-viewer').innerHTML='<p class="lab-loading">The control room could not load. Check that both SCADA packages and the scenario files are served together, then reload.</p>'; }
  finally { if (epoch === loadEpoch && !disposed) setBusy(false); }
}
async function onClick(event) {
  const scenario=event.target.closest('[data-scenario]'); if (scenario) { await loadScenario(scenario.dataset.scenario); return; }
  const fault=event.target.closest('[data-fault]'); if (fault) {
    const id=selectedEquipment(); if(command('setFault',{equipment:id,value:fault.dataset.fault})) dialogMessage('faults',`${descriptor(id).failureModes.find(item=>item.id===fault.dataset.fault)?.label ?? 'Fault'} injected. Run or step the model to observe its response.`); return;
  }
  const experiment=event.target.closest('[data-experiment]'); if(experiment){
    const item=selectedScenario.experiments.find(item=>item.id===experiment.dataset.experiment);
    let applied=true; for(const action of item.commands) if(!command(action.action,action.arguments)) {applied=false;break;}
    if(applied) dialogMessage('faults',`${item.expected} ${item.limitation ?? ''}`); return;
  }
  const action=event.target.closest('[data-action]')?.dataset.action; if(!action || !model) return;
  if(action==='sound-enabled') await sound.setEnabled(!sound.status.enabled || sound.status.contextState!=='running');
  else if(action==='clear-filters'){for(const selector of ['[data-scenario-search]','[data-scenario-sector]','[data-scenario-technology]','[data-scenario-facility]'])$(selector).value='';saveFiltersToURL();renderScenarioCards();}
  else if(action==='sound-ack') sound.acknowledge();
  else if(action==='running') command('setRunning',{value:!model.getSnapshot().running});
  else if(action==='step') {command('setRunning',{value:false});model.step(1);}
  else if(action==='repair') {const id=selectedEquipment(); if(command('repair',{equipment:id}))dialogMessage('faults',`${component(id).label} repaired. Its operating controls are preserved.`);}
  else if(action==='inspect-fault') {const id=selectedEquipment();workspace.close({restoreFocus:false});viewer.select(id,{open:true,opener:$('[data-scada-open="faults"]')});}
  else if(action==='parameter-defaults') {const id=selectedEquipment('model'); for(const parameter of descriptor(id).parameters) command('setParameter',{equipment:id,key:parameter.key,value:modelDefinition.components[id].parameters?.[parameter.key]??parameter.default});renderModelPanel(id);dialogMessage('model','Original component parameters restored for this equipment. Circuit, energy and environmental edits are preserved.');}
  else if(action==='reset') {model.reset();renderModelPanel(viewer.selected);dialogMessage('session','Process state, faults and time were reset. Edited parameters are preserved.');message('Process state restored. Parameter edits are preserved; faults, time and accumulated readings were reset.');}
  else if(action==='export') {download(`${selectedScenario.id}-session.json`,model.exportSnapshot());dialogMessage('session','Session JSON downloaded. Restore it into this same industry.');}
  else if(action==='import') $('[data-import-file]').click();
  else if(action==='system-json') download(`${selectedScenario.id}-system.json`,system);
  else if(action==='model-json') {download(`${selectedScenario.id}-model.json`,model.exportModelDefinition());dialogMessage('session','Model definition downloaded with current parameter edits.');}
}
async function onChange(event) {
  const target=event.target;
  if(target.matches('[data-scenario-sector],[data-scenario-technology],[data-scenario-facility]')){saveFiltersToURL();renderScenarioCards();}
  else if(target.matches('[data-speed]'))speed=Number(target.value);
  else if(target.matches('[data-fault-equipment]')){viewer.select(target.value);renderFaultPanel(target.value);}
  else if(target.matches('[data-model-equipment]')){viewer.select(target.value);renderModelPanel(target.value);}
  else if(target.matches('[data-sound-ambience]'))sound.setAmbience(target.value==='on');
  else if(target.matches('[data-import-file]')){
    const file=target.files?.[0];target.value=''; if(!file || pendingImport)return;
    if(file.size>2*1024*1024){dialogMessage('session','This file is larger than the 2 MiB example-session limit.',true);return;}
    pendingImport=true;const importingModel=model;
    try {const payload=JSON.parse(await file.text());if(model!==importingModel)throw new Error('The industry changed while the file was being read. Open the matching industry and try again.');model.importSnapshot(payload);renderModelPanel(viewer.selected);dialogMessage('session','Saved session restored. All views are reading the restored model.');message('Session restored from JSON.');}
    catch(error){dialogMessage('session',`The session was not restored: ${error.message}`,true);}
    finally{pendingImport=false;}
  }
}
function onSubmit(event) {
  if(!event.target.matches('[data-parameter-form]'))return;event.preventDefault();
  const id=selectedEquipment('model'), info=descriptor(id), values=[];
  for(const field of event.target.querySelectorAll('[data-parameter]')){
    const parameter=info.parameters.find(item=>item.key===field.dataset.parameter), value=Number(field.value);
    const valid=field.value.trim()!=='' && Number.isFinite(value) && value>=parameter.min && value<=parameter.max;
    field.setAttribute('aria-invalid',String(!valid)); if(!valid){field.focus();dialogMessage('model',`${parameter.label} must be between ${parameter.min} and ${parameter.max}.`,true);return;}
    if(value!==model.getSnapshot().parameters[id][parameter.key])values.push({equipment:id,key:parameter.key,value});
  }
  if(!values.length){dialogMessage('model','These parameters already match the shared model.');return;}
  for(const value of values)if(!command('setParameter',value)){dialogMessage('model','A parameter could not be applied. Check the model message.',true);return;}
  dialogMessage('model','Parameter edits applied to the shared model.');
}
function updateSound(){
  if(!tools.querySelector('[data-sound-label]'))return;
  const status=sound.status;
  const needsResume=status.enabled && status.contextState!=='running' && !status.pending;
  $('[data-sound-label]').textContent=needsResume?'Sound paused':status.enabled?'Sound on':'Sound off';
  $('[data-action="sound-enabled"]').textContent=status.pending?'Enabling…':needsResume?'Resume sound':status.enabled?'Mute sound':'Enable sound';
  $('[data-action="sound-enabled"]').setAttribute('aria-pressed',String(status.enabled));
  $('[data-action="sound-enabled"]').disabled=!status.supported;
  $('[data-action="sound-ack"]').disabled=status.unacknowledgedCount===0;
  $('[data-sound-volume-label]').textContent=`${Math.round(status.volume*100)}%`;
  if(document.activeElement!==$('[data-sound-volume]'))$('[data-sound-volume]').value=Math.round(status.volume*100);
  $('[data-sound-ambience]').value=status.ambience?'on':'off';
  const note=status.error || (!status.supported?'Web Audio is unavailable in this browser.':needsResume?'The browser paused audio. Select Resume sound to continue. Visual alarms remain available.':status.enabled?`${status.audible?'Sound active.':'Sound enabled; output currently silent.'} ${status.unacknowledgedCount} unacknowledged alarm${status.unacknowledgedCount===1?'':'s'}.`:'Sound is off. Visual alarms remain available.');
  dialogMessage('sound',note,!!status.error);
  $('[data-sound-alarms]').innerHTML=sound.alarms.length?sound.alarms.map(alarm=>`<li><strong>${esc(alarm.label)}</strong> <span class="lab-alarm-severity">${alarm.acknowledged?'Acknowledged':esc(titleCase(alarm.severity))}</span></li>`).join(''):'<li>No current warnings or faults.</li>';
}
function startClock(){ if(timer!==null)return;timer=setInterval(()=>{if(!document.hidden && model?.getSnapshot().running)model.step(speed);},1000); }
function stopClock(){if(timer!==null)clearInterval(timer);timer=null;}
function dispose(){disposed=true;++loadEpoch;loadAbort?.abort();stopClock();observer?.destroy();extendedEditor?.destroy();viewer?.destroy();unsubscribe?.();model?.destroy();sound.destroy();workspace?.destroy();document.removeEventListener('visibilitychange',update);}
window.addEventListener('pagehide',event=>{if(event.persisted){stopClock();sound.setActive(false);}else dispose();});
window.addEventListener('pageshow',event=>{if(event.persisted){sound.setActive(true);startClock();}});
document.addEventListener('visibilitychange',update);

try{
  const manifest=await json(new URL('index.json',base));
  if(manifest.format!=='scada-scenario-catalog'||manifest.version!==1||!Array.isArray(manifest.scenarios))throw new Error('Unsupported scenario catalog.');
  catalog=manifest.scenarios;renderTools();
  const requestedURL=new URL(location.href), requested=requestedURL.searchParams.get('scenario'), requestedType=requestedURL.searchParams.get('componentType');
  const selection=selectScenario(catalog,{scenario:requested??(!requestedType?'wastewater-digester':undefined),componentType:requestedType,variant:requestedURL.searchParams.get('variant')});
  await loadScenario(selection.entry?.id,{initial:true,fallback:selection.fallback});
  startClock();
}catch(error){message(error.message,true);setBusy(false);}
