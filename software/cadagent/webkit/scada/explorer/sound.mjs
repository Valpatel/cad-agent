/** Optional browser host audio. No model clock, network, media files or autoplay.
 * Aggregate model snapshots drive this stylized mix; it is not acoustic physics. */
const clamp=(value,min=0,max=1)=>Math.min(max,Math.max(min,Number.isFinite(value)?value:min));
function setGain(parameter,value,time,seconds=.06){parameter.cancelScheduledValues(time);parameter.setTargetAtTime(value,time,seconds);}

export function collectLabAlarms(snapshot={},labels={}){
  return Object.entries(snapshot.components??{}).flatMap(([id,state])=>{
    const severity=state.fault?'critical':state.status==='warning'||state.status==='offline'?'warning':null;
    if(!severity)return[];
    const condition=state.damage&&state.damage!=='none'?state.damage.replaceAll('-',' '):state.status==='offline'?'offline':severity==='critical'?'fault':'warning';
    return[{id,key:`${id}:${severity}:${condition}`,severity,label:`${labels[id]??id}: ${condition}`}];
  }).sort((a,b)=>(a.severity===b.severity?0:a.severity==='critical'?-1:1)||a.id.localeCompare(b.id));
}
export class LabSound {
  #factory;#onChange;#context=null;#master=null;#motor=null;#flow=null;#tone=null;#oscillators=[];#voices=new Set();
  #enabled=false;#volume=.25;#ambience=true;#snapshot={};#labels={};#visible=true;#active=true;#alarms=[];#ack=new Set();#lastAlarm=-Infinity;#destroyed=false;#request=0;#pending=false;#error='';
  constructor({onChange,contextFactory}={}){const Context=globalThis.AudioContext??globalThis.webkitAudioContext;this.#factory=contextFactory??(Context?()=>new Context({latencyHint:'interactive'}):null);this.#onChange=onChange;}
  get status(){return{enabled:this.#enabled,volume:this.#volume,ambience:this.#ambience,pending:this.#pending,supported:!!this.#factory,contextState:this.#context?.state??'uninitialized',error:this.#error,alarmCount:this.#alarms.length,unacknowledgedCount:this.#alarms.filter(alarm=>!this.#ack.has(alarm.key)).length,audible:this.#audible()};}
  get alarms(){return this.#alarms.map(alarm=>({...alarm,acknowledged:this.#ack.has(alarm.key)}));}
  #notify(){this.#onChange?.(this.status);}
  #contextChanged=()=>{if(!this.#destroyed){this.#sync();this.#notify();}};
  #audible(){return this.#enabled&&this.#context?.state==='running'&&!this.#destroyed&&this.#visible&&this.#active&&this.#snapshot.running===true&&this.#volume>0;}
  async setEnabled(value){
    const request=++this.#request;this.#enabled=Boolean(value)&&!this.#destroyed;this.#error='';
    if(!this.#enabled){this.#pending=false;this.#silenceVoices();this.#sync();this.#notify();return this.status;}
    if(!this.#factory){this.#enabled=false;this.#error='This browser does not support Web Audio.';this.#notify();return this.status;}
    this.#pending=true;this.#notify();
    try{
      if(!this.#context)this.#initialize();
      if(this.#context.state!=='running')await this.#context.resume();
      if(request!==this.#request||this.#destroyed)return this.status;
      if(this.#context.state!=='running')throw new Error('The browser paused audio. Try enabling sound again.');
      this.#pending=false;this.#sync();this.#notify();
    }catch(error){if(request!==this.#request)return this.status;this.#enabled=false;this.#pending=false;this.#error=error.message;this.#sync();this.#notify();}
    return this.status;
  }
  setVolume(value){if(typeof value!=='number'||!Number.isFinite(value))throw new TypeError('Sound volume must be finite.');this.#volume=clamp(value);this.#sync();this.#notify();}
  setAmbience(value){this.#ambience=Boolean(value);this.#sync();this.#notify();}
  setActive(value){this.#active=Boolean(value);this.#sync();this.#notify();}
  acknowledge(){this.#alarms.forEach(alarm=>this.#ack.add(alarm.key));this.#silenceVoices();this.#notify();}
  reset(){this.#alarms=[];this.#ack.clear();this.#lastAlarm=-Infinity;this.#silenceVoices();this.#snapshot={};this.#sync();this.#notify();}
  update(snapshot,{visible=true,labels={}}={}){
    if(this.#destroyed)return;this.#snapshot=snapshot??{};this.#visible=visible;this.#labels=labels;
    this.#alarms=collectLabAlarms(this.#snapshot,this.#labels);
    const current=new Set(this.#alarms.map(alarm=>alarm.key));for(const key of this.#ack)if(!current.has(key))this.#ack.delete(key);
    this.#sync();this.#notify();
  }
  #initialize(){
    const context=this.#factory();this.#context=context;
    const master=context.createGain(),compressor=context.createDynamicsCompressor();master.gain.value=0;
    compressor.threshold.value=-18;compressor.knee.value=12;compressor.ratio.value=8;compressor.attack.value=.008;compressor.release.value=.15;
    master.connect(compressor);compressor.connect(context.destination);this.#master=master;
    const motor=context.createGain();motor.gain.value=0;motor.connect(master);this.#motor=motor;
    for(const [frequency,level] of [[48,.8],[97,.25]]){const oscillator=context.createOscillator(),gain=context.createGain();oscillator.type='sine';oscillator.frequency.value=frequency;gain.gain.value=level;oscillator.connect(gain);gain.connect(motor);oscillator.start();this.#oscillators.push(oscillator);}
    this.#tone=this.#oscillators[0];
    const buffer=context.createBuffer(1,Math.floor(context.sampleRate*2),context.sampleRate),data=buffer.getChannelData(0);let seed=9137;
    for(let index=0;index<data.length;index++){seed=(1664525*seed+1013904223)>>>0;data[index]=(seed/4294967296-.5)*.7;}
    const noise=context.createBufferSource(),filter=context.createBiquadFilter(),flow=context.createGain();noise.buffer=buffer;noise.loop=true;filter.type='lowpass';filter.frequency.value=650;flow.gain.value=0;noise.connect(filter);filter.connect(flow);flow.connect(master);noise.start();this.#flow=flow;this.#oscillators.push(noise);
    context.addEventListener('statechange',this.#contextChanged);
  }
  #sync(){
    if(!this.#context)return;const time=this.#context.currentTime,audible=this.#audible();
    setGain(this.#master.gain,audible?this.#volume*.65:0,time);
    if(!audible)this.#silenceVoices();
    const readings=Object.values(this.#snapshot.readings??{}),components=Object.values(this.#snapshot.components??{});
    const working=components.filter(item=>item.active&&!item.fault&&item.status!=='offline').length;
    const flow=readings.reduce((sum,item)=>sum+clamp((item.flow??0)/100),0)/Math.max(1,readings.length);
    const activity=clamp(working/Math.max(1,components.length));
    setGain(this.#motor.gain,audible && this.#ambience ? .075*Math.sqrt(activity) : 0,time);
    setGain(this.#flow.gain,audible && this.#ambience ? .12*Math.sqrt(flow) : 0,time);
    this.#tone.frequency.setTargetAtTime(42+25*activity,time,.2);
    const unacknowledged=this.#alarms.filter(alarm=>!this.#ack.has(alarm.key));
    if(audible&&unacknowledged.length&&time-this.#lastAlarm>=6){this.#lastAlarm=time;this.#alarm(unacknowledged[0].severity);}
  }
  #alarm(severity){
    const context=this.#context,start=context.currentTime,oscillator=context.createOscillator(),gain=context.createGain();
    oscillator.type='sine';oscillator.frequency.setValueAtTime(severity==='critical'?620:440,start);oscillator.frequency.setValueAtTime(severity==='critical'?820:520,start+.22);
    gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.14,start+.025);gain.gain.linearRampToValueAtTime(0,start+.16);gain.gain.setValueAtTime(0,start+.22);gain.gain.linearRampToValueAtTime(.14,start+.245);gain.gain.linearRampToValueAtTime(0,start+.40);
    oscillator.connect(gain);gain.connect(this.#master);const voice={oscillator,gain};this.#voices.add(voice);oscillator.onended=()=>{this.#voices.delete(voice);oscillator.disconnect();gain.disconnect();};oscillator.start(start);oscillator.stop(start+.43);
  }
  #silenceVoices(){for(const voice of this.#voices){try{voice.oscillator.stop();}catch{}voice.oscillator.disconnect();voice.gain.disconnect();}this.#voices.clear();}
  async destroy(){if(this.#destroyed)return;this.#destroyed=true;this.#enabled=false;this.#request++;this.#silenceVoices();if(this.#context){this.#context.removeEventListener('statechange',this.#contextChanged);for(const oscillator of this.#oscillators){try{oscillator.stop();}catch{}}this.#master.gain.value=0;await this.#context.close();}this.#notify();}
}
