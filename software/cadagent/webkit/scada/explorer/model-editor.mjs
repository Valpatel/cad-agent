/** Host-side version 2 inspector. It edits an external model through commands;
 * it owns no model clock, process equations or private equipment state. */
import {getScadaComponent} from '../ui/src/index.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const label=value=>String(value??'').replace(/([a-z])([A-Z])/g,'$1 $2').replaceAll('-',' ').replace(/^./,c=>c.toUpperCase());
const number=value=>Number.isFinite(value)?value:0;
const format=value=>number(value).toFixed(1);
const row=(field,value,group)=>`<div class="lab-parameter-row"><div><label for="lab-${group}-${esc(field.key)}">${esc(field.label??label(field.key))}<span class="lab-parameter-value">${esc(field.unit??'index')} · assumed</span></label>${field.description?`<p>${esc(field.description)}</p>`:''}</div><input id="lab-${group}-${esc(field.key)}" type="number" data-editor-field="${esc(field.key)}" min="${field.min}" max="${field.max}" step="any" value="${number(value)}" required></div>`;
const form=(kind,title,fields,values,button)=>fields.length?`<form data-model-editor-form="${kind}"><h4 class="lab-editor-title">${title}</h4>${fields.map(field=>row(field,values[field.key],kind)).join('')}<button class="scada-toolbutton" type="submit">${button}</button></form>`:'';

export class ExtendedModelEditor{
 #root;#dispatch;#message;#context=null;
 constructor(root,{dispatch,onMessage}){this.#root=root;this.#dispatch=dispatch;this.#message=onMessage;root.addEventListener('change',this.#change);root.addEventListener('submit',this.#submit);}
 render(context){
  this.#context=context;const{id,model,descriptor,component}=context,definition=model.exportModelDefinition();
  if(definition.version!==2){this.#root.innerHTML='';return;}
  const config=definition.components[id],snapshot=model.getSnapshot(),visual=getScadaComponent(component.type,{variant:config.variant??component.variant}),modes=Object.keys(config.energy?.modes??{}),measurement=descriptor.visualFields?.measurement;
  const settings=[
   visual.selectedVariant?`<p class="lab-model-description"><strong>Configuration variant: ${esc(visual.selectedVariant.label)}</strong><br>${esc(visual.selectedVariant.description??'')} Variant and port changes belong to a new system/model configuration; live controls below keep this topology.</p>`:'',
   modes.length?`<label class="lab-field">Operating mode<select data-editor-mode>${modes.map(mode=>`<option value="${esc(mode)}"${snapshot.controls[id].mode===mode?' selected':''}>${esc(label(mode))}</option>`).join('')}</select></label>`:'',
   measurement?`<label class="lab-field">Probe identity<select data-editor-measurement>${measurement.options.map(value=>`<option value="${esc(value)}"${config.measurement===value?' selected':''}>${esc({ph:'pH illustration',ec:'Conductivity illustration',do:'Dissolved oxygen illustration'}[value]??label(value))}</option>`).join('')}</select><small>Changes the observed quantity with its identity. The reading remains an index.</small></label>`:'',
   descriptor.visualFields?.rodPosition?`<label class="lab-field">Illustrative rod-position command (%)<input type="number" data-editor-rods min="0" max="100" step="1" value="${number(snapshot.controls[id].rodPosition)}"><small>Fictional heat-source command, not an operating procedure.</small></label>`:'',
  ].filter(Boolean).join('');
  const circuits=Object.keys(config.circuits??{}),zones=Object.keys(definition.zones??{});
  this.#root.innerHTML=`${settings?`<details class="lab-code-disclosure" open><summary>Equipment configuration & operating modes</summary><div class="lab-fields">${settings}</div></details>`:''}
   ${circuits.length?`<details class="lab-code-disclosure"><summary>Circuits & composition · ${circuits.length} separate path${circuits.length===1?'':'s'}</summary><p class="lab-model-description">Each circuit owns its ports, stock and composition. Changing one does not merge it with another circuit.</p><label class="lab-field">Selected circuit<select data-editor-circuit>${circuits.map(circuit=>`<option value="${esc(circuit)}">${esc(label(circuit))} · ${esc(config.circuits[circuit].fluid)}</option>`).join('')}</select></label><div data-editor-circuit-body></div></details>`:''}
   ${config.energy?`<details class="lab-code-disclosure"><summary>Energy supply & conversion</summary><p class="lab-model-description">Role: ${esc(label(config.energy.role))}. ${config.energy.supply?`Declared source: ${esc(config.energy.supply.kind)}${config.energy.supply.environment?` / ${esc(config.energy.supply.environment)}`:''}.`:''} Energy domains stay separate from material inventory.</p><dl class="lab-readings" data-editor-energy-readings></dl>${form('energy','Editable energy assumptions',descriptor.energyParameters??[],config.energy,'Apply energy assumptions')}</details>`:''}
   ${zones.length?`<details class="lab-code-disclosure"><summary>Shared environmental zones</summary><p class="lab-model-description">These state changes affect every component assigned to the same zone.</p><label class="lab-field">Zone<select data-editor-zone>${zones.map(zone=>`<option value="${esc(zone)}"${zone===config.zone?' selected':''}>${esc(label(zone))}</option>`).join('')}</select></label><div data-editor-zone-body></div></details>`:''}
   ${Object.keys(definition.environment??{}).length?`<details class="lab-code-disclosure"><summary>External environment assumptions</summary><p class="lab-model-description">Declared boundary inputs for this complete system. All values are normalized indices.</p>${form('environment','External boundary values',Object.keys(definition.environment).map(key=>({key,label:label(key),unit:'index',min:0,max:100})),definition.environment,'Apply environment assumptions')}</details>`:''}`;
  this.#renderCircuit();this.#renderZone();this.update();
 }
 #config(){return this.#context.model.exportModelDefinition().components[this.#context.id];}
 #renderCircuit(){
  const select=this.#root.querySelector('[data-editor-circuit]');if(!select)return;const{descriptor,model,id}=this.#context,circuit=this.#config().circuits[select.value],state=model.getSnapshot().circuits[id][select.value];
  this.#root.querySelector('[data-editor-circuit-body]').innerHTML=`<p class="lab-model-description">${esc(label(circuit.role))} · ${esc(circuit.fluid)} · ports ${circuit.ports.map(esc).join(', ')}</p><dl class="lab-readings" data-editor-circuit-readings></dl>${form('circuit','Editable circuit assumptions',descriptor.circuitParameters??[],circuit.parameters,'Apply circuit assumptions')}<details class="lab-code-disclosure"><summary>Inject a composition change</summary><p class="lab-model-description">Edit current tracer indices for an experiment. These are separate observations, not chemical concentrations or operating targets.</p><div data-editor-composition data-has-stock="${state.amount>0}">${state.amount>0?form('tracer','Current composition indices',descriptor.tracers??[],state,'Apply composition change'):'<p class="lab-model-description">This circuit currently contains no material. Composition edits become available when material is present.</p>'}</div></details>`;this.update();
 }
 #renderZone(){const select=this.#root.querySelector('[data-editor-zone]');if(!select)return;const{descriptor,model}=this.#context;this.#root.querySelector('[data-editor-zone-body]').innerHTML=`<dl class="lab-readings" data-editor-zone-readings></dl>${form('zone','Current shared-zone indices',descriptor.zoneFields??[],model.getSnapshot().zones[select.value],'Apply zone state')}`;this.update();}
 update(){
  if(!this.#context)return;const{model,id}=this.#context,snapshot=model.getSnapshot();if(snapshot.version!==2)return;
  const write=(selector,values)=>{const node=this.#root.querySelector(selector);if(node)node.innerHTML=values.map(([title,value])=>`<div><dt>${esc(title)}</dt><dd>${format(value)}</dd></div>`).join('');};
  const circuit=this.#root.querySelector('[data-editor-circuit]')?.value,state=snapshot.circuits[id]?.[circuit];if(state)write('[data-editor-circuit-readings]',[['Stock index',state.inventory],['Inflow index',state.input],['Outflow index',state.output],['Pressure index',state.pressure],['Thermal index',state.temperature]]);
  const composition=this.#root.querySelector('[data-editor-composition]');if(state&&composition&&composition.dataset.hasStock!==String(state.amount>0)){this.#renderCircuit();return;}
  const reading=snapshot.readings[id];write('[data-editor-energy-readings]',[['Power in index',reading.powerIn],['Power out index',reading.powerOut]]);
  const zone=this.#root.querySelector('[data-editor-zone]')?.value,z=snapshot.zones[zone];if(z)write('[data-editor-zone-readings]',Object.entries(z).map(([key,value])=>[`${label(key)} index`,value]));
 }
 #change=event=>{
  if(!this.#context)return;const target=event.target,{id}=this.#context;
  if(target.matches('[data-editor-circuit]'))this.#renderCircuit();
  else if(target.matches('[data-editor-zone]'))this.#renderZone();
  else if(target.matches('[data-editor-mode]'))this.#apply('setMode',{equipment:id,value:target.value},'Operating mode updated.');
  else if(target.matches('[data-editor-measurement]'))this.#apply('setMeasurement',{equipment:id,value:target.value},'Probe identity and observed quantity updated together.');
  else if(target.matches('[data-editor-rods]')){if(target.reportValidity())this.#apply('setRodPosition',{equipment:id,value:Number(target.value)},'Illustrative rod-position command updated.');}
 };
 #apply(action,args,message){const applied=this.#dispatch(action,args);if(applied)this.#message(message);return applied;}
 #submit=event=>{
  const form=event.target;if(!form.matches('[data-model-editor-form]'))return;event.preventDefault();event.stopPropagation();if(!form.reportValidity())return;
  const kind=form.dataset.modelEditorForm,{id,model}=this.#context,circuit=this.#root.querySelector('[data-editor-circuit]')?.value,zone=this.#root.querySelector('[data-editor-zone]')?.value,config=this.#config(),snapshot=model.getSnapshot(),definition=model.exportModelDefinition();
  const current={circuit:config.circuits?.[circuit]?.parameters,tracer:snapshot.circuits?.[id]?.[circuit],energy:config.energy,zone:snapshot.zones?.[zone],environment:definition.environment}[kind]??{};
  let count=0;for(const field of form.querySelectorAll('[data-editor-field]')){const key=field.dataset.editorField,value=Number(field.value);if(value===current[key])continue;const action={circuit:'setCircuitParameter',tracer:'setTracer',energy:'setEnergyParameter',zone:'setZoneValue',environment:'setEnvironment'}[kind];const args={key,value,...(['circuit','tracer','energy'].includes(kind)?{equipment:id}:{}),...(['circuit','tracer'].includes(kind)?{circuit}:{}),...(kind==='zone'?{zone}:{})};if(!this.#dispatch(action,args))return;count++;}
  this.#message(count?`${label(kind)} edits applied to the shared model.`:'These values already match the shared model.');this.update();
 };
 destroy(){this.#root.removeEventListener('change',this.#change);this.#root.removeEventListener('submit',this.#submit);this.#root.innerHTML='';this.#context=null;}
}
