import { createModelHost, createFileHost } from './adapters.js';
const assembly = document.querySelector('#assembly'), original = document.querySelector('#original');
assembly.replaceChildren(); original.replaceChildren();
const viewers = [
  createModelHost(assembly, { title: 'Assembly document', manifestUrl: new URL('./example.json', import.meta.url).href }),
  createFileHost(original, { title: 'Original STL', file: new URL('./example.stl', import.meta.url).href }),
];
addEventListener('pagehide', () => viewers.forEach(viewer => viewer.dispose()), { once: true });
