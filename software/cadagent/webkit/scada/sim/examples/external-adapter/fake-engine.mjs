/** Test source, NOT pump physics. Requests never manufacture observations.
 * A real solver/telemetry host replaces this object, including its lifecycle. */
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
const number = (value, min = -Infinity) => typeof value === 'number' && Number.isFinite(value) && value >= min;

export class FakePumpEngine {
  #listeners = new Set();
  #state = freeze({timeSeconds:0, running:true, request:{enabled:true, speedRpm:1800}, observation:{valid:false, mechanicalRunning:false, speedRpm:null, powerKW:null, massFlowKgS:null, lastValidTimeSeconds:null, fault:false, warning:false}});
  get subscriberCount() { return this.#listeners.size; }
  read() { return this.#state; }
  onChange(listener) { this.#listeners.add(listener); return () => this.#listeners.delete(listener); }
  #commit(state, type) { this.#state = freeze(state); for (const listener of this.#listeners) listener(Object.freeze({type})); return this.#state; }
  setRequest(request) {
    if (!request || Object.keys(request).some(key => !['enabled', 'speedRpm'].includes(key)) || ('enabled' in request && typeof request.enabled !== 'boolean') || ('speedRpm' in request && !number(request.speedRpm, 0))) throw new TypeError('Invalid fake request.');
    return this.#commit({...this.#state, request:{...this.#state.request, ...request}}, 'command');
  }
  setRunning(running) {
    if (typeof running !== 'boolean') throw new TypeError('running must be boolean.');
    return this.#commit({...this.#state, running}, 'pause');
  }
  publishSample(sample) {
    if (!sample || Object.keys(sample).some(key => !['timeSeconds', 'valid', 'mechanicalRunning', 'speedRpm', 'powerKW', 'massFlowKgS', 'fault', 'warning'].includes(key)) || !number(sample.timeSeconds, this.#state.timeSeconds) || typeof sample.valid !== 'boolean') throw new TypeError('Invalid sample envelope.');
    let observation = {...this.#state.observation, valid:sample.valid};
    if (sample.valid) {
      for (const key of ['mechanicalRunning', 'fault', 'warning']) if (typeof sample[key] !== 'boolean') throw new TypeError(`Invalid ${key}.`);
      for (const key of ['speedRpm', 'powerKW', 'massFlowKgS']) if (!number(sample[key], key === 'massFlowKgS' ? -Infinity : 0)) throw new TypeError(`Invalid ${key}.`);
      const {timeSeconds, ...values} = sample;
      observation = {...values, lastValidTimeSeconds:timeSeconds};
    } else if (Object.keys(sample).some(key => !['timeSeconds', 'valid'].includes(key))) throw new TypeError('Invalid observations retain their previous values; send only timeSeconds and valid.');
    return this.#commit({...this.#state, timeSeconds:sample.timeSeconds, observation}, 'sample');
  }
}
