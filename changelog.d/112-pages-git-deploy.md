**Changed**
- The site is built and published by Cloudflare Pages from Git: every push to `main` runs `npm ci && npm run build`,
  the same settings as every other Valpatel Pages site. A Direct Upload project cannot switch, so the `cad-agent`
  project is recreated, Git-connected, under the same name, and the domains and `npm run deploy:site` keep working.
  The new `npm run build` (`tools/pages-build.mjs`) fetches the full history, `origin/main` and `origin/dev`, which
  Cloudflare's clone lacks, then runs the release build.
- `release.yml` only tags and publishes the GitHub release. Its token-gated deploy job is gone, so a green release run
  can no longer hide a skipped deploy. `npm run deploy:site` stays as the by-hand fallback (#112).
