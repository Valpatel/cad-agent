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
