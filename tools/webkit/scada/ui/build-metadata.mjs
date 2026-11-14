#!/usr/bin/env node
import {UI} from '../paths.mjs';
/** Serialize the UI contract without importing artwork or choosing host URLs. */
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {SCADA_COMPONENTS, SCADA_CATEGORIES} from '../../../../software/cadagent/webkit/scada/ui/src/catalog/registry.mjs';

const packageRoot = UI;

export async function buildScadaMetadata({check = false, outputDirectory = resolve(packageRoot, 'metadata')} = {}) {
  const manifest = JSON.parse(await readFile(resolve(packageRoot, 'package.json'), 'utf8'));
  const path = resolve(outputDirectory, 'components.json');
  const next = `${JSON.stringify({schemaVersion:1, package:{name:manifest.name, version:manifest.version}, categories:SCADA_CATEGORIES, components:SCADA_COMPONENTS}, null, 2)}\n`;
  let previous = null;
  try { previous = await readFile(path, 'utf8'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const changed = previous === next ? [] : ['components.json'];
  if (check && changed.length) throw new Error('SCADA metadata is stale; run npm --prefix tools/webkit/scada run build:metadata from the repository root.');
  if (!check && changed.length) {
    await mkdir(outputDirectory, {recursive:true});
    await writeFile(path, next);
  }
  return {checked:1, changed};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.some(arg => arg !== '--check')) throw new Error('Usage: node tools/webkit/scada/ui/build-metadata.mjs [--check]');
  const result = await buildScadaMetadata({check:args.includes('--check')});
  process.stdout.write(`${args.includes('--check') ? 'Verified' : 'Updated'} UI metadata (${result.changed.length} changed).\n`);
}
