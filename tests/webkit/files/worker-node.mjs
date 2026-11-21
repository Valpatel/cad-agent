// Test-only Node adapter: run the shipped parser workers without a GPU/browser.
import { readFile } from 'node:fs/promises';
import { parentPort, workerData } from 'node:worker_threads';

const step = workerData.format === 'step';
const url = new URL('../../../software/cadagent/webkit/files/' +
  (step ? 'file-step-worker.js' : 'file-mesh-worker.js'), import.meta.url);

globalThis.self = { location: { href: url.href } };
globalThis.onmessage = null;
globalThis.postMessage = (data, transfer) => parentPort.postMessage(data, transfer);

if (step) {
  // The browser build fetches its WASM asset. Node's fetch does not read file: URLs.
  const wasm = new URL('../vendor/occt-import-js/occt-import-js.wasm', url);
  const fetch = globalThis.fetch;
  globalThis.fetch = async (input, options) => String(input) === wasm.href
    ? new Response(await readFile(wasm), { headers: { 'Content-Type': 'application/wasm' } })
    : fetch(input, options);
}
await import(url.href);
parentPort.on('message', (data) => globalThis.onmessage({ data }));
