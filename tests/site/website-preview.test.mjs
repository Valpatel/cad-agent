import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
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
