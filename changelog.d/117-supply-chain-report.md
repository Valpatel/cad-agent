**New**
- `tools/resource_audit.py`: a deterministic supply-chain and resource report of what cad-agent depends on, vendors and links to: OSV advisories and malicious packages for Python (newest and lowest allowed releases, and the transitive packages deps.dev resolves) and npm, pins and recorded hashes, vendored files against upstream at the pinned commit, web kit files against the npm tarballs their receipts name, licences, and links that died, moved or redirect elsewhere. The latest run is `research/security-report.md`, with a figure, and `docs/supply-chain.md` explains it (#117).
- CI's new `supply-chain` job (offline, not required) fails a PR into `dev` that adds a dependency, vendored file or catalogue entry without its report row in the description, or with a medium or worse finding; every event also fails on a high finding anywhere. Release PRs into `main` get only that whole-checkout check (#117).
- A weekly `supply-chain.yml` workflow runs the online checks and keeps one "Supply-chain report: open findings" issue current; its report job reads only, and only its issue job can write issues (#117).
- The `cad-supply-chain` skill: when to run the report, how to read it, and what blocks a merge or an adoption (#117).

**Projects must change**
- A PR into cad-agent's `dev` that adds a dependency, vendored file or catalogue entry pastes the table from `python3 tools/resource_audit.py rows --base origin/dev --online` under "Supply chain" in its description (#117).
