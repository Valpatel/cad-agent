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
  // The single-file bundle inlines DOMPurify and KaTeX; the receipt names the versions inside it.
  const bundle = await readFile(path.join(vendor, 'mermaid/mermaid.min.js'), 'utf8');
  assert.ok(bundle.includes(`DOMPurify ${mermaid.bundled.dompurify}`) && bundle.includes(`"${mermaid.bundled.katex}"`));
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

/** The shipped 3MF worker's answer for these bytes: {error} or {model}, through the test-only Node adapter. */
async function viewer3MF(bytes) {
  const worker = new Worker(new URL('./webkit-file-worker-node.mjs', import.meta.url), { workerData: { format: '3mf' } });
  try {
    const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('the 3MF worker did not answer in 10 s')), 10000);
      worker.on('message', (m) => { if (m.error || m.model) { clearTimeout(timer); resolve(m); } });
      worker.once('error', reject);
      worker.postMessage({ format: '3mf', buffer, name: 'test.3mf', unit: 'millimeter' }, [buffer]);
    });
  } finally { await worker.terminate(); }
}

test('the file viewer rejects that archive before any parser runs', async () => {
  assert.equal((await viewer3MF(malformedZip64())).error, 'This 3MF uses an unsupported ZIP layout.');
});

/** A one-triangle 3MF: content types, relationships, the model, and optionally a thumbnail part. */
async function small3MF({ thumbnail = false, level = 6 } = {}) {
  const { zipSync, strToU8 } = await import(fflateURL);
  const model = '<?xml version="1.0"?><model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
    + '<resources><object id="1" type="model"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/>'
    + '<vertex x="0" y="10" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>'
    + '</resources><build><item objectid="1"/></build></model>';
  const files = {
    '[Content_Types].xml': strToU8('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'),
    '_rels/.rels': strToU8('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'),
    '3D/3dmodel.model': [strToU8(model), { level }],
  };
  if (thumbnail) files['Metadata/thumbnail.png'] = [strToU8('x'.repeat(4000)), { level: 6 }];
  return zipSync(files);
}

/** Overwrite the first bytes of `name`'s compressed data, or its compression method, in place. */
function damage(zip, name, { method } = {}) {
  const d = new DataView(zip.buffer, zip.byteOffset, zip.byteLength), want = new TextEncoder().encode(name);
  for (let at = 0; at + 30 < zip.length; at++) {
    if (d.getUint32(at, true) !== 0x04034b50) continue;
    const nameLength = d.getUint16(at + 26, true), extra = d.getUint16(at + 28, true);
    if (nameLength !== want.length || !want.every((b, i) => zip[at + 30 + i] === b)) continue;
    if (method !== undefined) {   // the local header and the central directory both name the method
      d.setUint16(at + 8, method, true);
      for (let c = 0; c + 46 < zip.length; c++) if (d.getUint32(c, true) === 0x02014b50 && d.getUint32(c + 42, true) === at) d.setUint16(c + 10, method, true);
    } else zip.fill(0xff, at + 30 + nameLength + extra, at + 30 + nameLength + extra + 4);
    return zip;
  }
  throw new Error('no local header for ' + name);
}

test('a damaged 3MF shows the generic message, not fflate or loader internals', async () => {
  assert.equal((await viewer3MF(await small3MF())).model?.triangles, 1, 'the undamaged fixture reads');
  const generic = 'The model file could not be decoded.';
  // fflate 0.8 throws Error objects ("invalid block type", "unknown compression type 12") where 0.6 threw strings.
  assert.equal((await viewer3MF(damage(await small3MF(), '3D/3dmodel.model'))).error, generic);
  assert.equal((await viewer3MF(damage(await small3MF(), '3D/3dmodel.model', { method: 12 }))).error, generic);
  // A damaged part beside the model passes the worker's model-only unzip; the loader's own unzip then fails.
  assert.equal((await viewer3MF(damage(await small3MF({ thumbnail: true }), 'Metadata/thumbnail.png'))).error, generic);
});

test('unzipSync keeps the interface the 3MF worker relies on, and honours its model filter', async () => {
  const { zipSync, unzipSync, strToU8, strFromU8 } = await import(fflateURL);
  const zip = zipSync({ '3D/3dmodel.model': strToU8('<model unit="millimeter"/>'), '_rels/.rels': strToU8('<Relationships/>') });
  assert.deepEqual(Object.keys(unzipSync(zip)).sort(), ['3D/3dmodel.model', '_rels/.rels']);
  const models = unzipSync(zip, { filter: (file) => /\.model$/i.test(file.name) });
  assert.deepEqual(Object.keys(models), ['3D/3dmodel.model']);
  assert.equal(strFromU8(models['3D/3dmodel.model']), '<model unit="millimeter"/>');
});
