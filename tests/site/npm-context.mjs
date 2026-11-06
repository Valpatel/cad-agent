/** Test-only dependency context: site npm packages resolve beside their owning manifest, without root wrappers. */
import { createRequire } from 'node:module';
const siteRequire = createRequire(new URL('../../tools/site/package.json', import.meta.url));
export const YAML = siteRequire('yaml');
export const { chromium, webkit } = siteRequire('@playwright/test');
