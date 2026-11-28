/** The built site the site tests read. With CAD_AGENT_SITE set (CI builds the site once per job, webkit.yml), that
 * folder, after checking it was built from HEAD and is not a --worktree draft, with the build log beside it as
 * <folder>.log; otherwise a fresh build of HEAD into a temporary folder, as before. Every caller only reads the folder. */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { previewRedirects, previewRoute } from '../../tools/site/preview-routes.mjs';
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
    // A --worktree draft records HEAD too, but holds uncommitted edits: the tests check what HEAD publishes.
    if (/\(draft: working tree\)/.test(log)) throw new Error(`CAD_AGENT_SITE=${given} is a --worktree draft, not HEAD: rebuild it without --worktree, or unset CAD_AGENT_SITE to build here`);
    if (stdio === 'inherit') console.log(`Using the site built in ${given} (CAD_AGENT_SITE)`);
    return { dir, log, done: async () => {} };
  }
  const tmp = await mkdtemp(path.join(os.tmpdir(), prefix));
  const dir = path.join(tmp, 'site');
  const log = String(execFileSync(process.execPath, ['tools/site/build-site.mjs', '--out', dir], { cwd: root, stdio: ['ignore', stdio, 'inherit'] }) ?? '');
  return { dir, log, done: () => rm(tmp, { recursive: true, force: true }) };
}

/** Inspect the immutable build's requested HTML after a failure, even if the preview never received a request.
 * Only the public file, byte count, digest and source revision enter the receipt. No HTTP request is made. */
export async function generatedDocument(dir, previewOrigin, target) {
  const url = new URL(target);
  if (url.origin !== previewOrigin) return { unavailable: 'requested URL belongs to another origin' };
  const signal = AbortSignal.timeout(1500);
  let revision = null;
  try {
    const version = JSON.parse(await readFile(path.join(dir, 'version.json'), { encoding: 'utf8', signal }));
    if (typeof version.revision === 'string' && /^[0-9a-f]{40}$/.test(version.revision)) revision = version.revision;
  } catch { /* retain the HTML identity even when the build metadata is missing */ }
  const result = revision ? { revision } : { revision: null, revisionUnavailable: 'build revision missing or invalid' };
  let route;
  try { route = await previewRoute(dir, url.pathname, await previewRedirects(dir, { signal })); }
  catch { return { ...result, unavailable: 'preview routing could not be inspected' }; }
  const { status, file, location } = route;
  result.status = status;
  if (location !== undefined) return { ...result, unavailable: 'requested route redirects without an HTML body' };
  if (!file?.endsWith('.html')) return { ...result, unavailable: 'requested route selects no generated HTML' };
  result.file = file.slice(0, 300);
  const hash = createHash('sha256');
  let bytes = 0;
  try {
    for await (const chunk of createReadStream(path.join(dir, file), { signal })) {
      hash.update(chunk);
      bytes += chunk.length;
    }
    return { ...result, bytes, sha256: hash.digest('hex') };
  } catch {
    return { ...result, unavailable: signal.aborted ? 'generated HTML read exceeded its deadline' : 'selected HTML could not be read' };
  }
}
