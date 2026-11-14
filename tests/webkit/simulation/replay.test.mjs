import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {validateRecording,samplePose,createPlayback,loadRecording,loadReceipt,RECORDING_LIMITS} from '../../../software/cadagent/webkit/simulation/replay.js';

const fixture=()=>({schema:'cad-agent.pose-recording/1',title:'Analytic rotation',convention:{length:'m',up:'z',handedness:'right',quaternion:'xyzw'},bodies:[{id:'arm',label:'Arm',geometry:[{shape:'box',size:[1,.1,.1],position:[.5,0,0],quaternion:[0,0,0,1],color:'#12abcd'}]}],frames:[{time_s:0,poses:[{position:[0,0,0],quaternion:[0,0,0,1]}]},{time_s:2,poses:[{position:[2,4,6],quaternion:[0,0,1,0]}]}]});
const near=(a,b)=>a.forEach((x,i)=>assert.ok(Math.abs(x-b[i])<1e-10,`${a} != ${b}`));
test('detached normalized poses, analytic midpoint rotation, endpoint clamps',()=>{
  const source=fixture(),recording=validateRecording(source);source.frames[1].poses[0].position[0]=999;
  assert.ok(Object.isFrozen(recording.frames[0].poses[0].position));
  const midpoint=samplePose(recording,1)[0];near(midpoint.position,[1,2,3]);near(midpoint.quaternion,[0,0,Math.SQRT1_2,Math.SQRT1_2]);
  near(samplePose(recording,-1)[0].position,[0,0,0]);near(samplePose(recording,10)[0].position,[2,4,6]);
});
test('equivalent negative quaternion signs take the short rotation path',()=>{
  const source=fixture();source.frames[1].poses[0].quaternion=[0,0,0,-1];
  near(samplePose(validateRecording(source),1)[0].quaternion,[0,0,0,1]);
});
test('rejects malformed identities, incomplete poses, nonfinite values and resource excess',()=>{
  const bad=[s=>s.bodies.push(s.bodies[0]),s=>s.bodies[0].id='__proto__',s=>s.frames[1].poses=[],s=>s.frames[1].time_s=0,s=>s.frames[0].time_s=.1,s=>s.frames[1].time_s=3601,s=>s.frames[0].poses[0].position[0]=Infinity,s=>s.frames[0].poses[0].quaternion=[0,0,0,2],s=>s.bodies[0].geometry[0].size[0]=0,s=>s.convention.up='y',s=>s.frames=Array(30002).fill(s.frames[0])];
  for(const edit of bad){const source=fixture();edit(source);assert.throws(()=>validateRecording(source),/Invalid pose recording/);}
});
test('clock pauses, changes speed, stops at capture end, restarts and disposes',()=>{
  const states=[],play=createPlayback(validateRecording(fixture()),s=>states.push(s));
  play.advance(.5);assert.equal(play.state().time,0);play.play();play.advance(.5);assert.equal(play.state().time,.5);
  play.setSpeed(2);play.advance(.5);assert.equal(play.state().time,1.5);play.pause();play.advance(.5);assert.equal(play.state().time,1.5);
  play.seek(1.9);play.play();play.advance(.1);assert.equal(play.state().time,2);assert.equal(play.state().playing,false);
  play.play();assert.equal(play.state().time,0);assert.throws(()=>play.seek(NaN));assert.throws(()=>play.setSpeed(0));
  play.dispose();const count=states.length;play.dispose();assert.equal(states.length,count);assert.equal(play.state().disposed,true);assert.throws(()=>play.play(),/disposed/);
});
test('loader verifies exact bytes, caps declared/streamed bodies and rejects unsafe URLs',async()=>{
  const bytes=JSON.stringify(fixture()),hash=createHash('sha256').update(bytes).digest('hex');
  const server=createServer((req,res)=>{
    if(req.url==='/declared'){res.writeHead(200,{'content-length':RECORDING_LIMITS.bytes+1});res.end();}
    else if(req.url==='/streamed'){res.writeHead(200);res.end(' '.repeat(RECORDING_LIMITS.bytes+1));}
    else if(req.url==='/receipt'){res.end(JSON.stringify({schema:'cad-agent.simulation-receipt/1',engine:{name:'MuJoCo',version:'3.3.7'},artifacts:{'recording.json':hash},effective_settings:{frame_count:2,completed_steps:1000,duration_s:2,timestep_s:.002,sample_hz:1}}));}
    else res.end(bytes);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
  try{
    assert.equal((await loadRecording(base,{expectedHash:hash})).duration,2);
    await assert.rejects(()=>loadRecording(base,{expectedHash:'0'.repeat(64)}),/SHA-256 mismatch/);
    await assert.rejects(()=>loadRecording(base+'/declared'),/byte limit/);
    await assert.rejects(()=>loadRecording(base+'/streamed'),/byte limit/);
    await assert.rejects(()=>loadRecording('file:///tmp/model.json'),/HTTP/);
    await assert.rejects(()=>loadRecording('https://name:password@example.test/model.json'),/HTTP/);
    assert.equal((await loadReceipt(base+'/receipt')).engine.version,'3.3.7');
    await assert.rejects(()=>loadReceipt(base),/Invalid simulation receipt/);
    const abort=new AbortController();abort.abort();await assert.rejects(()=>loadRecording(base,{signal:abort.signal}),/abort/i);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
