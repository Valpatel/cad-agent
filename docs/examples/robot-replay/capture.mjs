/** Capture the real standalone replay, with the existing Playwright context and Pillow extra. */
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '../../../tests/site/npm-context.mjs';
import {serveWebkit} from '../../../tests/webkit/webkit-server.mjs';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const bundle='software/cadagent/webkit/simulation/examples/two-link-arm';
const scratch=await mkdtemp(path.join(tmpdir(),'cad-replay-capture-'));
const server=await serveWebkit(new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]));
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
try{
  const page=await browser.newPage({viewport:{width:960,height:960},colorScheme:'dark',reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(server.url+'/kit/simulation/viewer.html');await page.waitForFunction(()=>document.body.dataset.ready==='1');
  await page.evaluate(async()=>{await document.fonts.ready;__replay.playback.seek(3.2);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
  const viewport=page.locator('.cad-viewer-viewport'),bounds=await viewport.boundingBox();
  await viewport.screenshot({path:path.join(scratch,'preview.png')});
  if(errors.length)throw new Error(errors.join('\n'));
  const output=path.join(root,bundle,'preview.webp');
  execFileSync(process.env.PYTHON||'python3',['-c','from PIL import Image; import sys; Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2],"WEBP",quality=88,method=6)',path.join(scratch,'preview.png'),output]);
  const sourcePaths=['docs/examples/robot-replay/capture.mjs',...['replay.js','viewer.js','scene.js','page.js','viewer.html','viewer.css','examples/two-link-arm/recording.json','examples/two-link-arm/receipt.json'].map(p=>'software/cadagent/webkit/simulation/'+p),...['model/stage.js','host/viewer-host.js','host/viewer-host.css','host/stage-controls.js','ui/theme.js','ui/theme.css'].map(p=>'software/cadagent/webkit/'+p)];
  const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
  const receipt={schema:'cad-agent.browser-capture/1',description:'Real recorded simulation at 3.2 seconds; dark theme, paused',browser:browser.version(),viewport:{width:960,height:960},capture:{width:Math.round(bounds.width),height:Math.round(bounds.height)},sources:Object.fromEntries(await Promise.all(sourcePaths.map(async p=>[p,sha(await readFile(path.join(root,p)))]))),artifact:{path:'preview.webp',sha256:sha(await readFile(output))}};
  await writeFile(path.join(root,bundle,'preview.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('Captured '+output);
}finally{await browser.close();await server.close();await rm(scratch,{recursive:true,force:true});}
