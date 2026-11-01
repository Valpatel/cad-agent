# Security policy for vendored code

Third-party code under `vendor/` is the main way we could be attacked through this repository: a compromised upstream
or a malicious update. These rules apply to every import and every weekly update.

1. **Pinned by commit.** `vendor/manifest.json` holds full commit SHAs. Branches and tags are never trusted.
2. **Fetched without running anything.**
   - `tools/vendor_sync.py` clones with git hooks disabled and the file/ext protocols blocked.
   - It exports with `git archive`, so there is no `.git`, no submodules and no symlinks.
   - It never runs upstream install scripts, setup hooks or CI.
3. **Never straight to main.** Imports land on a `vendor-update/<name>-<sha>` branch and are merged only after review.
4. **Red-flag scan on every change.**
   - `tools/security_scan.py` reports findings that are new against the reviewed baseline (`vendor/baselines/`).
   - A new HIGH finding (decoded exec, pipe-to-shell, credential access, install hooks, binaries, encoded blobs) blocks
     the merge until a reviewer explains it.
   - MEDIUM findings (network, subprocess, telemetry, dependency files) are read for intent.
5. **Exclusions are recorded.** Upstream CI and maintainer scripts that touch tokens, committed binaries and benchmark
   harnesses that handle API keys are excluded in the manifest, each with a reason.
6. **Our patches are re-applied on every import** from `vendor/patches/<name>/`. For example, text-to-cad's telemetry,
   update check and outbound API are disabled at the source.
7. **Sandboxed execution.** Vendored code is tested in Docker with no network, a read-only root, a non-root user, all
   capabilities dropped, no-new-privileges and no host home directory mounted.
8. **Dependencies.** Python dependencies are installed from hash-locked requirement files (`--require-hashes`) into
   isolated environments. A dependency change is itself a finding to review.
9. **Supply-chain report.** `tools/resource_audit.py` checks dependencies, vendored code (pins, recorded hashes,
   drift from upstream at the pinned commit, licences) and the links we publish; CI runs its offline checks on every
   PR and a weekly workflow runs the online ones and keeps one issue current. When to run it and what blocks a merge:
   [`skills/cad-supply-chain`](skills/cad-supply-chain/SKILL.md). A clean report is not proof of safety.

The initial baselines (2026-10-24) were accepted after every HIGH finding was read. Those findings were CI scripts,
docs and test fixtures, which are now excluded or documented. text-to-cad's runtime network and telemetry code was also
reviewed. Not every MEDIUM finding from the initial import was read line by line. From now on, each update reports only
what is new.
