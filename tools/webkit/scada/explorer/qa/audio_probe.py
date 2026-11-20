"""Instrumentation shared by actual Web Audio output checks; no model mocks."""
INSTRUMENT = r"""(() => {
  const NativeContext = window.AudioContext || window.webkitAudioContext;
  const qa = window.__audioQA = {contexts: [], starts: 0, oscillatorStarts: 0, bufferStarts: 0, ends: 0, outputConnections: 0};
  if (!NativeContext) return;
  const connect = AudioNode.prototype.connect;
  const outputs = new WeakMap();
  AudioNode.prototype.connect = function(destination, ...rest) {
    const output = outputs.get(this.context);
    if (output && destination === this.context.destination && this !== output) {
      qa.outputConnections++;
      connect.call(this, output, ...rest);
      return destination;
    }
    return connect.call(this, destination, ...rest);
  };
  class ObservedContext extends NativeContext {
    constructor(...args) {
      super(...args);
      const analyser = this.createAnalyser();
      // Keep ~0.7 seconds of real output, so a short valve transient survives
      // a busy main-thread layout before the next sampling callback executes.
      analyser.fftSize = 32768;
      connect.call(analyser, this.destination);
      outputs.set(this, analyser);
      qa.contexts.push({context: this, analyser});
      for (const method of ['createOscillator', 'createBufferSource']) {
        const create = this[method].bind(this);
        this[method] = (...options) => {
          const source = create(...options), start = source.start.bind(source);
          source.start = (...times) => { qa.starts++; qa[method === 'createOscillator' ? 'oscillatorStarts' : 'bufferStarts']++; return start(...times); };
          source.addEventListener('ended', () => { qa.ends++; });
          return source;
        };
      }
    }
  }
  window.AudioContext = ObservedContext;
  if (window.webkitAudioContext) window.webkitAudioContext = ObservedContext;
  qa.snapshot = () => ({contexts: qa.contexts.length, states: qa.contexts.map(x => x.context.state), starts: qa.starts, oscillatorStarts: qa.oscillatorStarts, bufferStarts: qa.bufferStarts, ends: qa.ends, outputConnections: qa.outputConnections});
  qa.signal = async (milliseconds = 600) => {
    let maxRms = 0, maxPeak = 0, samples = 0;
    const until = performance.now() + milliseconds;
    do {
      for (const {context, analyser} of qa.contexts) {
        if (context.state !== 'running') continue;
        const buffer = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(buffer);
        let sum = 0;
        for (const value of buffer) { sum += value * value; maxPeak = Math.max(maxPeak, Math.abs(value)); }
        maxRms = Math.max(maxRms, Math.sqrt(sum / buffer.length)); samples++;
      }
      await new Promise(resolve => setTimeout(resolve, 20));
    } while (performance.now() < until);
    return {maxRms, maxPeak, samples, ...qa.snapshot()};
  };
})();"""
