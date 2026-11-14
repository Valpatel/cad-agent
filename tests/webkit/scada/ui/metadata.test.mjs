import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {buildScadaMetadata} from '../../../../tools/webkit/scada/ui/build-metadata.mjs';
import {SCADA_COMPONENTS, SCADA_CATEGORIES} from '../../../../software/cadagent/webkit/scada/ui/src/catalog/registry.mjs';

test('generated UI metadata agrees with canonical contracts without timestamps or website output',async()=>{
  assert.deepEqual(await buildScadaMetadata({check:true}),{checked:1,changed:[]});
  const metadata=JSON.parse(await readFile(new URL('../../../../software/cadagent/webkit/scada/ui/metadata/components.json',import.meta.url),'utf8'));
  const manifest=JSON.parse(await readFile(new URL('../../../../software/cadagent/webkit/scada/ui/package.json',import.meta.url),'utf8'));
  assert.deepEqual(metadata.package,{name:manifest.name,version:manifest.version});
  assert.equal(metadata.schemaVersion,1);
  assert.deepEqual(metadata.components,SCADA_COMPONENTS);
  assert.deepEqual(metadata.categories,SCADA_CATEGORIES);
  assert.equal(metadata.generatedAt,undefined,'metadata has no wall-clock timestamp');
});

test('UI metadata checks do not create missing outputs or overwrite edited files',async t=>{
  const root=await mkdtemp(join(tmpdir(),'scada-ui-metadata-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const outputDirectory=join(root,'metadata'),target=join(outputDirectory,'components.json');
  await assert.rejects(buildScadaMetadata({check:true,outputDirectory}),/stale/);
  await assert.rejects(stat(outputDirectory),{code:'ENOENT'});
  await buildScadaMetadata({outputDirectory});
  const original=await readFile(target);
  await writeFile(target,'{"stale":true}\n');
  await assert.rejects(buildScadaMetadata({check:true,outputDirectory}),/stale/);
  assert.equal(await readFile(target,'utf8'),'{"stale":true}\n');
  await buildScadaMetadata({outputDirectory});
  assert.deepEqual(await readFile(target),original);
  assert.deepEqual(await buildScadaMetadata({check:true,outputDirectory}),{checked:1,changed:[]});
});
