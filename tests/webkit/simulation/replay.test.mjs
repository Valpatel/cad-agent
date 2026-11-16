import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {validateRecording,samplePose,createPlayback,loadRecording,loadReceipt,loadMeshLibrary,loadReplayIndex,RECORDING_LIMITS} from '../../../software/cadagent/webkit/simulation/replay.js';

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
test('near-coincident rotations follow uniform angular time',()=>{
  const source=fixture(),angle=2e-6;source.frames[1].poses[0].quaternion=[0,Math.sin(angle/2),0,Math.cos(angle/2)];
  const recording=validateRecording(source);
  for(const t of [.01,.25,.5,.9,1])near(samplePose(recording,2*t)[0].quaternion,[0,Math.sin(angle*t/2),0,Math.cos(angle*t/2)]);
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

// #798: mesh parts, scenery, a followed body and a replay index of named recordings.
const meshFixture=()=>{const s=fixture();s.bodies[0].geometry.push({shape:'mesh',part:'link_0',position:[0,0,0],quaternion:[0,0,0,1],color:'#f5b82e',opacity:.35});
  s.scenery=[{shape:'box',size:[2,2,.05],position:[0,0,.025],quaternion:[0,0,0,1],color:'#999a9e'}];s.view={follow:'arm',direction:[.5,-1,.4]};return s;};
test('mesh parts, scenery and a followed body validate; references are checked against a library',()=>{
  const recording=validateRecording(meshFixture(),{parts:new Set(['link_0'])});
  assert.deepEqual(recording.bodies[0].geometry[1],{shape:'mesh',part:'link_0',position:[0,0,0],quaternion:[0,0,0,1],color:'#f5b82e',opacity:.35});
  assert.equal(recording.scenery[0].size[2],.05);assert.deepEqual(recording.view,{follow:'arm',direction:[.5,-1,.4]});
  assert.ok(Object.isFrozen(recording.scenery[0]));
  assert.equal(validateRecording(fixture()).view,null,'existing recordings are unchanged');assert.deepEqual(validateRecording(fixture()).scenery,[]);
  assert.throws(()=>validateRecording(meshFixture(),{parts:new Set(['other'])}),/not in the mesh library/);
  const bad=[s=>s.bodies[0].geometry[1].part='../x',s=>s.bodies[0].geometry[1].opacity=0,s=>s.bodies[0].geometry[1].opacity=1.5,s=>s.view.follow='nobody',
    s=>s.view.direction=[0,0,0],s=>s.scenery=Array(65).fill(s.scenery[0]),s=>s.scenery[0]={shape:'mesh',part:'link_0',position:[0,0,0],quaternion:[0,0,0,1],color:'#ffffff'},s=>s.scenery[0].size=[1,1]];
  for(const edit of bad){const source=meshFixture();edit(source);assert.throws(()=>validateRecording(source),/Invalid pose recording/);}
});
test('the committed Gyropup example: index, mesh library and every recording verify and agree',async()=>{
  const kit=new URL('../../../software/cadagent/webkit/',import.meta.url);
  const server=createServer(async(req,res)=>{try{res.end(await readFile(new URL('.'+decodeURIComponent(new URL(req.url,'http://x').pathname),kit)));}catch{res.writeHead(404).end();}});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}/simulation/examples/gyropup-v2/`;
  try{
    const index=await loadReplayIndex(base+'index.json');
    assert.deepEqual(index.scenarios.map(s=>s.id),['kerb_drop','side_kerb','push','landing']);
    const library=await loadMeshLibrary(index.meshes.url,{expectedHash:index.meshes.expectedHash});
    for(const [name,part] of library){assert.ok(part.positions.every(Number.isFinite),name);assert.ok(Math.max(...part.positions.map(Math.abs))<0.5,`${name} is in metres`);assert.equal(part.index.length%3,0);}
    for(const scenario of index.scenarios){
      const recording=await loadRecording(scenario.recordingUrl,{expectedHash:scenario.expectedHash,parts:library});
      assert.equal(recording.bodies.length,13);assert.equal(scenario.summary.verdict.pass,true);
      assert.match(scenario.summary.metrics[0].value,/N·m .*% of its peak-torque limit/);
    }
    await assert.rejects(()=>loadMeshLibrary(index.meshes.url,{expectedHash:'0'.repeat(64)}),/SHA-256 mismatch/);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
test('replay index and summaries are bounded text, never markup or bidi controls',async()=>{
  const good={schema:'cad-agent.replay-index/1',title:'Index',meshes:{file:'robot.json',sha256:'a'.repeat(64)},scenarios:[{id:'one',label:'One',file:'one.json',sha256:'b'.repeat(64),summary:{title:'From the source',note:'Their numbers.',verdict:{pass:false,label:'fail',reasons:['fell']},metrics:[{label:'Peak',value:'1 N·m'}]}}]};
  const bodies=new Map();let n=0;
  const server=createServer((req,res)=>res.end(bodies.get(req.url)));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
  const serve=value=>{const url=`/i${n++}`;bodies.set(url,JSON.stringify(value));return base+url;};
  try{
    const index=await loadReplayIndex(serve(good));
    assert.equal(index.scenarios[0].recordingUrl.href,base+'/one.json');assert.deepEqual(index.scenarios[0].summary.verdict,{pass:false,label:'fail',reasons:['fell']});
    const bad=[s=>s.scenarios[0].file='../one.json',s=>s.scenarios[0].file='one.js',s=>s.scenarios.push(s.scenarios[0]),s=>s.scenarios[0].sha256='x',s=>s.meshes.file='/robot.json',
      s=>s.scenarios[0].summary.metrics[0].value='a‮b',s=>s.scenarios[0].summary.metrics=Array(9).fill({label:'a',value:'b'}),s=>s.scenarios[0].summary.verdict.pass='yes',s=>s.scenarios=[],s=>s.schema='x'];
    for(const edit of bad){const value=structuredClone(good);edit(value);await assert.rejects(()=>loadReplayIndex(serve(value)),/Invalid/);}
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
