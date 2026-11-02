**Changed**
- The site deploys itself. Cloudflare Pages is connected to the repository and builds and publishes
  cad-agent.valpatel.com and cad-agent.gyropup.com on every push to `main`, with `npm ci && npm run build`, the same
  settings as every other Valpatel Pages site. The new `npm run build` (`tools/pages-build.mjs`) fetches the full
  history and `origin/main` and `origin/dev`, which Cloudflare's clone lacks, then runs the release build.
  `release.yml` only tags and publishes the GitHub release now; its token-gated deploy job is gone, so a green release
  run can no longer hide a skipped deploy. `npm run deploy:site` stays as the by-hand fallback (#112).
