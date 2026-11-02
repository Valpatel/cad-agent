/** The built site the site tests read. With CAD_AGENT_SITE set (CI builds the site once per job, webkit.yml), that
 * folder, after checking it was built from HEAD with the build log beside it as <folder>.log; otherwise a fresh build
 * of HEAD into a temporary folder, as before. Every caller only reads the folder. */
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');

/** { dir, log, done }: the built site, its build's output, and a function that removes it if this call built it.
 * `prefix` names the temporary folder; `stdio: 'inherit'` shows the build's output as it runs (the log is then ''). */
export async function builtSite(prefix, { stdio = 'pipe' } = {}) {
  const given = process.env.CAD_AGENT_SITE;
  if (given) {
    const dir = path.resolve(given);
    const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root }).toString().trim();
    const { revision } = JSON.parse(await readFile(path.join(dir, 'version.json'), 'utf8'));
    if (revision !== head) throw new Error(`CAD_AGENT_SITE=${given} was built from ${revision}, not HEAD (${head}): rebuild it, or unset CAD_AGENT_SITE to build here`);
    const log = await readFile(`${dir}.log`, 'utf8');
    if (stdio === 'inherit') console.log(`Using the site built in ${given} (CAD_AGENT_SITE)`);
    return { dir, log, done: async () => {} };
  }
  const tmp = await mkdtemp(path.join(os.tmpdir(), prefix));
  const dir = path.join(tmp, 'site');
  const log = String(execFileSync(process.execPath, ['tools/build-site.mjs', '--out', dir], { cwd: root, stdio: ['ignore', stdio, 'inherit'] }) ?? '');
  return { dir, log, done: () => rm(tmp, { recursive: true, force: true }) };
}
