/** The web kit's vendored libraries match their receipts, and the fflate copy has the ZIP64 fix (#152).
 * Receipts: vendor/mermaid/SOURCE.json and vendor/file-viewer-sources.json record each file's SHA-256 and source. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');
const vendor = path.join(root, 'src/cadagent/webkit/vendor');
const json = async (rel) => JSON.parse(await readFile(path.join(vendor, rel), 'utf8'));
const sha256 = async (file) => createHash('sha256').update(await readFile(file)).digest('hex');
const fflateURL = pathToFileURL(path.join(vendor, 'file-parsers/fflate.module.js')).href;

test('every vendored file matches the SHA-256 in its receipt', async () => {
  const mermaid = await json('mermaid/SOURCE.json'), viewer = await json('file-viewer-sources.json');
  for (const [rel, want] of Object.entries(mermaid.files)) assert.equal(await sha256(path.join(vendor, 'mermaid', rel)), want, rel);
  for (const [rel, want] of Object.entries(viewer.sha256)) assert.equal(await sha256(path.join(vendor, rel)), want, rel);
  assert.ok(viewer.sha256['file-parsers/fflate.module.js'] && viewer.sha256['file-parsers/FFLATE-LICENSE.txt']);
});

test('receipts, notices and the source URLs name the same versions', async () => {
  const mermaid = await json('mermaid/SOURCE.json'), { fflate } = await json('file-viewer-sources.json');
  assert.equal(mermaid.source, `https://registry.npmjs.org/mermaid/-/mermaid-${mermaid.version}.tgz`);
  assert.equal(fflate.source, `https://registry.npmjs.org/fflate/-/fflate-${fflate.version}.tgz`);
  const notices = await readFile(path.join(root, 'THIRD_PARTY_NOTICES.md'), 'utf8');
  assert.match(notices, new RegExp(`^\\| Mermaid \\| MIT \\| ${mermaid.version.replaceAll('.', '\\.')} \\|`, 'm'));
  assert.match(notices, new RegExp(`^\\| fflate .*\\| MIT \\| ${fflate.version.replaceAll('.', '\\.')}, from npm \\|`, 'm'));
  const viewerNotices = await readFile(path.join(vendor, 'FILE-VIEWER-NOTICES.md'), 'utf8');
  assert.ok(viewerNotices.includes(`## ZIP reader: fflate ${fflate.version}`) && viewerNotices.includes(fflate.source));
  // The one local change to the three.js 3MF loader: it imports the adjacent fflate copy, not three's bundled one.
  const loader = await readFile(path.join(vendor, 'file-parsers/3MFLoader.js'), 'utf8');
  assert.match(loader, /^import \* as fflate from '\.\/fflate\.module\.js';$/m);
});

/** A ZIP whose only central-directory entry declares compressed size 0xFFFFFFFF (the ZIP64 sentinel) but has no ZIP64
 * extra field, behind a valid ZIP64 end-of-directory record and locator: the GHSA-px8p-9vwx-vf98 shape. fflate 0.6.9's
 * unzipSync loops forever on it; 0.8.3 throws "invalid zip data". */
function malformedZip64() {
  const bytes = new Uint8Array(176), d = new DataView(bytes.buffer);
  const u16 = (at, v) => d.setUint16(at, v, true), u32 = (at, v) => d.setUint32(at, v, true);
  u32(0, 0x04034b50); u16(4, 20); u16(26, 1); bytes[30] = 0x61;                      // local header, name "a", no data
  u32(31, 0x02014b50); u16(35, 20); u16(37, 45); u32(51, 0xffffffff); u16(59, 1);       // central entry: csize = sentinel
  bytes[77] = 0x61;                                                                  // its name; extra field length 0
  u32(78, 0x06064b50); u32(82, 44); u16(90, 45); u16(92, 45);                          // ZIP64 end of central directory
  u32(102, 1); u32(110, 1); u32(118, 47); u32(126, 31);                              // 1 entry, 47-byte directory at 31
  u32(134, 0x07064b50); u32(142, 78); u32(150, 1);                                   // ZIP64 locator -> record at 78
  u32(154, 0x06054b50); u16(162, 1); u16(164, 1); u32(166, 47); u32(170, 0xffffffff); // EOCD: offset in the ZIP64 record
  return bytes;
}

/** Run `unzipSync` from the vendored module in a worker, so a regression to the infinite loop fails the test on time. */
function unzipInWorker(bytes, ms = 5000) {
  const source = `import {workerData, parentPort} from 'node:worker_threads';
    const {unzipSync} = await import(workerData.module);
    try { const files = unzipSync(workerData.bytes); parentPort.postMessage({files: Object.keys(files)}); }
    catch (e) { parentPort.postMessage({error: e.message, code: e.code}); }`;
  const worker = new Worker(new URL('data:text/javascript,' + encodeURIComponent(source)), { workerData: { module: fflateURL, bytes } });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { worker.terminate(); reject(new Error(`unzipSync still running after ${ms} ms`)); }, ms);
    worker.once('message', (m) => { clearTimeout(timer); worker.terminate(); resolve(m); });
    worker.once('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

test('the vendored unzipSync rejects a malformed ZIP64 directory instead of looping (GHSA-px8p-9vwx-vf98)', async () => {
  assert.deepEqual(await unzipInWorker(malformedZip64()), { error: 'invalid zip data', code: 13 });
});

test('the file viewer rejects that archive before any parser runs', async () => {
  const worker = new Worker(new URL('./webkit-file-worker-node.mjs', import.meta.url), { workerData: { format: '3mf' } });
  try {
    const buffer = malformedZip64().buffer;
    const reply = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('the 3MF worker did not answer in 5 s')), 5000);
      worker.on('message', (m) => { if (m.error || m.model) { clearTimeout(timer); resolve(m); } });
      worker.once('error', reject);
      worker.postMessage({ format: '3mf', buffer, name: 'malformed.3mf', unit: 'millimeter' }, [buffer]);
    });
    assert.equal(reply.error, 'This 3MF uses an unsupported ZIP layout.');
  } finally { await worker.terminate(); }
});

test('unzipSync keeps the interface the 3MF worker relies on, and honours its model filter', async () => {
  const { zipSync, unzipSync, strToU8, strFromU8 } = await import(fflateURL);
  const zip = zipSync({ '3D/3dmodel.model': strToU8('<model unit="millimeter"/>'), '_rels/.rels': strToU8('<Relationships/>') });
  assert.deepEqual(Object.keys(unzipSync(zip)).sort(), ['3D/3dmodel.model', '_rels/.rels']);
  const models = unzipSync(zip, { filter: (file) => /\.model$/i.test(file.name) });
  assert.deepEqual(Object.keys(models), ['3D/3dmodel.model']);
  assert.equal(strFromU8(models['3D/3dmodel.model']), '<model unit="millimeter"/>');
});
