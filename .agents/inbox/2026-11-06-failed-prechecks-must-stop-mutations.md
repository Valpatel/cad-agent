# Failed prechecks must stop the command that mutates state

- **Observed, 2026-11-06 UTC:** A root coordinator command placed the premerge Python assertion, live-gates command and GitHub merge on separate shell lines without `set -e` or `&&`. All observed real prechecks and gates passed before #383/#385 merged; no failed guard was bypassed in those actions. The orchestration pattern itself did not enforce the dependency.
- **Harmless control (2026-11-06T10:39:50Z):** `bash -c 'false; printf MUTATION_MARKER'` exited 0 and printed `MUTATION_MARKER`. `bash -c 'false && printf MUTATION_MARKER'` and `bash -c 'set -e; false; printf MUTATION_MARKER'` exited 1 with empty stdout. These controls used a printed marker, no GitHub or filesystem mutation.
- **Cause:** Sequential shell lines do not imply success-dependent execution, and the last command can hide an earlier nonzero exit. A validator that fails correctly is insufficient when its caller proceeds anyway.
- **Corrective rule:** Put dependent precheck/gate/mutation steps in an explicit `&&` chain, or a reviewed script with failure propagation (for subprocess orchestration, `check=True` and no caught-and-ignored failure). Before using an unfamiliar wrapper, make its precheck fail in a harmless control and prove the mutation marker is never reached. Keep actual review, exact-head, CI and live-gate requirements; shell failure propagation supplements them.
- **Limits:** This control establishes Bash's exit propagation for the shown simple top-level forms. `errexit` has exceptions in conditional, pipeline and function contexts; prefer explicit checked control flow there. No repository hook or GitHub protection failure is inferred.

## A release producer can run after a failed preservation guard

**Recurrence, 2026-11-07 UTC:** The v0.27.0 coordinator put an inline Python preservation check, the standard minor-release producer, staging and log display on separate shell lines without checked dependency propagation. The check exited with `AssertionError`; the shell continued, `tools/cut_release.py --minor --date 2026-11-07` produced v0.27.0 and consumed two fragments, and the final log display masked the failure with exit 0. This time a failed guard really was followed by a local mutation.

The guard incorrectly required all non-table symptom-index lines to equal the integration base. Reviewed PR447 had added a blank line and two lesson-link bullets; PR451 added a table row. The source merge was correct, but a validation-assumption failure still had to stop its caller. All changes remained on the owned release worktree: pre-producer HEAD `5a471c0cc917a9f89aea2e1f58dbd9ecaf1ed889` was unchanged, protected dev/main stayed `2aaece3b92e1ac68679782f87931990b30cdeaf1` / `02cbc3c9cef53ef34a97fb24c14a133499af91ec`, and the remote release ref was still the integration base.

Continuation stopped. The corrected read-only proof preserves table rows and their order, takes changed non-table content from its unique source owner, and checks every other source path byte-for-byte. [Independent disposition](https://github.com/Valpatel/cad-agent/issues/446#issuecomment-6708435920) verified all 73 source paths, including 72 single-owner paths, and replayed the standard producer from the immutable pre-producer commit: all five staged paths matched exactly, both fragments were consumed, and dated release history remained byte-identical. The legitimate output was retained rather than reset blindly.

The next mutation was gated by the successful corrected proof in a separate checked tool call. Actual harmless controls of that same conditional pattern returned `checkExit: 9, continued: false` for a failing precheck and one `MUTATION_MARKER` for a successful precheck. Keep orchestration failure separate from product/source defects, propagate the first failed dependency, and inspect preserved state before deciding whether to retain or undo partial work. These controls prove the shown caller; they do not establish that every future command or exception path is guarded.

## A reviewer extraction can execute mutation assignments

**Incident, 2026-11-07 UTC:** During independent operational review of the frozen v0.27.0 dev-merge operator, the reviewer attempted to execute only its read-only definitions and constants. The scratch extractor selected every top-level `ast.Import`, `ast.ImportFrom`, `ast.Assign` and `ast.FunctionDef`, then executed the resulting module. Treating an assignment as inert was wrong: initializers included `first=read()`, the live gate command, `last=read()` and `r=subprocess.run(['gh','pr','merge', ...])`. The mutation assignment executed. The extractor omitted the operator's `with marker.open('x')` and receipt-write expressions, so it also bypassed the intended pre-action attempt marker.

**Actual outcome:** PR453 merged at 2026-11-07 15:19:08 UTC into dev `86fa3e91cd5ab569881c4562343a632bc1714b02`. The actual parents are `2aaece3b92e1ac68679782f87931990b30cdeaf1` and reviewed source `2c2cb9f4ee44be37628aba1f3f6095076a7e98b0`; its tree is exactly reviewed `7f360c52f12226d1a0f2b1e7a4de273a3ad5f96b`. Main remained `02cbc3c9cef53ef34a97fb24c14a133499af91ec`, the owned source worktree remained clean, and `/tmp/cad0270-merge-dev-attempt.json` did not exist. The next explicit read failed because dev had moved, exposing the unexpected mutation. This was not the coordinator executing the reviewed one-shot operator, and no complete normal attempt receipt is claimed.

**Cause:** An AST node-type filter is not a side-effect boundary. Assignments evaluate their right-hand sides; function definitions can also evaluate defaults and decorators. The reviewer did not use a read-only transport fence and violated the role's explicit no-merge instruction, regardless of the resulting tree. The executed source order implies that embedded source/check/live-gate reads returned before the merge, but their raw return values and merge output were not persisted; no complete pre-action receipt is available.

**Response:** The reviewer immediately told the coordinator to stop any operator repeat, admitted the accidental mutation, retained a read-only actual GitHub parent/tree/ref readback plus the selected-node listing, and made no rollback or further repository/ref mutation. Preserve the resulting state; the coordinator independently audits it before promotion. Source review, current CI and correct tree identity do not excuse bypassing ownership or write-ahead receipt boundaries.

**Corrective rule:** Never execute a whole-script extraction merely because selected nodes look like definitions or assignments. Review statically first. For a pure classifier control, construct the small literal inputs explicitly and extract only individually inspected function bodies under a transport that rejects mutation. Validate decorators/defaults and all calls; use literal evaluation for explicit named constants instead of executing arbitrary assignment expressions. A reviewer process must not have an operational `gh pr merge` or ref-write path callable through its test transport. Before any such read-only harness is used, plant a mutation initializer and prove it cannot reach a recorder. Mutation operators remain author-owned and execute once only after their own review and intent receipt.

**Limits:** The independently observed exact merge tree supports preserving this particular result, not a claim that the unsafe extraction was harmless or that all controls executed. This incident does not accept promotion, publication, issue closure or remote retirement. No source file was edited by the reviewer. The coordinator carried this lesson and reviewer guidance through an owned topic PR. The [coordinator readback](https://github.com/Valpatel/cad-agent/issues/446#issuecomment-6708997995) records the actual result and missing evidence.

## A comment must target the comment resource

**Observed, 2026-11-07 UTC:** A reviewer intended to append compiled-preview evidence to Gyropup PR257 but ran
`gh api repos/Valpatel/gyropup/issues/257 -X POST -F body=@<review-file>`. The missing `/comments` segment caused
the PR description to be replaced. A successful command exit did not establish that the intended resource changed.
The reviewer restored its captured description with `gh pr edit 257 --repo Valpatel/gyropup --body-file <original>`
and posted the [intended timeline comment](https://github.com/Valpatel/gyropup/pull/257#issuecomment-6710681099)
to the actual comments collection.

The coordinator independently compared raw API JSON with the author's separately preserved original file:
1,712 original bytes, SHA-256 `c35d107ca6eda2308b5273f6e2608925e6e37cac0a2b3450b5046062a86ce582`;
1,713 restored bytes, SHA-256 `583ba8a6c51350ed10ebcf9d1d5d4590100b44bc56b1f2732def5a9e57f676a4`.
The restored body equals the original plus one terminal newline. All original content is preserved; the raw bytes
are not identical. [Independent disposition](https://github.com/Valpatel/gyropup/pull/257#issuecomment-6710745646).

**Cause and rule:** The resource route, not merely an HTTP method or zero exit, determines the write. Use
`gh pr comment --body-file` or `gh issue comment --body-file` for ordinary timeline comments, and `gh pr review`
for a formal review. Keep the documented inline-review API for actual line comments. Read back the created
comment/review and its target. An intentional description update is a separate operation: preserve the original
raw body, apply the exact intended change, then compare raw API strings rather than stripping whitespace.
On an unexpected write, preserve evidence, stop dependent writes and obtain an independent correction disposition;
do not repeatedly restore from an unverified reconstruction.

**Limits:** The reviewer had not preserved pre-error raw API JSON; the independent author file establishes the
content boundary. This was a metadata-resource selection error, not a demonstrated service defect. No source or
ref change was part of the incident. Product checks, merge gates and publication remain separate. No live destructive
regression is justified for this CLI-selection mistake; the existing reviewer role and publication playbook carry
the procedure.

## A successful merge does not make a failed auxiliary preflight pass

**Recurrence, 2026-11-11 UTC:** The coordinator's auxiliary PR531 preflight asserted
`len(statusCheckRollup) == 20` and raised `AssertionError`. A separate next shell line still invoked
`gh pr merge`; that command exited 0, masking the preceding failure. This operator sequence is retained as
reported incident evidence; GitHub cannot reconstruct its local shell exit propagation.

Independent read-only GitHub readback at `2026-11-11T01:42:39Z` used:

```text
gh pr view 531 --repo Valpatel/cad-agent --json headRefOid,mergeCommit,mergedAt,statusCheckRollup,url
gh api repos/Valpatel/cad-agent/issues/531/timeline --paginate
gh run view 42939737859 --repo Valpatel/cad-agent --json event,headSha,createdAt,updatedAt,jobs
```

Actual head was `6fc79219a2ee313a728b26f05641561a4685f71d`. The `ready_for_review` event occurred at
`01:32:49Z`; the additional `pull_request_target` Gates run started at `01:32:52Z`, and its successful
`gates` job completed at `01:33:06Z`. The rollup contained **21 successful instances**, all completed or
posted before the `01:39:22Z` merge to `92fd8cf6156566d1291ec43bc00d7377f94e8dbe`.
[PR531](https://github.com/Valpatel/cad-agent/pull/531) and
[the additional run](https://github.com/Valpatel/cad-agent/actions/runs/42939737859) support that timing.
No failing required gate was bypassed; the failed auxiliary assertion and unsafe caller are real failures.
This repeats the existing [duplicate-check lesson](publish/2026-11-07-release-guards-need-current-boundaries.md#count-required-names-without-dropping-duplicate-check-instances).

**Cause:** A total-count assumption rejected an additional successful wrapper instance. Independent shell
lines then allowed a mutation after a failed dependency, and the last exit code hid the first failure.
The assertion's mistaken premise did not authorize ignoring its nonzero result.

**Corrective rule:** Identify required contexts and their expected source/head, require their successful states,
and inspect every applicable current check instance, including duplicates. Do not accept an absent required
context or discard an unsuccessful duplicate to meet a name/count expectation. Persist the exact preflight
inputs, checked identities, live-gate output and exit status before mutation. Put all assertions and the
mutation inside the same checked program, using checked subprocess calls, or launch mutation separately only
after inspecting the preflight's actual zero exit and receipt. Never append mutation to an unchecked multiline
shell sequence. Preserve the original failure and resulting state for independent disposition.

**Limits:** This is an operational documentation correction, not a new gate implementation, a release cut,
or proof that every operator is now fail-closed. The GitHub readback verifies states and timing, while the
coordinator supplies the local assertion/fallthrough evidence. Current CI, independent exact-head review and
live repository gates remain separate requirements; publication is not established by merge success.
