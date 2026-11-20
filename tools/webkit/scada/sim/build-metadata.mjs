#!/usr/bin/env node
import {SIM} from '../paths.mjs';
/** Serialize the public model registries for portable consumers. --check never
 * writes files or creates directories, and reports every stale output. */
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  MODEL_DESCRIPTORS,
  V2_MODEL_DESCRIPTORS,
  V2_VARIANT_DESCRIPTORS,
  V2_MODEL_FAMILIES,
} from '../../../../software/cadagent/webkit/scada/sim/src/index.mjs';

const packageRoot = SIM;
const defaultOutputDirectory = resolve(packageRoot, 'metadata');
const format = 'scada-placeholder-model-registry';

async function currentText(path) {
  try { return await readFile(path, 'utf8'); }
  catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

export async function buildScadaModelMetadata({check = false, outputDirectory = defaultOutputDirectory} = {}) {
  const outputs = [
    ['model-registry.json', {format, version:1, models:MODEL_DESCRIPTORS}],
    ['model-registry-v2.json', {
      format,
      version:2,
      families:V2_MODEL_FAMILIES,
      models:V2_MODEL_DESCRIPTORS,
      variants:V2_VARIANT_DESCRIPTORS,
    }],
  ];
  const changed = [];
  for (const [filename, registry] of outputs) {
    const path = resolve(outputDirectory, filename);
    const next = `${JSON.stringify(registry, null, 2)}\n`;
    if (await currentText(path) === next) continue;
    changed.push(filename);
    if (!check) {
      await mkdir(outputDirectory, {recursive:true});
      await writeFile(path, next);
    }
  }
  if (check && changed.length) {
    throw new Error(`Generated SCADA model metadata is stale: ${changed.join(', ')}. Run npm --prefix tools/webkit/scada run build:metadata.`);
  }
  return {checked:outputs.length, changed};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.some(arg => arg !== '--check')) throw new Error('Usage: node tools/webkit/scada/sim/build-metadata.mjs [--check]');
    const result = await buildScadaModelMetadata({check:args.includes('--check')});
    process.stdout.write(`${args.includes('--check') ? 'Verified' : 'Synced'} ${result.checked} model registries${result.changed.length ? ` (${result.changed.length} updated)` : ''}.\n`);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
