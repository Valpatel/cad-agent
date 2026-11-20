/** A deliberately fictional utility model. No UI/package dependencies. */
export class UtilityModel {
  #state = {minutes:0, running:true, pumpOn:true, valveOpen:true, demandPct:50, generatorFault:false, tankLevel:62};
  #listeners = new Set(); #timer = null; #visible = true;
  getSnapshot() { return Object.freeze({...this.#state}); }
  subscribe(listener) { this.#listeners.add(listener); return () => this.#listeners.delete(listener); }
  #emit() { const state = this.getSnapshot(); for (const listener of [...this.#listeners]) listener(state); }
  dispatch(command) {
    if (!command || typeof command !== 'object') throw new TypeError('A command object is required.');
    const args = command.arguments ?? {};
    if (command.action === 'set') {
      if (['pumpOn','valveOpen','running'].includes(args.key)) {
        if (typeof args.value !== 'boolean') throw new TypeError('This switch requires a boolean.');
      } else if (args.key === 'demandPct') {
        if (typeof args.value !== 'number' || !Number.isFinite(args.value) || args.value < 0 || args.value > 100) throw new RangeError('Demand must be from 0 to 100.');
      } else throw new RangeError('Unknown utility control.');
      this.#state = {...this.#state, [args.key]:args.value};
    } else if (command.action === 'fault') {
      if (args.equipment !== 'generator' || typeof args.value !== 'boolean') throw new TypeError('Choose a generator fault or repair.');
      this.#state = {...this.#state, generatorFault:args.value};
    } else if (command.action === 'step') {
      this.#state = {...this.#state, running:false}; this.#advance(); return;
    } else if (command.action === 'reset') {
      this.#state = {minutes:0, running:true, pumpOn:true, valveOpen:true, demandPct:50, generatorFault:false, tankLevel:62};
    } else throw new RangeError('Unknown utility command.');
    this.#emit();
  }
  #advance() {
    const flowing = this.#state.pumpOn && this.#state.valveOpen && !this.#state.generatorFault;
    const change = flowing ? 1.8 - this.#state.demandPct / 80 : -.6;
    this.#state = {...this.#state, minutes:this.#state.minutes + 1, tankLevel:Math.max(0, Math.min(100, this.#state.tankLevel + change))};
    this.#emit();
  }
  tick() { if (this.#state.running && this.#visible) this.#advance(); }
  setVisible(visible) { this.#visible = Boolean(visible); }
  start() { if (this.#timer === null) { this.#timer = setInterval(() => this.tick(), 1000); this.#timer?.unref?.(); } }
  stop() { if (this.#timer !== null) clearInterval(this.#timer); this.#timer = null; }
}
