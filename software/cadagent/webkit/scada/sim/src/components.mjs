/** Small replaceable model families. These equations use normalized demo
 * indices, never manufacturer curves, process recipes or protection logic. */
export const clamp = (value, min = 0, max = 100) => Math.min(max, Math.max(min, value));
const sum = values => values.reduce((total,value) => total + value, 0);
export class ComponentModel {
  constructor(id, descriptor, config) {
    this.id=id; this.descriptor=descriptor; this.kind=config.kind; this.parameters={...config.parameters};
    const initial=config.initial,failed=initial.failed||initial.damage>=100;
    this.state={enabled:initial.enabled,open:initial.open,load:initial.load,operating:initial.load,inventory:initial.inventory,
      pressure:initial.pressure,temperature:initial.temperature,damage:initial.failed?Math.max(initial.damage,descriptor.failureModes[0].initialDamage):initial.damage,failed,
      mode:failed?descriptor.failureModes[0].id:'none',signal:initial.load,warning:false,connected:true};
  }
  get storesResource(){return this.descriptor.inventory && !['energy-storage','source','sink'].includes(this.kind);}
  get storesPower(){return this.kind==='energy-storage';}
  get powerSource(){return this.kind==='generator' || this.storesPower;}
  get powerRelay(){return this.descriptor.powerRelay || this.storesPower;}
  get materialParticipant(){return !['controller','sensor','network'].includes(this.kind);}
  get faultEffect(){return this.descriptor.failureModes.find(mode=>mode.id===this.state.mode)?.effect??null;}
  get healthFactor(){
    if(this.state.failed)return this.faultEffect==='degrade'?.3:this.faultEffect==='leak'?.45:0;
    return Math.max(.1,1-this.state.damage/180);
  }
  get availability(){return this.state.enabled?this.healthFactor:0;}
  get conducting(){return this.descriptor.type==='breaker'?!this.state.open:this.state.open;}
  operatingStep(minutes,evaluate){const alpha=1-Math.exp(-this.parameters.response*minutes),operating=clamp(this.state.operating+(this.state.load-this.state.operating)*alpha);this.state.operating=evaluate?evaluate('operating',{operating}).operating:operating;}
  capacity(power=1,control=1){return this.parameters.capacity*this.state.operating/100*this.availability*clamp(power,0,1)*clamp(control,0,1);}
  powerRequest(){return this.parameters.demand*(.1+.9*this.state.operating/100)*(this.state.enabled?1:0);}
  pressureTarget(context){return clamp(context.upstreamPressure*.5+this.parameters.pressureGain*this.state.operating/100*(.4+context.blocked));}
  temperatureTarget(context){return clamp(20+context.upstreamTemperature*.2+context.heatIn*.25+this.parameters.heatGain*this.state.operating/100*.35);}
  signalTarget(context){return context.resourceOut || this.state.operating;}
  stockLeak(){return (this.faultEffect==='leak'?this.state.damage*.15:0)+(this.storesResource&&this.state.damage>35?this.state.damage*.015:0);}
  conditionStep(minutes,context,random,evaluate){
    const alpha=1-Math.exp(-Math.max(.1,this.parameters.response)*minutes);
    const target=(phase,value)=>evaluate?evaluate(phase,{target:value}).target:value;
    this.state.pressure=clamp(this.state.pressure+(target('pressure',this.pressureTarget(context))-this.state.pressure)*alpha);
    this.state.temperature=clamp(this.state.temperature+(target('temperature',this.temperatureTarget(context))-this.state.temperature)*alpha);
    this.state.signal=clamp(this.state.signal+(target('signal',this.signalTarget(context))-this.state.signal)*alpha);
    this.state.connected=context.connected;
    const stress=this.state.enabled?Math.max(this.state.operating,this.state.pressure,this.state.temperature,context.overload?100:0,context.missingSignal?95:0):0;
    this.state.warning=stress>this.parameters.warningAt || this.state.damage>=20 || context.powerFactor<.999 || context.missingSignal;
    if(!this.state.failed && this.state.enabled && stress>this.parameters.warningAt){
      this.state.damage=clamp(this.state.damage+this.parameters.damageRate*(stress-this.parameters.warningAt)/100*minutes*(.9+.2*random));
    }
    if(evaluate)this.state.damage=evaluate('condition',{damage:this.state.damage}).damage;
    if(!this.state.failed&&this.state.damage>=100){this.state.failed=true;this.state.mode=this.descriptor.failureModes[0].id;}
    return stress;
  }
}
export class SourceModel extends ComponentModel {pressureTarget(context){return clamp(this.parameters.pressureGain*this.state.operating/100*(1+context.blocked));}}
export class StorageModel extends ComponentModel {get storesResource(){return true;} pressureTarget(context){return clamp(this.state.inventory*.65+context.upstreamPressure*.35+context.blocked*this.parameters.pressureGain);}}
export class PumpModel extends ComponentModel {pressureTarget(context){return clamp(context.upstreamPressure*.5+this.parameters.pressureGain*this.state.operating/100*(.5+2*context.blocked));}}
export class ValveModel extends ComponentModel {capacity(power=1,control=1){return this.conducting?super.capacity(power,control):0;}}
export class PipeModel extends ValveModel {}
export class ProcessorModel extends ComponentModel {}
export class HeaterModel extends ComponentModel {temperatureTarget(context){return clamp(context.upstreamTemperature*.35+30+(this.descriptor.cooling?-1:1)*this.parameters.heatGain*this.state.operating/100+context.heatIn*.25);}}
export class GeneratorModel extends ComponentModel {temperatureTarget(context){return clamp(20+this.parameters.heatGain*this.state.operating/100+(context.overload?30:0));}}
export class PowerLoadModel extends PumpModel {}
export class EnergyStorageModel extends ComponentModel {get storesPower(){return true;}get storesResource(){return false;}}
export class SensorModel extends ComponentModel {
  get materialParticipant(){return this.descriptor.ports.some(port=>['liquid','gas','fluid','material','slurry','chemical','solids'].includes(port.medium));}
  signalTarget(context){
    if(this.state.failed)return this.state.signal;
    const reading=context.measurements[0];
    if(!reading)return this.state.operating; // Explicit bench-signal assumption.
    const key={'pressure-transmitter':'pressure','flow-meter':'flow','temperature-sensor':'temperature','level-sensor':'stock','gas-analyzer':'quality','electrical-meter':'power'}[this.descriptor.type]??'flow';
    return clamp(reading[key]??0);
  }
}
export class ControllerModel extends ComponentModel {
  get materialParticipant(){return false;}
  signalTarget(context){
    if(!context.connected || this.availability<=0)return 0;
    if(!context.signalInputs.length)return this.state.operating;
    return clamp(50+(this.state.load-sum(context.signalInputs)/context.signalInputs.length)*1.5);
  }
}
export class NetworkModel extends ControllerModel {signalTarget(context){return context.connected?clamp(15+context.signalInputs.length*8+this.state.operating*.5):0;}}
export class SinkModel extends ComponentModel {}
export const COMPONENT_MODEL_CLASSES=Object.freeze({source:SourceModel,storage:StorageModel,pump:PumpModel,valve:ValveModel,processor:ProcessorModel,heater:HeaterModel,generator:GeneratorModel,load:PowerLoadModel,controller:ControllerModel,sensor:SensorModel,pipe:PipeModel,network:NetworkModel,'energy-storage':EnergyStorageModel,sink:SinkModel});
