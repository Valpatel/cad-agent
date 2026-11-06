# Check discovered names and resource containment separately

On 2026-11-06, moving the canonical kit into `.agents/skills/` and `.agents/agents/` exposed two different contracts. Native discovery can succeed while a copied instruction still links outside its installed resources. Search of the existing process lessons and this symptom index found no earlier copy-mode resource note.

**Evidence:** [PR #387 component receipt](https://github.com/Valpatel/cad-agent/pull/387#issuecomment-6682286026), immutable source `95b0745881e8f8e480b02fe2a5d0e121c5e0f652`:

- Codex 0.166.0 app-server `initialize` followed by `skills/list` with `forceReload=true`: 19 global/system skills became 27 with the repository kit. All eight repository skills were enabled. Five names appeared at both repository and user scope; the probe did not infer a winner. Operational notes did not become skills.
- Claude Code 2.1.318 SDK control `initialize`, without a user prompt or tools: `.agents/` alone added no commands. Explicit `--plugin-dir <repository>` with the native manifest added exactly eight `cad-agent:<skill>` commands and two named roles alongside existing globals.
- A complete `git archive` cache retained 5,807 files / 80,911,190 bytes, with equal per-file sizes and SHA-256 values. After deleting its fixture source, actual native initialization still found those eight commands and two roles; all 19 local kit links stayed inside the cache. Removing a cached guide caused the existing link reader to reject it.
- Actual `cad-agent agents install --copy` retained exact skill instructions, bundled resources and role bodies after removing the fixture source. Its 18 external guide links did not resolve from the copied profiles. The same actual old-code install at `c45b6dfaf227f85715a9aa39c5063cb150153103` produced the same 18 failures: this limitation predates the canonical move.

**Cause:** native plugin mode copies the whole plugin root; the existing copy installer copies individual instructions and their bundled files. Both discover names, but their resource boundaries differ. A successful initialization or retained-checkout link check cannot prove standalone guide availability.

**Rule:** enumerate the expected nonempty names in the real supported harness, distinguish global duplicates, then remove only a disposable fixture source and validate resources in the installed mode. Preserve foreign user links. Test a missing resource through the same consumer. State whether a result proves exact instructions, retained-checkout links, or a self-contained native cache; do not call all three offline installation.

**Limits:** these probes sent no model prompt or tool request. Only the installed Codex and Claude versions were exercised; other adapter formats are not runtime discovery evidence. Copy-mode repository guides remain a distribution gap under #282; no documentation bundle or new installer framework was added. Later software-owner moves require fresh final-head packaging/cache evidence; this receipt is scoped to the named component.

## Exercise custom checkout names when repairing owned links

On 2026-11-06, a pre-merge probe at `fbb59c8931673340ea766b1211686d8fd164c774` found that `_kit_link` returned false for a dangling old `skills/` link inside a live valid checkout named `toolkit`. The same install left it as a conflict. The existing fleet 216 real editable update had used `cad-agent-updated`, whose name happened to satisfy the removed-worktree fallback; it did not establish the supported custom `--dir` contract.

The existing install/CLI consumer was expanded across named, unbranded and space-containing checkouts; old/current source and asset layouts; and existing/missing targets. The original classifier failed eight cases while 22 passed. Complete live kits must be identified by the package and both instruction roots before falling back to the removed-worktree name rule. Source-only, asset-only and non-kit lookalikes must remain foreign. The corrected existing agent-kit, installer and update suites passed 69 tests with one optional PowerShell parser skipped.

**Rule:** a migration must preserve a supported custom directory independently of branding. Exercise the actual old editable CLI update/reinstall/relink path and inspect all intended link targets, source origins and same-name foreign conflicts. An update exit code alone is insufficient: the old update can report success after the relink subprocess reports conflicts. Keep the named baseline and failed unbranded control as separate observations.

**Limits:** recognizing a still-live kit does not identify an arbitrarily named checkout after the entire checkout is removed. The existing removed-worktree fallback is unchanged; this correction does not adopt foreign instruction trees or broaden standalone copy resources.
