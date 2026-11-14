import {fileURLToPath} from 'node:url';
export const REPO = fileURLToPath(new URL('../../../', import.meta.url));
export const UI = fileURLToPath(new URL('../../../software/cadagent/webkit/scada/ui/', import.meta.url));
export const SIM = fileURLToPath(new URL('../../../software/cadagent/webkit/scada/sim/', import.meta.url));
export const TOOLS = fileURLToPath(new URL('./', import.meta.url));
export const TESTS = fileURLToPath(new URL('../../../tests/webkit/scada/', import.meta.url));
export const FIXTURES = fileURLToPath(new URL('../../../tests/fixtures/scada/', import.meta.url));
