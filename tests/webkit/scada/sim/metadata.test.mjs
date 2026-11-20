import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {buildScadaModelMetadata} from '../../../../tools/webkit/scada/sim/build-metadata.mjs';

test('model metadata checks report stale and missing outputs without creating or rewriting them', async () => {
  const root = await mkdtemp(join(tmpdir(), 'scada-model-metadata-'));
  const outputDirectory = join(root, 'metadata');
  try {
    await assert.rejects(buildScadaModelMetadata({check:true, outputDirectory}), /model-registry\.json, model-registry-v2\.json/);
    await assert.rejects(stat(outputDirectory), {code:'ENOENT'});

    assert.equal((await buildScadaModelMetadata({outputDirectory})).changed.length, 2);
    const v1Path = join(outputDirectory, 'model-registry.json');
    const v2Path = join(outputDirectory, 'model-registry-v2.json');
    const original = await readFile(v1Path, 'utf8');
    await writeFile(v1Path, '{"stale":true}\n');
    await rm(v2Path);

    await assert.rejects(buildScadaModelMetadata({check:true, outputDirectory}), /model-registry\.json, model-registry-v2\.json/);
    assert.equal(await readFile(v1Path, 'utf8'), '{"stale":true}\n');
    await assert.rejects(readFile(v2Path), {code:'ENOENT'});

    assert.equal((await buildScadaModelMetadata({outputDirectory})).changed.length, 2);
    assert.equal(await readFile(v1Path, 'utf8'), original);
    assert.deepEqual(await buildScadaModelMetadata({check:true, outputDirectory}), {checked:2, changed:[]});
  } finally {
    await rm(root, {recursive:true, force:true});
  }
});
