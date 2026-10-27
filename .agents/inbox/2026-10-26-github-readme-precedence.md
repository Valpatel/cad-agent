# A generic .github README overrides the repository's project overview

2026-10-26 evidence: `gh api repos/mvalancy/pcb-agx-thor-can-breakout/readme --jq .path` returned `.github/README.md`; the public repository page displayed only “.github / CI validation and prerelease publication.” The root README existed and was valid Markdown.

Cause: GitHub searches `.github`, root, then `docs` for the landing README. The every-folder generator created a higher-priority generic index. Corrective rule: deliberately omit `.github/README.md` when the root overview should be displayed; keep CI documentation in `.github/workflows/README.md`. Both the generator and release validator now reject the overriding file. Validate the hosted `/readme` API and visible page after publishing, not only local Markdown links.

Source: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes

Limit: this exception is specific to GitHub's README selection; other folders retain their READMEs. It does not establish design correctness.
