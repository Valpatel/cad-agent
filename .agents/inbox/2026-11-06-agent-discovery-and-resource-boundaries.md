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


## Installer guards are not full platform installation evidence

On 2026-11-07, the #282 acceptance audit at `2aaece3b92e1ac68679782f87931990b30cdeaf1` compared the actual owner decisions, current installers and their consumers. Merged [#293](https://github.com/Valpatel/cad-agent/pull/293) deliberately installs everything and reports unmet Needs; it declines the profile split. [#298](https://github.com/Valpatel/cad-agent/pull/298) delivered the thin installers and update handoff, with explicit later Windows and real-receipt follow-ups in [#282](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6573509994).

**Observed commands and output:** read-only `rg` inspection of `tests/cli/test_installer.py`, `tests/cli/test_update.py`, `tests/cli/test_agentkit.py`, `tools/quickstart_eval.py` and `.github/workflows/ci.yml` found real checksum/cleanup PowerShell guards with inert download/child fixtures, constructed uv receipts, a stand-in POSIX uv, and a monkeypatched symlink failure. The Windows job requires `pwsh`; it does not execute the full PowerShell 5.1/7 installer body. These are useful controls, but none establishes real uv reinstall, Windows self-replacement or an OS-denied symlink. No installation was run by this audit.

Historical evidence remains valid at its named source: [fleet job 91](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6575180970) installed live v0.15.0 twice and exported the real box. [#280](https://github.com/Valpatel/cad-agent/pull/280) retained actual older multi-command agent trials. Neither proves the later current checked entrypoint and eight-word agent flow. Do not replace these dated results with a claim that no earlier real trial existed.

**Rule:** exercise the canonical checked entrypoint in an empty owned environment, twice, then inspect the actual uv receipt before and after an extras-triggered reinstall. On Windows execute the unchanged installer body with both named PowerShell versions, observe the real exit-3/reinstall-command handoff and final state, and distinguish an actual OS-denied symlink from injected failure. Preserve full commands, exits, logs, source/runtime pins and failures before assertions. Never change machine policy or an existing user's environment to obtain a pass.

**Pending #282 plan:** one bounded CPU-fleet Linux run using the existing evaluator and a small `site` extra; a separate real Windows consumer for the body/handoff/fallback; and one named Claude/Opus clean-session trial if its explicitly supplied authentication is available. The ordinary fast guard/unit tests stay useful and unchanged in meaning. Heavy downloads and CAD smoke run on fleet/CI, not the shared workstation. A missing named harness/authentication or permissive Windows symlink policy is an unmet criterion, not a passed substitute. Commands/source require independent review before these runs; this paragraph records a plan, not results.

**Limits:** copied instructions and their bundled resources remain distinct from a standalone repository-guide bundle, as recorded above. No profile feature, new installer framework, recurring dependency campaign, machine-wide privilege change, implicit credential lookup or broader multi-model benchmark is authorized by this evidence plan. Current model trials must retain the evaluator's isolation limits; a fresh HOME alone is not a container.


### The fresh-session grader must read the current instruction owner

The same 2026-11-07 audit found `quickstart_eval._kit_skills()` still selecting `skills/*/SKILL.md` and `agents/*.md` from the old root. The real new control `python -m pytest -q tests/repo/test_agent_prompt.py -k preloaded_current_canonical` failed before correction: it found an empty name set despite a planted current `.agents/skills/design-process/SKILL.md` and `.agents/agents/cad-resume.md`. This could let the grader's initial loaded-skill check miss a preloaded current kit. No actual model transcript is claimed to have exploited this gap.

Select the canonical `.agents` instruction owner for current clones; use the old root only when grading a genuinely old clone without that owner. The regression feeds the actual grader an otherwise clean initialization, then preloads each current skill/role name and requires rejection. It also preserves a historical-layout positive. This repairs the evidence consumer before the planned trial; it is not fresh-agent acceptance itself.


### Keep real Windows evidence opt-in and preserve policy boundaries

The #282 consumer uses the existing CI workflow's explicit `installer_evidence` dispatch input, default false. Ordinary PR runs retain the fast guard job; a deliberately reviewed dispatch runs its actual body study in separate PowerShell 5.1 and 7 test cases within the same job. The consumer executes the canonical checked download and unchanged installer body twice in an owned USERPROFILE/AppData/TEMP, then makes a real installed `cad-agent.exe update --extras site` return exit 3. A third canonical call must execute the actual JSON/uv handoff, clear the pending marker and retain the real receipt's `[cad,site]` extras. Source/import origin and the real CAD box smoke are checked separately. These are proposed assertions until actual CI receipts are accepted.

For the copy fallback, a separate disposable Python child disables only its own `SeCreateSymbolicLinkPrivilege`. It changes no machine registry, Developer Mode, account/group membership or runner process token. The actual `Path.symlink_to` must fail with Windows error 1314 before the real `agentkit.install` copies instructions; an injected exception is not used. If existing Developer Mode still permits symlinks, the study fails and the criterion stays unproved rather than changing policy to force a pass. Foreign instructions must survive, and generated/shared names remain checked. This child-level privilege reduction needs independent operational review before dispatch; no Windows run has occurred yet.


### Settle owned installer descendants before saving a final result

Independent pre-execution review of the proposed Linux driver found that `subprocess.run(timeout=...)` settles only its direct child. The existing evaluator starts shell/installer/uv trees, so writing a done marker immediately after that timeout could race active descendants. No fleet install had started. The corrected finite collector reuses the already reviewed Linux subreaper/process-group pattern, masks INT/TERM through spawn/handle capture, restores the child's mask, and kills/reaps the owned group even after its leader exits. A 2,500-second study deadline leaves margin before the 45-minute scheduler wall. Final results state whether the group is actually quiescent; primary failures survive record failures.

The actual Linux helper controls passed for normal unmasked children, a leader exiting with a live grandchild, timeout with TERM-ignoring descendants, pending TERM during spawn capture, and pending TERM plus a phase-record failure. These are process-lifecycle controls only: they did not download/install anything or exercise CAD. They do not supply Linux installer acceptance.

The real Windows consumer uses a test-only anonymous Job Object with kill-on-close and no breakaway permission. A trusted stdlib Python trampoline must join that object before spawning the unchanged installer/native command; only its inherited job handle is lent. The owner bounds the wait, settles the trampoline and confirms active-process count zero before success. Refused nested-job assignment fails closed. The manually selected Windows run must first execute real child/grandchild failure and timeout controls through this exact adapter. Until those and the actual platform receipts run, syntax checks and the ordinary skipped opt-in test are not Windows lifecycle acceptance.
