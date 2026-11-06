#!/usr/bin/env node
// `npm --prefix tools/site run build`: the production site build entry.
// The Git-connected Pages project publishes only main, with previews off and repository-root dist output.
// Moving this entry does not update its external build command; the coordinated transition is tracked in #362.
//
// Cloudflare's clone may be shallow and has no `origin/main` or `origin/dev`. `build-site.mjs --release` needs both:
// full history, so each page shows when it really changed, and HEAD on a reviewed branch. This fetches what is
// missing from the public repository, then runs the release build. Run locally it does the same in a checkout that
// already has them, so it is safe anywhere.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
// CAD_AGENT_REPO_URL points the fetch at a mirror or fork (for testing); unset, it is the public repository.
const REPO = process.env.CAD_AGENT_REPO_URL || 'https://github.com/Valpatel/cad-agent.git';
const git = (...a) => execFileSync('git', a, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const has = ref => { try { git('rev-parse', '--verify', '--quiet', ref); return true; } catch { return false; } };

const shallow = git('rev-parse', '--is-shallow-repository') === 'true';
const missing = ['main', 'dev'].filter(b => !has(`refs/remotes/origin/${b}`));
if (shallow || missing.length) {
  // One fetch: full history (if shallow) and both branches, into refs/remotes/origin/*. It never moves HEAD, so the
  // commit built is the one Cloudflare checked out. A failed fetch throws, the build fails, and the live site stays.
  console.log(`pages-build: fetching ${shallow ? 'full history and ' : ''}origin/main and origin/dev`);
  git('fetch', '--quiet', ...(shallow ? ['--unshallow'] : []), REPO,
      '+refs/heads/main:refs/remotes/origin/main', '+refs/heads/dev:refs/remotes/origin/dev');
}
execFileSync(process.execPath, [resolve(root, 'tools/site/build-site.mjs'), '--release'], { cwd: root, stdio: 'inherit' });
