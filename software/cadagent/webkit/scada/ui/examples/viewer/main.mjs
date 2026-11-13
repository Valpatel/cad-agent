import {ScadaViewer} from '../../src/scada-viewer.mjs';
import {UtilityModel} from './utility-model.mjs';
import {createUtilityAdapter} from './utility-adapter.mjs';

const definition = await fetch('./system.json').then(response => {
  if (!response.ok) throw new Error('The sample system definition could not be loaded.');
  return response.json();
});
const model = new UtilityModel();
const adapter = createUtilityAdapter(model);
const editable = new ScadaViewer({definition, adapter, scope:'utility-controls'}).mount(document.querySelector('#utility-viewer'));
const monitor = new ScadaViewer({definition, adapter:createUtilityAdapter(model, {readOnly:true}), initialView:'power', scope:'utility-monitor'}).mount(document.querySelector('#utility-monitor'));
const status = document.querySelector('[data-demo-status]');
const updateStatus = () => {
  const state = model.getSnapshot();
  status.textContent = `${state.minutes} illustrative minutes · ${state.running ? 'Running' : 'Paused'} · reservoir ${state.tankLevel.toFixed(1)}%`;
  document.querySelector('[data-demo-action="running"]').textContent = state.running ? 'Pause example' : 'Run example';
};
const unsubscribe = model.subscribe(updateStatus);
document.querySelector('[data-demo-actions]').addEventListener('click', event => {
  const action = event.target.closest('[data-demo-action]')?.dataset.demoAction;
  if (!action) return;
  model.dispatch(action === 'running' ? {action:'set', arguments:{key:'running', value:!model.getSnapshot().running}} : {action});
});
const visibility = () => model.setVisible(!document.hidden);
document.addEventListener('visibilitychange', visibility);
visibility(); updateStatus(); model.start();
window.addEventListener('pagehide', event => {
  model.stop();
  if (!event.persisted) { editable.destroy(); monitor.destroy(); unsubscribe(); document.removeEventListener('visibilitychange', visibility); }
});
window.addEventListener('pageshow', event => { if (event.persisted) { visibility(); model.start(); } });
