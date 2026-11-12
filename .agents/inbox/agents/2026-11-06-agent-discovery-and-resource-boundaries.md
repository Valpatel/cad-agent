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


## Actual installer studies preserve passed and unmet scopes

On 2026-11-07, [Linux fleet job 252 acceptance](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6708675413) verified exact consumer `bf09a8ef9b92e97dd233666bb27b653ba3a843e3` and driver SHA-256 `0e315057789396f68a00d917bd7b926fbb41b4eec7b64f62ec476b659c30fc7d`. The canonical checked block ran twice at supported pinned `v0.26.1` / `02cbc3c9cef53ef34a97fb24c14a133499af91ec`, not a moving default-main assumption. All 13 owned phases exited 0 and settled their groups in the 34-second job. Actual uv receipts changed from `[cad]` to `[cad,site]`; the actual generated reinstall command executed and preserved both. Python 3.12.3, eight Claude skills, ten shared skills, llms200 and the real 17,664 mm³ box smoke were observed. Initial evaluator commands/exits/tails are retained; full initial installer stdout was not recorded, and this is not a model or physical qualification result.

Two bookkeeping mistakes did not justify a second installation. The local submit parser expected `job N`, but the current CLI returned `job=N`; exact structured job/source/alias metadata and read-only status reconciled the single job. Fetched evidence had 0750/0640 modes despite an earlier assumed 0700/0600 claim. Its outer private directory was already 0700; explicit stat/hash readback corrected the owned evidence and relevant parents to 0700/0600 without changing any content. **Rule:** inspect the actual structured response and fetched modes; never resubmit on a local receipt-parser mismatch, and never claim privacy modes from an expected umask alone. Keep the original failed-parser/mode observations and correction.

[Windows run 42384190136](https://github.com/Valpatel/cad-agent/actions/runs/42384190136), independently classified in [6708728215](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6708728215), executed both actual PowerShell 5.1 and 7.6 cases at the same consumer source. Before the final probe, both completed real descendant failure/timeout controls, three canonical checked procedures, actual executable exit3, JSON flattening/real uv handoff, pending-marker completion, `[cad,site]` receipts/import origin, source pin and the real 17,664 mm³ smoke. The original artifact's174 members and digest were verified.

**Both study results remain FAILED/ok:false.** After disabling its own symlink privilege, each disposable child could still create a real symlink. Its strict probe therefore rejected the absent OS-denied case; no Windows error 1314 occurred and automatic denied-link copy fallback was not exercised. This is not a full Windows pass, a demonstrated installer regression or permission to retry the unchanged permissive context. The image build recipes enable Developer Mode, which is relevant context, not a retained readback of that failed machine's registry/effective token. Do not change machine policy, inject an OSError and call it OS evidence, or erase the preceding actual body results. A distinct denied-symlink context requires its own bounded source/procedure review.

The named agent trial is also separate. Read-only `claude auth status --json` returned loggedIn:true with normal OS-user authentication; the same installed command under the evaluator's exact fresh HOME/config returned exit1/loggedIn:false. No credential contents were read or copied, account switched, login requested or relay invented. A deliberately reviewed normal-login fresh project/session may establish a narrower boundary; it must not be labeled a clean OS user or silently replace the historical acceptance. Initialization-only metadata and historical model trials remain distinct from a new current-prompt model run.


### Validate explicit copy without relabeling automatic denial

After the actual permissive-context failure, the bounded scope decision was to retain both failed receipts and their unproved automatic-denial criterion, add no container/volume harness or host-policy change, and prepare one actual Windows `--copy` content/resource/foreign-file consumer. This is a distinct selected run, not an unchanged retry of the denial case. The existing controlled OSError branch test remains exactly controlled evidence.

The proposed `installer_copy_evidence` input runs the actual CLI against a disposable copy of the current eight skills/two roles. Two real `--copy` calls must preserve every instruction/resource hash; an unrelated foreign skill and a same-name foreign collision must survive. Only the owned fixture source is removed before checking copied instructions/resources. External repository-guide links are still outside that standalone scope. The unchanged owned Windows Job Object adapter settles all three commands. Actual execution and independent result acceptance remain pending; syntax or an opt-in skip does not establish these outcomes.


### Compare the complete copied instruction, including its known marker

Independent review of the new explicit-copy consumer at `ff44e89f` reproduced a proof gap: `role.read_text().startswith(expected_role)` accepted an extra appended instruction while the consumer claimed exact instruction content. The correction compares the complete expected role plus only the existing known COPY_MARK trailer. A cheap control uses the real current-kit copy producer, verifies its complete role, appends an unexpected instruction to the disposable copy and requires that same assertion to reject it. This tightens the evidence consumer; it changes no installer behavior or automatic-denial criterion.


## Separate a normal-login flow trial from a clean-user claim

The distinct [explicit-copy run 42386330016](https://github.com/Valpatel/cad-agent/actions/runs/42386330016) completed its Windows job successfully at `d2baa28cc2c36f6d8ef321599f403e584ecd8f7c`. Its original ZIP digest was `7388796b20aa572f62174959eed610395b683e8ef0adf0596a89e4872922a825`; all 14 members matched extracted bytes. Three real CLI commands exited 0/0/1 as expected with active-process counts 0. The source's eight skill instructions plus one bundled reference were exact in both skill namespaces; complete roles plus their known markers, two generated shared roles and both foreign-file controls passed after only the disposable fixture source was removed. A fresh independent reviewer accepted this scope. It is not automatic OS-denial evidence, and both earlier overall failed receipts remain unchanged.

On 2026-11-07, one separately reviewed read-only discriminator used the existing Claude Code 2.1.319 binary with a fresh tool HOME/project and the existing normal login directory. Auth-status metadata and one SDK initialize request succeeded; no model prompt or tool request was sent, and both owned groups were settled before return. The initialize response advertised 45 commands and four agents, including a generic role advertisement, and no cad-agent names. It omitted memory metadata. An advertisement is not evidence of selected model context; missing memory fields remain unknown. Raw account metadata stayed private with actual 0700/0600 readback. The frozen collector SHA-256 was `9c256d2b616be140aab1be50f6e566b231afac67f8f71b3c5482fdcddb746e16`; its only SDK input was `control_request` initialize with `hooks:null`. The client used `--safe-mode --setting-sources "" --tools "" --no-session-persistence --strict-mcp-config --mcp-config '{"mcpServers":{}}'`. [Fresh scoped runtime review](https://github.com/Valpatel/cad-agent/pull/452#pullrequestreview-5813317622) distinguishes this from a model trial. No credential file was copied, linked or opened by the probe; normal CLI authentication and managed policy remain its own behavior.

The existing evaluator now offers an explicit `--normal-auth-config` route for a separately graded current paste/install/CLI flow. It requests SafeMode, empty settings/MCP, a builtin general-purpose agent, bounded file/shell/web tools and the existing normal login. It refuses mixed environment/normal auth, wrong harnesses, failed metadata and nonempty work directories. It resolves the existing CLI directly instead of lending unrelated user-bin commands. It never searches for credential files. The five inert real-process controls validate those boundaries; they are not a model trial.

**Rule:** retain the historical acceptance wording and declare the substitution. SafeMode disables native skill discovery, including newly installed toolkit skills; managed policy may still apply. The normal-login route therefore marks `fresh_session` unknown and excludes it from its score, while grading the existing 12 flow outcomes from transcript/files. It cannot claim a clean OS user, default-harness parity or native skill invocation. A current named model trial still needs exact source/command/runtime/tool/output bounds and independent actual-result review. Use an owned-group collector with an outer deadline below the evaluator's own timeout so a timed-out producer cannot leave descendants while grading or accepting files.

## Grade only after the entire service stops

On 2026-11-12, [independent PR #613 review](https://github.com/Valpatel/cad-agent/pull/613#discussion_r4552450994)
reproduced a new boundary failure: an inert CLI spawned a child with `start_new_session=True`. The initial
collector reported `collector_settled=True` and `usable_trial=True` while that detached child was still alive
inside the grader. No model trial had started. Killing a POSIX process group does not settle a different group.

The corrected collector never grades. An external finalizer binds the recorded cgroup to an explicit owned
service, captures its retained `Result`/`ExecMainStatus`, stops it with `KillMode=control-group`, and checks for
remaining members before reading subject output. A separate probe found that an already unloaded service returns
default success fields; `RemainAfterExit=yes` therefore retains actual status until the finalizer records it.

Evidence: `CAD_EVAL_SYSTEMD_CONTROL=1 python -m pytest -q tests/repo/test_standard_eval_runner.py` reported
`20 passed` on 2026-11-12. The actual service control asserts the detached child is alive after collection,
no result exists yet, and the child is absent before a graded result returns. Default CI explicitly skips this
service-dependent case; mocked state controls are not equivalent evidence. Wrong/active/unknown units and a
nonempty cgroup after stopping fail closed. The existing same-user login and directory-only input boundary do
not isolate hostile code or prevent a deliberately created unrelated service; no such claim is made.

A second independent control at `ffc14cb5` caught late inherited stdout: cached metrics reported zero malformed
lines and a usable trial, while the final transcript contained one malformed line. The [review finding](https://github.com/Valpatel/cad-agent/pull/613#discussion_r4552581625)
requires transcript parsing to move after service teardown as well. The corrected focused suite includes this
ordering control; transcript hashes and metrics must describe the same settled bytes, not different moments.

## A released toolkit checkout can contain its own evaluation answers

On 2026-11-12, the [architecture audit](https://github.com/Valpatel/cad-agent/issues/142#issuecomment-6831782191)
found a preparation boundary that must change before controlled native-CAD trials. Command
`git cat-file -e v0.38.0:tests/fixtures/evaluation/jobs/snapfit-sizing/reference.json` exited 0.
Read-only inspection of `tools/evaluation/standard_eval.py` at `c3010e618b4a06a74cc76970be6fa67f8f075799`
showed `prepare()` checking a clean pinned checkout and placing its entire path in the kit prompt. A clean
revision can therefore include answers, published solved attempts and git history. No model exploit was observed.

**Cause:** runtime and controller evidence share a repository; revision cleanliness is not information isolation.
**Rule:** new controlled studies use an allowlisted, hashed subject bundle and an enforced access boundary, with
real denied-read, traversal, symlink and answer-sentinel controls. Keep provider credentials outside the subject.
The [design/testing contract](../../../docs/practice/standard-evaluation.md#planned-cad-design-evaluations)
deprecates whole-checkout preparation for those studies; it does not claim that a new bundle/runtime is implemented.
**Limits:** v1 remains a disclosed cooperative smoke protocol. Its historical `59441e75` kit predates the shipped
corpus; this finding does not prove those subjects read answers or retrospectively change their records.
