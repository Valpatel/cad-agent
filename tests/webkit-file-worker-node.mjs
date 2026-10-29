// Test-only Node adapter: run the shipped parser workers without a GPU/browser.
import {parentPort,workerData} from 'node:worker_threads';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname} from 'node:path';
import vm from 'node:vm';
const url=new URL('../src/cadagent/webkit/'+(workerData.format==='step'?'file-step-worker.js':'file-mesh-worker.js'),import.meta.url);
globalThis.self={location:{href:url.href}};globalThis.onmessage=null;
globalThis.postMessage=(data,transfer)=>parentPort.postMessage(data,transfer);
globalThis.require=createRequire(import.meta.url);
globalThis.importScripts=path=>{globalThis.__dirname=dirname(fileURLToPath(path));vm.runInThisContext(readFileSync(new URL(path),'utf8'),{filename:fileURLToPath(path)});};
await import(url.href);
parentPort.on('message',data=>globalThis.onmessage({data}));
