import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {REPO,UI,SIM} from '../../../../tools/webkit/scada/paths.mjs';

test('source and offline simulation consumers receive the complete MIT grant without changing private publication policy',async()=>{
  const license=await readFile(join(REPO,'LICENSE'));
  assert.match(license.toString(),/^MIT License\n/);
  for(const owner of [join(SIM,'..'),UI,SIM]) assert.deepEqual(await readFile(join(owner,'LICENSE.txt')),license);
  const source=JSON.parse(await readFile(join(SIM,'../SOURCE.json'),'utf8'));
  assert.equal(source.packageTerms.license,'MIT');
  assert.equal(source.sourceRevision,'e4fd8965b5ac7058a88ca6924cf7ef2cf5d2dbac');
  assert.equal(source.sourceInventorySha256,'137c61c250db805bc54949300cbc12cf7788a4f688c79be4dbe8c3a8c5f6aca4','original import identity remains historical evidence');
  const temp=await mkdtemp(join(tmpdir(),'scada-sim-package-'));
  const run=(args,cwd)=>execFileSync('npm',args,{cwd,encoding:'utf8',timeout:30000,env:{...process.env,npm_config_cache:join(temp,'cache'),npm_config_update_notifier:'false'}});
  try {
    const packed=JSON.parse(run(['pack','--offline','--ignore-scripts','--json','--pack-destination',temp],SIM))[0];
    const consumer=join(temp,'consumer');await mkdir(consumer);
    await writeFile(join(consumer,'package.json'),JSON.stringify({private:true,type:'module'}));
    run(['install','--offline','--ignore-scripts','--no-audit','--no-fund','--no-package-lock',join(temp,packed.filename)],consumer);
    const installed=join(consumer,'node_modules/@valpatel/scada-sim');
    const manifest=JSON.parse(await readFile(join(installed,'package.json'),'utf8'));
    assert.equal(manifest.private,true);assert.equal(manifest.license,'MIT');
    assert.deepEqual(await readFile(join(installed,'LICENSE.txt')),license,'license bytes travel inside the actual npm artifact');
    assert.equal(manifest.dependencies,undefined,'no runtime download is introduced');
    const result=execFileSync(process.execPath,['--input-type=module','-e',"import {PlaceholderSystemModel} from '@valpatel/scada-sim'; console.log(typeof PlaceholderSystemModel)"],{cwd:consumer,encoding:'utf8'});
    assert.equal(result.trim(),'function','the separately installed model API still resolves');
  } finally {await rm(temp,{recursive:true,force:true});}
});
