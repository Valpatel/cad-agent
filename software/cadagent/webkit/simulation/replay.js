/** Recorded rigid-body poses. This module interpolates evidence; it never runs physics. */
export const RECORDING_LIMITS = Object.freeze({bytes:16 * 1024 * 1024, bodies:32, frames:30001, poses:200000, duration:3600});
const fail = message => { throw new TypeError(`Invalid pose recording: ${message}`); };
const finite = (n, limit=10000) => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= limit;
const text = (s, max) => typeof s === 'string' && s.length > 0 && s.length <= max && !/[\x00-\x1f]/.test(s);
const vector = (v, n, label) => {
  if (!Array.isArray(v) || v.length !== n || !v.every(x=>finite(x))) fail(label);
  return [...v];
};
function quaternion(value) {
  const q=vector(value,4,'quaternion'), length=Math.hypot(...q);
  if (Math.abs(length-1)>1e-5) fail('quaternion must be normalized (xyzw)');
  return q.map(x=>x/length);
}
const freeze = value => {
  if(value && typeof value==='object') {Object.values(value).forEach(freeze);Object.freeze(value);}
  return value;
};

/** Validate and detach all runtime data. Pose order is the immutable bodies array order. */
export function validateRecording(input) {
  if (!input || input.schema!=='cad-agent.pose-recording/1') fail('schema');
  const c=input.convention;
  if (!c || c.length!=='m' || c.up!=='z' || c.handedness!=='right' || c.quaternion!=='xyzw') fail('coordinate convention');
  if(!text(input.title,160))fail('title');
  if(!Array.isArray(input.bodies)||!input.bodies.length||input.bodies.length>RECORDING_LIMITS.bodies)fail('body count');
  const ids=new Set();
  const bodies=input.bodies.map(body=>{
    if(!body || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(body.id)||ids.has(body.id))fail('unique body IDs');
    ids.add(body.id);
    if(!text(body.label,128))fail('body label');
    if(!Array.isArray(body.geometry)||!body.geometry.length||body.geometry.length>16)fail('body geometry count');
    const geometry=body.geometry.map(g=>{
      const count={box:3,cylinder:2,sphere:1}[g?.shape];
      if(!count)fail('primitive shape');
      const size=vector(g.size,count,'primitive dimensions');
      if(size.some(n=>n<=0 || n>100))fail('primitive dimension range');
      if(typeof g.color!=='string'||!/^#[0-9a-f]{6}$/i.test(g.color))fail('primitive color');
      return {shape:g.shape,size,position:vector(g.position,3,'local position'),quaternion:quaternion(g.quaternion),color:g.color};
    });
    return {id:body.id,label:body.label,geometry};
  });
  if(!Array.isArray(input.frames)||input.frames.length<2||input.frames.length>RECORDING_LIMITS.frames||input.frames.length*bodies.length>RECORDING_LIMITS.poses)fail('frame/pose count');
  let previous=-1;
  const frames=input.frames.map((frame,i)=>{
    if(!frame||!finite(frame.time_s,RECORDING_LIMITS.duration)||frame.time_s<0||frame.time_s<=previous||(i===0&&frame.time_s!==0))fail('strictly increasing time starting at zero');
    previous=frame.time_s;
    if(!Array.isArray(frame.poses)||frame.poses.length!==bodies.length)fail('complete ordered poses');
    return {time_s:frame.time_s,poses:frame.poses.map(p=>{
      if(!p)fail('pose');
      return {position:vector(p.position,3,'world position'),quaternion:quaternion(p.quaternion)};
    })};
  });
  return freeze({schema:input.schema,title:input.title,convention:{length:'m',up:'z',handedness:'right',quaternion:'xyzw'},bodies,frames,duration:previous});
}

/** Shortest-path unit-quaternion interpolation, including equivalent q/-q endpoints. */
export function interpolateQuaternion(a,b,t) {
  let dot=a.reduce((sum,x,i)=>sum+x*b[i],0), target=b;
  if(dot<0){target=b.map(x=>-x);dot=-dot;}
  dot=Math.min(1,dot);
  let q;
  if(dot>.9995)q=a.map((x,i)=>x+(target[i]-x)*t);
  else {const angle=Math.acos(dot),s=Math.sin(angle);q=a.map((x,i)=>(x*Math.sin((1-t)*angle)+target[i]*Math.sin(t*angle))/s);}
  const length=Math.hypot(...q);return q.map(x=>x/length);
}

/** Sample a validated recording at seconds, clamping to the captured window. */
export function samplePose(recording,time) {
  if(!finite(time,Number.MAX_VALUE))throw new TypeError('Playback time must be finite');
  const frames=recording.frames,t=Math.max(0,Math.min(recording.duration,time));
  let lo=0,hi=frames.length-1;
  while(lo+1<hi){const mid=(lo+hi)>>1;if(frames[mid].time_s<=t)lo=mid;else hi=mid;}
  const a=frames[lo],b=frames[hi],alpha=(t-a.time_s)/(b.time_s-a.time_s);
  return a.poses.map((p,i)=>({position:p.position.map((n,k)=>n+(b.poses[i].position[k]-n)*alpha),quaternion:interpolateQuaternion(p.quaternion,b.poses[i].quaternion,alpha)}));
}

/** A caller-owned clock: advance(dt seconds) from the stage; no hidden animation frame. */
export function createPlayback(recording,onChange=()=>{}) {
  let time=0,speed=1,playing=false,disposed=false;
  const state=()=>({time,speed,playing,duration:recording.duration,disposed});
  const notify=()=>{if(!disposed)onChange(state(),samplePose(recording,time));};
  const alive=()=>{if(disposed)throw new Error('Replay has been disposed');};
  const api={
    state,
    play(){alive();if(time===recording.duration)time=0;playing=true;notify();},
    pause(){alive();playing=false;notify();},
    seek(value){alive();if(!finite(value,Number.MAX_VALUE))throw new TypeError('Seek time must be finite');time=Math.max(0,Math.min(recording.duration,value));notify();},
    setSpeed(value){alive();if(!finite(value)||value<.1||value>4)throw new TypeError('Replay speed must be between 0.1 and 4');speed=value;notify();},
    advance(dt){alive();if(!finite(dt)||dt<0||dt>1)throw new TypeError('Frame interval must be between 0 and 1 seconds');if(!playing)return;time=Math.min(recording.duration,time+dt*speed);if(time===recording.duration)playing=false;notify();},
    dispose(){if(disposed)return;playing=false;disposed=true;onChange=()=>{};},
  };
  notify();return api;
}

/** Bounded same-origin JSON loading with optional exact-byte SHA-256 verification. */
async function readJsonDocument(url,{signal,expectedHash,maxBytes=RECORDING_LIMITS.bytes}={}) {
  const target=new URL(url,globalThis.location?.href);
  if(!['http:','https:'].includes(target.protocol)||target.username||target.password||(globalThis.location&&target.origin!==location.origin))throw new TypeError('Recording URL must be same-origin HTTP(S)');
  if(expectedHash!==undefined&&!/^[0-9a-f]{64}$/.test(expectedHash))throw new TypeError('Invalid recording SHA-256');
  const response=await fetch(target,{signal,mode:'same-origin'});if(!response.ok)throw new Error(`Recording request failed: ${response.status}`);
  if(+response.headers.get('content-length')>maxBytes){await response.body?.cancel();throw new Error('Recording exceeds byte limit');}
  const reader=response.body.getReader(),chunks=[];let size=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maxBytes)throw new Error('Recording exceeds byte limit');chunks.push(value);}}
  catch(error){await reader.cancel().catch(()=>{});throw error;}
  finally{reader.releaseLock();}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  if(expectedHash){const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');if(hash!==expectedHash)throw new Error('Recording SHA-256 mismatch');}
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}

export async function loadRecording(url,options={}) {return validateRecording(await readJsonDocument(url,options));}

/** Load only the bounded receipt fields the standalone example presents. Hashes establish byte identity. */
export async function loadReceipt(url,{signal}={}) {
  const r=await readJsonDocument(url,{signal,maxBytes:65536}),s=r?.effective_settings;
  if(r?.schema!=='cad-agent.simulation-receipt/1'||r.engine?.name!=='MuJoCo'||!text(r.engine.version,32)||!s
    ||!/^[0-9a-f]{64}$/.test(r.artifacts?.['recording.json'])||!Number.isInteger(s.frame_count)||s.frame_count<2||s.frame_count>RECORDING_LIMITS.frames
    ||!Number.isInteger(s.completed_steps)||s.completed_steps<1||s.completed_steps>100000
    ||!finite(s.duration_s,RECORDING_LIMITS.duration)||s.duration_s<=0||!finite(s.timestep_s,1)||s.timestep_s<=0
    ||!finite(s.sample_hz,1000)||s.sample_hz<=0||Math.abs(s.completed_steps*s.timestep_s-s.duration_s)>1e-8)throw new TypeError('Invalid simulation receipt');
  return r;
}
