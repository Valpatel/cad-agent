/** Serve dist/ the way Cloudflare Pages does, for local preview and the site tests.
 *
 *   node tools/site/preview-site.mjs [--dir dist] [--port 8781] [--host 127.0.0.1]
 *
 * Pretty URLs (/docs/toolkit serves docs/toolkit.html; /x.html redirects to /x), 404.html with status 404, and the
 * response headers from dist/_headers (so the Content-Security-Policy is exercised before a deploy) and the redirects in
 * dist/_redirects (exact paths, as moved pages use them). Listens on
 * loopback only unless --host says otherwise.
 */
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const dir = path.resolve(arg('--dir', path.join(import.meta.dirname, '../..', 'dist')));
const port = Number(arg('--port', 8781)), host = arg('--host', '127.0.0.1');
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.woff2': 'font/woff2',
  '.wasm': 'application/wasm', '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
  '.xml': 'application/xml', '.step': 'model/step', '.stl': 'model/stl', '.glb': 'model/gltf-binary' };

/** Parse a Cloudflare Pages _headers file into [{ pattern: RegExp, headers: [[name, value]] }]. */
export function parseHeaders(text) {
  const rules = [];
  for (const line of text.split('\n')) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    if (!/^\s/.test(line)) {
      const re = '^' + line.trim().replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/:\w+/g, '[^/]+') + '$';
      rules.push({ pattern: new RegExp(re), headers: [] });
    } else if (rules.length) {
      const i = line.indexOf(':');
      rules.at(-1).headers.push([line.slice(0, i).trim(), line.slice(i + 1).trim()]);
    }
  }
  return rules;
}
/** Headers for a path; a header set by several matching rules gets the values joined, as Pages does. */
export function headersFor(rules, pathname) {
  const out = {};
  for (const r of rules) if (r.pattern.test(pathname))
    for (const [k, v] of r.headers) { const key = k.toLowerCase(); out[key] = out[key] ? `${out[key]}, ${v}` : v; }
  return out;
}

const exists = async f => { try { return (await stat(f)).isFile(); } catch { return false; } };
const rules = parseHeaders(await readFile(path.join(dir, '_headers'), 'utf8').catch(() => ''));
// _redirects, as Pages reads it for exact paths: "<from> <to> [status]" per line.
const redirects = new Map((await readFile(path.join(dir, '_redirects'), 'utf8').catch(() => '')).split('\n')
  .map(l => l.trim().split(/\s+/)).filter(p => p.length >= 2 && p[0].startsWith('/')).map(([from, to, code]) => [from, [to, Number(code) || 302]]));

/** The server's own record of recent requests and sockets, for a test that started it with an IPC channel (#686).
 * A browser test that sees a page request pending for 30 s cannot tell whether this server never received it,
 * received it and did not answer, or answered and the browser did not take the answer; this record says which.
 * Bookkeeping only: timestamps into fixed-size rings, a sha256 of each HTML body served, and a 100 ms interval
 * timer (unreferenced) that notes event-loop lag. Times are Date.now() epoch milliseconds, the clock the test
 * process reads too on the same host. Answers {type: 'preview-evidence', id, path, since} on the channel. */
const RING = 2000;
const record = { requests: [], sockets: [], lag: [], nextRequest: 1, nextSocket: 1, open: new Set() };
const ring = (list, item) => { list.push(item); if (list.length > RING) list.shift(); return item; };
const slot = Symbol('preview record');
function track(server) {
  server.on('connection', socket => {
    const s = ring(record.sockets, { id: record.nextSocket++, openedAt: Date.now(), remotePort: socket.remotePort, requests: 0 });
    record.open.add(s);
    socket[slot] = s;
    socket.on('timeout', () => { s.idleTimeoutAt = Date.now(); });   // Node's keep-alive close of an idle socket
    socket.on('close', hadError => { record.open.delete(s); Object.assign(s, { closedAt: Date.now(), hadError, bytesRead: socket.bytesRead }); });
  });
  // Before the route handler, so its first writeHead (a redirect is written synchronously) is timed too.
  server.prependListener('request', (req, res) => {
    const s = req.socket[slot], previous = s?.lastFinishedAt;
    const r = req[slot] = ring(record.requests, { id: record.nextRequest++, receivedAt: Date.now(), method: req.method,
      path: new URL(req.url, 'http://x').pathname, socket: s?.id, onSocket: s ? ++s.requests : 0,
      idleBeforeMs: previous ? Date.now() - previous : undefined });
    const writeHead = res.writeHead;
    res.writeHead = function (status, ...rest) { Object.assign(r, { status, headersAt: Date.now() }); return writeHead.call(this, status, ...rest); };
    res.on('finish', () => { r.finishedAt = Date.now(); if (s) s.lastFinishedAt = r.finishedAt; });
    res.on('close', () => { r.closedAt = Date.now(); if (!res.writableFinished) r.aborted = true; });
  });
  let expected = Date.now() + 100;
  setInterval(() => {
    const now = Date.now(), late = now - expected;
    if (late >= 20) ring(record.lag, { at: now, lateMs: late });
    expected = now + 100;
  }, 100).unref();
  process.on('message', message => {
    if (message?.type !== 'preview-evidence') return;
    const since = Number(message.since) || 0, inWindow = r => r.receivedAt >= since;
    const windowed = record.requests.filter(inWindow);
    process.send({ id: message.id, now: Date.now(), pid: process.pid,
      clock: 'Date.now() epoch ms in the preview server process',
      keepAlive: { keepAliveTimeout: server.keepAliveTimeout, keepAliveTimeoutBuffer: server.keepAliveTimeoutBuffer,
        headersTimeout: server.headersTimeout, requestTimeout: server.requestTimeout, maxRequestsPerSocket: server.maxRequestsPerSocket },
      openSockets: record.open.size,
      recordedFrom: record.requests[0]?.receivedAt ?? null, recordedRequests: record.requests.length,
      matching: record.requests.filter(r => r.path === message.path && inWindow(r)).slice(-10)
        .map(r => ({ ...r, socket: record.sockets.find(s => s.id === r.socket) ?? r.socket })),
      window: { requests: windowed.length, unanswered: windowed.filter(r => !r.headersAt).slice(-10),
        unfinished: windowed.filter(r => !r.finishedAt).length,
        socketsOpened: record.sockets.filter(s => s.openedAt >= since).length,
        socketsClosedIdle: record.sockets.filter(s => s.idleTimeoutAt >= since).length },
      lag: { samplesOver20ms: record.lag.filter(l => l.at >= since).slice(-20),
        maxMs: Math.max(0, ...record.lag.filter(l => l.at >= since).map(l => l.lateMs)) } });
  });
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  let pathname;
  try { pathname = decodeURIComponent(url.pathname); } catch { res.writeHead(400).end(); return; }   // e.g. /%
  // No NUL, no dot segments, no backslash: '/\\host' in a redirect would send the browser to another host.
  if (/[\0\\]/.test(pathname) || path.posix.normalize(pathname) !== pathname) { res.writeHead(400).end(); return; }
  if (redirects.has(pathname)) { const [to, code] = redirects.get(pathname); res.writeHead(code, { location: to + url.search }).end(); return; }
  if (pathname.endsWith('.html')) {                               // Pages drops .html with a redirect
    const pretty = pathname.endsWith('/index.html') ? pathname.slice(0,-'index.html'.length) : pathname.replace(/\.html$/, '');
    res.writeHead(308, { location: pretty + url.search }).end(); return;
  }
  const candidates = pathname.endsWith('/') ? [pathname + 'index.html'] : [pathname, pathname + '.html', pathname + '/index.html'];
  let file = null;
  for (const c of candidates) if (await exists(path.join(dir, c))) { file = c; break; }
  // Directory applications resolve their own modules beside index.html. Keep the trailing slash, including
  // requests for the bare directory; otherwise a relative ./app.mjs incorrectly resolves one level above it.
  if(file === pathname+'/index.html') {res.writeHead(308,{location:pathname+'/'+url.search}).end();return;}
  const status = file ? 200 : 404;
  file ??= '/404.html';
  const body = await readFile(path.join(dir, file)).catch(() => Buffer.from('Not found'));
  const r = req[slot];
  if (r) Object.assign(r, { file, readAt: Date.now(), bytes: body.length,
    sha256: file.endsWith('.html') ? createHash('sha256').update(body).digest('hex') : undefined });
  res.writeHead(status, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream', ...headersFor(rules, pathname) });
  res.end(req.method === 'HEAD' ? undefined : body);
});
if (process.argv[1] === import.meta.filename) {
  if (process.send) track(server);
  server.listen(port, host, () => console.log(`Serving ${path.relative(process.cwd(), dir) || dir} at http://${host}:${server.address().port}/`));
}
export { server };
