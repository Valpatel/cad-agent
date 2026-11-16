import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import net from 'node:net';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

test('directory applications retain a slash so their relative module URLs resolve correctly',async()=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'cad-agent-directory-preview-'));
  let server;
  try {
    await mkdir(path.join(dir,'kit/example'),{recursive:true});
    await writeFile(path.join(dir,'kit/example/index.html'),'<script type="module" src="./app.mjs"></script>');
    await writeFile(path.join(dir,'kit/example/app.mjs'),'export const ready=true;');
    await writeFile(path.join(dir,'toolkit.html'),'<h1>Toolkit</h1>');
    server=spawn(process.execPath,[path.resolve(import.meta.dirname,'../../tools/site/preview-site.mjs'),'--dir',dir,'--port','0']);
    const base=await new Promise((resolve,reject)=>{server.stdout.on('data',data=>{const url=String(data).match(/http:\/\/[\d.]+:\d+/);if(url)resolve(url[0]);});server.once('error',reject);server.once('exit',code=>reject(new Error(`preview exited ${code}`)));});
    for(const source of ['/kit/example/index.html','/kit/example']) {
      const first=await fetch(base+source+'?scenario=water',{redirect:'manual'});
      assert.equal(first.status,308);assert.equal(first.headers.get('location'),'/kit/example/?scenario=water');
      const response=await fetch(base+source+'?scenario=water');
      assert.equal(response.status,200);assert.equal(new URL(response.url).search,'?scenario=water');
      const module=await fetch(new URL('./app.mjs',response.url));assert.equal(module.status,200);assert.match(await module.text(),/ready=true/);
    }
    const flat=await fetch(base+'/toolkit.html',{redirect:'manual'});assert.equal(flat.headers.get('location'),'/toolkit');
  } finally {server?.kill();await rm(dir,{recursive:true,force:true});}
});

// The server's own request record, asked for over IPC by a browser test whose page request stalls (#686).
test('an IPC parent can read the server record of each request, its socket and idle closes',async()=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'cad-agent-preview-record-'));
  let server;
  try {
    const page='<h1>Recorded</h1>';
    await writeFile(path.join(dir,'recorded.html'),page);
    server=spawn(process.execPath,[path.resolve(import.meta.dirname,'../../tools/site/preview-site.mjs'),'--dir',dir,'--port','0'],{stdio:['pipe','pipe','inherit','ipc']});
    const base=await new Promise((resolve,reject)=>{server.stdout.on('data',data=>{const url=String(data).match(/http:\/\/[\d.]+:\d+/);if(url)resolve(url[0]);});server.once('exit',code=>reject(new Error(`preview exited ${code}`)));});
    const ask=(pathname,since)=>new Promise(resolve=>{const id=Math.random();server.on('message',function on(m){if(m.id===id){server.off('message',on);resolve(m);}});server.send({type:'preview-evidence',id,path:pathname,since});});
    const since=Date.now();
    // a raw keep-alive socket: two requests on it, then the server's idle close
    const socket=net.connect(new URL(base).port,'127.0.0.1');
    let text='';socket.on('data',d=>{text+=d;});
    const closed=new Promise(resolve=>socket.on('close',resolve));
    for(let n=1;n<=2;n++){socket.write('GET /recorded?q=private HTTP/1.1\r\nHost: x\r\n\r\n');while(text.split('Recorded').length<=n)await new Promise(r=>setTimeout(r,10));}
    const record=await ask('/recorded',since);
    assert.equal(record.matching.length,2);
    const [first,second]=record.matching;
    for(const r of record.matching){
      assert.equal(r.status,200);assert.equal(r.path,'/recorded');assert.equal(r.file,'/recorded.html');
      assert.equal(r.sha256,createHash('sha256').update(page).digest('hex'));
      assert(r.receivedAt>=since&&r.readAt>=r.receivedAt&&r.headersAt>=r.readAt&&r.finishedAt>=r.headersAt);
    }
    assert.equal(first.socket.id,second.socket.id,'both requests were on one socket');
    assert.deepEqual([first.onSocket,second.onSocket],[1,2]);assert(second.idleBeforeMs>=0);
    assert.equal(record.window.unfinished,0);assert.equal(record.openSockets,1);
    assert.equal(record.keepAlive.keepAliveTimeout,5000);assert(record.lag.maxMs>=0);
    assert.deepEqual((await ask('/never-requested',since)).matching,[]);
    await closed;   // Node closes the idle keep-alive socket (keepAliveTimeout plus its buffer, about 6 s)
    const after=await ask('/recorded',since);
    assert.equal(after.openSockets,0);assert.equal(after.window.socketsClosedIdle,1);
    assert(after.matching[1].socket.idleTimeoutAt>=after.matching[1].finishedAt);
  } finally {server?.kill();await rm(dir,{recursive:true,force:true});}
});

// The record is kept by time, not count (#686): a stalled request survives more traffic than the old 2,000-entry ring
// held, and when the hard bound does drop requests inside the window, the answer says so instead of looking empty.
test('the server record keeps the stalled request through heavy traffic and states when its window is truncated',async()=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'cad-agent-preview-bound-'));
  const servers=[];
  try {
    await writeFile(path.join(dir,'big.html'),Buffer.alloc(64*1024*1024,'x'));   // more than loopback buffers hold
    await writeFile(path.join(dir,'small.html'),'<p>small</p>');
    const start=async(...extra)=>{
      const server=spawn(process.execPath,[path.resolve(import.meta.dirname,'../../tools/site/preview-site.mjs'),'--dir',dir,'--port','0',...extra],{stdio:['pipe','pipe','inherit','ipc']});
      servers.push(server);
      const base=await new Promise((resolve,reject)=>{server.stdout.on('data',data=>{const url=String(data).match(/http:\/\/[\d.]+:\d+/);if(url)resolve(url[0]);});server.once('exit',code=>reject(new Error(`preview exited ${code}`)));});
      const ask=(pathname,since)=>new Promise(resolve=>{const id=Math.random();server.on('message',function on(m){if(m.id===id){server.off('message',on);resolve(m);}});server.send({type:'preview-evidence',id,path:pathname,since});});
      return {base,ask};
    };
    const scenario=async(...extra)=>{
      const {base,ask}=await start(...extra), since=Date.now(), port=new URL(base).port;
      // the stalled request: a client that never reads, so its response never finishes
      const stalled=net.connect(port,'127.0.0.1');stalled.pause();stalled.write('GET /big HTTP/1.1\r\nHost: x\r\n\r\n');
      const silent=net.connect(port,'127.0.0.1');   // connects and sends nothing
      while(!(await ask('/big',since)).matching[0]?.headersAt) await new Promise(r=>setTimeout(r,20));
      for(let i=0;i<2500;i+=50) await Promise.all(Array.from({length:50},()=>fetch(base+'/small').then(r=>r.text())));
      const answer={big:await ask('/big',since),small:await ask('/small',since)};
      stalled.destroy();silent.destroy();
      return answer;
    };
    // the default bound: everything from the window is still there
    const kept=await scenario();
    assert.equal(kept.big.coversWindow,true);
    assert.equal(kept.big.matching.length,1);assert.equal(kept.big.matching[0].finishedAt,undefined);
    assert.equal(kept.small.window.requests,2501,'the stalled request and all 2,500 since it');
    assert(kept.small.record.from<=kept.big.matching[0].receivedAt);assert.equal(kept.small.record.droppedByBound,0);
    assert(kept.big.window.socketsWithoutRequest.some(s=>s.requests===0&&s.bytesRead===0),'the silent socket is listed');
    assert(kept.small.matching.every(r=>r.socketBytesWritten>0&&r.finishedAt));
    // a bound below the traffic: finished requests go first, the stalled one stays, and coverage is reported lost
    const cut=await scenario('--record-max','1000');
    assert.equal(cut.big.coversWindow,false);assert(cut.big.record.droppedByBound>0);
    assert.equal(cut.big.matching.length,1,'the unfinished request is never the one dropped');
    assert(cut.small.window.requests<2501&&cut.small.record.requests<=1000);
  } finally {for(const server of servers)server.kill();await rm(dir,{recursive:true,force:true});}
});
