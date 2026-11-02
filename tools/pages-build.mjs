#!/usr/bin/env node
// `npm run build`: the production site build, as Cloudflare Pages runs it on every push to `main`.
// The Pages project is Git-connected: build command `npm ci && npm run build`, output `dist` (wrangler.toml), the
// same settings as every other Valpatel Pages site. Preview deployments are off, so only `main` publishes.
//
// Cloudflare's clone may be shallow and has no `origin/main` or `origin/dev`. `build-site.mjs --release` needs both:
// full history, so each page shows when it really changed, and HEAD on a reviewed branch. This fetches what is
// missing from the public repository, then runs the release build. Run locally it does the same in a checkout that
// already has them, so it is safe anywhere.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = process.env.CAD_AGENT_REPO_URL || 'https://github.com/Valpatel/cad-agent.git';
const git = (...a) => execFileSync('git', a, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const has = ref => { try { git('rev-parse', '--verify', '--quiet', ref); return true; } catch { return false; } };

if (git('rev-parse', '--is-shallow-repository') === 'true') {
  console.log('pages-build: shallow clone, fetching full history');
  git('fetch', '--quiet', '--unshallow', REPO);
}
const missing = ['main', 'dev'].filter(b => !has(`refs/remotes/origin/${b}`));
if (missing.length) {
  console.log(`pages-build: fetching origin/${missing.join(', origin/')}`);
  git('fetch', '--quiet', REPO, ...missing.map(b => `+refs/heads/${b}:refs/remotes/origin/${b}`));
}
execFileSync(process.execPath, [resolve(root, 'tools/build-site.mjs'), '--release'], { cwd: root, stdio: 'inherit' });
