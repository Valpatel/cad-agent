import {createRequire} from 'node:module';
const require = createRequire(new URL('../../../tools/webkit/scada/package.json', import.meta.url));
export const {JSDOM} = require('jsdom');
export const {build} = require('esbuild');
