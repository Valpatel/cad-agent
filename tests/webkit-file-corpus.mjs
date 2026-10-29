// Parse a bounded manifest of already-published originals using the actual workers.
// Run large corpora on a compute host; see docs/file-viewer.md.
import {readFile,writeFile} from 'node:fs/promises';
import {Worker} from 'node:worker_threads';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
const [manifestPath,root,out]=process.argv.slice(2);if(!out)throw new Error('Usage: node tests/webkit-file-corpus.mjs manifest.json corpus-root results.json');
const manifest=JSON.parse(await readFile(manifestPath,'utf8')),results=[];
for(const entry of manifest.files){
  const bytes=await readFile(path.join(root,entry.path)),sha256=createHash('sha256').update(bytes).digest('hex');if(sha256!==entry.sha256)throw new Error('Corpus changed: '+entry.path);
  const format=/\.(?:step|stp)$/i.test(entry.path)?'step':entry.path.split('.').pop().toLowerCase(),start=performance.now();let worker;
  try{
    worker=new Worker(new URL('./webkit-file-worker-node.mjs',import.meta.url),{workerData:{format}});
    const buffer=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
    const model=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Parser exceeded120s')),120000);const finish=(fn,value)=>{clearTimeout(timer);fn(value);};worker.on('error',e=>finish(reject,e));worker.on('message',data=>{if(data.error)finish(reject,new Error(data.error));else if(data.model)finish(resolve,data.model);});worker.postMessage({format,buffer,name:entry.path,unit:'millimeter'},[buffer]);});
    results.push({path:entry.path,sha256,bytes:bytes.length,triangles:model.triangles,meshes:model.meshes.length,bounds:model.meshes.map(m=>m.bounds),warnings:model.warnings,elapsedMs:Math.round(performance.now()-start),passed:true});
  }catch(error){results.push({path:entry.path,sha256,elapsedMs:Math.round(performance.now()-start),passed:false,error:error.message});}
  finally{await worker?.terminate();}
  console.log(JSON.stringify({index:results.length,total:manifest.files.length,...results.at(-1),bounds:undefined}));
  await writeFile(out,JSON.stringify({manifestSha256:createHash('sha256').update(await readFile(manifestPath)).digest('hex'),timestamp:new Date().toISOString(),node:process.version,passed:results.every(r=>r.passed),results},null,2));
}
if(results.some(r=>!r.passed))process.exitCode=1;
