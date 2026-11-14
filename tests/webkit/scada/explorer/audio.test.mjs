import test from 'node:test';
import assert from 'node:assert/strict';
import {LabSound, collectLabAlarms} from '../../../../software/cadagent/webkit/scada/explorer/sound.mjs';
class Param {value=0;cancelScheduledValues(){}setTargetAtTime(value){this.value=value;}setValueAtTime(value){this.value=value;}linearRampToValueAtTime(value){this.value=value;}}
class AudioNode {constructor(){this.gain=new Param();this.frequency=new Param();}connect(){}disconnect(){this.disconnected=true;}start(){this.started=true;}stop(){this.stopped=true;}}
class Context extends EventTarget {
  currentTime=0;sampleRate=8000;state='suspended';destination=new AudioNode();gains=[];sources=[];closeCalls=0;
  createGain(){const node=new AudioNode();this.gains.push(node);return node;}
  createOscillator(){const node=new AudioNode();this.sources.push(node);return node;}
  createBufferSource(){return this.createOscillator();}
  createBuffer(channels,length){return{getChannelData:()=>new Float32Array(length)};}
  createBiquadFilter(){return new AudioNode();}
  createDynamicsCompressor(){const node=new AudioNode();for(const key of ['threshold','knee','ratio','attack','release'])node[key]=new Param();return node;}
  async resume(){this.state='running';this.dispatchEvent(new Event('statechange'));}async suspend(){this.state='suspended';this.dispatchEvent(new Event('statechange'));}async close(){this.state='closed';this.closeCalls++;this.dispatchEvent(new Event('statechange'));}
}
const snapshot=()=>({running:true,components:{pump:{active:true,running:true,fault:false,status:'normal',damage:'none'}},readings:{pump:{flow:50,load:60}}});
function harness(){const context=new Context();let constructions=0;return{context,get constructions(){return constructions;},sound:new LabSound({contextFactory:()=>{constructions++;return context;}})};}

test('explorer audio is opt-in and shares one context through updates, reset and re-enable',async()=>{
  const h=harness();h.sound.update(snapshot());assert.equal(h.constructions,0);assert.equal(h.sound.status.enabled,false);
  await h.sound.setEnabled(true);assert.equal(h.constructions,1);assert.equal(h.sound.status.audible,true);assert.ok(h.context.gains[0].gain.value>0);
  h.sound.reset();assert.equal(h.sound.status.audible,false);h.sound.update(snapshot());await h.sound.setEnabled(false);await h.sound.setEnabled(true);assert.equal(h.constructions,1);
  await h.sound.destroy();assert.equal(h.context.closeCalls,1);assert.equal(h.sound.status.enabled,false);
});
test('paused, hidden, inactive, zero-volume and muted states silence the master mix',async()=>{
  const h=harness();h.sound.update(snapshot());await h.sound.setEnabled(true);
  for(const operation of [()=>h.sound.update({...snapshot(),running:false}),()=>h.sound.update(snapshot(),{visible:false}),()=>h.sound.setActive(false),()=>h.sound.setVolume(0),()=>h.sound.setEnabled(false)]){
    h.sound.update(snapshot());h.sound.setActive(true);h.sound.setVolume(.25);await h.sound.setEnabled(true);await operation();assert.equal(h.sound.status.audible,false);assert.equal(h.context.gains[0].gain.value,0);
  }
  await h.sound.destroy();
});
test('current faults drive alarms; acknowledge persists until clearing and reintroduction',async()=>{
  const h=harness(),state=snapshot();state.components.pump.fault=true;state.components.pump.damage='leaking';h.sound.update(state,{labels:{pump:'Feed pump'}});
  assert.equal(h.sound.alarms[0].label,'Feed pump: leaking');assert.equal(h.sound.status.unacknowledgedCount,1);
  await h.sound.setEnabled(true);const count=h.context.sources.length;assert.equal(count,4);
  h.sound.acknowledge();assert.equal(h.sound.status.unacknowledgedCount,0);h.context.currentTime=10;h.sound.update(state);assert.equal(h.context.sources.length,count);
  h.sound.update(snapshot());h.sound.update(state);assert.equal(h.sound.status.unacknowledgedCount,1);assert.equal(h.context.sources.length,count+1);
  await h.sound.destroy();
});
test('a changing fault severity rearms and repeat alarms stay rate limited',async()=>{
  const h=harness(),state=snapshot();state.components.pump.status='warning';h.sound.update(state);await h.sound.setEnabled(true);h.sound.acknowledge();
  state.components.pump.fault=true;state.components.pump.damage='seized';h.sound.update(state);assert.equal(h.sound.status.unacknowledgedCount,1);
  const count=h.context.sources.length;for(let i=0;i<100;i++)h.sound.update(state);assert.equal(h.context.sources.length,count);
  h.context.currentTime=6;h.sound.update(state);assert.equal(h.context.sources.length,count+1);await h.sound.destroy();
});
test('mute while an enable request is pending prevents late audio revival',async()=>{
  const h=harness();let resume;h.context.resume=()=>new Promise(resolve=>{resume=()=>{h.context.state='running';resolve();};});h.sound.update(snapshot());const enabling=h.sound.setEnabled(true);await h.sound.setEnabled(false);resume();await enabling;assert.equal(h.sound.status.enabled,false);assert.equal(h.context.gains[0].gain.value,0);await h.sound.destroy();
});
test('alarm collection excludes inactive healthy equipment and marks offline signals',()=>{
  const alarms=collectLabAlarms({components:{a:{active:false,fault:false,status:'normal'},b:{active:false,status:'offline'},c:{fault:true,damage:'overheated'}}},{b:'PLC'});
  assert.equal(alarms.length,2);assert.equal(alarms[0].id,'c');assert.equal(alarms[1].label,'PLC: offline');
});
test('browser suspension notifies the host and explicit resume reuses the existing graph',async()=>{
  const context=new Context(),changes=[];let constructions=0;
  const sound=new LabSound({contextFactory:()=>{constructions++;return context;},onChange:status=>changes.push(status)});
  sound.update(snapshot());await sound.setEnabled(true);const nodes=context.sources.length;
  await context.suspend();assert.equal(changes.at(-1).contextState,'suspended');assert.equal(changes.at(-1).audible,false);assert.equal(sound.status.enabled,true);assert.equal(context.gains[0].gain.value,0);
  await sound.setEnabled(true);assert.equal(sound.status.audible,true);assert.equal(constructions,1);assert.equal(context.sources.length,nodes);
  await sound.setEnabled(false);await context.suspend();await context.resume();assert.equal(sound.status.audible,false);assert.equal(context.gains[0].gain.value,0);
  await sound.destroy();
});
