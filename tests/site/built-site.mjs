/** The built site the site tests read. With CAD_AGENT_SITE set (CI builds the site once per job, webkit.yml), that
 * folder, after checking it was built from HEAD and is not a --worktree draft, with the build log beside it as
 * <folder>.log; otherwise a fresh build of HEAD into a temporary folder, as before. Every caller only reads the folder. */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { previewRedirects, previewRoute } from '../../tools/site/preview-routes.mjs';
import { execFileSync, spawn } from 'node:child_process';
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
  return { ...result, ...await generatedHtmlIdentity(dir, file, signal) };
}

/** Hash only the HTML selected by the caller's own server routing. */
export async function generatedHtmlIdentity(dir, file, signal = AbortSignal.timeout(1500)) {
  const result = { file: file.slice(0, 300) };
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

/** Start the Pages preview with its failure-only evidence channel. Each server owns its query IDs. */
export async function startPreview(dir) {
  const server = spawn(process.execPath, ['tools/site/preview-site.mjs', '--dir', dir, '--port', '0'], { cwd: root, stdio: ['pipe', 'pipe', 'inherit', 'ipc'] });
  server.channel?.unref();   // a pending evidence query holds its own timer; the channel alone never keeps this test alive
  let evidenceQueries = 0;
  const base = await new Promise((ok, fail) => {
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/[\d.]+:\d+/); if (m) ok(m[0]); });
    server.once('error', fail);
    server.once('exit', c => fail(new Error(`preview server exited ${c}`)));
  });
  /** Ask the preview server for its record of `pathname` since `since` (tools/site/preview-site.mjs). Bounded by
   * `limit`: a server that cannot answer in time is itself the evidence, and never turns a failure into a hang. */
  async function serverEvidence(pathname, since, limit = 2000) {
    if (!server.connected) return { unavailable: 'the preview server has no IPC channel (exited or disconnected)' };
    const id = ++evidenceQueries, asked = Date.now();
    let timer, listener;
    try {
      return await new Promise(resolve => {
        listener = message => { if (message?.id === id) resolve({ ...message, id: undefined, answeredInMs: Date.now() - asked }); };
        server.on('message', listener);
        timer = setTimeout(() => resolve({ unavailable: `the preview server did not answer in ${limit} ms` }), limit);
        server.send({ type: 'preview-evidence', id, path: pathname, since }, error => {
          if (error) resolve({ unavailable: `could not ask the preview server: ${error.message}` });
        });
      });
    } finally { clearTimeout(timer); server.off('message', listener); }
  }
  return { server, base, serverEvidence };
}
