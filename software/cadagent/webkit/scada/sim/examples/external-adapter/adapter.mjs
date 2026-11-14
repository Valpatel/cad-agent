/** Developer example only: maps the fake host contract to the existing viewer.
 * No solver, IO, timers, plant connection or package export is supplied here. */
const freeze = value => {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
};
const finite = (value, name, min = -Infinity, max = Infinity) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw new TypeError(`${name} must be finite and in range.`);
  return value;
};
const boolean = (value, name) => { if (typeof value !== 'boolean') throw new TypeError(`${name} must be boolean.`); return value; };
const percent = (value, rating) => Math.max(0, Math.min(100, 100 * value / rating));

export function createExternalAdapter(engine, {readOnly = true, ratedSpeedRpm = 3600, ratedPowerKW = 10} = {}) {
  if (typeof engine?.read !== 'function' || typeof engine?.onChange !== 'function' || (!readOnly && typeof engine?.setRequest !== 'function')) throw new TypeError('Expected the example host engine contract.');
  boolean(readOnly, 'readOnly');
  finite(ratedSpeedRpm, 'ratedSpeedRpm', Number.MIN_VALUE);
  finite(ratedPowerKW, 'ratedPowerKW', Number.MIN_VALUE);

  function getSnapshot() {
    const state = engine.read(), sample = state.observation;
    finite(state.timeSeconds, 'timeSeconds', 0);
    boolean(state.running, 'running'); boolean(state.request.enabled, 'request.enabled');
    finite(state.request.speedRpm, 'request.speedRpm', 0);
    for (const key of ['valid', 'mechanicalRunning', 'fault', 'warning']) boolean(sample[key], key);
    for (const key of ['speedRpm', 'powerKW', 'massFlowKgS']) {
      if (sample[key] !== null || sample.valid) finite(sample[key], key, key === 'massFlowKgS' ? -Infinity : 0);
    }
    if (sample.lastValidTimeSeconds !== null) finite(sample.lastValidTimeSeconds, 'lastValidTimeSeconds', 0, state.timeSeconds);
    if (sample.valid && sample.lastValidTimeSeconds === null) throw new TypeError('A valid observation needs its sample time.');
    const valid = sample.valid;
    const aboveDisplayRange = valid && (sample.speedRpm > ratedSpeedRpm || sample.powerKW > ratedPowerKW);
    const meterAvailable = valid && Math.abs(sample.massFlowKgS) <= 9999;
    return freeze({
      running:state.running, seconds:state.timeSeconds,
      model:{id:'fake-pump-source', revision:'example-1', accuracy:'No physics; supplied test observations only'},
      controls:{pump:{enabled:state.request.enabled, speedPercent:percent(state.request.speedRpm, ratedSpeedRpm)}},
      telemetry:{pump:{...sample, units:{speedRpm:'rpm', powerKW:'kW', massFlowKgS:'kg/s'}}},
      displayBasis:{ratedSpeedRpm, ratedPowerKW, provenance:'Assumed example display scales; replace with documented ranges'},
      components:{pump:{
        active:valid && sample.mechanicalRunning && sample.speedRpm > 0 && !sample.fault,
        running:state.running, fault:sample.fault,
        status:!valid ? 'offline' : sample.warning || sample.fault || aboveDisplayRange ? 'warning' : 'normal',
        speed:valid ? percent(sample.speedRpm, ratedSpeedRpm) : 0,
        load:valid ? percent(sample.powerKW, ratedPowerKW) : 0,
        damage:'none',
      },meter:{
        active:meterAvailable, running:state.running, fault:false,
        status:meterAvailable ? sample.warning ? 'warning' : 'normal' : 'offline',
        // The meter supports a bounded number and offline gate, not a valid field.
        value:sample.massFlowKgS !== null && Math.abs(sample.massFlowKgS) <= 9999 ? sample.massFlowKgS : 0,
        damage:'none',
      }},
      // An omitted boolean is unavailable to the standard connection renderer.
      // Its default animation does not encode signed reverse flow.
      flows:valid ? {delivery:sample.massFlowKgS !== 0} : {},
    });
  }

  function dispatch(command) {
    if (!command || typeof command !== 'object' || Array.isArray(command) || Object.keys(command).some(key => !['action', 'component', 'arguments', 'id', 'label'].includes(key))) throw new TypeError('Unknown command fields.');
    for (const key of ['action', 'component', 'id', 'label']) if (command[key] !== undefined && (typeof command[key] !== 'string' || !command[key].length)) throw new TypeError(`Invalid command ${key}.`);
    const args = command.arguments;
    if (!args || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).some(key => !['equipment', 'value'].includes(key))) throw new TypeError('Unknown command arguments.');
    if ((args.equipment ?? command.component) !== 'pump' || (command.component !== undefined && command.component !== 'pump')) throw new RangeError('Unknown equipment.');
    let request;
    if (command.action === 'setEnabled') request = {enabled:boolean(args.value, 'enabled')};
    else if (command.action === 'setSpeedPercent') request = {speedRpm:finite(args.value, 'speedPercent', 0, 100) * ratedSpeedRpm / 100};
    else throw new RangeError('Unsupported command; fault, repair, reset and restart are not implemented by this example.');
    // Requested inputs do not claim the machine has achieved those values.
    return engine.setRequest(request);
  }

  return Object.freeze({
    getSnapshot,
    subscribe(listener) {
      if (typeof listener !== 'function') throw new TypeError('Expected listener.');
      const remove = engine.onChange(event => listener(getSnapshot(), event));
      if (typeof remove !== 'function') throw new TypeError('Host subscription must return an unsubscribe function.');
      let attached = true;
      return () => { if (attached) { attached = false; remove(); } };
    },
    ...(readOnly ? {} : {dispatch}),
  });
}
